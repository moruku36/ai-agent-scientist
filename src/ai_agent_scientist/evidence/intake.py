'''Offline explicit-path intake of one existing run (standard library only).

Only the explicit paths given are opened. Input validation refuses before any
write. Bytes are then stored unchanged through import_existing_run / BlobStore,
every blob is re-read and compared, and a safe JSON-compatible summary is built.
I/O, digest or readback failures can happen after writes and may leave a subset
of immutable blobs: reconcile, do not retry blindly. Caller labels are not
authenticated. Final-component symlinks, non-regular files and oversize inputs
are refused; parent directories are trusted. Logs are never parsed or echoed.
'''
from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from typing import Optional

from .blob_store import BlobStore, BlobStoreError, _valid_digest
from .existing_run import (
    ImportRefused,
    MAX_ITEMS,
    MAX_MANIFEST_BYTES,
    MAX_TOTAL_BYTES,
    import_existing_run,
)
from .json_blob import InvalidJSONBlob, parse_json_bytes

__all__ = ['SUMMARY_VERSION', 'STAGES_VERSION', 'STAGES_VERSION_V2', 'IntakeResult', 'intake_paths']

SUMMARY_VERSION = 'intake-summary/1'
STAGES_VERSION = 'intake-stages/1'
STAGES_VERSION_V2 = 'intake-stages/2'
MAX_STAGES_BYTES = 1 << 16
MAX_COUNT = 10**9

_OK = ('started', 'failed', 'not_started', 'unknown')
_RESULTS = {
    'gpu_environment': _OK,
    'model_launches': _OK,
    'tests_collected': ('collected', 'failed', 'not_started', 'unknown'),
    'test_bodies_executed': ('executed', 'failed', 'not_started', 'unknown'),
    'patch_recovery': ('recovered', 'failed', 'not_started', 'unknown'),
    'test_pass': ('passed', 'failed', 'not_started', 'unknown'),
}
_COUNTED = frozenset(('model_launches', 'tests_collected', 'test_bodies_executed'))
_REASONS = frozenset(('none', 'not_started', 'interrupted', 'unavailable', 'unknown'))
_E_KEYS = frozenset(('stage', 'result', 'count', 'stop_reason', 'log_ids'))
_OUTCOME_STAGES = ('startup', 'inference', 'tool_handling', 'output_verification')
_OUTCOME_RESULTS = ('success', 'failure', 'not_run', 'unknown')
_OUTCOME_KEYS = frozenset(('stage', 'result', 'log_ids'))
_VERDICTS = ('exact_match', 'formatting_mismatch', 'numeric_mismatch')


@dataclass(frozen=True)
class IntakeResult:
    imported: object  # ExistingRunImport
    stages_sha256: Optional[str]
    summary: dict


def _need(condition: bool, reason: str) -> None:
    if not condition:
        raise ImportRefused(reason)


def _read(path: object, cap: int) -> bytes:
    need = hasattr(os, 'O_NOFOLLOW') and hasattr(os, 'O_NONBLOCK')
    _need(need, 'platform lacks required POSIX primitives')
    _need(isinstance(path, (str, os.PathLike)), 'path must be str or PathLike')
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, 'O_CLOEXEC', 0)
    fd = None
    data = b''
    ok = True
    try:
        fd = os.open(path, flags)
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > cap:
            ok = False
        else:
            chunks = []
            left = cap + 1
            while left > 0:
                chunk = os.read(fd, min(65536, left))
                if not chunk:
                    break
                chunks.append(chunk)
                left -= len(chunk)
            data = b''.join(chunks)
            ok = len(data) <= cap
    except (OSError, ValueError):
        ok = False
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                ok = False
    _need(ok, 'input is not a bounded regular file')
    return data


def _decode(data: bytes, reason: str) -> object:
    doc = None
    ok = True
    try:
        doc = parse_json_bytes(data)
    except InvalidJSONBlob:
        ok = False
    _need(ok, reason)
    return doc


def _profile(doc: object, log_ids: dict) -> dict:
    _need(type(doc) is dict and type(doc.get('artifacts')) is list, 'manifest shape')
    _need(type(doc.get('target')) is dict, 'manifest target shape')
    want = {'candidate': 'candidate', 'config': 'config'}
    want.update({i: 'log' for i in log_ids})
    seen = {}
    for entry in doc['artifacts']:
        _need(type(entry) is dict and type(entry.get('id')) is str, 'artifact entry')
        _need(entry['id'] not in seen, 'duplicate artifact id')
        seen[entry['id']] = entry
    _need(set(seen) == set(want), 'artifact ids differ from the supplied mapping')
    _need(all(seen[i].get('kind') == k for i, k in want.items()), 'artifact kind')
    target = doc['target']
    _need(
        seen['candidate'].get('source') == target and seen['config'].get('source') == target,
        'candidate and config must declare the target identity',
    )
    return seen


def _parse_stages(data: bytes, target: dict, logs: set) -> dict:
    sdoc = _decode(data, 'stages are not strict JSON')
    _need(
        type(sdoc) is dict
        and set(sdoc) == {'version', 'target', 'stages'}
        and sdoc['version'] in (STAGES_VERSION, STAGES_VERSION_V2)
        and type(sdoc['stages']) is list,
        'stages shape',
    )
    outcome_stages = _OUTCOME_STAGES if sdoc['version'] == STAGES_VERSION_V2 else ()
    _need(len(sdoc['stages']) <= len(_RESULTS) + len(outcome_stages), 'too many stages')
    _need(sdoc['target'] == target, 'stages target differs from manifest target')
    out = {}
    for e in sdoc['stages']:
        _need(type(e) is dict and type(e.get('stage')) is str, 'stage entry keys')
        name = e['stage']
        _need(name not in out and (name in _RESULTS or name in outcome_stages), 'stage name')
        if name in _RESULTS:
            _need(set(e) == _E_KEYS, 'stage entry keys')
            _need(type(e['result']) is str and e['result'] in _RESULTS[name], 'stage result')
            count = e['count']
            if name in _COUNTED:
                _need(count is None or (type(count) is int and 0 <= count <= MAX_COUNT), 'stage count')
            else:
                _need(count is None, 'count only for launches and tests')
            _need(e['result'] != 'unknown' or count is None, 'unknown result has no count')
            _need(type(e['stop_reason']) is str and e['stop_reason'] in _REASONS, 'stop reason')
        else:
            keys = _OUTCOME_KEYS
            if name == 'output_verification' and 'verdict' in e:
                keys = keys | {'verdict'}
            _need(set(e) - {'declared_evidence_sha256'} == keys, 'stage entry keys')
            _need(e['result'] in _OUTCOME_RESULTS, 'stage result')
            evidence_sha = e.get('declared_evidence_sha256')
            _need(evidence_sha is None or _valid_digest(evidence_sha), 'invalid declared evidence digest')
            verdict = e.get('verdict')
            _need(
                verdict is None
                or (verdict in _VERDICTS and e['result'] in ('success', 'failure')),
                'invalid output verification verdict',
            )
        ids = e['log_ids']
        _need(type(ids) is list and len(ids) <= 8, 'stage log ids')
        _need(all(type(i) is str and i in logs for i in ids), 'stage log id is not a target log')
        _need(len(set(ids)) == len(ids), 'duplicate stage log id')
        out[name] = e
    return out


def _ident(i) -> dict:
    return {
        'run_id': i.run_id,
        'candidate_sha256': i.candidate_sha256,
        'notebook_version': i.notebook_version,
    }


def _summary(imp, stages: dict, stages_sha: Optional[str]) -> dict:
    by_id = {a.id: a for a in imp.artifacts}
    results = {}
    for cs in imp.current:
        entry = {'state': 'UNKNOWN' if cs.defaulted else cs.state}
        if cs.category == 'official' and cs.state == 'scored' and cs.score is not None:
            obs = [o for o in imp.observations if o.category == 'official' and o.source == imp.target]
            entry['score'] = cs.score
            entry['score_provenance'] = {
                'artifact_sha256': by_id[obs[0].source_artifact_id].sha256,
                'source': _ident(obs[0].source),
            }
        results[cs.category] = entry
    shown = []
    for name in _RESULTS:
        e = stages.get(name)
        if e is None:  # missing stage: nothing was asserted
            shown.append({'stage': name, 'result': 'UNKNOWN', 'count': None,
                          'stop_reason': 'unknown', 'logs': []})
        else:  # explicit entry (incl. unknown) keeps its stated reason and logs
            shown.append({'stage': name,
                          'result': 'UNKNOWN' if e['result'] == 'unknown' else e['result'],
                          'count': e['count'], 'stop_reason': e['stop_reason'],
                          'logs': [by_id[i].sha256 for i in e['log_ids']]})
    cfg = by_id['config']
    stage_results = {}
    for name in _OUTCOME_STAGES:
        e = stages.get(name, {})
        result = e.get('result', 'unknown')
        stage_results[name] = {
            'result': 'UNKNOWN' if result == 'unknown' else result,
            'verdict': e.get('verdict'),
            'declared_evidence_sha256': e.get('declared_evidence_sha256'),
            'logs': [by_id[i].sha256 for i in e.get('log_ids', ())],
        }
    return {
        'format': SUMMARY_VERSION,
        'target': _ident(imp.target),
        'candidate': {'sha256': by_id['candidate'].sha256},
        'config': {'sha256': cfg.sha256, 'declared_identity': _ident(cfg.source)},
        'manifest_sha256': imp.manifest_sha256,
        'stages_sha256': stages_sha,
        'artifacts': [
            {'kind': a.kind, 'sha256': a.sha256, 'size': a.size, 'git_comparison': a.git_comparison}
            for a in imp.artifacts
        ],
        'results': results,
        'stages': shown,
        'stage_results': stage_results,
        'verified_readback': True,
        'note': 'caller-asserted labels; not authenticated; UNKNOWN is not proof of not run',
    }


def intake_paths(store, manifest_path, candidate_path, config_path, log_paths, stages_path=None):
    '''Read explicit files, validate, store unchanged, verify readback, summarize.'''
    _need(isinstance(store, BlobStore), 'store must be a BlobStore')
    _need(type(log_paths) is dict and len(log_paths) <= MAX_ITEMS - 2, 'log paths')
    _need(
        all(type(k) is str and k and k not in ('candidate', 'config') for k in log_paths),
        'log ids',
    )
    cap = store.max_blob_bytes
    total = 0

    def take(path: object, limit: int) -> bytes:
        nonlocal total
        data = _read(path, min(limit, cap))
        total += len(data)
        _need(total <= MAX_TOTAL_BYTES, 'inputs exceed the aggregate cap')
        return data

    manifest = take(manifest_path, MAX_MANIFEST_BYTES)
    supplied = {'candidate': take(candidate_path, cap), 'config': take(config_path, cap)}
    for log_id, path in log_paths.items():
        supplied[log_id] = take(path, cap)
    stages_bytes = None if stages_path is None else take(stages_path, MAX_STAGES_BYTES)

    mdoc = _decode(manifest, 'manifest is not strict JSON')
    seen = _profile(mdoc, log_paths)
    target = mdoc['target']
    stages = {}
    if stages_bytes is not None:
        logs = {i for i, a in seen.items() if a['kind'] == 'log' and a['source'] == target}
        stages = _parse_stages(stages_bytes, target, logs)

    imp = import_existing_run(store, manifest, supplied)  # validates, then writes
    stages_sha = None
    if stages_bytes is not None:
        stages_sha = hashlib.sha256(stages_bytes).hexdigest()
        _need(store.put(stages_bytes) == stages_sha, 'store digest mismatch')
    for art in imp.artifacts:
        _need(store.get(art.sha256) == supplied[art.id], 'readback mismatch')
    _need(store.get(imp.manifest_sha256) == manifest, 'readback mismatch')
    if stages_sha is not None:
        _need(store.get(stages_sha) == stages_bytes, 'readback mismatch')
    return IntakeResult(imp, stages_sha, _summary(imp, stages, stages_sha))


def _main() -> None:
    import argparse
    import json
    from pathlib import Path

    class IntakeParser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, 'intake: invalid arguments (see --help)\n')

    parser = IntakeParser(
        prog='python -m ai_agent_scientist.evidence.intake',
        description='Import existing run evidence from explicit paths and print its JSON summary.',
        allow_abbrev=False,
    )
    parser.add_argument('--store', required=True, help='existing private blob directory')
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--config', required=True)
    parser.add_argument('--log', action='append', nargs=2, metavar=('ID', 'PATH'), default=[])
    parser.add_argument('--stages')
    args = parser.parse_args()

    log_paths = dict(args.log)
    if not args.store or len(log_paths) != len(args.log):
        parser.error('empty store path or duplicate log id')
    try:
        store = BlobStore(Path(args.store), max_blob_bytes=MAX_TOTAL_BYTES)
        result = intake_paths(store, args.manifest, args.candidate, args.config, log_paths, args.stages)
    except ImportRefused as exc:
        parser.exit(1, f'intake: {exc.reason}\n')
    except BlobStoreError:
        parser.exit(1, 'intake: blob storage failed\n')
    print(json.dumps(result.summary))


if __name__ == '__main__':
    _main()

'''Offline importer for already-existing run evidence (standard library only).

The caller supplies bytes that were already fetched or read, plus a closed
local manifest ('existing-run-import/1'). The importer never resolves paths
or URLs, never imports or executes supplied code, never normalizes bytes and
never parses logs. It stores every artifact unchanged in a BlobStore and then
stores the original manifest bytes last. That ordering is not a completion
marker or a receipt.

The manifest is a separate local helper contract. It does not extend the
run-record schema. Identities, observations, timings and environment values
are caller-asserted labels. They are not authenticated. A run id is a
caller-chosen globally namespaced label (shape-checked only); a config
identity is the declared source identity of the config artifact, never
inferred from a candidate hash.

I/O: all validation happens before any write, so a refusal there leaves no
writes. There is no transaction after that. A storage or integrity error can
leave any subset of immutable blobs, including the manifest blob. Do not
retry blindly: reconcile the original inputs against the installed blobs.
'''
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Optional

from .blob_store import BlobStore
from .json_blob import InvalidJSONBlob, parse_json_bytes

__all__ = [
    'FORMAT_VERSION',
    'MAX_MANIFEST_BYTES',
    'MAX_TOTAL_BYTES',
    'MAX_ITEMS',
    'MAX_STRING_BYTES',
    'ImportRefused',
    'Identity',
    'ImportedArtifact',
    'Observation',
    'Timing',
    'Environment',
    'CategorySummary',
    'ExistingRunImport',
    'git_blob_sha1',
    'import_existing_run',
]

FORMAT_VERSION = 'existing-run-import/1'
MAX_MANIFEST_BYTES = 1 << 20
MAX_TOTAL_BYTES = 16 << 20
MAX_ITEMS = 64
MAX_STRING_BYTES = 1024

_KINDS = frozenset(('candidate', 'config', 'log', 'evidence', 'environment'))
_CPU_REAL = frozenset(('not_run', 'completed', 'failed', 'unknown'))
_OFFICIAL = frozenset(('not_obtained', 'submitted', 'scored', 'unknown'))
_STATES = {
    'cpu_simulation': _CPU_REAL,
    'real_model': _CPU_REAL,
    'official': _OFFICIAL,
}
_DEFAULT_STATE = {
    'cpu_simulation': 'not_run',
    'real_model': 'not_run',
    'official': 'not_obtained',
}
_CATEGORY_ORDER = ('cpu_simulation', 'real_model', 'official')
_PHASES = frozenset(('model_execution', 'gpu_preparation', 'evaluation', 'cleanup'))
_HEX = frozenset('0123456789abcdef')

_TOP_KEYS = frozenset(('version', 'target', 'artifacts', 'observations', 'timings', 'environment'))
_ID_KEYS = frozenset(('run_id', 'candidate_sha256', 'notebook_version'))
_ART_KEYS = frozenset(('id', 'kind', 'source', 'expected_git_blob_sha1'))
_OBS_KEYS = frozenset(('category', 'state', 'source_artifact_id', 'source', 'score'))
_TIMING_KEYS = frozenset(('phase', 'seconds', 'source_artifact_id', 'source', 'method'))
_ENV_KEYS = frozenset(('os', 'python', 'accelerator', 'source_artifact_id'))


class ImportRefused(Exception):
    '''Fixed, payload-free refusal. The reason is a literal chosen by this module.'''

    def __init__(self, reason: str = 'import refused') -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Identity:
    run_id: str  # caller-asserted, namespaced: at least two nonempty '/' segments
    candidate_sha256: str
    notebook_version: Optional[str]  # None or exactly owner/slug/version


@dataclass(frozen=True)
class ImportedArtifact:
    id: str
    kind: str
    source: Identity  # origin identity, supplied by the caller
    sha256: str  # exact content address of the supplied bytes
    size: int
    expected_git_blob_sha1: Optional[str]
    observed_git_blob_sha1: str
    git_comparison: str  # match, mismatch or unavailable


@dataclass(frozen=True)
class Observation:
    category: str
    state: str
    source_artifact_id: str
    source: Identity
    score: Optional[float]


@dataclass(frozen=True)
class Timing:
    phase: str
    seconds: Optional[float]  # None means unknown, never zero
    source_artifact_id: str
    source: Identity
    method: str


@dataclass(frozen=True)
class Environment:
    os: Optional[str]
    python: Optional[str]
    accelerator: Optional[str]
    source_artifact_id: Optional[str]
    source: Optional[Identity]


@dataclass(frozen=True)
class CategorySummary:
    category: str
    state: str  # 'ambiguous' when several observations match the target
    score: Optional[float]  # None when ambiguous: no score is selected
    defaulted: bool  # True: no evidence supplied for the target, not proof it never ran


@dataclass(frozen=True)
class ExistingRunImport:
    manifest_sha256: str
    manifest_bytes: bytes
    manifest_git_blob_sha1: str
    target: Identity
    artifacts: tuple
    observations: tuple  # every supplied observation, conflicts preserved
    current: tuple  # three CategorySummary, only observations whose source == target
    timings: tuple  # all supplied timings; filter by source for the current run
    environment: Environment


def git_blob_sha1(data: bytes) -> str:
    '''Git object id of a blob: sha1 over the header and the exact bytes.'''
    if type(data) is not bytes:
        raise TypeError('data must be exact bytes')
    header = b'blob ' + str(len(data)).encode('ascii') + bytes([0])
    return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()


# ------------------------------------------------------------ validation


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ImportRefused(reason)


def _utf8_len(text: str) -> int:
    try:
        return len(text.encode('utf-8'))
    except UnicodeEncodeError:
        return -1


def _text(value: object, nullable: bool = False) -> bool:
    if value is None:
        return nullable
    if type(value) is not str or not value or chr(0) in value:
        return False
    size = _utf8_len(value)
    return 0 < size <= MAX_STRING_BYTES


def _qualified(value: object, exact: int, nullable: bool = False) -> bool:
    '''Shape check only. exact=0 means at least two nonempty segments.'''
    if value is None:
        return nullable
    if not _text(value):
        return False
    parts = value.split('/')
    if not all(parts):
        return False
    return len(parts) == exact if exact else len(parts) >= 2


def _hex(value: object, length: int) -> bool:
    return type(value) is str and len(value) == length and all(c in _HEX for c in value)


def _number(value: object) -> bool:
    kind = type(value)
    if kind is int:
        return True
    return kind is float and math.isfinite(value)


def _exact(value: object, keys: frozenset) -> bool:
    return type(value) is dict and frozenset(value) == keys


def _decode(data: bytes) -> object:
    ok = True
    doc = None
    try:
        doc = parse_json_bytes(data)
    except InvalidJSONBlob:
        ok = False
    # Raised outside the handler: no cause and no context are attached.
    _require(ok, 'manifest is not strict JSON')
    return doc


def _identity(value: object) -> Identity:
    _require(_exact(value, _ID_KEYS), 'identity keys')
    run_id = value['run_id']
    candidate = value['candidate_sha256']
    notebook = value['notebook_version']
    _require(_qualified(run_id, 0), 'identity run id must be namespaced')
    _require(_hex(candidate, 64), 'identity candidate digest')
    _require(_qualified(notebook, 3, nullable=True), 'identity notebook version must be owner/slug/version')
    return Identity(run_id, candidate, notebook)


def _parse_artifacts(raw: object, supplied: dict) -> tuple:
    _require(type(raw) is list and 1 <= len(raw) <= MAX_ITEMS, 'artifact list')
    out = []
    seen = set()
    config_digest = {}
    for entry in raw:
        _require(_exact(entry, _ART_KEYS), 'artifact keys')
        art_id = entry['id']
        _require(_text(art_id) and art_id not in seen, 'artifact id')
        seen.add(art_id)
        kind = entry['kind']
        _require(type(kind) is str and kind in _KINDS, 'artifact kind')
        source = _identity(entry['source'])
        expected = entry['expected_git_blob_sha1']
        _require(expected is None or _hex(expected, 40), 'expected git blob sha1')
        _require(art_id in supplied, 'artifact bytes missing')
        data = supplied[art_id]
        observed = git_blob_sha1(data)
        digest = hashlib.sha256(data).hexdigest()
        if kind == 'config':
            prior = config_digest.setdefault(source, digest)
            _require(prior == digest, 'different config bytes for one identity')
        if expected is None:
            comparison = 'unavailable'
        elif expected == observed:
            comparison = 'match'
        else:
            comparison = 'mismatch'
        out.append(
            ImportedArtifact(art_id, kind, source, digest, len(data), expected, observed, comparison)
        )
    _require(len(seen) == len(supplied), 'artifact bytes not referenced by the manifest')
    return tuple(out)


def _parse_observations(raw: object, by_id: dict) -> tuple:
    _require(type(raw) is list and len(raw) <= MAX_ITEMS, 'observation list')
    out = []
    for entry in raw:
        _require(_exact(entry, _OBS_KEYS), 'observation keys')
        category = entry['category']
        state = entry['state']
        _require(type(category) is str and category in _STATES, 'observation category')
        _require(type(state) is str and state in _STATES[category], 'observation state')
        source = _identity(entry['source'])
        art_id = entry['source_artifact_id']
        _require(
            _text(art_id) and art_id in by_id and by_id[art_id].source == source,
            'observation source does not match its artifact',
        )
        score = entry['score']
        if category == 'official' and state == 'scored':
            _require(_number(score), 'official score')
        else:
            _require(score is None, 'score only for official scored')
        if category == 'official' and state != 'not_obtained':
            _require(source.notebook_version is not None, 'official observation needs notebook version')
        # Conflicting or duplicate observations are preserved, never merged.
        out.append(Observation(category, state, art_id, source, score))
    return tuple(out)


def _parse_timings(raw: object, by_id: dict) -> tuple:
    _require(type(raw) is list and len(raw) <= MAX_ITEMS, 'timing list')
    out = []
    seen = set()
    for entry in raw:
        _require(_exact(entry, _TIMING_KEYS), 'timing keys')
        phase = entry['phase']
        _require(type(phase) is str and phase in _PHASES, 'timing phase')
        seconds = entry['seconds']
        _require(seconds is None or (_number(seconds) and seconds >= 0), 'timing seconds')
        source = _identity(entry['source'])
        art_id = entry['source_artifact_id']
        _require(
            _text(art_id) and art_id in by_id and by_id[art_id].source == source,
            'timing source does not match its artifact',
        )
        _require(_text(entry['method']), 'timing method')
        key = (phase, source)
        _require(key not in seen, 'duplicate timing')
        seen.add(key)
        out.append(Timing(phase, seconds, art_id, source, entry['method']))
    return tuple(out)


def _parse_environment(raw: object, by_id: dict) -> Environment:
    _require(_exact(raw, _ENV_KEYS), 'environment keys')
    values = []
    for name in ('os', 'python', 'accelerator'):
        value = raw[name]
        _require(_text(value, nullable=True), 'environment value')
        values.append(value)
    art_id = raw['source_artifact_id']
    _require(_text(art_id, nullable=True), 'environment artifact id')
    if art_id is None:
        _require(all(v is None for v in values), 'environment values need an environment artifact')
        source = None
    else:
        artifact = by_id.get(art_id)
        _require(artifact is not None and artifact.kind == 'environment', 'environment artifact')
        source = artifact.source
    return Environment(values[0], values[1], values[2], art_id, source)


# ----------------------------------------------------------------- import


def import_existing_run(store: BlobStore, manifest: bytes, artifacts: dict) -> ExistingRunImport:
    '''Validate everything first, then store artifacts unchanged and the manifest last.'''
    _require(isinstance(store, BlobStore), 'store must be a BlobStore')
    _require(type(manifest) is bytes, 'manifest must be exact bytes')
    _require(type(artifacts) is dict, 'artifacts must be a dict')
    _require(len(artifacts) <= MAX_ITEMS, 'too many supplied artifacts')
    cap = store.max_blob_bytes
    _require(len(manifest) <= MAX_MANIFEST_BYTES and len(manifest) <= cap, 'manifest too large')
    total = len(manifest)
    for key, value in artifacts.items():
        _require(type(key) is str and type(value) is bytes, 'artifacts must map str to bytes')
        _require(len(value) <= cap, 'artifact exceeds the store cap')
        total += len(value)
    _require(total <= MAX_TOTAL_BYTES, 'supplied bytes exceed the aggregate cap')

    doc = _decode(manifest)
    _require(_exact(doc, _TOP_KEYS), 'manifest keys')
    _require(doc['version'] == FORMAT_VERSION, 'unsupported manifest version')
    target = _identity(doc['target'])
    arts = _parse_artifacts(doc['artifacts'], artifacts)
    by_id = {a.id: a for a in arts}

    anchored = False
    for art in arts:
        if art.kind == 'candidate':
            _require(art.source.candidate_sha256 == art.sha256, 'candidate source does not match its bytes')
            if art.source == target:
                anchored = True
    _require(anchored, 'no candidate artifact anchors the target identity')

    observations = _parse_observations(doc['observations'], by_id)
    timings = _parse_timings(doc['timings'], by_id)
    environment = _parse_environment(doc['environment'], by_id)

    current = []
    for category in _CATEGORY_ORDER:
        hits = [o for o in observations if o.category == category and o.source == target]
        if not hits:
            current.append(CategorySummary(category, _DEFAULT_STATE[category], None, True))
        elif len(hits) == 1:
            current.append(CategorySummary(category, hits[0].state, hits[0].score, False))
        else:
            current.append(CategorySummary(category, 'ambiguous', None, False))

    # All validation is done. Writes follow; there is no rollback.
    for art in arts:
        digest = store.put(artifacts[art.id])
        _require(digest == art.sha256, 'store digest mismatch')
    manifest_sha = hashlib.sha256(manifest).hexdigest()
    digest = store.put(manifest)
    _require(digest == manifest_sha, 'store digest mismatch')

    return ExistingRunImport(
        manifest_sha,
        manifest,
        git_blob_sha1(manifest),
        target,
        arts,
        observations,
        tuple(current),
        timings,
        environment,
    )

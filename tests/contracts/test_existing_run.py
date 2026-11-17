'''Contract tests for the existing-run evidence importer. Synthetic data only.'''
import hashlib
import json
import os
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))

from ai_agent_scientist.evidence.blob_store import BlobIOError, BlobStore  # noqa: E402
from ai_agent_scientist.evidence.existing_run import (  # noqa: E402
    MAX_ITEMS,
    MAX_MANIFEST_BYTES,
    ImportRefused,
    git_blob_sha1,
    import_existing_run,
)

NL = bytes([10])
CRLF = bytes([13, 10])
CAND = b'print(1)' + NL
CFG = b'seed=17' + NL
LOG = b'cpu simulation finished' + NL
EVID = b'cpu evidence' + NL
ENVB = b'environment note' + NL
OLD = b'earlier notebook version score 0.5' + NL
CFG2 = b'seed=41' + NL
EV2 = b'other run evidence' + NL
LOG2 = b'other run log' + NL
RUN = 'example.org/run-001'
NB2 = 'owner/slug/v2'
NB1 = 'owner/slug/v1'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def ident(candidate, notebook, run=RUN):
    return {'run_id': run, 'candidate_sha256': candidate, 'notebook_version': notebook}


def art(art_id, kind, source, expected):
    return {'id': art_id, 'kind': kind, 'source': dict(source), 'expected_git_blob_sha1': expected}


def obs(category, state, art_id, source, score):
    return {
        'category': category,
        'state': state,
        'source_artifact_id': art_id,
        'source': dict(source),
        'score': score,
    }


def fixture():
    cand = sha(CAND)
    tgt = ident(cand, NB2)
    old = ident(cand, NB1)
    manifest = {
        'version': 'existing-run-import/1',
        'target': dict(tgt),
        'artifacts': [
            art('cand', 'candidate', tgt, git_blob_sha1(CAND)),
            art('cfg', 'config', tgt, None),
            art('log', 'log', tgt, git_blob_sha1(LOG)),
            art('evid', 'evidence', tgt, git_blob_sha1(EVID)),
            art('envart', 'environment', tgt, None),
            art('old', 'evidence', old, git_blob_sha1(OLD)),
        ],
        'observations': [
            obs('cpu_simulation', 'completed', 'evid', tgt, None),
            obs('official', 'scored', 'old', old, 0.5),
        ],
        'timings': [],
        'environment': {'os': None, 'python': None, 'accelerator': None, 'source_artifact_id': None},
    }
    supplied = {'cand': CAND, 'cfg': CFG, 'log': LOG, 'evid': EVID, 'envart': ENVB, 'old': OLD}
    return manifest, supplied


def enc(manifest):
    return json.dumps(manifest).encode('utf-8')


def entry(manifest, art_id):
    return next(a for a in manifest['artifacts'] if a['id'] == art_id)


class RecordingStore(BlobStore):
    def __init__(self, root, *, max_blob_bytes):
        super().__init__(root, max_blob_bytes=max_blob_bytes)
        self.puts = []

    def put(self, data):
        self.puts.append(sha(data))
        return super().put(data)


class FailingStore(RecordingStore):
    fail_after = 10 ** 6
    wrong_digest = False

    def put(self, data):
        if len(self.puts) >= self.fail_after:
            raise OSError('injected storage failure')
        digest = super().put(data)
        return '0' * 64 if self.wrong_digest else digest


class ExistingRunTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.root = self.base / 'blobs'
        self.root.mkdir()
        self.store = RecordingStore(self.root, max_blob_bytes=1 << 20)

    def names(self, root=None):
        return sorted(p.name for p in (root or self.root).iterdir())

    def run_import(self, manifest, supplied):
        return import_existing_run(self.store, enc(manifest), supplied)

    def assert_refused(self, manifest, supplied, raw=None):
        raw = enc(manifest) if raw is None else raw
        with self.assertRaises(ImportRefused):
            import_existing_run(self.store, raw, supplied)
        self.assertEqual(self.store.puts, [])
        self.assertEqual(self.names(), [])

    # ---- existing behavior (adjusted to namespaced identities)

    def test_git_vector_and_trailing_newline_mismatch_retained(self):
        self.assertEqual(git_blob_sha1(b''), 'e69de29bb2d1d6434b8b29ae775ad8c2e48c5391')
        self.assertEqual(git_blob_sha1(b'hello' + NL), 'ce013625030ba8dba906f756967f9e9ca394464a')
        self.assertNotEqual(git_blob_sha1(b'hello'), git_blob_sha1(b'hello' + NL))
        self.assertNotEqual(hashlib.sha1(b'hello' + NL).hexdigest(), git_blob_sha1(b'hello' + NL))
        manifest, supplied = fixture()
        entry(manifest, 'log')['expected_git_blob_sha1'] = git_blob_sha1(LOG.rstrip(NL))
        result = self.run_import(manifest, supplied)
        by_id = {a.id: a for a in result.artifacts}
        self.assertEqual(by_id['log'].git_comparison, 'mismatch')
        self.assertEqual(by_id['log'].observed_git_blob_sha1, git_blob_sha1(LOG))
        self.assertEqual(by_id['log'].expected_git_blob_sha1, git_blob_sha1(LOG.rstrip(NL)))
        self.assertEqual(by_id['cand'].git_comparison, 'match')
        self.assertEqual(by_id['cfg'].git_comparison, 'unavailable')
        self.assertEqual(self.store.get(sha(LOG)), LOG)

    def test_unified_import_exact_replay_and_immutability(self):
        manifest, supplied = fixture()
        raw = enc(manifest)
        result = import_existing_run(self.store, raw, supplied)
        self.assertEqual(result.manifest_bytes, raw)
        self.assertEqual(result.manifest_sha256, sha(raw))
        self.assertEqual(self.store.get(sha(raw)), raw)
        self.assertEqual(self.store.puts[-1], sha(raw))
        self.assertEqual({a.kind for a in result.artifacts}, {'candidate', 'config', 'log', 'evidence', 'environment'})
        for data in supplied.values():
            self.assertEqual(self.store.get(sha(data)), data)
        self.assertEqual(len(self.names()), 7)
        again = import_existing_run(self.store, raw, supplied)
        self.assertEqual(again, result)
        self.assertEqual(len(self.names()), 7)
        self.assertIsInstance(result.artifacts, tuple)
        self.assertIsInstance(result.current, tuple)
        with self.assertRaises(FrozenInstanceError):
            result.target = None

    def test_historical_notebook_score_is_not_current_and_defaults(self):
        manifest, supplied = fixture()
        result = self.run_import(manifest, supplied)
        scored = [o for o in result.observations if o.category == 'official']
        self.assertEqual(len(scored), 1)
        self.assertEqual(scored[0].score, 0.5)
        self.assertEqual(scored[0].source.notebook_version, NB1)
        current = {c.category: c for c in result.current}
        self.assertEqual(current['official'].state, 'not_obtained')
        self.assertIsNone(current['official'].score)
        self.assertTrue(current['official'].defaulted)
        self.assertEqual(current['real_model'].state, 'not_run')
        self.assertTrue(current['real_model'].defaulted)
        self.assertEqual(current['cpu_simulation'].state, 'completed')
        self.assertFalse(current['cpu_simulation'].defaulted)

    def test_current_cpu_real_and_official_states_are_distinct(self):
        manifest, supplied = fixture()
        tgt = manifest['target']
        manifest['observations'].append(obs('real_model', 'failed', 'evid', tgt, None))
        manifest['observations'].append(obs('official', 'submitted', 'evid', tgt, None))
        result = self.run_import(manifest, supplied)
        current = {c.category: c for c in result.current}
        self.assertEqual(current['cpu_simulation'].state, 'completed')
        self.assertEqual(current['real_model'].state, 'failed')
        self.assertEqual(current['official'].state, 'submitted')
        self.assertIsNone(current['official'].score)
        manifest['observations'][-1] = obs('official', 'scored', 'evid', tgt, 0.75)
        scored = self.run_import(manifest, supplied)
        official = {c.category: c for c in scored.current}['official']
        self.assertEqual((official.state, official.score), ('scored', 0.75))
        self.assertIn(0.5, [o.score for o in scored.observations])

    def test_conflicting_current_observations_preserved_and_ambiguous(self):
        manifest, supplied = fixture()
        tgt = manifest['target']
        manifest['observations'].append(obs('cpu_simulation', 'failed', 'evid', tgt, None))
        result = self.run_import(manifest, supplied)
        cpu = {c.category: c for c in result.current}['cpu_simulation']
        self.assertEqual(cpu.state, 'ambiguous')
        self.assertIsNone(cpu.score)
        self.assertFalse(cpu.defaulted)
        states = sorted(o.state for o in result.observations if o.category == 'cpu_simulation')
        self.assertEqual(states, ['completed', 'failed'])

    def test_observation_artifact_identity_mismatch_refused(self):
        manifest, supplied = fixture()
        manifest['observations'][0] = obs('cpu_simulation', 'completed', 'old', manifest['target'], None)
        self.assert_refused(manifest, supplied)

    def test_duplicate_json_key_refused_without_cause_or_context(self):
        raw = b'{"version": 1, "version": 2}'
        with self.assertRaises(ImportRefused) as caught:
            import_existing_run(self.store, raw, {})
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)
        self.assertEqual(self.store.puts, [])

    def test_timing_and_environment_unknown_versus_measured(self):
        manifest, supplied = fixture()
        base = self.run_import(manifest, supplied)
        self.assertEqual(base.timings, ())
        self.assertIsNone(base.environment.os)
        self.assertIsNone(base.environment.source)
        tgt = manifest['target']
        manifest['timings'] = [
            {'phase': 'model_execution', 'seconds': 1.5, 'source_artifact_id': 'log', 'source': dict(tgt), 'method': 'operator stopwatch'},
            {'phase': 'evaluation', 'seconds': None, 'source_artifact_id': 'log', 'source': dict(tgt), 'method': 'not measured'},
        ]
        manifest['environment'] = {'os': 'example-os', 'python': '3.12', 'accelerator': None, 'source_artifact_id': 'envart'}
        result = self.run_import(manifest, supplied)
        self.assertEqual(result.timings[0].seconds, 1.5)
        self.assertIsNone(result.timings[1].seconds)
        self.assertEqual(result.environment.os, 'example-os')
        self.assertIsNone(result.environment.accelerator)
        self.assertEqual(result.environment.source, result.target)
        manifest['timings'][0]['seconds'] = True
        with self.assertRaises(ImportRefused):
            self.run_import(manifest, supplied)

    def test_candidate_bytes_not_matching_target_refused(self):
        manifest, supplied = fixture()
        supplied['cand'] = CAND + b'x'
        self.assert_refused(manifest, supplied)

    def test_unsupported_primitive_fails_closed_mocked_posix(self):
        # Mocks a missing POSIX primitive on this platform. This is NOT Windows acceptance.
        saved = getattr(os, 'O_NOFOLLOW', None)
        if saved is not None:
            del os.O_NOFOLLOW
        try:
            with self.assertRaises(BlobIOError):
                BlobStore(self.root, max_blob_bytes=1024)
        finally:
            if saved is not None:
                os.O_NOFOLLOW = saved
        self.assertEqual(self.names(), [])

    # ---- new: review findings (10 methods)

    def test_identity_shape_requirements(self):  # 8 subtests
        bad_runs = ['run-001', 'a//b', '/b']
        bad_notebooks = ['v2', 'owner/slug', 'owner//v2', 'owner/slug/v2/x']
        for run in bad_runs:
            with self.subTest(run_id=run):
                manifest, supplied = fixture()
                manifest['target']['run_id'] = run
                self.assert_refused(manifest, supplied)
        for nb in bad_notebooks:
            with self.subTest(notebook=nb):
                manifest, supplied = fixture()
                manifest['target']['notebook_version'] = nb
                self.assert_refused(manifest, supplied)
        with self.subTest(notebook=None):
            manifest, supplied = fixture()
            raw = enc(manifest).replace(json.dumps(NB2).encode('utf-8'), b'null')
            result = import_existing_run(self.store, raw, supplied)
            self.assertIsNone(result.target.notebook_version)

    def test_config_digest_conflict_for_one_identity_refused(self):
        manifest, supplied = fixture()
        manifest['artifacts'].append(art('cfg2', 'config', manifest['target'], None))
        supplied['cfg2'] = CFG + b'changed'
        self.assert_refused(manifest, supplied)
        # A different config under a different identity is a separate claim.
        manifest['artifacts'][-1]['source'] = ident(sha(CAND), NB1)
        result = self.run_import(manifest, supplied)
        self.assertEqual(len([a for a in result.artifacts if a.kind == 'config']), 2)

    def test_target_anchor_requires_full_identity(self):  # 2 subtests
        for field, value in (('notebook_version', 'owner/slug/v9'), ('run_id', 'example.org/other')):
            with self.subTest(field=field):
                manifest, supplied = fixture()
                entry(manifest, 'cand')['source'][field] = value
                self.assert_refused(manifest, supplied)

    def test_identical_and_conflicting_official_scores_ambiguous(self):
        manifest, supplied = fixture()
        tgt = manifest['target']
        manifest['observations'].append(obs('cpu_simulation', 'completed', 'evid', tgt, None))
        manifest['observations'].append(obs('official', 'scored', 'evid', tgt, 0.25))
        manifest['observations'].append(obs('official', 'scored', 'evid', tgt, 0.75))
        result = self.run_import(manifest, supplied)
        current = {c.category: c for c in result.current}
        for name in ('cpu_simulation', 'official'):
            self.assertEqual(current[name].state, 'ambiguous')
            self.assertIsNone(current[name].score)
            self.assertFalse(current[name].defaulted)
        self.assertEqual(len(result.observations), 5)
        self.assertEqual(sorted(o.score for o in result.observations if o.score is not None), [0.25, 0.5, 0.75])

    def test_count_and_size_caps_refused_before_writes(self):  # 3 subtests
        with self.subTest(cap='supplied artifacts'):
            many = {'a%d' % i: b'' for i in range(MAX_ITEMS + 1)}
            manifest, _ = fixture()
            self.assert_refused(manifest, many)
        with self.subTest(cap='observation list'):
            manifest, supplied = fixture()
            manifest['observations'] = [manifest['observations'][0]] * (MAX_ITEMS + 1)
            self.assert_refused(manifest, supplied)
        with self.subTest(cap='manifest bytes'):
            manifest, supplied = fixture()
            self.assert_refused(manifest, supplied, raw=b' ' * (MAX_MANIFEST_BYTES + 1))

    def test_strict_json_edge_cases_refused_without_cause(self):  # 4 subtests
        raws = [
            b'{"version": NaN}',
            bytes([0xFF, 0xFE, 0x00]),
            b'{"x": {"a": 1, "a": 2}}',
            b'[]',
        ]
        for raw in raws:
            with self.subTest(raw=raw):
                with self.assertRaises(ImportRefused) as caught:
                    import_existing_run(self.store, raw, {})
                self.assertIsNone(caught.exception.__cause__)
        self.assertEqual(self.store.puts, [])

    def test_exact_bytes_preserved_bom_crlf_multibyte(self):  # 3 subtests
        manifest, supplied = fixture()
        supplied['cfg'] = bytes.fromhex('efbbbf') + 'caf'.encode() + bytes.fromhex('c3a9e697a5') + CRLF
        supplied['log'] = b'a' + CRLF + b'b' + bytes([13]) + b'c' + NL + bytes([0]) + b'tail'
        supplied['evid'] = b'na' + bytes.fromhex('c3af') + b've' + CRLF
        entry(manifest, 'log')['expected_git_blob_sha1'] = git_blob_sha1(supplied['log'])
        entry(manifest, 'evid')['expected_git_blob_sha1'] = git_blob_sha1(supplied['evid'])
        result = self.run_import(manifest, supplied)
        by_id = {a.id: a for a in result.artifacts}
        for key in ('cfg', 'log', 'evid'):
            with self.subTest(artifact=key):
                data = supplied[key]
                self.assertEqual(self.store.get(sha(data)), data)
                self.assertEqual(by_id[key].sha256, sha(data))
                self.assertEqual(by_id[key].size, len(data))
                self.assertNotEqual(sha(data), sha(data.replace(CRLF, NL)))

    def test_zero_scores_zero_times_and_negative_duration(self):
        manifest, supplied = fixture()
        tgt = manifest['target']
        manifest['observations'].append(obs('official', 'scored', 'evid', tgt, 0.0))
        manifest['timings'] = [
            {'phase': 'model_execution', 'seconds': 0, 'source_artifact_id': 'log', 'source': dict(tgt), 'method': 'stopwatch'},
            {'phase': 'evaluation', 'seconds': 0.0, 'source_artifact_id': 'log', 'source': dict(tgt), 'method': 'stopwatch'},
            {'phase': 'cleanup', 'seconds': None, 'source_artifact_id': 'log', 'source': dict(tgt), 'method': 'unknown'},
        ]
        result = self.run_import(manifest, supplied)
        official = {c.category: c for c in result.current}['official']
        self.assertEqual((official.state, official.score, official.defaulted), ('scored', 0.0, False))
        self.assertIsNotNone(official.score)
        self.assertEqual([t.seconds for t in result.timings], [0, 0.0, None])
        self.assertIsNotNone(result.timings[0].seconds)
        manifest['timings'][0]['seconds'] = -0.5
        with self.assertRaises(ImportRefused):
            self.run_import(manifest, supplied)
        manifest['timings'][0]['seconds'] = 0
        manifest['observations'][-1]['score'] = True
        with self.assertRaises(ImportRefused):
            self.run_import(manifest, supplied)

    def test_missing_extra_malformed_and_late_failures_write_nothing(self):  # 6 subtests
        def drop(m, s):
            del s['cfg']

        def extra(m, s):
            s['zzz'] = b'x'

        def upper(m, s):
            entry(m, 'cfg')['expected_git_blob_sha1'] = 'A' * 40

        def short(m, s):
            entry(m, 'cfg')['expected_git_blob_sha1'] = 'a' * 39

        def nonstr(m, s):
            entry(m, 'cfg')['expected_git_blob_sha1'] = 5

        def late_env(m, s):  # environment is validated last
            m['environment'] = {'os': 'x', 'python': None, 'accelerator': None, 'source_artifact_id': None}

        for mutate in (drop, extra, upper, short, nonstr, late_env):
            with self.subTest(case=mutate.__name__):
                manifest, supplied = fixture()
                mutate(manifest, supplied)
                self.assert_refused(manifest, supplied)

    def test_partial_io_and_integrity_failure_leave_orphans_no_success(self):  # 3 subtests
        for index, fail_after in enumerate((2, 6)):
            with self.subTest(fail_after=fail_after):
                manifest, supplied = fixture()
                raw = enc(manifest)
                sub = self.base / ('io%d' % index)
                sub.mkdir()
                store = FailingStore(sub, max_blob_bytes=1 << 20)
                store.fail_after = fail_after
                with self.assertRaises(OSError):
                    import_existing_run(store, raw, supplied)
                self.assertNotIn(sha(raw), store.puts)
                self.assertEqual(len(self.names(sub)), fail_after)
        with self.subTest(case='digest mismatch'):
            manifest, supplied = fixture()
            sub = self.base / 'io-digest'
            sub.mkdir()
            store = FailingStore(sub, max_blob_bytes=1 << 20)
            store.wrong_digest = True
            with self.assertRaises(ImportRefused):
                import_existing_run(store, enc(manifest), supplied)
            self.assertEqual(len(store.puts), 1)
            self.assertEqual(len(self.names(sub)), 1)

    # ---- new: identity-collision regressions (2 methods, no subtests)

    def test_same_version_other_owner_slug_score_and_timing_stay_historical(self):
        manifest, supplied = fixture()
        other = ident(sha(CAND), 'other/nb/v2')
        manifest['artifacts'].append(art('oev', 'evidence', other, git_blob_sha1(EV2)))
        manifest['artifacts'].append(art('olog', 'log', other, None))
        manifest['observations'].append(obs('official', 'scored', 'oev', other, 0.9))
        manifest['timings'] = [
            {'phase': 'model_execution', 'seconds': 3.5, 'source_artifact_id': 'olog', 'source': dict(other), 'method': 'operator stopwatch'},
        ]
        supplied['oev'] = EV2
        supplied['olog'] = LOG2
        result = self.run_import(manifest, supplied)
        official = {c.category: c for c in result.current}['official']
        self.assertEqual(official.state, 'not_obtained')
        self.assertIsNone(official.score)
        self.assertTrue(official.defaulted)
        scores = sorted(o.score for o in result.observations if o.category == 'official')
        self.assertEqual(scores, [0.5, 0.9])
        self.assertEqual(len(result.timings), 1)
        self.assertEqual(result.timings[0].seconds, 3.5)
        self.assertNotEqual(result.timings[0].source, result.target)
        self.assertEqual(result.timings[0].source.notebook_version, 'other/nb/v2')

    def test_same_candidate_different_run_id_config_and_score_do_not_project(self):
        manifest, supplied = fixture()
        other = ident(sha(CAND), NB2, run='example.org/run-002')
        manifest['artifacts'].append(art('cfg2', 'config', other, None))
        manifest['artifacts'].append(art('evid2', 'evidence', other, git_blob_sha1(EV2)))
        manifest['observations'].append(obs('official', 'scored', 'evid2', other, 0.9))
        supplied['cfg2'] = CFG2
        supplied['evid2'] = EV2
        result = self.run_import(manifest, supplied)
        official = {c.category: c for c in result.current}['official']
        self.assertEqual(official.state, 'not_obtained')
        self.assertIsNone(official.score)
        self.assertTrue(official.defaulted)
        configs = [a for a in result.artifacts if a.kind == 'config']
        self.assertEqual(sorted(a.sha256 for a in configs), sorted([sha(CFG), sha(CFG2)]))
        self.assertEqual(sorted(o.score for o in result.observations if o.category == 'official'), [0.5, 0.9])
        for key, data in supplied.items():
            self.assertEqual(self.store.get(sha(data)), data)


if __name__ == '__main__':
    unittest.main()

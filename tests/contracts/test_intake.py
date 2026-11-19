import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ai_agent_scientist.evidence.blob_store import BlobStore
from ai_agent_scientist.evidence.existing_run import ImportRefused
from ai_agent_scientist.evidence.intake import intake_paths


def ident(cand, run='example.org/run-1', nb='owner/slug/1'):
    return {'run_id': run, 'candidate_sha256': hashlib.sha256(cand).hexdigest(), 'notebook_version': nb}


def art(i, kind, src):
    return {'id': i, 'kind': kind, 'source': src, 'expected_git_blob_sha1': None}


def E(stage, result, count=None, reason='none', logs=()):
    return {'stage': stage, 'result': result, 'count': count, 'stop_reason': reason, 'log_ids': list(logs)}


def outcome(stage, result, logs=(), **fields):
    return {'stage': stage, 'result': result, 'log_ids': list(logs), **fields}


def synthetic_verdict(expected, actual):
    if actual == expected:
        return 'exact_match'
    if int(actual) == int(expected):
        return 'formatting_mismatch'
    return 'numeric_mismatch'


class WrongGet(BlobStore):
    def get(self, digest, *args, **kwargs):
        return b'wrong'


class IntakeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name)
        (self.d / 'in').mkdir()
        (self.d / 'blobs').mkdir()
        self.store = BlobStore(self.d / 'blobs', max_blob_bytes=1 << 20)
        self.cand = b'code\r\n\xef\xbb\xbf\n'
        self.cfg = b'cfg=1\n'
        self.log = b'SECRET-LOG-LINE\n'
        self.t = ident(self.cand)

    def w(self, name, data):
        p = self.d / 'in' / name
        p.write_bytes(data)
        return p

    def st(self, *entries, target=None, version='intake-stages/1'):
        return {'version': version, 'target': target or self.t, 'stages': list(entries)}

    def prep(self, extra=(), obs=(), stages=None, cfg_src=None):
        doc = {
            'version': 'existing-run-import/1', 'target': self.t,
            'artifacts': [art('candidate', 'candidate', self.t), art('config', 'config', cfg_src or self.t),
                          art('log1', 'log', self.t)] + list(extra),
            'observations': list(obs), 'timings': [],
            'environment': {'os': None, 'python': None, 'accelerator': None, 'source_artifact_id': None},
        }
        m = self.w('m.json', json.dumps(doc).encode() + b'\n')
        sp = None if stages is None else self.w('s.json', json.dumps(stages).encode())
        return m, self.w('c.py', self.cand), self.w('cfg.json', self.cfg), {'log1': self.w('l.log', self.log)}, sp

    def go(self, logs=None, store=None, **kw):
        m, c, g, lp, sp = self.prep(**kw)
        lp.update(logs or {})
        return intake_paths(store or self.store, m, c, g, lp, stages_path=sp)

    def empty(self):
        self.assertEqual(os.listdir(self.d / 'blobs'), [])

    def cli(self, inputs, *, store=None, extra_args=()):
        manifest, candidate, config, logs, stages = inputs
        args = [sys.executable, '-B', '-m', 'ai_agent_scientist.evidence.intake',
                '--store', str(store or self.d / 'blobs'), '--manifest', str(manifest),
                '--candidate', str(candidate), '--config', str(config)]
        for log_id, path in logs.items():
            args.extend(('--log', log_id, str(path)))
        if stages is not None:
            args.extend(('--stages', str(stages)))
        src = Path(__file__).resolve().parents[2] / 'src'
        return subprocess.run(args + list(extra_args), cwd=self.d,
                              env=dict(os.environ, PYTHONPATH=str(src)),
                              capture_output=True, text=True, timeout=10)

    def test_exact_bytes_roundtrip_and_config_identity(self):
        s = self.go(stages=self.st(E('gpu_environment', 'started', logs=['log1']))).summary
        get = self.store.get
        self.assertEqual(get(hashlib.sha256(self.cand).hexdigest()), self.cand)
        self.assertEqual(get(s['config']['sha256']), self.cfg)
        self.assertEqual(s['config']['declared_identity'], self.t)
        raw = (self.d / 'in' / 'm.json').read_bytes()
        self.assertTrue(raw.endswith(b'\n'))
        self.assertEqual(get(s['manifest_sha256']), raw)
        self.assertEqual(get(s['stages_sha256']), (self.d / 'in' / 's.json').read_bytes())
        self.assertEqual(get(hashlib.sha256(self.log).hexdigest()), self.log)
        self.assertTrue(s['verified_readback'])
        with self.subTest('readback failure is refused'):
            (self.d / 'bad').mkdir()
            with self.assertRaises(ImportRefused):
                self.go(store=WrongGet(self.d / 'bad', max_blob_bytes=1 << 20))
        with self.subTest('additive import keeps original blobs'):
            old = self.log
            self.log = b'second log\n'
            self.go()
            self.assertEqual(get(hashlib.sha256(old).hexdigest()), old)
            self.assertEqual(get(hashlib.sha256(self.log).hexdigest()), self.log)
            self.assertEqual(get(hashlib.sha256(self.cand).hexdigest()), self.cand)

    def test_stages_are_independent(self):
        r = self.go(stages=self.st(
            E('gpu_environment', 'started'),
            E('model_launches', 'not_started', 0, 'not_started'),
            E('tests_collected', 'collected', 24),
            E('test_bodies_executed', 'not_started', 0, 'not_started'),
            E('patch_recovery', 'recovered')))
        by = {x['stage']: x for x in r.summary['stages']}
        self.assertEqual((by['gpu_environment']['result'], by['model_launches']['count']), ('started', 0))
        self.assertEqual((by['tests_collected']['count'], by['test_bodies_executed']['count']), (24, 0))
        self.assertEqual(by['patch_recovery']['result'], 'recovered')
        self.assertEqual((by['test_pass']['result'], by['test_pass']['count']), ('UNKNOWN', None))

    def test_missing_stages_are_unknown_not_zero(self):
        s = self.go().summary
        self.assertIsNone(s['stages_sha256'])
        absent = {'result': 'UNKNOWN', 'verdict': None, 'declared_evidence_sha256': None, 'logs': []}
        self.assertEqual(s['format'], 'intake-summary/1')
        self.assertEqual(s['stage_results'], dict.fromkeys(
            ('startup', 'inference', 'tool_handling', 'output_verification'), absent))
        self.assertEqual(len(s['stages']), 6)
        for x in s['stages']:
            self.assertEqual((x['result'], x['count'], x['stop_reason'], x['logs']), ('UNKNOWN', None, 'unknown', []))
        for cat in ('cpu_simulation', 'real_model', 'official'):
            self.assertEqual(s['results'][cat], {'state': 'UNKNOWN'})
        for reason in ('unavailable', 'interrupted'):
            with self.subTest('explicit unknown ' + reason):
                s = self.go(stages=self.st(E('test_pass', 'unknown', None, reason, ['log1']))).summary
                x = [y for y in s['stages'] if y['stage'] == 'test_pass'][0]
                self.assertEqual((x['result'], x['count'], x['stop_reason']), ('UNKNOWN', None, reason))
                self.assertEqual(x['logs'], [hashlib.sha256(self.log).hexdigest()])
                self.assertEqual(s['stage_results'], dict.fromkeys(
                    ('startup', 'inference', 'tool_handling', 'output_verification'), absent))

    def test_v2_preserves_legacy_entries_and_explicit_outcomes(self):
        legacy = [E('gpu_environment', 'started'), E('model_launches', 'not_started', 0),
                  E('tests_collected', 'collected', 1), E('test_bodies_executed', 'executed', 1),
                  E('patch_recovery', 'recovered'), E('test_pass', 'passed')]
        v1 = self.go(stages=self.st(*legacy)).summary
        v2 = self.go(stages=self.st(
            *legacy, outcome('startup', 'unknown', ['log1']), outcome('inference', 'not_run'),
            outcome('tool_handling', 'failure'),
            outcome('output_verification', 'success', verdict='formatting_mismatch'),
            version='intake-stages/2',
        )).summary
        self.assertEqual(v1['stages'], v2['stages'])
        self.assertEqual(v1['results'], v2['results'])
        self.assertEqual(v2['stage_results'], {
            'startup': {'result': 'UNKNOWN', 'verdict': None, 'declared_evidence_sha256': None,
                        'logs': [hashlib.sha256(self.log).hexdigest()]},
            'inference': {'result': 'not_run', 'verdict': None, 'declared_evidence_sha256': None, 'logs': []},
            'tool_handling': {'result': 'failure', 'verdict': None, 'declared_evidence_sha256': None, 'logs': []},
            'output_verification': {'result': 'success', 'verdict': 'formatting_mismatch',
                                    'declared_evidence_sha256': None, 'logs': []},
        })

    def test_cli_imports_synthetic_stage_results(self):
        expected = b'817394651\n'
        cases = (
            ('stopped', None, 'UNKNOWN', None),
            ('newline', b'817394651', 'failure', 'formatting_mismatch'),
            ('different-number', b'817394652\n', 'failure', 'numeric_mismatch'),
            ('exact', expected, 'success', 'exact_match'),
        )
        log_sha = hashlib.sha256(self.log).hexdigest()
        absent = {'result': 'UNKNOWN', 'verdict': None, 'declared_evidence_sha256': None, 'logs': []}
        for name, actual, verification_result, verdict in cases:
            with self.subTest(name):
                self.t = ident(self.cand, f'example.org/{name}')
                store = self.d / f'blobs-{name}'
                store.mkdir()
                evidence = b'SYNTHETIC-STOP-RECORD\n' if actual is None else actual
                evidence_sha = hashlib.sha256(evidence).hexdigest()
                if actual is None:
                    entries = [outcome('startup', 'not_run', ['log1'], declared_evidence_sha256=None),
                               outcome('inference', 'unknown', declared_evidence_sha256=evidence_sha)]
                else:
                    entries = [outcome('startup', 'success', ['log1']),
                               outcome('inference', 'success'), outcome('tool_handling', 'success'),
                               outcome('output_verification', verification_result, ['log1'],
                                       verdict=synthetic_verdict(expected, actual),
                                       declared_evidence_sha256=evidence_sha)]
                inputs = self.prep(stages=self.st(*entries, version='intake-stages/2'))
                run = self.cli(inputs, store=store)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(run.stderr, '')
                summary = json.loads(run.stdout)
                startup_result = 'not_run' if actual is None else 'success'
                completed = {'result': 'success', 'verdict': None, 'declared_evidence_sha256': None, 'logs': []}
                unknown_with_evidence = dict(absent, declared_evidence_sha256=evidence_sha)
                self.assertEqual(summary['stage_results'], {
                    'startup': {'result': startup_result, 'verdict': None,
                                'declared_evidence_sha256': None, 'logs': [log_sha]},
                    'inference': unknown_with_evidence if actual is None else completed,
                    'tool_handling': absent if actual is None else completed,
                    'output_verification': {'result': verification_result, 'verdict': verdict,
                                            'declared_evidence_sha256': None if actual is None else evidence_sha,
                                            'logs': [] if actual is None else [log_sha]},
                })
                self.assertTrue(summary['verified_readback'])
                manifest, candidate, config, logs, stages = inputs
                files = (manifest, candidate, config, logs['log1'], stages)
                blobs = {hashlib.sha256(p.read_bytes()).hexdigest(): p.read_bytes() for p in files}
                self.assertEqual({p.name: p.read_bytes() for p in store.iterdir()}, blobs)
                self.assertEqual(summary['stages_sha256'], hashlib.sha256(stages.read_bytes()).hexdigest())
                for needle in ('817394651', '817394652', 'SYNTHETIC-STOP-RECORD', 'SECRET-LOG-LINE', 'cfg=1', str(self.d)):
                    self.assertNotIn(needle, run.stdout)

    def test_invalid_v2_sidecars_are_refused_before_writes(self):
        private = 'PRIVATE-OUTPUT'
        invalid = (
            outcome('output_verification', 'failure', verdict=private),
            outcome('output_verification', 'not_run', verdict='exact_match'),
            outcome('output_verification', 'unknown', verdict='numeric_mismatch'),
            outcome('output_verification', 'failure', actual=private),
            outcome('tool_handling', 'success', verdict='exact_match'),
            outcome('startup', 'failed'),
            outcome('startup', 'success', ['foreign']),
            E('test_pass', 'success'),
            dict(E('test_pass', 'passed'), declared_evidence_sha256='a' * 64),
        )
        foreign = ident(b'other', 'example.org/other')
        cases = [self.st(entry, version='intake-stages/2') for entry in invalid]
        cases.extend((
            self.st(outcome('startup', 'success')),
            self.st(outcome('startup', 'success'), target=foreign, version='intake-stages/2'),
            self.st(outcome('startup', 'success'), outcome('startup', 'not_run'), version='intake-stages/2'),
        ))
        for index, stages in enumerate(cases):
            with self.subTest(index=index):
                with self.assertRaises(ImportRefused) as error:
                    self.go(stages=stages, extra=[art('foreign', 'log', foreign)],
                            logs={'foreign': self.w('f.log', b'foreign history')})
                self.assertNotIn(private, str(error.exception))
                self.empty()

    def test_cli_rejects_invalid_declared_evidence_digests_before_writes(self):
        for digest in ('A' * 64, 'a' * 63, 'g' * 64, 123):
            with self.subTest(digest=digest):
                entry = outcome('tool_handling', 'unknown', declared_evidence_sha256=digest)
                run = self.cli(self.prep(stages=self.st(entry, version='intake-stages/2')))
                self.assertEqual(run.returncode, 1, run.stderr)
                self.assertEqual(run.stdout, '')
                self.assertEqual(run.stderr, 'intake: invalid declared evidence digest\n')
                self.empty()

    def test_cli_refusals_are_payload_free_and_do_not_discover_logs(self):
        private = 'PRIVATE-CLI-PAYLOAD'
        bad = self.st(outcome('output_verification', 'failure', verdict=private), version='intake-stages/2')
        manifest, candidate, config, logs, stages = self.prep(stages=bad)
        good_inputs = (manifest, candidate, config, logs, None)
        for name, inputs, extra_args, status in (
            ('bad verdict', (manifest, candidate, config, logs, stages), (), 1),
            ('missing mapping', (manifest, candidate, config, {}, None), (), 1),
            ('unknown argument', good_inputs, (f'--{private}',), 2),
            ('duplicate log', good_inputs, ('--log', 'log1', private), 2),
        ):
            with self.subTest(name):
                run = self.cli(inputs, extra_args=extra_args)
                self.assertEqual(run.returncode, status, run.stderr)
                self.assertEqual(run.stdout, '')
                self.assertTrue(run.stderr.startswith('intake: '))
                self.assertEqual(len(run.stderr.splitlines()), 1)
                for needle in (private, str(self.d), 'SECRET-LOG-LINE'):
                    self.assertNotIn(needle, run.stderr)
                self.empty()

    def test_foreign_score_is_not_reassigned(self):
        fs = ident(b'other', 'example.org/other', 'o/s/2')
        foreign = {'category': 'official', 'state': 'scored', 'source_artifact_id': 'foreign',
                   'source': fs, 'score': 0.9}
        r = self.go(extra=[art('foreign', 'log', fs)], obs=[foreign],
                    logs={'foreign': self.w('f.log', b'f')})
        o = r.summary['results']['official']
        self.assertEqual(o, {'state': 'UNKNOWN'})
        self.assertEqual(len(r.imported.observations), 1)
        own = dict(foreign, source_artifact_id='log1', source=self.t, score=0.0)
        o = self.go(obs=[own]).summary['results']['official']
        self.assertEqual((o['state'], o['score']), ('scored', 0.0))
        self.assertEqual(o['score_provenance']['artifact_sha256'], hashlib.sha256(self.log).hexdigest())
        self.assertEqual(o['score_provenance']['source'], self.t)

    def test_invalid_sidecar_rejected_before_any_write(self):
        bad = {
            'target': self.st(E('gpu_environment', 'started'), target=ident(b'x')),
            'log id': self.st(E('gpu_environment', 'started', logs=['nope'])),
            'bool count': self.st(E('tests_collected', 'collected', True)),
            'negative count': self.st(E('tests_collected', 'collected', -1)),
            'count on gpu': self.st(E('gpu_environment', 'started', 1)),
            'duplicate': self.st(E('test_pass', 'passed'), E('test_pass', 'failed')),
            'unknown with count': self.st(E('tests_collected', 'unknown', 3)),
            'reason': self.st(E('gpu_environment', 'started', None, 'whatever')),
        }
        for name, doc in bad.items():
            with self.subTest(name):
                with self.assertRaises(ImportRefused):
                    self.go(stages=doc)
                self.empty()

    def test_unsafe_inputs_and_mapping_mismatch(self):
        link = self.d / 'in' / 'link.log'
        os.symlink(self.w('l.log', self.log), link)
        cases = {'symlink': {'log1': link}, 'directory': {'log1': self.d / 'in'},
                 'missing id': {}, 'extra id': {'log1': self.d / 'in' / 'l.log', 'zzz': self.d / 'in' / 'l.log'}}
        if hasattr(os, 'mkfifo'):
            os.mkfifo(self.d / 'in' / 'pipe')
            cases['fifo'] = {'log1': self.d / 'in' / 'pipe'}
        for name, lp in cases.items():
            with self.subTest(name):
                m, c, g, _, _ = self.prep()
                with self.assertRaises(ImportRefused):
                    intake_paths(self.store, m, c, g, lp)
        with self.subTest('other kind'):
            m, c, g, lp, _ = self.prep(extra=[art('ev', 'evidence', self.t)])
            with self.assertRaises(ImportRefused):
                intake_paths(self.store, m, c, g, lp)
        with self.subTest('oversize'):
            (self.d / 'small').mkdir()
            with self.assertRaises(ImportRefused):
                self.go(store=BlobStore(self.d / 'small', max_blob_bytes=4))
            self.assertEqual(os.listdir(self.d / 'small'), [])
        self.empty()

    def test_foreign_config_and_candidate_mismatch_refused(self):
        fs = ident(b'other', 'example.org/other', 'o/s/2')
        with self.assertRaises(ImportRefused):
            self.go(cfg_src=fs)
        m, c, g, lp, _ = self.prep()
        other = self.w('c2.py', b'different candidate')
        with self.assertRaises(ImportRefused):
            intake_paths(self.store, m, other, g, lp)
        self.empty()

    def test_summary_and_errors_carry_no_logs_or_paths(self):
        blob = json.dumps(self.go().summary)
        for needle in ('SECRET-LOG-LINE', str(self.d), 'l.log', 'cfg=1'):
            self.assertNotIn(needle, blob)
        m, c, g, lp, _ = self.prep()
        with self.assertRaises(ImportRefused) as cm:
            intake_paths(self.store, self.d / 'in' / 'missing.json', c, g, lp)
        self.assertNotIn(str(self.d), str(cm.exception))


if __name__ == '__main__':
    unittest.main()

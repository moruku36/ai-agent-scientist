import hashlib
import json
import os
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

    def st(self, *entries, target=None):
        return {'version': 'intake-stages/1', 'target': target or self.t, 'stages': list(entries)}

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

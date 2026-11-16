import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
import json

from ai_agent_scientist.admission import handoff_request as hr
from ai_agent_scientist.admission.handoff_request import (
    InvalidHandoffRequest, load_handoff_request, validate_handoff_request)
from ai_agent_scientist.evidence import json_blob
from ai_agent_scientist.evidence.blob_store import (
    BlobStore, BlobNotFound, BlobIntegrityError)

NOW = datetime(2026, 11, 17, 12, 0, 0, tzinfo=timezone.utc)
SECRET = 'SENTINEL-secret-value'
PUBLIC = 'invalid handoff request'


class Hostile:
    '''Custom hooks must never run on untrusted values.'''
    def __eq__(self, other):
        raise AssertionError('hostile __eq__ executed')

    def __ne__(self, other):
        raise AssertionError('hostile __ne__ executed')

    __hash__ = None


def req(**o):
    d = {
        'schema_version': 'harness-handoff/1', 'synthetic': True,
        'message_id': 'm1', 'request_id': 'r1', 'attempt_id': None,
        'replicate_id': None, 'project_id': 'p1', 'sender': 'scientist',
        'recipient': 'ctf', 'kind': 'request', 'in_reply_to': None,
        'expected_revision': 0, 'authorization_ref': 'a1',
        'budget_reservation_ref': 'b1',
        'payload': {'id': 'pl1', 'sha256': 'a' * 64,
                    'media_type': 'text/plain', 'classification': 'synthetic'},
        'created_at': '2026-11-17T11:00:00.123456Z',
        'expires_at': '2026-11-17T13:00:00Z',
    }
    d.update(o)
    return d


def pl(**o):
    d = dict(req()['payload'])
    d.update(o)
    return d


class _Fake:
    def __init__(self, data=None, exc=None):
        self.data, self.exc, self.calls = data, exc, 0

    def get(self, sha):
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.data


def snap(root):
    return {str(p.relative_to(root)): p.read_bytes()
            for p in sorted(root.rglob('*')) if p.is_file()}


class HandoffRequestTests(unittest.TestCase):
    def rej(self, v, now=NOW):
        with self.assertRaises(InvalidHandoffRequest) as c:
            validate_handoff_request(v, now=now)
        self.assertEqual(str(c.exception), PUBLIC)

    def test_h01_valid_load_real_store(self):
        with tempfile.TemporaryDirectory() as t:
            store = BlobStore(Path(t), max_blob_bytes=4096)
            sha = store.put(json.dumps(req()).encode())
            out = load_handoff_request(store, sha, now=NOW)
            self.assertEqual(out, req())
            self.assertIs(type(out), dict)
            edge = store.put(json.dumps(req(created_at='2026-11-17T12:00:00Z')).encode())
            self.assertEqual(load_handoff_request(store, edge, now=NOW)['created_at'],
                             '2026-11-17T12:00:00Z')

    def test_h02_shape_and_hostile_types(self):
        class D(dict): pass
        class S(str): pass
        class I(int): pass
        extra = req(); extra['x'] = 1
        missing = req(); del missing['project_id']
        keyed = req(); keyed[S('message_id')] = keyed.pop('message_id')
        cases = [None, [], D(req()), extra, missing, keyed,
                 req(message_id=S('m')), req(message_id=''), req(message_id=1),
                 req(synthetic=1), req(synthetic='true'), req(expected_revision=True),
                 req(expected_revision=I(1)), req(expected_revision=-1),
                 req(expected_revision='0'), req(expected_revision=1.0),
                 req(schema_version=S('harness-handoff/1')), req(payload=D(pl())),
                 req(schema_version=Hostile()), req(sender=Hostile()),
                 req(recipient=Hostile()), req(kind=Hostile()),
                 req(message_id=Hostile()), req(synthetic=Hostile()),
                 req(expected_revision=Hostile()),
                 req(payload=pl(classification=Hostile())),
                 req(payload=pl(sha256=Hostile()))]
        for c in cases:
            with self.subTest(c=repr(c)[:40]):
                self.rej(c)

    def test_h03_binding_version_kind_nulls(self):
        for c in [req(schema_version='harness-handoff/2'), req(kind='status'),
                  req(kind='result'), req(kind='cancel'), req(kind='other'),
                  req(kind=None), req(attempt_id='x'), req(in_reply_to='x'),
                  req(replicate_id=''), req(replicate_id=5)]:
            with self.subTest(c=repr(c)[:60]):
                self.rej(c)
        self.assertEqual(validate_handoff_request(req(replicate_id='rep'), now=NOW)['replicate_id'], 'rep')
        for role in ('scientist', 'ctf', 'sleep', 'evaluator'):
            validate_handoff_request(req(sender=role, recipient=role), now=NOW)

    def test_h04_payload_and_enums(self):
        bad_digest = ['A' * 64, 'a' * 63, 'a' * 65, 'a' * 64 + chr(10), 'g' * 64, '', None, 5]
        for d in bad_digest:
            with self.subTest(d=repr(d)[:20]):
                self.rej(req(payload=pl(sha256=d)))
        extra = pl(); extra['x'] = 1
        short = pl(); del short['id']
        for p in [extra, short, [], None, pl(id=''), pl(media_type=''),
                  pl(classification='public'), pl(id=3)]:
            with self.subTest(p=repr(p)[:40]):
                self.rej(req(payload=p))
        for c in ('private', 'reviewed_export', 'synthetic'):
            validate_handoff_request(req(payload=pl(classification=c)), now=NOW)
        self.rej(req(sender='mallory'))
        self.rej(req(recipient=None))

    def test_h05_timestamp_profile_negatives(self):
        wide = chr(0xFF12) + '026-11-17T11:00:00Z'
        for ts in ['2026-11-17T11:00:00+00:00', '2026-11-17T11:00:00z',
                   '2026-11-17 11:00:00Z', '2026-11-17T11:00:00',
                   '2026-11-17T11:00:00.Z', '2026-11-17T11:00:00.1234567Z',
                   '2026-02-30T11:00:00Z', '2026-13-01T11:00:00Z',
                   '2026-11-17T24:00:00Z', '2026-11-17T11:00:60Z',
                   '2026-11-17T11:00:00Z' + chr(10), '2026-11-17T11:00:00+09:00',
                   wide, '', 5, None]:
            with self.subTest(ts=repr(ts)):
                self.rej(req(created_at=ts))
                self.rej(req(expires_at=ts))
        validate_handoff_request(req(created_at='2026-11-17T11:00:00.5Z'), now=NOW)

    def test_h06_expiry_ordering_clock(self):
        self.rej(req(expires_at='2026-11-17T12:00:00Z'))
        validate_handoff_request(req(expires_at='2026-11-17T12:00:00.000001Z'), now=NOW)
        self.rej(req(created_at='2026-11-17T12:00:00.000001Z'))
        self.rej(req(created_at='2026-11-17T13:00:00Z'))
        self.rej(req(created_at='2026-11-17T14:00:00Z'))
        self.rej(req(), now=NOW + timedelta(hours=2))
        jst = timezone(timedelta(hours=9))
        for bad in [datetime(2026, 11, 17, 12), NOW.astimezone(jst), '2026-11-17T12:00:00Z', None]:
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(TypeError) as c:
                    validate_handoff_request(req(), now=bad)
                self.assertNotIn('2026', str(c.exception))

    def test_h07_upstream_failure_propagates(self):
        # Real store: actual missing digest and actual same-length tampering.
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            store = BlobStore(root, max_blob_bytes=4096)
            data = json.dumps(req()).encode()
            sha = store.put(data)
            missing = 'b' * 64
            self.assertNotEqual(missing, sha)
            blob = root / sha
            blob.chmod(0o600)
            blob.write_bytes(b'X' * len(data))
            for digest, exc in ((missing, BlobNotFound), (sha, BlobIntegrityError)):
                with self.subTest(exc=exc.__name__):
                    with mock.patch.object(store, 'get', wraps=store.get) as g, \
                            mock.patch.object(hr, 'validate_handoff_request') as m:
                        with self.assertRaises(exc) as c:
                            load_handoff_request(store, digest, now=NOW)
                        self.assertNotIsInstance(c.exception, InvalidHandoffRequest)
                        m.assert_not_called()
                        self.assertEqual(g.call_count, 1)
        # Fake store: malformed and duplicate-key JSON, strict-JSON read once.
        for data in (b'{', b'{"a":1,"a":2}'):
            store = _Fake(data=data)
            with self.subTest(data=data):
                with mock.patch.object(hr, 'validate_handoff_request') as m:
                    with self.assertRaises(json_blob.InvalidJSONBlob) as c:
                        load_handoff_request(store, 'a' * 64, now=NOW)
                    self.assertNotIsInstance(c.exception, InvalidHandoffRequest)
                    m.assert_not_called()
                self.assertEqual(store.calls, 1)
        ok = _Fake(data=b'[]')
        with self.assertRaises(InvalidHandoffRequest):
            load_handoff_request(ok, 'a' * 64, now=NOW)
        self.assertEqual(ok.calls, 1)

    def test_h08_detached_readonly_no_leak_no_authority(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            store = BlobStore(root, max_blob_bytes=4096)
            sha = store.put(json.dumps(req()).encode())
            before = snap(root)
            out = load_handoff_request(store, sha, now=NOW)
            out['payload']['id'] = 'changed'
            self.assertEqual(snap(root), before)
            self.assertEqual(load_handoff_request(store, sha, now=NOW)['payload']['id'], 'pl1')
        src = req()
        res = validate_handoff_request(src, now=NOW)
        self.assertIsNot(res['payload'], src['payload'])
        src['payload']['id'] = 'mutated'
        self.assertEqual(res['payload']['id'], 'pl1')
        self.assertIs(type(res['payload']), dict)
        for bad in [req(payload=pl(id=SECRET, sha256='Z' * 64)), req(project_id=SECRET, kind=SECRET)]:
            with self.assertRaises(InvalidHandoffRequest) as c:
                validate_handoff_request(bad, now=NOW)
            self.assertNotIn(SECRET, str(c.exception))
            self.assertNotIn(SECRET, repr(c.exception))
        for flag in (True, False):
            self.assertIs(validate_handoff_request(req(synthetic=flag), now=NOW)['synthetic'], flag)
        self.assertFalse(any('authoriz' in k and k != 'authorization_ref' for k in res))


if __name__ == '__main__':
    unittest.main()

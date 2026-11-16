"""P01-P10: authored offline binding integration cases; NOT EXECUTED here.

Independent of historical test modules. Real temporary BlobStores and envelopes;
deterministic subcases, no services, network, environment or permission changes.
"""
import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from ai_agent_scientist.admission import handoff_binding as hb
from ai_agent_scientist.admission.handoff_request import InvalidHandoffRequest
from ai_agent_scientist.evidence import blob_store as bs
from ai_agent_scientist.evidence.json_blob import InvalidJSONBlob

NOW = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
ID = 'payload-1'
PUBLIC = 'invalid handoff payload binding'
SECRET = 'binding-secret-sentinel'


class Hostile:
    def __eq__(self, other):
        raise AssertionError('hostile equality')

    def __ne__(self, other):
        raise AssertionError('hostile inequality')

    def __bool__(self):
        raise AssertionError('hostile truthiness')

    def __lt__(self, other):
        raise AssertionError('hostile ordering')

    def __hash__(self):
        return hash(ID)


def snapshot(root):
    return {str(p.relative_to(root)): (p.stat().st_ino, p.stat().st_mtime_ns, p.read_bytes())
            for p in root.rglob('*') if p.is_file()}


class HandoffBindingTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.request_root = self.root / 'envelopes'
        self.payload_root = self.root / 'payloads'
        self.request_root.mkdir()
        self.payload_root.mkdir()
        self.requests = bs.BlobStore(self.request_root, max_blob_bytes=4096)
        self.payloads = bs.BlobStore(self.payload_root, max_blob_bytes=32)
        self.raw = b'opaque:\xff\x00\r\n'
        digest = self.payloads.put(self.raw)
        self.binding = hb.PayloadBinding(
            id=ID, sha256=digest, media_type='application/octet-stream',
            classification='synthetic', max_payload_bytes=32, available=True,
            access_expires_at=NOW + timedelta(minutes=1))
        self.bindings = {ID: self.binding}
        self.request = {
            'schema_version': 'harness-handoff/1', 'synthetic': True,
            'message_id': 'm1', 'request_id': 'r1', 'attempt_id': None,
            'replicate_id': None, 'project_id': 'p1', 'sender': 'scientist',
            'recipient': 'ctf', 'kind': 'request', 'in_reply_to': None,
            'expected_revision': 0, 'authorization_ref': 'a1',
            'budget_reservation_ref': 'b1',
            'payload': {key: getattr(self.binding, key)
                        for key in ('id', 'sha256', 'media_type', 'classification')},
            'created_at': '2026-11-17T11:00:00Z',
            'expires_at': '2026-11-17T13:00:00Z',
        }
        self.request_sha = self.put_request(self.request)

    def put_request(self, request):
        return self.requests.put(json.dumps(request).encode('utf-8'))

    def load(self, digest=None, **changes):
        options = dict(payload_store=self.payloads, bindings=self.bindings, now=NOW)
        options.update(changes)
        return hb.load_bound_handoff_request(
            self.requests, self.request_sha if digest is None else digest, **options)

    def refuse(self, bindings):
        before = snapshot(self.root)
        with mock.patch.object(self.payloads, 'get', side_effect=AssertionError('payload read')) as read:
            with self.assertRaises(hb.InvalidHandoffBinding) as caught:
                self.load(bindings=bindings)
            read.assert_not_called()
        self.assertEqual(str(caught.exception), PUBLIC)
        self.assertNotIn(SECRET, repr(caught.exception))
        self.assertIsNone(caught.exception.__cause__)
        self.assertEqual(snapshot(self.root), before)

    def test_p01_real_verified_bytes_and_declarations(self):
        # The media declaration need not describe the bytes: there is no sniffing.
        for synthetic in (True, False):
            for classification in ('synthetic', 'private', 'reviewed_export'):
                with self.subTest(synthetic=synthetic, classification=classification):
                    self.request['synthetic'] = synthetic
                    self.request['payload'].update(media_type='text/plain', classification=classification)
                    digest = self.put_request(self.request)
                    binding = replace(self.binding, media_type='text/plain', classification=classification)
                    before = snapshot(self.root)
                    with mock.patch.object(hb, 'load_handoff_request', wraps=hb.load_handoff_request) as preflight, \
                            mock.patch.object(self.requests, 'get', wraps=self.requests.get) as envelope_read, \
                            mock.patch.object(self.payloads, 'get', wraps=self.payloads.get) as payload_read:
                        request, data = self.load(digest, bindings={ID: binding})
                        preflight.assert_called_once_with(self.requests, digest, now=NOW)
                        envelope_read.assert_called_once_with(digest)
                        payload_read.assert_called_once_with(binding.sha256)
                    self.assertEqual(request, self.request)
                    self.assertIs(type(request), dict)
                    self.assertIs(type(data), bytes)
                    self.assertEqual(data, self.raw)
                    self.assertEqual(hashlib.sha256(data).hexdigest(), binding.sha256)
                    self.assertEqual(snapshot(self.root), before)

    def test_p02_missing_and_substituted_metadata_refused_before_read(self):
        other_digest = self.payloads.put(b'other existing object')
        for field, value in (('id', SECRET), ('sha256', other_digest),
                             ('media_type', 'APPLICATION/OCTET-STREAM'),
                             ('classification', 'private')):
            with self.subTest(field=field):
                self.refuse({ID: replace(self.binding, **{field: value})})
        for table in ({}, {SECRET: self.binding}, {ID: None}):
            self.refuse(table)

    def test_p03_current_expiry_revocation_and_removal_every_invocation(self):
        self.assertEqual(self.load()[1], self.raw)
        for change in (dict(available=False), dict(access_expires_at=NOW),
                       dict(access_expires_at=NOW - timedelta(microseconds=1))):
            self.bindings[ID] = replace(self.binding, **change)
            self.refuse(self.bindings)
        self.bindings[ID] = replace(self.binding, access_expires_at=NOW + timedelta(microseconds=1))
        self.assertEqual(self.load()[1], self.raw)
        self.bindings[ID] = self.binding
        with mock.patch.object(self.payloads, 'get') as read:
            with self.assertRaises(hb.InvalidHandoffBinding):
                self.load(now=NOW + timedelta(minutes=2))
            read.assert_not_called()
        del self.bindings[ID]
        self.refuse(self.bindings)

    def test_p04_envelope_failures_stop_before_binding_and_payload(self):
        invalid = dict(self.request, kind='result')
        expired = dict(self.request, expires_at='2026-11-17T12:00:00Z')
        cases = [(self.requests.put(b'{'), InvalidJSONBlob),
                 (self.requests.put(b'{"x":1,"x":2}'), InvalidJSONBlob),
                 (self.put_request(invalid), InvalidHandoffRequest),
                 (self.put_request(expired), InvalidHandoffRequest),
                 (hashlib.sha256(b'absent envelope').hexdigest(), bs.BlobNotFound)]
        corrupt = self.requests.put(b'{"different":true}')
        (self.request_root / corrupt).write_bytes(b'X' * len(b'{"different":true}'))
        cases.append((corrupt, bs.BlobIntegrityError))
        for digest, error in cases:
            with self.subTest(error=error.__name__, digest=digest):
                before = snapshot(self.root)
                with mock.patch.object(self.payloads, 'get') as read:
                    # Invalid binding input proves envelope errors take precedence.
                    with self.assertRaises(error):
                        self.load(digest, bindings=None)
                    read.assert_not_called()
                self.assertEqual(snapshot(self.root), before)

    def test_p05_missing_tampered_and_io_payload_errors_preserve_evidence(self):
        path = self.payload_root / self.binding.sha256
        path.write_bytes(b'X' * len(self.raw))
        before = snapshot(self.root)
        with self.assertRaises(bs.BlobIntegrityError):
            self.load()
        self.assertEqual(snapshot(self.root), before)
        path.unlink()
        before = snapshot(self.root)
        with self.assertRaises(bs.BlobNotFound):
            self.load()
        self.assertEqual(snapshot(self.root), before)
        error = bs.BlobIOError('injected storage failure')
        with mock.patch.object(self.payloads, 'get', side_effect=error) as read:
            with self.assertRaises(bs.BlobIOError) as caught:
                self.load()
            self.assertIs(caught.exception, error)
            read.assert_called_once_with(self.binding.sha256)
        self.assertEqual(snapshot(self.root), before)

    def test_p06_explicit_cap_agreement_and_real_read_limit(self):
        self.assertEqual(self.payloads.max_blob_bytes, 32)
        with self.assertRaises(AttributeError):
            self.payloads.max_blob_bytes = 64
        for cap in (True, 0, -1, 32.0, '32', None, Hostile(), 31, 33):
            self.refuse({ID: replace(self.binding, max_payload_bytes=cap)})
        for raw in (b'', b'x' * 32, b'x' * 33):
            with self.subTest(size=len(raw)):
                writer = bs.BlobStore(self.payload_root, max_blob_bytes=33)
                digest = writer.put(raw)
                self.request['payload']['sha256'] = digest
                envelope = self.put_request(self.request)
                table = {ID: replace(self.binding, sha256=digest)}
                before = snapshot(self.root)
                if len(raw) <= 32:
                    self.assertEqual(self.load(envelope, bindings=table)[1], raw)
                else:
                    with self.assertRaises(bs.BlobTooLarge):
                        self.load(envelope, bindings=table)
                self.assertEqual(snapshot(self.root), before)

    def test_p07_exact_types_precede_hostile_comparisons(self):
        class S(str):
            pass

        class D(dict):
            def get(self, key):
                raise AssertionError('custom lookup')

        class T(datetime):
            def __le__(self, other):
                raise AssertionError('custom time comparison')

        class B(hb.PayloadBinding):
            pass

        for field in ('id', 'sha256', 'media_type', 'classification'):
            for bad in (Hostile(), S(SECRET), None, 1):
                with self.subTest(field=field, kind=type(bad).__name__):
                    self.refuse({ID: replace(self.binding, **{field: bad})})
        for field, values in (
                ('available', (1, 'true', Hostile(), None)),
                ('access_expires_at', (Hostile(), None, NOW.replace(tzinfo=None),
                                       NOW.astimezone(timezone(timedelta(hours=9))),
                                       T(2026, 11, 17, 13, tzinfo=timezone.utc)))):
            for bad in values:
                self.refuse({ID: replace(self.binding, **{field: bad})})
        for table in (None, [], D(self.bindings), {Hostile(): self.binding},
                      {S(ID): self.binding}, {ID: Hostile()},
                      {ID: B(ID, self.binding.sha256, 'text/plain', 'synthetic', 32, True, NOW)}):
            self.refuse(table)

    def test_p08_invalid_trusted_clock_and_store_contract_before_io(self):
        class T(datetime):
            pass

        class StoreSubclass(bs.BlobStore):
            pass

        for now in (None, Hostile(), NOW.replace(tzinfo=None),
                    NOW.astimezone(timezone(timedelta(hours=9))),
                    T(2026, 11, 17, 12, tzinfo=timezone.utc)):
            with mock.patch.object(self.requests, 'get') as envelope, \
                    mock.patch.object(self.payloads, 'get') as payload:
                with self.assertRaises(TypeError) as caught:
                    self.load(now=now)
                self.assertEqual(str(caught.exception), 'now must be a UTC-aware datetime')
                envelope.assert_not_called()
                payload.assert_not_called()
        request_subclass = StoreSubclass(self.request_root, max_blob_bytes=4096)
        payload_subclass = StoreSubclass(self.payload_root, max_blob_bytes=32)
        for request_store, payload_store in ((object(), self.payloads), (self.requests, object()),
                                             (request_subclass, self.payloads),
                                             (self.requests, payload_subclass)):
            with mock.patch.object(self.requests, 'get') as envelope, \
                    mock.patch.object(self.payloads, 'get') as payload:
                with self.assertRaises(TypeError) as caught:
                    hb.load_bound_handoff_request(request_store, self.request_sha,
                                                  payload_store=payload_store,
                                                  bindings=self.bindings, now=NOW)
                self.assertEqual(str(caught.exception), 'stores must be exact BlobStore instances')
                envelope.assert_not_called()
                payload.assert_not_called()

    def test_p09_uri_and_path_ids_are_only_local_table_keys(self):
        outside = self.root / 'outside'
        outside.write_bytes(SECRET.encode())
        for opaque in ('https://invalid.example/' + SECRET, 'file://' + str(outside),
                       '../outside', str(outside), 'store://other/' + SECRET):
            with self.subTest(opaque=opaque):
                self.request['payload']['id'] = opaque
                digest = self.put_request(self.request)
                table = {opaque: replace(self.binding, id=opaque)}
                before = snapshot(self.root)
                with mock.patch('urllib.request.urlopen', side_effect=AssertionError('URL dereference')), \
                        mock.patch('socket.create_connection', side_effect=AssertionError('network')), \
                        mock.patch.object(bs.os, 'open', wraps=bs.os.open) as opened:
                    self.assertEqual(self.load(digest, bindings=table)[1], self.raw)
                    self.assertEqual({Path(call.args[0]) for call in opened.call_args_list},
                                     {self.request_root / digest, self.payload_root / self.binding.sha256})
                    with mock.patch.object(self.payloads, 'get') as read:
                        with self.assertRaises(hb.InvalidHandoffBinding):
                            self.load(digest, bindings={})
                        read.assert_not_called()
                self.assertEqual(snapshot(self.root), before)

    def test_p10_detachment_fresh_reads_and_no_authority_result(self):
        before = snapshot(self.root)
        first, data = self.load()
        self.assertEqual(set(first), set(self.request))
        self.assertEqual(set(first['payload']), set(self.request['payload']))
        first['payload']['id'] = SECRET
        first['authorization_ref'] = SECRET
        self.request['payload']['id'] = 'caller mutation'
        self.bindings[ID] = replace(self.binding)
        second, fresh_data = self.load()
        self.assertEqual(second['payload']['id'], ID)
        self.assertEqual(second['authorization_ref'], 'a1')
        self.assertIsNot(first, second)
        self.assertIsNot(first['payload'], second['payload'])
        self.assertEqual(data, fresh_data)
        self.assertEqual(snapshot(self.root), before)
        # Prior success never bypasses the next actual verified read.
        (self.payload_root / self.binding.sha256).write_bytes(b'Y' * len(self.raw))
        changed = snapshot(self.root)
        with self.assertRaises(bs.BlobIntegrityError):
            self.load()
        self.assertEqual(snapshot(self.root), changed)
        self.assertEqual(data, self.raw)


if __name__ == '__main__':
    unittest.main()

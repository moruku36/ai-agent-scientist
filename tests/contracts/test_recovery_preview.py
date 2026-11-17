'''P01-P06: exactly six NEW self-contained tests, authored NOT EXECUTED.
Real private temporary BlobStore/SQLite fixtures; no historical test imports.
'''
import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from ai_agent_scientist.admission import durable_handoff as dh
from ai_agent_scientist.admission import recovery_operator as ro
from ai_agent_scientist.admission import recovery_preview as rp
from ai_agent_scientist.admission.handoff_binding import PayloadBinding
from ai_agent_scientist.evidence.blob_store import BlobStore

NOW = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)


class RecoveryPreviewContracts(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.root.chmod(0o700)
        for name in ('requests', 'payloads'):
            (self.root / name).mkdir(mode=0o700)
        self.requests = BlobStore(self.root / 'requests', max_blob_bytes=8192)
        self.payloads = BlobStore(self.root / 'payloads', max_blob_bytes=128)
        digest = self.payloads.put(b'synthetic private payload')
        self.binding = PayloadBinding('object', digest, 'application/octet-stream',
            'synthetic', 128, True, NOW + timedelta(hours=2))
        self.scope = dh.TrustedHandoffScope('principal', 'project', 'scientist', 'ctf')
        self.path = str(self.root / 'receiver.sqlite3')
        self.receiver = dh.DurableHandoffReceipts(self.path, scope=self.scope)
        self.envelope = dh.WorkerSecondsEnvelope('private-owner', 'private-envelope',
                                                410, 10, 1, 1, 8, 4)

    def retain(self, rid, *, receipt_only=False):
        s = self.scope
        ref = 'reserve-' + rid
        request = {
            'schema_version': 'harness-handoff/1', 'synthetic': True,
            'message_id': 'message-' + rid, 'request_id': rid,
            'attempt_id': None, 'replicate_id': None, 'project_id': s.project_id,
            'sender': s.sender, 'recipient': s.recipient, 'kind': 'request',
            'in_reply_to': None, 'expected_revision': 0,
            'authorization_ref': 'private-authority', 'budget_reservation_ref': ref,
            'payload': {n: getattr(self.binding, n)
                        for n in ('id', 'sha256', 'media_type', 'classification')},
            'created_at': '2026-11-17T11:00:00Z', 'expires_at': '2026-11-17T13:00:00Z',
        }
        digest = self.requests.put(json.dumps(request).encode('utf-8'))
        if receipt_only:
            return self.receiver.record(self.requests, digest,
                payload_store=self.payloads, bindings={'object': self.binding}, now=NOW)
        authorities = {(s.principal, s.project_id, s.sender, s.recipient,
            'private-authority', ref): dh.WorkerSecondsAuthority(
                self.envelope, True, NOW + timedelta(hours=1))}
        return self.receiver.reserve(self.requests, digest, authorities=authorities,
            payload_store=self.payloads, bindings={'object': self.binding}, now=NOW)

    def state(self):
        with closing(sqlite3.connect(self.path)) as conn:
            return tuple(conn.iterdump())

    def files(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def test_p1_exact_bytes_hash_and_immutable(self):
        self.retain('a')
        p = rp.build_reconciliation_preview(self.receiver, 'a')
        detail = ro.render_recovery_detail(self.receiver, 'a')
        snap = self.receiver.inspect_reservation('a')
        body = json.loads(p.data)
        self.assertEqual(sorted(body), ['action', 'expected_revision', 'limitations',
            'request_id', 'request_sha256', 'source_detail_sha256', 'source_detail_text',
            'version'])
        self.assertEqual(body['version'], 'recovery-reconciliation-preview/1')
        self.assertEqual(body['action'], 'mark_reconciliation_required')
        self.assertEqual(body['source_detail_text'], detail.text)
        self.assertEqual(body['source_detail_sha256'],
                         hashlib.sha256(detail.text.encode('ascii')).hexdigest())
        self.assertEqual((p.request_id, p.request_sha256, p.expected_revision),
                         ('a', snap.receipt.request_sha256, 1))
        self.assertEqual(body['request_sha256'], p.request_sha256)
        self.assertEqual(p.sha256, hashlib.sha256(p.data).hexdigest())
        expected = json.dumps(body, sort_keys=True, ensure_ascii=True,
                              separators=(',', ':')).encode('ascii')
        self.assertEqual(p.data, expected)
        self.assertNotIn(b'\n', p.data.replace(b'\\n', b''))
        self.assertFalse(p.data.endswith(b'\n'))
        self.assertIn('not authority', json.dumps(body['limitations']).lower())
        self.assertEqual(p.data, rp.build_reconciliation_preview(self.receiver, 'a').data)
        with self.assertRaises(AttributeError):
            p.data = b'forged'

    def test_p2_single_detail_read_and_no_writes(self):
        self.retain('a')
        self.retain('b')
        before, files = self.state(), self.files()
        with mock.patch.object(rp, 'render_recovery_detail',
                               wraps=rp.render_recovery_detail) as spy, \
             mock.patch.object(dh.DurableHandoffReceipts, '__init__',
                               side_effect=AssertionError('no receiver construction')), \
             mock.patch.object(dh.DurableHandoffReceipts, 'require_reconciliation',
                               side_effect=AssertionError('never executes the action')):
            rp.build_reconciliation_preview(self.receiver, 'a', max_output_bytes=1048576)
        self.assertEqual(spy.call_count, 1)
        self.assertEqual(spy.call_args.kwargs['max_output_bytes'], 1048576)
        self.assertEqual((self.state(), self.files()), (before, files))
        self.assertEqual(self.receiver.inspect_reservation('a').receipt.state, 'recorded')

    def test_p3_missing_and_receipt_only_return_none(self):
        self.retain('a')
        self.retain('receipt-only', receipt_only=True)
        self.assertIsNone(rp.build_reconciliation_preview(self.receiver, 'missing'))
        self.assertIsNone(rp.build_reconciliation_preview(self.receiver, 'receipt-only'))

    def test_p4_reconciliation_required_is_refused_value_free(self):
        self.retain('a')
        self.receiver.require_reconciliation('a', expected_revision=1,
                                             now=NOW + timedelta(seconds=2))
        digest = self.receiver.inspect_reservation('a').receipt.request_sha256
        before = self.state()
        with self.assertRaises(rp.RecoveryPreviewRefused) as ctx:
            rp.build_reconciliation_preview(self.receiver, 'a')
        self.assertNotIn(digest, str(ctx.exception))
        self.assertNotIn('a', str(ctx.exception).replace('preview refused', '').replace(
            'recovery', ''))
        self.assertEqual(self.state(), before)

    def test_p5_strict_cap_types_and_boundary(self):
        self.retain('a')
        size = len(rp.build_reconciliation_preview(self.receiver, 'a').data)
        self.assertEqual(len(rp.build_reconciliation_preview(
            self.receiver, 'a', max_output_bytes=size).data), size)
        with self.assertRaises(rp.RecoveryPreviewTooLarge) as ctx:
            rp.build_reconciliation_preview(self.receiver, 'a', max_output_bytes=size - 1)
        self.assertNotIn('private', str(ctx.exception))
        with mock.patch.object(rp, 'render_recovery_detail') as spy:
            for bad in (True, 0, -1, 1048577, '1', 1.0, None):
                with self.assertRaises(ValueError):
                    rp.build_reconciliation_preview(self.receiver, 'a', max_output_bytes=bad)
            spy.assert_not_called()

    def test_p6_escaping_privacy_and_propagated_errors(self):
        self.retain('a')
        snap = self.receiver.inspect_reservation('a')
        tainted = ro.RecoveryDetailView('x' + chr(34) + chr(10) + chr(127) + 'y\n',
            'a', snap.receipt.request_sha256, 1, 'recorded')
        with mock.patch.object(rp, 'render_recovery_detail', return_value=tainted):
            data = rp.build_reconciliation_preview(self.receiver, 'a').data
        self.assertTrue(data.isascii())
        self.assertNotIn(b'\x7f', data)
        self.assertIn(b'\\u007f', data)
        self.assertEqual(json.loads(data)['source_detail_text'], tainted.text)
        real = rp.build_reconciliation_preview(self.receiver, 'a').data
        for secret in (b'private-authority', b'private-owner', b'private-envelope',
                       b'synthetic private payload'):
            self.assertNotIn(secret, real)
        for error in (sqlite3.OperationalError('boom'), ValueError('invalid recovery report')):
            with mock.patch.object(rp, 'render_recovery_detail', side_effect=error):
                with self.assertRaises(type(error)):
                    rp.build_reconciliation_preview(self.receiver, 'a')


if __name__ == '__main__':
    unittest.main()

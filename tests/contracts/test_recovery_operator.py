'''O01-O06: exactly six NEW self-contained tests, authored NOT EXECUTED.
Real private temporary BlobStore/SQLite fixtures; no historical test imports.
'''
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from ai_agent_scientist.admission import durable_handoff as dh
from ai_agent_scientist.admission import recovery_console as rc
from ai_agent_scientist.admission import recovery_operator as ro
from ai_agent_scientist.admission.handoff_binding import PayloadBinding
from ai_agent_scientist.evidence.blob_store import BlobStore

NOW = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
BS = chr(92)


class RecoveryOperatorContracts(unittest.TestCase):
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

    def retain(self, rid):
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
        authorities = {(s.principal, s.project_id, s.sender, s.recipient,
            'private-authority', ref): dh.WorkerSecondsAuthority(
                self.envelope, True, NOW + timedelta(hours=1))}
        return self.receiver.reserve(self.requests, digest, authorities=authorities,
            payload_store=self.payloads, bindings={'object': self.binding}, now=NOW)

    def observe(self, retained, usage, stopped=False, cleanup=False):
        r = retained.reservation
        return self.receiver.record_usage_observation('obs-' + r.request_id,
            request_id=r.request_id, budget_reservation_ref=r.budget_reservation_ref,
            request_sha256=r.request_sha256, expected_revision=1, worker_seconds=usage,
            execution_stopped=stopped, cleanup_known=cleanup,
            observed_at=NOW + timedelta(seconds=1))

    def state(self):
        with closing(sqlite3.connect(self.path)) as conn:
            return tuple(conn.iterdump())

    def files(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def snap(self, rid):
        return self.receiver.inspect_reservation(rid)

    def mark(self, rid, *, rev=1, digest=None, now=None):
        digest = digest or self.snap(rid).receipt.request_sha256
        return ro.mark_recovery_for_reconciliation(self.receiver, request_id=rid,
            expected_request_sha256=digest, expected_revision=rev,
            now=now or NOW + timedelta(seconds=2))

    def test_o1_detail_binds_safe_fields_and_is_read_only(self):
        a = self.retain('a')
        self.retain('u')
        self.observe(a, 7, stopped=True)
        before, files = self.state(), self.files()
        page = rc.render_recovery_queue(self.receiver, reasons=('usage_unknown',),
                                        page_limit=1, max_pages=1)
        self.assertNotIn('request=' + json.dumps('u'), page.text)
        with mock.patch.object(ro, 'inspect_recovery_triage',
                               wraps=ro.inspect_recovery_triage) as spy, \
             mock.patch.object(dh.DurableHandoffReceipts, '__init__',
                               side_effect=AssertionError('no receiver construction')):
            view = ro.render_recovery_detail(self.receiver, 'a')
            unknown = ro.render_recovery_detail(self.receiver, 'u')
        self.assertEqual(spy.call_count, 2)
        snap = self.snap('a')
        self.assertEqual((view.request_id, view.request_sha256, view.revision, view.state),
                         ('a', snap.receipt.request_sha256, 2, 'reconciliation_required'))
        self.assertEqual(view.text.splitlines()[0],
                         'PRIVATE LOCAL RECOVERY DETAIL - NOT AUTHORITY')
        for needle in (
                'request_sha256=' + json.dumps(snap.receipt.request_sha256),
                'payload_sha256=' + json.dumps(snap.receipt.payload_sha256),
                'reservation_ref=' + json.dumps(snap.reservation.budget_reservation_ref),
                'outstanding_worker_seconds=%d' % snap.accounting.outstanding_worker_seconds,
                'observation_id=' + json.dumps('obs-a'),
                'sequence=%d' % snap.latest_usage_observation.sequence,
                'expected_revision=1', 'worker_seconds=7',
                'event_id=%d' % snap.current_status.event.event_id,
                'receipt_revision=2',
                'ack_revision=%d' % snap.current_status.ack_revision):
            self.assertIn(needle, view.text)
        self.assertIn('observation=none', unknown.text)
        self.assertIn('usage=UNKNOWN', unknown.text)
        self.assertNotIn('usage=ZERO', unknown.text)
        self.assertIsNone(ro.render_recovery_detail(self.receiver, 'missing'))
        for bad in (None, {}):
            with self.assertRaises(TypeError):
                ro.render_recovery_detail(bad, 'a')
        with self.assertRaises(AttributeError):
            view.text = 'forged'
        self.assertEqual((self.state(), self.files()), (before, files))

    def test_o2_escape_known_zero_and_exact_output_cap(self):
        self.observe(self.retain('z'), 0, stopped=True, cleanup=True)
        zero = ro.render_recovery_detail(self.receiver, 'z')
        self.assertIn('worker_seconds=0', zero.text)
        self.assertIn('usage=ZERO', zero.text)
        self.assertNotIn('worker_seconds=UNKNOWN', zero.text)
        real = ro._project

        def tainted(report):
            entry = real(report)
            entry['receipt']['state'] = 'x' + chr(34) + chr(10) + chr(127) + chr(233)
            return entry
        with mock.patch.object(ro, '_project', side_effect=tainted):
            text = ro.render_recovery_detail(self.receiver, 'z').text
        self.assertTrue(text.isascii())
        self.assertNotIn(chr(127), text)
        for piece in (BS + 'u007f', BS + 'u00e9', BS + 'n', BS + chr(34)):
            self.assertIn(piece, text)
        self.assertEqual(len(text.splitlines()), len(zero.text.splitlines()))
        size = len(zero.text)
        self.assertEqual(ro.render_recovery_detail(
            self.receiver, 'z', max_output_bytes=size).text, zero.text)
        with self.assertRaises(rc.RecoveryConsoleTooLarge):
            ro.render_recovery_detail(self.receiver, 'z', max_output_bytes=size - 1)
        with mock.patch.object(ro, 'inspect_recovery_triage') as spy:
            for bad in (True, 0, rc.MAX_CONSOLE_BYTES + 1, '1', 1.0):
                with self.assertRaises(ValueError):
                    ro.render_recovery_detail(self.receiver, 'z', max_output_bytes=bad)
            spy.assert_not_called()

    def test_o3_explicit_mark_advances_receipt_once_and_keeps_reservation(self):
        self.retain('a')
        self.retain('b')
        rc.render_recovery_queue(self.receiver, reasons=('no_observation',))
        ro.render_recovery_detail(self.receiver, 'a')
        before, other = self.snap('a'), self.snap('b')
        self.assertEqual((before.receipt.revision, before.receipt.state), (1, 'recorded'))
        receipt = self.mark('a')
        self.assertEqual((receipt.revision, receipt.state), (2, 'reconciliation_required'))
        after = self.snap('a')
        self.assertEqual(after.receipt, receipt)
        self.assertEqual(after.reservation, before.reservation)
        self.assertEqual(after.accounting, before.accounting)
        self.assertEqual(after.accounting.outstanding_worker_seconds,
                         before.reservation.worker_seconds)
        self.assertEqual(after.current_status.event.receipt_revision, 2)
        self.assertEqual(after.current_status.event.status, 'reconciliation_required')
        self.assertGreater(after.current_status.event.event_id,
                           before.current_status.event.event_id)
        self.assertEqual(self.snap('b'), other)
        self.assertIn('state=' + json.dumps('reconciliation_required'),
                      ro.render_recovery_detail(self.receiver, 'a').text)

    def test_o4_refusals_and_bad_arguments_change_nothing(self):
        self.retain('a')
        good = self.snap('a').receipt.request_sha256
        before, files = self.state(), self.files()
        for rid, digest, rev in (('a', '0' * 64, 1), ('a', good, 2), ('missing', good, 1)):
            with self.assertRaises(ro.RecoveryMarkRefused) as ctx:
                self.mark(rid, rev=rev, digest=digest)
            self.assertNotIn(digest, str(ctx.exception))
        # receipt-only requests surface as None from triage: refused, no CAS call
        with mock.patch.object(ro, 'inspect_recovery_triage', return_value=None), \
             mock.patch.object(dh.DurableHandoffReceipts, 'require_reconciliation') as act:
            with self.assertRaises(ro.RecoveryMarkRefused):
                self.mark('a', digest=good)
            act.assert_not_called()
        with mock.patch.object(ro, 'inspect_recovery_triage') as spy:
            for digest, rev in (('A' + good[1:], 1), (good[:-1], 1), (5, 1),
                                (good, True), (good, '1'), (good, 0)):
                with self.assertRaises(ValueError) as ctx:
                    self.mark('a', rev=rev, digest=digest)
                self.assertNotIsInstance(ctx.exception, ro.RecoveryMarkRefused)
            spy.assert_not_called()
        for bad in (None, {}):
            with self.assertRaises(TypeError):
                ro.mark_recovery_for_reconciliation(bad, request_id='a',
                    expected_request_sha256=good, expected_revision=1, now=NOW)
        self.assertEqual((self.state(), self.files()), (before, files))

    def test_o5_repeat_stale_and_backward_time_fail_unchanged(self):
        self.retain('a')
        self.retain('b')
        self.mark('a')
        after_mark = self.state()
        for rev in (1, 2):
            with self.assertRaises(ro.RecoveryMarkRefused):
                self.mark('a', rev=rev, now=NOW + timedelta(seconds=3))
        self.assertEqual(self.state(), after_mark)
        with self.assertRaises(ValueError):
            self.mark('b', now=NOW - timedelta(seconds=1))
        self.assertEqual(self.state(), after_mark)
        self.assertEqual(self.snap('b').receipt.state, 'recorded')

    def test_o6_concurrent_change_between_inspect_and_cas_fails_safely(self):
        retained = self.retain('c')
        self.retain('d')
        rc.render_recovery_queue(self.receiver, reasons=('no_observation',))
        ro.render_recovery_detail(self.receiver, 'c')
        self.assertEqual(self.snap('c').receipt.state, 'recorded')  # no implicit mark
        real, box = ro.inspect_recovery_triage, {}

        def racing(receiver, rid):
            report = real(receiver, rid)
            self.observe(retained, 3)  # independent writer advances the revision
            box['state'] = self.state()
            return report
        with mock.patch.object(ro, 'inspect_recovery_triage', side_effect=racing):
            with self.assertRaises(dh.ReceiptRevisionError):
                self.mark('c')
        self.assertEqual(self.state(), box['state'])
        self.assertEqual(self.snap('c').receipt.revision, 2)
        self.assertEqual(self.snap('d').receipt.state, 'recorded')


if __name__ == '__main__':
    unittest.main()

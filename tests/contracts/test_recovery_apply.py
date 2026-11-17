'''A01-A06: exactly six NEW self-contained tests, authored NOT EXECUTED.'''
import dataclasses
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ai_agent_scientist.admission import durable_handoff as dh
from ai_agent_scientist.admission import recovery_apply as ra
from ai_agent_scientist.admission import recovery_operator as ro
from ai_agent_scientist.admission import recovery_preview as rp
from ai_agent_scientist.admission.handoff_binding import PayloadBinding
from ai_agent_scientist.evidence.blob_store import BlobStore

NOW = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
LATER = NOW + timedelta(seconds=2)


class RecoveryApplyContracts(unittest.TestCase):
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

    def observe(self, retained, usage):
        r = retained.reservation
        return self.receiver.record_usage_observation('obs-' + r.request_id,
            request_id=r.request_id, budget_reservation_ref=r.budget_reservation_ref,
            request_sha256=r.request_sha256, expected_revision=1, worker_seconds=usage,
            execution_stopped=False, cleanup_known=False,
            observed_at=NOW + timedelta(seconds=1))

    def state(self):
        with closing(sqlite3.connect(self.path)) as conn:
            return tuple(conn.iterdump())

    def snap(self, rid):
        return self.receiver.inspect_reservation(rid)

    def preview(self, rid):
        return rp.build_reconciliation_preview(self.receiver, rid, max_output_bytes=1048576)

    def ack(self, rid):
        eid = self.snap(rid).current_status.event.event_id
        return self.receiver.acknowledge_status_event(
            eid, expected_ack_revision=0, now=NOW + timedelta(seconds=1))

    def test_a1_apply_marks_once_and_keeps_budget(self):
        self.retain('a')
        self.retain('b')
        pa = self.preview('a')
        before, other = self.snap('a'), self.snap('b')
        state = self.state()
        self.assertEqual(self.preview('a'), pa)
        self.assertEqual(self.state(), state)  # building writes nothing
        with mock.patch.object(ra, 'build_reconciliation_preview',
                               wraps=ra.build_reconciliation_preview) as build, \
             mock.patch.object(ra, 'mark_recovery_for_reconciliation',
                               wraps=ra.mark_recovery_for_reconciliation) as mark:
            receipt = ra.apply_reconciliation_preview(self.receiver, pa, now=LATER)
        self.assertEqual((build.call_count, mark.call_count), (1, 1))
        self.assertEqual((receipt.revision, receipt.state), (2, 'reconciliation_required'))
        after = self.snap('a')
        self.assertEqual(after.receipt, receipt)
        self.assertEqual(after.reservation, before.reservation)
        self.assertEqual(after.accounting, before.accounting)
        self.assertEqual(after.accounting.outstanding_worker_seconds,
                         before.reservation.worker_seconds)
        self.assertEqual(after.current_status.event.status, 'reconciliation_required')
        self.assertEqual(self.snap('b'), other)

    def test_a2_tampered_previews_refused_before_any_read(self):
        self.retain('a')
        good = self.preview('a')
        forged = b'{}'
        import hashlib
        cases = [
            SimpleNamespace(**dataclasses.asdict(good)),
            dataclasses.replace(good, data='text'),
            dataclasses.replace(good, data=b'', sha256=hashlib.sha256(b'').hexdigest()),
            dataclasses.replace(good, sha256=good.sha256.upper()),
            dataclasses.replace(good, sha256='0' * 64),
            dataclasses.replace(good, request_id=''),
            dataclasses.replace(good, request_id=5),
            dataclasses.replace(good, request_sha256='A' * 64),
            dataclasses.replace(good, expected_revision=0),
            dataclasses.replace(good, expected_revision=True),
        ]
        state = self.state()
        with mock.patch.object(ra, 'build_reconciliation_preview') as build, \
             mock.patch.object(ra, 'mark_recovery_for_reconciliation') as mark:
            for bad in cases:
                with self.assertRaises(ra.RecoveryApplyRefused) as ctx:
                    ra.apply_reconciliation_preview(self.receiver, bad, now=LATER)
                self.assertNotIn(good.request_sha256, str(ctx.exception))
            build.assert_not_called()
            mark.assert_not_called()
        # well-formed but forged bytes pass shape, differ from the rebuild
        fake = dataclasses.replace(good, data=forged, sha256=hashlib.sha256(forged).hexdigest())
        with mock.patch.object(ra, 'mark_recovery_for_reconciliation') as mark:
            with self.assertRaises(ra.RecoveryApplyRefused):
                ra.apply_reconciliation_preview(self.receiver, fake, now=LATER)
            mark.assert_not_called()
        self.assertEqual(self.state(), state)

    def test_a3_stale_revision_observation_and_ack_only_detected(self):
        self.retain('a')
        c = self.retain('c')
        pa, pc = self.preview('a'), self.preview('c')
        self.ack('a')  # ack-only change: receipt revision stays 1
        self.assertEqual(self.snap('a').receipt.revision, 1)
        self.observe(c, 3)  # observation advances revision and state
        state = self.state()
        with mock.patch.object(ra, 'mark_recovery_for_reconciliation') as mark:
            for stale, rid in ((pa, 'a'), (pc, 'c')):
                with self.assertRaises(ra.RecoveryApplyRefused):
                    ra.apply_reconciliation_preview(self.receiver, stale, now=LATER)
            mark.assert_not_called()
        self.assertEqual(self.state(), state)
        self.assertEqual(self.snap('a').receipt.state, 'recorded')

    def test_a4_race_after_rebuild_cas_and_ack_only_gap(self):
        a = self.retain('a')
        self.retain('k')
        pa, pk = self.preview('a'), self.preview('k')
        real, calls = ro.inspect_recovery_triage, []

        def racing(receiver, rid):
            report = real(receiver, rid)
            calls.append(rid)
            if len(calls) == 2:  # the mark inspection, after the rebuild
                self.observe(a, 3)
            return report
        with mock.patch.object(ro, 'inspect_recovery_triage', side_effect=racing):
            with self.assertRaises(dh.ReceiptRevisionError):
                ra.apply_reconciliation_preview(self.receiver, pa, now=LATER)
        self.assertEqual(self.snap('a').receipt.revision, 2)
        self.assertEqual(self.snap('a').latest_usage_observation.worker_seconds, 3)
        # ACK-ONLY after the fresh rebuild is NOT fenced: the mark still succeeds
        real_build = rp.build_reconciliation_preview

        def build_then_ack(receiver, rid, **kw):
            out = real_build(receiver, rid, **kw)
            self.ack('k')
            return out
        with mock.patch.object(ra, 'build_reconciliation_preview',
                               side_effect=build_then_ack):
            receipt = ra.apply_reconciliation_preview(self.receiver, pk, now=LATER)
        self.assertEqual(receipt.revision, 2)
        current = self.snap('k').current_status
        self.assertEqual(current.event.receipt_revision, 2)
        self.assertEqual(current.ack_revision, 0)
        events = self.receiver.inspect_status_events(
            after_event_id=0, limit=100, pending_only=False)
        retained = [entry for entry in events
                    if entry.event.request_id == 'k' and entry.event.receipt_revision == 1]
        self.assertEqual(len(retained), 1)
        self.assertEqual(retained[0].ack_revision, 1)

    def test_a5_time_and_errors_propagate_without_retry(self):
        self.retain('a')
        pa = self.preview('a')
        state = self.state()
        with mock.patch.object(ra, 'mark_recovery_for_reconciliation',
                               wraps=ra.mark_recovery_for_reconciliation) as mark:
            with self.assertRaises(ValueError):
                ra.apply_reconciliation_preview(
                    self.receiver, pa, now=NOW - timedelta(seconds=1))
            self.assertEqual(mark.call_count, 1)
        self.assertEqual(self.state(), state)
        with mock.patch.object(ra, 'build_reconciliation_preview',
                               side_effect=RuntimeError('storage')) as build, \
             mock.patch.object(ra, 'mark_recovery_for_reconciliation') as mark:
            with self.assertRaises(RuntimeError):
                ra.apply_reconciliation_preview(self.receiver, pa, now=LATER)
            self.assertEqual(build.call_count, 1)
            mark.assert_not_called()
        with mock.patch.object(ra, 'mark_recovery_for_reconciliation',
                               side_effect=dh.ReceiptRevisionError('cas')) as mark:
            with self.assertRaises(dh.ReceiptRevisionError):
                ra.apply_reconciliation_preview(self.receiver, pa, now=LATER)
            self.assertEqual(mark.call_count, 1)
        for bad in (None, {}):
            with self.assertRaises((TypeError, AttributeError)):
                ra.apply_reconciliation_preview(bad, pa, now=LATER)
        self.assertEqual(self.state(), state)

    def test_a6_missing_receipt_only_and_marked_refuse_no_construction(self):
        self.retain('a')
        retained = self.retain('receipt-only', receipt_only=True)
        pa = self.preview('a')
        state = self.state()
        ghost = dataclasses.replace(pa, request_id='missing')
        receipt_only = dataclasses.replace(pa, request_id=retained.request_id)
        with mock.patch.object(dh.DurableHandoffReceipts, '__init__',
                               side_effect=AssertionError('no receiver construction')), \
             mock.patch.object(ra, 'mark_recovery_for_reconciliation') as mark:
            with self.assertRaises(ra.RecoveryApplyRefused):
                ra.apply_reconciliation_preview(self.receiver, ghost, now=LATER)
            with self.assertRaises(ra.RecoveryApplyRefused):
                ra.apply_reconciliation_preview(self.receiver, receipt_only, now=LATER)
            mark.assert_not_called()
        self.assertEqual(self.state(), state)
        self.receiver.require_reconciliation('a', expected_revision=1, now=LATER)
        marked = self.state()
        with mock.patch.object(ra, 'mark_recovery_for_reconciliation') as mark:
            with self.assertRaises(ra.RecoveryApplyRefused):
                ra.apply_reconciliation_preview(self.receiver, pa, now=LATER)
            mark.assert_not_called()
        self.assertEqual(self.state(), marked)


if __name__ == '__main__':
    unittest.main()

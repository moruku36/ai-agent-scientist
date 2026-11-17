"""K01-K06: exactly six NEW self-contained unittest methods; NOT EXECUTED.

Private real SQLite/BlobStore setup copied from the existing six-case recovery
fixtures. No historical test classes are imported and no operational DB is used.
"""
import dataclasses
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from ai_agent_scientist.admission import durable_handoff as dh
from ai_agent_scientist.admission import recovery_ack as ra
from ai_agent_scientist.admission import recovery_operator as ro
from ai_agent_scientist.admission import recovery_triage as rt
from ai_agent_scientist.admission.handoff_binding import PayloadBinding
from ai_agent_scientist.evidence.blob_store import BlobStore

NOW = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
LATER = NOW + timedelta(seconds=2)
MAX_INT = (1 << 63) - 1


class RecoveryAckContracts(unittest.TestCase):
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

    def observe(self, retained):
        r = retained.reservation
        return self.receiver.record_usage_observation('obs-' + r.request_id,
            request_id=r.request_id, budget_reservation_ref=r.budget_reservation_ref,
            request_sha256=r.request_sha256, expected_revision=1, worker_seconds=None,
            execution_stopped=False, cleanup_known=False,
            observed_at=NOW + timedelta(seconds=1))

    def state(self):
        with closing(sqlite3.connect(self.path)) as conn:
            return tuple(conn.iterdump())

    def files(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def without_acks(self, state):
        return tuple(line for line in state
                     if not line.startswith('INSERT INTO "reservation_status_acks"'))

    def snap(self, rid):
        return self.receiver.inspect_reservation(rid)

    def arguments(self, selection):
        # Deliberately spell out scalar expectations. The action accepts no
        # selection object; event receipt revision is bound to receipt revision.
        return dict(request_id=selection.request_id,
                    expected_request_sha256=selection.request_sha256,
                    expected_receipt_revision=selection.receipt_revision,
                    expected_event_id=selection.event_id,
                    expected_ack_revision=selection.ack_revision)

    def mark(self, rid, receiver=None):
        return ro.mark_recovery_for_reconciliation(
            self.receiver if receiver is None else receiver, request_id=rid,
            expected_request_sha256=self.snap(rid).receipt.request_sha256,
            expected_revision=1, now=NOW + timedelta(seconds=1))

    def test_k01_selected_path_read_only_then_only_ack_changes_full_budget_retained(self):
        self.retain('a')
        b = self.retain('b')
        self.observe(b)  # exercise both receipt revisions, retaining UNKNOWN
        self.retain('untouched')
        untouched = self.snap('untouched')
        for rid in ('a', 'b'):
            before, files, snapshot = self.state(), self.files(), self.snap(rid)
            with mock.patch.object(ra, 'inspect_recovery_triage',
                                   wraps=ra.inspect_recovery_triage) as triage, \
                 mock.patch.object(self.receiver, 'inspect_reservation',
                                   wraps=self.receiver.inspect_reservation) as read, \
                 mock.patch.object(self.receiver, 'acknowledge_status_event') as ack:
                selected = ra.select_current_recovery_status(self.receiver, rid)
                triage.assert_called_once_with(self.receiver, rid)
                read.assert_called_once_with(rid)
                ack.assert_not_called()
            self.assertIs(type(selected), ra.RecoveryStatusSelection)
            self.assertEqual(dataclasses.asdict(selected), dict(
                request_id=rid, request_sha256=snapshot.receipt.request_sha256,
                receipt_revision=snapshot.receipt.revision,
                event_id=snapshot.current_status.event.event_id,
                event_receipt_revision=snapshot.current_status.event.receipt_revision,
                ack_revision=0))
            with self.assertRaises(dataclasses.FrozenInstanceError):
                selected.event_id = 999
            self.assertEqual((self.state(), self.files()), (before, files))
            with mock.patch.object(ra, 'inspect_recovery_triage',
                                   wraps=ra.inspect_recovery_triage) as triage, \
                 mock.patch.object(self.receiver, 'inspect_reservation',
                                   wraps=self.receiver.inspect_reservation) as read, \
                 mock.patch.object(self.receiver, 'acknowledge_status_event',
                                   wraps=self.receiver.acknowledge_status_event) as ack, \
                 mock.patch.object(dh.DurableHandoffReceipts, '__init__',
                                   side_effect=AssertionError('no construction')):
                result = ra.acknowledge_current_recovery_status(
                    self.receiver, **self.arguments(selected), now=LATER)
                triage.assert_called_once_with(self.receiver, rid)
                read.assert_called_once_with(rid)
                ack.assert_called_once_with(selected.event_id,
                                            expected_ack_revision=0, now=LATER)
                self.assertIs(ack.call_args.kwargs['now'], LATER)
            self.assertIs(type(result), dh.LocalStatusEntry)
            self.assertEqual(result, dh.LocalStatusEntry(
                snapshot.current_status.event, 1, '2026-11-17T12:00:02.000000Z'))
            self.assertEqual(self.snap(rid), dataclasses.replace(snapshot, current_status=result))
            self.assertEqual(self.without_acks(self.state()), self.without_acks(before))
            self.assertEqual(self.snap(rid).accounting, dh.ReservationAccounting(20, 20))
            self.assertEqual(self.snap('untouched'), untouched)
            self.assertEqual({k: v for k, v in self.files().items() if k != 'receiver.sqlite3'},
                             {k: v for k, v in files.items() if k != 'receiver.sqlite3'})

    def test_k02_malformed_exact_scalar_types_and_bounds_refuse_before_reads(self):
        self.retain('a')
        good = ra.select_current_recovery_status(self.receiver, 'a')

        class Text(str):
            pass

        class Number(int):
            pass

        bad_ids = (None, True, 1, b'a', '', Text('a'), 'x' * 1025,
                   '界' * 342, '\x00private', '\ud800')
        malformed = {
            'request_id': bad_ids,
            'expected_request_sha256': (None, b'0' * 64, True, Text('0' * 64),
                                        '0' * 63, '0' * 65, 'A' * 64, 'g' * 64),
            'expected_receipt_revision': (None, True, Number(1), 1.0, '1', 0, -1, MAX_INT + 1),
            'expected_event_id': (None, True, Number(1), 1.0, '1', 0, -1, MAX_INT + 1),
            'expected_ack_revision': (None, False, Number(0), 0.0, '0', -1, MAX_INT + 1),
        }
        before, files = self.state(), self.files()
        with mock.patch.object(ra, 'inspect_recovery_triage') as triage, \
             mock.patch.object(self.receiver, 'inspect_reservation') as read, \
             mock.patch.object(self.receiver, 'acknowledge_status_event') as ack:
            for field, values in malformed.items():
                for value in values:
                    with self.subTest(field=field, value=repr(value)):
                        args = dict(self.arguments(good), **{field: value})
                        with self.assertRaises(ra.RecoveryAckRefused) as ctx:
                            ra.acknowledge_current_recovery_status(self.receiver, **args, now=LATER)
                        self.assertEqual(str(ctx.exception), 'recovery acknowledgement refused')
            for value in bad_ids:
                with self.assertRaises(ra.RecoveryAckRefused):
                    ra.select_current_recovery_status(self.receiver, value)
            triage.assert_not_called()
            read.assert_not_called()
            ack.assert_not_called()
        self.assertEqual((self.state(), self.files()), (before, files))
        # Exactly 1024 UTF-8 bytes is valid syntax, even when no row exists.
        self.assertIsNone(ra.select_current_recovery_status(self.receiver, '界' * 341 + 'x'))

    def test_k03_stale_forged_digest_revision_event_and_ack_refuse_no_old_ack(self):
        self.retain('a')
        self.retain('b')
        old = ra.select_current_recovery_status(self.receiver, 'a')
        other = ra.select_current_recovery_status(self.receiver, 'b')
        self.mark('a')
        current = ra.select_current_recovery_status(self.receiver, 'a')
        cases = [self.arguments(old)]
        for change in ({'request_id': 'b'}, {'request_sha256': '0' * 64},
                       {'receipt_revision': 1}, {'receipt_revision': MAX_INT},
                       {'event_id': old.event_id}, {'event_id': other.event_id},
                       {'event_id': MAX_INT}, {'ack_revision': 1}, {'ack_revision': MAX_INT}):
            cases.append(self.arguments(dataclasses.replace(current, **change)))
        before, files = self.state(), self.files()
        with mock.patch.object(self.receiver, 'acknowledge_status_event') as ack:
            for args in cases:
                with self.subTest(args=args), self.assertRaises(ra.RecoveryAckRefused) as ctx:
                    ra.acknowledge_current_recovery_status(self.receiver, **args, now=LATER)
                self.assertEqual(str(ctx.exception), 'recovery acknowledgement refused')
            # A forged dataclass is constructible, but cannot be passed as authority.
            forged = dataclasses.replace(current, event_id=other.event_id)
            with self.assertRaises(TypeError):
                ra.acknowledge_current_recovery_status(self.receiver, forged, now=LATER)
            ack.assert_not_called()
        # Actual triage also rejects an internally forged event receipt revision.
        snap = self.snap('a')
        wrong = dataclasses.replace(snap, current_status=dataclasses.replace(
            snap.current_status, event=dataclasses.replace(
                snap.current_status.event, receipt_revision=1)))
        with mock.patch.object(self.receiver, 'inspect_reservation', return_value=wrong) as read, \
             mock.patch.object(self.receiver, 'acknowledge_status_event') as ack:
            with self.assertRaises(rt.InvalidRecoverySnapshot):
                ra.acknowledge_current_recovery_status(
                    self.receiver, **self.arguments(current), now=LATER)
            read.assert_called_once_with('a')
            ack.assert_not_called()
        self.assertEqual((self.state(), self.files()), (before, files))
        self.assertEqual(self.snap('a').current_status.ack_revision, 0)
        self.assertTrue(all(e.ack_revision == 0 for e in
                            self.receiver.inspect_status_events(pending_only=False)))

    def test_k04_real_missing_receipt_only_status_missing_and_already_acked(self):
        self.retain('legacy')
        self.retain('receipt-only', receipt_only=True)
        self.retain('acked')
        legacy = ra.select_current_recovery_status(self.receiver, 'legacy')
        self.mark('legacy')
        acked = ra.select_current_recovery_status(self.receiver, 'acked')
        self.receiver.acknowledge_status_event(acked.event_id, expected_ack_revision=0, now=LATER)
        # Fixture-only emulation of legacy missing current status, outside the
        # trusted API. Leave the OLD pending event to forbid fallback to it.
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute('DROP TRIGGER reservation_status_no_delete')
            conn.execute('DELETE FROM reservation_status_events '
                         'WHERE request_id=? AND receipt_revision=2', ('legacy',))
        before, files = self.state(), self.files()
        with mock.patch.object(self.receiver, 'acknowledge_status_event') as ack:
            for rid in ('missing', 'receipt-only', 'legacy'):
                self.assertIsNone(ra.select_current_recovery_status(self.receiver, rid))
                args = dict(self.arguments(legacy), request_id=rid,
                            expected_receipt_revision=2 if rid == 'legacy' else 1)
                with self.assertRaises(ra.RecoveryAckRefused) as ctx:
                    ra.acknowledge_current_recovery_status(self.receiver, **args, now=LATER)
                self.assertEqual(str(ctx.exception), 'recovery acknowledgement refused')
            selected = ra.select_current_recovery_status(self.receiver, 'acked')
            self.assertEqual(selected, dataclasses.replace(acked, ack_revision=1))
            for args in (self.arguments(acked), self.arguments(selected)):
                with self.assertRaises(ra.RecoveryAckRefused):
                    ra.acknowledge_current_recovery_status(self.receiver, **args, now=LATER)
            ack.assert_not_called()
        self.assertEqual((self.state(), self.files()), (before, files))
        self.assertEqual([e.event.event_id for e in self.receiver.inspect_status_events()],
                         [legacy.event_id])
        self.assertEqual(self.snap('legacy').accounting, dh.ReservationAccounting(20, 20))

    def test_k05_competing_ack_cas_and_new_event_after_inspection_truthful_old_result(self):
        self.retain('race-ack')
        self.retain('race-new')
        first = ra.select_current_recovery_status(self.receiver, 'race-ack')
        old = ra.select_current_recovery_status(self.receiver, 'race-new')
        peer = dh.DurableHandoffReceipts(self.path, scope=self.scope)
        real_inspect, box = ra.inspect_recovery_triage, {}

        def competing(receiver, rid):
            report = real_inspect(receiver, rid)
            peer.acknowledge_status_event(first.event_id, expected_ack_revision=0,
                                          now=NOW + timedelta(seconds=1))
            box['competing'] = self.state()
            return report

        with mock.patch.object(ra, 'inspect_recovery_triage', side_effect=competing) as read, \
             mock.patch.object(self.receiver, 'acknowledge_status_event',
                               wraps=self.receiver.acknowledge_status_event) as ack:
            with self.assertRaises(dh.ReceiptRevisionError):
                ra.acknowledge_current_recovery_status(
                    self.receiver, **self.arguments(first), now=LATER)
            read.assert_called_once_with(self.receiver, 'race-ack')
            ack.assert_called_once_with(first.event_id, expected_ack_revision=0, now=LATER)
        self.assertEqual(self.state(), box['competing'])

        def new_event(receiver, rid):
            report = real_inspect(receiver, rid)
            self.mark(rid, receiver=peer)  # independent receipt/event write AFTER read
            box['new'] = self.state()
            box['old_event'] = report.snapshot.current_status.event
            return report

        with mock.patch.object(ra, 'inspect_recovery_triage', side_effect=new_event) as read, \
             mock.patch.object(self.receiver, 'acknowledge_status_event',
                               wraps=self.receiver.acknowledge_status_event) as ack:
            result = ra.acknowledge_current_recovery_status(
                self.receiver, **self.arguments(old), now=LATER)
            read.assert_called_once_with(self.receiver, 'race-new')
            ack.assert_called_once_with(old.event_id, expected_ack_revision=0, now=LATER)
        self.assertEqual(result.event, box['old_event'])
        self.assertEqual((result.event.event_id, result.event.receipt_revision, result.ack_revision),
                         (old.event_id, 1, 1))
        current = self.snap('race-new')
        self.assertEqual((current.receipt.revision, current.current_status.event.receipt_revision,
                          current.current_status.ack_revision), (2, 2, 0))
        self.assertNotEqual(result.event.event_id, current.current_status.event.event_id)
        self.assertEqual(self.receiver.inspect_status_events(), (current.current_status,))
        self.assertEqual(self.without_acks(self.state()), self.without_acks(box['new']))
        for rid in ('race-ack', 'race-new'):
            self.assertEqual(self.snap(rid).accounting, dh.ReservationAccounting(20, 20))

    def test_k06_injected_time_errors_propagate_no_retry_no_constructor_concrete_receiver(self):
        self.retain('a')
        selected = ra.select_current_recovery_status(self.receiver, 'a')
        args = self.arguments(selected)
        before = self.state()

        class Clock(datetime):
            pass

        class ReceiverSubclass(dh.DurableHandoffReceipts):
            pass

        with mock.patch.object(dh.DurableHandoffReceipts, '__init__',
                               side_effect=AssertionError('no construction')):
            for time in (NOW - timedelta(seconds=1), None, NOW.replace(tzinfo=None),
                         NOW.astimezone(timezone(timedelta(hours=1))),
                         Clock(2026, 11, 17, 12, tzinfo=timezone.utc)):
                with mock.patch.object(ra, 'inspect_recovery_triage',
                                       wraps=ra.inspect_recovery_triage) as read, \
                     mock.patch.object(self.receiver, 'acknowledge_status_event',
                                       wraps=self.receiver.acknowledge_status_event) as ack:
                    with self.assertRaises((TypeError, ValueError)):
                        ra.acknowledge_current_recovery_status(self.receiver, **args, now=time)
                    read.assert_called_once_with(self.receiver, 'a')
                    ack.assert_called_once_with(selected.event_id, expected_ack_revision=0, now=time)
                    self.assertIs(ack.call_args.kwargs['now'], time)
                self.assertEqual(self.state(), before)
            for error in (dh.ReceiptStorageError('read failure'), RuntimeError('read failure')):
                with mock.patch.object(self.receiver, 'inspect_reservation',
                                       side_effect=error) as read, \
                     mock.patch.object(self.receiver, 'acknowledge_status_event') as ack:
                    with self.assertRaises(type(error)) as ctx:
                        ra.acknowledge_current_recovery_status(self.receiver, **args, now=LATER)
                    self.assertIs(ctx.exception, error)
                    read.assert_called_once_with('a')
                    ack.assert_not_called()
            for error in (dh.ReceiptRevisionError('CAS failure'),
                          dh.ReceiptStorageError('ack failure')):
                with mock.patch.object(ra, 'inspect_recovery_triage',
                                       wraps=ra.inspect_recovery_triage) as read, \
                     mock.patch.object(self.receiver, 'acknowledge_status_event',
                                       side_effect=error) as ack:
                    with self.assertRaises(type(error)) as ctx:
                        ra.acknowledge_current_recovery_status(self.receiver, **args, now=LATER)
                    self.assertIs(ctx.exception, error)
                    read.assert_called_once_with(self.receiver, 'a')
                    ack.assert_called_once_with(selected.event_id, expected_ack_revision=0, now=LATER)
            for receiver in (None, {}, mock.Mock(spec=dh.DurableHandoffReceipts),
                             object.__new__(ReceiverSubclass)):
                with self.assertRaises(TypeError):
                    ra.select_current_recovery_status(receiver, 'a')
                with self.assertRaises(TypeError):
                    ra.acknowledge_current_recovery_status(receiver, **args, now=LATER)
            self.assertEqual(self.state(), before)
            # A lost response AFTER a real commit remains an error, not retry
            # success. The retained ack survives for independent inspection.
            real_ack = self.receiver.acknowledge_status_event
            lost = dh.ReceiptStorageError('lost response')

            def commit_then_lose(*pos, **kw):
                real_ack(*pos, **kw)
                raise lost

            with mock.patch.object(self.receiver, 'acknowledge_status_event',
                                   side_effect=commit_then_lose) as ack, \
                 mock.patch.object(ra, 'inspect_recovery_triage',
                                   wraps=ra.inspect_recovery_triage) as read:
                with self.assertRaises(dh.ReceiptStorageError) as ctx:
                    ra.acknowledge_current_recovery_status(self.receiver, **args, now=LATER)
                self.assertIs(ctx.exception, lost)
                ack.assert_called_once_with(selected.event_id, expected_ack_revision=0, now=LATER)
                read.assert_called_once_with(self.receiver, 'a')
        self.assertEqual(self.snap('a').current_status.ack_revision, 1)
        self.assertEqual(self.without_acks(self.state()), self.without_acks(before))
        self.assertEqual(self.snap('a').accounting, dh.ReservationAccounting(20, 20))


if __name__ == '__main__':
    unittest.main()

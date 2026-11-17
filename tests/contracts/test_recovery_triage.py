"""T01–T06: exactly six NEW self-contained methods, authored NOT EXECUTED.

Real temporary BlobStore/private SQLite fixtures. No historical test imports.
All fixture identities, timestamps and worker-seconds values are synthetic.
"""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import FrozenInstanceError, asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from ai_agent_scientist.admission import durable_handoff as dh
from ai_agent_scientist.admission import recovery_triage as triage
from ai_agent_scientist.admission.handoff_binding import PayloadBinding
from ai_agent_scientist.evidence.blob_store import BlobStore


NOW = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
TABLES = ('durable_handoff_receipts', 'worker_seconds_envelope',
          'worker_seconds_reservations', 'reservation_status_events',
          'reservation_status_acks', 'local_usage_observations')


class RecoveryTriageContracts(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.root.chmod(0o700)
        (self.root / 'requests').mkdir(mode=0o700)
        (self.root / 'payloads').mkdir(mode=0o700)
        self.requests = BlobStore(self.root / 'requests', max_blob_bytes=8192)
        self.payloads = BlobStore(self.root / 'payloads', max_blob_bytes=128)
        digest = self.payloads.put(b'synthetic recovery payload\x00\xff')
        self.binding = PayloadBinding('object', digest, 'application/octet-stream',
            'synthetic', 128, True, NOW + timedelta(hours=2))
        self.scope = dh.TrustedHandoffScope('local-principal', 'project', 'scientist', 'ctf')
        self.path = str(self.root / 'receiver.sqlite3')
        self.receiver = self.reopen()
        self.envelope = dh.WorkerSecondsEnvelope(
            'synthetic-owner', 'synthetic-envelope', 410, 10, 1, 1, 8, 4)

    def reopen(self, scope=None):
        return dh.DurableHandoffReceipts(self.path, scope=self.scope if scope is None else scope)

    def retain(self, request_id='request-one', *, scope=None, receipt_only=False):
        scope = self.scope if scope is None else scope
        receiver = self.receiver if scope == self.scope else self.reopen(scope)
        suffix = '-'.join((request_id, scope.principal, scope.project_id,
                           scope.sender, scope.recipient))
        reservation_ref = 'reserve-' + suffix
        request = {
            'schema_version': 'harness-handoff/1', 'synthetic': True,
            'message_id': 'delivery-' + suffix, 'request_id': request_id,
            'attempt_id': None, 'replicate_id': None, 'project_id': scope.project_id,
            'sender': scope.sender, 'recipient': scope.recipient, 'kind': 'request',
            'in_reply_to': None, 'expected_revision': 0,
            'authorization_ref': 'authority-one', 'budget_reservation_ref': reservation_ref,
            'payload': {name: getattr(self.binding, name)
                        for name in ('id', 'sha256', 'media_type', 'classification')},
            'created_at': '2026-11-17T11:00:00Z', 'expires_at': '2026-11-17T13:00:00Z',
        }
        digest = self.requests.put(json.dumps(request).encode('utf-8'))
        kwargs = dict(payload_store=self.payloads, bindings={'object': self.binding}, now=NOW)
        if receipt_only:
            return receiver.record(self.requests, digest, **kwargs)
        authorities = {(scope.principal, scope.project_id, scope.sender, scope.recipient,
                        'authority-one', reservation_ref): dh.WorkerSecondsAuthority(
                            self.envelope, True, NOW + timedelta(hours=1))}
        return receiver.reserve(self.requests, digest, authorities=authorities, **kwargs)

    def observe(self, reserved, observation_id, *, revision=1, usage=None,
                stopped=False, cleanup=False, seconds=1):
        reservation = reserved.reservation
        return self.receiver.record_usage_observation(observation_id,
            request_id=reservation.request_id,
            budget_reservation_ref=reservation.budget_reservation_ref,
            request_sha256=reservation.request_sha256, expected_revision=revision,
            worker_seconds=usage, execution_stopped=stopped, cleanup_known=cleanup,
            observed_at=NOW + timedelta(seconds=seconds))

    def rows(self):
        with closing(sqlite3.connect(self.path)) as conn:
            return tuple(conn.execute('SELECT * FROM ' + name + ' ORDER BY 1').fetchall()
                         for name in TABLES)

    def sql(self, statement):
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute(statement)

    def test_t01_missing_recorded_pure_deterministic_frozen_full_retention(self):
        self.assertIsNone(triage.inspect_recovery_triage(self.receiver, 'absent'))
        self.retain('receipt-only', receipt_only=True)
        self.assertIsNone(triage.inspect_recovery_triage(self.receiver, 'receipt-only'))
        reserved = self.retain()
        before = self.rows()
        snapshot = self.receiver.inspect_reservation('request-one')
        report = triage.classify_reservation(snapshot, scope=self.scope)
        self.assertEqual(report, triage.classify_reservation(snapshot, scope=self.scope))
        self.assertIs(report.snapshot, snapshot)
        self.assertEqual(report.snapshot.reservation, reserved.reservation)
        self.assertEqual(report.snapshot.accounting, dh.ReservationAccounting(20, 20))
        self.assertEqual(report.reasons, (
            'reservation_fully_outstanding', 'receipt_recorded', 'local_ack_pending',
            'no_observation', 'usage_unknown', 'execution_not_independently_stopped',
            'cleanup_unknown'))
        with mock.patch.object(self.receiver, 'inspect_reservation',
                               wraps=self.receiver.inspect_reservation) as inspect:
            connected = triage.inspect_recovery_triage(self.receiver, 'request-one')
        inspect.assert_called_once_with('request-one')
        self.assertEqual(connected, report)
        for directory in (self.root / 'requests', self.root / 'payloads'):
            for path in directory.iterdir():
                path.unlink()
        with mock.patch.object(dh, 'load_bound_handoff_request',
                               side_effect=AssertionError('no blob or authority loading')):
            self.assertEqual(triage.inspect_recovery_triage(self.reopen(), 'request-one'), report)
        with self.assertRaises(FrozenInstanceError):
            report.reasons = ()
        with self.assertRaises(FrozenInstanceError):
            report.snapshot.reservation.worker_seconds = 0
        with self.assertRaises(FrozenInstanceError):
            report.snapshot.accounting.outstanding_worker_seconds = 0
        self.assertFalse(hasattr(report, '__dict__'))
        self.assertEqual(set(asdict(report)), {'snapshot', 'reasons'})
        self.assertNotIn(self.envelope.owner_namespace, json.dumps(asdict(report)))
        self.assertNotIn(self.envelope.envelope_id, json.dumps(asdict(report)))
        self.assertEqual(self.rows(), before)

    def test_t02_zero_unknown_stopped_cleanup_and_over_cap_are_separate(self):
        reserved = self.retain()
        accounting = self.rows()[1:3]
        zero = self.observe(reserved, 'zero', usage=0, stopped=True, cleanup=True)
        report = triage.inspect_recovery_triage(self.receiver, 'request-one')
        self.assertEqual(report.reasons, ('reservation_fully_outstanding',
            'receipt_reconciliation_required', 'local_ack_pending',
            'latest_insertion_view_only', 'usage_known_zero'))
        self.assertEqual(report.snapshot.latest_usage_observation, zero)
        unknown = self.observe(reserved, 'unknown', revision=2, seconds=2)
        report = triage.inspect_recovery_triage(self.receiver, 'request-one')
        self.assertEqual(report.snapshot.latest_usage_observation, unknown)
        self.assertIn('usage_unknown', report.reasons)
        self.assertNotIn('usage_known_zero', report.reasons)
        self.assertNotIn('no_observation', report.reasons)
        self.assertIn('execution_not_independently_stopped', report.reasons)
        self.assertIn('cleanup_unknown', report.reasons)
        self.assertIsNone(report.snapshot.latest_usage_observation.over_cap)
        overrun = self.observe(reserved, 'overrun', revision=2, usage=(1 << 63) - 1,
                               stopped=True, cleanup=False, seconds=3)
        report = triage.inspect_recovery_triages(self.receiver).entries[0]
        self.assertIn('observed_over_cap', report.reasons)
        self.assertIn('usage_known_positive', report.reasons)
        self.assertNotIn('execution_not_independently_stopped', report.reasons)
        self.assertIn('cleanup_unknown', report.reasons)
        self.assertEqual(report.snapshot.latest_usage_observation, overrun)
        for stopped, cleanup in ((False, True), (True, False), (True, True), (False, False)):
            snapshot = replace(report.snapshot, latest_usage_observation=replace(
                overrun, execution_stopped=stopped, cleanup_known=cleanup))
            classified = triage.classify_reservation(snapshot, scope=self.scope)
            self.assertEqual('execution_not_independently_stopped' in classified.reasons,
                             not stopped)
            self.assertEqual('cleanup_unknown' in classified.reasons, not cleanup)
            self.assertEqual(classified.snapshot.accounting, dh.ReservationAccounting(20, 20))
        self.assertEqual(self.rows()[1:3], accounting)

    def test_t03_latest_insertion_replay_reconciliation_ack_and_missing_status(self):
        reserved = self.retain()
        self.receiver.require_reconciliation('request-one', expected_revision=1, now=NOW)
        report = triage.inspect_recovery_triage(self.receiver, 'request-one')
        self.assertIn('receipt_reconciliation_required', report.reasons)
        self.assertIn('no_observation', report.reasons)
        later_time = self.observe(reserved, 'later-time', revision=2, usage=9, seconds=30)
        latest_insert = self.observe(reserved, 'latest-insert', revision=2, seconds=2)
        self.assertLess(latest_insert.observed_at, later_time.observed_at)
        self.assertGreater(latest_insert.sequence, later_time.sequence)
        self.assertEqual(self.observe(reserved, 'later-time', revision=2, usage=9, seconds=30),
                         later_time)
        current = self.receiver.inspect_reservation('request-one').current_status
        self.receiver.acknowledge_status_event(current.event.event_id,
            expected_ack_revision=0, now=NOW + timedelta(seconds=31))
        before = self.rows()
        report = triage.inspect_recovery_triage(self.reopen(), 'request-one')
        self.assertEqual(report.snapshot.latest_usage_observation, latest_insert)
        self.assertIn('usage_unknown', report.reasons)
        self.assertIn('local_acknowledged', report.reasons)
        self.assertNotIn('local_ack_pending', report.reasons)
        self.assertEqual(report.snapshot.accounting.outstanding_worker_seconds, 20)
        self.assertEqual(self.rows(), before)
        # Emulate older storage with no current-revision outbox event. The
        # remaining revision-1 event must never stand in for revision 2.
        self.sql('DROP TRIGGER reservation_status_no_delete')
        self.sql('DELETE FROM reservation_status_events WHERE receipt_revision=2')
        before = self.rows()
        report = triage.inspect_recovery_triage(self.receiver, 'request-one')
        self.assertIsNone(report.snapshot.current_status)
        self.assertIn('current_status_missing', report.reasons)
        self.assertIn('local_ack_unknown', report.reasons)
        self.assertNotIn('local_acknowledged', report.reasons)
        self.assertEqual(self.rows(), before)

    def test_t04_real_scoped_bounded_pages_exact_inputs_and_no_global_totals(self):
        self.retain('request-c')
        self.retain('request-a')
        self.retain('request-b')
        for scope in (replace(self.scope, principal='other'),
                      replace(self.scope, project_id='other'),
                      replace(self.scope, recipient='sleep')):
            self.retain('foreign', scope=scope)
            page = triage.inspect_recovery_triages(self.reopen(scope))
            self.assertEqual(tuple(r.snapshot.reservation.request_id for r in page.entries),
                             ('foreign',))
            self.assertIsNone(triage.inspect_recovery_triage(self.reopen(scope), 'request-a'))
        before = self.rows()
        receiver = self.reopen()
        with mock.patch.object(receiver, 'inspect_reservations',
                               wraps=receiver.inspect_reservations) as inspect:
            one = triage.inspect_recovery_triages(receiver, limit=2)
        inspect.assert_called_once_with(after_request_id=None, limit=2)
        self.assertEqual(tuple(r.snapshot.reservation.request_id for r in one.entries),
                         ('request-a', 'request-b'))
        self.assertEqual(one.next_after_request_id, 'request-b')
        two = triage.inspect_recovery_triages(receiver,
            after_request_id=one.next_after_request_id, limit=2)
        self.assertEqual(tuple(r.snapshot.reservation.request_id for r in two.entries),
                         ('request-c',))
        self.assertIsNone(two.next_after_request_id)
        self.assertEqual(triage.inspect_recovery_triages(receiver).entries, one.entries + two.entries)
        self.assertEqual(triage.inspect_recovery_triages(receiver,
            after_request_id='request-z').entries, ())
        self.assertEqual(len(triage.inspect_recovery_triages(receiver,
            after_request_id='request-aa').entries), 2)
        with self.assertRaises(FrozenInstanceError):
            one.next_after_request_id = 'changed'
        encoded = json.dumps(asdict(one))
        self.assertNotIn('foreign', encoded)
        self.assertNotIn(self.envelope.owner_namespace, encoded)
        self.assertNotIn(self.envelope.envelope_id, encoded)
        self.assertEqual(set(asdict(one)), {'entries', 'next_after_request_id'})
        self.assertEqual(set(asdict(one.entries[0].snapshot.accounting)),
                         {'allocation_worker_seconds', 'outstanding_worker_seconds'})
        class Text(str):
            pass
        class Number(int):
            pass
        for value in (True, 0, 101, 1.0, '1', Number(1), None):
            with self.assertRaises(ValueError):
                triage.inspect_recovery_triages(receiver, limit=value)
        for value in (True, '', Text('request-a'), b'x', 'x' * 1025, '界' * 342, '\ud800', '\x00'):
            with self.assertRaises(triage.InvalidRecoverySnapshot):
                triage.inspect_recovery_triage(receiver, value)
            with self.assertRaises(triage.InvalidRecoverySnapshot):
                triage.inspect_recovery_triages(receiver, after_request_id=value)
        self.assertIsNone(triage.inspect_recovery_triage(receiver, '界' * 341 + 'x'))
        self.assertEqual(triage.inspect_recovery_triages(receiver,
            after_request_id='x' * 1024).entries, ())
        wrong_sender = self.reopen(replace(self.scope, sender='sleep'))
        with self.assertRaises(dh.ReceiptScopeError):
            triage.inspect_recovery_triages(wrong_sender)
        with self.assertRaises(dh.ReceiptScopeError):
            triage.inspect_recovery_triage(wrong_sender, 'request-a')
        for candidate in (object(), mock.Mock(spec=dh.DurableHandoffReceipts)):
            with self.assertRaises(TypeError):
                triage.inspect_recovery_triages(candidate)
            with self.assertRaises(TypeError):
                triage.inspect_recovery_triage(candidate, 'request-a')
        self.assertEqual(self.rows(), before)

    def test_t05_pure_rejects_malformed_exact_types_and_forged_binding_summaries(self):
        reserved = self.retain()
        self.observe(reserved, 'observation', usage=0, stopped=True, cleanup=True)
        snapshot = self.receiver.inspect_reservation('request-one')
        receipt, reservation = snapshot.receipt, snapshot.reservation
        status, observation = snapshot.current_status, snapshot.latest_usage_observation
        class Text(str):
            pass
        class Number(int):
            pass
        class ForgedSnapshot(dh.ReservationSnapshot):
            pass
        class Hostile:
            def __eq__(self, other):
                raise AssertionError('must reject before equality hooks')
        malformed = [None, {}, ForgedSnapshot(receipt, reservation, snapshot.accounting,
                                              status, observation)]
        for name in ('principal', 'project_id', 'recipient', 'request_id', 'sender', 'request_sha256'):
            value = '0' * 64 if name == 'request_sha256' else 'different'
            for field, original in (('receipt', receipt), ('reservation', reservation),
                                    ('latest_usage_observation', observation)):
                malformed.append(replace(snapshot, **{field: replace(original, **{name: value})}))
            malformed.append(replace(snapshot, current_status=replace(status,
                event=replace(status.event, **{name: value}))))
        for field, values in (
            ('receipt', ({'revision': True}, {'revision': Number(2)}, {'revision': 3},
                         {'state': 'recorded'}, {'state': Hostile()},
                         {'message_id': ''}, {'payload_sha256': 'G' * 64},
                         {'recorded_at': 'bad'}, {'updated_at': '2026-11-17T11:00:00.000000Z'})),
            ('reservation', ({'worker_seconds': True}, {'worker_seconds': 0},
                             {'authorization_ref': Text('authority')},
                             {'budget_reservation_ref': 'different'}, {'recorded_at': 'bad'})),
            ('accounting', ({'allocation_worker_seconds': 19},
                            {'outstanding_worker_seconds': 0}, {'outstanding_worker_seconds': 19},
                            {'allocation_worker_seconds': Number(20)})),
            ('latest_usage_observation', ({'sequence': 0}, {'sequence': True},
                {'sequence': 1 << 63}, {'observation_id': ''},
                {'observation_id': Hostile()}, {'budget_reservation_ref': 'different'},
                {'expected_revision': True}, {'expected_revision': 0}, {'expected_revision': 3},
                {'worker_seconds': None}, {'worker_seconds': True}, {'worker_seconds': -1},
                {'worker_seconds': 1 << 63}, {'over_cap': None}, {'over_cap': True},
                {'over_cap': 0}, {'execution_stopped': 1}, {'cleanup_known': 0},
                {'observed_at': '2026-11-17T12:00:02.000000Z'}))):
            original = getattr(snapshot, field)
            malformed.extend(replace(snapshot, **{field: replace(original, **values_one)})
                             for values_one in values)
        for changes in ({'event_id': 0}, {'event_id': True}, {'budget_reservation_ref': 'different'},
                        {'receipt_revision': 1}, {'receipt_revision': True},
                        {'status': 'reservation_retained'}, {'status': Text('reconciliation_required')},
                        {'worker_seconds': 19}, {'worker_seconds': True}, {'created_at': 'bad'}):
            malformed.append(replace(snapshot, current_status=replace(status,
                event=replace(status.event, **changes))))
        for changes in ({'ack_revision': True}, {'ack_revision': 2}, {'ack_revision': 1},
                        {'acknowledged_at': '2026-11-17T12:00:02.000000Z'},
                        {'ack_revision': 1, 'acknowledged_at': '2026-11-17T11:00:00.000000Z'}):
            malformed.append(replace(snapshot, current_status=replace(status, **changes)))
        for field in ('receipt', 'reservation', 'accounting', 'current_status',
                      'latest_usage_observation'):
            malformed.append(replace(snapshot, **{field: {}}))
        malformed.append(replace(snapshot, receipt=replace(receipt,
            revision=1, state='recorded', updated_at=receipt.recorded_at)))
        malformed.append(replace(snapshot, latest_usage_observation=replace(
            observation, worker_seconds=None, over_cap=False)))
        before = self.rows()
        for index, candidate in enumerate(malformed):
            with self.subTest(case=index), self.assertRaises(triage.InvalidRecoverySnapshot):
                triage.classify_reservation(candidate, scope=self.scope)
        for scope in (None, {}, replace(self.scope, principal='other'),
                      replace(self.scope, sender='sleep'), replace(self.scope, principal=Hostile())):
            with self.assertRaises(triage.InvalidRecoverySnapshot):
                triage.classify_reservation(snapshot, scope=scope)
        self.assertEqual(self.rows(), before)

    def test_t06_one_real_read_transaction_failures_no_partial_reports_or_writes(self):
        self.retain('request-a')
        self.retain('request-b')
        before = self.rows()
        actual_connect = sqlite3.connect
        connections, statements = [], []
        def connect(*args, **kwargs):
            conn = actual_connect(*args, **kwargs)
            conn.set_trace_callback(statements.append)
            connections.append(conn)
            return conn
        with mock.patch.object(dh.sqlite3, 'connect', side_effect=connect):
            page = triage.inspect_recovery_triages(self.receiver, limit=2)
        self.assertEqual(len(page.entries), 2)
        self.assertEqual(len(connections), 1)
        self.assertEqual(statements.count('BEGIN'), 1)
        self.assertEqual(statements.count('COMMIT'), 1)
        self.assertFalse(any(s.startswith(('INSERT ', 'UPDATE ', 'DELETE ', 'CREATE '))
                             for s in statements))
        self.assertEqual(self.rows(), before)
        statements.clear()
        connections.clear()
        with mock.patch.object(dh.sqlite3, 'connect', side_effect=connect):
            self.assertIsNotNone(triage.inspect_recovery_triage(self.receiver, 'request-a'))
        self.assertEqual(len(connections), 1)
        self.assertEqual(statements.count('BEGIN'), 1)
        # Real malformed later-row accounting fails the entire page.
        self.sql("UPDATE worker_seconds_reservations SET worker_seconds=19 "
                 "WHERE request_id='request-b'")
        inconsistent = self.rows()
        with self.assertRaises(dh.ReceiptConflict):
            triage.inspect_recovery_triages(self.receiver)
        self.assertEqual(self.rows(), inconsistent)
        self.sql("UPDATE worker_seconds_reservations SET worker_seconds=20 "
                 "WHERE request_id='request-b'")
        # The old inspection seam retains a DB ack_revision=1 with malformed
        # timestamp; the new pure layer must reject it, without repair/write.
        event = self.receiver.inspect_reservation('request-b').current_status.event
        self.sql('INSERT INTO reservation_status_acks VALUES (' + str(event.event_id) + ",1,'bad')")
        malformed = self.rows()
        with self.assertRaises(triage.InvalidRecoverySnapshot):
            triage.inspect_recovery_triages(self.receiver)
        with self.assertRaises(triage.InvalidRecoverySnapshot):
            triage.inspect_recovery_triage(self.receiver, 'request-b')
        self.assertEqual(self.rows(), malformed)
        self.sql('DROP TABLE local_usage_observations')
        with self.assertRaises(dh.ReceiptStorageError):
            triage.inspect_recovery_triages(self.receiver)
        with self.assertRaises(dh.ReceiptStorageError):
            triage.inspect_recovery_triage(self.receiver, 'request-a')

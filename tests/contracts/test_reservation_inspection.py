"""I01–I06: exactly six authored methods, NOT EXECUTED.

Self-contained real BlobStore/private SQLite fixtures; no historical test imports.
All values are synthetic. Execution and acceptance remain pending.
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
from ai_agent_scientist.admission.handoff_binding import PayloadBinding
from ai_agent_scientist.evidence.blob_store import BlobStore


NOW = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
TABLES = ('durable_handoff_receipts', 'worker_seconds_envelope',
          'worker_seconds_reservations', 'reservation_status_events',
          'reservation_status_acks', 'local_usage_observations')


class ReservationInspectionContracts(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.root.chmod(0o700)
        (self.root / 'requests').mkdir(mode=0o700)
        (self.root / 'payloads').mkdir(mode=0o700)
        self.requests = BlobStore(self.root / 'requests', max_blob_bytes=8192)
        self.payloads = BlobStore(self.root / 'payloads', max_blob_bytes=128)
        digest = self.payloads.put(b'synthetic inspection payload\x00\xff')
        self.binding = PayloadBinding('object', digest, 'application/octet-stream',
            'synthetic', 128, True, NOW + timedelta(hours=2))
        self.scope = dh.TrustedHandoffScope('local-principal', 'project', 'scientist', 'ctf')
        self.path = str(self.root / 'receiver.sqlite3')
        self.receiver = self.reopen()
        self.envelope = dh.WorkerSecondsEnvelope(
            'synthetic-budget-owner', 'synthetic-fixed-envelope', 210, 10, 1, 1, 8, 4)

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

    def retained_rows(self):
        with closing(sqlite3.connect(self.path)) as conn:
            return tuple(conn.execute('SELECT * FROM ' + name + ' ORDER BY 1').fetchall()
                         for name in TABLES)

    def sql(self, statement):
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute(statement)

    def test_i01_reopen_exact_lookup_and_bounded_scoped_pages(self):
        third = self.retain('request-c')
        first = self.retain('request-a')
        self.retain('request-b', scope=replace(self.scope, principal='foreign-principal'))
        second = self.retain('request-b')
        before = self.retained_rows()
        receiver = self.reopen()
        one = receiver.inspect_reservations(limit=1)
        self.assertIs(type(one), dh.ReservationSnapshotPage)
        self.assertIs(type(one.entries), tuple)
        self.assertEqual(tuple(s.reservation for s in one.entries), (first.reservation,))
        self.assertEqual(one.next_after_request_id, 'request-a')
        two = receiver.inspect_reservations(after_request_id=one.next_after_request_id, limit=1)
        self.assertEqual(tuple(s.reservation for s in two.entries), (second.reservation,))
        self.assertEqual(two.next_after_request_id, 'request-b')
        three = receiver.inspect_reservations(after_request_id=two.next_after_request_id, limit=1)
        self.assertEqual(tuple(s.reservation for s in three.entries), (third.reservation,))
        self.assertIsNone(three.next_after_request_id)
        empty = receiver.inspect_reservations(after_request_id='request-z', limit=100)
        self.assertEqual((empty.entries, empty.next_after_request_id), ((), None))
        self.assertEqual(receiver.inspect_reservation('request-a'), one.entries[0])
        self.assertEqual(receiver.inspect_reservations(limit=100).entries,
                         one.entries + two.entries + three.entries)
        foreign = self.reopen(replace(self.scope, principal='foreign-principal'))
        self.assertNotEqual(foreign.inspect_reservation('request-b').reservation, second.reservation)
        self.assertEqual(len(foreign.inspect_reservations().entries), 1)
        encoded = json.dumps(asdict(receiver.inspect_reservations()))
        self.assertNotIn('foreign-principal', encoded)
        self.assertNotIn(self.envelope.owner_namespace, encoded)
        self.assertNotIn(self.envelope.envelope_id, encoded)
        self.assertEqual(set(asdict(one.entries[0].accounting)),
                         {'allocation_worker_seconds', 'outstanding_worker_seconds'})
        with self.assertRaises(FrozenInstanceError):
            one.next_after_request_id = 'changed'
        with self.assertRaises(FrozenInstanceError):
            one.entries[0].receipt = third.receipt
        with self.assertRaises(FrozenInstanceError):
            one.entries[0].accounting.outstanding_worker_seconds = 0
        self.assertEqual(self.retained_rows(), before)

    def test_i02_absent_receipt_only_and_no_observation_need_no_blob_or_authority(self):
        self.assertIsNone(self.receiver.inspect_reservation('absent'))
        self.assertEqual(self.receiver.inspect_reservations().entries, ())
        self.retain('receipt-only', receipt_only=True)
        self.assertIsNone(self.receiver.inspect_reservation('receipt-only'))
        reserved = self.retain()
        before = self.retained_rows()
        # Make fixture blobs unavailable; inspection uses retained SQLite only.
        for directory in (self.root / 'requests', self.root / 'payloads'):
            for path in directory.iterdir():
                path.unlink()
        with mock.patch.object(dh, 'load_bound_handoff_request',
                               side_effect=AssertionError('inspection must not load blobs')):
            snapshot = self.reopen().inspect_reservation('request-one')
            page = self.receiver.inspect_reservations()
        self.assertIs(type(snapshot), dh.ReservationSnapshot)
        self.assertEqual((snapshot.receipt, snapshot.reservation),
                         (reserved.receipt, reserved.reservation))
        self.assertIsNone(snapshot.latest_usage_observation)
        self.assertEqual(snapshot.accounting, dh.ReservationAccounting(20, 20))
        self.assertEqual(snapshot.current_status, self.receiver.inspect_status_events()[0])
        self.assertEqual(snapshot.current_status.event.status, 'reservation_retained')
        self.assertEqual(page.entries, (snapshot,))
        self.assertEqual(self.retained_rows(), before)

    def test_i03_known_zero_unknown_overrun_and_cleanup_never_reduce_outstanding(self):
        reserved = self.retain()
        accounting_before = self.retained_rows()[1:3]
        zero = self.observe(reserved, 'zero', usage=0, stopped=True, cleanup=True)
        snapshot = self.receiver.inspect_reservation('request-one')
        self.assertEqual(snapshot.latest_usage_observation, zero)
        self.assertIs(type(snapshot.latest_usage_observation.worker_seconds), int)
        self.assertEqual(snapshot.latest_usage_observation.worker_seconds, 0)
        self.assertIs(snapshot.latest_usage_observation.over_cap, False)
        self.assertEqual(snapshot.accounting, dh.ReservationAccounting(20, 20))
        unknown = self.observe(reserved, 'unknown', revision=2, seconds=2)
        snapshot = self.reopen().inspect_reservation('request-one')
        self.assertEqual(snapshot.latest_usage_observation, unknown)
        self.assertIsNone(snapshot.latest_usage_observation.worker_seconds)
        self.assertIsNone(snapshot.latest_usage_observation.over_cap)
        self.assertFalse(snapshot.latest_usage_observation.execution_stopped)
        self.assertFalse(snapshot.latest_usage_observation.cleanup_known)
        overrun = self.observe(reserved, 'overrun', revision=2, usage=(1 << 63) - 1,
                               stopped=True, cleanup=False, seconds=3)
        snapshot = self.receiver.inspect_reservations().entries[0]
        self.assertEqual(snapshot.latest_usage_observation, overrun)
        self.assertIs(snapshot.latest_usage_observation.over_cap, True)
        self.assertEqual(snapshot.accounting, dh.ReservationAccounting(20, 20))
        self.assertEqual(self.retained_rows()[1:3], accounting_before)

    def test_i04_reconciliation_current_ack_and_latest_insertion_not_timestamp(self):
        reserved = self.retain()
        current = self.receiver.require_reconciliation('request-one', expected_revision=1, now=NOW)
        no_usage = self.receiver.inspect_reservation('request-one')
        self.assertEqual(no_usage.receipt, current)
        self.assertIsNone(no_usage.latest_usage_observation)
        self.assertEqual(no_usage.current_status.event.receipt_revision, 2)
        self.assertEqual(no_usage.current_status.event.status, 'reconciliation_required')
        later_time = self.observe(reserved, 'later-time', revision=2, usage=9, seconds=30)
        latest_insert = self.observe(reserved, 'latest-insert', revision=2, usage=4, seconds=2)
        self.assertGreater(latest_insert.sequence, later_time.sequence)
        self.assertLess(latest_insert.observed_at, later_time.observed_at)
        ack = self.receiver.acknowledge_status_event(no_usage.current_status.event.event_id,
            expected_ack_revision=0, now=NOW + timedelta(seconds=31))
        before = self.retained_rows()
        snapshot = self.reopen().inspect_reservation('request-one')
        self.assertEqual(snapshot.receipt, current)
        self.assertEqual(snapshot.latest_usage_observation, latest_insert)
        self.assertEqual(snapshot.current_status, ack)
        self.assertEqual(snapshot.accounting, dh.ReservationAccounting(20, 20))
        # Replaying an older observation does not make it newly inserted.
        self.assertEqual(self.observe(reserved, 'later-time', revision=2, usage=9, seconds=30),
                         later_time)
        self.assertEqual(self.receiver.inspect_reservations().entries, (snapshot,))
        self.assertEqual(self.retained_rows(), before)

    def test_i05_scope_sender_exact_types_cursor_and_limit_boundaries(self):
        class Text(str):
            pass

        class Number(int):
            pass

        self.retain()
        for scope in (replace(self.scope, principal='elsewhere'),
                      replace(self.scope, project_id='elsewhere'),
                      replace(self.scope, recipient='sleep')):
            other = self.reopen(scope)
            self.assertIsNone(other.inspect_reservation('request-one'))
            self.assertEqual(other.inspect_reservations().entries, ())
        wrong_sender = self.reopen(replace(self.scope, sender='sleep'))
        with self.assertRaises(dh.ReceiptScopeError):
            wrong_sender.inspect_reservation('request-one')
        with self.assertRaises(dh.ReceiptScopeError):
            wrong_sender.inspect_reservations()
        before = self.retained_rows()
        for value in (None, True, 1, b'request-one', Text('request-one'), ''):
            with self.assertRaises(TypeError):
                self.receiver.inspect_reservation(value)
        for value in ('\x00', 'x' * 1025, '界' * 342, '\ud800'):
            with self.assertRaises(ValueError):
                self.receiver.inspect_reservation(value)
            with self.assertRaises(ValueError):
                self.receiver.inspect_reservations(after_request_id=value)
        for value in (True, 0, b'request-one', Text('request-one'), ''):
            with self.assertRaises(TypeError):
                self.receiver.inspect_reservations(after_request_id=value)
        for value in (True, False, 0, -1, 101, 1 << 63, 1.0, '1', Number(1), None):
            with self.assertRaises(ValueError):
                self.receiver.inspect_reservations(limit=value)
        self.assertIsNone(self.receiver.inspect_reservation('x' * 1024))
        self.assertIsNone(self.receiver.inspect_reservation('界' * 341 + 'x'))
        self.assertEqual(self.receiver.inspect_reservations(after_request_id='x' * 1024).entries, ())
        # Seek cursors need not name an existing row, and SQL text stays data.
        self.assertEqual(len(self.receiver.inspect_reservations(after_request_id="' OR 1=1 --").entries), 1)
        self.assertEqual(self.retained_rows(), before)

    def test_i06_one_read_transaction_and_failures_return_no_partial_view(self):
        self.retain('request-a')
        second = self.retain('request-b')
        before = self.retained_rows()
        actual_connect = sqlite3.connect
        connections, statements = [], []

        def connect(*args, **kwargs):
            connection = actual_connect(*args, **kwargs)
            connection.set_trace_callback(statements.append)
            connections.append(connection)
            return connection

        with mock.patch.object(dh.sqlite3, 'connect', side_effect=connect):
            page = self.receiver.inspect_reservations(limit=2)
        self.assertEqual(len(page.entries), 2)
        self.assertEqual(len(connections), 1)
        self.assertEqual(statements.count('BEGIN'), 1)
        self.assertEqual(statements.count('COMMIT'), 1)
        self.assertFalse(any(s.startswith(('INSERT ', 'UPDATE ', 'DELETE ')) for s in statements))
        self.assertEqual(self.retained_rows(), before)
        # A malformed later row must fail the whole page, after the first row
        # was decoded. No partial successful return and no implicit repair.
        self.sql("UPDATE worker_seconds_reservations SET worker_seconds=19 "
                 "WHERE request_id='request-b'")
        inconsistent = self.retained_rows()
        with self.assertRaises(dh.ReceiptConflict):
            self.receiver.inspect_reservations(limit=2)
        with self.assertRaises(dh.ReceiptConflict):
            self.receiver.inspect_reservation(second.reservation.request_id)
        self.assertEqual(self.retained_rows(), inconsistent)
        self.sql("UPDATE worker_seconds_reservations SET worker_seconds=20 "
                 "WHERE request_id='request-b'")
        # A real SQLite read failure is wrapped, including for exact lookup.
        self.sql('DROP TABLE local_usage_observations')
        with self.assertRaises(dh.ReceiptStorageError):
            self.receiver.inspect_reservation('request-a')
        with self.assertRaises(dh.ReceiptStorageError):
            self.receiver.inspect_reservations()

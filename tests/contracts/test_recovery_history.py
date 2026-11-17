"""H01-H06: six self-contained offline methods authored, NOT EXECUTED.

Real private SQLite/BlobStore fixtures copied from recovery contract setup;
no historical test classes or operational stores are imported or used.
"""
import dataclasses
import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from ai_agent_scientist.admission import durable_handoff as dh
from ai_agent_scientist.admission.handoff_binding import PayloadBinding
from ai_agent_scientist.evidence.blob_store import BlobStore

NOW = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
LATER = NOW + timedelta(seconds=2)
MAX_INT = (1 << 63) - 1


class RecoveryHistoryContracts(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.root.chmod(0o700)
        for name in ('requests', 'payloads'):
            (self.root / name).mkdir(mode=0o700)
        self.requests = BlobStore(self.root / 'requests', max_blob_bytes=8192)
        self.payloads = BlobStore(self.root / 'payloads', max_blob_bytes=128)
        digest = self.payloads.put(b'synthetic private history payload')
        self.binding = PayloadBinding('object', digest, 'application/octet-stream',
            'synthetic', 128, True, NOW + timedelta(hours=2))
        self.scope = dh.TrustedHandoffScope('principal', 'project', 'scientist', 'ctf')
        self.path = str(self.root / 'receiver.sqlite3')
        self.receiver = dh.DurableHandoffReceipts(self.path, scope=self.scope)
        self.envelope = dh.WorkerSecondsEnvelope('private-owner', 'private-envelope',
                                                410, 10, 1, 1, 8, 4)

    def retain(self, rid, *, receiver=None, receipt_only=False):
        receiver = self.receiver if receiver is None else receiver
        s = receiver._scope
        suffix = '-'.join((rid, s.principal, s.project_id, s.sender, s.recipient))
        ref = 'reserve-' + suffix
        request = {
            'schema_version': 'harness-handoff/1', 'synthetic': True,
            'message_id': 'message-' + suffix, 'request_id': rid,
            'attempt_id': None, 'replicate_id': None, 'project_id': s.project_id,
            'sender': s.sender, 'recipient': s.recipient, 'kind': 'request',
            'in_reply_to': None, 'expected_revision': 0,
            'authorization_ref': 'private-authority', 'budget_reservation_ref': ref,
            'payload': {n: getattr(self.binding, n)
                        for n in ('id', 'sha256', 'media_type', 'classification')},
            'created_at': '2026-11-17T11:00:00Z', 'expires_at': '2026-11-17T13:00:00Z',
        }
        digest = self.requests.put(json.dumps(request).encode('utf-8'))
        kwargs = dict(payload_store=self.payloads, bindings={'object': self.binding}, now=NOW)
        if receipt_only:
            return receiver.record(self.requests, digest, **kwargs)
        authorities = {(s.principal, s.project_id, s.sender, s.recipient,
            'private-authority', ref): dh.WorkerSecondsAuthority(
                self.envelope, True, NOW + timedelta(hours=1))}
        return receiver.reserve(self.requests, digest, authorities=authorities, **kwargs)

    def mark(self, rid, *, receiver=None):
        receiver = self.receiver if receiver is None else receiver
        return receiver.require_reconciliation(rid, expected_revision=1,
                                               now=NOW + timedelta(seconds=1))

    def history(self, rid, **kwargs):
        return self.receiver.inspect_reservation_status_history(rid, **kwargs)

    def state(self):
        with closing(sqlite3.connect(self.path)) as conn:
            return tuple(conn.iterdump())

    def files(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def sql(self, statement, parameters=()):
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute(statement, parameters)

    def test_h01_exact_frozen_read_only_history_old_ack_new_pending_full_budget(self):
        retained = self.retain('selected')
        old = self.receiver.inspect_reservation('selected').current_status
        self.mark('selected')
        acked = self.receiver.acknowledge_status_event(old.event.event_id,
                                                      expected_ack_revision=0, now=LATER)
        current = self.receiver.inspect_reservation('selected')
        before, files = self.state(), self.files()
        with mock.patch.object(self.receiver, 'inspect_status_events',
                               side_effect=AssertionError('no global feed')), \
             mock.patch.object(self.receiver, 'inspect_reservation',
                               side_effect=AssertionError('no independent snapshot')):
            result = self.history('selected')
        self.assertIs(type(result), dh.ReservationStatusHistory)
        self.assertEqual([f.name for f in dataclasses.fields(result)],
                         ['snapshot', 'entries', 'next_after_event_id'])
        self.assertFalse(hasattr(result, '__dict__'))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.next_after_event_id = 1
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.entries[0].ack_revision = 0
        self.assertIs(type(result.entries), tuple)
        self.assertEqual(result.snapshot, current)
        self.assertEqual(result.snapshot.reservation, retained.reservation)
        self.assertEqual(result.snapshot.accounting, dh.ReservationAccounting(20, 20))
        self.assertEqual(result.entries, (acked, current.current_status))
        self.assertEqual((result.entries[0].ack_revision,
                          result.snapshot.current_status.ack_revision), (1, 0))
        self.assertEqual(result.snapshot.receipt.revision, 2)
        self.assertIsNone(result.next_after_event_id)
        self.assertEqual((self.state(), self.files()), (before, files))

    def test_h02_strict_seek_limits_pagination_request_and_scope_isolation(self):
        self.retain('selected')
        self.retain('other')  # interleaved global event ID, never in this page
        foreign = dh.DurableHandoffReceipts(self.path, scope=dataclasses.replace(
            self.scope, principal='foreign-principal'))
        self.retain('selected', receiver=foreign)
        self.mark('selected')
        self.mark('other')
        expected = self.receiver.inspect_reservation('selected')
        first = self.history('selected', limit=1)
        old_id = first.entries[0].event.event_id
        new_id = expected.current_status.event.event_id
        self.assertEqual(len(first.entries), 1)
        self.assertEqual(first.next_after_event_id, old_id)
        self.assertGreater(new_id, old_id + 1)
        second = self.history('selected', after_event_id=old_id, limit=1)
        self.assertEqual(second.entries, (expected.current_status,))
        self.assertIsNone(second.next_after_event_id)  # exactly limit, no extra row
        self.assertEqual(first.snapshot, second.snapshot)
        for limit in (2, 100):
            page = self.history('selected', limit=limit)
            self.assertEqual(page.entries, first.entries + second.entries)
            self.assertIsNone(page.next_after_event_id)
        gap = self.history('selected', after_event_id=old_id + 1, limit=1)
        self.assertEqual(gap, second)
        for seek in (new_id, MAX_INT):
            page = self.history('selected', after_event_id=seek, limit=1)
            self.assertEqual(page.snapshot, expected)
            self.assertEqual(page.entries, ())
            self.assertIsNone(page.next_after_event_id)
        before = self.state()
        self.assertEqual(self.history('selected', limit=1), first)
        self.assertEqual(self.state(), before)  # cursors do not consume
        self.receiver.acknowledge_status_event(old_id, expected_ack_revision=0, now=LATER)
        self.assertEqual(self.history('selected', after_event_id=old_id, limit=1), second)
        restarted = self.history('selected', limit=1)
        self.assertEqual(restarted.entries[0].ack_revision, 1)
        self.assertEqual(first.entries[0].ack_revision, 0)  # independent snapshots
        self.assertTrue(all(e.event.request_id == 'selected' and
                            e.event.principal == self.scope.principal
                            for e in self.history('selected').entries))

    def test_h03_malformed_exact_types_and_bounds_before_any_transaction(self):
        class IntSubclass(int):
            pass

        class StrSubclass(str):
            pass

        invalid = []
        for rid in (None, 1, True, b'a', StrSubclass('a')):
            invalid.append((rid, {}, TypeError))
        for rid in ('',):
            invalid.append((rid, {}, TypeError))
        for rid in ('a\x00b', '\ud800', 'a' * 1025, 'é' * 513):
            invalid.append((rid, {}, ValueError))
        for seek in (None, False, True, 0.0, '0', IntSubclass(0), -1, MAX_INT + 1):
            invalid.append(('a', {'after_event_id': seek}, dh.ReceiptRevisionError))
        for limit in (None, False, True, 1.0, '1', IntSubclass(1), 0, -1, 101, MAX_INT):
            invalid.append(('a', {'limit': limit}, ValueError))
        before, files = self.state(), self.files()
        with mock.patch.object(self.receiver, '_transaction',
                               side_effect=AssertionError('validation must precede read')) as tx:
            for rid, kwargs, error in invalid:
                with self.subTest(rid=repr(rid), kwargs=kwargs):
                    with self.assertRaises(error):
                        self.history(rid, **kwargs)
            tx.assert_not_called()
        for rid in ('a' * 1024, 'é' * 512):
            with mock.patch.object(self.receiver, '_transaction',
                                   wraps=self.receiver._transaction) as tx:
                self.assertIsNone(self.history(rid, after_event_id=MAX_INT, limit=100))
                tx.assert_called_once_with(write=False)
        self.assertEqual((self.state(), self.files()), (before, files))

    def test_h04_real_missing_receipt_only_end_and_legacy_missing_current(self):
        self.retain('only', receipt_only=True)
        self.mark('only')  # must not invent a reservation or history
        self.retain('legacy')
        old = self.history('legacy').entries[0]
        self.mark('legacy')
        self.retain('no-events')
        # Fixture-only legacy emulation outside the trusted API; deletion is
        # normally forbidden. No repair/backfill is part of the read seam.
        self.sql('DROP TRIGGER reservation_status_no_delete')
        self.sql('DELETE FROM reservation_status_events WHERE '
                 '(request_id=? AND receipt_revision=2) OR request_id=?',
                 ('legacy', 'no-events'))
        before, files = self.state(), self.files()
        self.assertIsNone(self.history('missing'))
        self.assertIsNone(self.history('only'))
        legacy = self.history('legacy')
        self.assertEqual(legacy.snapshot.receipt.revision, 2)
        self.assertIsNone(legacy.snapshot.current_status)
        self.assertEqual(legacy.entries, (old,))
        self.assertIsNone(legacy.next_after_event_id)
        end = self.history('legacy', after_event_id=old.event.event_id)
        self.assertEqual(end.snapshot, legacy.snapshot)
        self.assertEqual(end.entries, ())
        self.assertIsNone(end.next_after_event_id)
        no_events = self.history('no-events')
        self.assertIsNotNone(no_events.snapshot)
        self.assertIsNone(no_events.snapshot.current_status)
        self.assertEqual(no_events.entries, ())
        self.assertIsNone(no_events.next_after_event_id)
        for page in (legacy, end, no_events):
            self.assertEqual(page.snapshot.accounting, dh.ReservationAccounting(20, 20))
        self.assertEqual((self.state(), self.files()), (before, files))

    def test_h05_historic_binding_and_ack_corruption_fail_whole_read_unchanged(self):
        self.retain('selected')
        old = self.history('selected').entries[0].event
        self.mark('selected')
        current = self.receiver.inspect_reservation('selected').current_status
        self.sql('DROP TRIGGER reservation_status_no_update')
        # Place the old fact after the valid current fact to exercise a valid
        # first entry followed by a corrupt historic entry, with no partial view.
        historic_id = current.event.event_id + 1
        self.sql('UPDATE reservation_status_events SET event_id=? WHERE event_id=?',
                 (historic_id, old.event_id))
        columns = ('sender', 'budget_reservation_ref', 'request_sha256',
                   'worker_seconds', 'receipt_revision', 'status')
        restore = tuple(getattr(old, name) for name in columns)
        cases = (
            ('sender', 'foreign-sender', dh.ReceiptScopeError),
            ('budget_reservation_ref', 'foreign-ref', dh.ReceiptConflict),
            ('request_sha256', 'f' * 64, dh.ReceiptConflict),
            ('worker_seconds', 19, dh.ReceiptConflict),
            ('worker_seconds', 'malformed', dh.ReceiptConflict),
            ('receipt_revision', 0, dh.ReceiptConflict),
            ('receipt_revision', 3, dh.ReceiptConflict),
            ('receipt_revision', 1.5, dh.ReceiptConflict),
            ('status', 'reconciliation_required', dh.ReceiptConflict),
        )
        for column, value, error in cases:
            with self.subTest(column=column, value=value):
                with closing(sqlite3.connect(self.path)) as conn, conn:
                    conn.execute('PRAGMA ignore_check_constraints=ON')
                    conn.execute('UPDATE reservation_status_events SET ' + column +
                                 '=? WHERE event_id=?', (value, historic_id))
                before, files = self.state(), self.files()
                with mock.patch.object(self.receiver, '_status_entry',
                                       wraps=self.receiver._status_entry) as decode:
                    with self.assertRaises(error) as caught:
                        self.history('selected')
                    self.assertGreaterEqual(decode.call_count, 3)
                self.assertIn(str(caught.exception), (
                    'retained local status mapping differs',
                    'retained status reservation binding differs'))
                self.assertEqual((self.state(), self.files()), (before, files))
                self.sql('UPDATE reservation_status_events SET ' +
                         ', '.join(name + '=?' for name in columns) + ' WHERE event_id=?',
                         (*restore, historic_id))
        for revision, stamp in ((0, '2026-11-17T12:00:02.000000Z'),
                                (2, '2026-11-17T12:00:02.000000Z'),
                                (1, ''), (1, '2026-11-17T11:59:59.000000Z')):
            with self.subTest(ack_revision=revision, stamp=stamp):
                with closing(sqlite3.connect(self.path)) as conn, conn:
                    conn.execute('PRAGMA ignore_check_constraints=ON')
                    conn.execute('INSERT INTO reservation_status_acks VALUES (?,?,?)',
                                 (historic_id, revision, stamp))
                before, files = self.state(), self.files()
                with self.assertRaises(dh.ReceiptConflict) as caught:
                    self.history('selected')
                self.assertEqual(str(caught.exception),
                                 'retained local status acknowledgement differs')
                self.assertEqual((self.state(), self.files()), (before, files))
                self.sql('DELETE FROM reservation_status_acks WHERE event_id=?', (historic_id,))
        # A syntactically valid revision/status pair newer than its receipt is
        # still invalid. The existing current snapshot sees no revision-1 event.
        self.retain('future')
        self.sql('UPDATE reservation_status_events SET receipt_revision=2, '
                 "status='reconciliation_required' WHERE request_id=?", ('future',))
        before = self.state()
        with self.assertRaises(dh.ReceiptConflict):
            self.history('future')
        self.assertEqual(self.state(), before)

    def test_h06_one_real_wal_snapshot_concurrent_commit_errors_no_constructor_retry(self):
        self.retain('selected')
        original = self.history('selected')
        peer = dh.DurableHandoffReceipts(self.path, scope=self.scope)
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute('PRAGMA journal_mode=WAL').fetchone(), ('wal',))
        actual_connect = sqlite3.connect
        actual_rows = self.receiver._status_rows
        reader_thread = threading.get_ident()
        statements, connections, writer_failures = [], [], []

        def connect(*args, **kwargs):
            connection = actual_connect(*args, **kwargs)
            if threading.get_ident() == reader_thread:
                connections.append(connection)
                connection.set_trace_callback(statements.append)
            return connection

        def writer():
            try:
                self.mark('selected', receiver=peer)
                peer.acknowledge_status_event(original.entries[0].event.event_id,
                                             expected_ack_revision=0, now=LATER)
            except BaseException as exc:
                writer_failures.append(exc)

        def commit_between_reads(connection, **kwargs):
            # The actual reservation/snapshot SELECTs have already fixed the
            # reader's SQLite snapshot. Another connection commits both changes
            # while this read transaction remains open; no fake row injection.
            worker = threading.Thread(target=writer, daemon=True)
            worker.start()
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive(), 'WAL writer must commit during read')
            self.assertEqual(writer_failures, [])
            return actual_rows(connection, **kwargs)

        with mock.patch.object(dh.sqlite3, 'connect', side_effect=connect), \
             mock.patch.object(dh.DurableHandoffReceipts, '__init__',
                               side_effect=AssertionError('no receiver construction')), \
             mock.patch.object(self.receiver, '_transaction',
                               wraps=self.receiver._transaction) as transaction, \
             mock.patch.object(self.receiver, '_reservation_snapshot',
                               wraps=self.receiver._reservation_snapshot) as snapshot, \
             mock.patch.object(self.receiver, '_status_rows',
                               side_effect=commit_between_reads) as rows:
            stable = self.history('selected', limit=1)
            transaction.assert_called_once_with(write=False)
            snapshot.assert_called_once()
            rows.assert_called_once_with(connections[0], request_id='selected',
                                         after_event_id=0, limit=2, pending_only=False)
            self.assertIs(snapshot.call_args.args[0], connections[0])
        self.assertEqual(len(connections), 1)
        self.assertEqual(statements.count('BEGIN'), 1)
        self.assertEqual(statements.count('COMMIT'), 1)
        self.assertFalse(any(s.startswith(('INSERT ', 'UPDATE ', 'DELETE ', 'CREATE '))
                             for s in statements))
        history_sql = [s for s in statements if 'ORDER BY e.event_id ASC LIMIT' in s]
        self.assertEqual(len(history_sql), 1)
        self.assertIn("AND e.request_id='selected'", history_sql[0])
        self.assertIn('LIMIT 2', history_sql[0])
        self.assertEqual(stable, original)  # no new current/old-ack mixed view
        fresh = self.history('selected')
        self.assertEqual(fresh.snapshot.receipt.revision, 2)
        self.assertEqual(tuple(e.ack_revision for e in fresh.entries), (1, 0))
        self.assertEqual(fresh.snapshot.current_status, fresh.entries[-1])
        self.assertEqual(fresh.snapshot.accounting, dh.ReservationAccounting(20, 20))

        before = self.state()
        for error in (dh.ReceiptConflict('injected conflict'),
                      dh.ReceiptScopeError('injected scope'),
                      dh.ReceiptStorageError('injected storage')):
            with self.subTest(error=type(error).__name__):
                with mock.patch.object(self.receiver, '_status_rows', side_effect=error) as rows, \
                     mock.patch.object(self.receiver, '_transaction',
                                       wraps=self.receiver._transaction) as transaction, \
                     mock.patch.object(dh.DurableHandoffReceipts, '__init__',
                                       side_effect=AssertionError('no construction')):
                    with self.assertRaises(type(error)) as caught:
                        self.history('selected')
                    self.assertIs(caught.exception, error)
                    rows.assert_called_once()
                    transaction.assert_called_once_with(write=False)
                self.assertEqual(self.state(), before)
        actual_transaction = self.receiver._transaction
        lost_response = dh.ReceiptStorageError('injected read exit failure')

        @contextmanager
        def fail_after_read(*, write):
            with actual_transaction(write=write) as connection:
                yield connection
            raise lost_response

        with mock.patch.object(self.receiver, '_transaction',
                               side_effect=fail_after_read) as transaction:
            with self.assertRaises(dh.ReceiptStorageError) as caught:
                self.history('selected')
            self.assertIs(caught.exception, lost_response)
            transaction.assert_called_once_with(write=False)
        self.assertEqual(self.state(), before)
        # Real SQL failure must retain the existing storage-error wrapper and
        # cause. The broken fixture is never reconstructed or repaired.
        self.sql('DROP TABLE reservation_status_acks')
        broken = self.state()
        with mock.patch.object(self.receiver, '_transaction',
                               wraps=self.receiver._transaction) as transaction, \
             mock.patch.object(dh.DurableHandoffReceipts, '__init__',
                               side_effect=AssertionError('no construction')):
            with self.assertRaises(dh.ReceiptStorageError) as caught:
                self.history('selected')
            self.assertIsInstance(caught.exception.__cause__, sqlite3.Error)
            transaction.assert_called_once_with(write=False)
        self.assertEqual(self.state(), broken)

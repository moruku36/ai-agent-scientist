"""U01–U06 authored, NOT EXECUTED: exactly six self-contained offline methods.

Real local reservation/blob/SQLite fixtures; no old test imports, threads, model,
network, dispatch or service. Coordinator owns all execution and acceptance.
"""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
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


class LocalUsageObservationContracts(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.root.chmod(0o700)
        (self.root / 'requests').mkdir(mode=0o700)
        (self.root / 'payloads').mkdir(mode=0o700)
        self.requests = BlobStore(self.root / 'requests', max_blob_bytes=8192)
        self.payloads = BlobStore(self.root / 'payloads', max_blob_bytes=128)
        self.raw = b'synthetic usage observation payload\x00\xff'
        payload_digest = self.payloads.put(self.raw)
        self.binding = PayloadBinding('object', payload_digest, 'application/octet-stream',
            'synthetic', 128, True, NOW + timedelta(hours=2))
        self.bindings = {'object': self.binding}
        self.scope = dh.TrustedHandoffScope('independent-local-principal', 'project',
                                            'scientist', 'ctf')
        self.path = str(self.root / 'receiver.sqlite3')
        self.receiver = self.reopen()
        self.authority = dh.WorkerSecondsAuthority(
            dh.WorkerSecondsEnvelope('budget-owner', 'fixed-study', 50, 10, 1, 1, 8, 4),
            True, NOW + timedelta(hours=1))
        self.request = {
            'schema_version': 'harness-handoff/1', 'synthetic': True,
            'message_id': 'delivery-one', 'request_id': 'request-one',
            'attempt_id': None, 'replicate_id': None, 'project_id': 'project',
            'sender': 'scientist', 'recipient': 'ctf', 'kind': 'request',
            'in_reply_to': None, 'expected_revision': 0,
            'authorization_ref': 'authority-one', 'budget_reservation_ref': 'reserve-one',
            'payload': {name: getattr(self.binding, name)
                        for name in ('id', 'sha256', 'media_type', 'classification')},
            'created_at': '2026-11-17T11:00:00Z', 'expires_at': '2026-11-17T13:00:00Z',
        }
        self.digest = self.requests.put(json.dumps(self.request).encode('utf-8'))

    def reopen(self, scope=None):
        return dh.DurableHandoffReceipts(self.path, scope=self.scope if scope is None else scope)

    def reserve(self):
        authorities = {(self.scope.principal, self.scope.project_id, self.scope.sender,
                        self.scope.recipient, 'authority-one', 'reserve-one'): self.authority}
        return self.receiver.reserve(self.requests, self.digest, payload_store=self.payloads,
            bindings=self.bindings, authorities=authorities, now=NOW)

    def observe(self, observation_id='observation-one', *, receiver=None, **changes):
        receiver = self.receiver if receiver is None else receiver
        values = dict(request_id='request-one', budget_reservation_ref='reserve-one',
            request_sha256=self.digest, expected_revision=1, worker_seconds=7,
            execution_stopped=True, cleanup_known=True, observed_at=NOW + timedelta(seconds=1))
        values.update(changes)
        return receiver.record_usage_observation(observation_id, **values)

    def snapshot(self):
        with closing(sqlite3.connect(self.path)) as conn:
            return tuple(conn.execute('SELECT * FROM ' + table + ' ORDER BY 1').fetchall()
                         for table in TABLES)

    def sql(self, statement):
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute(statement)

    def test_u01_real_reservation_observation_reopen_and_bounded_scoped_order(self):
        with mock.patch.object(dh, 'load_bound_handoff_request',
                               wraps=dh.load_bound_handoff_request) as loader:
            reserved = self.reserve()
        loader.assert_called_once_with(self.requests, self.digest, payload_store=self.payloads,
                                       bindings=self.bindings, now=NOW)
        accounting = self.snapshot()[1:3]
        first = self.observe()
        self.assertIs(type(first), dh.LocalUsageObservation)
        self.assertEqual((first.observation_id, first.principal, first.project_id, first.recipient,
                          first.request_id, first.sender, first.budget_reservation_ref,
                          first.request_sha256, first.expected_revision),
                         ('observation-one', self.scope.principal, 'project', 'ctf', 'request-one',
                          'scientist', reserved.reservation.budget_reservation_ref, self.digest, 1))
        self.assertEqual((first.worker_seconds, first.execution_stopped, first.cleanup_known,
                          first.over_cap, first.observed_at),
                         (7, True, True, False, '2026-11-17T12:00:01.000000Z'))
        reopened = self.reopen()
        current = reopened.inspect('request-one')
        self.assertEqual((current.revision, current.state, current.updated_at),
                         (2, 'reconciliation_required', first.observed_at))
        self.assertEqual(reopened.inspect_usage_observations(), (first,))
        events = reopened.inspect_status_events(pending_only=False)
        self.assertEqual(tuple(item.event.status for item in events),
                         ('reservation_retained', 'reconciliation_required'))
        second = self.observe('observation-two', receiver=reopened, expected_revision=2,
                              worker_seconds=9, observed_at=NOW + timedelta(seconds=2))
        self.assertGreater(second.sequence, first.sequence)
        self.assertEqual(reopened.inspect_usage_observations(limit=1), (first,))
        self.assertEqual(reopened.inspect_usage_observations(after_sequence=first.sequence, limit=1),
                         (second,))
        self.assertEqual(reopened.inspect_usage_observations(after_sequence=second.sequence), ())
        self.assertEqual(self.reopen(replace(self.scope, principal='elsewhere'))
                         .inspect_usage_observations(), ())
        self.assertEqual(reopened.inspect('request-one'), current)
        self.assertEqual(reopened.inspect_status_events(pending_only=False), events)
        self.assertEqual(self.snapshot()[1:3], accounting)
        self.assertNotIn(self.raw, Path(self.path).read_bytes())
        with self.assertRaises(ValueError):
            reopened.inspect_usage_observations(limit=101)
        with self.assertRaises(ValueError):
            reopened.inspect_usage_observations(limit=True)
        with self.assertRaises(dh.ReceiptRevisionError):
            reopened.inspect_usage_observations(after_sequence=-1)

    def test_u02_exact_replay_after_revision_advance_conflict_and_immutability(self):
        self.reserve()
        first = self.observe()
        self.assertEqual(self.receiver.inspect('request-one').revision, 2)
        before = self.snapshot()
        self.assertEqual(self.observe(receiver=self.reopen()), first)
        self.assertEqual(self.snapshot(), before)
        with self.assertRaises(dh.ReceiptConflict):
            self.observe(worker_seconds=8)
        with self.assertRaises(dh.ReceiptConflict):
            self.observe(observed_at=NOW + timedelta(seconds=2))
        with self.assertRaises(dh.ReceiptConflict):
            self.observe(expected_revision=2)
        with self.assertRaises(dh.ReceiptConflict):
            self.observe(cleanup_known=False)
        with self.assertRaises(dh.ReceiptConflict):
            self.observe(execution_stopped=False)
        with self.assertRaises(sqlite3.IntegrityError):
            self.sql('UPDATE local_usage_observations SET worker_seconds=0')
        with self.assertRaises(sqlite3.IntegrityError):
            self.sql('DELETE FROM local_usage_observations')
        self.assertEqual(self.snapshot(), before)

    def test_u03_unknown_cleanup_or_usage_and_known_zero_keep_full_reservation(self):
        reserved = self.reserve()
        accounting = self.snapshot()[1:3]
        uncertain_cleanup = self.observe(cleanup_known=False)
        self.assertEqual((uncertain_cleanup.worker_seconds, uncertain_cleanup.cleanup_known), (7, False))
        unknown_usage = self.observe('unknown-usage', expected_revision=2, worker_seconds=None,
                                     execution_stopped=False, cleanup_known=False)
        self.assertIsNone(unknown_usage.worker_seconds)
        self.assertIsNone(unknown_usage.over_cap)
        self.assertFalse(unknown_usage.execution_stopped)
        known_zero = self.observe('known-zero', expected_revision=2, worker_seconds=0)
        self.assertEqual((known_zero.worker_seconds, known_zero.execution_stopped,
                          known_zero.cleanup_known, known_zero.over_cap), (0, True, True, False))
        self.assertEqual(self.snapshot()[1:3], accounting)
        self.assertEqual((reserved.reservation.worker_seconds, accounting[0][0][4],
                          accounting[0][0][-1]), (20, 10, 20))
        self.assertEqual(len(self.receiver.inspect_status_events()), 2)
        self.assertEqual(self.receiver.inspect('request-one').state, 'reconciliation_required')

    def test_u04_wrong_binding_scope_stale_revision_and_invalid_domains_fail_closed(self):
        self.reserve()
        before = self.snapshot()
        with self.assertRaises(dh.ReceiptConflict):
            self.observe(request_sha256='0' * 64)
        with self.assertRaises(dh.ReceiptConflict):
            self.observe(request_id='another-request')
        with self.assertRaises(dh.ReceiptConflict):
            self.observe(budget_reservation_ref='another-reservation')
        with self.assertRaises(dh.ReceiptScopeError):
            self.observe(receiver=self.reopen(replace(self.scope, principal='elsewhere')))
        with self.assertRaises(dh.ReceiptScopeError):
            self.observe(receiver=self.reopen(replace(self.scope, project_id='elsewhere')))
        with self.assertRaises(dh.ReceiptScopeError):
            self.observe(receiver=self.reopen(replace(self.scope, recipient='sleep')))
        with self.assertRaises(dh.ReceiptScopeError):
            self.observe(receiver=self.reopen(replace(self.scope, sender='sleep')))
        with self.assertRaises(dh.ReceiptRevisionError):
            self.observe(expected_revision=0)
        with self.assertRaises(dh.ReceiptRevisionError):
            self.observe(expected_revision=True)
        with self.assertRaises(ValueError):
            self.observe(worker_seconds=-1)
        with self.assertRaises(ValueError):
            self.observe(worker_seconds=True)
        with self.assertRaises(ValueError):
            self.observe(worker_seconds=1 << 63)
        with self.assertRaises(TypeError):
            self.observe(cleanup_known=1)
        with self.assertRaises(TypeError):
            self.observe(execution_stopped=1)
        with self.assertRaises(ValueError):
            self.observe('x' * 1025)
        with self.assertRaises(TypeError):
            self.observe(observed_at=NOW.replace(tzinfo=None))
        with self.assertRaises(ValueError):
            self.observe(observed_at=NOW - timedelta(seconds=1))
        self.assertEqual(self.snapshot(), before)
        self.receiver.require_reconciliation('request-one', expected_revision=1, now=NOW)
        reconciled = self.snapshot()
        with self.assertRaises(dh.ReceiptRevisionError):
            self.observe('new-stale-observation', expected_revision=1)
        self.assertEqual(self.snapshot(), reconciled)
        self.assertEqual(self.receiver.inspect_usage_observations(), ())

    def test_u05_two_contenders_use_separate_connections_and_one_transition(self):
        self.reserve()
        contender = self.reopen()
        self.assertEqual(self.receiver.inspect('request-one').revision,
                         contender.inspect('request-one').revision)
        actual_connect = sqlite3.connect
        connections = []
        append = self.receiver._append_status_event

        def connect(*args, **kwargs):
            conn = actual_connect(*args, **kwargs)
            connections.append(conn)
            return conn

        def append_then_contend(conn, receipt, reservation, stamp):
            event = append(conn, receipt, reservation, stamp)
            # Winner still holds BEGIN IMMEDIATE. A real second connection must
            # time out without observing uncommitted revision/event or writing.
            with self.assertRaises(dh.ReceiptStorageError):
                self.observe('contender', receiver=contender)
            return event

        with mock.patch.object(dh.sqlite3, 'connect', side_effect=connect), \
                mock.patch.object(self.receiver, '_append_status_event', side_effect=append_then_contend):
            winner = self.observe('winner')
        self.assertEqual(len(connections), 2)
        self.assertIsNot(connections[0], connections[1])
        before = self.snapshot()
        with self.assertRaises(dh.ReceiptRevisionError):
            self.observe('contender', receiver=contender)
        self.assertEqual(self.observe('winner', receiver=contender), winner)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(contender.inspect_usage_observations(), (winner,))
        self.assertEqual(len(contender.inspect_status_events()), 2)
        self.assertEqual(contender.inspect('request-one').revision, 2)
        self.assertEqual(before[1][0][-1], 20)

    def test_u06_over_cap_unmodified_and_event_or_observation_failure_rolls_back(self):
        self.reserve()
        before = self.snapshot()
        self.sql("CREATE TRIGGER fail_usage_event AFTER INSERT ON reservation_status_events "
                 "WHEN NEW.receipt_revision=2 BEGIN SELECT RAISE(FAIL, 'synthetic event failure'); END")
        with self.assertRaises(dh.ReceiptStorageError):
            self.observe(worker_seconds=(1 << 63) - 1)
        self.assertEqual(self.snapshot(), before)
        self.sql('DROP TRIGGER fail_usage_event')
        self.sql("CREATE TRIGGER fail_usage_insert AFTER INSERT ON local_usage_observations "
                 "BEGIN SELECT RAISE(FAIL, 'synthetic late observation failure'); END")
        with self.assertRaises(dh.ReceiptStorageError):
            self.observe(worker_seconds=(1 << 63) - 1)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.reopen().inspect('request-one').revision, 1)
        self.sql('DROP TRIGGER fail_usage_insert')
        observation = self.observe(worker_seconds=(1 << 63) - 1)
        self.assertEqual(observation.worker_seconds, (1 << 63) - 1)
        self.assertIs(observation.over_cap, True)
        self.assertEqual(self.reopen().inspect_usage_observations(), (observation,))
        after = self.snapshot()
        self.assertEqual(after[1:3], before[1:3])
        self.assertEqual((len(after[3]), len(after[5])), (2, 1))
        self.assertEqual(self.receiver.inspect_status_events()[-1].event.worker_seconds, 20)

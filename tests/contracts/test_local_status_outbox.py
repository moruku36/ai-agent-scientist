"""O01–O06 authored, NOT EXECUTED: six self-contained offline scenarios.

Real bounded blob reads and temporary SQLite only. No historical test imports,
transport, sender, service, dispatch or research. This file was not imported/run.
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
          'reservation_status_acks')


class LocalStatusOutboxContracts(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.root.chmod(0o700)
        for name in ('requests', 'payloads'):
            (self.root / name).mkdir(mode=0o700)
        self.requests = BlobStore(self.root / 'requests', max_blob_bytes=8192)
        self.payloads = BlobStore(self.root / 'payloads', max_blob_bytes=128)
        self.raw = b'synthetic outbox payload\x00\xff'
        digest = self.payloads.put(self.raw)
        self.binding = PayloadBinding('object', digest, 'application/octet-stream',
            'synthetic', 128, True, NOW + timedelta(hours=2))
        self.bindings = {'object': self.binding}
        self.scope = dh.TrustedHandoffScope('independent-local-principal', 'project',
                                            'scientist', 'ctf')
        self.path = str(self.root / 'receiver.sqlite3')
        self.receiver = self.reopen()
        self.authority = dh.WorkerSecondsAuthority(
            dh.WorkerSecondsEnvelope('budget-owner', 'fixed-study', 100, 10, 1, 1, 8, 4),
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
        self.digest = self.put(self.request)

    def reopen(self, scope=None):
        return dh.DurableHandoffReceipts(self.path, scope=self.scope if scope is None else scope)

    def put(self, request):
        return self.requests.put(json.dumps(request).encode('utf-8'))

    def next_request(self, number, scope=None):
        scope = self.scope if scope is None else scope
        return dict(self.request, request_id='request-' + str(number),
                    message_id='delivery-' + str(number), budget_reservation_ref='reserve-' + str(number),
                    project_id=scope.project_id, sender=scope.sender, recipient=scope.recipient)

    def reserve(self, request=None, *, receiver=None, now=NOW):
        request = self.request if request is None else request
        receiver = self.receiver if receiver is None else receiver
        scope = receiver._scope
        authorities = {(scope.principal, scope.project_id, scope.sender, scope.recipient,
                        request['authorization_ref'], request['budget_reservation_ref']): self.authority}
        return receiver.reserve(self.requests, self.put(request), payload_store=self.payloads,
                                bindings=self.bindings, authorities=authorities, now=now)

    def snapshot(self):
        with closing(sqlite3.connect(self.path)) as conn:
            return tuple(conn.execute('SELECT * FROM ' + table + ' ORDER BY 1').fetchall()
                         for table in TABLES)

    def sql(self, statement):
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute(statement)

    def test_o01_real_loader_receipt_reservation_one_matching_event(self):
        with mock.patch.object(dh, 'load_bound_handoff_request',
                               wraps=dh.load_bound_handoff_request) as loader, \
                mock.patch.object(self.requests, 'get', wraps=self.requests.get) as envelopes, \
                mock.patch.object(self.payloads, 'get', wraps=self.payloads.get) as payloads:
            result = self.reserve()
        loader.assert_called_once_with(self.requests, self.digest, payload_store=self.payloads,
                                       bindings=self.bindings, now=NOW)
        envelopes.assert_called_once_with(self.digest)
        payloads.assert_called_once_with(self.binding.sha256)
        entries = self.receiver.inspect_status_events()
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        event = entry.event
        self.assertEqual((entry.ack_revision, entry.acknowledged_at), (0, None))
        self.assertEqual((event.principal, event.project_id, event.recipient, event.request_id,
                          event.sender, event.request_sha256, event.receipt_revision),
                         (result.receipt.principal, result.receipt.project_id, result.receipt.recipient,
                          result.receipt.request_id, result.receipt.sender,
                          result.receipt.request_sha256, result.receipt.revision))
        self.assertEqual(event.budget_reservation_ref, result.reservation.budget_reservation_ref)
        self.assertEqual((event.status, event.worker_seconds, event.created_at),
                         ('reservation_retained', 20, result.reservation.recorded_at))
        self.assertEqual(self.receiver.inspect('request-one'), result.receipt)
        self.assertEqual(self.snapshot()[1][0][-1], 20)
        self.assertNotIn(self.raw, Path(self.path).read_bytes())
        self.assertFalse(hasattr(event, 'admitted'))
        self.assertFalse(hasattr(event, 'delivered'))

    def test_o02_replay_and_reopen_preserve_event_identity_without_duplicate(self):
        first = self.reserve()
        events = self.receiver.inspect_status_events()
        before = self.snapshot()
        reopened = self.reopen()
        with mock.patch.object(self.payloads, 'get', wraps=self.payloads.get) as payloads:
            replay = self.reserve(receiver=reopened, now=NOW + timedelta(seconds=2))
        payloads.assert_called_once_with(self.binding.sha256)
        self.assertEqual(replay, first)
        self.assertEqual(reopened.inspect_status_events(), events)
        self.assertEqual(self.snapshot(), before)
        # Receipt-only replay also cannot create another reservation or event.
        self.assertEqual(reopened.record(self.requests, self.digest, payload_store=self.payloads,
            bindings=self.bindings, now=NOW + timedelta(seconds=3)), first.receipt)
        self.assertEqual(self.snapshot(), before)

    def test_o03_injected_event_write_failure_rolls_back_the_entire_transaction(self):
        failure = ("CREATE TRIGGER injected_status_failure AFTER INSERT ON reservation_status_events "
                   "BEGIN SELECT RAISE(FAIL, 'synthetic event write failure'); END")
        self.sql(failure)
        with self.assertRaises(dh.ReceiptStorageError):
            self.reserve()
        self.assertEqual(self.snapshot(), ([], [], [], [], []))
        self.assertIsNone(self.reopen().inspect('request-one'))
        self.sql('DROP TRIGGER injected_status_failure')
        self.reserve()
        before = self.snapshot()
        self.sql(failure)
        with self.assertRaises(dh.ReceiptStorageError):
            self.reserve(self.next_request(2))
        self.assertEqual(self.snapshot(), before)
        self.assertIsNone(self.reopen().inspect('request-2'))
        self.assertEqual(len(self.receiver.inspect_status_events()), 1)

    def test_o04_reconciliation_cas_next_event_stale_no_orphan_or_invented_reservation(self):
        first = self.reserve()
        initial = self.receiver.inspect_status_events()[0].event
        before = self.snapshot()
        self.sql("CREATE TRIGGER fail_reconciliation_event AFTER INSERT ON reservation_status_events "
                 "WHEN NEW.receipt_revision=2 BEGIN SELECT RAISE(FAIL, 'synthetic failure'); END")
        with self.assertRaises(dh.ReceiptStorageError):
            self.receiver.require_reconciliation('request-one', expected_revision=1,
                                                  now=NOW + timedelta(seconds=1))
        self.assertEqual(self.snapshot(), before)
        self.sql('DROP TRIGGER fail_reconciliation_event')
        current = self.receiver.require_reconciliation('request-one', expected_revision=1,
                                                        now=NOW + timedelta(seconds=1))
        events = self.receiver.inspect_status_events()
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].event, initial)
        next_event = events[1].event
        self.assertGreater(next_event.event_id, initial.event_id)
        self.assertEqual((next_event.receipt_revision, next_event.status, next_event.created_at),
                         (2, 'reconciliation_required', current.updated_at))
        self.assertEqual(next_event.budget_reservation_ref, first.reservation.budget_reservation_ref)
        self.assertEqual(next_event.request_sha256, first.receipt.request_sha256)
        self.assertEqual(next_event.worker_seconds, first.reservation.worker_seconds)
        retained = self.snapshot()
        self.assertEqual(retained[1:3], before[1:3])
        for revision, error in ((1, dh.ReceiptRevisionError), (2, dh.InvalidReceiptTransition)):
            with self.assertRaises(error):
                self.receiver.require_reconciliation('request-one', expected_revision=revision,
                                                      now=NOW + timedelta(seconds=2))
            self.assertEqual(self.snapshot(), retained)
        self.assertEqual(self.reserve(now=NOW + timedelta(seconds=3)).receipt, current)
        self.assertEqual(self.snapshot(), retained)
        receipt_only = self.next_request(3)
        receipt = self.receiver.record(self.requests, self.put(receipt_only),
            payload_store=self.payloads, bindings=self.bindings, now=NOW)
        self.receiver.require_reconciliation(receipt.request_id, expected_revision=1, now=NOW)
        after = self.snapshot()
        self.assertEqual(after[1:], retained[1:])
        self.assertEqual(len(after[0]), 2)

    def test_o05_bounded_ordered_inspection_and_scoped_ack_cas_without_regression(self):
        self.reserve()
        current = self.receiver.require_reconciliation('request-one', expected_revision=1, now=NOW)
        foreign_scope = replace(self.scope, principal='other-principal', project_id='other-project',
                                sender='ctf', recipient='sleep')
        foreign = self.reopen(foreign_scope)
        self.reserve(self.next_request(2, foreign_scope), receiver=foreign)
        one, two = self.receiver.inspect_status_events()
        foreign_event = foreign.inspect_status_events()[0].event
        self.assertEqual(self.receiver.inspect_status_events(limit=1), (one,))
        self.assertEqual(self.receiver.inspect_status_events(after_event_id=one.event.event_id,
                                                             limit=1), (two,))
        self.assertEqual(self.receiver.inspect_status_events(after_event_id=two.event.event_id), ())
        before = self.snapshot()
        # Different principal/project/recipient and changed sender mapping confer no ack right.
        for scope in (replace(self.scope, principal='elsewhere'),
                      replace(self.scope, project_id='elsewhere'),
                      replace(self.scope, recipient='sleep')):
            with self.assertRaises(dh.ReceiptRevisionError):
                self.reopen(scope).acknowledge_status_event(one.event.event_id,
                    expected_ack_revision=0, now=NOW)
        with self.assertRaises(dh.ReceiptScopeError):
            self.reopen(replace(self.scope, sender='sleep')).acknowledge_status_event(
                one.event.event_id, expected_ack_revision=0, now=NOW)
        with self.assertRaises(dh.ReceiptRevisionError):
            self.receiver.acknowledge_status_event(foreign_event.event_id,
                                                   expected_ack_revision=0, now=NOW)
        self.assertEqual(self.snapshot(), before)
        # Ack the newer fact first, then the older one: canonical status never regresses.
        ack = self.receiver.acknowledge_status_event(two.event.event_id,
                                                    expected_ack_revision=0, now=NOW)
        self.assertEqual((ack.event, ack.ack_revision), (two.event, 1))
        self.assertEqual(self.receiver.inspect_status_events(), (one,))
        acknowledged = self.snapshot()
        for revision in (0, 1, True):
            with self.assertRaises(dh.ReceiptRevisionError):
                self.receiver.acknowledge_status_event(two.event.event_id,
                                                       expected_ack_revision=revision, now=NOW)
            self.assertEqual(self.snapshot(), acknowledged)
        self.receiver.acknowledge_status_event(one.event.event_id, expected_ack_revision=0, now=NOW)
        self.assertEqual(self.receiver.inspect('request-one'), current)
        self.assertEqual(self.snapshot()[1:3], before[1:3])
        self.assertEqual(self.receiver.inspect_status_events(), ())
        self.assertEqual(tuple(item.event for item in
            self.receiver.inspect_status_events(pending_only=False)), (one.event, two.event))
        self.assertEqual(foreign.inspect_status_events()[0].event, foreign_event)
        for options, error in (({'limit': 0}, ValueError), ({'limit': 101}, ValueError),
                               ({'limit': True}, ValueError), ({'after_event_id': -1}, dh.ReceiptRevisionError),
                               ({'after_event_id': True}, dh.ReceiptRevisionError),
                               ({'after_event_id': 1 << 63}, dh.ReceiptRevisionError),
                               ({'pending_only': 1}, TypeError)):
            with self.assertRaises(error):
                self.receiver.inspect_status_events(**options)
        immutable = self.snapshot()
        for statement in ("UPDATE reservation_status_events SET status='reservation_retained'",
                          'DELETE FROM reservation_status_events'):
            with self.assertRaises(sqlite3.IntegrityError):
                self.sql(statement)
        self.assertEqual(self.snapshot(), immutable)

    def test_o06_lost_ack_reopen_retains_reservation_and_pending_until_local_ack(self):
        actual_connect = sqlite3.connect

        class LostCommitResponse(sqlite3.Connection):
            def commit(self):
                super().commit()
                raise sqlite3.OperationalError('synthetic response lost after commit')

        def connect(*args, **kwargs):
            return actual_connect(*args, **kwargs, factory=LostCommitResponse)

        with mock.patch.object(dh.sqlite3, 'connect', side_effect=connect):
            with self.assertRaises(dh.ReceiptStorageError):
                self.reserve()
        reopened = self.reopen()
        pending = reopened.inspect_status_events()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].ack_revision, 0)
        before = self.snapshot()
        self.assertEqual((len(before[0]), len(before[2]), before[1][0][-1]), (1, 1, 20))
        self.reserve(receiver=reopened)
        self.assertEqual(self.snapshot(), before)
        self.sql("CREATE TRIGGER fail_local_ack AFTER INSERT ON reservation_status_acks "
                 "BEGIN SELECT RAISE(FAIL, 'synthetic ack failure'); END")
        event_id = pending[0].event.event_id
        with self.assertRaises(dh.ReceiptStorageError):
            reopened.acknowledge_status_event(event_id, expected_ack_revision=0, now=NOW)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.reopen().inspect_status_events(), pending)
        self.sql('DROP TRIGGER fail_local_ack')
        # If the local ack itself committed before its response was lost, inspect
        # the separate ack record; neither outcome can release the reservation.
        with mock.patch.object(dh.sqlite3, 'connect', side_effect=connect):
            with self.assertRaises(dh.ReceiptStorageError):
                reopened.acknowledge_status_event(event_id, expected_ack_revision=0, now=NOW)
        reopened = self.reopen()
        self.assertEqual(reopened.inspect_status_events(), ())
        self.assertEqual(reopened.inspect_status_events(pending_only=False)[0].ack_revision, 1)
        self.assertEqual(self.snapshot()[:4], before[:4])
        self.assertEqual(self.reserve(receiver=reopened).reservation.worker_seconds, 20)
        self.assertEqual(reopened.inspect_status_events(), ())

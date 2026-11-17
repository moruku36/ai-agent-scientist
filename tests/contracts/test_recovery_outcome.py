"""Q01-Q06: exactly six self-contained private SQLite/blob methods.

Scientist25, authored NOT EXECUTED. Fixture code is copied locally; no historic
test class, operational database, credentials or external service is used.
"""
import dataclasses
import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import ExitStack, closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ai_agent_scientist.admission import durable_handoff as dh
from ai_agent_scientist.admission import recovery_ack as ack
from ai_agent_scientist.admission import recovery_apply as apply
from ai_agent_scientist.admission import recovery_outcome as outcome
from ai_agent_scientist.admission import recovery_preview as preview
from ai_agent_scientist.admission import recovery_triage as triage
from ai_agent_scientist.admission.handoff_binding import PayloadBinding
from ai_agent_scientist.evidence.blob_store import BlobStore

NOW = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
LATER = NOW + timedelta(seconds=2)
MAX_INT = (1 << 63) - 1


class RecoveryOutcomeContracts(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.root.chmod(0o700)
        for name in ('requests', 'payloads'):
            (self.root / name).mkdir(mode=0o700)
        self.requests = BlobStore(self.root / 'requests', max_blob_bytes=8192)
        self.payloads = BlobStore(self.root / 'payloads', max_blob_bytes=128)
        digest = self.payloads.put(b'synthetic private outcome payload')
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
        kwargs = dict(payload_store=self.payloads, bindings={'object': self.binding}, now=NOW)
        if receipt_only:
            return self.receiver.record(self.requests, digest, **kwargs)
        authorities = {(s.principal, s.project_id, s.sender, s.recipient,
            'private-authority', ref): dh.WorkerSecondsAuthority(
                self.envelope, True, NOW + timedelta(hours=1))}
        return self.receiver.reserve(self.requests, digest, authorities=authorities, **kwargs)

    def snap(self, rid):
        return self.receiver.inspect_reservation(rid)

    def intent(self, rid):
        return preview.build_reconciliation_preview(self.receiver, rid)

    def selected(self, rid):
        return ack.select_current_recovery_status(self.receiver, rid)

    def ack_arguments(self, selection):
        return dict(request_id=selection.request_id,
                    expected_request_sha256=selection.request_sha256,
                    expected_receipt_revision=selection.receipt_revision,
                    expected_event_id=selection.event_id,
                    expected_ack_revision=selection.ack_revision)

    def state(self):
        with closing(sqlite3.connect(self.path)) as conn:
            return tuple(conn.iterdump())

    def files(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def sql(self, statement, parameters=()):
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute(statement, parameters)

    def assert_full(self, result):
        self.assertEqual(result.snapshot.accounting, dh.ReservationAccounting(20, 20))
        self.assertEqual(result.snapshot.reservation.worker_seconds, 20)

    def test_q01_recorded_then_real_application_commit_followed_by_lost_response(self):
        retained = self.retain('apply')
        self.retain('untouched')
        untouched = self.snap('untouched')
        intent = self.intent('apply')
        before = self.snap('apply')
        result = outcome.inspect_reconciliation_outcome(self.receiver, intent)
        self.assertEqual(result.classification, 'receipt_still_recorded')
        self.assertEqual(result.action, 'mark_reconciliation_required')
        self.assertEqual((result.request_id, result.request_sha256),
                         (intent.request_id, intent.request_sha256))
        self.assertEqual(result.snapshot, before)
        self.assertIsNone(result.target_status)
        self.assertIsNone(result.target_event_is_current)
        real_transaction = self.receiver._transaction
        lost = dh.ReceiptStorageError('synthetic response lost after commit')

        @contextmanager
        def commit_then_lose(*, write):
            with real_transaction(write=write) as conn:
                yield conn
            if write:
                raise lost

        with mock.patch.object(self.receiver, '_transaction', side_effect=commit_then_lose):
            with self.assertRaises(dh.ReceiptStorageError) as error:
                apply.apply_reconciliation_preview(self.receiver, intent, now=LATER)
        self.assertIs(error.exception, lost)
        state, files = self.state(), self.files()
        result = outcome.inspect_reconciliation_outcome(self.receiver, intent)
        self.assertEqual(result.classification, 'reconciliation_transition_observed')
        self.assertEqual((result.snapshot.receipt.revision, result.snapshot.receipt.state),
                         (2, 'reconciliation_required'))
        self.assertEqual(result.snapshot.reservation, retained.reservation)
        self.assertIsNone(result.snapshot.latest_usage_observation)
        self.assert_full(result)
        self.assertEqual(self.snap('untouched'), untouched)
        self.assertEqual((self.state(), self.files()), (state, files))

    def test_q02_real_usage_observation_or_another_caller_has_same_noncausal_transition(self):
        retained = self.retain('observation')
        intent = self.intent('observation')
        # Bytes are opaque here; even valid non-JSON bytes do not grant authority
        # or undergo the full-preview comparison required by the action API.
        opaque = b'opaque non-JSON \xff'
        opaque_intent = dataclasses.replace(intent, data=opaque,
                                            sha256=hashlib.sha256(opaque).hexdigest())
        r = retained.reservation
        with mock.patch.object(apply, 'apply_reconciliation_preview',
                               side_effect=AssertionError('no attempted application')):
            recorded = outcome.inspect_reconciliation_outcome(self.receiver, opaque_intent)
            observation = self.receiver.record_usage_observation(
                'obs-private', request_id=r.request_id,
                budget_reservation_ref=r.budget_reservation_ref,
                request_sha256=r.request_sha256, expected_revision=1,
                worker_seconds=None, execution_stopped=False, cleanup_known=False,
                observed_at=NOW + timedelta(seconds=1))
            state, files = self.state(), self.files()
            result = outcome.inspect_reconciliation_outcome(self.receiver, intent)
        self.assertEqual(recorded.classification, 'receipt_still_recorded')
        self.assertEqual(result.classification, 'reconciliation_transition_observed')
        self.assertEqual(result.snapshot.latest_usage_observation, observation)
        self.assertIsNone(observation.worker_seconds)
        self.assertIsNone(observation.over_cap)
        self.assertFalse(observation.execution_stopped)
        self.assertFalse(observation.cleanup_known)
        self.assertEqual(result.snapshot.receipt.revision, 2)
        self.assert_full(result)
        self.assertEqual((self.state(), self.files()), (state, files))
        self.retain('other-caller')
        other_intent = self.intent('other-caller')
        self.receiver.require_reconciliation('other-caller', expected_revision=1, now=LATER)
        other = outcome.inspect_reconciliation_outcome(self.receiver, other_intent)
        self.assertEqual(other.classification, result.classification)
        self.assertIsNone(other.snapshot.latest_usage_observation)
        self.assert_full(other)

    def test_q03_real_ack_commit_lost_response_and_old_ack_new_pending_race(self):
        self.retain('ack-current')
        selected = self.selected('ack-current')
        pending = outcome.inspect_acknowledgement_outcome(self.receiver, selected)
        self.assertEqual(pending.classification, 'target_ack_pending')
        self.assertIs(pending.target_event_is_current, True)
        real_transaction = self.receiver._transaction
        lost = dh.ReceiptStorageError('synthetic ack response lost after commit')

        @contextmanager
        def commit_then_lose(*, write):
            with real_transaction(write=write) as conn:
                yield conn
            if write:
                raise lost

        with mock.patch.object(self.receiver, '_transaction', side_effect=commit_then_lose):
            with self.assertRaises(dh.ReceiptStorageError) as error:
                ack.acknowledge_current_recovery_status(
                    self.receiver, **self.ack_arguments(selected), now=LATER)
        self.assertIs(error.exception, lost)
        retained = outcome.inspect_acknowledgement_outcome(self.receiver, selected)
        self.assertEqual(retained.classification, 'target_ack_retained')
        self.assertEqual(retained.action, 'acknowledge_status_event')
        self.assertEqual(retained.target_status.event.event_id, selected.event_id)
        self.assertEqual(retained.target_status.ack_revision, 1)
        self.assertIs(retained.target_event_is_current, True)
        self.assert_full(retained)

        self.retain('race')
        old = self.selected('race')
        real_inspect = ack.inspect_recovery_triage

        def advance_after_inspection(receiver, rid):
            report = real_inspect(receiver, rid)
            receiver.require_reconciliation(rid, expected_revision=1,
                                            now=NOW + timedelta(seconds=1))
            return report

        with mock.patch.object(ack, 'inspect_recovery_triage',
                               side_effect=advance_after_inspection) as read:
            old_ack = ack.acknowledge_current_recovery_status(
                self.receiver, **self.ack_arguments(old), now=LATER)
            read.assert_called_once_with(self.receiver, 'race')
        new = self.selected('race')
        state, files = self.state(), self.files()
        historical = outcome.inspect_acknowledgement_outcome(self.receiver, old)
        current = outcome.inspect_acknowledgement_outcome(self.receiver, new)
        self.assertEqual(historical.classification, 'target_ack_retained')
        self.assertEqual(historical.target_status, old_ack)
        self.assertIs(historical.target_event_is_current, False)
        self.assertEqual(current.classification, 'target_ack_pending')
        self.assertIs(current.target_event_is_current, True)
        self.assertEqual(historical.snapshot, current.snapshot)
        self.assertEqual(historical.snapshot.receipt.revision, 2)
        self.assertEqual(historical.snapshot.current_status.ack_revision, 0)
        self.assertNotEqual(old.event_id, new.event_id)
        for result in (historical, current):
            self.assert_full(result)
        self.assertEqual((self.state(), self.files()), (state, files))

    def test_q04_missing_receipt_only_exact_target_digest_and_malformed_intents_pre_read(self):
        self.retain('a')
        intent, selected = self.intent('a'), self.selected('a')
        self.retain('only', receipt_only=True)
        for rid in ('missing', 'only'):
            for inspect, value in ((outcome.inspect_reconciliation_outcome, intent),
                                   (outcome.inspect_acknowledgement_outcome, selected)):
                result = inspect(self.receiver, dataclasses.replace(value, request_id=rid))
                self.assertEqual(result.classification, 'missing_or_receipt_only')
                self.assertIsNone(result.snapshot)
                self.assertIsNone(result.target_status)
                self.assertIsNone(result.target_event_is_current)
        self.retain('interleaved')
        wrong_id = self.selected('interleaved').event_id
        self.receiver.require_reconciliation('a', expected_revision=1, now=LATER)
        new = self.selected('a')
        self.receiver.acknowledge_status_event(new.event_id, expected_ack_revision=0, now=LATER)
        already_acked = self.selected('a')
        self.assertEqual(already_acked.ack_revision, 1)
        state, files = self.state(), self.files()
        for missing in (dataclasses.replace(selected, event_id=wrong_id),
                        dataclasses.replace(selected, event_id=MAX_INT),
                        dataclasses.replace(selected, receipt_revision=2,
                                            event_receipt_revision=2)):
            result = outcome.inspect_acknowledgement_outcome(self.receiver, missing)
            self.assertEqual(result.classification, 'target_event_not_found')
            self.assertIsNone(result.target_status)  # never borrow later ack=1
            self.assertIs(result.target_event_is_current, False)
            self.assert_full(result)
        for inspect, value in ((outcome.inspect_reconciliation_outcome, intent),
                               (outcome.inspect_acknowledgement_outcome, selected)):
            with mock.patch.object(self.receiver, 'inspect_reservation_status_history',
                    wraps=self.receiver.inspect_reservation_status_history) as read:
                with self.assertRaises(outcome.RecoveryOutcomeRefused) as error:
                    inspect(self.receiver, dataclasses.replace(value, request_sha256='0' * 64))
                self.assertEqual(str(error.exception), 'recovery outcome refused')
                self.assertEqual(read.call_count, 1)

        class Text(str):
            pass

        class Number(int):
            pass

        class Bytes(bytes):
            pass

        class PreviewSubclass(preview.ReconciliationPreview):
            pass

        class SelectionSubclass(ack.RecoveryStatusSelection):
            pass

        bad_ids = (None, True, 1, b'a', '', Text('a'), 'x' * 1025,
                   '界' * 342, '\x00private', '\ud800')
        bad_digests = (None, b'0' * 64, True, Text('0' * 64), '0' * 63,
                       '0' * 65, 'A' * 64, 'g' * 64)
        common = {'request_id': bad_ids, 'request_sha256': bad_digests}
        preview_fields = dict(common, data=(None, '', bytearray(b'x'), Bytes(b'x'),
                                            b'', b'x' * 1048577),
                              sha256=(*bad_digests, '0' * 64),
                              expected_revision=(None, True, Number(1), 1.0, '1',
                                                 0, -1, 2, MAX_INT + 1))
        selection_fields = dict(common,
            receipt_revision=(None, True, Number(1), 1.0, '1', 0, -1, 3, MAX_INT + 1),
            event_id=(None, True, Number(1), 1.0, '1', 0, -1, MAX_INT + 1),
            event_receipt_revision=(None, True, Number(1), 1.0, '1', 0, 2, MAX_INT + 1),
            ack_revision=(None, False, Number(0), 0.0, '0', -1, 1, MAX_INT + 1))
        with mock.patch.object(self.receiver, 'inspect_reservation_status_history') as read:
            for inspect, good, fields, subclass in (
                    (outcome.inspect_reconciliation_outcome, intent, preview_fields, PreviewSubclass),
                    (outcome.inspect_acknowledgement_outcome, selected, selection_fields, SelectionSubclass)):
                malformed = [None, object(), SimpleNamespace(**dataclasses.asdict(good)),
                             subclass(*dataclasses.astuple(good))]
                malformed.extend(dataclasses.replace(good, **{field: value})
                                 for field, values in fields.items() for value in values)
                for bad in malformed:
                    with self.subTest(api=inspect.__name__, intent_type=type(bad).__name__):
                        with self.assertRaises(outcome.RecoveryOutcomeRefused) as error:
                            inspect(self.receiver, bad)
                        self.assertEqual(str(error.exception), 'recovery outcome refused')
            # A freshly selected already-acked event is not an unspent intent.
            with self.assertRaises(outcome.RecoveryOutcomeRefused):
                outcome.inspect_acknowledgement_outcome(self.receiver, already_acked)
            read.assert_not_called()
        # Inclusive byte boundaries are accepted without parsing supplied data.
        boundary_id = '界' * 341 + 'x'
        for data in (b'x', b'x' * 1048576):
            valid = dataclasses.replace(intent, request_id=boundary_id, data=data,
                                        sha256=hashlib.sha256(data).hexdigest())
            self.assertEqual(outcome.inspect_reconciliation_outcome(
                self.receiver, valid).classification, 'missing_or_receipt_only')
        self.assertEqual(outcome.inspect_acknowledgement_outcome(self.receiver,
            dataclasses.replace(selected, request_id=boundary_id,
                                event_id=MAX_INT)).classification, 'missing_or_receipt_only')
        self.assertEqual((self.state(), self.files()), (state, files))

    def test_q05_one_actual_history_transaction_correct_seek_no_actions_db_files_unchanged(self):
        self.retain('other')  # make the selected event's exclusive seek nonzero
        self.retain('selected')
        intent, selected = self.intent('selected'), self.selected('selected')
        self.receiver.require_reconciliation('selected', expected_revision=1, now=LATER)
        expected = self.snap('selected')
        state, files = self.state(), self.files()
        real_transaction = self.receiver._transaction
        real_connect = sqlite3.connect
        writes, statements = [], []

        @contextmanager
        def track_transaction(*, write):
            writes.append(write)
            with real_transaction(write=write) as conn:
                yield conn

        def connect(*args, **kwargs):
            conn = real_connect(*args, **kwargs)
            conn.set_trace_callback(statements.append)
            return conn

        with ExitStack() as guards:
            for name in ('inspect', 'inspect_reservation', 'inspect_reservations',
                         'inspect_status_events', 'inspect_usage_observations',
                         'record', 'reserve', 'require_reconciliation',
                         'acknowledge_status_event', 'record_usage_observation'):
                guards.enter_context(mock.patch.object(self.receiver, name,
                    side_effect=AssertionError('no independent read or action')))
            for module, name in ((apply, 'apply_reconciliation_preview'),
                                 (ack, 'acknowledge_current_recovery_status'),
                                 (ack, 'select_current_recovery_status'),
                                 (preview, 'build_reconciliation_preview')):
                guards.enter_context(mock.patch.object(module, name,
                    side_effect=AssertionError('no action or rebuild')))
            guards.enter_context(mock.patch.object(dh.DurableHandoffReceipts, '__init__',
                side_effect=AssertionError('no receiver construction')))
            for inspect, value, seek in ((outcome.inspect_reconciliation_outcome, intent, 0),
                    (outcome.inspect_acknowledgement_outcome, selected, selected.event_id - 1)):
                writes.clear()
                statements.clear()
                with mock.patch.object(self.receiver, 'inspect_reservation_status_history',
                        wraps=self.receiver.inspect_reservation_status_history) as read, \
                     mock.patch.object(self.receiver, '_transaction', side_effect=track_transaction), \
                     mock.patch.object(dh.sqlite3, 'connect', side_effect=connect) as connections, \
                     mock.patch.object(outcome, 'classify_reservation',
                                       wraps=outcome.classify_reservation) as classify:
                    result = inspect(self.receiver, value)
                    read.assert_called_once_with('selected', after_event_id=seek, limit=1)
                    self.assertEqual(connections.call_count, 1)
                    classify.assert_called_once_with(result.snapshot, scope=self.scope)
                    self.assertIs(classify.call_args.args[0], result.snapshot)
                self.assertEqual(writes, [False])
                self.assertEqual(sum(s == 'BEGIN' for s in statements), 1)
                self.assertFalse(any(s.lstrip().upper().startswith(
                    ('INSERT', 'UPDATE', 'DELETE', 'REPLACE', 'CREATE', 'DROP', 'BEGIN IMMEDIATE'))
                    for s in statements))
                self.assertEqual(result.snapshot, expected)
                self.assert_full(result)
        self.assertEqual((self.state(), self.files()), (state, files))

    def test_q06_same_storage_triage_errors_no_retry_constructor_frozen_and_current_missing(self):
        self.retain('legacy')
        intent, selected = self.intent('legacy'), self.selected('legacy')
        apis = ((outcome.inspect_reconciliation_outcome, intent, 0),
                (outcome.inspect_acknowledgement_outcome, selected, selected.event_id - 1))
        state, files = self.state(), self.files()

        class ReceiverSubclass(dh.DurableHandoffReceipts):
            pass

        subclass = object.__new__(ReceiverSubclass)
        with mock.patch.object(dh.DurableHandoffReceipts, '__init__',
                               side_effect=AssertionError('no constructor')):
            for inspect, value, seek in apis:
                for invalid_receiver in (None, object(), SimpleNamespace(), subclass):
                    with mock.patch.object(self.receiver, 'inspect_reservation_status_history') as read:
                        with self.assertRaises(TypeError):
                            inspect(invalid_receiver, value)
                        read.assert_not_called()
                for error in (dh.ReceiptStorageError('storage failure'),
                              dh.ReceiptConflict('binding failure'), RuntimeError('read failure')):
                    with mock.patch.object(self.receiver, 'inspect_reservation_status_history',
                                           side_effect=error) as read:
                        with self.assertRaises(type(error)) as caught:
                            inspect(self.receiver, value)
                        self.assertIs(caught.exception, error)
                        read.assert_called_once_with('legacy', after_event_id=seek, limit=1)
                error = triage.InvalidRecoverySnapshot('invalid recovery snapshot')
                with mock.patch.object(self.receiver, 'inspect_reservation_status_history',
                        wraps=self.receiver.inspect_reservation_status_history) as read, \
                     mock.patch.object(outcome, 'classify_reservation', side_effect=error) as classify:
                    with self.assertRaises(triage.InvalidRecoverySnapshot) as caught:
                        inspect(self.receiver, value)
                    self.assertIs(caught.exception, error)
                    self.assertEqual((read.call_count, classify.call_count), (1, 1))
            # Actual pure triage rejects an invalid snapshot; no second read.
            history = self.receiver.inspect_reservation_status_history('legacy', limit=1)
            invalid_snapshot = dataclasses.replace(history.snapshot, accounting=dataclasses.replace(
                history.snapshot.accounting, outstanding_worker_seconds=0))
            with mock.patch.object(self.receiver, 'inspect_reservation_status_history',
                    return_value=dataclasses.replace(history, snapshot=invalid_snapshot)) as read:
                with self.assertRaises(triage.InvalidRecoverySnapshot):
                    outcome.inspect_reconciliation_outcome(self.receiver, intent)
                self.assertEqual(read.call_count, 1)
        self.assertEqual((self.state(), self.files()), (state, files))
        result = outcome.inspect_acknowledgement_outcome(self.receiver, selected)
        self.assertIs(type(result), outcome.RecoveryActionOutcome)
        self.assertEqual([field.name for field in dataclasses.fields(result)],
                         ['action', 'classification', 'request_id', 'request_sha256',
                          'snapshot', 'target_status', 'target_event_is_current'])
        self.assertFalse(hasattr(result, '__dict__'))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.classification = 'invented'
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.target_status.ack_revision = 1
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.snapshot.receipt.revision = 2

        # Legacy fixture only: bypass the immutable-event deletion guard outside
        # the trusted API. The outcome module performs no repair or backfill.
        self.receiver.require_reconciliation('legacy', expected_revision=1, now=LATER)
        self.receiver.acknowledge_status_event(selected.event_id, expected_ack_revision=0, now=LATER)
        self.sql('DROP TRIGGER reservation_status_no_delete')
        self.sql('DELETE FROM reservation_status_events WHERE request_id=? AND receipt_revision=2',
                 ('legacy',))
        state, files = self.state(), self.files()
        result = outcome.inspect_acknowledgement_outcome(self.receiver, selected)
        self.assertEqual(result.classification, 'target_ack_retained')
        self.assertIsNone(result.snapshot.current_status)
        self.assertIsNone(result.target_event_is_current)
        self.assertEqual(result.target_status.event.event_id, selected.event_id)
        self.assert_full(result)
        recon = outcome.inspect_reconciliation_outcome(self.receiver, intent)
        self.assertEqual(recon.classification, 'reconciliation_transition_observed')
        self.assertIsNone(recon.snapshot.current_status)
        self.assertIsNone(recon.target_event_is_current)
        self.assertEqual((self.state(), self.files()), (state, files))
        # Removing the remaining event emulates entirely missing local history.
        self.sql('DELETE FROM reservation_status_events WHERE request_id=?', ('legacy',))
        missing_state, missing_files = self.state(), self.files()
        missing = outcome.inspect_acknowledgement_outcome(self.receiver, selected)
        self.assertEqual(missing.classification, 'target_event_not_found')
        self.assertIsNone(missing.target_status)
        self.assertIsNone(missing.target_event_is_current)
        self.assert_full(missing)
        self.assertEqual((self.state(), self.files()), (missing_state, missing_files))

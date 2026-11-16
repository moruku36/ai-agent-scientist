"""R01–R10: authored NOT RUN. Synthetic, connected, local-only scenarios.

No historical test imports. The coordinator owns execution and acceptance.
"""
import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from ai_agent_scientist.admission import durable_handoff as dh
from ai_agent_scientist.admission.handoff_binding import PayloadBinding, InvalidHandoffBinding
from ai_agent_scientist.admission.handoff_request import InvalidHandoffRequest
from ai_agent_scientist.evidence.blob_store import BlobStore, BlobIntegrityError

INSTANT = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
MAXIMUM = (1 << 63) - 1


class IntegerChild(int):
    pass


class ReservationContracts(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.root.chmod(0o700)
        for name in ('requests', 'payloads'):
            (self.root / name).mkdir(mode=0o700)
        self.requests = BlobStore(self.root / 'requests', max_blob_bytes=8192)
        self.payloads = BlobStore(self.root / 'payloads', max_blob_bytes=128)
        self.raw = b'local reservation opaque bytes\x00\xff'
        digest = self.payloads.put(self.raw)
        self.binding = PayloadBinding('object', digest, 'application/octet-stream',
            'synthetic', 128, True, INSTANT + timedelta(hours=2))
        self.bindings = {'object': self.binding}
        self.scope = dh.TrustedHandoffScope('owner-verified-person', 'project', 'scientist', 'ctf')
        self.path = str(self.root / 'receiver.sqlite3')
        self.receiver = self.open()
        # Each request reserves (1+1)*8+4=20; settled floor consumes 10 of 50.
        self.envelope = dh.WorkerSecondsEnvelope('budget-owner', 'fixed-study', 50, 10, 1, 1, 8, 4)
        self.authority = dh.WorkerSecondsAuthority(self.envelope, True,
                                                   INSTANT + timedelta(hours=1))
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

    def open(self, scope=None):
        return dh.DurableHandoffReceipts(self.path, scope=self.scope if scope is None else scope)

    def put(self, request, **kwargs):
        return self.requests.put(json.dumps(request, **kwargs).encode())

    def mapping(self, request=None, scope=None, authority=None):
        request = self.request if request is None else request
        scope = self.scope if scope is None else scope
        return {(scope.principal, scope.project_id, scope.sender, scope.recipient,
                 request['authorization_ref'], request['budget_reservation_ref']):
                self.authority if authority is None else authority}

    def reserve(self, request=None, *, receiver=None, digest=None, **kwargs):
        request = self.request if request is None else request
        receiver = self.receiver if receiver is None else receiver
        args = dict(payload_store=self.payloads, bindings=self.bindings, now=INSTANT,
                    authorities=self.mapping(request, receiver._scope))
        args.update(kwargs)
        return receiver.reserve(self.requests, self.put(request) if digest is None else digest, **args)

    def next_request(self, number, **changes):
        return dict(self.request, request_id='request-' + str(number),
                    message_id='delivery-' + str(number),
                    budget_reservation_ref='reserve-' + str(number), **changes)

    def snapshot(self):
        with closing(sqlite3.connect(self.path)) as conn:
            return tuple(conn.execute('SELECT * FROM ' + table + ' ORDER BY 1').fetchall()
                         for table in ('durable_handoff_receipts',
                                       'worker_seconds_envelope', 'worker_seconds_reservations'))

    def sql(self, statement):
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute(statement)

    def test_r01_real_reads_arithmetic_and_independent_scoped_mapping(self):
        with mock.patch.object(self.requests, 'get', wraps=self.requests.get) as envelopes, \
                mock.patch.object(self.payloads, 'get', wraps=self.payloads.get) as payloads, \
                mock.patch.object(dh, 'check_uniform_worker_budget',
                                  wraps=dh.check_uniform_worker_budget) as arithmetic:
            result = self.reserve()
        envelopes.assert_called_once_with(self.digest)
        payloads.assert_called_once_with(self.binding.sha256)
        arithmetic.assert_called_once_with(planned_attempts=1, max_retries=1,
            per_attempt_seconds=8, evaluation_cleanup_seconds=4, total_worker_seconds=50)
        self.assertEqual(result.receipt, self.receiver.inspect('request-one'))
        self.assertEqual(result.reservation.worker_seconds, 20)
        self.assertEqual(result.reservation.request_sha256, self.digest)
        self.assertEqual(result.reservation.authorization_ref, 'authority-one')
        self.assertEqual(self.snapshot()[1][0][-1], 20)
        self.assertNotIn(self.raw, Path(self.path).read_bytes())
        for authorities in ({}, self.mapping(scope=replace(self.scope, principal='other')),
                            self.mapping(request=dict(self.request, authorization_ref='wrong')),
                            self.mapping(request=dict(self.request, budget_reservation_ref='wrong'))):
            before = self.snapshot()
            with self.assertRaises(dh.ReservationRefused):
                self.reserve(authorities=authorities)
            self.assertEqual(self.snapshot(), before)

    def test_r02_settled_floor_shared_capacity_and_exact_boundary(self):
        first = self.reserve()
        second = self.reserve(self.next_request(2))
        self.assertNotEqual(first.reservation, second.reservation)
        self.assertEqual(self.snapshot()[1][0][-1], 40)
        before = self.snapshot()
        with self.assertRaises(dh.ReservationRefused):
            self.reserve(self.next_request(3))
        self.assertEqual(self.snapshot(), before)
        self.assertIsNone(self.receiver.inspect('request-3'))
        # A failed first allocation must not initialize any accounting or receipt.
        other_path = str(self.root / 'too-small.sqlite3')
        small = dh.DurableHandoffReceipts(other_path, scope=self.scope)
        authority = replace(self.authority, envelope=replace(self.envelope, cap_worker_seconds=29))
        with self.assertRaises(dh.ReservationRefused):
            self.reserve(receiver=small, authorities=self.mapping(authority=authority))
        with closing(sqlite3.connect(other_path)) as conn:
            for table in ('durable_handoff_receipts', 'worker_seconds_envelope',
                          'worker_seconds_reservations'):
                self.assertEqual(conn.execute('SELECT count(*) FROM ' + table).fetchone()[0], 0)

    def test_r03_legitimate_scopes_share_one_owner_envelope_without_reset(self):
        self.reserve()
        other_scope = replace(self.scope, principal='another-authenticated-person', sender='sleep')
        other = self.open(other_scope)
        request = self.next_request(2, sender='sleep')
        self.reserve(request, receiver=other)
        before = self.snapshot()
        with self.assertRaises(dh.ReservationRefused):
            self.reserve(self.next_request(3, sender='sleep'), receiver=other)
        self.assertEqual(self.snapshot(), before)
        # A caller-declared new envelope/owner cannot open fresh capacity in this DB.
        changed = replace(self.authority, envelope=replace(self.envelope, owner_namespace='other'))
        with self.assertRaises(dh.ReceiptConflict):
            self.reserve(self.next_request(4), authorities=self.mapping(
                self.next_request(4), authority=changed))
        self.assertEqual(self.snapshot(), before)

    def test_r04_exact_bytes_and_stable_reference_cannot_alias_requests(self):
        self.reserve()
        before = self.snapshot()
        variants = [self.put(self.request, indent=1),
                    self.put(dict(self.request, authorization_ref='new-authority')),
                    self.put(dict(self.request, budget_reservation_ref='new-reference')),
                    self.put(dict(self.request, message_id='changed-delivery'))]
        for digest in variants:
            parsed = json.loads(self.requests.get(digest))
            with self.subTest(digest=digest), self.assertRaises(dh.ReceiptConflict):
                self.reserve(parsed, digest=digest)
        collision = self.next_request(2)
        collision['budget_reservation_ref'] = 'reserve-one'
        with self.assertRaises(dh.ReceiptConflict):
            self.reserve(collision)
        other = self.open(replace(self.scope, principal='other-person'))
        with self.assertRaises(dh.ReceiptConflict):
            self.reserve(receiver=other)
        self.assertEqual(self.snapshot(), before)

    def test_r05_duplicate_reopen_reconciliation_and_receipt_only_attachment(self):
        old = self.receiver.record(self.requests, self.digest, payload_store=self.payloads,
                                   bindings=self.bindings, now=INSTANT)
        first = self.reserve()
        self.assertEqual(first.receipt, old)
        current = self.receiver.require_reconciliation('request-one', expected_revision=1,
                                                       now=INSTANT + timedelta(seconds=1))
        reopened = self.open()
        before = self.snapshot()
        with mock.patch.object(self.payloads, 'get', wraps=self.payloads.get) as read:
            duplicate = self.reserve(receiver=reopened, now=INSTANT + timedelta(seconds=2))
        read.assert_called_once_with(self.binding.sha256)
        self.assertEqual(duplicate.receipt, current)
        self.assertEqual(duplicate.reservation, first.reservation)
        self.assertEqual(self.snapshot(), before)
        ambiguous = self.next_request(2)
        self.receiver.record(self.requests, self.put(ambiguous), payload_store=self.payloads,
                             bindings=self.bindings, now=INSTANT)
        self.receiver.require_reconciliation(ambiguous['request_id'], expected_revision=1, now=INSTANT)
        before = self.snapshot()
        with self.assertRaises(dh.ReceiptConflict):
            self.reserve(ambiguous)
        self.assertEqual(self.snapshot(), before)

    def test_r06_fixed_envelope_baseline_and_all_arithmetic_bindings_survive_reopen(self):
        self.reserve()
        before = self.snapshot()
        for field, value in (('owner_namespace', 'changed'), ('envelope_id', 'changed'),
                             ('cap_worker_seconds', 60), ('settled_worker_seconds', 0),
                             ('planned_attempts', 2), ('max_retries', 0),
                             ('per_attempt_seconds', 9), ('evaluation_cleanup_seconds', 5)):
            changed = replace(self.authority, envelope=replace(self.envelope, **{field: value}))
            with self.subTest(field=field), self.assertRaises(dh.ReceiptConflict):
                self.reserve(receiver=self.open(), authorities=self.mapping(authority=changed))
        self.assertEqual(self.snapshot(), before)

    def test_r07_exact_bounded_integer_domains_and_overflow_no_writes(self):
        invalid = [('cap_worker_seconds', True), ('settled_worker_seconds', -1),
                   ('planned_attempts', IntegerChild(1)), ('max_retries', 1.0),
                   ('per_attempt_seconds', None), ('evaluation_cleanup_seconds', MAXIMUM + 1),
                   ('planned_attempts', MAXIMUM), ('per_attempt_seconds', MAXIMUM),
                   ('evaluation_cleanup_seconds', MAXIMUM), ('cap_worker_seconds', 0),
                   ('settled_worker_seconds', 51)]
        for field, value in invalid:
            authority = replace(self.authority, envelope=replace(self.envelope, **{field: value}))
            with self.subTest(field=field, value=value), self.assertRaises(dh.ReservationRefused):
                self.reserve(authorities=self.mapping(authority=authority))
            self.assertEqual(self.snapshot(), ([], [], []))
        for mapping in (None, [], {('short',): self.authority},
                        {(True,) * 6: self.authority}, {tuple(self.mapping())[0]: object()}):
            with self.assertRaises(dh.ReservationRefused):
                self.reserve(authorities=mapping)
            self.assertEqual(self.snapshot(), ([], [], []))
        edge = dh.WorkerSecondsEnvelope('budget-owner', 'fixed-study', MAXIMUM, 0,
                                       1, 0, MAXIMUM, 0)
        result = self.reserve(authorities=self.mapping(authority=replace(self.authority, envelope=edge)))
        self.assertEqual(result.reservation.worker_seconds, MAXIMUM)
        self.assertEqual(self.snapshot()[1][0][-1], MAXIMUM)
        with self.assertRaises(dh.ReservationRefused):
            self.reserve(self.next_request(2), authorities=self.mapping(
                self.next_request(2), authority=replace(self.authority, envelope=edge)))

    def test_r08_fresh_authority_expiry_revocation_payload_and_request_on_duplicate(self):
        # First-time denial also leaves no receipt/envelope/reservation.
        revoked = replace(self.authority, available=False)
        with self.assertRaises(dh.ReservationRefused):
            self.reserve(authorities=self.mapping(authority=revoked))
        self.assertEqual(self.snapshot(), ([], [], []))
        self.reserve()
        before = self.snapshot()
        for authority in (revoked, replace(self.authority, available=1),
                          replace(self.authority, expires_at=INSTANT),
                          replace(self.authority, expires_at=INSTANT.replace(tzinfo=None))):
            with self.assertRaises(dh.ReservationRefused):
                self.reserve(authorities=self.mapping(authority=authority))
        with self.assertRaises(InvalidHandoffBinding):
            self.reserve(bindings={'object': replace(self.binding, available=False)})
        with self.assertRaises(InvalidHandoffRequest):
            self.reserve(now=INSTANT + timedelta(hours=1))
        # Verified payload is actually reread, not served from retained metadata.
        (self.root / 'payloads' / self.binding.sha256).write_bytes(b'tampered')
        with self.assertRaises(BlobIntegrityError):
            self.reserve()
        self.assertEqual(self.snapshot(), before)

    def test_r09_late_atomic_failure_and_lost_commit_ack_retain_conservative_state(self):
        self.sql("CREATE TRIGGER fail_reservation BEFORE INSERT ON worker_seconds_reservations "
                 "BEGIN SELECT RAISE(ABORT, 'synthetic storage failure'); END")
        with self.assertRaises(dh.ReceiptStorageError):
            self.reserve()
        self.assertEqual(self.snapshot(), ([], [], []))
        self.sql('DROP TRIGGER fail_reservation')
        self.reserve()
        before = self.snapshot()
        self.sql("CREATE TRIGGER fail_reservation BEFORE INSERT ON worker_seconds_reservations "
                 "BEGIN SELECT RAISE(ABORT, 'synthetic storage failure'); END")
        with self.assertRaises(dh.ReceiptStorageError):
            self.reserve(self.next_request(2))
        self.assertEqual(self.snapshot(), before)
        self.sql('DROP TRIGGER fail_reservation')
        original_connect = sqlite3.connect

        class LostAcknowledgement(sqlite3.Connection):
            def commit(self):
                super().commit()
                raise sqlite3.OperationalError('synthetic acknowledgement lost after commit')

        def connect(*args, **kwargs):
            return original_connect(*args, **kwargs, factory=LostAcknowledgement)

        with mock.patch.object(dh.sqlite3, 'connect', side_effect=connect):
            with self.assertRaises(dh.ReceiptStorageError):
                self.reserve(self.next_request(2))
        self.assertEqual(self.snapshot()[1][0][-1], 40)
        self.assertEqual(len(self.snapshot()[2]), 2)
        retained = self.reserve(self.next_request(2), receiver=self.open())
        self.assertEqual(retained.reservation.worker_seconds, 20)
        self.receiver.require_reconciliation('request-2', expected_revision=1, now=INSTANT)
        self.assertEqual(self.snapshot()[1][0][-1], 40)
        with self.assertRaises(dh.ReservationRefused):
            self.reserve(self.next_request(3))

    def test_r10_real_separate_connection_concurrent_duplicate_and_competing_capacity(self):
        receivers = [self.open(), self.open()]
        actual_loader = dh.load_bound_handoff_request

        def race(requests):
            barrier = threading.Barrier(2)

            def synchronized_load(*args, **kwargs):
                result = actual_loader(*args, **kwargs)
                barrier.wait(timeout=5)
                return result

            def call(index):
                try:
                    return self.reserve(requests[index], receiver=receivers[index])
                except dh.ReservationRefused as error:
                    return error

            # Each operation opens its own actual SQLite connection and uses
            # BEGIN IMMEDIATE. Only the loader timing is synchronized.
            with mock.patch.object(dh, 'load_bound_handoff_request', side_effect=synchronized_load):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    return list(pool.map(call, (0, 1)))

        duplicates = race([self.request, self.request])
        self.assertEqual(duplicates[0], duplicates[1])
        self.assertEqual(len(self.snapshot()[2]), 1)
        competitors = race([self.next_request(2), self.next_request(3)])
        self.assertEqual(sum(type(item) is dh.ReservedHandoff for item in competitors), 1)
        self.assertEqual(sum(type(item) is dh.ReservationRefused for item in competitors), 1)
        rows = self.snapshot()
        self.assertEqual((len(rows[0]), len(rows[2]), rows[1][0][-1]), (2, 2, 40))

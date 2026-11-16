"""D01-D10 authored, NOT RUN: connected offline SQLite/BlobStore scenarios.

No historical test imports, network, services, research or dispatch. Temporary
local databases and synthetic bytes only. Coordinator owns execution/review.
"""
import copy
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
from ai_agent_scientist.evidence.blob_store import (
    BlobStore, BlobNotFound, BlobIntegrityError, BlobTooLarge, BlobIOError,
)
from ai_agent_scientist.evidence.json_blob import InvalidJSONBlob

NOW = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)


class Hostile:
    def __eq__(self, other):
        raise AssertionError('untrusted comparison')

    def __bool__(self):
        raise AssertionError('untrusted truthiness')


class IntSubclass(int):
    pass


class DurableHandoffTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.envelopes = self.root / 'envelopes'
        self.payload_root = self.root / 'payloads'
        self.envelopes.mkdir()
        self.payload_root.mkdir()
        self.requests = BlobStore(self.envelopes, max_blob_bytes=8192)
        self.payloads = BlobStore(self.payload_root, max_blob_bytes=64)
        self.raw = b'opaque payload sentinel:\xff\x00\r\n'
        payload_sha = self.payloads.put(self.raw)
        self.binding = PayloadBinding(
            'payload-1', payload_sha, 'application/octet-stream', 'synthetic',
            64, True, NOW + timedelta(minutes=30))
        self.bindings = {self.binding.id: self.binding}
        self.request = {
            'schema_version': 'harness-handoff/1', 'synthetic': True,
            'message_id': 'm1', 'request_id': 'r1', 'attempt_id': None,
            'replicate_id': None, 'project_id': 'p1', 'sender': 'scientist',
            'recipient': 'ctf', 'kind': 'request', 'in_reply_to': None,
            'expected_revision': 0, 'authorization_ref': 'a1',
            'budget_reservation_ref': 'b1',
            'payload': {key: getattr(self.binding, key)
                        for key in ('id', 'sha256', 'media_type', 'classification')},
            'created_at': '2026-11-17T11:00:00Z',
            'expires_at': '2026-11-17T13:00:00Z',
        }
        self.digest = self.put(self.request)
        self.scope = dh.TrustedHandoffScope('authenticated-local-principal', 'p1', 'scientist', 'ctf')
        self.db_path = str(self.root / 'receipts.sqlite3')
        self.receiver = self.reopen()

    def reopen(self, scope=None):
        return dh.DurableHandoffReceipts(
            self.db_path, scope=self.scope if scope is None else scope)

    def put(self, request, **options):
        return self.requests.put(json.dumps(request, **options).encode('utf-8'))

    def record(self, digest=None, receiver=None, **options):
        args = dict(payload_store=self.payloads, bindings=self.bindings, now=NOW)
        args.update(options)
        return (self.receiver if receiver is None else receiver).record(
            self.requests, self.digest if digest is None else digest, **args)

    def count(self):
        with closing(sqlite3.connect(self.db_path)) as conn:
            return conn.execute('SELECT count(*) FROM durable_handoff_receipts').fetchone()[0]

    def sql(self, statement):
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(statement)

    def test_d01_actual_connected_load_and_minimal_receipt(self):
        with mock.patch.object(dh, 'load_bound_handoff_request',
                               wraps=dh.load_bound_handoff_request) as load, \
                mock.patch.object(self.requests, 'get', wraps=self.requests.get) as envelope, \
                mock.patch.object(self.payloads, 'get', wraps=self.payloads.get) as payload:
            receipt = self.record()
            load.assert_called_once_with(self.requests, self.digest,
                payload_store=self.payloads, bindings=self.bindings, now=NOW)
            envelope.assert_called_once_with(self.digest)
            payload.assert_called_once_with(self.binding.sha256)
        self.assertEqual((receipt.revision, receipt.state), (1, 'recorded'))
        self.assertEqual(receipt.request_sha256, self.digest)
        self.assertEqual(receipt.payload_sha256, self.binding.sha256)
        self.assertEqual(receipt.principal, self.scope.principal)
        self.assertNotEqual(receipt.principal, self.request['sender'])
        self.assertEqual(self.receiver.inspect('r1'), receipt)
        with closing(sqlite3.connect(self.db_path)) as conn:
            columns = [row[1] for row in conn.execute('PRAGMA table_info(durable_handoff_receipts)')]
            self.assertEqual(set(columns), set(dh.DurableReceipt.__dataclass_fields__))
        self.assertNotIn(self.raw, Path(self.db_path).read_bytes())
        self.assertFalse(hasattr(receipt, 'authorization_ref'))
        self.assertFalse(hasattr(receipt, 'admitted'))

    def test_d02_reopen_replay_current_unresolved_cas(self):
        first = self.record()
        receiver = self.reopen()
        self.assertEqual(self.record(receiver=receiver, now=NOW + timedelta(seconds=1)), first)
        current = receiver.require_reconciliation('r1', expected_revision=1,
                                                   now=NOW + timedelta(seconds=2))
        self.assertEqual((current.revision, current.state), (2, 'reconciliation_required'))
        self.assertEqual(current.recorded_at, first.recorded_at)
        self.assertNotEqual(current.updated_at, first.updated_at)
        reopened = self.reopen()
        with mock.patch.object(self.payloads, 'get', wraps=self.payloads.get) as read:
            self.assertEqual(self.record(receiver=reopened, now=NOW + timedelta(seconds=3)), current)
            read.assert_called_once_with(self.binding.sha256)
        self.assertEqual(reopened.inspect('r1'), current)
        with self.assertRaises(dh.ReceiptRevisionError):
            reopened.require_reconciliation('r1', expected_revision=1, now=NOW)
        with self.assertRaises(dh.InvalidReceiptTransition):
            reopened.require_reconciliation('r1', expected_revision=2, now=NOW + timedelta(seconds=4))
        self.assertEqual(self.count(), 1)

    def test_d03_exact_byte_conflicts_whitespace_message_time_payload(self):
        first = self.record()
        variants = [self.put(self.request, indent=2),
                    self.requests.put(json.dumps(self.request).encode() + b'\n')]
        for field, value in (('message_id', 'm2'), ('created_at', '2026-11-17T11:01:00Z'),
                             ('expires_at', '2026-11-17T13:01:00Z'),
                             ('authorization_ref', 'a2')):
            changed = dict(self.request, **{field: value})
            variants.append(self.put(changed))
        other_sha = self.payloads.put(b'other verified bytes')
        other_binding = replace(self.binding, sha256=other_sha)
        changed = copy.deepcopy(self.request)
        changed['payload']['sha256'] = other_sha
        for digest in variants:
            with self.subTest(digest=digest), self.assertRaises(dh.ReceiptConflict):
                self.record(digest)
        with self.assertRaises(dh.ReceiptConflict):
            self.record(self.put(changed), bindings={other_binding.id: other_binding})
        self.assertEqual(self.reopen().inspect('r1'), first)
        self.assertEqual(self.count(), 1)

    def test_d04_message_collision_and_independent_identity_scopes(self):
        self.record()
        changed = dict(self.request, request_id='r2')
        with self.assertRaises(dh.ReceiptConflict):
            self.record(self.put(changed))
        self.assertIsNone(self.receiver.inspect('r2'))
        for scope in (replace(self.scope, principal='other-authenticated-principal'),
                      replace(self.scope, project_id='p2'), replace(self.scope, recipient='sleep')):
            request = dict(self.request, project_id=scope.project_id, recipient=scope.recipient)
            receipt = self.record(self.put(request), receiver=self.reopen(scope))
            self.assertEqual(receipt.principal, scope.principal)
            self.assertEqual(receipt.project_id, scope.project_id)
            self.assertEqual(receipt.recipient, scope.recipient)
        # A changed sender mapping does not create a new identity namespace.
        alias = self.reopen(replace(self.scope, sender='sleep'))
        with self.assertRaises(dh.ReceiptScopeError):
            alias.inspect('r1')
        with self.assertRaises(dh.ReceiptScopeError):
            self.record(self.put(dict(self.request, sender='sleep')), receiver=alias)
        self.assertEqual(self.count(), 4)

    def test_d05_revision_exact_types_bounds_stale_and_clock(self):
        for value, error in ((True, InvalidHandoffRequest), (-1, InvalidHandoffRequest),
                             ('0', InvalidHandoffRequest), (1, dh.ReceiptRevisionError),
                             ((1 << 63) - 1, dh.ReceiptRevisionError),
                             ((1 << 63), dh.ReceiptRevisionError)):
            with self.subTest(value=value), self.assertRaises(error):
                self.record(self.put(dict(self.request, expected_revision=value)))
        self.assertEqual(self.count(), 0)
        first = self.record()
        for value in (True, False, IntSubclass(1), Hostile(), -1, 0, 2, (1 << 63) - 1, 1 << 63):
            with self.subTest(value=type(value)), self.assertRaises(dh.ReceiptRevisionError):
                self.receiver.require_reconciliation('r1', expected_revision=value, now=NOW)
        with self.assertRaises(ValueError):
            self.receiver.require_reconciliation('r1', expected_revision=1, now=NOW - timedelta(seconds=1))
        for now in (None, Hostile(), NOW.replace(tzinfo=None), NOW.astimezone(timezone(timedelta(hours=1)))):
            with self.subTest(now=type(now)), self.assertRaises(TypeError):
                self.record(now=now)
        with self.assertRaises(TypeError):
            self.receiver.inspect(Hostile())
        self.assertEqual(self.receiver.inspect('r1'), first)

    def test_d06_mapping_and_trusted_path_type_guards(self):
        for field, value in (('project_id', 'wrong'), ('sender', 'sleep'), ('recipient', 'sleep')):
            with self.subTest(field=field), self.assertRaises(dh.ReceiptScopeError):
                self.record(self.put(dict(self.request, **{field: value})))
        for field in ('principal', 'project_id', 'sender', 'recipient'):
            for value in (Hostile(), True, ''):
                with self.subTest(field=field), self.assertRaises(TypeError):
                    self.reopen(replace(self.scope, **{field: value}))
        for path in (Hostile(), Path(self.db_path), True):
            with self.assertRaises(TypeError):
                dh.DurableHandoffReceipts(path, scope=self.scope)
        with self.assertRaises(ValueError):
            dh.DurableHandoffReceipts('relative.sqlite3', scope=self.scope)
        link = self.root / 'link.sqlite3'
        link.symlink_to(self.db_path)
        with self.assertRaises(dh.ReceiptStorageError):
            dh.DurableHandoffReceipts(str(link), scope=self.scope)
        public = self.root / 'public'
        public.mkdir(mode=0o755)
        public.chmod(0o755)
        with self.assertRaises(dh.ReceiptStorageError):
            dh.DurableHandoffReceipts(str(public / 'db'), scope=self.scope)
        self.assertEqual(self.count(), 0)

    def test_d07_fresh_preflight_expiry_revocation_and_retained_inspection(self):
        failures = [dict(now=NOW + timedelta(hours=1)),
                    dict(bindings={}),
                    dict(bindings={self.binding.id: replace(self.binding, available=False)}),
                    dict(bindings={self.binding.id: replace(self.binding, access_expires_at=NOW)}),
                    dict(bindings={self.binding.id: replace(self.binding, sha256='0' * 64)})]
        for options in failures:
            with self.subTest(options=tuple(options)), self.assertRaises(
                    (InvalidHandoffRequest, InvalidHandoffBinding)):
                self.record(**options)
            self.assertEqual(self.count(), 0)
        # Actual strict JSON and request preflight, not a stubbed request dict.
        for raw, error in ((b'{"kind":"request","kind":"request"}', InvalidJSONBlob),
                           (b'{broken', InvalidJSONBlob),
                           (json.dumps(dict(self.request, kind='result')).encode(), InvalidHandoffRequest)):
            with self.assertRaises(error):
                self.record(self.requests.put(raw))
            self.assertEqual(self.count(), 0)
        first = self.record()
        for options in failures:
            with self.assertRaises((InvalidHandoffRequest, InvalidHandoffBinding)):
                self.record(**options)
            self.assertEqual(self.reopen().inspect('r1'), first)
        # Local reconciliation after expiry does not read or grant blob access.
        current = self.receiver.require_reconciliation('r1', expected_revision=1,
                                                       now=NOW + timedelta(hours=2))
        self.assertEqual(current.state, 'reconciliation_required')
        with self.assertRaises(InvalidHandoffRequest):
            self.record(now=NOW + timedelta(hours=2))

    def test_d08_actual_blob_failures_before_insert_and_on_replay(self):
        for store_root, digest, original in (
                (self.envelopes, self.digest, (self.envelopes / self.digest).read_bytes()),
                (self.payload_root, self.binding.sha256, self.raw)):
            path = store_root / digest
            for replacement, error in ((None, BlobNotFound), (b'tampered', BlobIntegrityError),
                                       (b'x' * (8193 if store_root == self.envelopes else 65), BlobTooLarge)):
                try:
                    if replacement is None:
                        path.unlink()
                    else:
                        path.write_bytes(replacement)
                    with self.assertRaises(error):
                        self.record()
                    self.assertEqual(self.count(), 0)
                finally:
                    path.write_bytes(original)
        first = self.record()
        path = self.payload_root / self.binding.sha256
        path.write_bytes(b'changed after recording')
        try:
            with self.assertRaises(BlobIntegrityError):
                self.record()
            self.assertEqual(self.reopen().inspect('r1'), first)
        finally:
            path.write_bytes(self.raw)
        with mock.patch.object(self.payloads, 'get', side_effect=BlobIOError('injected local I/O')):
            with self.assertRaises(BlobIOError):
                self.record()
        self.assertEqual(self.receiver.inspect('r1'), first)

    def test_d09_atomic_sqlite_failure_rollback_and_lock(self):
        # RAISE(FAIL) retains statement changes until OUR transaction rollback.
        self.sql("CREATE TRIGGER fail_insert AFTER INSERT ON durable_handoff_receipts "
                 "BEGIN SELECT RAISE(FAIL, 'injected insert'); END")
        with self.assertRaises(dh.ReceiptStorageError):
            self.record()
        self.assertEqual(self.count(), 0)
        self.sql('DROP TRIGGER fail_insert')
        real_connect = sqlite3.connect

        class CommitFailure(sqlite3.Connection):
            def commit(self):
                raise sqlite3.OperationalError('injected commit failure')

        def connect(*args, **kwargs):
            return real_connect(*args, **kwargs, factory=CommitFailure)

        with mock.patch.object(dh.sqlite3, 'connect', side_effect=connect):
            with self.assertRaises(dh.ReceiptStorageError):
                self.record()
        self.assertEqual(self.count(), 0)
        blocker = real_connect(self.db_path, isolation_level=None)
        try:
            blocker.execute('BEGIN IMMEDIATE')
            with self.assertRaises(dh.ReceiptStorageError):
                self.record()
        finally:
            blocker.rollback()
            blocker.close()
        self.assertEqual(self.count(), 0)
        first = self.record()
        self.sql("CREATE TRIGGER fail_update AFTER UPDATE ON durable_handoff_receipts "
                 "BEGIN SELECT RAISE(FAIL, 'injected update'); END")
        with self.assertRaises(dh.ReceiptStorageError):
            self.receiver.require_reconciliation('r1', expected_revision=1, now=NOW)
        self.assertEqual(self.reopen().inspect('r1'), first)
        self.sql('DROP TRIGGER fail_update')
        self.assertEqual(self.receiver.require_reconciliation(
            'r1', expected_revision=1, now=NOW).revision, 2)
        # An error after commit is not evidence that the receipt is absent.
        class CloseFailure(sqlite3.Connection):
            def close(self):
                super().close()
                raise sqlite3.OperationalError('injected post-commit close failure')

        def close_failure_connect(*args, **kwargs):
            return real_connect(*args, **kwargs, factory=CloseFailure)

        digest = self.put(dict(self.request, request_id='r-close', message_id='m-close'))
        with mock.patch.object(dh.sqlite3, 'connect', side_effect=close_failure_connect):
            with self.assertRaises(dh.ReceiptStorageError):
                self.record(digest)
        retained = self.reopen().inspect('r-close')
        self.assertEqual((retained.revision, retained.state), (1, 'recorded'))
        self.assertEqual(self.record(digest), retained)
        self.assertEqual(self.count(), 2)

    def test_d10_concurrent_local_connections_dedup_and_cas(self):
        receivers = [self.reopen(), self.reopen()]
        barrier = threading.Barrier(2)

        def record(index):
            barrier.wait(timeout=5)
            return self.record(receiver=receivers[index])

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(record, range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(self.count(), 1)
        barrier = threading.Barrier(2)

        def transition(index):
            barrier.wait(timeout=5)
            try:
                return receivers[index].require_reconciliation('r1', expected_revision=1, now=NOW)
            except dh.ReceiptRevisionError:
                return 'stale'

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(transition, range(2)))
        self.assertEqual(results.count('stale'), 1)
        current = self.reopen().inspect('r1')
        self.assertEqual((current.revision, current.state), (2, 'reconciliation_required'))
        self.assertEqual(self.record(), current)
        self.assertEqual(self.count(), 1)

"""F01–F06: exactly six NEW self-contained tests, authored NOT EXECUTED.
Real BlobStore/private SQLite fixtures; no historical test imports.
"""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from unittest import mock

from ai_agent_scientist.admission import durable_handoff as dh
from ai_agent_scientist.admission import recovery_report as rr
from ai_agent_scientist.admission import recovery_triage as triage
from ai_agent_scientist.admission.handoff_binding import PayloadBinding
from ai_agent_scientist.evidence.blob_store import BlobStore

NOW = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)


class RecoveryReportContracts(unittest.TestCase):
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

    def retain(self, request_id='request-one', *, scope=None, receipt_only=False):
        scope = self.scope if scope is None else scope
        receiver = (self.receiver if scope == self.scope else
                    dh.DurableHandoffReceipts(self.path, scope=scope))
        suffix = '-'.join((request_id, scope.principal, scope.project_id, scope.recipient))
        reservation_ref = 'reserve-' + suffix
        request = {
            'schema_version': 'harness-handoff/1', 'synthetic': True,
            'message_id': 'message-' + suffix, 'request_id': request_id,
            'attempt_id': None, 'replicate_id': None, 'project_id': scope.project_id,
            'sender': scope.sender, 'recipient': scope.recipient, 'kind': 'request',
            'in_reply_to': None, 'expected_revision': 0,
            'authorization_ref': 'private-authority', 'budget_reservation_ref': reservation_ref,
            'payload': {name: getattr(self.binding, name)
                        for name in ('id', 'sha256', 'media_type', 'classification')},
            'created_at': '2026-11-17T11:00:00Z', 'expires_at': '2026-11-17T13:00:00Z',
        }
        digest = self.requests.put(json.dumps(request).encode('utf-8'))
        kwargs = dict(payload_store=self.payloads, bindings={'object': self.binding}, now=NOW)
        if receipt_only:
            return receiver.record(self.requests, digest, **kwargs)
        authorities = {(scope.principal, scope.project_id, scope.sender, scope.recipient,
            'private-authority', reservation_ref): dh.WorkerSecondsAuthority(
                self.envelope, True, NOW + timedelta(hours=1))}
        return receiver.reserve(self.requests, digest, authorities=authorities, **kwargs)

    def observe(self, retained, name, *, usage=None, revision=1, seconds=1,
                stopped=False, cleanup=False):
        r = retained.reservation
        return self.receiver.record_usage_observation(name, request_id=r.request_id,
            budget_reservation_ref=r.budget_reservation_ref, request_sha256=r.request_sha256,
            expected_revision=revision, worker_seconds=usage, execution_stopped=stopped,
            cleanup_known=cleanup, observed_at=NOW + timedelta(seconds=seconds))

    def sql(self, statement):
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute(statement)

    def state(self):
        with closing(sqlite3.connect(self.path)) as conn:
            return tuple(conn.iterdump())

    def document(self, **kwargs):
        return json.loads(rr.build_recovery_report(self.receiver, **kwargs).data)

    def test_f01_connected_chain_allowlist_exact_sources_and_immutable_artifact(self):
        retained = self.retain()
        observation = self.observe(retained, 'observation-one')
        source = triage.inspect_recovery_triages(self.receiver).entries[0]
        with mock.patch.object(rr, 'inspect_recovery_triages',
                               wraps=rr.inspect_recovery_triages) as inspect:
            artifact = rr.build_recovery_report(self.receiver)
        inspect.assert_called_once_with(self.receiver, after_request_id=None, limit=100)
        item = json.loads(artifact.data)['entries'][0]
        self.assertEqual(item['reasons'], list(source.reasons))
        for section, original in (('receipt', source.snapshot.receipt),
                ('reservation', retained.reservation), ('accounting', source.snapshot.accounting),
                ('latest_usage_observation', observation)):
            self.assertEqual(item[section], {k: getattr(original, k) for k in item[section]})
        status = source.snapshot.current_status
        self.assertEqual(item['current_status']['event'],
                         {k: getattr(status.event, k) for k in item['current_status']['event']})
        self.assertEqual(item['current_status']['ack_revision'], status.ack_revision)
        self.assertEqual(item['current_status']['acknowledged_at'], status.acknowledged_at)
        forbidden = {'principal', 'owner_namespace', 'envelope_id', 'authorization_ref',
            'cap_worker_seconds', 'settled_worker_seconds', 'reserved_worker_seconds',
            'remaining_worker_seconds', 'payload', 'db_path', 'exception'}
        def keys(value):
            if isinstance(value, dict):
                return set(value).union(*(keys(v) for v in value.values()))
            if isinstance(value, list):
                return set().union(*(keys(v) for v in value))
            return set()
        self.assertFalse(keys(json.loads(artifact.data)) & forbidden)
        self.assertNotIn(b'private-authority', artifact.data)
        self.assertNotIn(b'private-owner', artifact.data)
        self.assertNotIn(self.path.encode(), artifact.data)
        self.assertIs(type(artifact.data), bytes)
        self.assertEqual(artifact.sha256, sha256(artifact.data).hexdigest())
        with self.assertRaises(FrozenInstanceError):
            artifact.sha256 = 'forged'
        self.assertFalse(hasattr(artifact, '__dict__'))

    def test_f02_exact_empty_bytes_reopen_hash_and_unavailable_blobs(self):
        golden = (b'{"entries":[],"local_report_version":"receiver-recovery-report-local/1",'
                  b'"observation_selection":"latest_local_insertion_only","page":{'
                  b'"after_request_id":null,"limit":100,"next_after_request_id":null},'
                  b'"visibility":"private"}')
        empty = rr.build_recovery_report(self.receiver)
        self.assertEqual(empty.data, golden)
        self.assertEqual(empty.sha256, sha256(golden).hexdigest())
        self.retain('request-雪')
        original = rr.build_recovery_report(self.receiver)
        reopened = dh.DurableHandoffReceipts(self.path, scope=self.scope)
        for name in ('requests', 'payloads'):
            for path in (self.root / name).iterdir():
                path.unlink()
        with mock.patch.object(dh, 'load_bound_handoff_request',
                               side_effect=AssertionError('retained read only')):
            self.assertEqual(rr.build_recovery_report(reopened), original)
            self.assertEqual(rr.build_recovery_report(reopened,
                max_output_bytes=len(original.data)), original)
        self.assertIn(br'\u96ea', original.data)
        self.assertNotIn('雪'.encode(), original.data)
        self.assertFalse(original.data.endswith(b'\n'))

    def test_f03_real_pagination_scopes_and_exact_cursor_limit_types(self):
        for name in ('request-c', 'request-a', 'request-b'):
            self.retain(name)
        self.retain('receipt-only', receipt_only=True)
        for scope in (replace(self.scope, principal='other'),
                      replace(self.scope, project_id='other'),
                      replace(self.scope, recipient='sleep')):
            self.retain('foreign', scope=scope)
        first = rr.build_recovery_report(self.receiver, limit=2)
        self.assertEqual([e['receipt']['request_id'] for e in json.loads(first.data)['entries']],
                         ['request-a', 'request-b'])
        self.assertEqual((first.after_request_id, first.limit, first.entry_count,
                          first.next_after_request_id), (None, 2, 2, 'request-b'))
        last = rr.build_recovery_report(self.receiver, after_request_id='request-b', limit=2)
        self.assertEqual(last.entry_count, 1)
        self.assertIsNone(last.next_after_request_id)
        self.assertEqual(json.loads(last.data)['page']['after_request_id'], 'request-b')
        self.assertEqual(rr.build_recovery_report(self.receiver,
                         after_request_id='request-z').entry_count, 0)
        self.retain('request-aa')  # New rows behind a cursor require restarting the scan.
        self.assertEqual(rr.build_recovery_report(self.receiver,
                         after_request_id='request-b').entry_count, 1)
        self.assertEqual(rr.build_recovery_report(self.receiver).entry_count, 4)
        class Text(str):
            pass
        for kwargs in ({'limit': True}, {'limit': 0}, {'limit': 101}, {'limit': 1.0},
                       {'after_request_id': ''}, {'after_request_id': Text('request-a')},
                       {'after_request_id': 0}, {'after_request_id': 'x' * 1025}):
            with self.subTest(kwargs=kwargs), self.assertRaises((ValueError, TypeError)):
                rr.build_recovery_report(self.receiver, **kwargs)
        changed_sender = dh.DurableHandoffReceipts(self.path,
                            scope=replace(self.scope, sender='sleep'))
        with self.assertRaises(dh.ReceiptScopeError):
            rr.build_recovery_report(changed_sender)

    def test_f04_unknown_zero_overcap_ack_and_latest_insertion_facts(self):
        retained = {name: self.retain(name) for name in ('none', 'unknown', 'zero', 'over')}
        old = self.observe(retained['unknown'], 'older-known', usage=7)
        self.observe(retained['unknown'], 'later-time', revision=2, usage=8, seconds=8)
        latest = self.observe(retained['unknown'], 'inserted-last', revision=2, seconds=3)
        self.assertEqual(self.observe(retained['unknown'], 'older-known', usage=7), old)
        self.observe(retained['zero'], 'zero-observation', usage=0, stopped=True, cleanup=True)
        self.observe(retained['over'], 'over-observation', usage=21, stopped=True)
        event = self.receiver.inspect_reservation('zero').current_status.event
        ack = self.receiver.acknowledge_status_event(event.event_id,
                    expected_ack_revision=0, now=NOW + timedelta(seconds=10))
        entries = {e['receipt']['request_id']: e for e in self.document()['entries']}
        self.assertIsNone(entries['none']['latest_usage_observation'])
        self.assertIn('no_observation', entries['none']['reasons'])
        unknown = entries['unknown']['latest_usage_observation']
        self.assertEqual((unknown['sequence'], unknown['observation_id'], unknown['observed_at']),
                         (latest.sequence, latest.observation_id, latest.observed_at))
        self.assertIsNone(unknown['worker_seconds'])
        self.assertIsNone(unknown['over_cap'])
        self.assertIn('latest_insertion_view_only', entries['unknown']['reasons'])
        zero = entries['zero']
        self.assertIs(type(zero['latest_usage_observation']['worker_seconds']), int)
        self.assertEqual(zero['latest_usage_observation']['worker_seconds'], 0)
        self.assertIn('usage_known_zero', zero['reasons'])
        self.assertIn('local_acknowledged', zero['reasons'])
        self.assertIs(zero['latest_usage_observation']['execution_stopped'], True)
        self.assertIs(zero['latest_usage_observation']['cleanup_known'], True)
        self.assertEqual(zero['current_status']['acknowledged_at'], ack.acknowledged_at)
        self.assertIs(entries['over']['latest_usage_observation']['over_cap'], True)
        self.assertIs(entries['over']['latest_usage_observation']['cleanup_known'], False)
        self.assertIn('observed_over_cap', entries['over']['reasons'])
        for entry in entries.values():
            self.assertEqual(entry['accounting'], {'allocation_worker_seconds': 20,
                                                 'outstanding_worker_seconds': 20})
        # In this private temporary DB, emulate a legacy missing event through
        # fixture corruption outside the trusted API.
        self.sql("DROP TRIGGER reservation_status_no_delete")
        self.sql("DELETE FROM reservation_status_events WHERE request_id='unknown' AND receipt_revision=2")
        missing = next(e for e in self.document()['entries'] if e['receipt']['request_id'] == 'unknown')
        self.assertIsNone(missing['current_status'])
        self.assertIn('local_ack_unknown', missing['reasons'])

    def test_f05_exact_byte_limits_types_whole_refusal_and_no_intake(self):
        self.retain()
        artifact = rr.build_recovery_report(self.receiver)
        self.assertEqual(rr.build_recovery_report(self.receiver,
                         max_output_bytes=len(artifact.data)), artifact)
        before = self.state()
        for bound in (1, len(artifact.data) - 1):
            result = None
            with self.assertRaises(rr.RecoveryReportTooLarge) as error:
                result = rr.build_recovery_report(self.receiver, max_output_bytes=bound)
            self.assertIsNone(result)
            self.assertEqual(error.exception.args, ('recovery report exceeds byte limit',))
        class Number(int):
            pass
        with mock.patch.object(rr, 'inspect_recovery_triages') as inspect:
            for bound in (True, False, Number(10), 0, -1, 1.0, '10', None, rr.MAX_OUTPUT_BYTES + 1):
                with self.subTest(bound=bound), self.assertRaises(ValueError):
                    rr.build_recovery_report(self.receiver, max_output_bytes=bound)
            inspect.assert_not_called()
        for candidate in (None, {}, triage.inspect_recovery_triages(self.receiver)):
            with self.assertRaises(TypeError):
                rr.build_recovery_report(candidate)
        self.assertEqual(self.state(), before)

    def test_f06_one_real_snapshot_no_writes_later_row_and_storage_failures(self):
        self.retain('request-a')
        self.retain('request-b')
        before = self.state()
        files = {str(p.relative_to(self.root)): p.read_bytes()
                 for p in self.root.rglob('*') if p.is_file()}
        actual_connect = sqlite3.connect
        connections, statements = [], []
        def connect(*args, **kwargs):
            conn = actual_connect(*args, **kwargs)
            conn.set_trace_callback(statements.append)
            connections.append(conn)
            return conn
        with mock.patch.object(dh.sqlite3, 'connect', side_effect=connect), \
             mock.patch.object(dh.DurableHandoffReceipts, '__init__',
                               side_effect=AssertionError('never construct a receiver')), \
             mock.patch('builtins.open', side_effect=AssertionError('no report file writes')):
            self.assertEqual(rr.build_recovery_report(self.receiver).entry_count, 2)
        self.assertEqual(len(connections), 1)
        self.assertEqual(statements.count('BEGIN'), 1)
        self.assertEqual(statements.count('COMMIT'), 1)
        self.assertFalse(any(s.startswith(('INSERT ', 'UPDATE ', 'DELETE ', 'CREATE ', 'ALTER '))
                             for s in statements))
        self.assertEqual(self.state(), before)
        self.assertEqual({str(p.relative_to(self.root)): p.read_bytes()
                          for p in self.root.rglob('*') if p.is_file()}, files)
        # A different trusted writer commits between two real snapshot reads.
        self.sql('PRAGMA journal_mode=WAL')
        writer = dh.DurableHandoffReceipts(self.path, scope=self.scope)
        snapshot = self.receiver._reservation_snapshot
        def read_then_commit(conn, row):
            result = snapshot(conn, row)
            if result.receipt.request_id == 'request-a':
                writer.require_reconciliation('request-b', expected_revision=1,
                                              now=NOW + timedelta(seconds=2))
            return result
        with mock.patch.object(self.receiver, '_reservation_snapshot', side_effect=read_then_commit):
            page = self.document()['entries']
        self.assertEqual([e['receipt']['revision'] for e in page], [1, 1])
        self.assertEqual(self.receiver.inspect('request-b').revision, 2)
        self.sql("UPDATE worker_seconds_reservations SET worker_seconds=19 WHERE request_id='request-b'")
        corrupted = self.state()
        result = None
        with self.assertRaises(dh.ReceiptConflict):
            result = rr.build_recovery_report(self.receiver)
        self.assertIsNone(result)
        self.assertEqual(self.state(), corrupted)
        self.sql("UPDATE worker_seconds_reservations SET worker_seconds=20 WHERE request_id='request-b'")
        self.sql('DROP TABLE local_usage_observations')
        broken = self.state()
        with self.assertRaises(dh.ReceiptStorageError):
            result = rr.build_recovery_report(self.receiver)
        self.assertIsNone(result)
        self.assertEqual(self.state(), broken)

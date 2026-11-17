"""K01–K06: exactly six NEW self-contained tests, authored NOT EXECUTED.
Real BlobStore/private SQLite fixtures; no historical test imports.
"""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from unittest import mock

from ai_agent_scientist.admission import durable_handoff as dh
from ai_agent_scientist.admission import recovery_console as rc
from ai_agent_scientist.admission import recovery_report as rr
from ai_agent_scientist.admission.handoff_binding import PayloadBinding
from ai_agent_scientist.evidence.blob_store import BlobStore

NOW = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)


class RecoveryConsoleContracts(unittest.TestCase):
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

    def retain(self, request_id='request-one'):
        scope = self.scope
        reservation_ref = 'reserve-' + request_id
        request = {
            'schema_version': 'harness-handoff/1', 'synthetic': True,
            'message_id': 'message-' + request_id, 'request_id': request_id,
            'attempt_id': None, 'replicate_id': None, 'project_id': scope.project_id,
            'sender': scope.sender, 'recipient': scope.recipient, 'kind': 'request',
            'in_reply_to': None, 'expected_revision': 0,
            'authorization_ref': 'private-authority', 'budget_reservation_ref': reservation_ref,
            'payload': {name: getattr(self.binding, name)
                        for name in ('id', 'sha256', 'media_type', 'classification')},
            'created_at': '2026-11-17T11:00:00Z', 'expires_at': '2026-11-17T13:00:00Z',
        }
        digest = self.requests.put(json.dumps(request).encode('utf-8'))
        authorities = {(scope.principal, scope.project_id, scope.sender, scope.recipient,
            'private-authority', reservation_ref): dh.WorkerSecondsAuthority(
                self.envelope, True, NOW + timedelta(hours=1))}
        return self.receiver.reserve(self.requests, digest, authorities=authorities,
            payload_store=self.payloads, bindings={'object': self.binding}, now=NOW)

    def observe(self, retained, name, *, usage=None, stopped=False, cleanup=False):
        r = retained.reservation
        return self.receiver.record_usage_observation(name, request_id=r.request_id,
            budget_reservation_ref=r.budget_reservation_ref, request_sha256=r.request_sha256,
            expected_revision=1, worker_seconds=usage, execution_stopped=stopped,
            cleanup_known=cleanup, observed_at=NOW + timedelta(seconds=1))

    def sql(self, statement):
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute(statement)

    def state(self):
        with closing(sqlite3.connect(self.path)) as conn:
            return tuple(conn.iterdump())

    def test_k01_one_connected_report_header_digest_and_immutable_view(self):
        self.retain('request-a')
        with mock.patch.object(rc, 'build_recovery_report',
                               wraps=rc.build_recovery_report) as build:
            view = rc.render_recovery_console(self.receiver)
        self.assertEqual(build.call_count, 1)
        artifact = rr.build_recovery_report(self.receiver)
        lines = view.text.split('\n')
        self.assertEqual(lines[0], 'PRIVATE LOCAL RECOVERY CONSOLE - NOT AUTHORITY')
        self.assertEqual(view.report_sha256, artifact.sha256)
        self.assertNotEqual(view.report_sha256, sha256(view.text.encode()).hexdigest())
        self.assertIn('source_report_sha256=' + artifact.sha256 + ' entries=1', lines[1])
        self.assertEqual((view.entry_count, view.next_after_request_id), (1, None))
        entry = lines[3]
        self.assertIn('request="request-a" receipt="reservation_placeholder"'.replace(
            'reservation_placeholder', 'recorded') + '/rev1', entry)
        self.assertIn('outstanding_worker_seconds=20', entry)
        self.assertTrue(view.text.endswith('\n'))
        with self.assertRaises(FrozenInstanceError):
            view.text = 'forged'
        self.assertFalse(hasattr(view, '__dict__'))

    def test_k02_unknown_zero_known_stop_cleanup_and_ack_states(self):
        retained = {n: self.retain(n) for n in ('none', 'unknown', 'zero', 'known')}
        self.observe(retained['unknown'], 'obs-unknown')
        self.observe(retained['zero'], 'obs-zero', usage=0, stopped=True, cleanup=True)
        self.observe(retained['known'], 'obs-known', usage=7, stopped=True)
        event = self.receiver.inspect_reservation('zero').current_status.event
        self.receiver.acknowledge_status_event(event.event_id, expected_ack_revision=0,
                                               now=NOW + timedelta(seconds=9))
        lines = {l.split(' ')[0]: l for l in rc.render_recovery_console(
            self.receiver).text.split('\n')[3:] if l}
        none = lines['request="none"']
        self.assertIn('usage=UNKNOWN stop=unknown cleanup=unknown', none)
        self.assertIn('usage=UNKNOWN stop=false cleanup=false', lines['request="unknown"'])
        zero = lines['request="zero"']
        self.assertIn('usage=ZERO stop=true cleanup=true ack=acknowledged', zero)
        known = lines['request="known"']
        self.assertIn('usage=KNOWN:7 stop=true cleanup=false ack=pending', known)
        self.assertIn('usage_known_positive', known)
        for line in lines.values():
            self.assertIn('outstanding_worker_seconds=20', line)
        self.sql("DROP TRIGGER reservation_status_no_delete")
        self.sql("DELETE FROM reservation_status_events WHERE request_id='unknown' "
                 "AND receipt_revision=2")
        text = rc.render_recovery_console(self.receiver).text
        self.assertIn('ack=unknown', [l for l in text.split('\n') if 'request="unknown"' in l][0])

    def test_k03_untrusted_identifiers_are_escaped_to_printable_ascii(self):
        hostile = 'a\nb\x1b[31m\x7f"q"\\雪\r'
        self.retain(hostile)
        view = rc.render_recovery_console(self.receiver)
        text = view.text
        text.encode('ascii')
        self.assertTrue(all(c == '\n' or 0x20 <= ord(c) < 0x7f for c in text))
        for raw in ('\x1b', '\x7f', '\r', '雪'):
            self.assertNotIn(raw, text)
        self.assertIn('"a\\nb\\u001b[31m\\u007f\\"q\\"\\\\\\u96ea\\r"', text)
        self.assertEqual(len(text.split('\n')), 5)  # three header lines, one entry, trailing
        self.assertEqual(view.entry_count, 1)

    def test_k04_empty_pages_cursors_and_argument_failures(self):
        empty = rc.render_recovery_console(self.receiver)
        self.assertEqual((empty.entry_count, empty.next_after_request_id), (0, None))
        self.assertEqual(len(empty.text.split('\n')), 4)
        for name in ('request-c', 'request-a', 'request-b'):
            self.retain(name)
        first = rc.render_recovery_console(self.receiver, limit=2)
        self.assertEqual((first.entry_count, first.next_after_request_id), (2, 'request-b'))
        self.assertIn('next="request-b"', first.text)
        self.assertLess(first.text.index('request="request-a"'), first.text.index('request="request-b"'))
        last = rc.render_recovery_console(self.receiver, after_request_id='request-b', limit=2)
        self.assertEqual((last.entry_count, last.next_after_request_id), (1, None))
        self.assertIn('after="request-b" next=null', last.text)
        self.assertNotEqual(first.report_sha256, last.report_sha256)
        for kwargs in ({'limit': True}, {'limit': 0}, {'limit': 101}, {'after_request_id': ''}):
            with self.subTest(kwargs=kwargs), self.assertRaises((ValueError, TypeError)):
                rc.render_recovery_console(self.receiver, **kwargs)

    def test_k05_exact_output_limit_refuses_whole_view(self):
        self.retain()
        view = rc.render_recovery_console(self.receiver)
        exact = len(view.text)
        self.assertEqual(rc.render_recovery_console(self.receiver, max_output_bytes=exact), view)
        for bound in (1, exact - 1):
            result = None
            with self.assertRaises(rc.RecoveryConsoleTooLarge) as error:
                result = rc.render_recovery_console(self.receiver, max_output_bytes=bound)
            self.assertIsNone(result)
            self.assertEqual(error.exception.args, ('recovery console exceeds byte limit',))

        class Number(int):
            pass
        with mock.patch.object(rc, 'build_recovery_report') as build:
            for bound in (True, Number(10), 0, -1, 1.0, '10', None, rc.MAX_CONSOLE_BYTES + 1):
                with self.subTest(bound=bound), self.assertRaises(ValueError):
                    rc.render_recovery_console(self.receiver, max_output_bytes=bound)
            build.assert_not_called()
        self.assertEqual(len(rc.render_recovery_console(
            self.receiver, max_output_bytes=rc.MAX_CONSOLE_BYTES).text), exact)

    def test_k06_read_only_invariance_and_report_failures_return_nothing(self):
        self.retain('request-a')
        self.retain('request-b')
        before = self.state()
        files = {str(p.relative_to(self.root)): p.read_bytes()
                 for p in self.root.rglob('*') if p.is_file()}
        with mock.patch.object(dh.DurableHandoffReceipts, '__init__',
                               side_effect=AssertionError('never construct a receiver')), \
             mock.patch('builtins.open', side_effect=AssertionError('no console file writes')):
            self.assertEqual(rc.render_recovery_console(self.receiver).entry_count, 2)
        self.assertEqual(self.state(), before)
        self.assertEqual({str(p.relative_to(self.root)): p.read_bytes()
                          for p in self.root.rglob('*') if p.is_file()}, files)
        for candidate in (None, {}):
            with self.assertRaises(TypeError):
                rc.render_recovery_console(candidate)
        self.sql("UPDATE worker_seconds_reservations SET worker_seconds=19 "
                 "WHERE request_id='request-b'")
        corrupted = self.state()
        result = None
        with self.assertRaises(dh.ReceiptConflict):
            result = rc.render_recovery_console(self.receiver)
        self.assertIsNone(result)
        self.assertEqual(self.state(), corrupted)
        with mock.patch.object(rc, 'build_recovery_report', return_value=mock.Mock(
                data=b'not json', sha256='0' * 64, after_request_id=None,
                next_after_request_id=None, entry_count=0)):
            with self.assertRaises(ValueError):
                rc.render_recovery_console(self.receiver)

"""Q01-Q06: exactly six NEW self-contained tests, authored NOT EXECUTED.
Real private temporary BlobStore/SQLite fixtures; no historical test imports.
"""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from ai_agent_scientist.admission import durable_handoff as dh
from ai_agent_scientist.admission import recovery_console as rc
from ai_agent_scientist.admission import recovery_report as rr
from ai_agent_scientist.admission.handoff_binding import PayloadBinding
from ai_agent_scientist.evidence.blob_store import BlobStore

NOW = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)


class RecoveryQueueContracts(unittest.TestCase):
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

    def retain(self, rid):
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
        authorities = {(s.principal, s.project_id, s.sender, s.recipient,
            'private-authority', ref): dh.WorkerSecondsAuthority(
                self.envelope, True, NOW + timedelta(hours=1))}
        return self.receiver.reserve(self.requests, digest, authorities=authorities,
            payload_store=self.payloads, bindings={'object': self.binding}, now=NOW)

    def observe(self, retained, usage, stopped=False, cleanup=False):
        r = retained.reservation
        return self.receiver.record_usage_observation('obs-' + r.request_id,
            request_id=r.request_id, budget_reservation_ref=r.budget_reservation_ref,
            request_sha256=r.request_sha256, expected_revision=1, worker_seconds=usage,
            execution_stopped=stopped, cleanup_known=cleanup,
            observed_at=NOW + timedelta(seconds=1))

    def queue(self, *reasons, **kw):
        return rc.render_recovery_queue(self.receiver, reasons=reasons, **kw)

    def shown(self, view):
        return [l.split(chr(34))[1] for l in view.text.splitlines()
                if l.startswith('request=')]

    def state(self):
        with closing(sqlite3.connect(self.path)) as conn:
            return tuple(conn.iterdump())

    def files(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def test_q01_any_reason_filter_and_resume_cursor_not_last_displayed(self):
        a = self.retain('a')
        self.retain('b')
        self.retain('c')
        self.observe(a, 7)
        first = self.queue('usage_known_positive', page_limit=2, max_pages=1)
        self.assertEqual(self.shown(first), ['a'])
        self.assertEqual((first.inspected_count, first.displayed_count, first.pages_scanned),
                         (2, 1, 1))
        self.assertEqual((first.next_after_request_id, first.reached_end), ('b', False))
        self.assertEqual(first.source_report_sha256s,
                         (rr.build_recovery_report(self.receiver, limit=2).sha256,))
        second = self.queue('usage_known_positive', after_request_id='b',
                            page_limit=2, max_pages=1)
        self.assertEqual((second.inspected_count, second.displayed_count), (1, 0))
        self.assertEqual((second.next_after_request_id, second.reached_end), (None, True))
        both = self.queue('usage_known_positive', 'no_observation')
        self.assertEqual(self.shown(both), ['a', 'b', 'c'])

    def test_q02_no_matches_bounded_scan_with_continuation(self):
        for name in 'abc':
            self.retain(name)
        view = self.queue('observed_over_cap', page_limit=1, max_pages=2)
        self.assertEqual(self.shown(view), [])
        self.assertEqual((view.inspected_count, view.displayed_count, view.pages_scanned),
                         (2, 0, 2))
        self.assertEqual((view.next_after_request_id, view.reached_end), ('b', False))
        self.assertEqual(view.source_report_sha256s, (
            rr.build_recovery_report(self.receiver, limit=1).sha256,
            rr.build_recovery_report(self.receiver, after_request_id='a', limit=1).sha256))
        self.assertIn('separate read snapshot', view.text)

    def test_q03_empty_receiver_is_distinct_from_empty_filter(self):
        view = self.queue('usage_unknown')
        self.assertEqual((view.inspected_count, view.displayed_count, view.pages_scanned),
                         (0, 0, 1))
        self.assertEqual((view.next_after_request_id, view.reached_end), (None, True))
        self.assertEqual(len(view.source_report_sha256s), 1)
        self.assertEqual(view.text.splitlines()[0],
                         'PRIVATE LOCAL RECOVERY QUEUE - NOT AUTHORITY')
        self.assertIn('inspected=0 displayed=0', view.text)

    def test_q04_unknown_zero_and_over_cap_stay_distinct(self):
        self.retain('u')
        self.observe(self.retain('z'), 0, stopped=True, cleanup=True)
        self.observe(self.retain('o'), 99)
        unknown = self.queue('usage_unknown')
        self.assertEqual(self.shown(unknown), ['u'])
        self.assertIn('usage=UNKNOWN', unknown.text)
        zero = self.queue('usage_known_zero')
        self.assertEqual(self.shown(zero), ['z'])
        self.assertIn('usage=ZERO', zero.text)
        over = self.queue('observed_over_cap')
        self.assertEqual(self.shown(over), ['o'])
        self.assertIn('usage=KNOWN:99', over.text)
        self.assertNotIn('usage=ZERO', over.text)

    def test_q05_bounds_before_reads_and_failures_return_no_partial_view(self):
        ok = ('usage_unknown',)
        bad = [dict(reasons=()), dict(reasons=['usage_unknown']), dict(reasons=('nope',)),
               dict(reasons=ok * 2), dict(reasons=(1,)), dict(page_limit=True),
               dict(page_limit=0), dict(page_limit=101), dict(max_pages=0),
               dict(max_pages=11), dict(max_pages=True), dict(max_output_bytes=0),
               dict(max_output_bytes=rc.MAX_CONSOLE_BYTES + 1)]
        with mock.patch.object(rc, 'build_recovery_report') as build:
            for kw in bad:
                kw.setdefault('reasons', ok)
                with self.subTest(kw=kw), self.assertRaises(ValueError):
                    rc.render_recovery_queue(self.receiver, **kw)
            build.assert_not_called()
        for name in 'abc':
            self.retain(name)
        size = len(self.queue('no_observation').text)
        self.assertEqual(len(self.queue('no_observation', max_output_bytes=size).text), size)
        with self.assertRaises(rc.RecoveryConsoleTooLarge):
            self.queue('no_observation', max_output_bytes=size - 1)
        first = rr.build_recovery_report(self.receiver, limit=1)
        result = None
        with mock.patch.object(rc, 'build_recovery_report',
                               side_effect=[first, RuntimeError('later page')]):
            with self.assertRaises(RuntimeError):
                result = self.queue('no_observation', page_limit=1, max_pages=2)
        self.assertIsNone(result)
        stuck = mock.Mock(data=b'{"entries":[]}', sha256='0' * 64, entry_count=0,
                          next_after_request_id='x')
        with mock.patch.object(rc, 'build_recovery_report', return_value=stuck):
            with self.assertRaises(ValueError):
                self.queue('no_observation')

    def test_q06_read_only_invariance_and_exact_receiver(self):
        self.retain('a')
        self.retain('b')
        before, files = self.state(), self.files()
        with mock.patch.object(rc, 'build_recovery_report',
                               wraps=rc.build_recovery_report) as build, \
             mock.patch.object(dh.DurableHandoffReceipts, '__init__',
                               side_effect=AssertionError('no receiver construction')):
            view = self.queue('no_observation', page_limit=1, max_pages=2)
        self.assertEqual(build.call_count, view.pages_scanned)
        self.assertEqual(self.state(), before)
        self.assertEqual(self.files(), files)
        with self.assertRaises(AttributeError):
            view.text = 'forged'
        for candidate in (None, {}):
            with self.assertRaises(TypeError):
                rc.render_recovery_queue(candidate, reasons=('usage_unknown',))

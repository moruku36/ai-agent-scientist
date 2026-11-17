'''PRIVATE local operator workflow: queue -> selected detail -> explicit mark.

Authored NOT EXECUTED. Trusted in-process caller and receiver only. The detail
view is ONE actual inspect_recovery_triage call; the mark action is a separate
explicit call that delegates once to the existing receiver CAS. This module adds
no CLI, receiver construction, IO, clock, process, network, or tool use and does
not authenticate the caller, scope or history. Nothing here stops, cleans up,
releases, settles, authorizes, dispatches, retries or completes anything. See
docs/31-recovery-operator.md.
'''
from __future__ import annotations

from dataclasses import dataclass

from ai_agent_scientist.admission.durable_handoff import DurableHandoffReceipts, DurableReceipt
from ai_agent_scientist.admission.recovery_console import (
    MAX_CONSOLE_BYTES, RecoveryConsoleTooLarge, _bad, _cursor, _flag, _int, _line, _q)
from ai_agent_scientist.admission.recovery_report import _project
from ai_agent_scientist.admission.recovery_triage import inspect_recovery_triage

__all__ = ['RecoveryDetailView', 'RecoveryMarkRefused',
           'mark_recovery_for_reconciliation', 'render_recovery_detail']


class RecoveryMarkRefused(ValueError):
    '''Value-free refusal; nothing was written.'''


@dataclass(frozen=True, slots=True)
class RecoveryDetailView:
    '''Immutable private text. The identity fields are receipt identity, not
    report hashes and not authorization.'''

    text: str
    request_id: str
    request_sha256: str
    revision: int
    state: str


def _cap(value):
    if type(value) is not int or not 1 <= value <= MAX_CONSOLE_BYTES:
        raise ValueError('max_output_bytes must be an exact integer in 1..1048576')


def render_recovery_detail(receiver: DurableHandoffReceipts, request_id: str, *,
                           max_output_bytes: int = 65536) -> RecoveryDetailView | None:
    '''Render ONE selected request from ONE actual triage call, or None.

    None means missing or receipt-only (no reservation). Any request may be
    selected, including one outside a previously displayed queue page; the
    snapshot is independent of any earlier queue snapshot. Output is escaped
    printable ASCII bounded exactly by max_output_bytes (whole refusal, never
    truncated). Absent evidence prints UNKNOWN/unknown, never zero. No writes.
    '''
    _cap(max_output_bytes)
    report = inspect_recovery_triage(receiver, request_id)
    if report is None:
        return None
    try:
        entry = _project(report)
        r, v, a = entry['receipt'], entry['reservation'], entry['accounting']
        o, s = entry['latest_usage_observation'], entry['current_status']
        lines = [
            'PRIVATE LOCAL RECOVERY DETAIL - NOT AUTHORITY',
            'single read snapshot; selection fields are receipt identity, not report '
            'hashes or authorization; UNKNOWN is not zero; nothing here stops, releases, '
            'dispatches or settles budget',
            'request=%s revision=%d state=%s request_sha256=%s payload_sha256=%s' % (
                _q(r['request_id']), _int(r['revision']), _q(r['state']),
                _q(r['request_sha256']), _q(r['payload_sha256'])),
            'reservation_ref=%s reservation_request_sha256=%s reserved_worker_seconds=%d '
            'outstanding_worker_seconds=%d' % (
                _q(v['budget_reservation_ref']), _q(v['request_sha256']),
                _int(v['worker_seconds']), _int(a['outstanding_worker_seconds'])),
        ]
        if o is None:
            lines.append('observation=none (UNKNOWN) latest local insertion view only')
        else:
            seconds, over = o['worker_seconds'], o['over_cap']
            lines.append(
                'observation_id=%s sequence=%d observed_at=%s expected_revision=%d '
                'worker_seconds=%s execution_stopped=%s cleanup_known=%s over_cap=%s' % (
                    _q(o['observation_id']), _int(o['sequence']), _q(o['observed_at']),
                    _int(o['expected_revision']),
                    'UNKNOWN' if seconds is None else '%d' % _int(seconds),
                    _flag(o['execution_stopped']), _flag(o['cleanup_known']),
                    'unknown' if over is None else _flag(over)))
        if s is None:
            lines.append('status_event=none ack=unknown')
        else:
            ev = s['event']
            lines.append(
                'event_id=%d receipt_revision=%d event_status=%s event_at=%s '
                'ack_revision=%d acknowledged_at=%s' % (
                    _int(ev['event_id']), _int(ev['receipt_revision']), _q(ev['status']),
                    _q(ev['created_at']), _int(s['ack_revision']),
                    _cursor(s['acknowledged_at'])))
        lines.append('summary ' + _line(entry))
        identity = (r['request_id'], r['request_sha256'], r['revision'], r['state'])
    except (KeyError, TypeError, ValueError, AttributeError):
        _bad()
    text = '\n'.join(lines) + '\n'
    if len(text) > max_output_bytes:  # ASCII only: characters equal bytes
        raise RecoveryConsoleTooLarge('recovery detail exceeds byte limit') from None
    return RecoveryDetailView(text, *identity)


def mark_recovery_for_reconciliation(receiver: DurableHandoffReceipts, *, request_id: str,
                                     expected_request_sha256: str, expected_revision: int,
                                     now) -> DurableReceipt:
    '''EXPLICIT trusted-caller action: recorded -> reconciliation_required.

    Never called by queue or detail rendering. Digest and revision types are
    validated before any read. One inspect_recovery_triage call must show an
    existing reservation, the exact request digest, the expected revision and
    state recorded; otherwise RecoveryMarkRefused (value-free, nothing written).
    Then exactly ONE receiver.require_reconciliation delegation provides the
    atomic CAS and time validation. Inspection and CAS are separate
    transactions: a concurrent change fails through the existing CAS. Already
    required reconciliation is a refusal, not replay success. now is injected.
    No reservation, budget, acknowledgment or observation write is added.
    '''
    digest = expected_request_sha256
    if type(digest) is not str or len(digest) != 64 or any(
            c not in '0123456789abcdef' for c in digest):
        raise ValueError('expected_request_sha256 must be 64 lowercase hex characters')
    if type(expected_revision) is not int or expected_revision < 1:
        raise ValueError('expected_revision must be an exact positive integer')
    report = inspect_recovery_triage(receiver, request_id)
    if report is None:
        raise RecoveryMarkRefused('recovery mark refused') from None
    receipt = report.snapshot.receipt
    if (receipt.request_id != request_id or receipt.request_sha256 != digest
            or receipt.revision != expected_revision or receipt.state != 'recorded'):
        raise RecoveryMarkRefused('recovery mark refused') from None
    return receiver.require_reconciliation(
        request_id, expected_revision=expected_revision, now=now)

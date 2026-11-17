"""PRIVATE local operator console text, not proof, authority or wire format.

Authored NOT EXECUTED. Trusted in-process caller and receiver only. Each page read
is ONE connected build_recovery_report call; this module adds no CLI, receiver
construction, IO, clock, process, network or tool use. The report digest
describes the SOURCE report bytes, never the rendered text. Nothing here infers
release, settlement or live process truth. See docs/29-recovery-console.md and
docs/30-recovery-queue.md (reason-filtered bounded operator queue).
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from ai_agent_scientist.admission.durable_handoff import DurableHandoffReceipts
from ai_agent_scientist.admission.recovery_report import MAX_OUTPUT_BYTES, build_recovery_report

__all__ = ['ConsoleView', 'KNOWN_TRIAGE_REASONS', 'MAX_CONSOLE_BYTES',
           'RecoveryConsoleTooLarge', 'RecoveryQueueView',
           'render_recovery_console', 'render_recovery_queue']

MAX_CONSOLE_BYTES = 1_048_576

# Exact conservative reason codes produced by recovery_triage.classify_reservation.
KNOWN_TRIAGE_REASONS = frozenset((
    'reservation_fully_outstanding', 'receipt_recorded',
    'receipt_reconciliation_required', 'current_status_missing',
    'local_ack_unknown', 'local_ack_pending', 'local_acknowledged',
    'no_observation', 'usage_unknown', 'execution_not_independently_stopped',
    'cleanup_unknown', 'latest_insertion_view_only', 'usage_known_zero',
    'usage_known_positive', 'observed_over_cap'))


class RecoveryConsoleTooLarge(ValueError):
    """Whole view refused; no partial text is returned."""


@dataclass(frozen=True, slots=True)
class ConsoleView:
    """Immutable private text; report_sha256 is the SOURCE report digest."""

    text: str
    report_sha256: str
    entry_count: int
    next_after_request_id: str | None


@dataclass(frozen=True, slots=True)
class RecoveryQueueView:
    """Immutable private queue text; digests are SOURCE report digests per page.

    next_after_request_id is the last SCANNED page cursor, never the last
    displayed request. reached_end only means the last observed page had no next.
    """

    text: str
    source_report_sha256s: tuple[str, ...]
    inspected_count: int
    displayed_count: int
    pages_scanned: int
    next_after_request_id: str | None
    reached_end: bool


def _bad():
    raise ValueError('invalid recovery report') from None


def _q(value):
    # JSON string with ASCII escapes; json leaves DEL raw, so escape it too.
    if type(value) is not str:
        _bad()
    return json.dumps(value, ensure_ascii=True).replace('\x7f', '\\u007f')


def _cursor(value):
    return 'null' if value is None else _q(value)


def _int(value):
    if type(value) is not int:
        _bad()
    return value


def _flag(value):
    if type(value) is not bool:
        _bad()
    return 'true' if value else 'false'


def _line(entry):
    receipt, accounting = entry['receipt'], entry['accounting']
    status, observation = entry['current_status'], entry['latest_usage_observation']
    if observation is None:
        usage, stop, cleanup = 'UNKNOWN', 'unknown', 'unknown'
    else:
        seconds = observation['worker_seconds']
        if seconds is None:
            usage = 'UNKNOWN'
        else:
            usage = 'ZERO' if _int(seconds) == 0 else 'KNOWN:%d' % seconds
        stop = _flag(observation['execution_stopped'])
        cleanup = _flag(observation['cleanup_known'])
    if status is None:
        ack = 'unknown'
    elif _int(status['ack_revision']) == 0:
        ack = 'pending'
    elif status['ack_revision'] == 1:
        ack = 'acknowledged'
    else:
        _bad()
    reasons = entry['reasons']
    if type(reasons) is not list:
        _bad()
    return ('request=%s receipt=%s/rev%d outstanding_worker_seconds=%d usage=%s '
            'stop=%s cleanup=%s ack=%s reasons=[%s]' % (
                _q(receipt['request_id']), _q(receipt['state']), _int(receipt['revision']),
                _int(accounting['outstanding_worker_seconds']), usage, stop, cleanup,
                ack, ','.join(_q(r) for r in reasons)))


def render_recovery_console(receiver: DurableHandoffReceipts, *,
                            after_request_id: str | None = None, limit: int = 100,
                            max_output_bytes: int = 65536) -> ConsoleView:
    """Render ONE actual recovery report page as deterministic printable ASCII.

    Exact builtin max_output_bytes in 1..1048576 bounds the finished text; the
    whole view is refused, never truncated. Usage/stop/cleanup/ack show UNKNOWN or
    unknown when retained evidence is absent; UNKNOWN is never zero. Pages are
    independent read snapshots. Errors from the connected report propagate.
    """
    if type(max_output_bytes) is not int or not 1 <= max_output_bytes <= MAX_CONSOLE_BYTES:
        raise ValueError('max_output_bytes must be an exact integer in 1..1048576')
    artifact = build_recovery_report(receiver, after_request_id=after_request_id,
                                     limit=limit, max_output_bytes=MAX_OUTPUT_BYTES)
    try:
        entries = json.loads(artifact.data)['entries']
        if type(entries) is not list or len(entries) != artifact.entry_count:
            _bad()
        lines = [
            'PRIVATE LOCAL RECOVERY CONSOLE - NOT AUTHORITY',
            'source_report_sha256=%s entries=%d after=%s next=%s' % (
                artifact.sha256, artifact.entry_count, _cursor(artifact.after_request_id),
                _cursor(artifact.next_after_request_id)),
            'single page snapshot; UNKNOWN is not zero; nothing here releases or settles budget',
        ]
        lines.extend(_line(entry) for entry in entries)
    except (KeyError, TypeError, ValueError, AttributeError):
        _bad()
    text = '\n'.join(lines) + '\n'
    if len(text) > max_output_bytes:  # ASCII only: characters equal bytes
        raise RecoveryConsoleTooLarge('recovery console exceeds byte limit') from None
    return ConsoleView(text, artifact.sha256, artifact.entry_count,
                       artifact.next_after_request_id)


def _wanted(reasons):
    message = 'reasons must be a nonempty tuple of unique known triage reason codes'
    if type(reasons) is not tuple or not reasons:
        raise ValueError(message)
    for reason in reasons:
        if type(reason) is not str or reason not in KNOWN_TRIAGE_REASONS:
            raise ValueError(message)
    if len(set(reasons)) != len(reasons):
        raise ValueError(message)
    return frozenset(reasons)


def _digest(value):
    if type(value) is not str or len(value) != 64 or any(
            c not in '0123456789abcdef' for c in value):
        _bad()
    return value


def render_recovery_queue(receiver: DurableHandoffReceipts, *, reasons: tuple[str, ...],
                          after_request_id: str | None = None, page_limit: int = 100,
                          max_pages: int = 5, max_output_bytes: int = 65536
                          ) -> RecoveryQueueView:
    """Scan at most max_pages ACTUAL report pages; show entries with ANY reason.

    reasons: nonempty tuple of unique exact known triage reason codes. Arguments
    are validated before any read. Each page is one connected
    build_recovery_report call and an independent read snapshot: no cross-page
    consistency, no aggregate accounting or free budget, no writes or release.
    Scanning stops at max_pages even without matches; the resume cursor is the
    last scanned page cursor, never the last displayed request. An empty filtered
    result is not an empty receiver. reached_end only describes the last observed
    page. Any later page failure, forward-progress violation or byte overflow
    fails the whole call; no partial view is returned.
    """
    wanted = _wanted(reasons)
    if type(page_limit) is not int or not 1 <= page_limit <= 100:
        raise ValueError('page_limit must be an exact integer in 1..100')
    if type(max_pages) is not int or not 1 <= max_pages <= 10:
        raise ValueError('max_pages must be an exact integer in 1..10')
    if type(max_output_bytes) is not int or not 1 <= max_output_bytes <= MAX_CONSOLE_BYTES:
        raise ValueError('max_output_bytes must be an exact integer in 1..1048576')
    cursor, digests, shown, inspected, reached_end = after_request_id, [], [], 0, False
    for _ in range(max_pages):
        artifact = build_recovery_report(receiver, after_request_id=cursor,
                                         limit=page_limit, max_output_bytes=MAX_OUTPUT_BYTES)
        try:
            entries = json.loads(artifact.data)['entries']
            if type(entries) is not list or len(entries) != artifact.entry_count:
                _bad()
            following = artifact.next_after_request_id
            if following is not None:
                if type(following) is not str or not entries:
                    _bad()
                if cursor is not None and following.encode('utf-8') <= cursor.encode('utf-8'):
                    _bad()  # cursor must strictly advance
            digests.append(_digest(artifact.sha256))
            for entry in entries:
                found = entry['reasons']
                if type(found) is not list:
                    _bad()
                inspected += 1
                if any(r in wanted for r in found):
                    shown.append(_line(entry))
        except (KeyError, TypeError, ValueError, AttributeError):
            _bad()
        if following is None:
            reached_end = True
            break
        cursor = following
    resume = None if reached_end else cursor
    lines = [
        'PRIVATE LOCAL RECOVERY QUEUE - NOT AUTHORITY',
        'reasons=[%s] pages=%d inspected=%d displayed=%d after=%s next=%s reached_end=%s' % (
            ','.join(_q(r) for r in reasons), len(digests), inspected, len(shown),
            _cursor(after_request_id), _cursor(resume), 'true' if reached_end else 'false'),
        'each page is a separate read snapshot; no cross-page consistency, no aggregate '
        'accounting; reached_end covers only the last observed page; UNKNOWN is not zero; '
        'nothing here releases, dispatches or settles budget',
    ]
    lines.extend('page=%d source_report_sha256=%s' % (i, d) for i, d in enumerate(digests, 1))
    lines.extend(shown)
    text = '\n'.join(lines) + '\n'
    if len(text) > max_output_bytes:
        raise RecoveryConsoleTooLarge('recovery queue exceeds byte limit') from None
    return RecoveryQueueView(text, tuple(digests), inspected, len(shown), len(digests),
                             resume, reached_end)

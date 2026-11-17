"""PRIVATE local operator console text, not proof, authority or wire format.

Authored NOT EXECUTED. Trusted in-process caller and receiver only. The sole
read is ONE connected build_recovery_report call; this module adds no CLI,
receiver construction, IO, clock, process, network or tool use. The report digest
describes the SOURCE report bytes, never the rendered text. Nothing here infers
release, settlement or live process truth. See docs/29-recovery-console.md.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from ai_agent_scientist.admission.durable_handoff import DurableHandoffReceipts
from ai_agent_scientist.admission.recovery_report import MAX_OUTPUT_BYTES, build_recovery_report

__all__ = ['ConsoleView', 'MAX_CONSOLE_BYTES', 'RecoveryConsoleTooLarge',
           'render_recovery_console']

MAX_CONSOLE_BYTES = 1_048_576


class RecoveryConsoleTooLarge(ValueError):
    """Whole view refused; no partial text is returned."""


@dataclass(frozen=True, slots=True)
class ConsoleView:
    """Immutable private text; report_sha256 is the SOURCE report digest."""

    text: str
    report_sha256: str
    entry_count: int
    next_after_request_id: str | None


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

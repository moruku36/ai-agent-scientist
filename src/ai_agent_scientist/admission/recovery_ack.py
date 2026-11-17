"""Explicit trusted-caller acknowledgement of a freshly selected local event.

Authored, NOT EXECUTED. One actual triage inspection precedes one existing
event-ack CAS; these are separate transactions. The returned LocalStatusEntry
identifies the ACKED EVENT only, which may already have ceased to be current.
No receiver construction, clock sampling, retries, delivery or settlement.
See docs/34-recovery-ack.md for the race and private receiver trust boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ai_agent_scientist.admission.durable_handoff import (
    DurableHandoffReceipts, LocalStatusEntry,
)
from ai_agent_scientist.admission.recovery_triage import inspect_recovery_triage

__all__ = ['RecoveryAckRefused', 'RecoveryStatusSelection',
           'select_current_recovery_status', 'acknowledge_current_recovery_status']

_MAX_INT = (1 << 63) - 1


class RecoveryAckRefused(ValueError):
    """Value-free selection/input refusal before delegating any write."""


@dataclass(frozen=True, slots=True)
class RecoveryStatusSelection:
    """Read snapshot identity, freely constructible and never a capability.

    event_id is local to the independently trusted receiver's database. This
    value authenticates neither the caller nor the receiver nor stored history.
    """

    request_id: str
    request_sha256: str
    receipt_revision: int
    event_id: int
    event_receipt_revision: int
    ack_revision: int


def _refuse() -> None:
    raise RecoveryAckRefused('recovery acknowledgement refused') from None


def _request_id(value: object) -> None:
    if type(value) is not str or not 1 <= len(value) <= 1024 or '\x00' in value:
        _refuse()
    try:
        size = len(value.encode('utf-8'))
    except UnicodeError:
        _refuse()
    if size > 1024:
        _refuse()


def _integer(value: object, minimum: int) -> None:
    if type(value) is not int or not minimum <= value <= _MAX_INT:
        _refuse()


def select_current_recovery_status(receiver: DurableHandoffReceipts,
                                   request_id: str) -> RecoveryStatusSelection | None:
    """Read ONE actual selected triage view; no writes or fallback to old events.

    Missing/receipt-only/current-status-missing returns None. Already acked
    events remain visible with ack_revision=1. Actual triage enforces the exact
    concrete receiver and scope and validates all receipt/reservation/event
    bindings. Receiver/triage failures propagate without retry or translation.
    """
    _request_id(request_id)
    report = inspect_recovery_triage(receiver, request_id)
    if report is None or report.snapshot.current_status is None:
        return None
    receipt, status = report.snapshot.receipt, report.snapshot.current_status
    return RecoveryStatusSelection(
        receipt.request_id, receipt.request_sha256, receipt.revision,
        status.event.event_id, status.event.receipt_revision, status.ack_revision)


def acknowledge_current_recovery_status(
        receiver: DurableHandoffReceipts, *, request_id: str,
        expected_request_sha256: str, expected_receipt_revision: int,
        expected_event_id: int, expected_ack_revision: int,
        now: datetime) -> LocalStatusEntry:
    """EXPLICIT trusted-caller action; selection objects grant no authority.

    Validate exact scalar identity types/bounds before any read, then select
    once through actual triage. Bind request/digest/receipt revision/current
    event ID/event receipt revision/pending ack revision 0 before delegating
    ONCE to receiver.acknowledge_status_event. Stale/forged/missing/already
    acked selections refuse value-free before delegation. No arbitrary old
    event may be chosen merely because it remains pending.

    The separate event CAS fences only that event's ack revision. A competing
    ack fails there; a new receipt/event after inspection can instead leave
    the OLD event acknowledged and the NEW current event pending. The result
    identifies the ACKED EVENT, NOT current state, delivery or settlement.
    now is passed unchanged to existing receiver clock validation. All delegated
    errors propagate; no retry, construction, post-read or budget write.
    """
    _request_id(request_id)
    digest = expected_request_sha256
    if (type(digest) is not str or len(digest) != 64
            or any(c not in '0123456789abcdef' for c in digest)):
        _refuse()
    _integer(expected_receipt_revision, 1)
    _integer(expected_event_id, 1)
    _integer(expected_ack_revision, 0)
    if expected_ack_revision != 0:
        _refuse()

    selected = select_current_recovery_status(receiver, request_id)
    if selected is None or (
            selected.request_id, selected.request_sha256, selected.receipt_revision,
            selected.event_id, selected.event_receipt_revision, selected.ack_revision
    ) != (request_id, digest, expected_receipt_revision, expected_event_id,
          expected_receipt_revision, 0):
        _refuse()
    return receiver.acknowledge_status_event(
        selected.event_id, expected_ack_revision=expected_ack_revision, now=now)

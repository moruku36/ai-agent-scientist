"""Private, bounded local outcome inspection after an uncertain response.

Scientist25: authored, NOT EXECUTED. Each API composes ONE actual selected
history transaction and pure triage validation. No action, retry, clock or
receiver construction. Matching state is not causal proof or replay authority.
See docs/36-recovery-outcome.md for the independently trusted receiver boundary.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ai_agent_scientist.admission.durable_handoff import (
    DurableHandoffReceipts, LocalStatusEntry, ReservationSnapshot,
)
from ai_agent_scientist.admission.recovery_ack import RecoveryStatusSelection
from ai_agent_scientist.admission.recovery_preview import ReconciliationPreview
from ai_agent_scientist.admission.recovery_triage import classify_reservation

__all__ = ['RecoveryActionOutcome', 'RecoveryOutcomeRefused',
           'inspect_reconciliation_outcome', 'inspect_acknowledgement_outcome']

_MAX_INT = (1 << 63) - 1
_MAX_BYTES = 1048576
_HEX = '0123456789abcdef'


class RecoveryOutcomeRefused(ValueError):
    """Value-free malformed-intent or selected-identity refusal; no view."""


@dataclass(frozen=True, slots=True)
class RecoveryActionOutcome:
    """A local observation, freely constructible and never a capability.

    target_status is the exact sought historical entry, or None. The current
    flag compares the intended event ID to this snapshot's current event ID;
    None means no current event (or no event target for reconciliation).
    No field establishes execution success, delivery, settlement or safe replay.
    """

    action: str
    classification: str
    request_id: str
    request_sha256: str
    snapshot: ReservationSnapshot | None
    target_status: LocalStatusEntry | None
    target_event_is_current: bool | None


def _refuse() -> None:
    raise RecoveryOutcomeRefused('recovery outcome refused') from None


def _receiver(receiver: DurableHandoffReceipts) -> None:
    if type(receiver) is not DurableHandoffReceipts:
        raise TypeError('receiver must be an exact DurableHandoffReceipts')


def _request_id(value: object) -> None:
    if type(value) is not str or not 1 <= len(value) <= 1024 or '\x00' in value:
        _refuse()
    try:
        size = len(value.encode('utf-8'))
    except UnicodeError:
        _refuse()
    if size > 1024:
        _refuse()


def _digest(value: object) -> None:
    if (type(value) is not str or len(value) != 64
            or any(c not in _HEX for c in value)):
        _refuse()


def _preview(preview: ReconciliationPreview) -> None:
    if type(preview) is not ReconciliationPreview:
        _refuse()
    if type(preview.data) is not bytes or not 1 <= len(preview.data) <= _MAX_BYTES:
        _refuse()
    _digest(preview.sha256)
    if preview.sha256 != hashlib.sha256(preview.data).hexdigest():
        _refuse()
    _request_id(preview.request_id)
    _digest(preview.request_sha256)
    if type(preview.expected_revision) is not int or preview.expected_revision != 1:
        _refuse()


def _selection(selection: RecoveryStatusSelection) -> None:
    if type(selection) is not RecoveryStatusSelection:
        _refuse()
    _request_id(selection.request_id)
    _digest(selection.request_sha256)
    if (type(selection.receipt_revision) is not int
            or selection.receipt_revision not in (1, 2)
            or type(selection.event_id) is not int
            or not 1 <= selection.event_id <= _MAX_INT
            or type(selection.event_receipt_revision) is not int
            or selection.event_receipt_revision != selection.receipt_revision
            or type(selection.ack_revision) is not int
            or selection.ack_revision != 0):
        _refuse()


def _history(receiver, request_id, request_sha256, after_event_id):
    # The only storage read. Do not use an independently inspected snapshot,
    # the global event feed, a preview rebuild or action delegation here.
    history = receiver.inspect_reservation_status_history(
        request_id, after_event_id=after_event_id, limit=1)
    if history is not None:
        snapshot = history.snapshot
        classify_reservation(snapshot, scope=receiver._scope)
        if (snapshot.receipt.request_id != request_id
                or snapshot.receipt.request_sha256 != request_sha256):
            _refuse()
    return history


def inspect_reconciliation_outcome(
        receiver: DurableHandoffReceipts,
        preview: ReconciliationPreview) -> RecoveryActionOutcome:
    """Observe matching recorded/advanced state in ONE read transaction.

    Validate shape and exact-byte hash before reading; never parse supplied
    bytes or compare the full preview to a rebuild. Revision 2 may result from
    a usage observation or another caller, not this attempted application.
    Recorded state is NOT proof that replay is safe. Errors propagate unchanged.
    """
    _receiver(receiver)
    _preview(preview)
    history = _history(receiver, preview.request_id, preview.request_sha256, 0)
    snapshot = None if history is None else history.snapshot
    classification = ('missing_or_receipt_only' if snapshot is None else
                      'receipt_still_recorded' if snapshot.receipt.revision == 1 else
                      'reconciliation_transition_observed')
    return RecoveryActionOutcome(
        'mark_reconciliation_required', classification,
        preview.request_id, preview.request_sha256, snapshot, None, None)


def inspect_acknowledgement_outcome(
        receiver: DurableHandoffReceipts,
        selection: RecoveryStatusSelection) -> RecoveryActionOutcome:
    """Seek the original PENDING intent's event in ONE actual history read.

    An already-acked selection is not an unspent intent. Only the exact event
    ID AND intended receipt revision can supply its ack outcome. Later events
    are never borrowed. A local ack is never remote delivery. The current
    distinction uses this SAME snapshot, which can already be superseded.
    No exception is converted to a view, retried or used to dispatch an action.
    """
    _receiver(receiver)
    _selection(selection)
    history = _history(receiver, selection.request_id, selection.request_sha256,
                       selection.event_id - 1)
    snapshot = None if history is None else history.snapshot
    target = None
    is_current = None
    classification = 'missing_or_receipt_only'
    if history is not None:
        current = snapshot.current_status
        if current is not None:
            is_current = current.event.event_id == selection.event_id
        classification = 'target_event_not_found'
        if history.entries:
            entry = history.entries[0]
            if (entry.event.event_id == selection.event_id
                    and entry.event.receipt_revision == selection.event_receipt_revision):
                target = entry
                classification = ('target_ack_pending' if entry.ack_revision == 0
                                  else 'target_ack_retained')
    return RecoveryActionOutcome(
        'acknowledge_status_event', classification,
        selection.request_id, selection.request_sha256, snapshot, target, is_current)

"""Conservative retained-evidence triage; no recovery or budget authority.

Authoring status: NOT EXECUTED; coordinator checks remain pending.
Pure classification validates structure/binding, not provenance or truth. The
connected functions consume actual receiver snapshots in one existing read
transaction per call. See docs/27-recovery-triage.md. No clock is sampled.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ai_agent_scientist.admission.durable_handoff import (
    DurableHandoffReceipts, DurableReceipt, DurableReservation, LocalStatusEntry,
    LocalStatusEvent, LocalUsageObservation, ReservationAccounting,
    ReservationSnapshot, ReservationSnapshotPage, TrustedHandoffScope,
)

__all__ = ['InvalidRecoverySnapshot', 'RecoveryTriageReport', 'RecoveryTriagePage',
           'classify_reservation', 'inspect_recovery_triage', 'inspect_recovery_triages']

_MAX_INT = (1 << 63) - 1
_ROLES = ('scientist', 'ctf', 'sleep', 'evaluator')


class InvalidRecoverySnapshot(ValueError):
    """Value-free refusal of malformed or internally inconsistent evidence."""


@dataclass(frozen=True, slots=True)
class RecoveryTriageReport:
    """API-produced bounded reasons plus the entire original reservation view.

    Every report retains snapshot.accounting.outstanding_worker_seconds equal
    to snapshot.reservation.worker_seconds. No disposition or action is granted.
    """

    snapshot: ReservationSnapshot
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RecoveryTriagePage:
    """At most 100 reports from ONE receiver page; no aggregate accounting."""

    entries: tuple[RecoveryTriageReport, ...]
    next_after_request_id: str | None


def _require(condition: bool) -> None:
    if not condition:
        raise InvalidRecoverySnapshot('invalid recovery snapshot') from None


def _identifier(value: object) -> None:
    _require(type(value) is str)
    _require(0 < len(value) <= 1024 and '\x00' not in value)
    try:
        size = len(value.encode('utf-8'))
    except UnicodeError:
        raise InvalidRecoverySnapshot('invalid recovery snapshot') from None
    _require(size <= 1024)


def _integer(value: object, minimum: int = 0) -> None:
    _require(type(value) is int)
    _require(minimum <= value <= _MAX_INT)


def _digest(value: object) -> None:
    _require(type(value) is str)
    _require(len(value) == 64 and all(c in '0123456789abcdef' for c in value))


def _stamp(value: object) -> None:
    _require(type(value) is str)
    _require(len(value) == 27 and value.endswith('Z'))
    try:
        parsed = datetime.fromisoformat(value[:-1] + '+00:00')
    except ValueError:
        raise InvalidRecoverySnapshot('invalid recovery snapshot') from None
    _require(parsed.tzinfo is timezone.utc and
             parsed.isoformat(timespec='microseconds').replace('+00:00', 'Z') == value)


def _scope(scope: TrustedHandoffScope) -> None:
    _require(type(scope) is TrustedHandoffScope)
    for value in (scope.principal, scope.project_id, scope.sender, scope.recipient):
        _identifier(value)
    _require(scope.sender in _ROLES and scope.recipient in _ROLES)


def _identity(value: object) -> tuple:
    # Only called after the exact dataclass type has been checked.
    parts = (value.principal, value.project_id, value.recipient,
             value.request_id, value.sender)
    for part in parts:
        _identifier(part)
    _require(value.sender in _ROLES and value.recipient in _ROLES)
    _digest(value.request_sha256)
    return (*parts, value.request_sha256)


def _validate(snapshot: ReservationSnapshot, scope: TrustedHandoffScope) -> None:
    _scope(scope)
    _require(type(snapshot) is ReservationSnapshot)
    receipt, reservation, accounting = snapshot.receipt, snapshot.reservation, snapshot.accounting
    _require(type(receipt) is DurableReceipt)
    _require(type(reservation) is DurableReservation)
    _require(type(accounting) is ReservationAccounting)
    receipt_key = _identity(receipt)
    reservation_key = _identity(reservation)
    _require(receipt_key == reservation_key)
    _require(receipt_key[:3] == (scope.principal, scope.project_id, scope.recipient)
             and receipt.sender == scope.sender)
    _identifier(receipt.message_id)
    _digest(receipt.payload_sha256)
    _integer(receipt.revision, 1)
    _require(type(receipt.state) is str)
    _require((receipt.revision, receipt.state) in
             ((1, 'recorded'), (2, 'reconciliation_required')))
    _stamp(receipt.recorded_at)
    _stamp(receipt.updated_at)
    _require(receipt.updated_at >= receipt.recorded_at)
    if receipt.revision == 1:
        _require(receipt.updated_at == receipt.recorded_at)
    _identifier(reservation.budget_reservation_ref)
    _identifier(reservation.authorization_ref)
    _integer(reservation.worker_seconds, 1)
    _stamp(reservation.recorded_at)
    _integer(accounting.allocation_worker_seconds, 1)
    _integer(accounting.outstanding_worker_seconds, 1)
    _require(accounting.allocation_worker_seconds == reservation.worker_seconds ==
             accounting.outstanding_worker_seconds)

    status = snapshot.current_status
    if status is not None:
        _require(type(status) is LocalStatusEntry)
        event = status.event
        _require(type(event) is LocalStatusEvent)
        event_key = _identity(event)
        _require(event_key == reservation_key)
        _integer(event.event_id, 1)
        _identifier(event.budget_reservation_ref)
        _integer(event.receipt_revision, 1)
        _integer(event.worker_seconds, 1)
        _require(type(event.status) is str)
        expected_status = ('reservation_retained' if receipt.revision == 1
                           else 'reconciliation_required')
        _require(event.budget_reservation_ref == reservation.budget_reservation_ref
                 and event.receipt_revision == receipt.revision
                 and event.status == expected_status
                 and event.worker_seconds == reservation.worker_seconds)
        _stamp(event.created_at)
        _integer(status.ack_revision)
        _require(status.ack_revision in (0, 1))
        if status.ack_revision == 0:
            _require(status.acknowledged_at is None)
        else:
            _stamp(status.acknowledged_at)
            _require(status.acknowledged_at >= event.created_at)

    observation = snapshot.latest_usage_observation
    if observation is not None:
        _require(type(observation) is LocalUsageObservation)
        observation_key = _identity(observation)
        _require(observation_key == reservation_key)
        _integer(observation.sequence, 1)
        _identifier(observation.observation_id)
        _identifier(observation.budget_reservation_ref)
        _integer(observation.expected_revision, 1)
        _require(observation.expected_revision in (1, 2))
        _require(observation.budget_reservation_ref == reservation.budget_reservation_ref
                 and receipt.revision == 2)
        _require(type(observation.execution_stopped) is bool)
        _require(type(observation.cleanup_known) is bool)
        _stamp(observation.observed_at)
        _require(observation.observed_at >= receipt.updated_at)
        if observation.expected_revision == 1:
            # A revision-1 observation itself creates revision 2 at this stamp.
            _require(observation.observed_at == receipt.updated_at)
        if observation.worker_seconds is None:
            _require(observation.over_cap is None)
        else:
            _integer(observation.worker_seconds)
            _require(type(observation.over_cap) is bool)
            _require(observation.over_cap ==
                     (observation.worker_seconds > reservation.worker_seconds))


def classify_reservation(snapshot: ReservationSnapshot, *,
                         scope: TrustedHandoffScope) -> RecoveryTriageReport:
    """Pure deterministic validation/classification of one retained snapshot.

    Exact types and internal bindings cannot authenticate a consistently forged
    snapshot. Supply independently trusted scope/evidence. UNKNOWN is not zero.
    Latest insertion is only a view, never newest truth or a cumulative meter.
    """
    _validate(snapshot, scope)
    reasons = ['reservation_fully_outstanding',
               'receipt_recorded' if snapshot.receipt.revision == 1
               else 'receipt_reconciliation_required']
    status = snapshot.current_status
    if status is None:
        reasons.extend(('current_status_missing', 'local_ack_unknown'))
    else:
        reasons.append('local_ack_pending' if status.ack_revision == 0
                       else 'local_acknowledged')
    observation = snapshot.latest_usage_observation
    if observation is None:
        reasons.extend(('no_observation', 'usage_unknown',
                        'execution_not_independently_stopped', 'cleanup_unknown'))
    else:
        reasons.append('latest_insertion_view_only')
        if observation.worker_seconds is None:
            reasons.append('usage_unknown')
        else:
            reasons.append('usage_known_zero' if observation.worker_seconds == 0
                           else 'usage_known_positive')
        if not observation.execution_stopped:
            reasons.append('execution_not_independently_stopped')
        if not observation.cleanup_known:
            reasons.append('cleanup_unknown')
        if observation.over_cap is True:
            reasons.append('observed_over_cap')
    return RecoveryTriageReport(snapshot, tuple(reasons))


def _receiver(receiver: DurableHandoffReceipts) -> TrustedHandoffScope:
    # Deliberately concrete, not duck-typed candidate reports or an adapter.
    if type(receiver) is not DurableHandoffReceipts:
        raise TypeError('receiver must be an exact DurableHandoffReceipts')
    scope = receiver._scope
    _scope(scope)
    return scope


def inspect_recovery_triage(receiver: DurableHandoffReceipts,
                            request_id: str) -> RecoveryTriageReport | None:
    """Compose one actual receiver inspection; missing/receipt-only is None.

    Existing receiver failures propagate. There are no writes or second reads.
    """
    scope = _receiver(receiver)
    _identifier(request_id)
    snapshot = receiver.inspect_reservation(request_id)
    if snapshot is None:
        return None
    report = classify_reservation(snapshot, scope=scope)
    _require(report.snapshot.reservation.request_id == request_id)
    return report


def inspect_recovery_triages(receiver: DurableHandoffReceipts, *,
                             after_request_id: str | None = None,
                             limit: int = 100) -> RecoveryTriagePage:
    """Classify ONE actual bounded page atomically as a returned value.

    Pages/calls are independent SQLite views, not a frozen multi-page scan.
    Later validation failure returns no partial report. No sums are computed.
    """
    scope = _receiver(receiver)
    if after_request_id is not None:
        _identifier(after_request_id)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('triage limit must be an exact integer in 1..100')
    page = receiver.inspect_reservations(after_request_id=after_request_id, limit=limit)
    _require(type(page) is ReservationSnapshotPage)
    _require(type(page.entries) is tuple)
    _require(len(page.entries) <= limit)
    reports = tuple(classify_reservation(entry, scope=scope) for entry in page.entries)
    previous = None if after_request_id is None else after_request_id.encode('utf-8')
    identities = [set() for _ in range(6)]
    for report in reports:
        snapshot = report.snapshot
        reservation = snapshot.reservation
        key = reservation.request_id.encode('utf-8')
        _require(previous is None or key > previous)
        previous = key
        observation, status = snapshot.latest_usage_observation, snapshot.current_status
        values = (reservation.budget_reservation_ref, reservation.request_sha256,
                  snapshot.receipt.message_id,
                  None if status is None else status.event.event_id,
                  None if observation is None else observation.observation_id,
                  None if observation is None else observation.sequence)
        for seen, value in zip(identities, values):
            if value is not None:
                _require(value not in seen)
                seen.add(value)
    cursor = page.next_after_request_id
    if cursor is not None:
        _identifier(cursor)
        _require(len(reports) == limit and cursor == reports[-1].snapshot.reservation.request_id)
    return RecoveryTriagePage(reports, cursor)

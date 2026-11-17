"""PRIVATE selected recovery metadata, not proof, authority, wire format or JCS.

Authored NOT EXECUTED; earlier validation banners do not cover this increment.
Only the connected receiver page is accepted. Caller, receiver, imports and DB
must be independently trusted: consistent fabricated histories cannot be
self-authenticated. No writes, blob reads, clock, process or network operations
are added; the existing receiver supplies one consistent retained read page.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from json import JSONEncoder

from ai_agent_scientist.admission.durable_handoff import DurableHandoffReceipts
from ai_agent_scientist.admission.recovery_triage import inspect_recovery_triages

__all__ = ['LOCAL_REPORT_VERSION', 'MAX_OUTPUT_BYTES', 'RecoveryReportArtifact',
           'RecoveryReportTooLarge', 'build_recovery_report']

LOCAL_REPORT_VERSION = 'receiver-recovery-report-local/1'
MAX_OUTPUT_BYTES = 1_048_576


class RecoveryReportTooLarge(ValueError):
    """Whole artifact refused; no bytes, digest or partial cursor is returned."""


@dataclass(frozen=True, slots=True)
class RecoveryReportArtifact:
    """Immutable exact bytes/hash and page metadata; no authenticity assertion."""

    data: bytes
    sha256: str
    after_request_id: str | None
    limit: int
    next_after_request_id: str | None
    entry_count: int


def _select(value, names):
    # Explicit allowlists only: never asdict(), __dict__, blobs or exception text.
    return {name: getattr(value, name) for name in names}


def _project(report):
    snapshot = report.snapshot
    status, observation = snapshot.current_status, snapshot.latest_usage_observation
    return {
        'receipt': _select(snapshot.receipt, (
            'project_id', 'sender', 'recipient', 'request_id', 'message_id',
            'request_sha256', 'payload_sha256', 'revision', 'state',
            'recorded_at', 'updated_at')),
        'reservation': _select(snapshot.reservation, (
            'budget_reservation_ref', 'request_id', 'request_sha256',
            'worker_seconds', 'recorded_at')),
        'accounting': _select(snapshot.accounting, (
            'allocation_worker_seconds', 'outstanding_worker_seconds')),
        'current_status': None if status is None else {
            'event': _select(status.event, (
                'event_id', 'request_id', 'budget_reservation_ref', 'request_sha256',
                'receipt_revision', 'status', 'worker_seconds', 'created_at')),
            'ack_revision': status.ack_revision,
            'acknowledged_at': status.acknowledged_at,
        },
        'latest_usage_observation': None if observation is None else _select(
            observation, ('sequence', 'observation_id', 'request_id',
                          'budget_reservation_ref', 'request_sha256',
                          'expected_revision', 'worker_seconds', 'execution_stopped',
                          'cleanup_known', 'over_cap', 'observed_at')),
        'reasons': list(report.reasons),
    }


def build_recovery_report(receiver: DurableHandoffReceipts, *,
                          after_request_id: str | None = None, limit: int = 100,
                          max_output_bytes: int = MAX_OUTPUT_BYTES
                          ) -> RecoveryReportArtifact:
    """Build ONE actual inspect_recovery_triages page, without further reads.

    Exact builtin max_output_bytes must be in 1..MAX_OUTPUT_BYTES (no bool or
    subclasses). Cursor/limit/type/binding checks belong to connected triage.
    Serializer v1: JSONEncoder, sorted keys, ASCII escapes, compact separators,
    no NaN, UTF-8, no BOM/newline. This is deliberately NOT JCS/canonical wire.
    SHA-256 covers exactly data. Separate pages are separate read snapshots;
    cursors are exclusive local request-ID positions, never leases/authority.
    Failures propagate without a successful artifact or mutation/repair.
    """
    if type(max_output_bytes) is not int or not 1 <= max_output_bytes <= MAX_OUTPUT_BYTES:
        raise ValueError('max_output_bytes must be an exact integer in 1..1048576')
    page = inspect_recovery_triages(receiver, after_request_id=after_request_id, limit=limit)
    document = {
        'local_report_version': LOCAL_REPORT_VERSION,
        'visibility': 'private',
        'observation_selection': 'latest_local_insertion_only',
        'page': {'after_request_id': after_request_id, 'limit': limit,
                 'next_after_request_id': page.next_after_request_id},
        'entries': [_project(report) for report in page.entries],
    }
    encoder = JSONEncoder(ensure_ascii=True, sort_keys=True, allow_nan=False,
                          separators=(',', ':'))
    output = bytearray()
    for chunk in encoder.iterencode(document):
        encoded = chunk.encode('utf-8')
        if len(output) + len(encoded) > max_output_bytes:
            raise RecoveryReportTooLarge('recovery report exceeds byte limit') from None
        output.extend(encoded)
    data = bytes(output)
    return RecoveryReportArtifact(data, sha256(data).hexdigest(), after_request_id,
                                  limit, page.next_after_request_id, len(page.entries))

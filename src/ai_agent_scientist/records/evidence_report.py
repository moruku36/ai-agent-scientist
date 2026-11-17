"""Pure private evidence projection; no publication or evaluator authority.

One actual paired comparison revalidates all source bytes and identities. The
output hash binds exact encoded bytes, not JCS or a logical evidence identity.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from ai_agent_scientist.records.attempt_inventory import AttemptInventory
from ai_agent_scientist.records.paired_metrics import compare_paired_metrics

__all__ = [
    "PrivateEvidenceReport", "EvidenceReportRefused", "build_private_evidence_report",
]

_MAX_OUTPUT_BYTES = 1_048_576
_MESSAGE = "evidence report refused"


class EvidenceReportRefused(ValueError):
    """Fixed, value-free output refusal without retained encoder cause/context."""


@dataclass(frozen=True, slots=True)
class PrivateEvidenceReport:
    data: bytes
    sha256: str
    manifest_sha256: str
    expected_attempts: int
    present_attempts: int
    missing_attempts: int


def _summary(comparison):
    inventory = comparison.inventory
    attempts = []
    present = 0
    for slot in inventory.slots:
        spec, record = slot.spec, slot.record
        present += record is not None
        attempts.append({
            "run_id": spec.run_id,
            "attempt_id": spec.attempt_id,
            "replicate_id": spec.replicate_id,
            "candidate_revision": spec.candidate_revision,
            "role": spec.role,
            "record_sha256": None if record is None else record.sha256,
            "status": None if record is None else record.status,
            "validity": None if record is None else record.validity,
            "usage": {
                "wall_seconds": None if record is None else record.usage.wall_seconds,
                "incremental_api_usd": (
                    None if record is None else record.usage.incremental_api_usd
                ),
            },
            "limitation_count": None if record is None else len(record.limitations),
            "metric_value": (
                None if record is None else dict(record.metrics).get(comparison.metric)
            ),
        })
    return {
        "format": "offline-evidence-report/1",
        "scope": "unverified_private_local_summary",
        "manifest_sha256": inventory.sha256,
        "project_id": inventory.project_id,
        "protocol_revision": inventory.protocol_revision,
        "metric": comparison.metric,
        "direction": comparison.direction,
        "expected_attempts": len(attempts),
        "present_attempts": present,
        "missing_attempts": len(attempts) - present,
        "attempts": attempts,
        "declared_pair_count": len(comparison.pairs),
        "paired_observation_count": sum(
            pair.classification == "paired_observation" for pair in comparison.pairs
        ),
        "pairs": [{
            "replicate_id": pair.replicate_id,
            "baseline_run_id": pair.baseline.spec.run_id,
            "candidate_run_id": pair.candidate.spec.run_id,
            "classification": pair.classification,
            "baseline_value": pair.baseline_value,
            "candidate_value": pair.candidate_value,
            "raw_delta": pair.raw_delta,
            "directional_delta": pair.directional_delta,
        } for pair in comparison.pairs],
    }


def build_private_evidence_report(
    inventory: AttemptInventory, *, metric: str, direction: str,
    max_output_bytes: int = 1048576,
) -> PrivateEvidenceReport:
    """Return one complete private JSON artifact, or refuse without truncation.

    Validate the exact builtin int cap (1..1 MiB) before one actual Scientist29
    comparison. Its errors propagate unchanged, without wrapping or retry; it
    alone reconstructs/revalidates the inventory, record bytes and selectors.
    All attempts and pairs retain manifest order, including missing/ineligible
    records. Only the selected metric and limitation counts are projected.

    IDs and selected values may be sensitive: never publish automatically.
    Freely constructible report values confer no authority. Output bounds are
    not an aggregate input, memory, CPU or isolation limit. No I/O, clock,
    authentication, authorization, evaluator or research action is performed.
    """
    if (type(max_output_bytes) is not int
            or not 1 <= max_output_bytes <= _MAX_OUTPUT_BYTES):
        raise EvidenceReportRefused(_MESSAGE)

    # Keep the actual comparison outside our output-error handler. No supplied
    # comparison object is accepted, and there is no second inventory rebuild.
    comparison = compare_paired_metrics(inventory, metric=metric, direction=direction)
    try:
        summary = _summary(comparison)
        data = json.dumps(
            summary, allow_nan=False, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        if len(data) > max_output_bytes:
            raise ValueError(_MESSAGE)
    except (ValueError, TypeError, RecursionError, OverflowError):
        pass
    else:
        return PrivateEvidenceReport(
            data, sha256(data).hexdigest(), summary["manifest_sha256"],
            summary["expected_attempts"], summary["present_attempts"],
            summary["missing_attempts"],
        )
    # Even `from None` retains __context__; leave the handler before raising.
    raise EvidenceReportRefused(_MESSAGE)

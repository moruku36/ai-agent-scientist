"""Pure paired observations over a fully revalidated local attempt inventory.

Source status and validity are caller labels, not protected evaluation proof.
No aggregation, selection, inference or external action is performed.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from math import isfinite

from ai_agent_scientist.records.attempt_inventory import (
    AttemptInventory, AttemptSlot, AttemptSpec, build_attempt_inventory,
)
from ai_agent_scientist.records.run_record import ArtifactRef, RunRecord, Usage

__all__ = [
    "MetricPair", "PairedMetricComparison", "PairedMetricsRefused",
    "compare_paired_metrics",
]

_MESSAGE = "paired metrics refused"
_RECORD_TYPES = (
    AttemptInventory, AttemptSlot, AttemptSpec, RunRecord, ArtifactRef, Usage,
)


class PairedMetricsRefused(ValueError):
    """Fixed, value-free refusal without retained decoder cause/context."""


@dataclass(frozen=True, slots=True)
class MetricPair:
    replicate_id: str
    baseline: AttemptSlot
    candidate: AttemptSlot
    classification: str
    baseline_value: int | float | None
    candidate_value: int | float | None
    raw_delta: int | float | None
    directional_delta: int | float | None


@dataclass(frozen=True, slots=True)
class PairedMetricComparison:
    inventory: AttemptInventory
    metric: str
    direction: str
    pairs: tuple[MetricPair, ...]


def _require(condition):
    if not condition:
        raise ValueError(_MESSAGE)


def _same_value(value, rebuilt):
    """Check every field and nested scalar; never use dataclass equality."""
    if type(value) is not type(rebuilt):
        return False
    if type(rebuilt) is tuple:
        return (len(value) == len(rebuilt)
                and all(_same_value(a, b) for a, b in zip(value, rebuilt)))
    if type(rebuilt) in _RECORD_TYPES:
        return all(_same_value(getattr(value, field.name),
                               getattr(rebuilt, field.name))
                   for field in fields(rebuilt))
    if type(rebuilt) in (bytes, str, int, float, type(None)):
        return value == rebuilt
    return False


def _validate(inventory, metric, direction):
    _require(type(inventory) is AttemptInventory)
    # Validate both selectors before extracting records or rebuilding bytes.
    _require(type(metric) is str and 0 < len(metric) <= 4096
             and "\0" not in metric)
    _require(len(metric.encode("utf-8")) <= 4096)
    _require(type(direction) is str and direction in ("maximize", "minimize"))
    _require(type(inventory.slots) is tuple and len(inventory.slots) <= 1024)
    _require(all(type(slot) is AttemptSlot for slot in inventory.slots))
    rebuilt = build_attempt_inventory(
        inventory.data,
        tuple(slot.record for slot in inventory.slots if slot.record is not None),
    )
    _require(_same_value(inventory, rebuilt))


def _metric_value(record: RunRecord | None, metric: str) -> int | float | None:
    return None if record is None else dict(record.metrics).get(metric)


def _pair(replicate_id, baseline, candidate, metric, direction):
    b, c = baseline.record, candidate.record
    baseline_value = _metric_value(b, metric)
    candidate_value = _metric_value(c, metric)
    raw_delta = directional_delta = None
    if b is None or c is None:
        classification = "missing_record"
    elif b.status != "completed" or c.status != "completed":
        classification = "ineligible_status"
    elif b.validity != "valid" or c.validity != "valid":
        classification = "unchecked_validity"
    elif baseline_value is None or candidate_value is None:
        classification = "missing_metric"
    else:
        try:
            raw_delta = candidate_value - baseline_value
            directional_delta = raw_delta if direction == "maximize" else -raw_delta
        except OverflowError:
            classification = "numeric_range_unsupported"
            raw_delta = directional_delta = None
        else:
            # Never convert exact integers to floats, including for finiteness.
            if ((type(raw_delta) is float and not isfinite(raw_delta))
                    or (type(directional_delta) is float
                        and not isfinite(directional_delta))):
                classification = "numeric_range_unsupported"
                raw_delta = directional_delta = None
            else:
                classification = "paired_observation"
    return MetricPair(
        replicate_id, baseline, candidate, classification,
        baseline_value, candidate_value, raw_delta, directional_delta,
    )


def compare_paired_metrics(
    inventory: AttemptInventory, *, metric: str, direction: str,
) -> PairedMetricComparison:
    """Retain every declared replicate once, ordered by first manifest appearance.

    Exact inventory/selector types are required. Metric names are nonempty UTF-8
    <=4096 bytes without NUL/surrogates; direction is maximize or minimize.
    Rebuild with the actual inventory builder, then compare every field with
    exact nested types before observing any pair. Returned inventory and slots
    retain caller identity. Only completed, caller-labelled valid records with
    both metric values and supported arithmetic yield paired_observation.

    No storage, network, artifact resolution, evaluator or runtime is invoked.
    This is neither protected verification nor statistical or scientific inference.
    """
    try:
        _validate(inventory, metric, direction)
    except (ValueError, TypeError, AttributeError, RecursionError, OverflowError):
        pass
    else:
        groups: dict[str, dict[str, AttemptSlot]] = {}
        for slot in inventory.slots:
            groups.setdefault(slot.spec.replicate_id, {})[slot.spec.role] = slot
        return PairedMetricComparison(
            inventory, metric, direction,
            tuple(_pair(replicate_id, roles["baseline"], roles["candidate"],
                        metric, direction)
                  for replicate_id, roles in groups.items()),
        )
    # Raising outside the handler removes even a payload-bearing __context__.
    raise PairedMetricsRefused(_MESSAGE)

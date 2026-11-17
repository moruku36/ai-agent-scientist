"""Exactly four self-contained authored scenarios; NOT EXECUTED."""
from dataclasses import replace
import json
import unittest

from ai_agent_scientist.records.attempt_inventory import build_attempt_inventory
from ai_agent_scientist.records.paired_metrics import (
    PairedMetricComparison, PairedMetricsRefused, compare_paired_metrics,
)
from ai_agent_scientist.records.run_record import parse_run_record


def _manifest_data():
    # Candidate first deliberately separates manifest position from pair role.
    return json.dumps({
        "format": "offline-attempt-manifest/1",
        "project_id": "synthetic-project",
        "protocol_revision": "protocol-1",
        "attempts": [
            {"run_id": "run-c", "attempt_id": "attempt-c",
             "replicate_id": "replicate-1", "candidate_revision": "candidate-1",
             "role": "candidate"},
            {"run_id": "run-b", "attempt_id": "attempt-b",
             "replicate_id": "replicate-1", "candidate_revision": "baseline-1",
             "role": "baseline"},
        ],
    }).encode("utf-8")


def _record(run_id, attempt_id, revision, score, *, status="completed"):
    return parse_run_record(json.dumps({
        "run_id": run_id, "attempt_id": attempt_id,
        "replicate_id": "replicate-1", "project_id": "synthetic-project",
        "protocol_revision": "protocol-1", "candidate_revision": revision,
        "status": status, "validity": "valid", "artifacts": [],
        "metrics": {"score": score},
        "usage": {"wall_seconds": 1, "incremental_api_usd": None},
        "limitations": ["synthetic caller labels; no protected proof"],
    }).encode("utf-8"))


class PairedMetricsContractTests(unittest.TestCase):
    def test_completed_valid_pair_has_exact_minimize_delta_and_original_slots(self):
        baseline = _record("run-b", "attempt-b", "baseline-1", 10)
        candidate = _record("run-c", "attempt-c", "candidate-1", 11)
        inventory = build_attempt_inventory(_manifest_data(), (baseline, candidate))

        result = compare_paired_metrics(inventory, metric="score", direction="minimize")

        self.assertIs(type(result), PairedMetricComparison)
        self.assertIs(result.inventory, inventory)
        self.assertEqual((result.metric, result.direction), ("score", "minimize"))
        self.assertIs(type(result.pairs), tuple)
        self.assertEqual(len(result.pairs), 1)
        pair = result.pairs[0]
        self.assertEqual(pair.replicate_id, "replicate-1")
        self.assertIs(pair.baseline, inventory.slots[1])
        self.assertIs(pair.candidate, inventory.slots[0])
        self.assertIs(pair.baseline.record, baseline)
        self.assertIs(pair.candidate.record, candidate)
        self.assertEqual(pair.classification, "paired_observation")
        self.assertEqual((pair.baseline_value, pair.candidate_value), (10, 11))
        self.assertIs(type(pair.raw_delta), int)
        self.assertIs(type(pair.directional_delta), int)
        self.assertEqual(pair.raw_delta, 1)
        self.assertEqual(pair.directional_delta, -1)

    def test_failed_candidate_is_retained_as_ineligible_without_deltas(self):
        baseline = _record("run-b", "attempt-b", "baseline-1", 10)
        candidate = _record("run-c", "attempt-c", "candidate-1", 11, status="failed")
        inventory = build_attempt_inventory(_manifest_data(), (candidate, baseline))

        result = compare_paired_metrics(inventory, metric="score", direction="maximize")

        self.assertIs(result.inventory, inventory)
        self.assertEqual(len(result.pairs), 1)
        pair = result.pairs[0]
        self.assertEqual(pair.classification, "ineligible_status")
        self.assertIs(pair.baseline, inventory.slots[1])
        self.assertIs(pair.candidate, inventory.slots[0])
        self.assertIs(pair.candidate.record, candidate)
        self.assertEqual(pair.candidate.record.status, "failed")
        self.assertEqual((pair.baseline_value, pair.candidate_value), (10, 11))
        self.assertIsNone(pair.raw_delta)
        self.assertIsNone(pair.directional_delta)

    def test_missing_candidate_keeps_the_declared_pair_and_available_value(self):
        baseline = _record("run-b", "attempt-b", "baseline-1", 10)
        inventory = build_attempt_inventory(_manifest_data(), (baseline,))

        result = compare_paired_metrics(inventory, metric="score", direction="maximize")

        self.assertIs(result.inventory, inventory)
        self.assertEqual(len(inventory.slots), 2)
        self.assertEqual(len(result.pairs), 1)
        pair = result.pairs[0]
        self.assertEqual(pair.replicate_id, "replicate-1")
        self.assertEqual(pair.classification, "missing_record")
        self.assertIs(pair.baseline, inventory.slots[1])
        self.assertIs(pair.baseline.record, baseline)
        self.assertIs(pair.candidate, inventory.slots[0])
        self.assertEqual(pair.candidate.spec.run_id, "run-c")
        self.assertIsNone(pair.candidate.record)
        self.assertEqual(pair.baseline_value, 10)
        self.assertIsNone(pair.candidate_value)
        self.assertIsNone(pair.raw_delta)
        self.assertIsNone(pair.directional_delta)

    def test_nested_bool_equal_to_int_forgery_refuses_before_comparison(self):
        baseline = _record("run-b", "attempt-b", "baseline-1", 10)
        candidate = _record("run-c", "attempt-c", "candidate-1", 11)
        inventory = build_attempt_inventory(_manifest_data(), (baseline, candidate))
        forged_record = replace(baseline, usage=replace(baseline.usage, wall_seconds=True))
        forged_slot = replace(inventory.slots[1], record=forged_record)
        forged = replace(inventory, slots=(inventory.slots[0], forged_slot))
        self.assertEqual(forged, inventory)  # Ordinary dataclass equality is unsafe.
        self.assertIs(type(baseline.usage.wall_seconds), int)
        self.assertIs(type(forged_record.usage.wall_seconds), bool)

        with self.assertRaises(PairedMetricsRefused) as caught:
            compare_paired_metrics(forged, metric="score", direction="minimize")

        self.assertEqual(caught.exception.args, ("paired metrics refused",))
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)

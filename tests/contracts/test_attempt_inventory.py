"""Exactly four authored offline scenarios; NOT EXECUTED in this increment."""
from hashlib import sha256
import json
import unittest

from ai_agent_scientist.records.attempt_inventory import (
    AttemptInventoryRefused, AttemptSpec, build_attempt_inventory,
)
from ai_agent_scientist.records.run_record import parse_run_record


def _manifest_data(*, candidate_attempt_id="attempt-c"):
    return b"\n" + json.dumps({
        "format": "offline-attempt-manifest/1",
        "project_id": "synthetic-project",
        "protocol_revision": "protocol-1",
        "attempts": [
            {"run_id": "run-b", "attempt_id": "attempt-b",
             "replicate_id": "replicate-1", "candidate_revision": "baseline-1",
             "role": "baseline"},
            {"run_id": "run-c", "attempt_id": candidate_attempt_id,
             "replicate_id": "replicate-1", "candidate_revision": "candidate-1",
             "role": "candidate"},
        ],
    }, indent=2).encode("utf-8") + b"\n"


def _record_data(run_id, attempt_id, candidate_revision, *,
                 protocol_revision="protocol-1", status="completed"):
    return json.dumps({
        "run_id": run_id,
        "attempt_id": attempt_id,
        "replicate_id": "replicate-1",
        "project_id": "synthetic-project",
        "protocol_revision": protocol_revision,
        "candidate_revision": candidate_revision,
        "status": status,
        "validity": "unchecked",
        "artifacts": [],
        "metrics": {"score": None},
        "usage": {"wall_seconds": None, "incremental_api_usd": None},
        "limitations": ["synthetic outcome; no protected evaluation"],
    }).encode("utf-8")


class AttemptInventoryContractTests(unittest.TestCase):
    def test_full_pair_preserves_exact_records_in_manifest_order(self):
        manifest_data = _manifest_data()
        baseline = parse_run_record(_record_data(
            "run-b", "attempt-b", "baseline-1"))
        candidate = parse_run_record(_record_data(
            "run-c", "attempt-c", "candidate-1"))

        inventory = build_attempt_inventory(manifest_data, (candidate, baseline))

        self.assertIs(inventory.data, manifest_data)
        self.assertEqual(inventory.sha256, sha256(manifest_data).hexdigest())
        self.assertEqual(inventory.project_id, "synthetic-project")
        self.assertEqual(inventory.protocol_revision, "protocol-1")
        self.assertIs(type(inventory.slots), tuple)
        self.assertEqual(len(inventory.slots), 2)
        self.assertEqual(inventory.slots[0].spec, AttemptSpec(
            "run-b", "attempt-b", "replicate-1", "baseline-1", "baseline"))
        self.assertEqual(inventory.slots[1].spec, AttemptSpec(
            "run-c", "attempt-c", "replicate-1", "candidate-1", "candidate"))
        self.assertIs(inventory.slots[0].record, baseline)
        self.assertIs(inventory.slots[1].record, candidate)

    def test_missing_candidate_retains_failed_unchecked_baseline_and_null_usage(self):
        baseline = parse_run_record(_record_data(
            "run-b", "attempt-b", "baseline-1", status="failed"))

        inventory = build_attempt_inventory(_manifest_data(), (baseline,))

        self.assertEqual(len(inventory.slots), 2)
        self.assertIs(inventory.slots[0].record, baseline)
        self.assertEqual(inventory.slots[0].record.status, "failed")
        self.assertEqual(inventory.slots[0].record.validity, "unchecked")
        self.assertIs(inventory.slots[0].record.usage, baseline.usage)
        self.assertIsNone(inventory.slots[0].record.usage.wall_seconds)
        self.assertIsNone(inventory.slots[0].record.usage.incremental_api_usd)
        self.assertEqual(inventory.slots[0].record.metrics, (("score", None),))
        self.assertEqual(inventory.slots[0].record.limitations, baseline.limitations)
        self.assertEqual(inventory.slots[1].spec.role, "candidate")
        self.assertEqual(inventory.slots[1].spec.attempt_id, "attempt-c")
        self.assertIsNone(inventory.slots[1].record)

    def test_mismatched_protocol_record_refuses(self):
        baseline = parse_run_record(_record_data(
            "run-b", "attempt-b", "baseline-1"))
        candidate = parse_run_record(_record_data(
            "run-c", "attempt-c", "candidate-1", protocol_revision="protocol-2"))

        with self.assertRaises(AttemptInventoryRefused) as caught:
            build_attempt_inventory(_manifest_data(), (baseline, candidate))

        self.assertEqual(caught.exception.args, ("attempt inventory refused",))
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)

    def test_duplicate_manifest_attempt_identity_refuses(self):
        manifest_data = _manifest_data(candidate_attempt_id="attempt-b")

        with self.assertRaises(AttemptInventoryRefused) as caught:
            build_attempt_inventory(manifest_data, ())

        self.assertEqual(caught.exception.args, ("attempt inventory refused",))
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)

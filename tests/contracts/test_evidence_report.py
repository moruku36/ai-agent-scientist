"""Scientist30: exactly four self-contained authored scenarios; NOT EXECUTED."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from ai_agent_scientist.evidence.blob_store import BlobStore
from ai_agent_scientist.records.attempt_inventory import build_attempt_inventory
from ai_agent_scientist.records.evidence_report import (
    EvidenceReportRefused, PrivateEvidenceReport, build_private_evidence_report,
)
from ai_agent_scientist.records.paired_metrics import compare_paired_metrics
from ai_agent_scientist.records.run_record import parse_run_record
from ai_agent_scientist.records.run_store import load_run_record, store_run_record


def _manifest_data():
    # Candidate first; input record arrival and baseline role cannot reorder it.
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


def _record_data(run_id, attempt_id, revision, score, artifact_sha256):
    return json.dumps({
        "run_id": run_id, "attempt_id": attempt_id,
        "replicate_id": "replicate-1", "project_id": "synthetic-project",
        "protocol_revision": "protocol-1", "candidate_revision": revision,
        "status": "completed", "validity": "valid",
        "artifacts": [{"id": "private-artifact-reference",
                       "sha256": artifact_sha256, "kind": "raw_output"}],
        "metrics": {"score": score, "secret_metric_name_do_not_export": 987654321},
        "usage": {"wall_seconds": None, "incremental_api_usd": None},
        "limitations": ["freeform-limitation-private-sentinel"],
    }).encode("utf-8")


class EvidenceReportContractTests(unittest.TestCase):
    def test_A_private_store_load_inventory_report_exact_bytes_and_projection(self):
        manifest = _manifest_data()
        artifact_payload = b"artifact-payload-private-sentinel"
        with tempfile.TemporaryDirectory() as directory:
            store = BlobStore(Path(directory), max_blob_bytes=1048576)
            artifact_digest = store.put(artifact_payload)
            stored_baseline = store_run_record(store, _record_data(
                "run-b", "attempt-b", "baseline-1", 10, artifact_digest,
            ))
            stored_candidate = store_run_record(store, _record_data(
                "run-c", "attempt-c", "candidate-1", 11, artifact_digest,
            ))
            with mock.patch.object(store, "get", wraps=store.get) as get:
                baseline = load_run_record(store, stored_baseline.sha256)
                candidate = load_run_record(store, stored_candidate.sha256)
                inventory = build_attempt_inventory(manifest, (baseline, candidate))
                with mock.patch(
                    "ai_agent_scientist.records.evidence_report.compare_paired_metrics",
                    wraps=compare_paired_metrics,
                ) as compare:
                    report = build_private_evidence_report(
                        inventory, metric="score", direction="minimize",
                    )
                compare.assert_called_once_with(
                    inventory, metric="score", direction="minimize",
                )
                self.assertEqual(get.call_count, 2)  # No artifact/report store read.

        expected = {
            "format": "offline-evidence-report/1",
            "scope": "unverified_private_local_summary",
            "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
            "project_id": "synthetic-project", "protocol_revision": "protocol-1",
            "metric": "score", "direction": "minimize",
            "expected_attempts": 2, "present_attempts": 2, "missing_attempts": 0,
            "declared_pair_count": 1, "paired_observation_count": 1,
            "attempts": [
                {"run_id": "run-c", "attempt_id": "attempt-c",
                 "replicate_id": "replicate-1", "candidate_revision": "candidate-1",
                 "role": "candidate", "record_sha256": candidate.sha256,
                 "status": "completed", "validity": "valid",
                 "usage": {"wall_seconds": None, "incremental_api_usd": None},
                 "limitation_count": 1, "metric_value": 11},
                {"run_id": "run-b", "attempt_id": "attempt-b",
                 "replicate_id": "replicate-1", "candidate_revision": "baseline-1",
                 "role": "baseline", "record_sha256": baseline.sha256,
                 "status": "completed", "validity": "valid",
                 "usage": {"wall_seconds": None, "incremental_api_usd": None},
                 "limitation_count": 1, "metric_value": 10},
            ],
            "pairs": [{
                "replicate_id": "replicate-1", "baseline_run_id": "run-b",
                "candidate_run_id": "run-c", "classification": "paired_observation",
                "baseline_value": 10, "candidate_value": 11,
                "raw_delta": 1, "directional_delta": -1,
            }],
        }
        expected_data = json.dumps(
            expected, allow_nan=False, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        self.assertIs(type(report), PrivateEvidenceReport)
        self.assertTrue(PrivateEvidenceReport.__dataclass_params__.frozen)
        self.assertFalse(hasattr(report, "__dict__"))
        self.assertIs(type(report.data), bytes)
        self.assertEqual(report.data, expected_data)
        self.assertEqual(report.sha256, hashlib.sha256(expected_data).hexdigest())
        self.assertEqual(report.manifest_sha256, hashlib.sha256(manifest).hexdigest())
        self.assertEqual((report.expected_attempts, report.present_attempts,
                          report.missing_attempts), (2, 2, 0))
        document = json.loads(report.data)
        self.assertEqual(document["pairs"][0]["raw_delta"], 1)
        self.assertEqual(document["pairs"][0]["directional_delta"], -1)
        self.assertEqual(document["attempts"][0]["usage"],
                         {"wall_seconds": None, "incremental_api_usd": None})
        self.assertNotIn(b"secret_metric_name_do_not_export", report.data)
        self.assertNotIn(b"987654321", report.data)
        self.assertNotIn(b"freeform-limitation-private-sentinel", report.data)
        self.assertNotIn(b"private-artifact-reference", report.data)
        self.assertNotIn(artifact_digest.encode("ascii"), report.data)
        self.assertNotIn(artifact_payload, report.data)

    def test_B_missing_candidate_retains_both_attempts_and_declared_pair(self):
        baseline = parse_run_record(_record_data(
            "run-b", "attempt-b", "baseline-1", 10, "0" * 64,
        ))
        inventory = build_attempt_inventory(_manifest_data(), (baseline,))

        report = build_private_evidence_report(
            inventory, metric="score", direction="maximize",
        )

        document = json.loads(report.data)
        self.assertEqual((report.expected_attempts, report.present_attempts,
                          report.missing_attempts), (2, 1, 1))
        self.assertEqual((document["expected_attempts"], document["present_attempts"],
                          document["missing_attempts"]), (2, 1, 1))
        self.assertEqual(len(document["attempts"]), 2)
        self.assertEqual(document["attempts"][0], {
            "run_id": "run-c", "attempt_id": "attempt-c",
            "replicate_id": "replicate-1", "candidate_revision": "candidate-1",
            "role": "candidate", "record_sha256": None, "status": None,
            "validity": None,
            "usage": {"wall_seconds": None, "incremental_api_usd": None},
            "limitation_count": None, "metric_value": None,
        })
        self.assertEqual(document["attempts"][1]["record_sha256"], baseline.sha256)
        self.assertEqual(document["attempts"][1]["metric_value"], 10)
        self.assertEqual(document["declared_pair_count"], 1)
        self.assertEqual(document["paired_observation_count"], 0)
        self.assertEqual(document["pairs"], [{
            "replicate_id": "replicate-1", "baseline_run_id": "run-b",
            "candidate_run_id": "run-c", "classification": "missing_record",
            "baseline_value": 10, "candidate_value": None,
            "raw_delta": None, "directional_delta": None,
        }])

    def test_C_valid_inventory_refuses_whole_artifact_above_one_byte_cap(self):
        baseline = parse_run_record(_record_data(
            "run-b", "attempt-b", "baseline-1", 10, "0" * 64,
        ))
        inventory = build_attempt_inventory(_manifest_data(), (baseline,))
        report = None

        with mock.patch(
            "ai_agent_scientist.records.evidence_report.compare_paired_metrics",
            wraps=compare_paired_metrics,
        ) as compare:
            with self.assertRaises(EvidenceReportRefused) as caught:
                report = build_private_evidence_report(
                    inventory, metric="score", direction="maximize", max_output_bytes=1,
                )
            compare.assert_called_once_with(inventory, metric="score", direction="maximize")

        self.assertIsNone(report)
        self.assertFalse(hasattr(caught.exception, "data"))
        self.assertEqual(caught.exception.args, ("evidence report refused",))
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)

    def test_D_bool_cap_refuses_before_comparison(self):
        inventory = build_attempt_inventory(_manifest_data(), ())

        with mock.patch(
            "ai_agent_scientist.records.evidence_report.compare_paired_metrics",
            side_effect=AssertionError("comparison must not run"),
        ) as compare:
            with self.assertRaises(EvidenceReportRefused) as caught:
                build_private_evidence_report(
                    inventory, metric="score", direction="maximize", max_output_bytes=True,
                )
            compare.assert_not_called()

        self.assertEqual(caught.exception.args, ("evidence report refused",))
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)

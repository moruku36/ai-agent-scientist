"""R01-R04: four limited scenarios, authored NOT EXECUTED."""
from dataclasses import FrozenInstanceError
import hashlib
import unittest
from unittest import mock

from ai_agent_scientist.records import run_record
from ai_agent_scientist.records.run_record import (
    ArtifactRef, RunRecord, RunRecordRefused, Usage, parse_run_record,
)


class RunRecordTests(unittest.TestCase):
    def test_R01_valid_record_identity_and_immutability(self):
        raw = (
            b' \n{"run_id":"run-1","attempt_id":"attempt-1","replicate_id":"replicate-1",'
            b'"project_id":"project-1","protocol_revision":"protocol-1",'
            b'"candidate_revision":"candidate-1","status":"failed","validity":"unchecked",'
            b'"artifacts":[{"id":"log-1","sha256":"0000000000000000000000000000000000000000000000000000000000000000","kind":"raw_output"}],'
            b'"metrics":{"delta":-1.5,"score":null},'
            b'"usage":{"wall_seconds":null,"incremental_api_usd":null},'
            b'"limitations":["Synthetic; no evaluation performed."]}\t'
        )
        got = parse_run_record(raw)
        self.assertIs(type(got), RunRecord)
        self.assertIs(got.data, raw)
        self.assertEqual(got.sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual((got.status, got.validity), ("failed", "unchecked"))
        self.assertEqual(got.artifacts, (ArtifactRef("log-1", "0" * 64, "raw_output"),))
        self.assertEqual(got.metrics, (("delta", -1.5), ("score", None)))
        self.assertEqual(got.usage, Usage(None, None))
        self.assertEqual(got.limitations, ("Synthetic; no evaluation performed.",))
        self.assertIs(type(got.artifacts), tuple)
        self.assertIs(type(got.metrics), tuple)
        self.assertIs(type(got.metrics[0]), tuple)
        self.assertIs(type(got.metrics[1]), tuple)
        self.assertIs(type(got.limitations), tuple)
        with self.assertRaises(TypeError):
            got.metrics[0][1] = 0
        with self.assertRaises(FrozenInstanceError):
            got.status = "completed"
        with self.assertRaises(FrozenInstanceError):
            got.artifacts[0].id = "changed"
        with self.assertRaises(FrozenInstanceError):
            got.usage.wall_seconds = 0

    def test_R02_duplicate_decoded_key_refused(self):
        raw = (
            b'{"run_id":"run-1","\\u0072un_id":"run-2",'
            b'"attempt_id":"attempt-1","replicate_id":"replicate-1",'
            b'"project_id":"project-1","protocol_revision":"protocol-1",'
            b'"candidate_revision":"candidate-1","status":"failed","validity":"unchecked",'
            b'"artifacts":[],"metrics":{},'
            b'"usage":{"wall_seconds":null,"incremental_api_usd":null},'
            b'"limitations":["Synthetic; no evaluation performed."]}'
        )
        with self.assertRaises(RunRecordRefused) as caught:
            parse_run_record(raw)
        error = caught.exception
        self.assertEqual(error.args, ("run record refused",))
        self.assertEqual(str(error), "run record refused")
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)

    def test_R03_boolean_usage_refused(self):
        raw = (
            b'{"run_id":"run-1","attempt_id":"attempt-1","replicate_id":"replicate-1",'
            b'"project_id":"project-1","protocol_revision":"protocol-1",'
            b'"candidate_revision":"candidate-1","status":"failed","validity":"unchecked",'
            b'"artifacts":[],"metrics":{},'
            b'"usage":{"wall_seconds":true,"incremental_api_usd":null},'
            b'"limitations":["Synthetic; no evaluation performed."]}'
        )
        with self.assertRaises(RunRecordRefused):
            parse_run_record(raw)

    def test_R04_byte_cap_refused_before_decode(self):
        raw = (
            b'{"run_id":"run-1","attempt_id":"attempt-1","replicate_id":"replicate-1",'
            b'"project_id":"project-1","protocol_revision":"protocol-1",'
            b'"candidate_revision":"candidate-1","status":"failed","validity":"unchecked",'
            b'"artifacts":[],"metrics":{},'
            b'"usage":{"wall_seconds":null,"incremental_api_usd":null},'
            b'"limitations":["Synthetic; no evaluation performed."]}'
        )
        with mock.patch.object(run_record, "parse_json_bytes") as decoder:
            with self.assertRaises(RunRecordRefused):
                parse_run_record(raw, max_bytes=16)
            decoder.assert_not_called()

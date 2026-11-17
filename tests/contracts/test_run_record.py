"""R01-R04: four self-contained methods, authored NOT EXECUTED.

Only synthetic inline fixtures; no previous test classes, services or runners.
There are 316 labelled subcases (26 / 30 / 202 / 58), not 316 test methods.
"""
from dataclasses import FrozenInstanceError
import hashlib
import json
import math
import unittest
from unittest import mock

from ai_agent_scientist.records import run_record
from ai_agent_scientist.records.run_record import (
    ArtifactRef, RunRecord, RunRecordRefused, Usage, parse_run_record,
)


def _fixture():
    return {
        "run_id": "run-é", "attempt_id": "attempt-1", "replicate_id": "replicate-1",
        "project_id": "project-1", "protocol_revision": "protocol-1",
        "candidate_revision": "candidate-1", "status": "failed", "validity": "unchecked",
        "artifacts": [{"id": "a-" + kind, "sha256": "ab" * 32, "kind": kind}
                      for kind in ("input", "source", "environment", "raw_output",
                                   "derived", "metric_receipt")],
        "metrics": {"negative": -2.5, "integer": -3, "unknown": None,
                    "negative_zero": -0.0, "large_integer": 10 ** 400},
        "usage": {"wall_seconds": 0, "incremental_api_usd": 0.0},
        "limitations": ["Synthetic; no verified claim.", "合成値"],
    }


def _wire(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


def _refused(case, data, **kwargs):
    with case.assertRaises(RunRecordRefused) as caught:
        parse_run_record(data, **kwargs)
    error = caught.exception
    case.assertEqual(error.args, ("run record refused",))
    case.assertEqual(str(error), "run record refused")
    case.assertEqual(repr(error), "RunRecordRefused('run record refused')")
    case.assertIsNone(error.__cause__)
    case.assertIsNone(error.__context__)


class RunRecordTests(unittest.TestCase):
    def test_R01_valid_identity_and_immutability(self):
        # 24 independent status/validity combinations; neither field promotes.
        for status in ("completed", "partial", "failed", "timeout", "cancelled", "rejected"):
            for validity in ("unchecked", "valid", "invalid", "inconclusive"):
                with self.subTest(status=status, validity=validity):
                    obj = _fixture()
                    obj.update(status=status, validity=validity)
                    raw = b" \n" + _wire(obj) + b"\t"
                    got = parse_run_record(raw)
                    self.assertIs(type(got), RunRecord)
                    self.assertIs(got.data, raw)
                    self.assertEqual(got.sha256, hashlib.sha256(raw).hexdigest())
                    for name in ("run_id", "attempt_id", "replicate_id", "project_id",
                                 "protocol_revision", "candidate_revision", "status", "validity"):
                        self.assertEqual(getattr(got, name), obj[name])
                    self.assertEqual(got.artifacts, tuple(ArtifactRef(**a) for a in obj["artifacts"]))
                    self.assertEqual(got.metrics, tuple(obj["metrics"].items()))
                    self.assertEqual(got.limitations, tuple(obj["limitations"]))
                    self.assertEqual(got.usage, Usage(0, 0.0))
                    self.assertIs(type(got.usage.wall_seconds), int)
                    self.assertIs(type(got.usage.incremental_api_usd), float)
                    metrics = dict(got.metrics)
                    self.assertIs(type(metrics["integer"]), int)
                    self.assertIs(type(metrics["negative"]), float)
                    self.assertIsNone(metrics["unknown"])
                    self.assertEqual(metrics["large_integer"], 10 ** 400)
                    self.assertEqual(math.copysign(1, metrics["negative_zero"]), -1)
                    for value, field in ((got, "status"), (got.artifacts[0], "id"),
                                         (got.usage, "wall_seconds")):
                        self.assertFalse(hasattr(value, "__dict__"))
                        with self.assertRaises(FrozenInstanceError):
                            setattr(value, field, "changed")
                    for value in (got.artifacts, got.metrics, got.metrics[0], got.limitations):
                        self.assertIs(type(value), tuple)
                        with self.assertRaises(TypeError):
                            value[0] = "changed"
                    # Mutating the source fixture cannot mutate the parsed value.
                    obj["artifacts"][0]["id"] = "changed"
                    obj["metrics"]["negative"] = 99
                    obj["limitations"][0] = "changed"
                    self.assertEqual(got.artifacts[0].id, "a-input")
                    self.assertEqual(dict(got.metrics)["negative"], -2.5)
                    self.assertEqual(got.limitations[0], "Synthetic; no verified claim.")
        with self.subTest(case="null-usage-empty-collections"):
            obj = _fixture()
            obj.update(artifacts=[], metrics={}, limitations=[],
                       usage={"wall_seconds": None, "incremental_api_usd": None})
            got = parse_run_record(_wire(obj))
            self.assertEqual((got.artifacts, got.metrics, got.limitations), ((), (), ()))
            self.assertIsNone(got.usage.wall_seconds)
            self.assertIsNone(got.usage.incremental_api_usd)
        with self.subTest(case="equivalent-json-distinct-byte-identity"):
            obj = _fixture()
            first = _wire(obj)
            second = json.dumps(dict(reversed(list(obj.items()))), ensure_ascii=False,
                                indent=2).encode("utf-8")
            a, b = parse_run_record(first), parse_run_record(second)
            self.assertIs(a.data, first)
            self.assertIs(b.data, second)
            self.assertNotEqual(a.sha256, b.sha256)
            self.assertEqual(b.sha256, hashlib.sha256(second).hexdigest())
            self.assertEqual((a.run_id, a.artifacts, a.metrics, a.usage, a.limitations),
                             (b.run_id, b.artifacts, b.metrics, b.usage, b.limitations))

    def test_R02_strict_json_and_byte_types(self):
        raw = _wire(_fixture())
        cases = [
            ("empty", b""), ("whitespace", b" \n\t"), ("truncated", raw[:-1]),
            ("trailing-comma", raw[:-1] + b",}"), ("trailing-value", raw + b"null"),
            ("invalid-utf8", b'"private-\xff"'), ("bom", b"\xef\xbb\xbf" + raw),
            ("utf16", raw.decode().encode("utf-16")),
            ("utf32", raw.decode().encode("utf-32")),
            ("unescaped-nul", b'{"private":"secret\x00"}'),
            ("top-duplicate", b'{"run_id":"private-secret",' + raw[1:]),
            ("escaped-duplicate", b'{"\\u0072un_id":"private-secret",' + raw[1:]),
            ("artifact-duplicate", raw.replace(b'"id":"a-input"',
                                              b'"id":"a-input","id":"private-secret"', 1)),
            ("metric-duplicate", raw.replace(b'"negative":-2.5',
                                            b'"negative":-2.5,"negative":3', 1)),
            ("usage-duplicate", raw.replace(b'"wall_seconds":0',
                                           b'"wall_seconds":0,"wall_seconds":1', 1)),
            ("nan", raw.replace(b'"negative":-2.5', b'"negative":NaN')),
            ("infinity", raw.replace(b'"negative":-2.5', b'"negative":Infinity')),
            ("negative-infinity", raw.replace(b'"negative":-2.5', b'"negative":-Infinity')),
            ("float-overflow", raw.replace(b'"negative":-2.5', b'"negative":1e999')),
            ("negative-float-overflow", raw.replace(b'"negative":-2.5', b'"negative":-1e999')),
            ("depth-refusal", b"[" * 2000 + b"0" + b"]" * 2000),
        ]
        for label, bad in cases:
            with self.subTest(case=label):
                _refused(self, bad)

        class BytesSubclass(bytes):
            pass

        for index, bad in enumerate((BytesSubclass(raw), bytearray(raw), memoryview(raw),
                                     "private-secret", None, True, 0, {}, [])):
            with self.subTest(byte_type=index):
                _refused(self, bad)

    def test_R03_complete_shape_and_semantic_refusals(self):
        # Every table entry starts with a fresh complete fixture.
        identity = ("run_id", "attempt_id", "replicate_id", "project_id",
                    "protocol_revision", "candidate_revision")
        bad_text = ("", None, True, 7, 1.5, [], {}, "a\0b", "\ud800", "\udfff")
        cases = []
        for name in _fixture():
            obj = _fixture()
            del obj[name]
            cases.append(("missing-" + name, obj))
        obj = _fixture()
        obj["private-secret"] = "extra"
        cases.append(("extra-top", obj))
        cases.extend(("root-" + str(i), v) for i, v in enumerate(([], None, True, 1, 1.5, "secret")))
        for name in identity:
            for i, value in enumerate(bad_text):
                obj = _fixture()
                obj[name] = value
                cases.append((f"identity-{name}-{i}", obj))
        for name in ("status", "validity", "kind"):
            for i, value in enumerate(("", None, True, 7, [], {}, "UNKNOWN", "completed\0")):
                obj = _fixture()
                target = obj["artifacts"][0] if name == "kind" else obj
                target[name] = value
                cases.append((f"enum-{name}-{i}", obj))
        for name in ("artifacts", "limitations", "metrics", "usage"):
            wrong_collection = {} if name in ("artifacts", "limitations") else []
            for i, value in enumerate((None, wrong_collection, "", True, 1)):
                obj = _fixture()
                obj[name] = value
                cases.append((f"collection-{name}-{i}", obj))
        for i, value in enumerate((None, [], "", True, 1, 1.5)):
            obj = _fixture()
            obj["artifacts"] = [value]
            cases.append((f"artifact-type-{i}", obj))
        for name in ("id", "sha256", "kind", "extra"):
            obj = _fixture()
            if name == "extra":
                obj["artifacts"][0][name] = "private-secret"
            else:
                del obj["artifacts"][0][name]
            cases.append(("artifact-shape-" + name, obj))
        for i, value in enumerate(bad_text):
            obj = _fixture()
            obj["artifacts"][0]["id"] = value
            cases.append((f"artifact-id-{i}", obj))
        for i, value in enumerate(("", None, True, 7, [], {}, "a" * 63, "a" * 65,
                                   "A" * 64, "g" * 64, "a" * 63 + "\n")):
            obj = _fixture()
            obj["artifacts"][0]["sha256"] = value
            cases.append((f"artifact-hash-{i}", obj))
        for label, changes in (("identical-tuple", {}), ("same-id-new-hash", {"sha256": "cd" * 32}),
                               ("same-id-new-kind", {"kind": "derived"})):
            obj = _fixture()
            obj["artifacts"].append(dict(obj["artifacts"][0], **changes))
            cases.append((label, obj))
        for i, value in enumerate(("", "a\0b", "\ud800", "\udfff")):
            obj = _fixture()
            obj["metrics"] = {value: 1}
            cases.append((f"metric-name-{i}", obj))
        for name in ("metric", "wall_seconds", "incremental_api_usd"):
            for i, value in enumerate((True, False, "1", [], {}, float("nan"),
                                       float("inf"), -float("inf"))):
                obj = _fixture()
                target = obj["metrics"] if name == "metric" else obj["usage"]
                target[name] = value
                cases.append((f"numeric-{name}-{i}", obj))
        for name in ("wall_seconds", "incremental_api_usd"):
            for value in (-1, -0.5):
                obj = _fixture()
                obj["usage"][name] = value
                cases.append((f"negative-usage-{name}-{value}", obj))
        for name in ("wall_seconds", "incremental_api_usd", "extra"):
            obj = _fixture()
            if name == "extra":
                obj["usage"][name] = 0
            else:
                del obj["usage"][name]
            cases.append(("usage-shape-" + name, obj))
        for i, value in enumerate(bad_text):
            obj = _fixture()
            obj["limitations"] = [value]
            cases.append((f"limitation-{i}", obj))
        for label, obj in cases:
            with self.subTest(case=label):
                _refused(self, _wire(obj))

    def test_R04_resource_bounds_and_predecode_rejection(self):
        raw = _wire(_fixture())

        class IntSubclass(int):
            pass

        class BytesSubclass(bytes):
            pass

        # Invalid arguments and byte overruns must not call the decoder.
        for i, cap in enumerate((True, False, None, 1.0, "1", IntSubclass(1), 0, -1, 1048577)):
            with self.subTest(cap=i), mock.patch.object(run_record, "parse_json_bytes") as parser:
                _refused(self, raw, max_bytes=cap)
                parser.assert_not_called()
        for i, bad in enumerate((BytesSubclass(raw), bytearray(raw), memoryview(raw),
                                 "private-secret", None, True, 0, {}, [])):
            with self.subTest(predecode_type=i), mock.patch.object(run_record, "parse_json_bytes") as parser:
                _refused(self, bad)
                parser.assert_not_called()
        for label, data, cap in (("caller-cap", raw, len(raw) - 1),
                                 ("hard-cap", b" " * 1048577, 1048576)):
            with self.subTest(over_bytes=label), mock.patch.object(run_record, "parse_json_bytes") as parser:
                _refused(self, data, max_bytes=cap)
                parser.assert_not_called()
        positions = ("run_id", "attempt_id", "replicate_id", "project_id", "protocol_revision",
                     "candidate_revision", "status", "validity", "artifact-id", "artifact-sha256",
                     "artifact-kind", "metric-name", "limitation")
        for position in positions:
            for label, text in (("ascii", "x" * 4097), ("utf8", "é" * 2049)):
                with self.subTest(over_string=position, encoding=label):
                    obj = _fixture()
                    if position.startswith("artifact-"):
                        obj["artifacts"][0][position.split("-", 1)[1]] = text
                    elif position == "metric-name":
                        obj["metrics"] = {text: 0}
                    elif position == "limitation":
                        obj["limitations"] = [text]
                    else:
                        obj[position] = text
                    _refused(self, _wire(obj))
        for size in (1025, 1024):
            for name in ("artifacts", "metrics", "limitations"):
                with self.subTest(collection=name, size=size):
                    obj = _fixture()
                    obj[name] = ({str(i): None for i in range(size)} if name == "metrics" else
                                 [{"id": str(i), "sha256": "0" * 64, "kind": "input"}
                                  for i in range(size)] if name == "artifacts" else ["x"] * size)
                    if size == 1025:
                        _refused(self, _wire(obj))
                    else:
                        self.assertEqual(len(getattr(parse_run_record(_wire(obj)), name)), size)
        for label, text in (("ascii", "x" * 4096), ("utf8", "é" * 2048), ("astral", "😀" * 1024)):
            with self.subTest(string_boundary=label):
                obj = _fixture()
                for name in positions[:6]:
                    obj[name] = text
                obj["artifacts"][0]["id"] = text
                obj["metrics"] = {text: -1}
                obj["limitations"] = [text]
                got = parse_run_record(_wire(obj))
                self.assertEqual(got.run_id, text)
                self.assertEqual(got.artifacts[0].id, text)
                self.assertEqual(got.metrics, ((text, -1),))
                self.assertEqual(got.limitations, (text,))
        for label, data, kwargs in (("exact-caller-cap", raw, {"max_bytes": len(raw)}),
                                    ("default-hard-cap", b" " * (1048576 - len(raw)) + raw, {})):
            with self.subTest(byte_boundary=label), mock.patch.object(
                    run_record, "parse_json_bytes", wraps=run_record.parse_json_bytes) as parser:
                self.assertIs(parse_run_record(data, **kwargs).data, data)
                parser.assert_called_once_with(data)
        with self.subTest(case="minimum-cap-reaches-decoder"), mock.patch.object(
                run_record, "parse_json_bytes", wraps=run_record.parse_json_bytes) as parser:
            _refused(self, b"0", max_bytes=1)
            parser.assert_called_once_with(b"0")

"""Bounded run-record summary parsing; no authentication or promotion.

The unchanged run-record.schema.json supplies the closed shape. Local resource
and string bounds narrow that shape. Exact bytes are retained, never serialized
again. These freely constructible values are not protected evaluator receipts.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
import re

from ai_agent_scientist.evidence.json_blob import parse_json_bytes

__all__ = ["ArtifactRef", "Usage", "RunRecord", "RunRecordRefused", "parse_run_record"]

_MAX_BYTES = 1_048_576
_MAX_ITEMS = 1024
_MAX_STRING_BYTES = 4096
_MESSAGE = "run record refused"
_IDENTITY = ("run_id", "attempt_id", "replicate_id", "project_id",
             "protocol_revision", "candidate_revision")
_TOP = frozenset((*_IDENTITY, "status", "validity", "artifacts", "metrics",
                  "usage", "limitations"))
_ARTIFACT = frozenset(("id", "sha256", "kind"))
_USAGE = frozenset(("wall_seconds", "incremental_api_usd"))
_STATUSES = ("completed", "partial", "failed", "timeout", "cancelled", "rejected")
_VALIDITIES = ("unchecked", "valid", "invalid", "inconclusive")
_KINDS = ("input", "source", "environment", "raw_output", "derived", "metric_receipt")
_HASH = re.compile(r"[a-f0-9]{64}")


class RunRecordRefused(ValueError):
    """Fixed, value-free refusal with no retained decoder exception chain."""


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    id: str
    sha256: str
    kind: str


@dataclass(frozen=True, slots=True)
class Usage:
    wall_seconds: int | float | None
    incremental_api_usd: int | float | None


@dataclass(frozen=True, slots=True)
class RunRecord:
    data: bytes
    sha256: str
    run_id: str
    attempt_id: str
    replicate_id: str
    project_id: str
    protocol_revision: str
    candidate_revision: str
    status: str
    validity: str
    artifacts: tuple[ArtifactRef, ...]
    metrics: tuple[tuple[str, int | float | None], ...]
    usage: Usage
    limitations: tuple[str, ...]


def _require(condition):
    if not condition:
        raise ValueError(_MESSAGE)


def _text(value):
    _require(type(value) is str and 0 < len(value) <= _MAX_STRING_BYTES
             and "\0" not in value)
    # Strict UTF-8 encoding rejects escaped lone surrogates left by json.loads.
    _require(len(value.encode("utf-8")) <= _MAX_STRING_BYTES)
    return value


def _object(value, keys=None):
    _require(type(value) is dict and len(value) <= _MAX_ITEMS)
    for key in value:
        _text(key)
    if keys is not None:
        _require(value.keys() == keys)
    return value


def _array(value):
    _require(type(value) is list and len(value) <= _MAX_ITEMS)
    return value


def _enum(value, allowed):
    value = _text(value)
    _require(value in allowed)
    return value


def _number(value, *, nonnegative=False):
    if value is not None:
        # Integers are finite without converting (possibly very large) ints.
        _require(type(value) is int or (type(value) is float and isfinite(value)))
        _require(not nonnegative or value >= 0)
    return value


def _record(value, data):
    obj = _object(value, _TOP)
    identity = {name: _text(obj[name]) for name in _IDENTITY}
    status = _enum(obj["status"], _STATUSES)
    validity = _enum(obj["validity"], _VALIDITIES)
    artifacts, seen_ids, seen_refs = [], set(), set()
    for item in _array(obj["artifacts"]):
        item = _object(item, _ARTIFACT)
        digest = _text(item["sha256"])
        _require(_HASH.fullmatch(digest) is not None)
        ref = ArtifactRef(_text(item["id"]), digest, _enum(item["kind"], _KINDS))
        _require(ref.id not in seen_ids and ref not in seen_refs)
        seen_ids.add(ref.id)
        seen_refs.add(ref)
        artifacts.append(ref)
    metrics = tuple((name, _number(number))
                    for name, number in _object(obj["metrics"]).items())
    usage = _object(obj["usage"], _USAGE)
    usage = Usage(_number(usage["wall_seconds"], nonnegative=True),
                  _number(usage["incremental_api_usd"], nonnegative=True))
    limitations = tuple(_text(item) for item in _array(obj["limitations"]))
    return RunRecord(data=data, sha256=sha256(data).hexdigest(), **identity,
                     status=status, validity=validity, artifacts=tuple(artifacts),
                     metrics=metrics, usage=usage, limitations=limitations)


def parse_run_record(data: bytes, *, max_bytes: int = 1048576) -> RunRecord:
    """Parse bounded exact bytes or raise a fixed RunRecordRefused.

    Exact builtin bytes/int only; cap 1..1048576, checked before decoding. All
    strings (including keys) are nonempty UTF-8, <=4096 bytes, without NUL or
    surrogates; each array/map has <=1024 entries. Numeric types and null are
    preserved. Neither status nor validity grants trust. Byte/item limits are
    not a complete depth, CPU or memory isolation boundary.
    """
    if (type(data) is not bytes or type(max_bytes) is not int
            or not 1 <= max_bytes <= _MAX_BYTES or len(data) > max_bytes):
        raise RunRecordRefused(_MESSAGE)
    try:
        result = _record(parse_json_bytes(data), data)
    except (ValueError, TypeError, RecursionError, OverflowError):
        pass
    else:
        return result
    # Raise after leaving the handler: even __context__ must not retain a
    # JSONDecodeError/UnicodeDecodeError carrying untrusted source material.
    raise RunRecordRefused(_MESSAGE)

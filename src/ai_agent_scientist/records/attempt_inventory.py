"""Pure, bounded inventory of a locally declared paired attempt denominator.

This internal manifest is neither a canonical wire schema nor authenticated
preregistration. Missing records remain explicit; no outcome is inferred.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from hashlib import sha256

from ai_agent_scientist.evidence.json_blob import parse_json_bytes
from ai_agent_scientist.records.run_record import (
    ArtifactRef, RunRecord, Usage, parse_run_record,
)

__all__ = [
    "AttemptSpec", "AttemptSlot", "AttemptInventory", "AttemptInventoryRefused",
    "build_attempt_inventory",
]

_MAX_BYTES = 1_048_576
_MAX_ITEMS = 1024
_MAX_STRING_BYTES = 4096
_MESSAGE = "attempt inventory refused"
_TOP = frozenset(("format", "project_id", "protocol_revision", "attempts"))
_ATTEMPT = frozenset((
    "run_id", "attempt_id", "replicate_id", "candidate_revision", "role",
))
_ROLES = frozenset(("baseline", "candidate"))


class AttemptInventoryRefused(ValueError):
    """Fixed, value-free refusal without retained parser exception chains."""


@dataclass(frozen=True, slots=True)
class AttemptSpec:
    run_id: str
    attempt_id: str
    replicate_id: str
    candidate_revision: str
    role: str


@dataclass(frozen=True, slots=True)
class AttemptSlot:
    spec: AttemptSpec
    record: RunRecord | None


@dataclass(frozen=True, slots=True)
class AttemptInventory:
    data: bytes
    sha256: str
    project_id: str
    protocol_revision: str
    slots: tuple[AttemptSlot, ...]


def _require(condition):
    if not condition:
        raise ValueError(_MESSAGE)


def _text(value):
    _require(type(value) is str and 0 < len(value) <= _MAX_STRING_BYTES
             and "\0" not in value)
    _require(len(value.encode("utf-8")) <= _MAX_STRING_BYTES)
    return value


def _object(value, keys):
    _require(type(value) is dict and value.keys() == keys)
    return value


def _same_value(value, parsed):
    """Compare every parsed field with exact types, including nested values.

    Dataclass equality alone would accept a forged bool in place of an int.
    Only types produced by the actual parser reach the equality operation.
    """
    if type(value) is not type(parsed):
        return False
    if type(parsed) is tuple:
        return (len(value) == len(parsed)
                and all(_same_value(a, b) for a, b in zip(value, parsed)))
    if type(parsed) in (RunRecord, ArtifactRef, Usage):
        return all(_same_value(getattr(value, field.name),
                               getattr(parsed, field.name))
                   for field in fields(parsed))
    return value == parsed


def _build(manifest_data, records):
    manifest = _object(parse_json_bytes(manifest_data), _TOP)
    _require(_text(manifest["format"]) == "offline-attempt-manifest/1")
    project = _text(manifest["project_id"])
    protocol = _text(manifest["protocol_revision"])
    attempts = manifest["attempts"]
    _require(type(attempts) is list and 1 <= len(attempts) <= _MAX_ITEMS)

    specs, by_run, attempt_ids, pairs = [], {}, set(), set()
    for item in attempts:
        item = _object(item, _ATTEMPT)
        spec = AttemptSpec(
            _text(item["run_id"]), _text(item["attempt_id"]),
            _text(item["replicate_id"]), _text(item["candidate_revision"]),
            _text(item["role"]),
        )
        _require(spec.role in _ROLES)
        pair = (spec.replicate_id, spec.role)
        _require(spec.run_id not in by_run and spec.attempt_id not in attempt_ids
                 and pair not in pairs)
        specs.append(spec)
        by_run[spec.run_id] = spec
        attempt_ids.add(spec.attempt_id)
        pairs.add(pair)
    for spec in specs:
        _require((spec.replicate_id, "baseline") in pairs
                 and (spec.replicate_id, "candidate") in pairs)

    supplied = {}
    for record in records:
        _require(type(record) is RunRecord)
        # Each record uses the actual parser's own default 1 MiB byte bound.
        reparsed = parse_run_record(record.data)
        _require(_same_value(record, reparsed))
        _require(record.run_id in by_run and record.run_id not in supplied)
        spec = by_run[record.run_id]
        _require(record.project_id == project
                 and record.protocol_revision == protocol
                 and record.run_id == spec.run_id
                 and record.attempt_id == spec.attempt_id
                 and record.replicate_id == spec.replicate_id
                 and record.candidate_revision == spec.candidate_revision)
        supplied[record.run_id] = record

    return AttemptInventory(
        data=manifest_data, sha256=sha256(manifest_data).hexdigest(),
        project_id=project, protocol_revision=protocol,
        slots=tuple(AttemptSlot(spec, supplied.get(spec.run_id)) for spec in specs),
    )


def build_attempt_inventory(
    manifest_data: bytes,
    records: tuple[RunRecord, ...],
    *,
    max_bytes: int = 1048576,
) -> AttemptInventory:
    """Bind exact records to every declared slot, retaining missing records.

    Exact builtin bytes/int/tuple only; the manifest cap is 1..1048576 and is
    enforced before decoding. At most 1024 attempts and 1024 records; every
    replicate declares exactly one baseline and one candidate. All manifest
    strings are nonempty UTF-8 <=4096 bytes without NUL or surrogates. Record
    fields must completely match reparsing, with exact nested types. Returned
    records retain caller identity, status, validity, usage and limitations.

    Refusals carry only fixed text, without our decoder/parser cause/context.
    Byte/item bounds are not full depth, CPU or memory isolation. No storage,
    network, authorization, evaluator, budget or research action is performed.
    """
    if (type(manifest_data) is not bytes or type(max_bytes) is not int
            or not 1 <= max_bytes <= _MAX_BYTES or len(manifest_data) > max_bytes
            or type(records) is not tuple or len(records) > _MAX_ITEMS):
        raise AttemptInventoryRefused(_MESSAGE)
    try:
        result = _build(manifest_data, records)
    except (ValueError, TypeError, AttributeError, RecursionError, OverflowError):
        pass
    else:
        return result
    # Leave the handler before raising: from None would still retain context.
    raise AttemptInventoryRefused(_MESSAGE)

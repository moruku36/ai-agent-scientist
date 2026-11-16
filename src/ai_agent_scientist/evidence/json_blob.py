"""Strict JSON decoding of exact bytes read from a trusted BlobStore.

Narrow internal helper profile: UTF-8 only, no BOM, no duplicate keys, no
non-finite numbers. No canonicalization, schema, admission or access logic.
The byte cap comes from BlobStore only; it is not a depth/CPU/memory limit.
Standard json may retain escaped unpaired surrogates: not I-JSON/JCS.
"""
from __future__ import annotations

import json
import math

from .blob_store import BlobStore

_BOM = bytes([0xEF, 0xBB, 0xBF])


class InvalidJSONBlob(ValueError):
    """Payload-free failure to decode verified bytes as strict JSON."""


def _unique_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:  # decoded code points, no normalization
            raise InvalidJSONBlob("duplicate object key")
        out[key] = value
    return out


def _reject_constant(_name):
    raise InvalidJSONBlob("non-finite number")


def _finite_float(text):
    value = float(text)
    if not math.isfinite(value):
        raise InvalidJSONBlob("non-finite number")
    return value


def parse_json_bytes(data: bytes) -> object:
    """Decode exact builtin bytes; raise InvalidJSONBlob on any violation."""
    if type(data) is not bytes:
        raise TypeError("data must be exact bytes")
    if data.startswith(_BOM):
        raise InvalidJSONBlob("byte order mark not allowed")
    try:
        text = data.decode("utf-8")
        return json.loads(
            text,
            object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except InvalidJSONBlob:
        raise
    except (ValueError, RecursionError) as exc:
        # Includes UnicodeDecodeError, JSONDecodeError and the int digit limit.
        raise InvalidJSONBlob("invalid JSON blob") from exc


def load_json_blob(store: BlobStore, sha256: str) -> object:
    """Read once from the store, then strictly parse. Storage errors propagate."""
    data = store.get(sha256)
    return parse_json_bytes(data)

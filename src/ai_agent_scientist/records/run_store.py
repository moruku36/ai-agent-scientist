"""Bounded exact-byte run-record storage in a trusted private BlobStore.

No registry, logical identity, authentication or evaluator authority. Storage
errors propagate unchanged; a failed write may already have committed. No retry.
"""
from __future__ import annotations

import re

from ai_agent_scientist.evidence.blob_store import BlobStore
from ai_agent_scientist.records.run_record import RunRecord, parse_run_record

__all__ = ["RunStoreRefused", "store_run_record", "load_run_record"]

_MAX_BYTES = 1_048_576
_MESSAGE = "run store refused"
_HASH = re.compile(r"[a-f0-9]{64}")


class RunStoreRefused(ValueError):
    """Fixed, value-free refusal of store, digest, cap or byte binding."""


def _validate_store(store: BlobStore, max_bytes: int) -> None:
    if (type(store) is not BlobStore or type(max_bytes) is not int
            or not 1 <= max_bytes <= _MAX_BYTES):
        raise RunStoreRefused(_MESSAGE)
    # get() has no per-call cap: bound its configured read before any I/O.
    cap = getattr(store, "max_blob_bytes", None)
    if type(cap) is not int or not 1 <= cap <= max_bytes:
        raise RunStoreRefused(_MESSAGE)


def store_run_record(
    store: BlobStore, data: bytes, *, max_bytes: int = 1048576
) -> RunRecord:
    """Parse before one put of the original bytes; verify its returned digest.

    Parser and storage exceptions propagate unchanged. A put failure or bad
    returned digest can follow a committed write; never retry or repair here.
    """
    _validate_store(store, max_bytes)
    record = parse_run_record(data, max_bytes=max_bytes)
    digest = store.put(data)
    if type(digest) is not str or digest != record.sha256:
        raise RunStoreRefused(_MESSAGE)
    return record


def load_run_record(
    store: BlobStore, sha256: str, *, max_bytes: int = 1048576
) -> RunRecord:
    """Validate before one bounded get, parse, then bind to the requested hash.

    A known-hash read is observation only, including after an uncertain write.
    Freely constructible parsed records confer no authority.
    """
    _validate_store(store, max_bytes)
    if type(sha256) is not str or _HASH.fullmatch(sha256) is None:
        raise RunStoreRefused(_MESSAGE)
    data = store.get(sha256)
    record = parse_run_record(data, max_bytes=max_bytes)
    if record.sha256 != sha256:
        raise RunStoreRefused(_MESSAGE)
    return record

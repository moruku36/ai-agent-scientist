"""Offline handoff payload binding, not admission or authorization.

The trusted caller supplies both concrete local stores independently of the
request and a current, caller-owned binding table. IDs are opaque dict keys;
they never select a store, path or URI. Metadata is a caller declaration, not
MIME sniffing or authentication. See docs/21-handoff-payload-binding.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import NoReturn

from ai_agent_scientist.admission.handoff_request import load_handoff_request
from ai_agent_scientist.evidence.blob_store import BlobStore

__all__ = ['PayloadBinding', 'InvalidHandoffBinding', 'load_bound_handoff_request']


@dataclass(frozen=True, slots=True)
class PayloadBinding:
    """Current trusted local declaration; validated anew on every load.

    All fields are mandatory. available=False includes revocation. The caller
    refreshes this table from its own current access state, outside candidate
    control, and serializes updates/reads. This is not an access credential.
    """

    id: str
    sha256: str
    media_type: str
    classification: str
    max_payload_bytes: int
    available: bool
    access_expires_at: datetime


class InvalidHandoffBinding(ValueError):
    """Fixed, value-free refusal before reading a referenced payload."""


def _bad() -> NoReturn:
    raise InvalidHandoffBinding('invalid handoff payload binding') from None


def load_bound_handoff_request(
    request_store: BlobStore,
    request_sha256: str,
    *,
    payload_store: BlobStore,
    bindings: dict[str, PayloadBinding],
    now: datetime,
) -> tuple[dict, bytes]:
    """Preflight one envelope, bind current metadata/access, read exact bytes.

    Exact BlobStore instances and a builtin dict with builtin string keys are
    required. The binding cap must equal the payload store's configured cap,
    so the existing bounded verified read enforces it before returning bytes.
    Storage/strict-JSON/request errors propagate unchanged. No writes, caches,
    authority flags, payload decoding or dispatch. Returned data is a snapshot,
    never a reusable access decision; invoke again for each new read.
    """
    if type(now) is not datetime or now.tzinfo is not timezone.utc:
        raise TypeError('now must be a UTC-aware datetime')
    if type(request_store) is not BlobStore or type(payload_store) is not BlobStore:
        raise TypeError('stores must be exact BlobStore instances')

    # Preserve the existing verified strict-JSON/request boundary and ordering.
    request = load_handoff_request(request_store, request_sha256, now=now)
    if type(bindings) is not dict or any(type(key) is not str for key in bindings):
        _bad()  # Guard keys before a lookup can invoke hostile equality hooks.
    reference = request['payload']
    binding = bindings.get(reference['id'])
    if type(binding) is not PayloadBinding:
        _bad()

    metadata = (binding.id, binding.sha256, binding.media_type, binding.classification)
    if any(type(value) is not str for value in metadata):
        _bad()  # Guard all values before any equality comparison.
    if metadata != tuple(reference[key] for key in ('id', 'sha256', 'media_type', 'classification')):
        _bad()
    cap = binding.max_payload_bytes
    store_cap = payload_store.max_blob_bytes
    if type(cap) is not int or cap < 1 or type(store_cap) is not int or store_cap != cap:
        _bad()
    expires = binding.access_expires_at
    if binding.available is not True:
        _bad()
    if type(expires) is not datetime or expires.tzinfo is not timezone.utc:
        _bad()
    if now >= expires:
        _bad()

    # Only the matched, trusted digest reaches the independently selected store.
    # BlobStore bounds the read and verifies SHA-256; its errors stay unchanged.
    return request, payload_store.get(metadata[1])

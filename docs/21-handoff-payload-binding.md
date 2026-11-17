# 21 Handoff Payload Binding (P1, Offline)

[日本語](21-handoff-payload-binding.ja.md) | [Home](../README.md)

**Status (2026-11-17): implemented; ten new P01–P10 unittest scenarios passed once offline (0.074s, Python 3.15.2).** Coordinator source review completed before the targeted invocation. Required design-check results are recorded separately. No historical tests were replayed. No research request was admitted, dispatched, reproduced or independently reviewed. Python 3.12 compatibility is a source target, not an executed-interpreter claim.

This bounded seam composes [20 request preflight](20-handoff-request-preflight.md) with [18 BlobStore](18-immutable-blob-helper.md). It implements only the local payload-binding portion of the [11 handoff contract](11-harness-boundaries.md), within the existing [architecture](03-architecture.md) and [roadmap](10-roadmap.md). The [canonical harness-handoff/1 schema](../schemas/handoff.schema.json) is unchanged.

## Explicit API

[Source](../src/ai_agent_scientist/admission/handoff_binding.py):

```python
load_bound_handoff_request(
    request_store, request_sha256, *, payload_store, bindings, now
) -> tuple[dict, bytes]
```

- Both stores must be exact `BlobStore` instances, selected and configured by the trusted caller independently of request content. Separate stores can have different envelope/payload caps. Subclasses and duck-typed adapters are deliberately excluded.
- `bindings` is a current, trusted builtin `dict[str, PayloadBinding]`. Every key must be an exact builtin string, including unrelated keys. A request's payload ID is only an opaque lookup key: it never becomes a path, URI, network destination, root or store selector. There is no resolver callback or fallback dereference.
- `PayloadBinding` is a frozen local dataclass. All seven fields are mandatory: `id`, `sha256`, `media_type`, `classification`, `max_payload_bytes`, `available`, `access_expires_at`. It is not a wire object or credential. The caller owns this table outside candidate control and scopes it to the intended store, project, recipient and purpose before calling.
- `now` must be an exact `datetime` with `tzinfo is timezone.utc`, supplied by the trusted caller for this invocation. There is no system-clock read. `access_expires_at` has the same exact UTC type requirement.
- The return is the detached ordinary request dictionary from existing preflight plus the exact immutable bytes returned by the actual payload `BlobStore.get`. It contains no binding record, cached access decision, admission/authorization flag or receipt. Payload bytes are not decoded or normalized.

## Refusal and read ordering

1. Reject invalid clock/store argument types before I/O, with fixed `TypeError` messages.
2. Call existing `load_handoff_request(request_store, request_sha256, now=now)` once. This preserves bounded, digest-verified envelope reads, [strict JSON](19-json-blob-reader.md), request shape and current envelope-expiry checks. Failure stops before binding lookup or payload reads.
3. Check table/key types before lookup, and selected binding/value types before comparisons. Require exact equality of all four reference fields: ID, SHA-256, media type and classification. No case folding or MIME inference.
4. Require an exact builtin integer `max_payload_bytes >= 1` (booleans excluded), equal to `payload_store.max_blob_bytes`. This new read-only property exposes the existing configured cap; it changes no storage behavior. A mismatched cap is refused rather than silently weakened. The caller prepares the correctly capped store; the request cannot choose it.
5. Require `available is True` and `now < access_expires_at`. Missing binding, revoked/unavailable binding, missing/invalid expiry, expiry equal to now and expired access all refuse before payload `get`, even when retained bytes still exist.
6. Only then call `payload_store.get(binding.sha256)` once. BlobStore enforces its cap while reading (at most cap+1 bytes) and verifies SHA-256 before returning. An oversized object raises the existing `BlobTooLarge`.

Every invocation repeats all checks and the actual verified reads; previous success does not confer continuing access. Binding failures raise `InvalidHandoffBinding(ValueError)` with the fixed public message `invalid handoff payload binding`, without displayed chaining. Envelope, strict-JSON and underlying storage exceptions propagate unchanged; I/O is never relabeled as missing or as a binding refusal. No store writes, repair, deletion, caching or evidence mutation occur. Tracebacks/context and upstream diagnostics remain private because they can retain inputs.

## Synthetic declaration example

The following JSON illustrates trusted caller metadata, **not** new fields in the handoff schema, live access state, MIME validation or authentication proof. The digest identifies empty bytes; the ID and metadata must exactly match the envelope's existing `payload` object. The caller constructs `PayloadBinding` with a UTC `datetime` for the expiry, not a JSON string. Merely decoding this example does not make it trusted.

```json
{
  "id": "payload-1",
  "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "media_type": "application/octet-stream",
  "classification": "synthetic",
  "max_payload_bytes": 32,
  "available": true,
  "access_expires_at": "2026-11-17T12:01:00Z"
}
```

For trusted `now=2026-11-17T12:00:00Z`, that expiry is current. At `12:01:00Z` it is refused even if the empty blob remains stored. A `text/plain` declaration can also match opaque non-text bytes: metadata is a trusted caller declaration, not content sniffing, schema validation or proof of access rights. Both envelope `synthetic` values remain structurally eligible and grant nothing.

## Scenarios executed once offline

[New test file](../tests/contracts/test_handoff_binding.py), ten methods total with deterministic subcases; no imports of historical tests:

| ID | Scenario |
|---|---|
| P01 | Real stores/envelopes, exact bytes and one read at each boundary; both synthetic flags, all classifications, declarations without MIME sniffing |
| P02 | Missing binding and independent substitution of ID, digest, media type or classification refuse before payload read |
| P03 | Prior success followed by revocation, expiry/equality, later injected time or binding removal; one-microsecond valid boundary |
| P04 | Missing/tampered envelope, malformed/duplicate JSON, non-request and expired request stop before binding/payload work |
| P05 | Actual missing/tampered payload and injected storage I/O error; errors propagate, evidence stays unchanged |
| P06 | Mandatory exact positive cap, store-cap mismatch, read-only cap property, empty/exact-cap success and actual cap+1 refusal |
| P07 | Hostile comparison/truthiness values, subclasses, invalid UTC access expiry and hostile table keys rejected safely |
| P08 | Invalid injected clock/store types refuse before envelope or payload I/O |
| P09 | URL/file/path/store-looking IDs only use a local table; inspect opened digest paths and forbid network helpers |
| P10 | Detached request/result bytes, fresh reads, no additional authority fields, tamper after prior success is detected |

After source review, the coordinator ran the targeted test command below exactly once. The required design checker uses the existing validation environment, not an installation. The implementer ran neither command:

```sh
env PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/contracts -p test_handoff_binding.py -v
python -B scripts/check_design.py
```

Do not replay the historical request/JSON/blob/budget tests. Record actual outcomes separately; authored cases and offline design checks establish no SCI runtime acceptance.

## Limits and caller duties

The caller supplies genuinely current access metadata, a trustworthy fresh UTC time and independently chosen stores. It must serialize table/store configuration changes across a call; this single-owner offline seam is not an atomic revocation service. It cannot detect a stale table, a lying trusted caller, clock rollback or revocation after the supplied instant. A returned snapshot is data, not durable authority; later use needs current checks under its actual policy. Caller-owned store instances/methods and roots/ancestors remain trusted under docs 18's POSIX assumptions.

There is no authentication, authorization proof, identity/revision check, durable admission, idempotency, reservation/budget authority, dispatch, evaluator/knowledge promotion, JCS or schema/wire-version change. Metadata equality does not prove MIME or payload semantics. There is no CPU/memory/depth isolation, concurrent-writer guarantee or new power-loss/recovery claim. Existing request-profile limits remain. Private access tables, real evidence, credentials and final answers stay outside this public repository. Rollback stops using this seam and preserves all blobs; it must not bypass current access checks.

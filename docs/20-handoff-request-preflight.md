# Handoff request preflight (P1, offline)

日本語: [20-handoff-request-preflight.ja.md](20-handoff-request-preflight.ja.md) · Back to [README](../README.md)

## Status

**Implemented and checked offline, 2026-11-17.** H01–H08 passed once (8 tests, 0.006s) on Python 3.15.2. Coordinator source review is not independent scientific reproduction or runtime acceptance. No actual request was admitted or dispatched.

## What it does

`ai_agent_scientist.admission.handoff_request` provides:

- `validate_handoff_request(value, *, now)` returns a detached ordinary `dict` for a structurally valid `harness-handoff/1` **request**.
- `load_handoff_request(store, sha256, *, now)` calls `load_json_blob` exactly once (verified bytes, strict UTF-8 JSON) and then validates the result.

`now` is a trusted, caller-injected `datetime` whose `tzinfo` is exactly `datetime.timezone.utc`. Anything else raises `TypeError` with a generic message.

## Checks (request subset only)

- Untrusted values must be exact builtin `dict`, `str`, `int`, `bool` or `None`. Subclasses are rejected, and `bool` is not accepted as a revision.
- All required top-level and payload keys are present, with no extras.
- `schema_version` is exactly `harness-handoff/1`. `kind` must be `request`; other kinds are explicitly rejected here.
- `attempt_id` and `in_reply_to` are `null`. `replicate_id` is `null` or a nonempty string.
- Identifier and reference strings are nonempty. `sender`, `recipient` and `classification` are checked against their enums. `expected_revision` is an integer >= 0.
- The payload digest must fully match `[a-f0-9]{64}`, and a trailing newline is rejected.
- Timestamps use the strict profile `YYYY-MM-DDTHH:MM:SS[.1-6 digits]Z`. There are no offsets, leap seconds or lowercase letters, and the calendar and clock must be valid.
- `created_at < expires_at` and `created_at <= now < expires_at`. Expiry equal to `now` is rejected.

All untrusted violations raise `InvalidHandoffRequest` (a `ValueError`) with a fixed, payload-free message. Chaining is suppressed, but tracebacks and frames may still hold untrusted data and stay sensitive.

## Not claimed

- **No authorization.** `synthetic` is accepted as `true` or `false`, and neither value authorizes anything. A structurally valid request is not approved dispatch.
- This is **not** a generic JSON Schema engine. The timestamp profile is narrower than the schema `date-time` format, and the fixed profile can drift from the authoritative schema, which is unchanged.
- There is no logical digest, JCS canonicalization, sender authentication, registry or receipt.
- It does no URL parsing, payload resolution, writes, schema fetching or network access.

## Caller duties

Authenticate the sender and resolve current authorization, reservation and payload permissions. Enforce idempotency, revisions and budget before dispatch. If any later authority check fails, discard the returned snapshot.

## Recovery

Storage, tamper and strict-JSON errors propagate unchanged. Validation is not reached and nothing is written. Evidence is preserved and the system fails closed.

## Verification and bounds

Executed once, no historical tests replayed:

```sh
env PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/contracts -p test_handoff_request.py -v
```

H01: valid real-store load and creation equality; H02: exact types and hostile equality hooks; H03: version/request bindings; H04: payload/enums/digest; H05: timestamp profile; H06: expiry/order/trusted clock; H07: real missing/tampered objects and malformed/duplicate JSON stop before validation; H08: detached copies, read-only bytes, sanitized public errors and no authorization flag.

The stored envelope is byte-bounded by BlobStore. Direct validation has no byte/string cap; caller bounds it. Neither entry point isolates CPU/memory/depth. The payload reference is structurally checked only: its target is not read, its media type is not verified, and it may be unavailable. Exact byte identity is preserved; no logical identity or deduplication is computed. Both synthetic values can pass even with unresolvable references. Do not use this snapshot after expiry without current authoritative checks. UTC clock trust and clock rollback remain caller responsibilities. Date parsing suppresses displayed chaining but exception context/frames may retain inputs; upstream errors retain their original diagnostics.

Sources: [P1 roadmap](10-roadmap.md), [handoff contract](11-harness-boundaries.md), [unchanged canonical schema](../schemas/handoff.schema.json), [strict reader](19-json-blob-reader.md). This internal profile intentionally accepts only initial requests, not every valid canonical envelope.

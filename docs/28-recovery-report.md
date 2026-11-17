# 28 Bounded Deterministic Private Recovery Report

> Increment28 coordinator checks: initial six-method run had five successes and one F04 fixture error: immutable-event deletion was correctly refused. A file-only test-fixture correction emulates a legacy missing event outside the trusted API; the sole targeted rerun passed all six F01–F06 methods (0.050s). Existing-environment design checker passed once (620 links, 36 language pairs); whitespace passed. Remaining NOT EXECUTED/pending text records worker authorship, not subsequent checks. Independent review is recorded separately; no runtime acceptance.

[日本語](28-recovery-report.ja.md) | [Home](../README.md) | [Roadmap](10-roadmap.md) | [27 Recovery triage](27-recovery-triage.md)

**Increment 28 status (2026-11-17): source and exactly six NEW self-contained unittest methods authored; NOT EXECUTED.** This is the third connected bounded offline increment. Previous coordinator banners cover their named earlier increments only. Files were read/edited only; no tests, checkers, builds, implementation imports, network, Git operations, model subcalls, processes or publication were performed. Execution, reproduction, independent review and runtime acceptance remain pending for increment 28.

[recovery_report.py](../src/ai_agent_scientist/admission/recovery_report.py) connects actual [triage](27-recovery-triage.md) to an immutable in-memory artifact. It creates no ledger, database, file, sender or public export. Existing [inspection](26-reservation-inspection.md), receipts, reservations, observations, schemas and canonical wire versions are unchanged.

## Small connected API

```python
artifact = build_recovery_report(
    trusted_receiver, after_request_id=None, limit=25, max_output_bytes=65536)
# artifact.data: bytes; artifact.sha256: lowercase SHA-256 of exactly those bytes
# artifact.after_request_id, limit, next_after_request_id, entry_count: frozen metadata
```

Use an **existing independently trusted receiver**. The builder calls actual `inspect_recovery_triages` exactly once, which calls one receiver page using one existing read transaction. Projection, serialization and hashing use that returned immutable view without a second lookup. There is no CLI or constructor invocation: opening a receiver invokes schema writes. The builder adds no filesystem operations, blob reads, clock sampling, process/network access, acknowledgements, writes or repairs. The delegated receiver performs its existing retained SQLite read and error handling.

Only the concrete receiver API is accepted; there is no caller-supplied report/snapshot/JSON intake. The caller, imports, receiver instance/methods, scope mapping and private SQLite state must remain outside candidate control. Exact types, consistent references and SHA-256 cannot self-authenticate a consistently fabricated history. Artifact dataclass construction is not a provenance API. This is **PRIVATE selected metadata**, not a proof, authority, authenticated receipt, admission result, canonical wire object or JCS.

## Explicit projection and diagnosis

The implementation enumerates each allowed field; it never dumps whole dataclasses. Each page entry retains:

| Section | Selected original facts |
|---|---|
| Receipt | Project/endpoints, request/message IDs, exact request/payload digests, current revision/state and retained timestamps |
| Reservation/accounting | Stable reservation reference, request ID/digest, original amount/time and full allocation/outstanding amounts |
| Current status/local ack | Exact event ID, request/reservation/digest/revision, status/amount/time; separate ack revision and nullable acknowledgement time |
| Latest usage observation | Exact sequence/observation ID, request/reservation/digest, original expected revision/time, nullable usage/over-cap and independent stopped/cleanup flags |
| Reasons | All connected triage reason strings in their original deterministic order, with no action/disposition |

No principal identity, shared owner namespace/envelope, authorization reference, global totals, cap, settled floor, remaining capacity, blob contents, DB path or exception detail enters the artifact. Reservation references and digests are diagnostic locators, never permissions. Event IDs and observation sequences are receiver-local: retain the association with the independently trusted originating receiver outside this artifact; it cannot discover or authenticate its source. No new source ledger is introduced.

Every returned reservation remains fully outstanding, including known zero, stopped execution, known cleanup and locally acknowledged status. An absent observation is JSON `null`; an UNKNOWN observation is an object with `worker_seconds:null` and `over_cap:null`. Known zero stays integer `0`; overruns remain exact. Missing current status stays `null` with unknown local ack. A local ack says nothing about remote delivery. Reasons remain descriptive and never authorize retry, release, dispatch, settlement or completion.

Selection means greatest **local insertion sequence** only, not latest timestamp, authoritative newest truth, complete history, cumulative usage or maximum usage. Older exact replay does not advance it; later-inserted UNKNOWN stays UNKNOWN. No observations are summed or deducted. Separate calls/pages can see later commits; the binary request-ID cursor is exclusive, not a lease or cross-page frozen snapshot. Restart from `None` to revisit changed entries or inserts behind a cursor. Empty/receipt-only scopes produce no reservation entries; absence grants no authority.

## Exact bytes, bounds and failure

The fixed explicit local-only version is `receiver-recovery-report-local/1`. Its serializer is Python standard-library `JSONEncoder` with `sort_keys=True`, `ensure_ascii=True`, `allow_nan=False` and `separators=(',', ':')`, encoded as UTF-8 with no BOM or trailing newline. Object keys sort lexically; arrays preserve receiver/reason order; strings use JSON ASCII escapes. Integer/null/bool facts retain their types. This exact recipe is deliberately not RFC 8785 JCS. A future serialization change requires an explicit local version change. SHA-256 hashes exactly `artifact.data` and is not embedded inside those bytes. Identical selected page facts and page parameters produce identical bytes/hash, including after reopening unchanged retained state; concurrent changes can alter later artifacts.

`max_output_bytes` is an exact builtin int in `1..1_048_576`; bool, subclasses and coercion are rejected before reading. The default and absolute cap are 1 MiB. Cursor and `limit` retain triage's exact validation and `1..100` page bound. Encoded chunks are checked before extending the private buffer; equality with the byte limit succeeds. Oversize raises value-free `RecoveryReportTooLarge`, discarding the whole artifact: no partial bytes, digest or success cursor is returned. There is no truncation or automatic smaller-page retry. This bounds output, not total database retention or all interpreter memory.

Receiver/storage/scope/triage failures propagate and return no successful artifact, including later-row failures; exception chains remain owner diagnostics and are never serialized. No failure becomes an empty/UNKNOWN success. Rollback means ceasing to call this builder and retaining authoritative state; there are no report writes to undo. Private handling and any later selected export follow the owner's actual authorization under [09](09-safety-publication.md); no automatic export is implemented.

## Mirrored synthetic local example

All values below are synthetic, not an actual artifact or verified history. This is the complete selected JSON shape, pretty-printed for reading; actual bytes follow the compact sorted recipe above. No canonical schema/example file is added or changed.

```json
{
  "local_report_version": "receiver-recovery-report-local/1",
  "visibility": "private",
  "observation_selection": "latest_local_insertion_only",
  "page": {"after_request_id": null, "limit": 1, "next_after_request_id": null},
  "entries": [{
    "receipt": {
      "project_id": "synthetic-project", "sender": "scientist", "recipient": "ctf",
      "request_id": "request-one", "message_id": "message-one",
      "request_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "payload_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "revision": 2, "state": "reconciliation_required",
      "recorded_at": "2026-11-17T12:00:00.000000Z",
      "updated_at": "2026-11-17T12:00:01.000000Z"
    },
    "reservation": {
      "budget_reservation_ref": "reserve-one", "request_id": "request-one",
      "request_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "worker_seconds": 20, "recorded_at": "2026-11-17T12:00:00.000000Z"
    },
    "accounting": {"allocation_worker_seconds": 20, "outstanding_worker_seconds": 20},
    "current_status": {
      "event": {
        "event_id": 2, "request_id": "request-one", "budget_reservation_ref": "reserve-one",
        "request_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "receipt_revision": 2, "status": "reconciliation_required", "worker_seconds": 20,
        "created_at": "2026-11-17T12:00:01.000000Z"
      },
      "ack_revision": 0, "acknowledged_at": null
    },
    "latest_usage_observation": {
      "sequence": 1, "observation_id": "observation-one", "request_id": "request-one",
      "budget_reservation_ref": "reserve-one",
      "request_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "expected_revision": 1, "worker_seconds": null, "execution_stopped": false,
      "cleanup_known": false, "over_cap": null, "observed_at": "2026-11-17T12:00:01.000000Z"
    },
    "reasons": [
      "reservation_fully_outstanding", "receipt_reconciliation_required", "local_ack_pending",
      "latest_insertion_view_only", "usage_unknown", "execution_not_independently_stopped",
      "cleanup_unknown"
    ]
  }]
}
```

## Exactly six NEW authored tests — NOT EXECUTED

[Self-contained unittest source](../tests/contracts/test_recovery_report.py) uses real temporary BlobStore/private SQLite fixtures and no historical test imports.

| ID | Authored coverage |
|---|---|
| F01 | Request → reserve → observation → actual triage → bytes; exact source references, allowlist omissions, immutable artifact/hash |
| F02 | Exact empty golden bytes, Unicode escaping, deterministic reopen/hash and absent blob access |
| F03 | Scoped real pagination/cursors, receipt-only exclusion, inserts behind cursor, exact types/bounds and sender refusal |
| F04 | No observation versus UNKNOWN/zero/over-cap, independent flags, local ack/missing status, insertion versus time/replay, full outstanding reservation |
| F05 | Exact byte boundary, strict capped types, whole-artifact refusal without partial return and no arbitrary intake |
| F06 | One real SQLite read transaction/connection, unchanged rows/files, no constructor/write, consistent page across a concurrent WAL commit, later-row conflict and real storage failure |

All execution and [design checks](../scripts/check_design.py) for links, language pairs, JSON examples and status consistency remain **pending, NOT EXECUTED** under the file-only instruction. These authored cases establish no passing result, recovery/reproduction outcome or independent review.

# 27 Conservative Receiver-Local Recovery Triage

> Increment27 coordinator checks: six NEW T01–T06 offline methods passed once (0.045s); existing-environment design checker passed once (594 links, 35 language pairs); whitespace passed. Subsequent NOT EXECUTED/pending statements are worker-only authoring history, not these coordinator results. Independent review recorded separately; no runtime acceptance.

[日本語](27-recovery-triage.ja.md) | [Home](../README.md) | [Roadmap](10-roadmap.md) | [26 Reservation inspection](26-reservation-inspection.md)

**Status (2026-11-17): source, exactly six NEW dedicated self-contained unittest methods and documentation authored; NOT EXECUTED.** This is the second of three connected bounded offline increments. Only checkout files were read/edited. Tests, checkers, implementation imports, builds, network, Git operations, model calls, publication and process execution were not performed. Coordinator checks, execution, reproduction, independent review and runtime acceptance remain pending. Earlier validation banners concern earlier increments only.

[recovery_triage.py](../src/ai_agent_scientist/admission/recovery_triage.py) composes the actual [26 inspection APIs](26-reservation-inspection.md) over retained [22 receipts](22-durable-handoff-receipt.md), [23 reservations](23-local-budget-reservation.md), [24 local status/ack](24-local-status-outbox.md) and [25 observations](25-local-usage-observations.md). It adds a conservative description of evidence gaps. It is **not admission, readiness, dispatch, settlement, authorization, process control or a recovery executor**. It issues no retry, completion or release decision. Canonical wire versions, schemas and earlier receiver behavior are unchanged.

## Small local API

```python
report = classify_reservation(snapshot, scope=independently_trusted_scope)
report = inspect_recovery_triage(receiver, 'request-one')
page = inspect_recovery_triages(receiver, after_request_id=None, limit=25)
```

`classify_reservation` is pure and deterministic: no storage, clock sampling, process, network or authority lookup. It requires an exact `ReservationSnapshot` and exact `TrustedHandoffScope`. It returns a frozen, slotted `RecoveryTriageReport(snapshot, reasons)`. `snapshot` is the entire validated input, including the original full `DurableReservation`, receipt, allocation accounting, current status/ack and latest inserted observation. It is not an abbreviated accounting claim. There is no action/disposition field.

The connected functions require an exact `DurableHandoffReceipts`, not a duck-typed adapter or candidate report. They read its existing trusted scope internally. The single function calls the actual `inspect_reservation` exactly once; missing and receipt-only return `None`, which is different from a reservation with no observation. The page function calls `inspect_reservations` exactly once and classifies that page, without composing individual reads. A frozen, slotted `RecoveryTriagePage(entries, next_after_request_id)` retains its bounded tuple and cursor. API-produced reports have at most nine distinct fixed reason strings; pages have at most 100 reports. Direct dataclass construction is not a validation or provenance API.

## Machine-readable reasons, in deterministic order

| Reason | Meaning in this retained view |
|---|---|
| `reservation_fully_outstanding` | Always present; allocation and outstanding both equal the entire reservation |
| `receipt_recorded` / `receipt_reconciliation_required` | Exact retained unresolved receipt state; neither is work authority |
| `current_status_missing` | No event for the current receipt revision; no fallback to an older event |
| `local_ack_unknown` | Current status is missing, so its local ack cannot be described |
| `local_ack_pending` / `local_acknowledged` | Current event has local ack revision 0 / 1; no transport or remote delivery claim |
| `no_observation` | No retained observation; distinct from a retained UNKNOWN observation |
| `latest_insertion_view_only` | An observation exists; local insertion selects this view only |
| `usage_unknown` | No observation or observation usage is `None`; never coerced to zero |
| `usage_known_zero` / `usage_known_positive` | Exact retained integer usage; zero is explicit, positive may exceed allocation |
| `execution_not_independently_stopped` | No observation or independently supplied stopped flag is false |
| `cleanup_unknown` | No observation or independently supplied cleanup-known flag is false |
| `observed_over_cap` | Retained known usage exceeds this reservation's fixed allocation |

Order is reservation, receipt, status/ack, observation presence/view, usage, stopped gap, cleanup gap, over-cap. Missing status includes both missing-status and unknown-ack reasons. All reasons describe local retained facts or gaps; absence of a gap is not a positive recovery verdict. Even known zero with both flags true and a local ack leaves the entire reservation outstanding. No shared totals, owner identity, cap, settled floor, remaining capacity or summed observations are returned or calculated.

## Exact validation and trust

Malformed or internally inconsistent snapshots raise the value-free `InvalidRecoverySnapshot`, before returning a summary. Exact dataclass/builtin types reject subclasses, coercion, bool-as-int and equality-hook objects. Identifiers are nonempty exact strings of at most 1024 UTF-8 bytes, without NUL/invalid Unicode; digests are exactly 64 lowercase hex characters. Integers fit `0..2**63-1`, with positive allocations and local identities; flags are exact bools. Stored timestamps must be canonical microsecond UTC strings and valid calendar values; no fresh clock or expiry decision is introduced.

Validation binds receipt/reservation/status/observation principal, project, recipient, request, sender and envelope digest to each other and to the independently trusted scope. It checks reservation references, authorization/message/observation identifiers, payload digest shape, the revision/state pair, full allocation/outstanding equality, current status revision/kind/amount, ack revision/timestamp pairing and ack ordering. Observations require receipt revision 2, original expected revision 1 or 2, valid sequence/identity, independent flags, UNKNOWN/over-cap pairing and an exact over-cap comparison. Revision-1 observation time equals the reconciliation transition time; revision-2 observation time cannot precede it. Reservation/event creation timestamps are not used to invent an ordering across independently supplied caller clocks or legacy attachment/backfill.

The page also validates its exact container/bounds, strict binary UTF-8 request-ID order after the supplied cursor, non-reused reservation/digest/message/event/observation identities and cursor binding to the last returned entry. One bad later entry yields no partial successful page. Receiver scope/accounting/storage errors propagate unchanged. Classification does not repair storage or translate a failure into UNKNOWN success.

These checks reject **inconsistent forgery**, not a consistently fabricated history. Digests identify exact bytes, not provenance. Pure classification cannot prove that a snapshot came from SQLite or that an observation is true. Use connected inspection with independently controlled receiver/scope/DB and observations; the caller, imports, receiver instance/methods, scope mapping, schema and SQLite files must remain outside candidate control. The receiver's existing private local trust assumptions apply; same-UID hostile code is not isolated by frozen dataclasses. There is no wire intake, authentication, signature verification or evaluator receipt here.

## Concurrency, retention and recovery limits

Each connected call uses the receiver's one existing read transaction. Classification occurs over the returned immutable snapshot after that transaction closes; concurrent commits can already supersede the view. Separate calls/pages are independent. Request-ID seek pagination is not a durable lease or a multi-page frozen scan; restart from `None` to revisit changed rows or rows inserted behind the cursor. The connected layer performs no writes, ack, CAS, migration or additional snapshot lookup.

Latest means **greatest local insertion sequence**, not authoritative newest truth, greatest timestamp, cumulative metering, a maximum over all observations or reconciliation of contradictory facts. Older exact replay does not advance insertion. A later UNKNOWN observation stays UNKNOWN despite earlier known usage. Reports retain only the receiver's selected observation; they do not claim a complete observation history. Stopped/cleanup flags are retained independent observations, not live process inspection. No fencing, cancellation, resource measurement, lease reconciliation, backup/restore, cross-DB identity guarantee or distributed recovery is implemented.

Rollback consists of ceasing to use triage and using the existing inspection APIs while preserving all receipts, unresolved reservations, events, acks and observations. There are no triage writes to undo and no new schema to roll back. On an error, retain the authoritative DB and investigate independently; do not reset it or treat failure/absence as a budget reduction. Total DB size, operation/disk budgets, private report handling and retention remain owner duties. No pruning, deletion, export, scheduling or publication path is added.

## One synthetic projection

This single illustrative case is mirrored in Japanese. It is an abbreviated local display, **not a new canonical wire/schema object**, authenticated observation or protected verification receipt. All values are synthetic. The actual Python report retains every nested snapshot field, including the entire reservation; this display omits scope, bindings and timestamps for readability.

```json
{
  "request_id": "request-one",
  "reservation_worker_seconds": 20,
  "outstanding_worker_seconds": 20,
  "latest_observation_id": "observation-unknown",
  "latest_worker_seconds": null,
  "reasons": [
    "reservation_fully_outstanding",
    "receipt_reconciliation_required",
    "local_ack_pending",
    "latest_insertion_view_only",
    "usage_unknown",
    "execution_not_independently_stopped",
    "cleanup_unknown"
  ]
}
```

## Exactly six NEW methods — NOT EXECUTED

[test_recovery_triage.py](../tests/contracts/test_recovery_triage.py) is dedicated and self-contained, with real temporary BlobStore/private SQLite fixtures and no imports from old tests.

| ID | Authored coverage |
|---|---|
| T01 | Missing/receipt-only, deterministic pure and connected output, frozen full retention, reopen, absent blobs, no writes |
| T02 | Known zero versus UNKNOWN, separate stopped/cleanup flags, over-cap and unchanged full accounting |
| T03 | Direct reconciliation, insertion versus timestamp, old replay, current local ack and missing current event |
| T04 | Real scoped pages/cursors, concrete receiver calls, bounds/exact types, sender refusal and no global totals |
| T05 | Pure malformed/forged snapshots: exact types, scope/digest/reference/revision/status/accounting/observation and ack consistency |
| T06 | One real read transaction, no writes, later-row accounting/ack failure and actual SQLite failure with no partial success |

All test execution and [design checks](../scripts/check_design.py), including links, language pairs, JSON examples and status consistency, are **pending and NOT EXECUTED** under the file-only instruction. Coordinator verification is separate. No pass, runtime/recovery outcome, reproducibility or independent-review result is claimed. The third increment is outside this change.

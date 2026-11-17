# 26 Receiver-Scoped Reservation Inspection and Recovery Snapshots

[日本語](26-reservation-inspection.ja.md) | [Home](../README.md) | [Roadmap](10-roadmap.md) | [25 Usage observations](25-local-usage-observations.md)

**Status (2026-11-17): implementation and exactly six new self-contained unittest methods authored; NOT EXECUTED.** This is the first of three bounded offline increments, limited to retained inspection. Files were read and edited only. No tests, checkers, implementation imports, builds, network, Git operations, model calls, processes, services or publication were performed. Execution, reproduction, independent review and runtime acceptance remain pending for this increment. Historical validation of earlier helpers does not validate these APIs.

The [implementation](../src/ai_agent_scientist/admission/durable_handoff.py) connects the existing [22 receipt](22-durable-handoff-receipt.md), [23 reservation and fixed accounting](23-local-budget-reservation.md), [24 outbox](24-local-status-outbox.md) and [25 immutable observations](25-local-usage-observations.md). Existing observation recording/replay and reconciliation behavior is reused. Canonical schemas and wire versions are unchanged. There is no settlement, release, retry, dispatch, transport or authority resolver.

## Local API and frozen views

```python
snapshot = receiver.inspect_reservation('request-one')
page = receiver.inspect_reservations(after_request_id=None, limit=25)
if page.next_after_request_id is not None:
    following = receiver.inspect_reservations(
        after_request_id=page.next_after_request_id, limit=25)
```

`inspect_reservation` returns one exact retained `ReservationSnapshot`, or `None` when this scope has no reservation for that request ID. Receipt-only rows return `None`; inspection never attaches a reservation. The page API returns a frozen, slotted `ReservationSnapshotPage` with a tuple of `entries` and `next_after_request_id`. Each frozen, slotted `ReservationSnapshot` contains:

| Field | Retained meaning |
|---|---|
| `receipt` | Current `DurableReceipt`, including unresolved revision/state |
| `reservation` | Original exact-bound `DurableReservation` |
| `accounting` | Frozen `ReservationAccounting`: this reservation's fixed allocation and full outstanding worker-seconds |
| `current_status` | `LocalStatusEntry` for the current receipt revision, including its separate local ack; `None` if no such event is retained |
| `latest_usage_observation` | Original `LocalUsageObservation` with greatest local insertion sequence for this reservation, or `None` if absent |

Missing events can occur in older databases with no backfilled outbox history. Inspection does not synthesize events or fall back to a previous revision's event. An ack is receiver-local bookkeeping, not remote delivery or a reservation release.

## One read transaction and UNKNOWN semantics

Each API opens exactly one existing `_transaction(write=False)` (`BEGIN`). Reservation selection, current receipt, fixed envelope accounting, current revision event/ack, and latest observation are read through that same connection and SQLite snapshot. A page has one consistent view across all returned entries; composing separate inspection APIs would not provide that property. Separate pages and separate calls can see later commits. The existing private SQLite trust, path checks, timeout, commit/close error handling and owner-only chained diagnostics apply; see [22](22-durable-handoff-receipt.md#transactions-failures-and-local-trust).

Latest means **latest inserted**, not greatest `observed_at`. Exact replay of an older observation does not advance its insertion sequence. Observations are independent facts: inspection does not sum them, choose a maximum usage, subtract usage from outstanding, or infer spend. No observation is distinct from an observation whose `worker_seconds=None`; both lack known usage. An UNKNOWN latest observation stays UNKNOWN even after an earlier known observation. Known zero remains integer zero with its original flags. Overruns stay unmodified. Neither stopped execution nor known cleanup implies settlement.

Accounting reads the actual singleton's fixed arithmetic and validates the reservation allocation against it. It returns only `allocation_worker_seconds` and `outstanding_worker_seconds`, both equal to the entire original allocation. **No global totals are exposed:** no owner namespace, envelope identity, shared cap, settled floor, shared reserved total, remaining capacity, other-scope reservation list or count. Shared accounting is not mislabeled as a scope total. The API does not enumerate other scopes or derive totals from observations. The fixed settled floor and shared reserved counter are never changed.

## Scope, bounds and failures

The receiver's independently trusted `TrustedHandoffScope` fixes principal/project/recipient. Retained reservation, receipt, status and observation sender mappings are checked; a changed sender mapping raises `ReceiptScopeError`, rather than creating another namespace. Another principal/project/recipient sees only its own rows. Candidate workers must remain outside the caller, DB, evaluator, authorization and budget-write boundaries. Scope declaration remains a caller duty, not authentication implemented here.

Request IDs and non-null cursors must be exact builtin nonempty strings, at most 1024 UTF-8 bytes, without NUL or invalid Unicode. Subclasses and coercion are refused. The cursor is an exclusive request-ID seek position using SQLite binary ascending order, not insertion/time order or a global row number. It may name a missing row; it is not a credential. `after_request_id=None` starts a scan. `limit` is an exact builtin integer in `1..100`, excluding bool and subclasses. Fixed SQL binds all supplied values.

The page fetches at most `limit+1` scoped reservation rows to detect a following page, and constructs at most `limit` snapshots. `next_after_request_id` is the last returned request ID only when another row exists in this transaction; otherwise it is `None`. Empty pages have no next cursor. New reservations inserted behind a previous cursor and changes to previously returned rows require a new scan from `None`. Pagination is not a durable scan lease or a cross-call frozen database view. An internal request/sequence index bounds latest-observation lookup to the selected request; total DB retention and operation/disk budgets remain owner duties.

Binding/accounting inconsistencies raise `ReceiptConflict`. Filesystem/SQLite failures use `ReceiptStorageError`; commit/close failure returns no successful snapshot. A later-row failure aborts the whole page without returning partial entries. These reads do not repair state. No blob access, request expiry check, current authority lookup or fresh clock is required to inspect retained metadata after expiry. A returned snapshot grants no continuing blob access, work, replay, budget or evaluation authority.

## Synthetic local projection

This illustrative projection is not a new wire object or an evaluation/usage receipt. All identifiers and values are synthetic; omitted nested fields are described above. The Python API returns dataclasses, not this abbreviated JSON.

```json
{
  "request_id": "request-one",
  "receipt_revision": 2,
  "receipt_state": "reconciliation_required",
  "accounting": {
    "allocation_worker_seconds": 20,
    "outstanding_worker_seconds": 20
  },
  "latest_usage_observation": {
    "sequence": 2,
    "worker_seconds": null,
    "execution_stopped": false,
    "cleanup_known": false,
    "over_cap": null
  },
  "next_after_request_id": null
}
```

## Exactly six authored methods — NOT EXECUTED

[Dedicated self-contained unittest file](../tests/contracts/test_reservation_inspection.py) uses real BlobStore and private temporary SQLite fixtures, importing no old tests.

| ID | Authored coverage |
|---|---|
| I01 | Exact lookup/reopen, ordered bounded scoped pages, cursor exhaustion, frozen views and no global/owner disclosure |
| I02 | Missing and receipt-only rows, no observations, current event and retained-only inspection with unavailable blobs |
| I03 | Known zero versus UNKNOWN, overrun and cleanup flags; entire reservation stays outstanding |
| I04 | Direct reconciliation, current revision/ack, latest insertion versus timestamp, older replay and no observation sum |
| I05 | Principal/project/recipient isolation, sender refusal, exact identifier/cursor/limit types and byte boundaries |
| I06 | One read transaction/connection per page, no data writes, later-row accounting conflict and real SQLite read failure without partial success |

Test execution and [design checks](../scripts/check_design.py), including links, language pairs, JSON examples and status consistency, remain pending, **not run** under the file-only instruction. No runtime, recovery, reproducibility, durability or independent-review outcome is claimed. Further increments remain outside this change.

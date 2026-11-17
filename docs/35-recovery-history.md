# 35. Selected reservation status history

[日本語](35-recovery-history.ja.md) | [README](../README.md) | [24 Local status outbox](24-local-status-outbox.md) | [26 Reservation inspection](26-reservation-inspection.md) | [34 Recovery acknowledgement](34-recovery-ack.md)

**Scientist24, file-only (2026-11-17), extending the supplied Scientist23 pin `56d3be6`: source, exactly six NEW self-contained offline unittest methods and paired docs authored; NOT EXECUTED.** The pin is caller-supplied and was not checked with git. No tests, checks, implementation imports, builds, network, git, model/API calls or research runs were executed for this increment. Execution, reproduction, independent review and runtime acceptance remain pending. Earlier results do not validate this increment; document number 35 is separate from the Scientist label.

[durable_handoff.py](../src/ai_agent_scientist/admission/durable_handoff.py) adds one receiver-local read seam. The global event feed cannot atomically pair a selected request's current reservation snapshot with its older event acknowledgements. In particular, [Scientist23's separate read and ack CAS](34-recovery-ack.md#separate-read-and-event-ack-cas) can acknowledge an OLD event while a NEW current event remains pending. This seam exposes that retained relationship in one SQLite read snapshot. It adds no action or authority.

## One selected read transaction

```python
history = receiver.inspect_reservation_status_history(
    'req-1', after_event_id=0, limit=100,
)
```

The frozen, slotted `ReservationStatusHistory` has exactly three fields:

```python
snapshot: ReservationSnapshot
entries: tuple[LocalStatusEntry, ...]
next_after_event_id: int | None
```

Before opening a transaction, the method validates the request ID with the existing exact-string guard: nonempty, at most 1024 UTF-8 bytes, no NUL or invalid Unicode. `after_event_id` must be an exact builtin integer in `0..2**63-1`, using the existing revision guard. `limit` must be an exact builtin integer in `1..100`. Bools, subclasses and coercion are refused. Existing value-free identifier/revision/limit exceptions propagate.

One existing `_transaction(write=False)` performs the actual selected reservation lookup using bound request ID and trusted principal/project/recipient. Missing and receipt-only requests return `None`. A retained reservation is passed to the existing `_reservation_snapshot` on that same connection. Thus receipt, reservation, current event/ack, latest usage observation and full outstanding allocation retain their existing inspection semantics.

The same transaction reads event history through the existing fixed SQL helper, extended only with an optional bound request filter. The query selects that exact request and trusted scope, LEFT JOINs separate local acknowledgements, includes both ACKED and pending events, seeks strictly above `after_event_id`, orders by ascending local `event_id` and fetches at most `limit + 1` rows. It never calls the global inspection API or independently opens a second snapshot. Existing callers of the private SQL helper retain their defaults and behavior. No unrelated request is returned or materialized as a history entry. This is a request-filtered SQL read using existing indexes; no new query-plan or performance guarantee is claimed.

Only the first `limit` entries are returned. `next_after_event_id` is the **last returned event ID only if an extra row exists**; otherwise it is `None`, including when the result contains exactly `limit` events. The extra row supplies only continuation evidence and is not returned as an entry. Seeking beyond the last event returns the selected current snapshot with an empty tuple and no next cursor.

## Historic binding and acknowledgement consistency

Each returned historic event must match the selected receipt/reservation's exact request ID, digest, principal, project, recipient, sender, budget reference and worker seconds. The revision/status pair must be exactly revision 1 / `reservation_retained` or revision 2 / `reconciliation_required`, with revision no newer than the selected current receipt. Older facts are checked against their own revision/status pair, rather than incorrectly requiring the current receipt's status.

Each returned acknowledgement revision must be an exact integer 0 or 1. Pending revision 0 requires no acknowledgement timestamp. Revision 1 requires a string timestamp no earlier than the event's creation, following the existing stored UTC-string ordering. Sender mismatch raises the existing value-free `ReceiptScopeError`; other historic binding or ack inconsistency raises value-free `ReceiptConflict`. Existing snapshot/scope/storage errors propagate. A malformed retained entry fails the whole call; no partial history, repair, fallback or retry is returned.

This is validation of retained local bindings under the [existing private SQLite trust assumptions](22-durable-handoff-receipt.md#transactions-failures-and-local-trust), not authentication or protection against a hostile database owner, modified trusted code/schema, or consistently fabricated history. Rows outside the selected request/scope or before the seek position are not audited by this bounded history page. Missing current status in a legacy fixture remains `snapshot.current_status is None`; an older entry is never substituted as current.

## Seek semantics and truthful interpretation

The snapshot and all returned history entries describe the same SQLite read transaction, including when another connection commits during that transaction in WAL mode. Another page is an independent snapshot; the cursor is a seek position, not a durable scan lease or consumption token. An older event's acknowledgement may change without changing its ID. **Restart at zero to revisit changed acknowledgements.** The result can already be superseded after its transaction ends.

`None`, an empty page and an absent current status never establish delivery, completion, settlement or a drained queue. ACKED means only a separate receiver-local ack row exists. The method neither acknowledges nor retries anything, and it leaves every reservation fully outstanding regardless of usage, cleanup, receipt revision or ack state. Frozen values prevent ordinary mutation; they are freely constructible values, not capabilities or independently verified receipts.

Illustrative abbreviated JSON, mirrored in Japanese, uses synthetic private values. It is not a new wire/schema format; the actual return includes the full existing snapshot and event records.

```json
{
  "snapshot": {
    "receipt": {"request_id": "req-1", "revision": 2},
    "current_status": {"event_id": 2, "ack_revision": 0},
    "accounting": {"allocation_worker_seconds": 20, "outstanding_worker_seconds": 20}
  },
  "entries": [
    {"event_id": 1, "receipt_revision": 1, "status": "reservation_retained", "ack_revision": 1},
    {"event_id": 2, "receipt_revision": 2, "status": "reconciliation_required", "ack_revision": 0}
  ],
  "next_after_event_id": null
}
```

This shows OLD ACKED and NEW pending together, without labeling the request acknowledged or complete. With `limit=1`, the first page contains event 1 and cursor 1; the next seek contains event 2 and no cursor. A later seek above event 2 still returns the current snapshot with no history entries.

## Authored coverage and boundaries

[test_recovery_history.py](../tests/contracts/test_recovery_history.py) contains exactly six new self-contained unittest methods. Private temporary SQLite/BlobStore fixture code is copied locally; no old test class is imported and all values are synthetic.

| ID | Authored coverage |
|---|---|
| H01 | Exact frozen/slotted bounded history and current snapshot, OLD ack/NEW pending, read-only DB/blob bytes, full outstanding budget |
| H02 | Strict exclusive seek, limit 1/2/100, extra-row versus exact-end cursor, gaps, other request/scope isolation, independent pages and restart for changed ack |
| H03 | Malformed exact scalar types, subclasses, Unicode, byte/integer bounds refused before any transaction; valid boundary reads |
| H04 | Real missing, receipt-only, beyond-end, legacy missing current event and entirely missing event history, with selected snapshot retained |
| H05 | Historic sender/digest/reference/seconds/revision/status and ack corruption, valid earlier entry followed by malformed history, whole-read refusal and unchanged DB/files |
| H06 | One real read connection/transaction and fixed request-filtered SQL; real WAL concurrent commit between snapshot and history; consistent old view then fresh OLD ack/NEW pending; propagated errors, real SQL failure, read-exit failure, no constructors or retries |

No schema, migration, store, index, write path, transport, authorization, evaluator, settlement, retry, clock sampling or default change is added. Candidate workers remain outside authorization and budget-write boundaries. No schedules, communication, services, publication or external runs are introduced. Existing wire versions and all existing receipts/reservations/events remain unchanged. To stop using the seam, retain the database and use the existing inspection APIs; no rollback or deletion is needed.

All six tests, link/language-pair/JSON/status checks, [design checker](../scripts/check_design.py), runtime and reproducibility checks are **NOT EXECUTED and pending**, as required by the explicit file-only instruction. Source authorship is not a passing, reproduced, independently reviewed or accepted result.

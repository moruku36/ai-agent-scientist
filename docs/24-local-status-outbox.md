# 24 Transactional Receiver-Local Reservation Status Outbox


**Outbox coordinator verification (2026-11-17): O01–O06 passed once offline, 0.046s; required design checker passed once (504 links, 32 language pairs). Original selected worker timed out at 600s; no task_complete/final, completion UNKNOWN, no replay. Authored/not-executed wording below records worker-only activity, not current coordinator check status. No live acceptance.**

[日本語](24-local-status-outbox.ja.md) | [Home](../README.md)

**Status (2026-11-17): implementation and exactly six new offline unittest scenarios authored; NOT EXECUTED.** Based on reviewed commit `d3245b42dafb0438ebd5a0065e930a3f759004f5`. File reads/edits only: no tests, checkers, implementation imports, builds, network, installs, services, models, research or dispatch. No runtime acceptance, reproduction, independent review, remote delivery or measured durability is claimed. Earlier helper results do not validate this increment.

This narrow P1 increment extends [23 reservations](23-local-budget-reservation.md) at the actual [22 receipt](22-durable-handoff-receipt.md) transaction seam in [durable_handoff.py](../src/ai_agent_scientist/admission/durable_handoff.py), implementing only local outbox bookkeeping from [11](11-harness-boundaries.md#4-delivery-leases-and-cancellation). The existing APIs and return types remain intact. This base calls the connected receipt/reservation API `reserve`, not `record_and_reserve`. Canonical receipts retain exactly two unresolved states: `recorded` revision 1 and `reconciliation_required` revision 2.

## Atomic facts and stable identity

The same existing `BEGIN IMMEDIATE` that creates/attaches the receipt, retains the reservation and debits its fixed worker-seconds envelope appends one immutable `LocalStatusEvent`. Revision 1 says only `reservation_retained`. A successful `require_reconciliation` CAS appends revision 2, `reconciliation_required`, in the transaction updating the receipt **only if a matching reservation already exists**. Receipt-only `record` and receipt-only reconciliation create neither reservation nor event. Events describe retained reservation/reconciliation only; they confer no admission, dispatch, attempt, completion or verification status.

The unique key is `(principal, project_id, recipient, request_id, receipt_revision)`, also unique by `(budget_reservation_ref, receipt_revision)`. Each event retains the trusted sender mapping, reservation reference, verified exact-byte request digest, worker-seconds and creation instant. Sender is checked against `TrustedHandoffScope`; changing sender cannot create another namespace. `event_id` is an ascending integer local to this authoritative database, not a wire identity or credential.

Every `reserve` replay still performs the fresh loader/binding/authority checks from 23 and returns the original reservation and current receipt. Its event remains the same through inspection: no duplicate, timestamp reset, second debit or acknowledgement reset. Reconciliation replay preserves both events. SQL uniqueness and serialized writers enforce deduplication; event UPDATE/DELETE triggers reject mutation. Acknowledgements are stored separately.

Opening a preceding-version DB creates empty outbox tables without backfilling history. A fresh authorized replay of an older retained reservation can append its missing **current** revision event in that transaction, timestamped at that call. A later reconciliation can likewise record its current revision. Neither invents a missing earlier event or past delivery. This local schema addition is not a general migration/repair facility; canonical schemas and wire versions remain unchanged.

## Bounded inspection and acknowledgement CAS

```python
pending = receiver.inspect_status_events(after_event_id=0, limit=25)
all_local = receiver.inspect_status_events(limit=25, pending_only=False)
ack = receiver.acknowledge_status_event(
    pending[0].event.event_id, expected_ack_revision=0, now=fresh_utc_now,
)
```

Inspection returns a tuple of frozen `LocalStatusEntry(event, ack_revision, acknowledged_at)` values in ascending `event_id` order. Reads are restricted to the independently trusted principal/project/recipient and checked sender mapping. They expose retained metadata only, including after authority/access expiry, and grant no blob access or continuing authority. `limit` must be an exact builtin integer in `1..100`, `after_event_id` an exact builtin integer in `0..2**63-1`, and `pending_only` an exact bool (default true); bool/integer subclasses are not accepted as integers. The exclusive cursor does not consume or acknowledge anything. Restart at zero to find older pending events after interruption. Cross-scope ID gaps are normal.

Absent acknowledgement means revision 0 and null time. `acknowledge_status_event` requires a positive bounded exact integer event ID, exact expected acknowledgement revision 0, and exact UTC datetime no earlier than event creation. `BEGIN IMMEDIATE` serializes the scoped lookup and one acknowledgement insert at revision 1. Missing, foreign, stale or repeated acknowledgement raises `ReceiptRevisionError`; changed sender mapping raises `ReceiptScopeError`. Acknowledgement is per event, not a request-wide cursor or status overwrite. Acknowledging revision 2 before revision 1 cannot regress the receipt or clear another pending event/scope.

Acknowledgement means **receiver-local bookkeeping only**. It never asserts remote receipt/delivery, resolves UNKNOWN usage, releases reservations, changes accounting, settles/refunds usage, or grants retry/dispatch. No sender, daemon, polling loop, transport, callback, delivery attempt or remote acknowledgement is implemented.

## Synthetic local snapshot

Illustrative JSON, not a canonical wire object. The API returns frozen dataclasses; identifiers and digest below are synthetic.

```json
{
  "event": {
    "event_id": 1,
    "principal": "trusted-local-principal",
    "project_id": "p1",
    "recipient": "ctf",
    "request_id": "r1",
    "sender": "scientist",
    "budget_reservation_ref": "b1",
    "request_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "receipt_revision": 1,
    "status": "reservation_retained",
    "worker_seconds": 20,
    "created_at": "2026-11-17T12:00:00.000000Z"
  },
  "ack_revision": 0,
  "acknowledged_at": null
}
```

## Failure, bounds and uncertainty

Event-write failure rolls back the entire active receipt/reservation/accounting transaction or reconciliation transition, leaving no orphan event. Acknowledgement-write failure rolls back its own transaction. A post-commit commit/close error remains an uncertain observed outcome: preserve the DB, reopen and inspect the original identity before replay through current checks. Lost reservation response retains both charge and pending event. Lost local acknowledgement response can leave revision 0 pending or revision 1 acknowledged depending on commit; neither releases budget. No distributed atomicity or power-loss guarantee is claimed.

Events contain fixed metadata only: existing identifiers are bounded to 1024 UTF-8 bytes, request digests to 64 characters and worker-seconds to signed-63 integers. Two receipt revisions and uniqueness bound each reservation to at most two events and two acknowledgement rows. Pages contain at most 100 entries. The owner must still budget total rows, disk/journal space and operations; no total quota, pruning/reset/release API is supplied. The [22 private SQLite trust assumptions](22-durable-handoff-receipt.md#transactions-failures-and-local-trust) apply. Candidate workers cannot control the caller, scope, DB/schema/triggers, authority, evaluator or budget-writing boundary. This is not hostile-DB or same-UID attacker defense.

Historical UNKNOWN outcomes remain unresolved. This increment performs no currency measurement, reconciliation, settlement or refund. Full admission, money accounting, leases/fencing, logical/JCS identity, dispatch and delivery remain outside this increment. Existing runtime/authentication/configuration/defaults, guards, reviewers and inactive examples are unchanged.

## Exactly six authored scenarios — not executed

[Dedicated unittest file](../tests/contracts/test_local_status_outbox.py), self-contained with real temporary BlobStore/SQLite and no historical test imports:

| ID | Authored coverage |
|---|---|
| O01 | Actual loader → receipt → reserve; exactly one matching event |
| O02 | Replay/reopen preserve identity, timestamps and accounting |
| O03 | Injected event-write failure atomically rolls back new/existing-envelope transactions |
| O04 | Reconciliation next event/failure rollback/stale CAS without orphan; receipt-only reconciliation invents nothing |
| O05 | Bounded ordered scoped inspection, scoped ack CAS, immutable events and no scope/status regression |
| O06 | Lost commit acknowledgement/reopen retain reservation/pending; failed/lost local ack cannot release budget |

All six are authored, not executed. File review considered links, language pairs, JSON examples and status consistency; the [design checker](../scripts/check_design.py) and all runtime checks were **not run** under the file-only instruction. No passing result is claimed.

# 23 Local Durable Worker-Seconds Reservation Prerequisite

[日本語](23-local-budget-reservation.ja.md) | [Home](../README.md)

**Status (2026-11-17): implemented; ten R01–R10 scenarios passed once offline (0.082s).** The selected worker authored the files; the coordinator reviewed the full diff and ran the targeted scenarios once. The original worker call timed out at 600 seconds, without task_complete or a durable final; worker completion is unverified and was not replayed. No acceptance, reproduction, independent review or measured durability claim is made.

This narrow P1 prerequisite extends the actual [22 durable receipt](22-durable-handoff-receipt.md) transaction seam, using the actual [21 bound loader](21-handoff-payload-binding.md) and [17 pure arithmetic](17-budget-preflight.md). It reserves **worker-seconds only**. Architecture, schemas, wire versions, inactive examples, runtime settings and historical budgets remain unchanged. Historical allocations and unresolved outcomes remain untouched.

## Ownership and fixed namespace

[Source](../src/ai_agent_scientist/admission/durable_handoff.py) adds frozen, slotted `WorkerSecondsEnvelope`, `WorkerSecondsAuthority`, `DurableReservation` and `ReservedHandoff`, plus `ReservationRefused` and `DurableHandoffReceipts.reserve`. The existing `record`, `inspect` and reconciliation APIs keep their receipt-only behavior and return types.

An independent trusted receiver caller selects the private authoritative DB, authenticates the principal outside this module, and supplies current authority, bindings, stores and a fresh UTC instant on **every** reserve call. There is no authentication implementation or current-authority service lookup here. Candidate workers must not control this caller, its mappings, database or envelope. References are lookup keys, never bearer credentials.

The exact builtin dictionary key is:

```python
(principal, project_id, sender, recipient, authorization_ref, budget_reservation_ref)
```

The first four fields come from the trusted `TrustedHandoffScope`; the endpoints/project and both references are checked against the freshly verified actual request. A matching key must resolve to an exact `WorkerSecondsAuthority` whose `available is True` and whose exact UTC `expires_at` is later than `now`. Missing mappings, revocation or expiry refuse duplicates too. The caller refreshes this independent mapping and serializes changes to authority, bindings and stores throughout the call, including the wait for the SQLite lock. A stale caller snapshot or dishonest supplied clock is not detectable generally.

**One authoritative DB owns exactly one fixed envelope**, shared by every legitimate principal/project/sender/recipient/reference using that budget. Its singleton row binds `owner_namespace`, `envelope_id`, cap, settled floor and all four arithmetic inputs. Those values become immutable upon the first successful reservation and stay fixed across reopen. They cannot be changed by changing a principal, sender, reference or envelope name. Use this same DB for all scopes sharing that budget; choosing another file, deleting rows or copying an old DB would defeat accounting. The caller's budget ownership namespace is independent of receipt identity and must not be derived from sender-controlled input. This implementation supplies no reset, migration or refund operation.

The trusted caller supplies one fixed uniform allocation independently of the payload:

`required = (planned_attempts + max_retries) * per_attempt_seconds + evaluation_cleanup_seconds`.

The actual pure preflight is reused. Retry allowance is aggregate, and evaluation/cleanup is included. Each distinct reservation consumes this same fixed allocation. There is **no protocol/plan semantic resolver**: payload contents, declared caps and enabled flags do not establish authority or prove the allocation covers a real plan. All arithmetic fields and intermediate results must be exact builtin integers within SQLite's nonnegative signed-63 range (`0..2**63-1`), with positive cap, attempts and per-attempt seconds. Bool/subclasses/coercion are refused. Overflow is rejected conservatively before SQL binding; settled must not exceed cap.

## Local API and retained example

```python
envelope = WorkerSecondsEnvelope(
    owner_namespace='budget-owner', envelope_id='fixed-study',
    cap_worker_seconds=50, settled_worker_seconds=10,
    planned_attempts=1, max_retries=1, per_attempt_seconds=8,
    evaluation_cleanup_seconds=4,
)
current_authorities = {
    (scope.principal, scope.project_id, scope.sender, scope.recipient, 'a1', 'b1'):
        WorkerSecondsAuthority(envelope, True, authority_expires_at),
}
result = receiver.reserve(
    request_store, verified_envelope_sha256,
    payload_store=payload_store, bindings=current_payload_bindings,
    authorities=current_authorities, now=fresh_utc_now,
)
# result.receipt is the current unresolved DurableReceipt.
# result.reservation is the immutable retained DurableReservation.
```

This illustrative JSON is local retained metadata, **not a new wire schema or admission receipt**. The corresponding verified request must actually contain `a1`/`b1` and the mapped endpoints. No operational authority is stored in this public example.

```json
{
  "budget_reservation_ref": "b1",
  "authorization_ref": "a1",
  "principal": "trusted-local-principal",
  "project_id": "p1",
  "recipient": "ctf",
  "request_id": "r1",
  "sender": "scientist",
  "request_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "worker_seconds": 20,
  "recorded_at": "2026-11-17T12:00:00.000000Z"
}
```

In that arithmetic example, settled 10 plus two distinct reservations of 20 exhausts cap 50. Different legitimate scopes consume the same singleton counter. The cap, floor and allocation are deliberately fixed, rather than a live settlement ledger.

## Connected transaction and duplicates

Every `reserve`, including duplicates, runs the real fresh bound loader: bounded SHA-256-verified exact envelope bytes, strict JSON/request checks and expiry, current payload metadata/access, and the real bounded verified payload read. Payload bytes are discarded. The envelope identity remains its original exact bytes; whitespace, field order and transport changes are not canonicalized. This is the partial local docs11 profile, **not logical JCS identity or authenticated admission**.

One `BEGIN IMMEDIATE` transaction checks the immutable envelope, reservation/request collisions and remaining capacity, then inserts or attaches the receipt, creates the reservation and debits the singleton counter atomically. The constraint is `settled_floor + retained_reservations + new_charge <= fixed_cap`. No missing authority, insufficient capacity, invalid inputs or conflict creates a receipt, reservation or envelope accounting row. Constructor table initialization is allowed and creates no budget rows.

A `budget_reservation_ref` is globally unique within this authoritative DB, across authorization refs and receipt scopes. It permanently binds authorization ref, scope/sender, request ID, exact envelope digest and charge. A request receipt key can have only one reservation; global envelope-digest uniqueness also blocks reserving identical bytes under another principal. Reusing a stable reference for unrelated work, changing references for the same request, or changing fixed envelope/allocation conflicts. Distinct requests require distinct stable reservation references. The database is not a logical duplicate detector for requests deliberately issued with entirely different identities/bytes; all such accepted requests still consume the shared cap.

An exact duplicate returns the current retained unresolved receipt and original reservation, even at exhausted capacity, with no second debit, timestamp reset or revision reset. Current authority/access/expiry must still pass. `record` alone continues to reserve nothing. A receipt-only `recorded` row may acquire a reservation atomically only for the same freshly verified exact bytes, with no existing request/ref/digest reservation collision and no same-digest receipt in another scope. A receipt-only `reconciliation_required` row is ambiguous and refuses attachment. No recovery inference about past work is made.

Reconciliation changes only the receipt revision/state; it retains the entire charge. UNKNOWN is unresolved usage and supplies **no refund, retry or dispatch API**. No settlement, release, cancellation, completion, outbox, runner or admission API is added. `ReservedHandoff` is retained metadata and grants no work/replay authorization.

## Failures, trust and remaining work

The original [22 private authoritative SQLite trust profile](22-durable-handoff-receipt.md#transactions-failures-and-local-trust) applies, including owner-only POSIX paths, trusted schema/triggers/processes/ancestors/sidecars, no hostile DB defense or file replacement, one-second lock timeout and `synchronous=FULL`. Fixed SQL and bound values are used. The DB contains only private accounting/identity/digest metadata, no payload/envelope bodies or credentials. Owner-managed row/disk limits remain necessary.

Commit/close failures never return success. An active transaction is rolled back where possible; a committed-but-unacknowledged transaction may retain the full charge. Preserve the DB and inspect/reconcile; do not assume failure means unused capacity. A subsequent `reserve` goes through all fresh checks and can return retained metadata, never replay authorization. No refund/reset follows ambiguity. Commit/reopen is not a demonstrated power-loss guarantee. A caller must not build dispatch from these metadata returns.

Missing dimensions include money, tokens, GPU, memory/disk, elapsed-time enforcement, live settlement, fencing and run/manifest/protocol reconciliation. This is not full SCI-01/04/05/20 reservation/admission acceptance or a research runtime. No general plan mapping, JCS, authorization backend or protocol change is supplied.

## Scenarios passed once offline

[Self-contained scenario file](../tests/contracts/test_budget_reservation.py) has at most ten new methods and imports no historical tests:

| ID | Authored coverage |
|---|---|
| R01 | Real connected reads, pure arithmetic call, independent scoped current authority/ref matching |
| R02 | Settled baseline, exact exhaustion, different requests, insufficient first request writes nothing |
| R03 | Shared capacity across legitimate scopes; namespace/envelope changes cannot reset it |
| R04 | Exact-byte conflicts, changed refs, stable ref collision and cross-principal aliases |
| R05 | Exact receipt-only attachment, reopen/duplicate and current reconciliation state with retained charges |
| R06 | Immutable owner/envelope/cap/floor and every arithmetic input across reopen |
| R07 | Invalid/exact/bounded types, overflow and signed-63 boundary with no partial writes |
| R08 | First and duplicate revocation, expiry, current mapping/access and actual tampered payload reads |
| R09 | Late insert rollback, existing charge preservation, lost commit acknowledgement and retained charges |
| R10 | Real separate-connection concurrent duplicate and competing capacity transactions |

The coordinator ran the focused scenarios once within the authorized allocation: all ten passed in 0.082s. Required design/schema check results are retained separately in the coordinator record. Existing earlier helper results remain historical and do not validate this extension.

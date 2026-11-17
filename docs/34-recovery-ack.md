# 34. Explicit current recovery status acknowledgement

[日本語](34-recovery-ack.ja.md) | [README](../README.md) | [24 Local status outbox](24-local-status-outbox.md) | [27 Recovery triage](27-recovery-triage.md) | [31 Recovery operator](31-recovery-operator.md) | [33 Preview application](33-recovery-apply.md)

**Scientist increment23, file-only (2026-11-17): source, exactly six NEW self-contained unittest methods and paired documentation authored; NOT EXECUTED.** No tests, checks, implementation imports, builds, network, git, models, APIs or research runs were executed for this increment. Execution, reproduction, independent review and runtime acceptance remain pending. Earlier coordinator results do not validate these files. Document number 34 is separate from the Scientist increment label and from [23 budget reservations](23-local-budget-reservation.md).

[recovery_ack.py](../src/ai_agent_scientist/admission/recovery_ack.py) connects one actual selected triage inspection to the existing receiver-local event acknowledgement CAS. It follows the explicit trusted-caller action pattern of [31](31-recovery-operator.md), using [27](27-recovery-triage.md) over actual [26 reservation inspection](26-reservation-inspection.md) and [22 durable receipts](22-durable-handoff-receipt.md). The helper constructs no receiver, opens no separate store and adds no schema, dependency, wire version, CLI, transport, clock sampling, retry or automatic action. Candidate workers remain outside the caller, scope, receiver, authorization, evaluator and budget-writing boundaries.

## Selection is a read snapshot

```python
selected = select_current_recovery_status(receiver, 'req-1')
```

An exact request ID is validated before the read. The selector calls the actual `inspect_recovery_triage(receiver, request_id)` exactly once. That dependency requires an exact concrete `DurableHandoffReceipts` and validates its independently trusted scope and the full receipt/reservation/event bindings. No duck-typed adapter, supplied report, receiver constructor or second inspection is used. Existing receiver and triage failures propagate.

Missing requests, receipt-only requests and reservations with no current-revision status event return `None`. There is no fallback to a pending older event. An already acknowledged current event remains selectable with `ack_revision=1`; selection performs no acknowledgement.

The frozen, slotted `RecoveryStatusSelection` copies exactly six selected fields: `request_id`, `request_sha256`, `receipt_revision`, `event_id`, `event_receipt_revision`, `ack_revision`. It is freely constructible, replaceable and neither validated provenance nor authority. Frozen storage prevents ordinary mutation of that instance; it cannot authenticate a caller, receiver, history or human intent. Event IDs are local to the authoritative database. Keep the independently trusted receiver fixed between selection and action; this value does not bind a database identity or authorize a different receiver.

## Explicit scalar action

```python
selected = select_current_recovery_status(receiver, 'req-1')
if selected is not None:
    # A trusted caller separately chooses this action; selection never invokes it.
    acked_event = acknowledge_current_recovery_status(
        receiver,
        request_id=selected.request_id,
        expected_request_sha256=selected.request_sha256,
        expected_receipt_revision=selected.receipt_revision,
        expected_event_id=selected.event_id,
        expected_ack_revision=selected.ack_revision,
        now=injected_utc_now,
    )
```

The generic action deliberately accepts explicit keyword expectations rather than a selection dataclass as a capability. Its return type is the existing `LocalStatusEntry`.

1. Before any read, require exact builtin scalar types. Request IDs are nonempty strings of at most 1024 UTF-8 bytes, without NUL or invalid Unicode. Digests are exactly 64 lowercase hexadecimal characters. Expected receipt revision and event ID are integers in `1..2**63-1`; expected ack revision must be the exact integer `0`. Bool, integer/string subclasses and coercion are refused. Invalid scalars raise value-free `RecoveryAckRefused` before inspection.
2. Select once through the actual triage path, independently of any earlier selection. Require the selected request ID, request digest, receipt revision, current event ID and ack revision to equal the explicit expectations. Additionally bind the selected event's receipt revision to the expected receipt revision and require pending ack revision 0. Actual triage already binds event identity/digest/scope to the receipt and reservation. Missing, receipt-only, current-status-missing, stale, already acknowledged or forged identity expectations raise `RecoveryAckRefused('recovery acknowledgement refused')` before write delegation. A pending old event cannot be acknowledged by supplying its ID against a newer current receipt/event.
3. Delegate **once** to `receiver.acknowledge_status_event(selected.event_id, expected_ack_revision=0, now=now)`. Preserve its scoped acknowledgement CAS, time validation, error types and returned value. No catch/retry, fallback, post-write inspection or second acknowledgement is added.

`now` is injected and passed unchanged. The existing receiver requires an exact UTC-aware `datetime` whose `tzinfo` is `timezone.utc`, no earlier than the selected event's creation. Time validation occurs in the delegated method after selection; a bad clock can therefore follow a successful read, but cannot insert an acknowledgement. Receiver scope/storage errors, `InvalidRecoverySnapshot`, `ReceiptRevisionError` and clock errors propagate without conversion to success or UNKNOWN.

## Separate read and event-ack CAS

The fresh triage inspection is one read transaction. The acknowledgement is a **separate event-ack CAS transaction**, checking only the selected event's acknowledgement revision. These do not form an atomic current-receipt/current-event check-and-ack.

- A receipt/event change completed before the action's inspection makes old identity expectations stale and refuses before delegation.
- A competing acknowledgement after inspection wins its own CAS; this action's one delegation raises the existing `ReceiptRevisionError`. The competitor's change remains; this action adds no second acknowledgement.
- A new receipt revision and status event committed **after inspection but before acknowledgement** do not invalidate the old event's still-pending ack revision. This action can successfully acknowledge the **OLD event**, while the **NEW current event stays pending**. The receipt, new event and all reservations remain retained.

**The result identifies the ACKED EVENT, NOT current state, delivery or settlement.** Do not label successful return as "current request acknowledged", "queue drained", "delivered", "completed" or "settled". The helper intentionally performs no additional read to make such a claim. Any subsequent inspection is another independent snapshot, which may itself already be superseded.

All budget allocations and full outstanding reservations remain unchanged, including UNKNOWN usage and cleanup. Acknowledgement changes only the existing event's separate local ack row, never the receipt, immutable event, observations, authorization, settled floor or shared reserved counter. It neither stops work nor grants admission, dispatch, retry, release or verification authority.

## Synthetic values and the race outcome

Illustrative JSON only, mirrored in Japanese; no new wire/schema format. Identifiers/digest are synthetic. The selection is a local private value, not a public export or protected verification receipt.

```json
{
  "request_id": "req-1",
  "request_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "receipt_revision": 1,
  "event_id": 1,
  "event_receipt_revision": 1,
  "ack_revision": 0
}
```

If revision 2 appears after the action's fresh inspection, the following abbreviated projection is a possible successful outcome. The Python return retains the entire old `LocalStatusEvent` inside `LocalStatusEntry`; the separately inspected current view below is not part of that return.

```json
{
  "returned_acked_event": {
    "event_id": 1,
    "receipt_revision": 1,
    "ack_revision": 1,
    "acknowledged_at": "2026-11-17T12:00:02.000000Z"
  },
  "separately_inspected_current": {
    "receipt_revision": 2,
    "event_id": 2,
    "event_receipt_revision": 2,
    "ack_revision": 0
  },
  "outstanding_worker_seconds": 20
}
```

## Errors, retention and authored coverage

`RecoveryAckRefused` is a value-free refusal before any acknowledgement delegation. Delegated failures are different: a post-commit response/close error may leave the selected event acknowledged. Preserve the authoritative DB and inspect independently after uncertainty; never reset accounting or retry automatically. No rollback API, acknowledgement deletion, backfill, migration, repair, pruning, scheduling, publication or external communication is introduced. The [existing private SQLite trust assumptions](22-durable-handoff-receipt.md#transactions-failures-and-local-trust) apply, including trusted code/imports/receiver methods/schema and no defense against hostile same-UID code or consistently fabricated history. To stop using this increment, use the existing inspection APIs while retaining all facts and acknowledgements.

[test_recovery_ack.py](../tests/contracts/test_recovery_ack.py) contains exactly six NEW self-contained methods with copied real private temporary SQLite/BlobStore fixtures and no imports from historical test classes:

| ID | Authored coverage |
|---|---|
| K01 | Frozen exact selection, one actual read, revision 1 and 2 action paths, one ack delegation, entire DB unchanged except ack rows, full budget/observations/other request retained |
| K02 | Malformed exact scalar types, UTF-8/hash/integer bounds and subclasses refused before reads; valid 1024-byte ID boundary |
| K03 | Stale/forged digest, receipt revision, old/other event and ack expectations refused; no dataclass capability; actual triage rejects forged event receipt revision |
| K04 | Real missing/receipt-only/current-status-missing/already acknowledged states; legacy missing event emulated outside trusted API; no fallback to old pending event |
| K05 | Competing ack CAS fails once; injected new receipt/event after inspection permits truthful OLD-event result while NEW current remains pending, full budget retained |
| K06 | Injected invalid/backward time, unchanged errors, no retries/constructor, concrete receiver enforcement, real commit followed by lost response |

All six methods, link/language-pair/JSON/status checks, [design checks](../scripts/check_design.py), runtime checks and reproducibility checks are **NOT EXECUTED and pending** under the explicit file-only instruction. No passing, reproduced, independently reviewed or accepted runtime result is claimed.

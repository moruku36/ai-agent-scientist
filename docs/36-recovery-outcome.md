# 36. Bounded recovery action outcome inspection

[日本語](36-recovery-outcome.ja.md) | [README](../README.md) | [Scientist22 application](33-recovery-apply.md) | [Scientist23 acknowledgement](34-recovery-ack.md) | [Scientist24 history](35-recovery-history.md)

**Scientist25, file-only (2026-11-17): source, exactly six self-contained unittest methods and paired docs authored; NOT EXECUTED.** The supplied Scientist24 pin `45d7fea` was not verified with git. No tests, checks, implementation imports, builds, network, git, model/API or research execution was performed. Execution, reproduction, independent review and runtime acceptance remain pending; earlier results do not validate these files.

[recovery_outcome.py](../src/ai_agent_scientist/admission/recovery_outcome.py) closes the inspection gap after an uncertain/lost response from [22's application module](../src/ai_agent_scientist/admission/recovery_apply.py) or [23's acknowledgement module](../src/ai_agent_scientist/admission/recovery_ack.py). It composes the actual `inspect_reservation_status_history` added by [24](35-recovery-history.md) in [durable_handoff.py](../src/ai_agent_scientist/admission/durable_handoff.py). It dispatches neither action. Blind replay is forbidden; **no classification recommends or permits replay**.

Each function requires the exact concrete `DurableHandoffReceipts`. The caller must keep its independently trusted receiver/database/scope fixed from intent creation through inspection. Event IDs are local to that database; neither a preview hash nor a selection authenticates or selects a receiver. The [private SQLite trust assumptions](22-durable-handoff-receipt.md#transactions-failures-and-local-trust) include trusted imports, code, methods, schema and filesystem ownership. This is not protection against hostile same-UID code, a hostile database owner or consistently fabricated history. Candidate workers remain outside evaluator, authorization and budget-write authority.

## Validate intent before reading

```python
view = inspect_reconciliation_outcome(receiver, preview)
view = inspect_acknowledgement_outcome(receiver, original_pending_selection)
```

Only exact `ReconciliationPreview` / `RecoveryStatusSelection` dataclass types and exact builtin scalar types are accepted; subclasses, bool-as-int and coercion are refused. Both request IDs must be nonempty strings, at most 1024 UTF-8 bytes, with no NUL or invalid Unicode. Request digests must be exactly 64 lowercase hexadecimal characters.

The preview must contain exact `bytes` of length `1..1048576`, a matching exact-byte SHA-256 in lowercase hex, and exact integer `expected_revision=1`. Its bytes are never parsed. **Full preview equality is not checked here**: no preview rebuild occurs. Valid shape/hash is not provenance, human confirmation or authority.

The selection must describe an original pending intent: exact integer receipt revision 1 or 2, event ID in `1..2**63-1`, event receipt revision equal to the intended receipt revision, and exact integer ack revision 0. An already-acked selection with ack revision 1 is refused as an unspent intent, even though the selector can return it. Keep the original pending selection to inspect its retained outcome.

Malformed intents raise value-free `RecoveryOutcomeRefused('recovery outcome refused')` before any storage read. An invalid receiver type raises value-free `TypeError`. Neither refusal produces a successful view.

## One actual history transaction

Reconciliation calls `receiver.inspect_reservation_status_history(request_id, after_event_id=0, limit=1)` exactly once. Acknowledgement calls it exactly once with `after_event_id=selection.event_id-1, limit=1`. The actual [24 history seam](35-recovery-history.md) supplies both the complete current reservation snapshot and bounded history in **one SQLite read transaction**. There is no global feed read or independent current-state read.

The returned actual snapshot is validated by existing pure [classify_reservation](../src/ai_agent_scientist/admission/recovery_triage.py), with `scope=receiver._scope`, without another read. A differing selected request ID or current request digest raises the same dedicated value-free refusal, returning no view. Existing storage, history binding, scope and triage errors propagate unchanged; no catch-to-success, retry, fallback or partial output is added. Missing/receipt-only history has no reservation snapshot to validate and yields the classification below.

| Action | Classification | Local meaning only |
|---|---|---|
| Either | `missing_or_receipt_only` | No selected reservation snapshot; no conclusion about completion |
| Reconciliation | `receipt_still_recorded` | Matching receipt is revision 1 / recorded; **not proof safe to replay** |
| Reconciliation | `reconciliation_transition_observed` | Matching local state advanced to revision 2; **causality unproven** |
| Acknowledgement | `target_event_not_found` | Seek is empty or its event ID/intended receipt revision does not match |
| Acknowledgement | `target_ack_pending` | Exact intended event remains locally pending |
| Acknowledgement | `target_ack_retained` | Exact intended event has a retained local ack |

A real usage observation or another caller can create the same reconciliation transition as the attempted application. Revision 2 therefore does not prove that this attempted action caused it, returned successfully or executed work. Recorded state does not establish a safe retry window.

The acknowledgement inspector never borrows a later event's acknowledgement. It requires both exact target event ID and intended event receipt revision before returning pending/retained. The same snapshot's exact current event ID is compared with the intended target ID for `target_event_is_current`. If current status is missing, the flag is `None` (unknown), even when an old target ack is retained. `False` means a different current event ID was observed; it is not a delivery finding.

## Immutable observations and limitations

The frozen, slotted `RecoveryActionOutcome` contains exactly `action`, `classification`, `request_id`, `request_sha256`, the actual full `snapshot: ReservationSnapshot | None`, `target_status: LocalStatusEntry | None`, and `target_event_is_current: bool | None`. Action names are `mark_reconciliation_required` and `acknowledge_status_event`. Reconciliation has no specific event target, so both target fields are `None`; missing/receipt-only results also have no target. An unmatched acknowledgement target has `target_status=None` while the current-ID comparison still describes the selected snapshot. There is no execution-success, delivery, settlement or retry-permission boolean. Frozen values are freely constructible observations, not capabilities.

Illustrative abbreviated JSON only, mirrored in Japanese; no new wire format. Actual Python values retain the entire snapshot and targeted entry. This OLD ack / NEW pending view does not label a request delivered or complete.

```json
{
  "action": "acknowledge_status_event",
  "classification": "target_ack_retained",
  "request_id": "req-1",
  "request_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "snapshot": {
    "receipt": {"revision": 2},
    "current_status": {"event_id": 2, "ack_revision": 0},
    "accounting": {"allocation_worker_seconds": 20, "outstanding_worker_seconds": 20},
    "latest_usage_observation": null
  },
  "target_status": {"event_id": 1, "receipt_revision": 1, "ack_revision": 1},
  "target_event_is_current": false
}
```

The snapshot may already be superseded after its transaction ends. A local ack never establishes remote delivery. Entire reservations remain fully outstanding; UNKNOWN usage/cleanup stays UNKNOWN, never zero or released budget. No receiver construction, clock sampling, action dispatch, write, settlement, scheduling, transport, publication, dependency or wire-version change is introduced. Preserve the authoritative database and the original intent after uncertainty; this read supplies no replay recommendation or new authority.

[test_recovery_outcome.py](../tests/contracts/test_recovery_outcome.py) copies real private temporary SQLite/BlobStore fixtures locally, without historical test-class imports. Exactly six authored methods cover:

| ID | Coverage authored, not executed |
|---|---|
| Q01 | Recorded view; real application commit then lost response; retained full budget |
| Q02 | Real UNKNOWN usage observation and another caller create the same noncausal revision-2 classification; opaque bytes |
| Q03 | Real ack commit then lost response; OLD ack / NEW pending race and retained historical selection |
| Q04 | Real missing/receipt-only, wrong ID/revision, target missing, digest refusal; strict malformed intents before read and valid boundaries |
| Q05 | One actual history call/connection/read transaction, correct nonzero seek, pure triage, no independent/global reads/actions/constructor, entire DB/files unchanged |
| Q06 | Same storage/triage error objects, no retries/constructor, concrete receiver, actual pure triage refusal, frozen/slotted outputs and legacy current-missing fixture |

All six methods, link/language-pair/JSON/status checks, [design checker](../scripts/check_design.py), runtime and reproducibility checks are **NOT EXECUTED and pending** under the explicit file-only instruction. Source authorship is not a passing, reproduced, independently reviewed or accepted result.

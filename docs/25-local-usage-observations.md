# 25 Immutable Receiver-Local Worker-Seconds Observations

> Coordinator validation, 2026-11-17 (round3 only): six NEW U01–U06 scenarios passed once (1.183s); existing-venv design checker passed once (534 links, 33 language pairs). Independent review pending. Later authored/NOT EXECUTED wording below is historical worker-file-only status, not current coordinator validation. Round2 original raw check receipts remain unavailable; do not infer their verification from round3.

[日本語](25-local-usage-observations.ja.md) | [Home](../README.md) | [Roadmap](10-roadmap.md) | [24 Local outbox](24-local-status-outbox.md)

**Authoring status (2026-11-17): implementation and exactly six self-contained unittest methods authored; NOT EXECUTED.** Scientist round3 is based on independently source-reviewed round2 `bf4743970dc48e0e89e2717a2e07c2591c8db129`, as supplied by the coordinator. That review concerns the base, not this increment. Only files were read/edited: no tests, checkers, implementation imports, builds, model calls, network, git mutations, installs, services or dispatch. Coordinator checks are pending. No execution, reproduction, independent review, runtime acceptance or measured durability is claimed for round3.

This narrow P1 increment connects [23 retained reservations](23-local-budget-reservation.md), the existing [22 reconciliation transition](22-durable-handoff-receipt.md) and [24 local status outbox](24-local-status-outbox.md) in [durable_handoff.py](../src/ai_agent_scientist/admission/durable_handoff.py). It retains observations only. **Every reservation remains fully outstanding forever through these APIs; the fixed envelope's settled floor and reserved counter never change here.** Known zero usage, independently stopped execution and known cleanup do not release anything. There is no settlement, refund, completion, admission, process metering or authentication implementation.

## Independently trusted local caller

The caller independently establishes the principal/project/sender/recipient mapping, selects the same authoritative private DB and observes usage, whether execution has stopped, and whether cleanup is known. `TrustedHandoffScope` remains a caller declaration, not authentication. Candidate workers must not control this caller, observations, mappings, DB/schema/triggers, authorization, budget writer or evaluator. A wire sender string, report or reference is not independent evidence. There is no arbitrary sender observation API, wire extension, transport, callback or process inspection.

The [22 private SQLite assumptions](22-durable-handoff-receipt.md#transactions-failures-and-local-trust) apply, including trusted local processes and journal/sidecar paths. Immutability triggers prevent accidental edits through this schema; they do not defend against a hostile DB or same-UID attacker. No current authority/blob lookup is needed to retain local metadata after expiry; this grants no continuing access or authority. `reserve` keeps all its existing fresh binding/authority checks.

## Explicit local API and exact replay

```python
observation = receiver.record_usage_observation(
    'observation-one', request_id='request-one',
    budget_reservation_ref='reserve-one', request_sha256=original_envelope_sha256,
    expected_revision=1, worker_seconds=None,
    execution_stopped=False, cleanup_known=False,
    observed_at=original_observation_utc,
)
page = receiver.inspect_usage_observations(after_sequence=0, limit=25)
```

The receiver's fixed trusted scope is part of the binding. An existing reservation must match the supplied reservation reference, request ID, original exact-byte envelope digest and every scope field, including sender; the exact retained receipt must also exist. Receipt-only rows cannot acquire observations or invented reservations. A reservation reference or digest confers no authority. There is no logical/JCS identity change.

Identifiers reuse the exact builtin nonempty string limit of 1024 UTF-8 bytes, without NUL; the digest must be exactly 64 lowercase hex characters. `expected_revision` reuses the exact bounded integer guard; a new observation must match the current receipt revision (1 or 2). `worker_seconds` is either an exact builtin integer in `0..2**63-1`, excluding bool/subclasses, or `None` for UNKNOWN. Both independently observed flags must be exact bools. They are separate facts: neither implies the other or usage knowledge.

`observed_at` is an exact UTC-aware datetime (`tzinfo is timezone.utc`) normalized with the existing microsecond UTC formatter. It is **immutable observation content**, not a new retry clock. A new observation cannot precede the current receipt's `updated_at`. The API neither samples a clock nor verifies the truth/freshness of the caller's timestamp or facts.

`observation_id` is unique across this authoritative DB. Exact replay compares all original content: scope, reservation/request/digest binding, expected revision, usage, both flags, derived over-cap flag and normalized observed timestamp. It returns the original frozen `LocalUsageObservation`, including local insertion sequence. This comparison precedes the current-revision check, so an original revision-1 observation replays after its own transition advanced the receipt to revision 2. **Reuse the original timestamp and expected revision on retry.** Changing either is conflicting content (`ReceiptConflict`), even if all other values match. A new observation ID with stale revision fails (`ReceiptRevisionError`). Wrong scope raises `ReceiptScopeError`; missing/wrong reservation or request/digest binding raises `ReceiptConflict`. No conflict updates old content.

## One transaction, existing transition and event

The existing `BEGIN IMMEDIATE` serializes binding lookup, observation-ID comparison, revision checking, the existing `require_reconciliation` CAS/outbox path, and observation insertion. The existing CAS body is shared internally without opening a nested transaction or changing the public API's guards/return type. For a recorded receipt, only `recorded` revision 1 → `reconciliation_required` revision 2 is allowed; its existing matching reservation event is appended in that same transaction. Observation insertion follows the transition/event, so a late observation-write failure rolls both back too.

For a receipt already requiring reconciliation, a new observation bound to its **exact current revision 2** is retained without retransition, receipt timestamp change or additional outbox event. This includes receipts reconciled directly before any observation. Exact replay writes nothing. No observation-completed, cleanup-completed or settlement event exists. Existing event acknowledgement is unchanged and cannot release reservations. Opening an older DB adds an empty internal observation table/index/triggers; it does not backfill observations or repair past events.

Known usage is retained **unmodified**, including an overrun. `over_cap` compares it with that reservation's full fixed worker-seconds allocation, including retry and evaluation/cleanup allowance; it is not a process-limit verdict or a comparison to free envelope capacity. UNKNOWN retains `worker_seconds=None` and `over_cap=None`; unknown is never coerced to zero or reported within cap. Multiple observations are independent records, not additive debits, a latest-wins settlement or permission to sum usage. The whole original reservation stays outstanding in every case.

Before-commit validation, event-write or observation-write failures roll back the active observation/transition/outbox transaction. Existing SQLite/filesystem errors become `ReceiptStorageError`. An error after commit or during close can still mean the transaction committed; preserve the DB, reopen and inspect/replay the exact original content rather than inferring absence. No power-loss, hostile-file, backup, migration or distributed atomicity guarantee is claimed.

## Bounded inspection and synthetic retained snapshot

`inspect_usage_observations` returns a tuple of frozen observations within the receiver's principal/project/recipient scope and verifies sender mapping. It orders by ascending local insertion `sequence`, with exclusive `after_sequence` cursor (exact builtin integer `0..2**63-1`) and `limit` in `1..100`, reusing existing limits. Supplied observation timestamps need not order all rows; insertion sequence defines inspection order. Cross-scope gaps are normal. Inspection consumes/acknowledges nothing and exposes no blobs or authority. There is no sender-supplied scope/query fragment or unbounded read API.

This illustrative JSON is local metadata, not a canonical wire object or protected usage receipt. The digest is synthetic; the Python API returns a frozen dataclass. Here the full reserved allocation remains 20 even though the observation reports 21.

```json
{
  "sequence": 1,
  "observation_id": "observation-one",
  "principal": "trusted-local-principal",
  "project_id": "p1",
  "recipient": "ctf",
  "request_id": "r1",
  "sender": "scientist",
  "budget_reservation_ref": "b1",
  "request_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "expected_revision": 1,
  "worker_seconds": 21,
  "execution_stopped": true,
  "cleanup_known": true,
  "over_cap": true,
  "observed_at": "2026-11-17T12:00:01.000000Z"
}
```

Rows have bounded fields and pages have at most 100 entries, but observation count per reservation and total DB size are not capped here. The trusted owner budgets operation count, disk/journal space and retention. There is no pruning, delete, release or reset API. Historical UNKNOWN outcomes remain UNKNOWN. No currency measurement or reconciliation occurs. Canonical schemas/wire versions, guards, authentication, runtime/defaults, reviewers, evaluator and knowledge-promotion authority remain unchanged.

## Exactly six authored methods — NOT EXECUTED

[Dedicated self-contained unittest file](../tests/contracts/test_local_usage_observations.py) reuses the local fixture pattern with real temporary BlobStore/SQLite reservations, without importing historical tests or parameterizing hidden cases.

| ID | Authored coverage |
|---|---|
| U01 | Real reservation observation/reopen, exact binding, bounded ordered scoped inspection; new current-revision observation without extra transition/event |
| U02 | Exact replay after revision advance, changed content/timestamp/revision conflicts and UPDATE/DELETE immutability |
| U03 | Unknown cleanup, UNKNOWN usage and known zero keep the full reservation/floor unchanged |
| U04 | Wrong reservation/request/digest/scope, stale revision, bounded types and clock rejection leave no observation |
| U05 | Deterministic two-connection contenders: held SQLite writer lock, bounded loser timeout, stale loser and exact winner replay; one transition |
| U06 | Over-cap signed-63 maximum retained unmodified; injected event and late observation failures roll back observation/transition/outbox |

All six are authored, not executed. No tests, imports, builds or [design checker](../scripts/check_design.py) were run under the file-only instruction. Coordinator runtime/contract/recovery/reproducibility and link/language-pair/JSON/status checks remain pending; source inspection alone establishes none of their outcomes. Earlier passing checks apply only to their historical increments.

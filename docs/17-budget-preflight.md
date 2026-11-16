# 17 Pure Worker-Budget Preflight

[日本語](17-budget-preflight.ja.md) | [Home](../README.md)

**Status: offline helper implemented and ten fixtures authored, 2026-11-17; B01–B10 passed once offline.** On 2026-11-17, one focused offline invocation passed all ten B01–B10 cases; the coordinator also retains execution evidence. It covers only the arithmetic portion of P1 / SCI-05, not full admission, a runner or runtime acceptance. No scientific or measured result is claimed. The [CPU pilot](../examples/cpu-pilot.json) remains disabled.

## Implementation and command

Implemented, offline, standard library only (namespace packages, no `__init__.py` files):

- `src/ai_agent_scientist/admission/budget_preflight.py`
- `tests/contracts/test_budget_preflight.py` (exactly ten methods B01–B10, one vector each)

Executed reproducible command (2026-11-17, ten cases passed):

```
env PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/contracts -p test_budget_preflight.py -v
```

This is not full SCI-05 launch rejection, not admission and not a runner. No production wiring, registry, schema or wire-version change is part of this increment.

## Internal interface

Name: `check_uniform_worker_budget`, with exactly five keyword-only inputs, in the validation order below. They are values from [evaluation-protocol/1](../schemas/evaluation-protocol.schema.json) `execution`, not a new wire contract.

| Input | Symbol | Domain |
|---|---|---|
| `planned_attempts` | P | positive integer |
| `max_retries` | R | nonnegative integer |
| `per_attempt_seconds` | S | positive integer |
| `evaluation_cleanup_seconds` | E | nonnegative integer |
| `total_worker_seconds` | T | positive integer |

Only the exact built-in `int` type is accepted. Bool, subclasses, every float (including integral-looking floats), strings, null, nonfinite values and integers outside the stated domain are rejected. No coercion, custom converter or float conversion; exact integer precision is preserved. Missing cost is not zero.

For valid inputs: `required = (P + R) × S + E`; `shortfall = max(required − T, 0)`. R is one study-wide retry allowance, not retries multiplied by P. E is predeclared overhead. Freeze verification/reproduction allocation once, in planned attempts or explicit overhead, without omission or double charging. Heterogeneous caps are outside this helper.

Immutable internal result (frozen dataclass, field order as listed):

- `outcome`: `fits_arithmetic` if required <= T, otherwise `exceeds_cap`; invalid input yields `invalid_input`.
- `required_worker_seconds`, `cap_worker_seconds`, `shortfall_worker_seconds`: exact integers for valid input.
- `invalid_field`, `invalid_reason`: null for valid input. For invalid input, the first invalid field in table order; reason is `not_integer` (including bool) or `below_minimum`.
- Invalid required and shortfall are null. Cap is retained only if T independently satisfies its positive-integer domain; otherwise cap is null.

Identical inputs produce identical results. No raw-value logging is needed. No file/JSON reader, URI resolver, clock, process, environment, authorization reference or ledger is an input. This pure calculation changes no state and launches nothing.

## Validation and result decision

All five supplied values are checked against their own domains without coercion, including T even when an earlier field is invalid. Within each field, the integer requirement is decided first: a non-integer yields `not_integer`; only an integer below its minimum yields `below_minimum`. Thus a negative float is `not_integer`, not `below_minimum`.

If any domain fails, the result is `invalid_input` with only the first failing field in P, R, S, E, T order and that field's reason. Required and shortfall are both null; no partial total is computed from otherwise valid fields. Cap is T exactly when T independently passes its own domain, otherwise null, regardless of which field is reported. Only when all five pass is the exact formula applied and `fits_arithmetic` or `exceeds_cap` chosen; both invalid metadata fields are then null.

Declarative edge examples, **UNEXECUTED**. Input order is (P,R,S,E,T). Every row has outcome `invalid_input` and required/shortfall null; cap and the single reported field/reason are explicit.

| Input | Cap | Invalid field / reason |
|---|---|---|
| 0,-1,1,0,0 | null | planned_attempts / below_minimum |
| 0,0,1,0,10 | 10 | planned_attempts / below_minimum |
| 1,0,1,0,0 | null | total_worker_seconds / below_minimum |
| 1,-1,1,-1,10 | 10 | max_retries / below_minimum |
| 1,0,1,-1,10 | 10 | evaluation_cleanup_seconds / below_minimum |
| 1,-1.0,1,0,10 | 10 | max_retries / not_integer |
| 1,0,1,0,true | null | total_worker_seconds / not_integer |
| 1,0,1,0,10.0 | null | total_worker_seconds / not_integer |

These explanatory examples are separate from B01–B10, not additional fixtures or an additional authorized test allocation. They do not expand the one-invocation / ten-case / 30-second allocation.

## Ten fixtures — passed once offline

Input order is (P,R,S,E,T). Cap equals T in every case below, including invalid cases because their T is valid. Valid cases have null invalid field/reason. The test asserts every result field for each case.

| ID | Input | Outcome | Required | Shortfall | Invalid field / reason |
|---|---|---|---|---|---|
| B01 / SCI-05 arithmetic | 72,0,600,0,1800 | exceeds_cap | 43200 | 41400 | — |
| B02 exact boundary | 2,0,600,600,1800 | fits_arithmetic | 1800 | 0 | — |
| B03 global retry allowance | 2,1,400,100,1300 | fits_arithmetic | 1300 | 0 | — |
| B04 cleanup one too much | 2,1,400,101,1300 | exceeds_cap | 1301 | 1 | — |
| B05 retry changes decision | 2,1,600,0,1200 | exceeds_cap | 1800 | 600 | — |
| B06 no attempts | 0,0,1,0,1 | invalid_input | null | null | planned_attempts / below_minimum |
| B07 bool is not integer | true,0,1,0,1 | invalid_input | null | null | planned_attempts / not_integer |
| B08 unknown cost | 1,0,1,null,10 | invalid_input | null | null | evaluation_cleanup_seconds / not_integer |
| B09 no coercion | 1,0,1.5,0,10 | invalid_input | null | null | per_attempt_seconds / not_integer |
| B10 exact large integer | 9007199254740993,0,1,0,9007199254740992 | exceeds_cap | 9007199254740993 | 1 | — |

B01 preserves the existing 12 × 2 × 3 = 72 attempt mismatch with the 1,800-second sketch; it does not authorize or run that study. B08 tests missing arithmetic input, not reconciliation of a real UNKNOWN attempt. These ten vectors are not exhaustive domain coverage.

## Limits, authority and recovery

The [experiment plan](../schemas/experiment-plan.schema.json) uses `limits.per_run_seconds` / `limits.total_seconds`; the protocol uses `execution.per_attempt_seconds` / `execution.total_worker_seconds`. They are not silently interchangeable. Both hash-bound documents and the authoritative envelope must eventually be satisfied. A complete mapping/conflict resolver is unspecified here: ambiguous or conflicting mapping blocks actual admission. This helper checks protocol arithmetic only.

`fits_arithmetic` is **not** admission, authorization, reservation success, remaining-ledger validity, manifest-count/hash validation, scientific validity, experiment success, a verification receipt or a DecisionReceipt. Future authoritative admission must atomically recheck current authority, remaining budget, reservations, bindings and isolation. Missing/expired/revoked authority or a disabled plan still blocks launch; enabled=true is not authority.

Do not raise caps/retries, drop cleanup or silently shrink a study to obtain a fit. Recalculation creates no reservation, replicate or dispatch right. It does not refund/reset spent budgets or clear UNKNOWN outcomes. Keep conservative reservations for unknown actual usage and reconcile the original attempt before overlapping dispatch/retry. Worker self-refunds and blind replay remain prohibited.

## Verification status

The command above passed all ten B01–B10 cases in one invocation on 2026-11-17 (unittest reported 0.000 seconds, within the 30-second cap). No rerun. The coordinator also retains execution evidence. No dependency install, build, full suite, CI, network, model/API/GPU or experiment process is included. Prior budgets and UNKNOWNs remain unchanged. The parent attempted `python3 scripts/check_design.py`, but it stopped before checks because the environment lacks `jsonschema` (`ModuleNotFoundError`). Design validation remains blocked; no design-checker success or runtime acceptance is claimed.

## Design sources

- [06 Experiment contracts](06-experiment-contracts.md): reserve before dispatch; verification/reproduction/cleanup.
- [10 Roadmap](10-roadmap.md): P1 and proposed runtime tree.
- [11 Budget ownership](11-harness-boundaries.md): settled usage plus outstanding reservations.
- [12 Protocol and acceptance](12-protocol-and-acceptance.md): uniform bound and SCI-05.
- [13 Verification](13-verified-discovery.md) and [14 Lifecycle](14-sakana-lifecycle.md): same envelope and unresolved-attempt preservation.

Full SCI-05 launch rejection, SCI-04/20 recovery and all other runtime acceptance remain unimplemented/unexecuted by this change. Existing design-1, evaluation-protocol/1, harness-handoff/1, verification-contract/1, verification-report/1 and run-record shape are unchanged.

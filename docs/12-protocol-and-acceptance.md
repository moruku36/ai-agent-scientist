# 12 Frozen Evaluation Protocol and Implementation Acceptance

[日本語](12-protocol-and-acceptance.ja.md) | [Home](../README.md)

Status: design-only handoff. No experiment or independent replication has been performed. This document makes the normative parts of [evaluation](07-evaluation.md) and [execution](06-experiment-contracts.md) explicit for an implementer.

## Protocol before a run

The [evaluation protocol schema](../schemas/evaluation-protocol.schema.json) supplements, rather than silently replaces, `experiment-plan.schema.json` (`design-1`). The old CPU example is an inactive resource sketch; it is not a complete admissible scientific protocol. An accepted experiment must bind both documents by hash in its private manifest. Existing `design-1` files remain readable for inspection, but must not bypass the new protocol requirement.

Freeze these decisions before obtaining candidate results:

| Decision | Required record |
|---|---|
| Hypothesis | One falsifiable prediction and at least one plausible alternative explanation |
| Estimand | Primary metric, direction, unit of analysis, aggregation, practically meaningful effect |
| Split | Immutable development/final manifest hashes; group definition; owner and prior-exposure record |
| Conditions | Baseline/candidate source and configuration hashes, actual model/reasoning labels, allowed tools |
| Repetitions | Task manifest, seed/replicate list, order policy, expected run count |
| Selection | Rule using development results; candidate frozen before final access |
| Failure | Prespecified scoring for timeout/crash/missing output versus invalid measurement |
| Resources | Per-attempt and total budget, retry allowance, evaluation/cleanup reservation |
| End condition | Budget/expiry, scientific stopping rule, treatment of deviations |

The JSON example is symbolic and disabled. Strings with correct hash shape are not proof of an existing immutable artifact. Runtime must resolve and verify the actual records. A local plan containing `enabled=true` cannot authorize itself.

## Resolve the pilot's budget arithmetic

The earlier 600-second per-run cap and 1,800-second aggregate cap are maxima, not a promise that a 12-task, two-condition, three-replicate study fits. That study contains **72 attempts before retries**, with 43,200 seconds of worst-case execution at the per-run maximum, plus evaluation and cleanup. The budget example must not be read as authorization for all 72 attempts.

The implementer must choose and freeze either a small complete pilot that fits the existing envelope, or a separately authorized larger envelope. Admission computes reserved worst-case cost from the actual run manifest, including retries and overhead. Do not silently skip remaining tasks, lower per-run caps after seeing failures or ask for extra budget merely to rescue a preferred result. A stopped study is incomplete and reports coverage plus all incurred cost.

In the supplemental schema, `planned_attempts` counts the initial attempts across all conditions/tasks/replicates; `max_retries` is the aggregate number of additional attempts for the whole study. The simple uniform-cap admission bound is `(planned_attempts + max_retries) × per_attempt_seconds + evaluation_cleanup_seconds <= total_worker_seconds`. A heterogeneous run manifest may reserve exact per-attempt caps instead, but must bind that allocation before execution. These worker seconds do not replace a separate elapsed-time expiry.

## Evaluation receipts and scientific claims

A protected receipt binds `run_id`, `attempt_id`, candidate/config/input hashes, protocol hash, evaluator hash, evaluation-set hash, evaluation time, validity, primary metric (or null), limitations and issuer identity. Verify the issuer through the accepted evaluation boundary, not a string supplied by the candidate. The existing run-record schema is a summary and does not, on its own, establish this receipt binding.

Execution success, valid measurement, supported hypothesis, reproduction and independent review are separate claims. A rerun by the same AI/environment is a reproduction attempt, not independent review. A completed process with no valid score stays `unchecked` or `inconclusive`; it is never assigned a favorable default.

Claims in a manuscript or report each reference exact receipts, counterevidence, analysis version and limitation. Literature claims additionally identify the source version and supporting location. Automated review scores cannot establish novelty or replace a missing experiment. Negative and inconclusive outcomes get the same provenance as positive ones.

## Statistical and contamination rules

Pair conditions by task group, with repeated seeds nested inside a task. Aggregate within task before estimating across-task uncertainty. Use the same sampled groups for both conditions in a paired bootstrap; a small set and reused development data limit interpretation. Predeclare the analysis method, interval level, missing-outcome rule and all secondary comparisons. A confidence interval is not a correction for unrecorded adaptive search.

Record every configuration tried and total search cost. Exclude invalid infrastructure measurements only under a prespecified rule and show both the intention-to-evaluate denominator and the qualified subset. For a success-rate endpoint, timeout is an unsuccessful attempt; for a latency endpoint, use a prespecified censored/penalized treatment instead of averaging only successful runs.

If all available tasks have already informed design, mark the analysis exploratory. Resplitting, new seeds and nested CV do not restore an untouched holdout. A final result that changes a candidate or memory policy retires that set from confirmatory reuse. An acceptance gate repeatedly evaluated during development is a regression suite, not an endless supply of independent evidence.

## Required implementation fixtures

All cases below are **not executed**. They specify acceptance tests for later implementation, distinct from documentation/schema checks.

| ID | Fixture | Expected observable result |
|---|---|---|
| SCI-01 | Same request delivered after lost acknowledgement | One logical run and reservation; same receipt returned |
| SCI-02 | Same request key, changed input/config hash | Conflict; original run unchanged |
| SCI-03 | Old worker writes after replacement lease | Fencing rejection; no budget refund or state overwrite |
| SCI-04 | Crash between reserve, launch, receipt and settlement | Reconciliation preserves usage; no untracked duplicate |
| SCI-05 | 72-run plan exceeds 1,800-second envelope | Admission rejects or returns incomplete planned coverage before launch |
| SCI-06 | Candidate substitutes evaluator or metric receipt | Invalid result; immutable evaluator reference preserved |
| SCI-07 | Translation/variant of one task appears across splits | Group-overlap rejection; no confirmatory result |
| SCI-08 | Final feedback enters candidate or sleep memory | Exposure recorded; final set retired before further tuning |
| SCI-09 | Completed process, missing/non-finite score | Missing/invalid score; no manufactured zero or win |
| SCI-10 | Cancel races with successful process exit | Actual outcome and cleanup preserved; no duplicated attempt |
| SCI-11 | Fresh workspace rerun | Same deterministic fixture artifacts/metrics, or explicit nondeterminism |
| SCI-12 | Private evidence unavailable or revoked | Claim marked unverifiable; no automatic copy to public Git |

## Handoff to the implementing AI

Read README → docs/03–07 → this document → docs/11. Implement P1 records and fake-runner recovery before any model-backed experiment. Choose accepted Python/OS/locking primitives in the implementation PR; do not invent a portable sandbox by merely setting environment variables.

Deliver each work package with: schema/source versions, implemented invariants, fixture IDs and actual outcomes, commands/environment needed to reproduce, failures, resource measurements, migration/rollback notes and unresolved dependencies. Preserve English/Japanese status statements. No package is accepted because its code compiles or a model says it worked.

Only after the standalone loop passes should DOTS transport, optional memory or CTF adapters be connected. These design changes do not request another user decision about already authorized repository publication.

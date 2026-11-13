# 14 Sakana Scientist Lifecycle Integration

[日本語](14-sakana-lifecycle.ja.md) | [Home](../README.md)

**Status: proposed architecture, 2026-11-14.** Documentation only: no runtime, experiment, paper reproduction, measured gain or live DOTS integration. Preserve the existing single-worker, frozen-specification and verified-knowledge design.

## Primary-source coverage and traceability

The methodology sections below were inspected on 2026-11-14. HTML extraction was capped; complete papers, appendices and later evaluation sections were not fully read. This is section-grounded synthesis, not a full-paper review. Titles, versions, authors and Sakana affiliations were checked against primary pages.

| Primary source and inspected location | Mechanism | Design decision / limit |
|---|---|---|
| [P1: The AI Scientist: Towards Fully Automated Open-Ended Scientific Discovery](https://arxiv.org/html/2408.06292v3), §§3–4 | Idea generation, experimental iteration, writing and automated review form a connected lifecycle | Close the loop through evidence-backed reporting; retain rejected ideas and negative results. Review is criticism, not scientific truth. Reported cost/review performance is not our measurement. |
| [P2: The AI Scientist-v2: Workshop-Level Automated Scientific Discovery via Agentic Tree Search](https://arxiv.org/html/2504.08066v1), §§3.1–3.4, Fig.2 | Stage checkpoints; debug/refinement/hyperparameter/ablation/replication/aggregation nodes; figure critique | Adopt explicit node purpose and completion criteria; adapt to one sequential worker. Aggregation does not launch new experiments. VLM figure critique is deferred and cannot establish numeric correctness. |
| P2 §§4.1–4.2 | Accepted manuscript withdrawn before publication; humans select the best manuscript across runs | Acceptance is not replication; selection is not fully human-free. Do not use manuscript count or review score as the project endpoint. |
| [P3: The Agentic Scientist: Orchestrating Coding Agents for Automated Scientific (Co-)Discovery](https://arxiv.org/html/2610.18933v1), §§3.1–3.3, Figs.1–4 | Machine-readable task/evaluator contract; isolated budgeted workers; read-only ideation; rubric completion distinct from best-score promotion | Freeze task authority, separate proposal from execution and separate correctness/rubric/incumbent decisions. Shared concurrent leases are a later implementation need, not an installed scheduler. |
| P3 §§3.4–3.5 | Controlled baselines/ablations; numerical claims resolve to raw evidence; claim/source map, figure manifest and read-only audit | Freeze selected candidate before confirmation; single-change comparisons and reproducible transforms; no numerical authority from memory summaries. |
| P3 §3.6 and visible §4 human-supervision discussion | Orchestration includes human task selection and verification/manuscript intervention | Retain owner/domain review; do not infer fully autonomous scientific acceptance. |

P1 v3: 2024-09-01 (first submitted 2024-08-12); P2 v1: 2025-04-10; P3 v1: 2026-10-13. These are separate systems, not interchangeable results. Upstream code is not installed or adopted.

## Lifecycle and gates

Brief → reviewed design → frozen task/protocol/specification → baseline feasibility → read-only idea → bounded execution → protected correctness receipt → rubric decision → development incumbent selection → frozen selected candidate → controlled confirmation → aggregation → claim-grounded report → independent read-only audit → authorized export → cleanup.

This refines [04](04-research-workflow.md), not a replacement state machine. Logical roles may be sequential in the existing DOTS/Codex client. Ideation reads permitted development evidence and emits a hypothesis, falsifier, parent, ordered implementation plan and rubric IDs; it does not execute or edit the candidate. The implementation assignment receives that accepted proposal under its own resource reservation.

Three decisions remain distinct:

1. Protected checking establishes only the receipt's exact conformance/assurance scope.
2. Rubric completion records whether declared research tasks were addressed, including inconclusive outcomes.
3. Incumbent selection applies the frozen development rule; a valid, complete candidate need not improve or replace the incumbent.

A rubric pass cannot bypass correctness. A score increase cannot bypass validity. A rejected or non-improving result remains archived. Knowledge promotion remains the separate registry gate in [13](13-verified-discovery.md).

## Additive conceptual artifacts, not new wire fields

| Concept / owner | Minimum content | Existing binding / implementation gap |
|---|---|---|
| TaskSpec / registry | Specification/dependency digests, candidate interface, search/final split, evaluator identity, resource envelope | Compose experiment-plan, evaluation-protocol and verification-contract by immutable references; never create a second editable protocol |
| IdeaContract / coordinator | Hypothesis, falsifier, parent candidate, ordered plan, rubric IDs | New private proposal record needs a future schema; not an extra field in existing closed schemas |
| SearchNode / registry | Parent, purpose, candidate digest, attempt refs, reserved/consumed budget, state | New lineage record; purpose is baseline, debug, refine, hyperparameter, ablation, replication or aggregation |
| AttemptEvidence / runner and protected evaluator | Run/attempt/replicate IDs, process status, validity, raw hashes, nullable metrics/usage, failures | Existing run-record and verification-report remain authoritative in their scopes; unknown dispatch stays a reconciliation event, not an invented terminal status |
| DecisionReceipt / registry | Rule/revision, evidence bindings, rubric outcome, independent selection outcome and reason | New decision record; never synthesize a protected verification receipt from reviewer agreement |
| ClaimEvidenceMap and FigureManifest / reporting, audited read-only | Claim/figure ID, exact run/artifact/metric, transform version, uncertainty, scope, counterevidence, audit outcome | Extend the planned claim ledger with separately versioned records; existing artifact references carry content, not numeric authority |

No JSON/schema/fixture changes are made. Preserve design-1, evaluation-protocol/1, harness-handoff/1, verification-contract/1 and verification-report/1; the run-record shape also stays unchanged. New concepts require reviewed schemas and semantic checks in a later implementation change. Do not insert them as unknown properties into closed schemas.

## Bounded search and confirmation

Start with one active worker and sequential nodes. Reserve every debug, retry, replication, verification and cleanup against the same envelope in [11](11-harness-boundaries.md). An unknown process outcome retains its reservation and blocks overlapping dispatch until the original attempt is reconciled. Unknown cost is null/unknown, not zero. A node cannot increase its own budget, revise the evaluator or expose final answers.

Use P2's stages as optional research checkpoints, not automatic instructions to add datasets, models or complexity. At each checkpoint record coverage, unresolved questions, remaining resources and stop/continue reason. Aggregation reads immutable evidence only; any fresh measurement requires a separately admitted experiment node.

Freeze the selected program before controlled baseline/ablation/replication. Predeclare the change, seeds, metric and exclusions; distinguish an ablation from a differently tuned new candidate. Post-hoc diagnostics are labeled exploratory and do not silently retrain or reselect the frozen candidate. Final feedback exposure follows [12](12-protocol-and-acceptance.md).

## Evidence-to-report and audit

Each quantitative sentence resolves through the claim map to exact raw artifacts and a pinned transform, units and uncertainty. Each figure identifies its underlying runs, plotting/aggregation revision and exclusions. The writer may use summaries for navigation, never as the original numeric source. Missing/revoked evidence marks the claim unsupported or unverifiable, not repaired by another model's confidence.

A read-only auditor checks claims, figures, denominators, negative outcomes and selection history against immutable evidence. Record its actual independence/access boundary; a sequential self-review is not independent acceptance. The auditor cannot mutate protocol or issue experiment receipts. Corrections produce a new report/analysis revision, with new experiments admitted only if actually required and authorized.

## Implementation slices and comparison

| Slice | Existing package | Reviewable acceptance, future work only |
|---|---|---|
| Contract mapping | P1 | No duplicate authority; new proposal/node/decision/claim schemas explicitly versioned and bound to existing objects |
| One CPU baseline/candidate loop | P2–P3 | Valid, invalid and unknown outcomes remain distinct; original-run reconciliation and cleanup demonstrated within a separately agreed small check budget |
| Evidence-to-report | P3, before P4 claims | Every numerical claim/figure resolves to exact evidence; missing/forged source remains unsupported |
| Sequential branching | P5 | Parent/purpose and all failed-node cost retained; aggregation launches nothing |
| Optional concurrency | P6 or later P5 study | Atomic reservations/fencing and isolated workspaces accepted; equal-total-budget benefit established before adding workers |

Compare against the existing single-worker baseline under the same frozen task, model/client and total time/call/cost/evaluator-call envelope. Report complete attempt coverage, invalid/missing/unknown outcomes, reproducibility, claim support coverage, holdout exposure, wall time and measured/unknown cost separately. Predeclare metrics and the smallest useful replications; a generated manuscript is not a scientific contribution endpoint.

Defer beam/tree orchestration, persistent multi-worker teams, VLM critique, automatic LaTeX/diagram generation and general-domain bootstrapping until the CPU loop works and measured need justifies one extension. Rollback disables optional search/promotion, retaining evidence and reservations; it does not return to self-certified results.

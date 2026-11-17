# 10 Implementation Roadmap and Decisions

> Increment27 coordinator checks: six NEW T01–T06 offline methods passed once (0.045s); existing-environment design checker passed once (594 links, 35 language pairs); whitespace passed. Subsequent NOT EXECUTED/pending statements are worker-only authoring history, not these coordinator results. Independent review recorded separately; no runtime acceptance.

**Increment 27: authored, NOT EXECUTED (2026-11-17).** [Conservative recovery triage](27-recovery-triage.md) is the second of three connected bounded offline increments. Pure classification validates exact snapshot types/bindings; connected inspection uses actual receiver snapshots. Bounded frozen reports retain the full outstanding reservation and explicit evidence-gap/local-ack reasons, without global totals or admission/readiness/dispatch/settlement authority. Exactly six NEW self-contained unittest methods and paired documentation are authored; coordinator checks remain pending. Earlier validation banners apply only to earlier increments.

> Coordinator validation (2026-11-17): six new I01–I06 offline contract methods passed once (0.039s); existing-environment design checker passed once (564 links, 34 language pairs); whitespace passed. Independent pinned full-source review found no implementation defect under documented trust assumptions. Later NOT EXECUTED/pending wording records worker-file-only authorship, not the subsequent coordinator checks. No runtime acceptance.

> Coordinator validation, 2026-11-17 (round3 only): six NEW U01–U06 scenarios passed once (1.183s); existing-venv design checker passed once (534 links, 33 language pairs). Independent review pending. Later authored/NOT EXECUTED wording below is historical worker-file-only status, not current coordinator validation. Round2 original raw check receipts remain unavailable; do not infer their verification from round3.


**Outbox coordinator verification (2026-11-17): O01–O06 passed once offline, 0.046s; required design checker passed once (504 links, 32 language pairs). Original selected worker timed out at 600s; no task_complete/final, completion UNKNOWN, no replay. Authored/not-executed wording below records worker-only activity, not current coordinator check status. No live acceptance.**

[日本語](10-roadmap.ja.md) | [Home](../README.md)

[26 receiver-scoped reservation inspection](26-reservation-inspection.md) is the first of three bounded offline increments. Implementation and exactly six new self-contained unittest methods authored, **NOT EXECUTED**; checks for this increment remain pending. One read transaction connects retained receipts/reservations, current local outbox/ack, latest inserted usage and fixed allocation accounting. Only scoped snapshots with the full outstanding allocation are returned; no global totals, owner identity, authority lookup, settlement or continuing authority. Earlier coordinator validation applies only to its named historical increments.

[25 immutable local usage observations](25-local-usage-observations.md) is the narrow Scientist round3 increment on independently source-reviewed round2 `bf4743970dc48e0e89e2717a2e07c2591c8db129`. Implementation and exactly six self-contained methods authored, **NOT EXECUTED**; coordinator checks pending. Trusted observations, existing reconciliation CAS and local outbox share one SQLite transaction. All reservations remain fully outstanding and the settled floor is unchanged; no settlement, refund, completion, admission, metering or authentication is added. Historical UNKNOWNs remain unchanged.

[24 local status outbox](24-local-status-outbox.md) adds atomic retained-reservation/reconciliation events and scoped local acknowledgement CAS. Implementation and exactly six scenarios authored, not executed; no sender, transport or delivery acceptance. Earlier no-outbox statements below describe historical increments.

[23 local worker-seconds reservation](23-local-budget-reservation.md) is a narrow P1 extension at the durable receipt transaction seam: current independent caller authority, one immutable shared envelope/allocation and atomic receipt/reservation/accounting. Implemented; ten R01–R10 scenarios passed once offline (0.082s); coordinator diff review completed. Original receipt-only behavior remains unchanged. Full reservation/admission acceptance, other resource dimensions, protocol/plan resolution, JCS and dispatch remain missing. Earlier receipt-only status below is historical.

## Decisions for this design

- Name: `ai-agent-scientist`; English default and Japanese counterparts.
- Center: existing DOTS, explicitly selected by the user; existing ChatGPT/Codex for research/implementation.
- Framework: extend that established workflow. Do not introduce eve, a new agent runtime or provider keys merely to produce the design.
- First deployment: one accepted connected environment, local state, one CPU worker. Actual Windows/Mac selection and spare resources require inspection before execution.
- Record/evaluation first; adaptive search and teams later. No new schedule, cloud service or GPU run in this update.
- Public design and synthetic examples; private operational state and protected final evaluation.

These are architectural choices, not claims of environment acceptance or authorization for future runtime changes.

## Work packages

| Package | Deliverable | Acceptance |
|---|---|---|
| P0: actual environment | Identify one connected Codex environment, resource ceiling, data eligibility, tool capabilities and project envelope | A harmless file/task handoff with returned evidence; no heavy benchmark |
| P1: record contracts | Project/protocol/run records plus specification closure, verification bindings and knowledge eligibility; atomic revisions, hashes, idempotency and budgets | Valid/invalid records, stale writes, duplicate requests, mismatched bindings and expired envelopes rejected correctly |
| P2: offline vertical slice | One deterministic CPU experiment, baseline/candidate artifacts, protected owner-run verification/evaluation and scoped receipts | Fresh reproduction; specification/dependency substitution and forged receipts rejected; bounded failures; no model API call for fixtures |
| P3: DOTS/Codex loop | Brief → bounded assignment → candidate → scoped receipt → eligible knowledge → next decision | Actual context/result retrieval; no duplicate resume; reviewed ideas never self-promote; no final-answer leakage |
| P4: pilot study | Raw-log versus evidence-indexed handoff research, or another owner-selected narrow question | Frozen development/final split and complete matched outcomes; no result prefilled |
| P5: one adaptive extension | Archive first, then one search/role mechanism if justified | Same budget comparison against single-worker baseline; retain regressions |
| P6: remote and long-running | Optional NUC registry/MCP/events, separate worker, backup and cancellation | Authentication, restart/lease reconciliation, quota, restore, expiry and end-to-end delivery accepted |
| P7: wider research | New topics, optional formal-verifier adapter, GPU or independent specialist reviewer | Topic-specific proof assumptions/claim scope, data/resources and actual authorization; no claim of upstream library availability |

## Sakana integration slices — still unimplemented

[14](14-sakana-lifecycle.md) refines P1 with explicit proposal/node/decision/claim record gaps; P2–P3 with one sequential CPU loop and evidence-to-report audit; and P5 with typed bounded branching. Implement those slices without changing existing schema versions. New runtime checks and experiments need their own small, explicit case/resource budget; none run in this documentation revision. P6 concurrency requires atomic shared reservations/fencing and measured benefit first. Defer multi-worker trees, VLM critique and automatic manuscript generation. Roll back optional mechanisms while preserving evidence and unresolved reservations.

## Proposed runtime tree

```text
src/ai_agent_scientist/
  records/       # project, protocol, candidate, run, claim ledger
  admission/     # scope, budget, leases, expected revisions
  runners/       # accepted isolated CPU backend first
  evidence/      # hashes, provenance, bounded reads, export
  evaluation/    # frozen empirical metrics; protected execution is separate
  verification/  # specification closure, scoped receipts, optional adapters
  knowledge/     # eligibility view; reviewed notes separate from checked results
  integration/   # task packets; optional MCP/events later
tests/
  contracts/
  integration/
  reproducibility/
```

The full tree remains planned. The [17 budget preflight](17-budget-preflight.md) pure arithmetic helper (ten historical offline cases) and [18 immutable blob helper](18-immutable-blob-helper.md) (E01–E12 passed once offline) are implemented. The [19 strict JSON blob reader](19-json-blob-reader.md) connects verified bytes to strict decoding (J01–J08 passed once offline); it accepts no records. The [20 request preflight](20-handoff-request-preflight.md) adds a fixed request-only structure/expiry check (H01–H08 passed once offline), not authorization or dispatch. No runner, admission service or research runtime is delivered. Start with the standard library where practical, adding pinned libraries only for a measured need. Validate supported schema keywords explicitly; the sample schemas do not implement policy.

The [21 handoff payload binding](21-handoff-payload-binding.md) seam is implemented with ten new P01–P10 scenarios passed once offline (0.074s); coordinator source review is complete. It binds current caller-owned local metadata/access before the actual bounded BlobStore payload read, without admission, dispatch or new authority.

The [22 durable byte-bound handoff receipt](22-durable-handoff-receipt.md) connects that actual loader to receiver-owned local SQLite persistence under an independently trusted principal/project/recipient scope. Implemented; ten D01–D10 scenarios passed once offline (1.172s); coordinator source review completed. Required design-check results are recorded separately. Exact envelope replay returns the current durable unresolved receipt; changed bytes conflict; one receiver-local revision CAS marks reconciliation required. This is a partial docs11 profile: full logical/JCS identity, admission, reservation/budget authority, outbox, dispatch and retry remain missing. No architecture or canonical wire/schema change.

## First pilot in concrete terms

1. Define one falsifiable question with the [brief](../templates/research-brief.md).
2. Create owned synthetic tasks and fixed baseline/metric before calling any model.
3. Implement registry, dry-run admission and evidence receipts; prove cancel/retry correctness.
4. Have DOTS assign one small Codex task in the accepted environment.
5. Reproduce and inspect the result outside the candidate's control.
6. Run only the predeclared matched study inside the authorized envelope.
7. Publish a sanitized report only if permitted, including no-gain/negative outcomes.

## Acceptance record and open questions

Record proposed / implemented / executed / independently verified separately. A passing unit test is not a live DOTS connection. A successful task is not proof of novel research. This repository's initial checks cover document links, language pairs, JSON structure/examples and status consistency only.

At implementation, resolve the actual execution computer, spare capacity, private state destination, evaluator isolation and accepted client task route. Choose a first research question and the desired model-use budget then. These unknowns do not block publishing the design, and this update does not ask the user to decide them prematurely.

## Concrete implementation contracts

[11 Ownership and handoffs](11-harness-boundaries.md) defines state authority, duplicate delivery, fencing, parent/child budgets and pinned schemas. [12 Evaluation and acceptance](12-protocol-and-acceptance.md) defines the frozen protocol, receipt binding and SCI-01–12. The old 1,800-second CPU sketch cannot reserve 72 attempts at up to 600 seconds each; reconcile the actual run manifest and total budget before launch. This update checks design/examples only, not runtime acceptance.

## Revision sequence and rollback

Implement [13](13-verified-discovery.md) as an extension of P1–P3, not a new research runtime. Accept the original SCI-01–12 plus applicable SCI-13–20 before using their guarantees. First prove the empirical/offline path; proof-assistant installation and multi-team services remain deferred. On incompatibility, disable new knowledge promotion/reuse, preserve immutable records and return to the accepted single-worker configuration. Never fall back to self-certified passes or enlarge the experiment budget.

## Kaggle implementation slices — not implemented (2026-11-16)

[15](15-kaggle-competitions.md) and [16](16-kaggle-knowledge-oss.md) map onto the existing work packages. No new runtime is created; the competitions are the first application of P1–P4. This change is documentation only: no joining, download, training or submission.

| Slice | Existing package | Deliverable | Acceptance |
|---|---|---|---|
| K0 Competition briefs | P0 | [Competition briefs](../templates/competition-brief.md) for the three competitions; the owner fills in participation, resource envelope, and submission/publication authorization | Unknowns, Rules included, are resolved or stated |
| K1 Records | P1 | Versioned records for CompetitionProfile, submission ledger, offline bundle and final selection | Valid/invalid fixtures for KGL-04, 05, 08, 10 |
| K2 Pre-submission checks | P2 | Format check, no-internet rerun, resource estimate | KGL-01–03 on synthetic data, without connecting to Kaggle |
| K3 Name That LLM CPU loop | P2–P4 | Group-split CV, character n-gram baseline, out-of-fold predictions, confusion matrix | Reproduced in a fresh workspace. One submission if authorized; local and LB values recorded in the ledger |
| K4 Gemma loop within the deadline | P3–P4 | Local reproduction of sample_submission, repository holdout, comparison of prompt/Skill candidates | Results and failure types for all tasks retained. Final submissions frozen by 2026-12-02 |
| K5 PLE harness | P3–P5 | Submission in a separate repository, dev ablations, score versus cost, failure breakdown | `kit check` and `kit artifacts` pass. Every Writeup number resolves to evidence (KGL-09) |
| K6 GPU training | P7 | LoRA or encoder fine-tuning | Separate GPU envelope and training-data authorization. Compared with non-trained candidates on the same split |

Proposed order, counted back from deadlines: K0 (before the Gemma entry deadline, 2026-11-25) → K1 and K2 → K3 and K4 (by 2026-12-02) → K5 (by 2027-01-05) → extensions of K3 (by 2027-01-13). Because K4's window is short, starting it with manual records before K1 and K2 is a possible decision; if so, state it as a procedural boundary and import the records into the registry afterwards.

Add `competition/` (profile, pre-submission checks, submission ledger, offline bundle) to the proposed implementation layout. Competition-specific code stays in the private project; the public repository keeps only generic checks and templates.

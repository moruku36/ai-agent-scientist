# 10 Implementation Roadmap and Decisions

[日本語](10-roadmap.ja.md) | [Home](../README.md)

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
| P1: record contracts | Project/protocol/run records, atomic revision update, artifact hash/paging, request idempotency and budget reservation | Synthetic valid/invalid records, stale write, duplicate request and expired envelope behave correctly |
| P2: offline vertical slice | One small deterministic CPU experiment, baseline/candidate artifacts, independent owner-run evaluator and report | Reproduction from a fresh workspace; failures and resource limits recorded; no model API call required for bookkeeping fixtures |
| P3: DOTS/Codex loop | Brief → bounded assignment → candidate → verified receipt → next decision | Actual context and result retrieval accepted; interrupted task resumes without double execution |
| P4: pilot study | Raw-log versus evidence-indexed handoff research, or another owner-selected narrow question | Frozen development/final split and complete matched outcomes; no result prefilled |
| P5: one adaptive extension | Archive first, then one search/role mechanism if justified | Same budget comparison against single-worker baseline; retain regressions |
| P6: remote and long-running | Optional NUC registry/MCP/events, separate worker, backup and cancellation | Authentication, restart/lease reconciliation, quota, restore, expiry and end-to-end delivery accepted |
| P7: wider research | New topics, optional GPU or independent specialist reviewer | Topic-specific protocol/data/resource acceptance and concrete user authorization where needed |

## Proposed runtime tree

```text
src/ai_agent_scientist/
  records/       # project, protocol, candidate, run, claim ledger
  admission/     # scope, budget, leases, expected revisions
  runners/       # accepted isolated CPU backend first
  evidence/      # hashes, provenance, bounded reads, export
  evaluation/    # receipt contracts; protected execution is separate
  integration/   # task packets; optional MCP/events later
tests/
  contracts/
  integration/
  reproducibility/
```

This tree is planned; no runtime files are included. Start with the standard library where practical, adding pinned libraries only for a measured need. Validate supported schema keywords explicitly; the sample schemas do not implement policy.

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

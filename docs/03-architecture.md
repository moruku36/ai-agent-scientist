# 03 Whole-System Architecture

[日本語](03-architecture.ja.md) | [Home](../README.md)

## Responsibilities

| Layer | Responsibility | Must not own |
|---|---|---|
| Moruku | Research objective, acceptable resources/data, interpretation of significance, steering | Routine mechanical execution of every authorized step |
| Existing DOTS | Maintain agenda, select next informative experiment, assign bounded work, integrate results | Unrecorded unlimited compute, fabricated evidence or implicit permission expansion |
| Project registry | Canonical project/protocol revisions, job state, budgets and candidate lineage | Scientific conclusions inferred from task completion |
| Codex implementation worker | Inspect permitted inputs, write code, execute accepted plan and report failures | Evaluator/holdout/permission mutation |
| Experiment runner | Enforce workspace/resource/network limits, record environment and process outcomes | Research judgment or model self-score as ground truth |
| Evaluation worker/service | Validate artifacts, calculate frozen metrics and repeat experiments | Tuning candidate code on final holdout answers |
| Reporting/export | Map claims to evidence and prepare a selected public report | Automatic export of private transcripts or raw datasets |

DOTS is the coordinator already selected by the user, not a service this repository implements. Logical roles may run sequentially through the same client. Separation of evaluation is enforced by access control, not just by telling the same AI to “be a reviewer.”

## Data and control flow

```mermaid
flowchart LR
    U["Research brief"] --> D["DOTS"]
    D --> P["Frozen experiment protocol"]
    P --> J["Registry / bounded job admission"]
    J --> W["Codex workspace: candidate code"]
    W --> A["Artifacts + environment + logs"]
    A --> Q["Protected evaluator"]
    Q --> M["Metric receipt + verification"]
    M --> D
    D --> C["Claim-evidence ledger"]
    C --> O["Report candidate"]
```

A submitted plan is not an accepted job; an accepted job is not a successful process; a successful process is not a valid result; a valid result is not novel science.

## Storage proposal

For the first local implementation: Python 3.12-compatible code after version acceptance, SQLite for a single-host registry, append-only JSONL event records, filesystem blobs identified by SHA-256, Markdown for human review. These are proposed choices, not installed dependencies. No extra agent framework, vector DB or distributed queue is required initially.

Suggested private project layout:

```text
project/
  brief.md
  sources/index.json
  protocols/<protocol-revision>.json
  state/project.json
  candidates/<candidate-id>/manifest.json
  runs/<run-id>/manifest.json
  runs/<run-id>/events.jsonl
  evidence/<sha256>
  claims/ledger.json
  reports/draft.md
```

Evaluator code, sealed holdout and authorization records live **outside the implementation worker's mount/access domain**. Keeping them in a second directory under the same unrestricted user is not sufficient protection. On a host without that isolation, use an owner-operated evaluation step and label the boundary procedural until stronger execution isolation is accepted.

## Integrity and concurrency

The registry is the sole authority for state transitions. Each update carries the expected revision; a stale writer reloads rather than overwrites. Reserve a job lease and budget before launch. Record run/event IDs, sequence numbers and artifact hashes. Export an immutable manifest before closing the run.

Start with a single registry writer and one active worker. Git records protocol/source revisions; it is not a cross-process lock. A queued job with an expired lease is reconciled with actual process state before any retry. Immutable artifacts may be deduplicated; scientific trials must not be silently deduplicated when an intentional replicate is requested.

Local worker outage leaves project state intact. A DOTS task can be replaced using a fresh handoff. Recovery must not automatically duplicate a running expensive experiment.

## Interface choices

The minimum interface is file-based task/result manifests with existing client tools. A later MCP adapter may offer conceptual capabilities such as project snapshot, plan submission, run status, evidence paging and cancellation. These names are design concepts, not claims about tools installed in DOTS. A validator and runner enforce contracts regardless of the transport.

A NUC-hosted registry and remote workers require accepted identity, encrypted transport, per-project authorization, quota enforcement and backup/restore. Introduce that only after the local loop works. The existing report MCP stays read-only and separate. No live wiring is created here.

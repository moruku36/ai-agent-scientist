# 06 Experiment Contracts and Execution

[日本語](06-experiment-contracts.ja.md) | [Home](../README.md)

## Identity and immutable inputs

Separate `project_id`, `hypothesis_id`, `protocol_revision`, `candidate_id`, `run_id`, `attempt_id` and `replicate_id`. A request key identifies the logical assignment; retries reuse it for reconciliation, while a genuine repeat gets a new replicate ID. Record the input/code/environment hashes before launch. Hashes identify content, not scientific correctness or secrecy.

A plan specifies question, baseline/candidate revisions, datasets and split references, metric/evaluator revision, seed list, expected artifacts, allowed operations, resource caps, total experiment budget and stopping rule. Schemas in this repository describe structure only; semantic policy validation remains required.

## Initial execution profile

Proposed CPU pilot limits: one active job; two CPU cores; 4 GiB memory; 2 GiB scratch; 600 seconds per run; 1,800 total experiment seconds; no GPU; no network; no paid API spend. These are **proposed maxima**, not measurements of spare host capacity. Reduce them if the actual host cannot reserve them.

Default configuration is disabled. An implementation must reject a missing authorization reference, expired scope, unsupported isolation backend, unknown dependency lock or insufficient free resources. It must never silently drop a limit just because the host cannot enforce it.

Use a disposable container/VM or accepted restricted execution environment with no host administration sockets, no broad home-directory mount and no ambient production credentials. Generated research code needs execution privileges inside that boundary; analysis is not limited to static tools. The runner launches a declared entrypoint with structured arguments, not a network-exposed arbitrary shell service.

Dependency acquisition is a separate controlled preparation phase: pin versions and hashes, inspect licenses, then freeze the environment. Runtime network remains off for offline experiments. Do not install CUDA stacks or models merely to exercise record contracts.

## Run state and recovery

```mermaid
sequenceDiagram
    participant D as DOTS
    participant R as Registry
    participant W as Runner
    participant E as Evaluator
    D->>R: Submit plan and expected revision
    R->>R: Validate scope; reserve budget and lease
    R->>W: Launch accepted immutable inputs
    W-->>R: Heartbeat and artifact references
    W-->>R: Exit status and resource receipt
    R->>E: Frozen candidate artifacts
    E-->>R: Validity and metric receipt
    R-->>D: Verified status or explicit failure
```

Reserve worst-case time/resource allowance before dispatch; settle with measured usage when known, retaining a conservative reservation after ambiguous failures. The admission service and evaluator records are not worker-writable. A worker report cannot refund its own budget.

Timeout/cancel terminates the child process group, checks for leftovers, captures partial output and records a terminal reason. Restart reconciliation first checks process identity and artifacts; do not treat missing heartbeat as proof a process has stopped. OOM/disk failures are infrastructure outcomes, not a zero or winning metric.

## Evidence envelope

Every result contains run/attempt identity, protocol and artifact hashes, timestamps, status, measured usage, tool/environment versions, captured stdout/stderr references, metric receipt reference and limitations. Status distinguishes `completed`, `partial`, `failed`, `timeout`, `cancelled` and `rejected`. Metric validity is a separate field; missing metrics remain missing.

Keep originals in private storage, with paged access for agents and explicit truncation markers. Derived summaries link to originals. Capture code diff, lockfile/environment image, seed, hardware/runtime context and measurement procedure. Large datasets stay in controlled storage; record source/license/version/hash rather than copying them into Git.

The [run record schema](../schemas/run-record.schema.json) is a design contract, not a full validator. Store ISO 8601 timestamps with timezone; UTC internally, JST in user-facing summaries where appropriate. Reporting must distinguish end time, evaluation time and publication time.

## Data boundary

Use owned synthetic data first. Public data still requires license and evaluation-split handling. Redact secrets and private source material before any model/cloud transfer where required. Keeping a dataset public does not make final-evaluation answers available to the tuning worker. Programmatically verify split hashes and evaluator identity at evaluation.

Proposed examples are not runnable launch configurations. No experiment is executed by reading or committing a plan.

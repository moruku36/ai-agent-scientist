# 08 Adaptive Search and Improvement

[日本語](08-adaptive-improvement.ja.md) | [Home](../README.md)

Search and team extensions in this document are optional, disabled initially, and evaluated against a single-worker baseline. The basic receipt/knowledge distinction in [13](13-verified-discovery.md) is a record invariant, not an enabled search algorithm. They improve the external research procedure; they do not train DOTS or alter its internal implementation.

## Candidate archive: DGM-inspired

Each candidate record stores parent ID, hypothesis, code/config hashes, protocol/evaluator revision, disclosed development feedback, resource use and failures. Preserve interesting failed branches, not only the current winner. Every revision is a new candidate; never overwrite the evidence of an earlier result.

Candidate code is untrusted. It cannot change the runner, budget policy, acceptance tests or evaluator. Changes to the harness itself use a separate development branch, regression fixtures and frozen evaluation; they are not automatically promoted into live research. A higher score can arise from measurement exploitation, so audit score increases against the actual objective.

## Budgeted branching: AB-MCTS-inspired

Begin with sequential refinement. If development evaluation is cheap and repeatable, compare it with independent sampling before a tree policy. Proposed first search envelope: at most 8 candidates, depth 3 and one active evaluation, all within the project budget. These are pilot values, not paper recommendations.

A branch decision chooses either a new hypothesis/implementation family or a refinement of a known family. Store why the next observation is informative, parent lineage, score uncertainty, cost and remaining budget. A bandit/Thompson policy requires an explicitly justified observation/reward model; a raw AI novelty score is not calibrated evidence. Do not label a simple heuristic scheduler as an implemented AB-MCTS algorithm.

Use development metrics only. The final selected candidate is frozen before holdout. Count search cost and report final selection separately from the best candidate ever observed.

## Role changes: EAT-inspired

After a declared plateau, diagnose:
- Measurement unstable → measurement/profiling review.
- Validity uncertain → methods/criticism review.
- Implementation blocked → focused coding/debugging task.
- Question exhausted → revise the research question or stop.

The first response is a sequential specialist pass, not a larger permanent team. Later parallel work needs separate task contracts, merge ownership, aggregate budget reservation and an explicit comparison. Concurrent experiments on shared hardware can invalidate timing comparisons; serialize measurement even if analysis runs in parallel.

## Verified lessons: optional sleep connection

Export only reviewed general methods, failure classifications and provenance to an external lesson store. No raw private transcript, holdout answer, result cherry-picking or unverified speculative idea becomes an instruction. Retrieval returns a bounded, dated bundle, and a lesson must be revalidated when context changes.

Unverified hypotheses remain tagged as hypotheses. No memory consolidation step is allowed to silently change an experiment protocol. The last accepted instruction version remains usable while any optional consolidation is pending.

## Admission and rollback

Promote an extension only if matched-budget experiments show useful gains or a clearly documented operational benefit without validity loss. Revert to the simpler accepted configuration on flat, noisy or regressed outcomes. Keep all failed extension results.

These mechanisms are this project's adaptations of the [seven sources](02-research-foundations.md). They are not evidence of recursive self-acceleration, automatic scientific discovery, or guaranteed improvement on Moruku's tasks.

## Knowledge promotion before wider search

A candidate archive stores all attempts; the eligible knowledge index is a stricter view. Promote checked results/components only under their contract and receipt bindings; retain reviewed ideas and conditional dead ends as separate note kinds. Newly generated teams or branches may reuse only permitted compatible entries. They cannot inherit a claim merely by citing its title.

A specification, dependency or cost-model revision invalidates affected comparisons and reuse eligibility until rechecked. Keep verification cost in the fixed search budget. Prefer targeted checks for unchanged objects, but do not reuse a development cache as final confirmation or as an intentional replicate. Adopt wider discussion only if it resolves a concrete bottleneck; no conference schedule is part of this design.

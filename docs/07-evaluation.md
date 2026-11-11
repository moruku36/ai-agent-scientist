# 07 Evaluation and Scientific Validity

[日本語](07-evaluation.ja.md) | [Home](../README.md)

## Four independent questions

| Gate | Question | Evidence |
|---|---|---|
| Execution | Did the intended code run within the envelope? | Process/resource receipt, immutable code/input/environment |
| Validity | Does the measurement test the stated hypothesis fairly? | Accepted protocol, functioning baseline, leakage/confounder checks |
| Reproducibility | Can a fresh run obtain compatible results? | Re-run with seeds/environment recorded; independent operator or isolated evaluator where feasible |
| Research contribution | Is the finding meaningful and distinct from known work? | Literature comparison, effect/uncertainty, alternative explanations and human review |

Do not collapse these into a single model-generated score. An automated reviewer may suggest criticisms, but not certify novelty or correctness.

## Protected evaluation

The candidate worker can inspect development data and disclosed feedback. Final holdout, evaluator source where necessary, reference outputs, authorization policy and usage receipts are outside its write/access domain. The trusted evaluator receives only frozen artifacts and returns the predeclared feedback. Do not reveal hidden answers through detailed error messages.

For an owner-operated pilot, final evaluation can be a manually invoked protected step. Mark its actual isolation strength. Separate processes under the same unrestricted account do not provide an adversarial boundary. If the worker can edit tests, global environment or metric files, reject “independent evaluation” claims.

Check deterministic fixtures before scoring: known-good, known-bad, malformed/empty output, timeout, crash, and attempted evaluator-file replacement. Missing or invalid output has a documented outcome, never a favorable default.

## Development and final evaluation

Predeclare data/seed splits, task IDs, primary metric/direction, meaningful effect, repetitions and stopping. Tune only on development evidence. Freeze candidate and protocol before the final set. Once final results influence design, that set is development data; use a new untouched set for further confirmatory claims.

Record every candidate, run and exclusion. Publish failures and negative results alongside winners. Distinguish the highest score seen during search from the frozen final selected candidate. Best-of-many and one-shot outcomes are not interchangeable.

## Statistical comparison

For an initial controlled pilot, propose 12 owned synthetic tasks split into 6 development and 6 untouched evaluation tasks, with 3 replicates per evaluated condition. This is exploratory, not enough for broad scientific claims. Choose the actual task list and matching before execution.

Compare A: existing single-worker workflow, B: A plus external state/evidence harness, and later C: B plus one adaptive mechanism. Match model/reasoning configuration, input, time/call/resource budgets and available tools. Record intentional differences. Randomize/interleave order where practical to reduce host-load and temporal effects.

Report per-task paired outcomes, all replicates, mean/median and dispersion; use task-level uncertainty methods appropriate to the sample. Repeated runs of one task are not independent evidence from many tasks. Report unstable effects and practical magnitude, not only significance or one best run. Additional exploratory comparisons must be labelled.

For runtime optimization, establish numerical correctness first; then isolate warmup, measurement overhead, load, and cache behavior. A faster incorrect implementation fails. For scientific ML, audit splits, label leakage, baseline tuning effort and equal compute. For an evidence-memory experiment, score against owned ground truth without using an LLM opinion as the only judge.

## Cost and research progress

Measure elapsed time, active experiment time, calls, tokens when observable, hardware usage, user interventions and recovery effort. Separate subscription use, incremental API charges, local energy/resource estimates, and unmeasured costs. Zero additional API budget is not a claim that the whole workflow is free.

Research progress is a ledger of uncertainty resolved: hypothesis supported/refuted/inconclusive, reproducible effect, new constraint or failed replication. A negative result can be useful; a generated manuscript alone is not progress.

## Release gate

The first usable version must preserve traceable evidence, enforce resource/expiry limits, recover without duplicate work, reproduce its local fixture result, and report complete outcomes. Performance claims require matched experiments, not just those integration checks. General claims about autonomous science require broader tasks and independent review beyond this pilot.

## Concrete implementation contracts

[11 Ownership and handoffs](11-harness-boundaries.md) defines state authority, duplicate delivery, fencing, parent/child budgets and pinned schemas. [12 Evaluation and acceptance](12-protocol-and-acceptance.md) defines the frozen protocol, receipt binding and SCI-01–12. The old 1,800-second CPU sketch cannot reserve 72 attempts at up to 600 seconds each; reconcile the actual run manifest and total budget before launch. This update checks design/examples only, not runtime acceptance.

## Verification does not replace scientific evaluation

The [verification layer](13-verified-discovery.md) strengthens the artifact/specification boundary beneath these four gates. Match not only the evaluator's main file but the trusted definitions, preprocessing, units, tolerances and dependency closure. Known-bad fixtures must include indirect definition changes and forged receipts. Validate objective correctness before comparing objective cost.

Record empirical checking, formal proof, reproduction and research review separately with their actual scope and assumptions. A proof is about a stated proposition; a test is about tested conditions. Neither validates the choice of scientific model automatically. A clean verifier process is not an independent scientist. Keep the candidate-selection and knowledge-promotion decision on development evidence; frozen final evaluation remains a distinct event. SCI-13–20 extend, rather than replace, the original acceptance cases.

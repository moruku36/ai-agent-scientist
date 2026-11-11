# Experiment Plan

[日本語](experiment-plan.ja.md)

- Project/hypothesis/protocol ID; parent protocol and reason for revision:
- Baseline and candidate source/config hashes:
- Dataset/license/version and split hashes:
- Environment lock/image and accepted worker profile:
- Entrypoint, structured arguments, expected output contract:
- Evaluator identity/revision and access boundary:
- Primary metric, direction, validity checks and missing-result rule:
- Task unit, seeds, replicates, order and selection rule:
- Per-run and aggregate resource/call/cost caps; expiry:
- Checkpoint/cancel/retry behavior; request/replicate IDs:
- Confounders, exclusions defined before results, stop conditions:
- Authorization reference and permitted output destinations:

Freeze before confirmatory execution. Later deviations remain visible under a new revision.

## Supplemental verification manifest
- Verification-contract ID/hash binding this plan and evaluation protocol:
- Trusted specification/dependency closure, cost model and allowed replacement interfaces:
- Accepted verifier/toolchain/environment; scoped obligations and required evidence:
- If formal: theorem/assumption/axiom policy and independent checker boundary:
- Verification/reproduction/cleanup reservation; cache versus fresh-attempt policy:
- Revision impact on baseline comparisons and reusable knowledge:

Use [verification-contract/1](../schemas/verification-contract.schema.json); do not add unknown fields to the older plan schema.

# Contract Status

[日本語](README.ja.md)

These JSON Schemas are design contracts, not a runtime or permission engine. The CPU example is disabled and contains no executable entrypoint, real identity or connection.

An implementation must additionally enforce: unexpired actual authorization, immutable hashes and source access, accepted environment isolation, resource availability and OS-level limits, aggregate budget reservations, dataset/split rights, evaluator ownership, transition rules, cancellation and redacted export. JSON Schema alone cannot prove those properties.

The run record intentionally permits missing metrics and unchecked/inconclusive validity. A completed process must not imply valid science. Evidence hashes and measurement receipts need independent validation.

## Supplemental contracts (design only)

- [handoff.schema.json](handoff.schema.json): `harness-handoff/1`, reference-only sibling messages. [Example](../examples/handoff.synthetic.json): synthetic, deliberately expired in 2000, unresolvable symbolic IDs/zero hashes; never dispatch it.
- [evaluation-protocol.schema.json](evaluation-protocol.schema.json): `evaluation-protocol/1`, frozen estimand, exposure, conditions, runs, budgets and analysis. [Example](../examples/evaluation-protocol.synthetic.json): disabled and exploratory; symbolic hashes are not real data. Its four attempts × 300 seconds + 600 seconds evaluation/cleanup fit the illustrative 1,800-second envelope.

These supplement `design-1`; no silent migration. Runtime resolves actual hashes, enforces unique condition IDs with one baseline and at least one candidate, verifies group-disjoint splits and exposure, reconciles run counts/retries/budget, binds the issuer and receipt, and rejects expired/unauthorized execution. Arithmetic, temporal ordering, reference existence and cross-record equality are semantic checks beyond JSON Schema. Enable format checking and reject duplicate JSON keys/non-finite numbers. Load pinned local schemas only, without network `$ref` resolution. See [the handoff specification](../docs/11-harness-boundaries.md) and [protocol acceptance](../docs/12-protocol-and-acceptance.md).

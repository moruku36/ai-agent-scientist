# Contract Status

[日本語](README.ja.md)

These JSON Schemas are design contracts, not a runtime or permission engine. The CPU example is disabled and contains no executable entrypoint, real identity or connection.

An implementation must additionally enforce: unexpired actual authorization, immutable hashes and source access, accepted environment isolation, resource availability and OS-level limits, aggregate budget reservations, dataset/split rights, evaluator ownership, transition rules, cancellation and redacted export. JSON Schema alone cannot prove those properties.

The run record intentionally permits missing metrics and unchecked/inconclusive validity. A completed process must not imply valid science. Evidence hashes and measurement receipts need independent validation.

# Offline design checks

[日本語](README.ja.md) | [Home](../README.md)

From the repository root, run `python scripts/check_design.py` in an existing Python environment with `jsonschema` supporting Draft 2020-12. The script does not install anything, contact services, launch experiments or write files.

It checks all six schema definitions, every JSON example, a minimal legacy run-record shape, empirical-only contract/report shapes, an incomplete formal claim without proof artifacts, negative shape mutations, local Markdown link target existence, reciprocal English/Japanese links, and limited inactive/design-only status markers. Format checking is enabled; the local date-time profile accepts ordinary RFC3339 instants but rejects leap-second notation, without relying on optional format packages. Duplicate JSON keys, non-finite numbers and non-local schema references are rejected. External links, Markdown anchors and full translation equivalence are not checked.

A passing result is **documentation/schema validation only**, never a SCI runtime acceptance result. The script does not resolve symbolic artifact IDs, authenticate issuers, compute canonical manifest hashes, enforce isolation or budgets, check formal proofs, or measure performance. It intentionally does not turn a structurally valid receipt into a trusted result.

See [schema boundaries](../schemas/README.md) for required runtime checks. No additional dependencies are installed by this design change.

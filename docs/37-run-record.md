# 37 Run-record contracts

[日本語](37-run-record.ja.md) | [Home](../README.md)

**Scientist26: source and four test methods authored, NOT EXECUTED.** This narrow
[P1 record-contract](10-roadmap.md) increment adds a pure parser for the existing
[run-record schema](../schemas/run-record.schema.json). Recovery inspection and
operator tools do not implement research records. P1's other records, persistence
and authority checks, and P2's runner/protected evaluation/reproduction remain
separate unfinished work. No existing schema, wire version or source is changed.

[parse_run_record](../src/ai_agent_scientist/records/run_record.py) accepts exact
builtin `bytes` and an exact builtin integer `max_bytes` in 1..1048576 (default
1048576). It checks the byte cap before calling the existing
[strict JSON parser](../src/ai_agent_scientist/evidence/json_blob.py). Duplicate
decoded keys, BOM, malformed UTF-8/JSON and nonfinite numbers are refused.

All 12 schema fields are required, with no extras; artifact and usage objects
also have exact keys. Every string, including map keys and IDs, is nonempty,
at most 4096 UTF-8 bytes, and contains no NUL or surrogate. Each array/map has
at most 1024 entries. Artifact hashes are exactly 64 lowercase hexadecimal
characters; repeated artifact IDs, including identical artifact tuples, are
refused. Distinct IDs may share a hash. These local bounds narrow the accepted
profile without changing the schema.

The frozen, slotted `RunRecord` retains the original `data` object and its exact
byte `sha256`, six identity/revision strings, status and validity. Artifacts are
a tuple of frozen, slotted `ArtifactRef(id, sha256, kind)` values; metrics are a
tuple of `(name, value)` pairs in input order; `usage` is frozen, slotted `Usage`
with `wall_seconds` and `incremental_api_usd`; limitations are a string tuple.
Numbers retain builtin `int`/`float` types, without conversion; bool is refused.
Metrics may be negative or null; usage is nonnegative or null. Unknown usage
stays null rather than becoming zero. No canonicalization or reserialization.

This complete synthetic JSON illustrates a failed, unchecked summary, not a
real run or verified receipt:

```json
{
  "run_id": "run-1", "attempt_id": "attempt-1", "replicate_id": "replicate-1",
  "project_id": "project-1", "protocol_revision": "protocol-1",
  "candidate_revision": "candidate-1", "status": "failed", "validity": "unchecked",
  "artifacts": [{"id": "log-1", "sha256": "0000000000000000000000000000000000000000000000000000000000000000", "kind": "raw_output"}],
  "metrics": {"delta": -1.5, "score": null},
  "usage": {"wall_seconds": 0, "incremental_api_usd": null},
  "limitations": ["Synthetic fixture; no evaluation performed."]
}
```

All six statuses and four validity labels are preserved independently, including
`failed` and `unchecked`. Even `valid` is only an input label. Parsing does not
resolve artifacts, authenticate an issuer, verify evidence, authorize execution,
settle usage or promote validity/knowledge. These values are freely constructible
and confer no authority. The protected binding described in
[12](12-protocol-and-acceptance.md) remains outside this summary parser.

Failures use only `RunRecordRefused("run record refused")`, with no retained
decoder cause/context or payload-bearing error text. Traceback frame locals can
still contain private input: do not export them. Byte/item bounds are not full
CPU, memory or depth isolation.

[Four self-contained unittest methods](../tests/contracts/test_run_record.py)
contain **316 labelled subcases**: R01 26 (24 status/validity combinations,
null/empty values, alternate byte representation, with immutable value checks);
R02 30 (strict JSON and byte types); R03 202 (complete shape/semantic refusals);
R04 58 (predecode refusals, byte/string/collection limits and accepted boundaries).
All are authored **NOT EXECUTED**. Tests, imports, builds, link/language/JSON/status
checks and the [design checker](../scripts/check_design.py) were not run under
the explicit file-only instruction. No runtime acceptance, reproduction or
independent review is claimed; no runner, model/API or research run is started.

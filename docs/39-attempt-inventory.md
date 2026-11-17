# 39 Local Paired Attempt Inventory

[日本語](39-attempt-inventory.ja.md) | [Home](../README.md)

**Scientist28 P1/P2 status: source, exactly four self-contained unittest methods and paired documentation authored; NOT EXECUTED.** No tests, imports, builds, design/link/status checks, reproduction or independent review were executed for this increment. This is a pure offline denominator helper, with no runtime acceptance or research result.

[Source](../src/ai_agent_scientist/records/attempt_inventory.py) and [four scenarios](../tests/contracts/test_attempt_inventory.py) compose the actual [run-record parser](../src/ai_agent_scientist/records/run_record.py) described in [37](37-run-record.md) and the existing [strict JSON parser](../src/ai_agent_scientist/evidence/json_blob.py). The [run-record schema](../schemas/run-record.schema.json) and [P1/P2 roadmap](10-roadmap.md) remain unchanged.

`build_attempt_inventory(manifest_data: bytes, records: tuple[RunRecord, ...], *, max_bytes: int = 1048576)` returns frozen, slotted `AttemptInventory(data, sha256, project_id, protocol_revision, slots)`. Each frozen, slotted `AttemptSlot(spec, record)` contains a frozen, slotted `AttemptSpec(run_id, attempt_id, replicate_id, candidate_revision, role)` and the original record or explicit `None`. Slots follow manifest order even when records arrive in another order. Exact manifest bytes and their SHA-256 are retained without reserialization.

The local **INTERNAL** format below is a narrow paired profile, not a canonical schema change. This inactive synthetic example declares the entire denominator independently of available records:

```json
{
  "format": "offline-attempt-manifest/1",
  "project_id": "synthetic-project",
  "protocol_revision": "protocol-1",
  "attempts": [
    {"run_id": "run-b", "attempt_id": "attempt-b", "replicate_id": "replicate-1", "candidate_revision": "baseline-1", "role": "baseline"},
    {"run_id": "run-c", "attempt_id": "attempt-c", "replicate_id": "replicate-1", "candidate_revision": "candidate-1", "role": "candidate"}
  ]
}
```

Only these exact top-level and attempt keys are allowed. The strict existing decoder rejects duplicate keys, BOM, invalid UTF-8 and non-finite numbers. Exact builtin bytes/int/tuple are required; `max_bytes` is 1..1 MiB and bounds the manifest before decoding. Attempts are an exact nonempty list of at most 1024; records are an exact tuple of at most 1024. Every string is exact builtin `str`, nonempty, at most 4096 UTF-8 bytes, without NUL or surrogates.

Run IDs and attempt IDs are each globally unique. Every replicate must declare exactly one `baseline` and one `candidate`; duplicate `(replicate_id, role)` pairs and single-role replicates refuse. This profile excludes multiple candidates or retries under one replicate/role. It does not infer undeclared attempts.

Each supplied value must be an exact actual `RunRecord`. Its own bytes are reparsed with the actual parser's default 1 MiB cap; every field, including nested types, must equal reparsing. Freely constructed altered fields refuse. Duplicate or unexpected record run IDs and any project, protocol, run, attempt, replicate or candidate-revision mismatch refuse. No record is borrowed from another attempt. Matching records retain object identity and all failed/unchecked/null-usage values, metrics and limitations. Missing records remain `None`; no slot is dropped and no success, score, cost or validity is inferred.

Own validation, decoder and record-parser errors become only `AttemptInventoryRefused("attempt inventory refused")`, raised outside the handler without a payload-bearing cause/context. Byte/item bounds are not full depth/CPU/memory isolation. A manifest and content hash do not authenticate preregistration or prove declaration preceded outcomes. Completeness is relative to the supplied manifest.

The four authored scenarios are: a full parsed pair with identities and order preserved; a missing candidate with failed, unchecked baseline and null usage retained; one protocol mismatch refused; duplicate manifest attempt identity refused. They contain no test matrix and have not been run. Other validation branches remain unexecuted. The helper performs no storage, network, evaluator or budget actions and grants no authorization, protected evaluation, knowledge promotion or research authority. Existing DOTS/ChatGPT/Codex constraints and wire versions remain intact; real task state stays outside this public repository.

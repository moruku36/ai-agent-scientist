# 41 Private Evidence Report

[日本語](41-evidence-report.ja.md) | [Home](../README.md)

**Scientist30 P2 evidence-to-report audit: source, exactly four self-contained
unittest methods and paired docs authored; NOT EXECUTED.** Tests, checks
(including design/link/language/JSON/status checks), imports and builds were
not run under the file-only instruction. Execution, reproduction, independent
review and runtime acceptance remain pending. No science, evaluator, network,
model/API, deployment or child launch occurred.

[Source](../src/ai_agent_scientist/records/evidence_report.py) and
[four scenarios](../tests/contracts/test_evidence_report.py) connect the actual
[37 parser](37-run-record.md), [38 private blob store adapter](38-run-store.md),
[39 inventory](39-attempt-inventory.md) and [40 comparison](40-paired-metrics.md).
The protected evaluation and scientific claims in
[12](12-protocol-and-acceptance.md) remain separate.

`build_private_evidence_report(inventory: AttemptInventory, *, metric: str,
direction: str, max_output_bytes: int = 1048576)` returns frozen, slotted
`PrivateEvidenceReport(data, sha256, manifest_sha256, expected_attempts,
present_attempts, missing_attempts)`. First it requires an exact builtin integer
cap in 1..1048576, rejecting bool before any comparison. It then calls actual29
`compare_paired_metrics` exactly once, relying on its complete revalidation of
inventory/record bytes, nested types, identities and selectors. There is no
second rebuild, store read or caller-supplied comparison shortcut. Actual29
exceptions propagate unchanged, including identity, without retry.

The internal format is `offline-evidence-report/1`, with scope
`unverified_private_local_summary`. Top-level fields bind the exact manifest
SHA-256, project/protocol IDs, selected `metric`/`direction`, expected/present/
missing attempt counts, `declared_pair_count` and `paired_observation_count`.
`attempts` contains every slot in manifest order: `run_id`, `attempt_id`,
`replicate_id`, `candidate_revision`, `role`, `record_sha256`, `status`,
`validity`, `usage` (only `wall_seconds` and `incremental_api_usd`),
`limitation_count` and selected `metric_value`. Missing record fields, including
limitation count, are null; missing/unknown usage stays null, never zero.
No other metric names/values, freeform limitations, raw record bytes, artifact
references/payloads or authorization paths enter the projection.

Every pair retains actual29's first-manifest-appearance order and exact
`replicate_id`, `baseline_run_id`, `candidate_run_id`, `classification`,
`baseline_value`, `candidate_value`, `raw_delta` and `directional_delta`.
Missing and ineligible pairs remain in the denominator. No outcome filtering,
success sorting, winner, aggregate estimate, inference or proof is added.
Completeness is only relative to the supplied manifest.

This inactive synthetic excerpt shows counts and a retained missing pair;
metadata and the full two-entry `attempts` array are omitted from this excerpt,
never from a returned artifact:

```json
{
  "format": "offline-evidence-report/1",
  "scope": "unverified_private_local_summary",
  "metric": "score", "direction": "maximize",
  "expected_attempts": 2, "present_attempts": 1, "missing_attempts": 1,
  "declared_pair_count": 1, "paired_observation_count": 0,
  "pairs": [{"replicate_id": "replicate-1", "baseline_run_id": "run-b",
             "candidate_run_id": "run-c", "classification": "missing_record",
             "baseline_value": 10, "candidate_value": null,
             "raw_delta": null, "directional_delta": null}]
}
```

Encoding uses UTF-8 with `allow_nan=False`, `sort_keys=True`,
`separators=(',', ':')`, `ensure_ascii=True`. SHA-256 binds these exact bytes;
this is neither JCS nor logical identity. The cap applies to the whole encoded
artifact: oversize, encoding or overflow failures yield only
`EvidenceReportRefused("evidence report refused")`, raised outside the handler
without encoder cause/context. No partial/truncated report is returned. The
output cap is not a full memory/CPU/isolation or aggregate-input limit.

The four authored scenarios are A actual27 store/load of two synthetic records
in a private temporary BlobStore, through actual28 to the report, checking exact
bytes/hash/counts/deltas and omission of secret metrics, freeform limitations,
artifact references and a stored artifact payload without resolving it; B a
retained missing candidate and full denominator; C valid inventory with a
one-byte cap refusing the whole artifact; D bool cap refusing before patched
actual29 can run. Each method calls the report once; fixtures are local, with
no historical test imports, loops, scenario tables, subtests or extra variants.
Ordering is apparent in source; determinism is not tested by repeated execution.

**PRIVATE:** IDs and selected metrics can still be sensitive. Do not publish
automatically; real evidence and traceback locals stay outside this public
repository. Constructors confer no authority, and source status/validity labels
are not authenticated receipts. The helper performs no writes, clock access,
storage, network, export, authentication, authorization or evaluation. Existing
DOTS/ChatGPT/Codex constraints, dependencies and schemas/wire versions are unchanged.

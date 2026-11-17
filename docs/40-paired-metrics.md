# 40 Paired Metric Observations

[日本語](40-paired-metrics.ja.md) | [Home](../README.md)

**Scientist29 status: source, exactly four self-contained unittest methods and paired documentation authored; NOT EXECUTED.** No tests, checks, imports, builds, reproduction or independent review were executed for this increment. This is an offline observation helper, without runtime acceptance or a research result.

[Source](../src/ai_agent_scientist/records/paired_metrics.py) and [four scenarios](../tests/contracts/test_paired_metrics.py) compose the actual [attempt inventory](39-attempt-inventory.md) and [run-record parser](../src/ai_agent_scientist/records/run_record.py). The scientific and protected-evaluation requirements in [12](12-protocol-and-acceptance.md) remain separate and unchanged.

`compare_paired_metrics(inventory: AttemptInventory, *, metric: str, direction: str)` returns frozen, slotted `PairedMetricComparison(inventory, metric, direction, pairs)`. It retains the original inventory. Each frozen, slotted `MetricPair(replicate_id, baseline, candidate, classification, baseline_value, candidate_value, raw_delta, directional_delta)` retains the original baseline/candidate `AttemptSlot` objects. `pairs` is a tuple containing every declared replicate exactly once, in first manifest appearance order. Pairing uses actual `spec.replicate_id` and role, independent of record arrival order; inventory validation requires both roles in every replicate.

The inventory must have the exact actual type. Before reconstruction, the metric must be exact builtin `str`, nonempty, at most 4096 UTF-8 bytes, without NUL or surrogates; direction must be exact builtin `str` equal to `maximize` or `minimize`. Reconstruction calls `build_attempt_inventory(inventory.data, tuple(non-None records in slots))` with its default bounds. Recursive comparison requires exact types and equal values for every inventory field, slot, spec, record, artifact, usage, tuple and nested scalar, including hashes and original bytes. Ordinary dataclass equality would accept `True` for `1` or `1.0` for `1`; those substitutions and forged slots refuse. Only revalidated exact builtin parser numbers are used, with no coercion.

Classifications have this priority; earlier conditions always take precedence:

| Classification | Condition | Deltas |
|---|---|---|
| `missing_record` | Either record absent | Both `None` |
| `ineligible_status` | Both present, either status other than `completed` | Both `None` |
| `unchecked_validity` | Both completed, either validity other than `valid` | Both `None` |
| `missing_metric` | Both completed/valid, metric key absent or null on either side | Both `None` |
| `numeric_range_unsupported` | Otherwise, subtraction/sign arithmetic raises `OverflowError` or yields a nonfinite float | Both `None` |
| `paired_observation` | Both completed/valid, both values present, arithmetic supported | Candidate minus baseline; same sign for maximize, negated for minimize |

Available original values remain present even for ineligible or range-unsupported pairs; missing keys/records and null values appear as `None`. Integer arithmetic stays exact without float conversion. Mixed/float arithmetic follows Python builtin arithmetic: overflow or a nonfinite result retains the pair and its source values, with no infinite delta. No pair is dropped and no missing value is replaced by zero. Completeness is relative to the supplied manifest, not evidence that all real attempts were declared.

This inactive synthetic JSON illustrates selected observation fields, not a new wire format or an executed result:

```json
{
  "metric": "score", "direction": "minimize",
  "pairs": [{"replicate_id": "replicate-1", "classification": "paired_observation",
             "baseline_value": 10, "candidate_value": 11,
             "raw_delta": 1, "directional_delta": -1}]
}
```

Own validation and reconstruction failures produce only `PairedMetricsRefused("paired metrics refused")`, raised outside the handler without a payload decoder cause/context. Existing byte/item bounds are not complete depth, CPU or memory isolation. Status and `valid` are caller-supplied source labels, not authenticated execution success or protected verification proof. Even `paired_observation` is only an eligible observation: no average, winner, success decision, promotion, statistical inference or evaluator is provided.

The four authored scenarios cover the completed/valid integer pair (11 versus 10, minimize: 1 and -1), a retained failed candidate without deltas, a retained missing candidate without denominator loss, and a nested `Usage.wall_seconds=True` substitution for parsed integer `1` refused despite ordinary equality. Fixtures are local; no historical tests are imported, and there are no loops, tables, subtests or parameterized scenario variants in the tests. All four and other branches remain unexecuted. No store read, network, artifact resolution, runtime, model/API/science run or child process is launched by this helper. Existing DOTS/ChatGPT/Codex constraints, dependencies and wire/schema versions remain unchanged; private task state remains outside the public repository.

# 38 Run-record blob storage

[日本語](38-run-store.ja.md) | [Home](../README.md)

**Scientist27: source, exactly four self-contained unittest methods and paired
docs authored, NOT EXECUTED.** This narrow [P1 increment](10-roadmap.md) connects
the unchanged [Scientist26 parser](37-run-record.md) to the existing
[BlobStore](../src/ai_agent_scientist/evidence/blob_store.py). No architecture,
schema, wire version, dependency or existing file changes.

[Source](../src/ai_agent_scientist/records/run_store.py) exposes
`store_run_record(store: BlobStore, data: bytes, *, max_bytes=1048576) -> RunRecord`
and `load_run_record(store: BlobStore, sha256: str, *, max_bytes=1048576) -> RunRecord`.
Both require an exact concrete `BlobStore` and an exact builtin integer cap in
1..1048576. Before any storage call, the store's configured cap must be an exact
builtin integer in 1..max_bytes. This bounds the actual `get`, which has no
per-call cap; a larger store is refused, never replaced or reconfigured.

Store calls the actual26 parser on exact builtin bytes before storage, enforcing
the caller byte cap. It delegates exactly once to `store.put` with the original
bytes and requires its returned exact string digest to equal the parsed SHA-256.
Existing-digest verification semantics remain those of `BlobStore.put`: bytes
are never reserialized, overwritten or repaired. Load validates an exact builtin
string of 64 lowercase hex characters before one actual `store.get`, then uses
the actual26 parser and requires the parsed hash to equal the requested hash.

Malformed store/digest/cap or failed hash binding produces only
`RunStoreRefused("run store refused")`. An unexpected trusted `put` return is a
binding refusal. Parser errors propagate without payload-bearing decoder chains;
storage exceptions propagate unchanged, including object identity. No wrapping
or retry. Traceback locals may contain private bytes and must stay private.

The synthetic JSON below is a summary only; null usage remains unknown:

```json
{
  "run_id": "run-1", "attempt_id": "attempt-1", "replicate_id": "replicate-1",
  "project_id": "project-1", "protocol_revision": "protocol-1",
  "candidate_revision": "candidate-1", "status": "failed", "validity": "unchecked",
  "artifacts": [], "metrics": {"score": null},
  "usage": {"wall_seconds": null, "incremental_api_usd": null},
  "limitations": ["Synthetic; no evaluation."]
}
```

Trust is the existing private, owner-controlled POSIX filesystem profile: one
trusted owner/writer, trusted root and ancestors, no concurrent attacker control.
The caller supplies the existing store; the helper constructs none. A write may
have committed before an exception or binding refusal. There is no automatic
retry, rollback, delete or repair. Loading a known hash is observation only and
does not prove write completion/durability. There is no registry, index, logical
idempotency or run-identity uniqueness. Parsed records are freely constructible;
status/validity labels grant no authority. No dispatch, evaluation, authentication,
authorization or evaluator-proof claim is added. Real records stay outside this
public repository.

[Tests](../tests/contracts/test_run_store.py) author **four methods, four scenarios
total**: a real private temporary store/load exact-byte roundtrip with null usage;
invalid run-record rejection before put with no writes; invalid digest rejection
before get; and a real tampered final blob propagating the identical observed
storage integrity error with one get and no retry. No historic test classes or
hidden subcases. Tests, checks (including design/link/language/JSON/status checks),
imports and builds were not executed under the file-only instruction. Execution,
reproduction, independent review and runtime acceptance remain pending. No model,
API, network, research, child-agent or service execution occurred.

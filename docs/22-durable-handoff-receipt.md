# 22 Durable Byte-Bound Handoff Receipt (P1, Offline)

[日本語](22-durable-handoff-receipt.ja.md) | [Home](../README.md)

**Reservation extension:** [23](23-local-budget-reservation.md) adds connected `reserve` in the same module, implemented with ten scenarios passed once offline (0.082s); coordinator diff review completed. Receipt-only limits and historical D01–D10 results below describe the original `record` path and do not validate this extension. `record` still creates no reservation. Constructor initialization also creates empty internal reservation/accounting tables; only `reserve` writes those rows. No dispatch or full admission authority is added.

**Status (2026-11-17): implemented; ten new D01–D10 scenarios passed once offline (1.172s).** The implementer ran no tests, design checker, imports of the implementation for execution, research or dispatch. Coordinator source review and one targeted invocation completed; required design-check results are recorded separately. No reproduction, independent review, runtime acceptance or power-loss result is claimed. Python 3.12 compatibility is a source target only.

This is a narrow connected seam within [P1](10-roadmap.md), composing the actual [21 binding loader](21-handoff-payload-binding.md), [20 request preflight](20-handoff-request-preflight.md), [19 strict reader](19-json-blob-reader.md) and [18 BlobStore](18-immutable-blob-helper.md) with stdlib SQLite. Architecture and the canonical [harness-handoff/1 schema](../schemas/handoff.schema.json) are unchanged.

## Partial docs11 profile and ownership

This implements only receiver-owned local receipt persistence and an unresolved marker from [11](11-harness-boundaries.md). Identity is the **original envelope `request_sha256` over exact stored bytes**, as verified by the real loader. No digest is computed from a parsed or sorted JSON representation. Whitespace, key order, message ID, creation time, expiry and every other byte change conflict under a reused request key. Full docs11 logical request identity (which excludes transport fields), RFC 8785 JCS, admission, reservation, outbox delivery, attempts, fencing, retry and settlement remain missing. This receipt is internal metadata, not a new wire response or a protected evaluator receipt.

The trusted caller selects the private database path and supplies `TrustedHandoffScope(principal, project_id, sender, recipient)` independently of the envelope. `principal` is the caller's declaration of an independently authenticated identity; this module performs no authentication and makes **no sender authenticity claim**. Wire `sender` is only a logical endpoint and must exactly match that supplied mapping, along with project and recipient. Deriving the mapping, path, stores or access table from candidate content defeats the trust boundary.

The request key is `(principal, project_id, recipient, request_id)`. A unique `(principal, project_id, recipient, message_id)` also prevents delivery-ID reuse for another request/digest. Sender is retained and checked against the mapping, not used to create an alternate namespace. Different trusted principals/projects/recipients have separate namespaces; changing a principal declaration is a caller authority decision, not a way to authenticate a sender.

## Explicit local API

[Source](../src/ai_agent_scientist/admission/durable_handoff.py):

```python
scope = TrustedHandoffScope(principal, project_id, sender, recipient)
receiver = DurableHandoffReceipts(db_path, scope=scope)
receipt = receiver.record(
    request_store, request_sha256,
    payload_store=payload_store, bindings=current_bindings, now=fresh_utc_now,
)
retained = receiver.inspect(request_id)  # DurableReceipt or None; metadata only
unresolved = receiver.require_reconciliation(
    request_id, expected_revision=receipt.revision, now=fresh_utc_now,
)
```

`scope` must be the exact frozen local dataclass; its four fields, request/message IDs and inspection IDs must be exact nonempty builtin strings, valid UTF-8, no NUL, at most 1024 UTF-8 bytes. Endpoint roles retain the canonical enums. Path must be an exact builtin absolute string with no NUL or `..` segment; SQLite URI mode is disabled. SQL is fixed internally with bound values. There is no network or untrusted SQL/path resolver.

`now` must be an exact `datetime` with `tzinfo is timezone.utc`. The caller supplies a fresh trustworthy instant on each call, current scoped bindings, and independently selected exact `BlobStore` instances. `record` calls `load_bound_handoff_request` on **every** creation and replay before opening its receipt transaction: verified bounded strict-JSON envelope read, real request preflight/expiry, current binding match/access/cap and actual verified payload bytes. Payload bytes are then discarded. It checks the scope and initial revision; it never serves payload from the database or treats an existing receipt as current access.

An initial envelope requires exact builtin integer `expected_revision=0`, creating revision **1**, state **`recorded`**. Replaying identical bytes returns the current persisted receipt, including timestamps and any unresolved marker, without resetting or incrementing it. Different bytes with the same request key raise `ReceiptConflict`; message collision also raises `ReceiptConflict`. Nothing is dispatched or reserved.

`require_reconciliation` is a receiver-local CAS, separate from wire requests. Only `recorded` revision 1 → `reconciliation_required` revision 2 exists. Both states remain unresolved. Missing/stale revisions raise `ReceiptRevisionError`; repeated transition at current revision raises `InvalidReceiptTransition`. No backward transition, implicit retry, cancellation, completion or settlement exists. Revisions must be exact builtin ints in `0..2**63-1`, excluding bool/subclasses; incrementing the maximum is refused before SQLite binding. A backward supplied transition timestamp is refused. A new receiver instance reopens the same retained state.

`inspect` and local reconciliation can operate after envelope/access expiry or revocation because they expose only retained metadata. They confer no blob access, authorization or continuing authority. Later `record` still repeats all current checks and refuses expired/revoked/unavailable input even when the receipt exists.

## Synthetic retained metadata example

This JSON illustrates a local receipt snapshot, not a canonical handoff envelope, authentication proof or dispatch permission. Digests are synthetic placeholders; the actual API returns a frozen `DurableReceipt`.

```json
{
  "principal": "trusted-local-principal", "project_id": "p1", "recipient": "ctf",
  "request_id": "r1", "sender": "scientist", "message_id": "m1",
  "request_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "payload_sha256": "1111111111111111111111111111111111111111111111111111111111111111",
  "revision": 2, "state": "reconciliation_required",
  "recorded_at": "2026-11-17T12:00:00.000000Z",
  "updated_at": "2026-11-17T12:00:02.000000Z"
}
```

The internal SQLite table stores only these fixed digest, identity and receipt metadata columns, with primary/unique constraints and a two-state revision check. It stores neither envelope/payload bytes nor authorization/reservation records or credentials. It has no budget, admission, dispatch or evaluator/knowledge-promotion authority.

## Transactions, failures and local trust

Each operation opens/closes its own local connection; writers use `BEGIN IMMEDIATE` and readers a read transaction, with a one-second SQLite lock timeout and `synchronous=FULL`. Deduplication, collision checks, insert and CAS are serialized by SQLite transactions and constraints. Success is returned only after commit. Exceptions roll back an active transaction; rollback/close failures are reported through errors/notes, never successful receipts. `sqlite3.Error` and filesystem errors become `ReceiptStorageError` with private chained diagnostics. Existing loader errors propagate unchanged and prevent a new receipt row. A failed commit/connection/cleanup can leave an uncertain observed outcome: preserve the DB and inspect/replay through current checks rather than assuming absence or dispatching. No manual recovery, deletion or repair is implemented.

The POSIX database parent must already exist, be owned by the current UID and have no group/other permission bits (normally 0700). Missing DB files are exclusively created with mode 0600; existing files must be regular, owned by that UID, private, non-symlink and single-link. Ancestors are checked for real directories, and replacement of the file inode during one receiver's lifetime is refused. These are misconfiguration checks, **not malicious database defense**. All ancestors, the DB and SQLite journal/sidecar paths, local processes and module/store methods must be trusted and outside candidate control, without concurrent replacement or permission changes. The caller provisions and enforces that boundary; this module cannot prove who controls the directory or authenticate DB contents, triggers or an existing schema. No network filesystem, hostile file race, same-UID attacker, corruption recovery or migration guarantee is provided.

Envelope/payload memory is bounded by caller-selected BlobStore caps; receipt identifiers have the cap above. The caller must budget total row count, disk/journal space, operation count and the SQLite environment. There is no total database quota, CPU/memory isolation or atomic transaction with the separate binding table/BlobStores. The caller serializes access-table/store changes across a call; revocation after the supplied instant, stale caller metadata and clock rollback cannot be detected generally. SQLite commit/reopen is the persistence seam, **not a tested power-loss, hardware-durability or backup claim**. Keep private operational data outside this public repository. Stopping use preserves receipts/blobs and never authorizes a retry.

## Checks executed once offline

[Targeted test file](../tests/contracts/test_durable_handoff.py) contains exactly ten new offline unittest scenario methods, no historical test imports:

| ID | Scenario passed once offline |
|---|---|
| D01 | Actual connected envelope/payload reads and minimal durable receipt |
| D02 | Reopen, exact replay, current unresolved CAS and stale/repeated transition |
| D03 | Exact-byte conflicts, including whitespace, message/time/expiry and changed verified payload |
| D04 | Message collision, independent identity namespaces and changed sender mapping |
| D05 | Initial/CAS revisions, bool/subclass/hostile values, int overflow and clock bounds |
| D06 | Project/sender/recipient mismatches, scope/path guards and unsafe local roots |
| D07 | Fresh preflight, strict JSON, access expiry/revocation before insert and on replay; retained inspection |
| D08 | Actual missing/tampered/oversize blobs and propagated I/O errors |
| D09 | Insert/update/commit fault rollback, local lock contention and post-commit close-error replay |
| D10 | Two concurrent local connections: one duplicate receipt and one CAS winner |

After source review, the coordinator ran the targeted command once: ten scenarios passed in 1.172s. The required design checker uses the existing validation environment; no installs or historical reruns. Neither command below was run by the implementer:

```sh
env PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/contracts -p test_durable_handoff.py -v
python -B scripts/check_design.py
```

Actual check outcomes are retained in the coordinator report. Design checks concern document links, language pairs, JSON examples/schema and status consistency; they establish no runtime or scientific acceptance.

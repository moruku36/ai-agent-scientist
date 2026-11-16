# 19. Strict JSON blob reader

[日本語](19-json-blob-reader.ja.md) · [Home](../README.md)

Status: **implemented**; J01–J08 in `tests/contracts/test_json_blob.py` **passed once offline** (8 tests, 0.011 seconds) on Python 3.15.2. Python 3.12 compatibility is a source target, not an executed-interpreter claim.

This is one narrow input-boundary prerequisite. It makes JSON stored in the [immutable blob helper](18-immutable-blob-helper.md) readable with strict decoding, as required by the duplicate-key and non-finite rejection rule in [harness boundaries](11-harness-boundaries.md). It does **not** accept records.

## API (`src/ai_agent_scientist/evidence/json_blob.py`)

- `parse_json_bytes(data: bytes) -> object`: exact builtin `bytes` only (subclasses, `bytearray`, `str` raise `TypeError`).
- `load_json_blob(store, sha256) -> object`: calls `store.get` once, then `parse_json_bytes`. No writes, no side effects.
- `InvalidJSONBlob(ValueError)`: generic, payload-free message.

## Profile (this helper only, no wire version change)

- UTF-8 only; a UTF-8 BOM, UTF-16 and UTF-32 are rejected.
- JSON grammar must match exactly; trailing content and empty input are rejected.
- Duplicate keys are rejected recursively, including escape-equivalent keys. Equality uses decoded code points; no Unicode normalization.
- `NaN`, `Infinity`, `-Infinity` and floats overflowing to infinity (`1e999`) are rejected.
- Integers are arbitrary-size, subject to the interpreter digit limit (failure becomes `InvalidJSONBlob`).
- No canonicalization. Sorted JSON is not JCS; escaped unpaired surrogates may survive, so this is not I-JSON/JCS eligibility.

## Errors

Underlying parser, decode, integer-limit and recursion failures become `InvalidJSONBlob` with the original exception as `__cause__`. Explicit BOM, duplicate-key and non-finite checks raise `InvalidJSONBlob` directly, without a wrapped cause. Only `ValueError` and `RecursionError` are wrapped; `MemoryError` and `BaseException` pass through. Storage errors (`InvalidInput`, `BlobTooLarge`, `BlobNotFound`, `BlobIntegrityError`, `BlobIOError`) propagate unchanged and are never converted to parse errors or masked; parsing does not run after a failed read.

The public message is generic, but chained causes are owner-only: for example `JSONDecodeError.doc` can retain the input. A traceback is not a safe export.

## Limits

- The exact-byte SHA-256 is unchanged; no digest is recomputed after decoding. Representations differing only in whitespace or object-key order have different byte digests but equal decoded objects.
- A hash does not imply access, schema, semantics, authentication or revocation. There is no schema validation, record admission, registry, JCS, I-JSON or SCI acceptance. The registry stays blocked on the unchosen record, revision and JCS decisions.
- The byte cap comes from `BlobStore` only; direct `parse_json_bytes` calls have no size cap and require caller-bounded bytes. Neither API provides a depth, CPU or memory-isolation limit.
- The trusted caller chooses the concrete store and enforces current access. There is no contains, list, delete or URL path.
- Inherits the blob cap and trusted single-writer POSIX assumptions of docs 18.

## Executed scenarios (one invocation)

J01 round trip; J02 duplicate keys and no key leak; J03 non-finite numbers; J04 encodings and BOM; J05 malformed input, exact type, chained cause; J06 missing and tampered entries skip parse; J07 oversize and injected I/O error propagate; J08 distinct digests with equal objects, read-only store, recursion wrapping.

No research runs are involved.

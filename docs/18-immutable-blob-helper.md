# 18 Immutable Exact-Byte Blob Helper

[日本語](18-immutable-blob-helper.ja.md) | [Home](../README.md)

**Status (2026-11-17): implemented; E01–E12 in `tests/contracts/test_blob_store.py` passed in one offline invocation (12 tests, 0.013 seconds) on Python 3.15.2.** Python 3.12 compatibility is a source target, not an executed interpreter claim. This is a P1 hash/persistence prerequisite only. It is not a registry, admission, authorization, receipt issuer or research runtime. See [03 architecture](03-architecture.md) (SHA-256 filesystem blobs), [11 harness boundaries](11-harness-boundaries.md) (byte hashes versus JCS manifest IDs) and [10 roadmap](10-roadmap.md).

## What it does

`BlobStore(root, *, max_blob_bytes)` stores opaque bytes at `root/<sha256>` and returns the lowercase hex digest of the exact bytes.

- `put(data: bytes) -> str`: exact built-in `bytes` only (no `bytearray`/`str`); empty bytes allowed; length must be at most the cap.
- `get(sha256: str) -> bytes`: the digest must be exactly 64 lowercase hex characters before any path is built; reads at most cap+1 bytes and verifies the digest before returning.
- Deliberately omitted: contains, delete, list, JSON import, record acceptance, receipts.

Equal bytes deduplicate and return the same digest, also across fresh helper instances. Different bytes (even JSON differing only by whitespace) are different objects. The helper has no logical request key, so it cannot detect a reused request ID, and deduplicating bytes never deduplicates scientific repetitions.

## Byte identity is not JCS

The digest is SHA-256 over the exact bytes, with no decoding, newline/Unicode normalization or key sorting. It cannot compute the RFC 8785 (JCS) structured-manifest identity used in [11](11-harness-boundaries.md). Optimistic revisions, idempotency and expected-revision handling are not implemented; no schema or wire version changes.

## Accepted local profile

Single trusted owner / single writer on POSIX. The root must already exist, be a real directory chosen by the trusted caller, and neither the root nor its ancestors may be attacker-controlled concurrently. The root is validated before each operation. A root that is missing or not a directory, or a symlink, is `InvalidInput`; a permission or other filesystem failure on the root is `BlobIOError`. If `os.link`, `fsync`, `O_NOFOLLOW`, `O_DIRECTORY` or `O_EXCL` is unavailable, construction fails closed with `BlobIOError`. There is no overwrite fallback.

Install sequence for a new object: unique same-directory staging file created exclusively (mode 0600), full write, file fsync, close, `os.link` to the final name with no replacement, remove the staging name, fsync the root directory. If the final name already exists, it is read and verified first; it is never replaced or repaired. Staging names (`.<digest>.<random>.stage`) are never evidence and are never promoted or swept; unrelated orphans are ignored.

## Errors

`BlobStoreError` base; `InvalidInput`, `BlobTooLarge`, `BlobNotFound`, `BlobIntegrityError` (digest mismatch, final symlink or nonregular entry), `BlobIOError`. Filesystem errors are translated with the original exception chained as the cause. Messages never include payload bytes. A final entry that disappears during access is `BlobNotFound`; permission and other I/O failures are never reported as not found.

## Failure behavior

- Own staging is removed on every failure where possible. A failed cleanup is reported (as `BlobIOError` after an otherwise successful install, or as a note on the primary exception), never as silent success.
- If a failure occurs after the final object is installed (for example, directory fsync), the valid object stays. The caller must not infer absence from an exception; retrying the same bytes or calling `get` reconciles.
- An existing corrupt, oversize, symlink or nonregular final entry is rejected and left untouched.

## Limits

Not tested for power loss, hardware durability, cross-host or network filesystems, multiple concurrent writers, corruption recovery, backups or migration. Immutability is by convention of this helper, not OS-enforced against the owner. A successful `get` does not mean access is currently permitted or the claim unrevoked: the caller must enforce access, authorization and revocation (SCI-12) before serving an object. A hash does not authenticate an issuer or promote knowledge ([13](13-verified-discovery.md)). Example fixtures (expired handoff, disabled CPU pilot) must not be ingested as approved live requests. The caller keeps the semantic ID, type and classification separately.

## Executed cases (one invocation)

| ID | Scenario |
|---|---|
| E01 | Known SHA-256 vectors, including empty bytes |
| E02 | Same bytes twice across fresh instances: one object |
| E03 | Whitespace/one-byte differences give distinct objects |
| E04 | Invalid type/cap/root; root permission failure is `BlobIOError` |
| E05 | Exactly cap persists; cap+1 is `BlobTooLarge` before write |
| E06 | Invalid digests rejected before filesystem access |
| E07 | Absent versus injected permission/I/O failure |
| E08 | Tampered final object rejected on `get` and `put`, not overwritten |
| E09 | Oversize, symlink and nonregular final entries |
| E10 | Write/file-fsync/pre-install link failures leave no final object; post-install cleanup failure is reported and leaves the valid final object |
| E11 | Destination appears at install: matching verified, corrupt rejected, never replaced |
| E12 | Directory fsync failure after install; reopen reconciles, orphan ignored |

These are unit and fault-injection checks of the exercised behavior only. They do not establish SCI-01–20, real admission, durability or independent reproduction.

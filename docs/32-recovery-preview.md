# 32. Reconciliation preview

Japanese: [32-recovery-preview.ja.md](32-recovery-preview.ja.md) | [README](../README.md)

## Status

- Proposed and authored; **NOT EXECUTED**. No test, check or run has been performed for this increment.
- Six offline synthetic unittest methods are planned in `tests/contracts/test_recovery_preview.py`. The full outstanding reservation is unchanged.
- This advances P1 explicit recovery intent and review. It adds no runtime, schema, wire version, CLI or service.

## What it is

`build_reconciliation_preview(receiver, request_id, *, max_output_bytes=65536)` in `src/ai_agent_scientist/admission/recovery_preview.py` joins one real selected recovery detail (`render_recovery_detail`, called exactly once) to a caller-reviewable description of the action `mark_reconciliation_required`. It returns a frozen `ReconciliationPreview(data, sha256, request_id, request_sha256, expected_revision)`, or `None` when the request is missing or receipt-only.

- The byte cap must be an exact builtin integer in 1..1048576 and is validated before any read. The whole artifact is refused (`RecoveryPreviewTooLarge`) when it exceeds the cap; it is never truncated.
- Only state `recorded` is previewed. Any other state raises the value-free `RecoveryPreviewRefused`.
- The bytes are deterministic: sorted keys, ASCII, compact, no trailing newline, DEL escaped.
- JSON fields: private local version `recovery-reconciliation-preview/1`, action, request id, request digest, expected revision, source detail SHA-256, the exact full source detail text, and a limitations string.

## Limits

- Private and local. Not authority. The preview is never executed; it does not stop, release, settle, authorize or dispatch anything and performs no writes, clock reads or receiver construction.
- `sha256` hashes the preview bytes. It is not a CAS token and not authentic human confirmation. A forged object is not a capability; trusted caller and receiver are assumed.
- A future application step must re-read and compare before the existing receipt CAS. The separate snapshot race between preview and action remains.
- Storage and read errors propagate unchanged.

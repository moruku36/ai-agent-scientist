# 33. Recovery preview application

[README](../README.md) · [32 Recovery preview](32-recovery-preview.md) · [日本語](33-recovery-apply.ja.md)

Status: authored, NOT EXECUTED. All checks are pending.

`apply_reconciliation_preview(receiver, preview, *, now)` is an EXPLICIT action by a trusted in-process caller. It joins an immutable `ReconciliationPreview` to the EXISTING `mark_recovery_for_reconciliation` and its receipt CAS. It adds no store, receiver construction, clock, IO, process, network or authority. It never runs automatically and does not authenticate human intent.

## Steps

1. Validate the preview shape before any read: exact type, bytes of length 1..1048576, lowercase sha256 equal to SHA256(data), nonempty request_id of at most 1024 characters, lowercase request_sha256, integer expected_revision >= 1. Failure raises value-free `RecoveryApplyRefused`.
2. Rebuild the preview once with `build_reconciliation_preview`. None, a state refusal, or any difference from the supplied preview refuses before writing. Equality is compared on the trusted builder output, so the supplied bytes are never parsed.
3. Delegate once to `mark_recovery_for_reconciliation` with the expected digest, revision and injected `now`. It performs its own inspection and the receipt CAS.

## Limits

- The initial preview read, the fresh rebuild, the mark inspection and the receipt CAS are separate snapshots.
- Full equality detects ack, observation and status changes completed before the rebuild. It is NOT atomic full-snapshot fencing: a competing acknowledgment after the rebuild can still allow the mark, because the CAS fences only the receipt revision.
- Already marked requests refuse; they are not idempotent success.
- Receiver and storage errors propagate. There are no retries.
- No settlement, dispatch, release, cleanup, budget or permission change.

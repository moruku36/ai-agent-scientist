# 31. Recovery operator workflow (queue -> detail -> explicit mark)

[日本語](31-recovery-operator.ja.md) | See also [29 console](29-recovery-console.md), [30 queue](30-recovery-queue.md).

Status: **authored, NOT EXECUTED**. Private, local, in-process. Not authority, not a wire format, not runtime acceptance.

## Flow

1. `render_recovery_queue(receiver, reasons=(...))` lists candidates by conservative reason code.
2. `render_recovery_detail(receiver, request_id)` shows ONE selected request (any request, also outside the last queue page). Returns `RecoveryDetailView(text, request_id, request_sha256, revision, state)` or `None` for a missing or receipt-only request.
3. A trusted caller MAY then choose to mark it:

```python
view = render_recovery_detail(receiver, 'req-1')
receipt = mark_recovery_for_reconciliation(
    receiver, request_id=view.request_id,
    expected_request_sha256=view.request_sha256,
    expected_revision=view.revision, now=injected_now)
```

The mark is never automatic; queue and detail only read.

## Detail content

Header `PRIVATE ... NOT AUTHORITY`, request/payload digests, reservation reference and full outstanding worker-seconds, the retained latest observation (ID, sequence, time, expected revision), the retained status event (ID, receipt revision, ack timestamp) and the normal summary line with reasons. The `request_sha256` and `payload_sha256` shown are receipt identity fields, not report hashes and not authorization. All values are JSON-escaped printable ASCII. Absent evidence prints `UNKNOWN`/`unknown`, never zero. `max_output_bytes` (exact int 1..1048576) is a whole-view refusal, never truncation. The detail does not construct a receiver and writes nothing.

## Mark semantics

- Digest (64 lowercase hex) and revision (positive int) types are checked before any read.
- One `inspect_recovery_triage` call must show an existing reservation, the exact request digest, the expected revision and state `recorded`; otherwise a value-free `RecoveryMarkRefused`. Receipt-only requests are refused.
- Then exactly one `receiver.require_reconciliation(...)` runs, keeping its atomic CAS and clock validation. `now` is injected, never sampled.
- Already requiring reconciliation is a refusal, not replay success.
- The delegated existing transition updates the receipt and appends its existing local status event. No new store, reservation/budget change, acknowledgment or observation write is added.

## Snapshots and races

Inspection and CAS are separate transactions. If the receipt changes between them, the existing CAS fails (`ReceiptRevisionError`) and this action makes no additional change; the concurrent writer's change remains. The helper does not read again to fake an atomic view and does not authenticate caller, scope or history; the receiver and caller must be independently trusted. Queue and detail are independent snapshots.

## Non-claims

Marking records only an explicit trusted-caller reconciliation request, not proof of human action. It does not stop work, clean up, release or settle budget, authorize, admit, dispatch, retry, or complete anything, and the reservation stays fully outstanding. Tests use synthetic local fixtures only; no operational database is touched.

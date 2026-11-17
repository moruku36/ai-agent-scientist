# 30. Recovery operator queue (PRIVATE, authored NOT EXECUTED)

[日本語](30-recovery-queue.ja.md) · Builds on [29 console](29-recovery-console.md).

`render_recovery_queue(receiver, *, reasons, ...)` in `recovery_console.py` scans at most `max_pages` actual report pages (`page_limit` 1..100, `max_pages` 1..10) and lists entries having ANY requested exact known triage reason (unique nonempty tuple).

- One connected `build_recovery_report` call per page; each page is a separate read snapshot. No cross-page consistency, no aggregate accounting; nothing writes, dispatches or releases budget.
- Header lists per-page SOURCE report SHA-256 digests (not a text hash).
- `next_after_request_id` is the last scanned page cursor, never the last displayed request. `reached_end` covers only the last observed page.
- No match is not an empty receiver. UNKNOWN is not zero.
- Later page failure, non-advancing cursor or byte overflow fails the whole call; no partial view.

No authority. Tests in `tests/contracts/test_recovery_queue.py` are authored, NOT EXECUTED.

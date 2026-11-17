# 29 Local recovery console

[日本語](29-recovery-console.ja.md) | English

**Status: increment 29 (2026-11-17) authored, NOT EXECUTED.** Source and six new self-contained tests (K01–K06) are written; no check for this increment has run. Earlier validation banners cover earlier increments only. No runtime acceptance.

`render_recovery_console(receiver, *, after_request_id=None, limit=100, max_output_bytes=65536)` in `admission/recovery_console.py` turns ONE page of the [private recovery report](28-recovery-report.md) into an immutable `ConsoleView(text, report_sha256, entry_count, next_after_request_id)`.

## Trusted boundary

- In-process library call by an independently trusted caller with an already-constructed receiver. There is no CLI, receiver construction, file/network/process/tool use, clock, or new schema, default, guard, authentication, runtime or dispatch change.
- It calls `build_recovery_report` exactly once and parses its actual JSON. A forged but internally consistent history cannot be detected.

## Rendering

A `PRIVATE LOCAL RECOVERY CONSOLE - NOT AUTHORITY` header, then one line per reservation: request ID, receipt state/revision, full outstanding worker-seconds, latest usage, stop and cleanup facts, local ack state and reason codes.

- Usage is `UNKNOWN`, `ZERO` or `KNOWN:n`; stop/cleanup are `unknown`, `false` or `true` (`unknown` when no observation exists); ack is `unknown`, `pending` or `acknowledged`. UNKNOWN is never zero, and the console never infers release, settlement or live process truth.
- Output is deterministic printable ASCII plus line separators. Identifiers are JSON-escaped, including control characters, DEL and non-ASCII, so terminal controls cannot be injected.
- `report_sha256` is the digest of the SOURCE report bytes, not of the text.

## Privacy, limits, failure

The text is private operator output; do not publish it. Each page is an independent read snapshot, and cursors are exclusive positions, not leases. `max_output_bytes` must be an exact int in 1..1048576; an oversized view is refused whole (`RecoveryConsoleTooLarge`) with no partial text. Report errors propagate and return nothing.

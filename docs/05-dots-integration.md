# 05 DOTS Integration and Handoffs

[日本語](05-dots-integration.ja.md) | [Home](../README.md)

## Product facts and acceptance boundary

The official [Tasks and memory guide](https://learn.chatgpt.com/docs/dots/tasks-and-memory), checked 2026-11-09, describes DOTS assigning work to connected local computers or prepared Codex cloud environments. New tasks receive selected context rather than every previous conversation. Local work depends on the connected computer being available. This supports a delegation design, not an assertion that Moruku's research environment is already connected.

No undocumented DOTS REST endpoint, task identifier format or direct memory-write API is invented here. Configuration and actual supported task/connector tools must be checked in the target account. This project extends the user's explicitly chosen DOTS/Codex workflow, so it does not scaffold a replacement agent framework.

## Minimum viable assignment

A human asks DOTS to take responsibility for one bounded research question and points it at the current brief. DOTS prepares a task packet containing:

1. Project ID, task/request key, protocol revision, expected state revision, and expiry.
2. Objective and acceptance checks; inputs with immutable source/data hashes.
3. Current facts, previous candidate/result references and unresolved questions.
4. Code revision, allowed workspace, accepted execution profile and remaining budget.
5. Required outputs, evidence contract, stop conditions, and where to return results.

Use a short packet with pointers, not an entire chat transcript. Initial target: up to roughly 2,000 tokens of relevant context, measured and adjusted for the real client. Essential current instructions remain explicit; retrieved memory is supporting context.

The worker acknowledges assignment and reports an external run ID. Task/thread IDs are transport metadata, not substitutes for run records. A DOTS “done” response triggers artifact verification, not automatic scientific acceptance.

## Transport stages

| Stage | Mechanism | Acceptance |
|---|---|---|
| M0 | User-assisted task packet + existing Git/file tools | One bounded request yields identifiable artifacts and a checked result; no always-on service. |
| M1 | Existing supported DOTS-to-Codex assignment | Confirm the actual local/cloud environment, context received, status retrieval and interruption behavior. |
| M2 | Optional private collaboration adapter | Reuse current request/receipt semantics only after protocol and identity checks. No change to private mailbox behavior in this repository. |
| M3 | Optional MCP research tools and completion events | Expose only scoped run operations and metadata; accept authentication, subscription lifecycle and duplicate handling. |

A local file does not become a cloud-accessible endpoint by naming it in a prompt. A GitHub file update does not guarantee immediate DOTS wakeup.

The official [MCP Events guide](https://developers.openai.com/plugins/build/mcp-events) describes subscriptions and signed webhook delivery for supported clients, including dots. This is an optional later path: capabilities and account controls require validation. A future event should carry an opaque project/run ID, status revision and evidence locator, not secrets or instructions copied from output. Stable event IDs, bounded subscriptions, expiry, verification and deduplication are acceptance requirements. The existing finite Mattermost PoC is useful experience, not a ready research-event implementation.

## Roles without premature multiplication

Initially DOTS coordinates one Codex worker; review and planning are explicit sequential stages. Later request an independent reviewer only for a concrete uncertainty, with its own budget and evidence access. Avoid repeated model-to-model discussion without a new observation. A reviewer may disagree; disagreement is recorded and resolved through evidence or marked unresolved.

The user can steer DOTS during work. A new instruction updates the current brief/state revision and cancels or supersedes only affected jobs. Unrelated completed evidence remains valid with its original protocol.

## Failure and recovery

- No reply: mark pending/overdue; check actual task activity and connection before retrying.
- Computer unavailable: retain state and return a blocked reason; do not silently switch hosts or start cloud spending.
- Lost context: rebuild the packet from the latest registry revision and evidence, not remembered chat.
- Lease expiry: reconcile actual process/artifacts, then cancel or retry with a new attempt ID.
- Duplicate delivery: return the existing logical job status; a new replicate needs an explicit new replicate ID.
- DOTS pause/cancel: stop delegated work and runner jobs separately as applicable; verify actual cleanup. Pausing the coordinator alone is not assumed to stop every process.

Sleep integration may later supply reviewed general methods. It does not write DOTS internal memory or inject evaluation answers. No active message, schedule, plugin or subscription is created by this design.

## Concrete implementation contracts

[11 Ownership and handoffs](11-harness-boundaries.md) defines state authority, duplicate delivery, fencing, parent/child budgets and pinned schemas. [12 Evaluation and acceptance](12-protocol-and-acceptance.md) defines the frozen protocol, receipt binding and SCI-01–12. The old 1,800-second CPU sketch cannot reserve 72 attempts at up to 600 seconds each; reconcile the actual run manifest and total budget before launch. This update checks design/examples only, not runtime acceptance.

## Verification-aware task packets

Add the immutable verification-contract reference, the requested claim scope/assurance and eligible knowledge references to the existing packet. Candidate tasks receive only permitted specification/development views. A separate protected verification assignment resolves authoritative inputs itself; it never adopts an evaluator path from candidate output. Keep actual client/tool support explicit, with owner-operated verification where necessary.

The return packet distinguishes candidate submission, verification receipt, scientific interpretation and proposed knowledge promotion. DOTS may request a check or summarize a receipt, but a chat completion cannot issue one. The registry verifies issuer/bindings before reuse. [13](13-verified-discovery.md) defines the boundary; no new transport, credentials or scheduled discussion is required.

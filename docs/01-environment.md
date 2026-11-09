# 01 Environment and Scope

[日本語](01-environment.ja.md) | [Home](../README.md)

Design baseline: 2026-11-09 JST. Repository documentation is evidence of recorded observations, not a live hardware inventory. We performed read-only document review, not host access.

## Observed context versus proposal

| Area | Recorded context | Proposed role / remaining check |
|---|---|---|
| DOTS | The user explicitly chooses DOTS as the center. Existing public integration notes describe selected task context and external-state handoffs. | Research coordinator. Confirm repository access, task delegation, working computer/environment and result retrieval in one bounded acceptance run. |
| Windows workstation | Public lab design records a Windows workstation with 64 GB RAM and an RTX 3070 8 GB; actual performance/current availability was not measured here. | Candidate CPU workspace on a connected computer. GPU remains disabled until environment, available memory and isolation are accepted. |
| Intel NUC / Ubuntu | Existing Docker Compose automation and monitoring; read-only report MCP; independent security-analysis KVM guest. | Optional metadata/evidence service later, with separate identity, storage and resource caps. Do not alter production Compose or borrow the security VM. |
| Mac mini | November 6–9 records describe installed OpenClaw/Kurotchi, limited CLI/browser checks, and bounded GitHub/communication progress. | Optional separate worker after research-task acceptance. Full operations and isolation are not proven by limited checks. Do not assume a particular GPU or RAM capacity from a pre-purchase plan. |
| GitHub | Existing research notes, sleep design, and bounded collaboration patterns. | This public repository holds design and sanitized templates. Raw run state/results default to private local storage or a separately scoped private project. |
| Agent communication | A private asynchronous collaboration mechanism exists; individual adapters have different acceptance states. | Optional request/result transport. No private messages, addresses, credentials or mailbox internals are exported here. |
| Sleep / memory | External-memory-first design exists; integration remains proposed. | Optional reviewed general lessons only; not a dependency of the research loop. |

## Recommended initial placement

Use an already connected, accepted Codex execution environment, with one disposable research workspace and one active CPU job. The operator can select Windows or Mac after confirming the actual execution path; this design does not pretend that selection was already tested.

Keep data/state beside the worker initially. A local SQLite registry plus append-only records and content-addressed files is a candidate implementation. No database server, n8n workflow, always-on model service, new cloud account or GPU purchase is needed for the first version. A public repository is not the live job queue.

If local availability is intermittent, checkpoint and stop; do not silently migrate a task to another machine. A prepared Codex cloud environment is a later option with separate data and budget eligibility. NUC hosting is optional, not a prerequisite.

## Explicit non-goals of this delivery

This is a detailed design and handoff scaffold, not a deployed scientist, a GPU experiment, an automatic publication service, or model-weight training. There is no assumption of an undocumented DOTS API, unlimited subscription compute, equivalent rights in every client, or automatic access to every past conversation.

Within a future authorized project envelope, ordinary implementation and experiments may continue without asking before every step. New spending, data destinations, hardware changes and publication beyond that envelope remain separate decisions.

## Public evidence consulted

- [Home lab overview](https://github.com/moruku36/home-ai-engineering-lab/blob/main/README.md): NUC and Mac mini observations have different dates.
- [Kurotchi improvement record, 2026-11-09](https://github.com/moruku36/home-ai-engineering-lab/blob/main/docs/kurotchi-improvements-2026-11-09.ja.md): limited progress is not general acceptance.
- [Local GPU design](https://github.com/moruku36/home-ai-engineering-lab/blob/main/docs/local-gpu-security-analysis-design.md): historical workstation facts; this project does not activate its inference plan.
- [Sleep project DOTS design](https://github.com/moruku36/agent-sleep-lab/blob/main/docs/dots-integration.ja.md): prior external-state design, not product authority.
- [Mattermost DOTS PoC](https://github.com/moruku36/mattermost-dots-poc): one finite event trial is not continuous integration.

OpenAI product capabilities are sourced separately in [05](05-dots-integration.md). Actual connection names, tokens, host addresses and private paths are intentionally absent.

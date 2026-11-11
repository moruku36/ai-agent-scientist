# 02 Research Foundations

[日本語](02-research-foundations.ja.md) | [Home](../README.md)

The first six studies were saved in the research-notes repository and consulted on 2026-11-09. The seventh primary source, arXiv:2611.09822v2, was inspected for the 2026-11-11 revision; no pre-existing saved note is claimed for it. No experiment was reproduced here. Borrowing an idea does not make an upstream implementation a dependency.

| Source | Relevant evidence | Our extraction | Limit |
|---|---|---|---|
| [The AI Scientist](https://arxiv.org/html/2408.06292v3), [Sakana article](https://sakana.ai/ai-scientist/) | An ML-template-based pipeline connects ideation, implementation, experiments, writing and automated review. | Stage-specific artifacts and checks connecting claims to measured results. | Human-provided templates/fields; errors remain. Automated review is not independent scientific acceptance. Do not assume v2 outcomes for this 2024 system. |
| [How Much of a Harness Does a Strong Agent Need for Autonomous ML Engineering?](https://arxiv.org/html/2609.40303v1) | Compares a minimal long-session coding agent with more elaborate configurations under controlled ML-task conditions. | One capable worker and good execution/evidence tools as baseline. | Task/model/compute-specific; no significant advantage is not a proof of universal equivalence, nor a reason to remove controls. |
| [Can AI agents conduct open-ended AI research?](https://arxiv.org/html/2607.27191v2) | Two shadow-evaluation cases separate engineering completion from research progress. | Milestone reviews, explicit alternative hypotheses and stop/backtrack criteria. | Small case set; neither a universal incapability claim nor proof that extra reviewers solve the problem. |
| [Evolving Agent Teams](https://arxiv.org/html/2610.36848v1) | Restructures roles after stagnation in optimization tasks, using retained artifacts/history. | Diagnose whether a bottleneck needs implementation, measurement or criticism; add a role selectively. | GPU tasks and limited trials; unresolved baseline/model descriptions in the source constrain causal interpretation. |
| [Darwin Gödel Machine](https://arxiv.org/html/2505.22954v3), [Sakana article](https://sakana.ai/dgm/) | Searches changes to agent code while retaining a candidate archive; base-model weights remain fixed. | Candidate lineage, reproducible comparisons and protected evaluators. | Benchmark optimization is not unlimited self-improvement; score manipulation must be checked. No self-modifying production controller. |
| [AB-MCTS](https://arxiv.org/html/2503.04412v5), [Sakana article](https://sakana.ai/ab-mcts/) | Allocates search between new candidates and refinements with external feedback. | Optional budgeted branching and distinct candidate-discovery versus final-selection metrics. | Requires informative evaluation. Noisy scientific judgments are not automatically calibrated tree rewards; more generations have costs. |
| [Discovering formally verified quantum programs with AI](https://arxiv.org/abs/2611.09822v2) | [Source locations and interpretation](13-verified-discovery.md). | Bind candidate checks to complete frozen specifications; separate checked knowledge from discussion. | Domain-specific proof results do not establish general scientific validity or gains for this harness. |

## Saved notes

All links below point to existing Japanese notes in `moruku36/independent-tech-research-notes`:

- [AI Scientist](https://github.com/moruku36/independent-tech-research-notes/blob/main/surveys/coding-agents/2024-sakana-ai-scientist.ja.md)
- [Minimal ML harness](https://github.com/moruku36/independent-tech-research-notes/blob/main/surveys/coding-agents/2026-ml-engineering-minimal-harness.ja.md)
- [Open-ended research evaluation](https://github.com/moruku36/independent-tech-research-notes/blob/main/surveys/agent-safety/2026-open-ended-ai-research-shadow-evaluation.ja.md)
- [Evolving Agent Teams](https://github.com/moruku36/independent-tech-research-notes/blob/main/surveys/coding-agents/2026-evolving-agent-teams.ja.md)
- [DGM](https://github.com/moruku36/independent-tech-research-notes/blob/main/surveys/coding-agents/2025-sakana-darwin-godel-machine.ja.md)
- [AB-MCTS](https://github.com/moruku36/independent-tech-research-notes/blob/main/surveys/llm-infrastructure/2025-sakana-adaptive-branching-mcts.ja.md)

## Synthesis and adoption policy

Start with the pipeline and external evidence, not with seven simultaneous frameworks. Initial custom code is restricted to records, validation, bounded execution and deterministic evaluation. Existing DOTS/Codex remains the agent runtime. No upstream scientist/search framework is installed by this design.

Compare each additional layer against the same model, tasks, resources and stopping rule. Use an archive and tree search only when a cheap, repeatable development metric exists. Scientific importance and novelty remain explicitly reviewed judgments. Negative results, failed replications and rejected hypotheses are first-class outputs.

Pin a source revision, dependencies, license and compatibility before adopting code. Names and results in the papers identify their experimental context, not currently recommended model versions or hardware purchases.

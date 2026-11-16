# 16 Kaggle Knowledge and OSS Candidates

[日本語](16-kaggle-knowledge-oss.ja.md) | [Home](../README.md)

**Status: proposed design, 2026-11-16.** This collects the knowledge behind the competition profiles in [15](15-kaggle-competitions.md) and the OSS that may be used. The OSS tables are **candidate lists: nothing is installed, pinned, license-reviewed or tested.** Competition facts rest on the source coverage in 15. Other statements about methods are general knowledge and were not re-checked against primary sources in this change. Their effect is a hypothesis until measured in each competition's local evaluation.

## Common knowledge

### Evaluation design

- **Making local evaluation trustworthy is the first job.** Split in a way that imitates how the test was built (unseen prompts, private repositories, hidden tasks). A loose split gives high local numbers that collapse on the leaderboard.
- **The public LB is a small sample.** Estimate the standard error from the public portion's size and do not treat smaller differences as improvement. Fitting to the public LB can reorder ranks sharply on the private LB.
- **Check local-to-LB correlation.** With a few submissions, confirm both move in the same direction. If not, suspect the split or a preprocessing difference and find the cause before submitting more.
- **Seeds and replicates.** Fix and record seed, folds and training order, and compare seed-to-seed variation with the difference between candidates.
- **Ensembling.** Stored out-of-fold predictions allow comparing weights and stacking without submitting. Averaging diverse models is more stable than a single one but consumes the inference-time envelope.

### Code competitions and submission

- **No-internet rerun.** On submission the notebook reruns from scratch on hidden data. Model weights, wheels and auxiliary data are attached beforehand as Kaggle Datasets/Models and installed with `pip install --no-index --find-links`.
- **Time estimate.** Estimate inference time at the hidden test size and leave headroom. The interactive test has only a few rows, so time a full-size imitation separately.
- **Format pre-check.** Check column names, IDs, nulls, label set, file name and file format mechanically before submitting. A scoring error can consume submission quota.
- **Final selection.** Many competitions ask you to choose the submissions used for final scoring before the deadline. Check the count and default behaviour in each Rules page.
- **Reproducibility material.** Winners are normally asked for code, training procedure and external-data provenance. The registry and evidence records serve directly.

### Common OSS candidates

| OSS | Use | Caution |
|---|---|---|
| [Kaggle API](https://github.com/Kaggle/kaggle-cli), [kagglehub](https://github.com/Kaggle/kagglehub) | Data download, Dataset/Notebook updates, submission, LB retrieval | Credentials stay outside the workspace. Submission commands pass through authorization and the submission ledger |
| [Kaggle docker-python](https://github.com/Kaggle/docker-python) | Reproducing the notebook environment | Large image; versions change during a competition |
| [uv](https://github.com/astral-sh/uv), Docker | Pinned dependencies and isolated runs; assumed by the PLE kit and the Gemma sandbox | Keep separate from Docker used by existing services |
| [scikit-learn](https://github.com/scikit-learn/scikit-learn), [pandas](https://github.com/pandas-dev/pandas), [Apache Arrow](https://github.com/apache/arrow) | Splits, metrics, parquet I/O | Match versions in the Kaggle image |
| [Optuna](https://github.com/optuna/optuna) | Hyperparameter search | Search inside folds only; count trials against budget |
| [Matplotlib](https://github.com/matplotlib/matplotlib) | Writeup figures | Record source runs and plotting revision in the figure manifest |

No dedicated experiment-tracking service, vector database or distributed queue is added. Records use the existing registry design.

## Gemma 4 Developer Agent

### Knowledge

- **SWE-bench-style scoring.** The agent sees only the issue text, edits the repository, and passes when hidden tests (Fail-to-Pass) pass and existing tests (Pass-to-Pass) stay green. There is no partial credit.
- **Main failure types.** (1) wrong localization, (2) edit-tool failure (such as an `old_string` mismatch), (3) fixing without reproducing and missing the point, (4) breaking existing tests, (5) repeating the same action, (6) timing out with no patch submitted, (7) malformed tool calls. Count trajectories by type and address the most frequent first.
- **Structure that tends to help small models.** A fixed procedure (read the issue → locate related code → reproduction test → fix → run tests → `submit_patch`), truncated tool output, summarized long history, re-reading target lines before editing, and submitting a provisional patch early.
- **Provided graph tools.** `get_code_neighbors`, `search_similar_code` and `get_code_subgraph` support localization through call relations and embeddings. Whether they beat grep-centred exploration in pass rate and time is an ablation target.
- **Where Skills fit.** ADK Skill scripts run in the sandbox and their run time is debited from the budget. Put deterministic work (extracting failing tests, listing candidate files from a stack trace, checking the diff) into scripts to reduce model turns.
- **LoRA training.** The usual recipe collects successful fix trajectories for supervised fine-tuning and optionally extends with reinforcement learning. Training data concentrated on the same four repositories as the 129 public tasks may not transfer to private repositories. Check the Rules on whether trajectories generated by other models may be used for training.
- **Inference settings.** Match temperature, maximum tokens, context length and tool-call format to what the base model expects. Confirm behaviour on the quantized base by local reproduction.
- **Time allocation.** Set per-task limits from the mean (12 hours over the task count) and from the distribution in which hard tasks absorb time.

### OSS candidates

| OSS | Use | Caution |
|---|---|---|
| [Google ADK (adk-python)](https://github.com/google/adk-python) | Agent Config (YAML), Skill and sub-agent specification; submissions compile into ADK agents | The competition adds restrictions. `HARNESS_README.md` is authoritative |
| Bundled `swegemma`, `adk-submission`, `adk-eval-core` | Local evaluation CLI and the two-container sandbox | Not read; check after obtaining the data |
| [PEFT](https://github.com/huggingface/peft), [Transformers](https://github.com/huggingface/transformers), [TRL](https://github.com/huggingface/trl) | LoRA training; `adapter_config.json` and `adapter_model.safetensors` output | Submission format is a safetensors PEFT LoRA |
| [Unsloth](https://github.com/unslothai/unsloth) | LoRA training with less GPU memory | Gemma 4 support and output compatibility unverified |
| [vLLM](https://github.com/vllm-project/vllm), [llama.cpp](https://github.com/ggml-org/llama.cpp) | Local Gemma inference, serving with LoRA | Quantization and chat template may differ from the scoring environment |
| [SWE-bench](https://github.com/SWE-bench/SWE-bench) | Reference for the evaluation method; additional validation tasks | Public tasks may be in the model's training data. Check license and terms |
| [SWE-agent](https://github.com/SWE-agent/SWE-agent), [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent), [OpenHands](https://github.com/OpenHands/OpenHands) | Reference for prompts, procedure and tool design | Submissions may use only competition tools and sub-agents; use as ideas only |
| [SWE-smith](https://github.com/SWE-bench/SWE-smith), [SWE-Gym](https://github.com/SWE-Gym/SWE-Gym), [R2E-Gym](https://github.com/R2E-Gym/R2E-Gym) | Generating training tasks and trajectories; environments | Check the generating model's terms and the Rules. Heavy on GPU and time |
| [NetworkX](https://github.com/networkx/networkx), [NumPy](https://github.com/numpy/numpy) | Analysing the bundled code graphs (JSON) and embeddings (npz) | Packages usable inside Skill scripts depend on the sandbox |
| [pytest](https://github.com/pytest-dev/pytest) | Reproduction tests and verification | The sandbox is Python 3.13, with shims for older test suites |

## Name That LLM

### Knowledge

- **Nature of the task.** Not human-versus-AI detection but authorship attribution across 18 models. Topic and length are designed not to help, so capture vocabulary, phrasing, punctuation and formatting habits.
- **Group split.** Use GroupKFold on `prompt_id`. Training and validating across the same prompts scores by memorizing topics and drops on unseen test prompts.
- **Strong baseline.** Character and word n-gram TF-IDF with a linear classifier (logistic regression, linear SVM). With only 2,699 passages, high-dimensional sparse features and strong regularization fit well.
- **Stylometric features.** Frequencies of punctuation and Unicode characters (dashes, quotation marks, ellipses), sentence length and paragraph structure, function-word ratios, leftover Markdown, and stock openings and closings. Model families tend to show habits here.
- **Language-model features.** Statistics of token probabilities or perplexity under open small LMs, and sentence embeddings. This family was effective in past AI-text-detection competitions but costs inference time.
- **Fine-tuning.** Fine-tuned encoders (DeBERTa or ModernBERT families), or a small LLM with a classification head and LoRA. With little data, fold-to-fold variation is large and seed averaging is needed.
- **Hierarchy.** Decide from the confusion matrix whether to classify provider (six labs) then model, or add specialist classifiers for confusions within one lab.
- **Optimizing balanced accuracy.** Class weights in training and per-class scaling fitted on out-of-fold predictions are candidates. Test class ratios are unequal and differ between public and private, so do not fit priors to the test distribution.
- **Test-time adaptation.** Refitting the TF-IDF vocabulary on test text or pseudo-labelling inside the notebook was used in past code competitions. Confirm that the rules permit it and consider harm from skewed class ratios before making it a comparison arm.
- **Robustness to length.** Length varies randomly from 40 to 250 words, so check short-text performance with truncation augmentation.
- **Label inspection.** Only "light formatting cleanup" is said to be applied. Check for duplicate and extremely short passages.

### OSS candidates

| OSS | Use | Caution |
|---|---|---|
| [scikit-learn](https://github.com/scikit-learn/scikit-learn) | `TfidfVectorizer`, linear classifiers, `StratifiedGroupKFold`, `balanced_accuracy_score` | Enough for the first baseline |
| [LightGBM](https://github.com/lightgbm-org/LightGBM), [XGBoost](https://github.com/dmlc/xgboost) | Stacking stylometric features and out-of-fold predictions | Overfits easily on small data |
| [Transformers](https://github.com/huggingface/transformers), [Sentence Transformers](https://github.com/huggingface/sentence-transformers) | Encoder fine-tuning, sentence embeddings | Attach weights as Kaggle Datasets/Models; check licenses |
| [PEFT](https://github.com/huggingface/peft) | LoRA for small LLM classifiers | GPU envelope and inference within 9 hours |
| [RAPIDS cuML](https://github.com/NVIDIA/cuml) | GPU TF-IDF and linear models | Unnecessary if CPU is fast enough at this size |
| [cleanlab](https://github.com/cleanlab/cleanlab) | Label and outlier inspection | Output is a starting point for review, not automatic removal |
| [Optuna](https://github.com/optuna/optuna) | Regularization, n-gram ranges, ensemble weights | Tune only inside group-split folds |

## PLE Agent Harness

### Knowledge

- **Two kinds of grading.** Verification scripts check quantitative calculations, CAD/IFC geometry and constraints; an LLM judge grades open-ended deliverables from 0.0 to 1.0. Deliver not only the result but also the governing clause, assumptions, units and conclusion.
- **Failures named by the host.** Misread drawing callouts, the wrong code clause, dropped unit conversions and stopping early. Add a self-check before finishing that confirms unit consistency, referenced clause and edition, presence of every deliverable and coverage of every requirement.
- **Context management for long tasks.** Dozens of files are read, so begin with a file inventory and requirement list, externalize working notes to files and keep key points with their sources. This is the same idea as this design's "keep facts outside the conversation".
- **Choosing tools.** Both the task container's local MCP servers (documents, spreadsheets, email, CAD) and the shell are available. Do not let the language model do arithmetic in its head; compute in scripts and keep result files.
- **Drawings and documents.** Text extraction alone loses the spatial relation of dimensions and callouts in PDF drawings. Cross-check a path where the model reads page images against vector/text extraction.
- **IFC and clashes.** For IFC4 deliverables, mechanically check schema validity, element counts, spatial structure and clashes before finishing.
- **Cost versus performance.** Prizes require being on the Pareto frontier, so a configuration that reaches the frontier with a cheaper model is in scope alongside scoring high with an expensive one. A score-versus-cost curve over verification retries, context length and parallelism is also a required Writeup figure.
- **Mean of three runs.** Stability scores, not a single success. First harden against HTTP 400s, unrecovered crashes and timeouts.
- **Environment limits.** Install within 30 minutes on `debian:bookworm`; `/opt/harness` at most 2 GiB compressed and read-only; 1 GB writable `/tmp` and `$HOME`; 2 CPUs and 4 GB RAM. Heavy dependencies and local models do not fit.
- **Codes and copyright.** Design-code texts are copyrighted. Web search is unavailable in Stage 2, so required clauses are read from the task folder. Do not bundle code texts in the submission repository.
- **Cross-model comparison.** Try the same change on models from two or more families and separate changes that help every model from those that help one. This maps directly to 15 rubric points.

### OSS candidates

| OSS | Use | Caution |
|---|---|---|
| [google-research/ple](https://github.com/google-research/ple) | Kit (`kit check`, `kit artifacts`), `eval/run.py`, eight sample_submissions, protocol documents | Apache-2.0. Start from submission-template or a sample |
| Harbor (the kit pins `harbor==0.20.0`) | Running the dev tasks | Follow the kit's pinned version |
| [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk), [websockets](https://github.com/python-websockets/websockets) | Calling task MCP servers; WebSocket to the evaluator | `docs/protocol.md` is authoritative |
| [IfcOpenShell](https://github.com/IfcOpenShell/IfcOpenShell) | Reading, writing and validating IFC4; clash checking | LGPL family. Check size and install time on bookworm |
| [ezdxf](https://github.com/mozman/ezdxf) | Reading and writing DXF drawings | Does not handle DWG directly |
| [pypdf](https://github.com/py-pdf/pypdf), [pdfplumber](https://github.com/jsvine/pdfplumber), [PyMuPDF](https://github.com/pymupdf/PyMuPDF) | PDF text and table extraction, page rendering | PyMuPDF is AGPL family; check consistency with the Apache-2.0/MIT submission requirement |
| openpyxl, LibreOffice (headless) | Spreadsheet I/O, formula recalculation | LibreOffice is large. First check whether the task MCP servers suffice |
| [Pint](https://github.com/hgrecco/pint) | Unit-aware calculation, catching conversion errors | Handle mixed US customary and SI units |
| [NumPy](https://github.com/numpy/numpy), [SciPy](https://github.com/scipy/scipy), [SymPy](https://github.com/sympy/sympy), [pandas](https://github.com/pandas-dev/pandas) | Numerics, checking formulas, tables | Within 4 GB RAM |
| [Shapely](https://github.com/shapely/shapely), [trimesh](https://github.com/mikedh/trimesh) | Planar and solid geometry, auxiliary clash checks | State precision and tolerance |
| [PyNite](https://github.com/JWock82/Pynite), [anaStruct](https://github.com/anastruct/anaStruct) | Frame structural analysis | Code checks themselves need separate implementation |
| [pandapower](https://github.com/e2nIEE/pandapower) | Power-flow and short-circuit calculation | Building electrical load and cable sizing is often spreadsheet work |
| [CoolProp](https://github.com/CoolProp/CoolProp), [fluids](https://github.com/CalebBell/fluids), [ht](https://github.com/CalebBell/ht) | Thermophysical properties, pipe pressure drop, heat transfer | For cooling-tower and chilled-water studies |
| [WNTR](https://github.com/USEPA/WNTR) | Water-network hydraulics | For civil drainage and supply studies |
| [Matplotlib](https://github.com/matplotlib/matplotlib) | Figures in deliverables and the Writeup | — |

The sample_submissions also include adapters for existing agents (Hermes Agent, Pi, Antigravity CLI). Whether to build on a small custom harness or an existing agent is decided by comparing dev score, cost and robustness.

## OSS adoption rules

1. On adoption, record version, origin, hash and license in `sources/index.json` and the OfflineBundle.
2. When bundling into a submission, check dependency licenses against the competition's requirement (Apache-2.0/MIT for PLE; freely and publicly available for Name That LLM).
3. Measure that it fits the runtime's size, time and memory limits.
4. Add one at a time and compare before and after on the same split and budget. Remove dependencies that show no effect.
5. URLs in the tables above were checked for a response only, on 2026-11-16. Versions, APIs, licenses and behaviour in each competition environment are unverified.

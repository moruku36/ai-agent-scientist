# Existing-experiment intake

Japanese: [39-intake-summary.ja.md](39-intake-summary.ja.md). Builds on [38 existing-run import](38-existing-run-import.md), which defines identity and the import contracts and is unchanged.

## Status

The standard-library offline helper `ai_agent_scientist.evidence.intake` includes a CLI and explicit stage outcomes. Run the synthetic contract suite, including the CLI cases, with `PYTHONPATH=src python3 -B -m unittest discover -s tests/contracts`. Run the offline design checks with `python scripts/check_design.py` and a JSON Schema 2020-12 validator. Real-model, GPU, research, Windows/WSL and official-score acceptance are outside the scope of these local checks.

## API

`intake_paths(store, manifest_path, candidate_path, config_path, log_paths, stages_path=None)` returns `IntakeResult(imported, stages_sha256, summary)`. `log_paths` maps log ids to explicit paths; only these are opened (no discovery, glob or manifest-supplied paths). Without `stages_path` every stage is UNKNOWN.

1. Files are opened nonblocking/no-follow, checked as regular by descriptor, bounded by the store cap and 16 MiB total. A final-component symlink, directory, FIFO, oversize file or missing `O_NOFOLLOW`/`O_NONBLOCK` is refused with a fixed payload-free reason. Parent directories are trusted (single local owner); this is not an isolated runner.
2. Only input-validation refusals (files, profile, stages, mapping) happen before any write.
3. Candidate, config, logs, manifest bytes and stages bytes are stored unchanged, then each blob is read back and compared. I/O, digest or readback failures can occur after writes and may leave a subset of immutable blobs: reconcile, do not retry blindly.

The store must be an existing, private, owner-controlled, non-symlink directory on trusted ancestors with one writer, separate from the run inputs. It persists the imported evidence; this API deletes nothing and does not enforce global `run_id` uniqueness, so use a new `run_id` whenever the config or attempt changes.

## CLI

From the repository root, run the module with explicit paths to the existing store and input files.

```sh
PYTHONPATH=src python -m ai_agent_scientist.evidence.intake \
  --store /path/to/run/blobs --manifest /path/to/run/in/manifest.json \
  --candidate /path/to/run/in/candidate.py --config /path/to/run/in/config.json \
  --log train /path/to/run/in/train.log --stages /path/to/run/in/stages.json
```

Repeat `--log ID PATH` once per manifest log and omit it for a manifest with no logs. `--stages` is optional. The CLI calls `intake_paths` with a 16 MiB store cap and writes one summary JSON object to stdout on success. Invalid evidence or storage failure exits 1. Invalid arguments exit 2. Both write a fixed diagnostic to stderr and leave stdout empty. The CLI uses the same explicit-path and write behavior as the API.

## Manifest profile

A normal `existing-run-import/1` manifest with exactly these artifacts: `candidate` (kind `candidate`), `config` (kind `config`) and your log ids (kind `log`); other ids or kinds are refused. `candidate` and `config` must declare the target identity, so a foreign config is never bound to the target. The candidate hash must match its bytes. Logs may declare another run's identity and stay history. The config identity is its declared label, never derived from the candidate hash.

## Stages file

Separate closed contract `intake-stages/1`; manifest and run-record wire are unchanged. Stages: `gpu_environment`, `model_launches`, `tests_collected`, `test_bodies_executed`, `patch_recovery`, `test_pass`, each at most once; entry keys `stage`, `result`, `count`, `stop_reason`, `log_ids`. `target` equals the manifest target. Results per stage: `started`/`collected`/`executed`/`recovered`/`passed`, `failed`, `not_started`, `unknown`. `count` is null or an int 0..10^9, only for launches and tests (explicit 0 differs from null; `unknown` has none). `stop_reason`: `none`, `not_started`, `interrupted`, `unavailable`, `unknown`. `log_ids`: at most 8 imported logs declaring the target.

A missing stage and an explicit `unknown` both show `UNKNOWN` with count null. A missing stage reports stop reason `unknown` and no logs; an explicit `unknown` keeps its stated stop reason and log digests. Nothing is inferred across stages (GPU started is not launches; collected is not executed; recovered is not passed). Logs are not parsed; labels are caller assertions.

### Explicit stage outcomes in v2

Set `version` to `intake-stages/2` to include `startup`, `inference`, `tool_handling` or `output_verification` in the `stages` list. V2 uses the same top-level keys, target identity check and six historical stage contracts. Each new stage may appear once with `stage`, `result` and `log_ids`. Use `success`, `failure`, `not_run` or `unknown` for `result`. Use up to eight distinct target log IDs for `log_ids`, or `[]` when none are available.

Each new stage accepts an optional `declared_evidence_sha256` for external evidence. Supply a string of 64 lowercase hexadecimal characters, use null or omit the field. Intake validates the digest syntax and retains the caller's declaration without fetching, storing or hashing the external evidence bytes. A malformed digest is rejected before any writes.

An `output_verification` entry also accepts an optional `verdict`. For a caller-declared `success` or `failure`, the comparison verdict can be `exact_match`, `formatting_mismatch` or `numeric_mismatch`. Omit `verdict` or use null when no comparison verdict is available. A terminal-newline difference with the same numeric value can be declared `formatting_mismatch`. The caller supplies the outcome according to its verification policy. Intake validates the labels and accepts no raw actual or expected output fields.

In this v2 sidecar, the caller declares the SHA-256 of the two ASCII bytes `42` after comparing them with `42` followed by a newline. The target and log come from the [synthetic example](#synthetic-example).

```json
{
  "version": "intake-stages/2",
  "target": {
    "run_id": "example.org/demo-1",
    "notebook_version": "owner/slug/1",
    "candidate_sha256": "cc42155088fca5730758db72b2a5bca33112a941dfaa2d43098ec422ce4ea213"
  },
  "stages": [
    {"stage": "gpu_environment", "result": "started", "count": null, "stop_reason": "none", "log_ids": ["train"]},
    {"stage": "startup", "result": "success", "log_ids": ["train"]},
    {
      "stage": "output_verification",
      "result": "failure",
      "verdict": "formatting_mismatch",
      "declared_evidence_sha256": "73475cb40a568e8da8a045ced110137e159f890ac4da883b6b17dc651b3a8049",
      "log_ids": []
    }
  ]
}
```

## Summary

JSON-compatible: target identity, candidate and config digests with declared identity, manifest and stages digests, artifact kinds/digests/sizes/Git comparison, three result categories (CPU simulation, real model, official), six stages and `verified_readback`. A category without evidence for the target shows `UNKNOWN`, not `not_run`. An official score appears only when exactly one official observation declares the target identity and is `scored`, with artifact digest and source identity; other candidates' or runs' scores stay in `imported.observations`. No log content, local paths, environment labels or input error text.

The `format` value stays `intake-summary/1`, and the original fields retain their shape. Each of the four `stage_results` entries has `result`, `verdict`, `declared_evidence_sha256` and `logs` (SHA-256 digests of supplied target logs). The declared digest is null when omitted or explicitly null. With no sidecar, a v1 sidecar or an omitted v2 entry, the stage shows `UNKNOWN`, null for both the verdict and the declared digest, and an empty log list. An explicit `unknown` retains any declared digest and supplied log digests. Explicit `not_run` stays `not_run`. Each stage is reported independently.

`stages_sha256` identifies the exact validated sidecar bytes. `verified_readback` covers the bytes intake stored. The stage result, verdict and external evidence digest are unverified caller declarations. The v2 sidecar above produces this `stage_results` object.

```json
{
  "startup": {
    "result": "success",
    "verdict": null,
    "declared_evidence_sha256": null,
    "logs": ["b7126ac71c7f87a2146297b1bd0f53a934b2a189fd3d2995e1ff1358715560c4"]
  },
  "inference": {"result": "UNKNOWN", "verdict": null, "declared_evidence_sha256": null, "logs": []},
  "tool_handling": {"result": "UNKNOWN", "verdict": null, "declared_evidence_sha256": null, "logs": []},
  "output_verification": {
    "result": "failure",
    "verdict": "formatting_mismatch",
    "declared_evidence_sha256": "73475cb40a568e8da8a045ced110137e159f890ac4da883b6b17dc651b3a8049",
    "logs": []
  }
}
```

## Synthetic example

Creates a NEW synthetic directory (not real evidence), prepares the inputs and manifest, imports and prints the summary. The store persists for readback; nothing is overwritten or deleted. No model or candidate is executed.

```python
import hashlib, json, tempfile
from pathlib import Path
from ai_agent_scientist.evidence.blob_store import BlobStore
from ai_agent_scientist.evidence.intake import intake_paths

d = Path(tempfile.mkdtemp())
inp, blobs = d / 'in', d / 'blobs'
inp.mkdir(); blobs.mkdir()
cand = b'print(1)\n'
files = {'candidate.py': cand, 'config.json': b'{"seed": 1}\n', 'train.log': b'step 1\n'}
for name, data in files.items():
    (inp / name).write_bytes(data)  # exact bytes, terminal newline kept
t = {'run_id': 'example.org/demo-1', 'notebook_version': 'owner/slug/1',
     'candidate_sha256': hashlib.sha256(cand).hexdigest()}
art = lambda i, k: {'id': i, 'kind': k, 'source': t, 'expected_git_blob_sha1': None}
manifest = {'version': 'existing-run-import/1', 'target': t,
            'artifacts': [art('candidate', 'candidate'), art('config', 'config'), art('train', 'log')],
            'observations': [], 'timings': [],
            'environment': {'os': None, 'python': None, 'accelerator': None, 'source_artifact_id': None}}
stages = {'version': 'intake-stages/1', 'target': t, 'stages': [
    {'stage': 'gpu_environment', 'result': 'started', 'count': None, 'stop_reason': 'none', 'log_ids': ['train']}]}
(inp / 'manifest.json').write_bytes(json.dumps(manifest).encode() + b'\n')
(inp / 'stages.json').write_bytes(json.dumps(stages).encode())
store = BlobStore(blobs, max_blob_bytes=1 << 20)
r = intake_paths(store, inp / 'manifest.json', inp / 'candidate.py', inp / 'config.json',
                 {'train': inp / 'train.log'}, stages_path=inp / 'stages.json')
print(d)
print(json.dumps(r.summary, indent=2))
```

`candidate`, `config` and `train` share one target identity whose `candidate_sha256` matches `candidate.py`; the stages file repeats the same target. Use a new `run_id` for a new config or attempt.

## Not claimed

CPU simulation, real model and official results stay separate. No GPU, real-model, research or official-score success and no native Windows support: `BlobStore` needs POSIX primitives, so use WSL2 on a Linux filesystem as in [38](38-existing-run-import.md).

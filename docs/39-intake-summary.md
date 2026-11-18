# Existing-experiment intake

Japanese: [39-intake-summary.ja.md](39-intake-summary.ja.md). Builds on [38 existing-run import](38-existing-run-import.md), which defines identity and the import contracts and is unchanged.

## Status

Offline helper `ai_agent_scientist.evidence.intake` (standard library only). Source, eight synthetic unittest methods and these docs are authored; checks and review are pending. No real model, GPU, research, Windows/WSL or official-score claim; no real data used.

## API

`intake_paths(store, manifest_path, candidate_path, config_path, log_paths, stages_path=None)` returns `IntakeResult(imported, stages_sha256, summary)`. `log_paths` maps log ids to explicit paths; only these are opened (no discovery, glob or manifest-supplied paths). Without `stages_path` every stage is UNKNOWN.

1. Files are opened nonblocking/no-follow, checked as regular by descriptor, bounded by the store cap and 16 MiB total. A final-component symlink, directory, FIFO, oversize file or missing `O_NOFOLLOW`/`O_NONBLOCK` is refused with a fixed payload-free reason. Parent directories are trusted (single local owner); this is not an isolated runner.
2. Only input-validation refusals (files, profile, stages, mapping) happen before any write.
3. Candidate, config, logs, manifest bytes and stages bytes are stored unchanged, then each blob is read back and compared. I/O, digest or readback failures can occur after writes and may leave a subset of immutable blobs: reconcile, do not retry blindly.

The store must be an existing, private, owner-controlled, non-symlink directory on trusted ancestors with one writer, separate from the run inputs. It persists the imported evidence; this API deletes nothing and does not enforce global `run_id` uniqueness, so use a new `run_id` whenever the config or attempt changes.

## Manifest profile

A normal `existing-run-import/1` manifest with exactly these artifacts: `candidate` (kind `candidate`), `config` (kind `config`) and your log ids (kind `log`); other ids or kinds are refused. `candidate` and `config` must declare the target identity, so a foreign config is never bound to the target. The candidate hash must match its bytes. Logs may declare another run's identity and stay history. The config identity is its declared label, never derived from the candidate hash.

## Stages file

Separate closed contract `intake-stages/1`; manifest and run-record wire are unchanged. Stages: `gpu_environment`, `model_launches`, `tests_collected`, `test_bodies_executed`, `patch_recovery`, `test_pass`, each at most once; entry keys `stage`, `result`, `count`, `stop_reason`, `log_ids`. `target` equals the manifest target. Results per stage: `started`/`collected`/`executed`/`recovered`/`passed`, `failed`, `not_started`, `unknown`. `count` is null or an int 0..10^9, only for launches and tests (explicit 0 differs from null; `unknown` has none). `stop_reason`: `none`, `not_started`, `interrupted`, `unavailable`, `unknown`. `log_ids`: at most 8 imported logs declaring the target.

A missing stage and an explicit `unknown` both show `UNKNOWN` with count null. A missing stage reports stop reason `unknown` and no logs; an explicit `unknown` keeps its stated stop reason and log digests. Nothing is inferred across stages (GPU started is not launches; collected is not executed; recovered is not passed). Logs are not parsed; labels are caller assertions.

## Summary

JSON-compatible: target identity, candidate and config digests with declared identity, manifest and stages digests, artifact kinds/digests/sizes/Git comparison, three result categories (CPU simulation, real model, official), six stages and `verified_readback`. A category without evidence for the target shows `UNKNOWN`, not `not_run`. An official score appears only when exactly one official observation declares the target identity and is `scored`, with artifact digest and source identity; other candidates' or runs' scores stay in `imported.observations`. No log content, local paths, environment labels or input error text.

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

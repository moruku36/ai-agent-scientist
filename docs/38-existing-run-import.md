# Existing-run evidence import

Japanese: [38-existing-run-import.ja.md](38-existing-run-import.ja.md)

Standard-library, offline helper `ai_agent_scientist.evidence.existing_run`. It imports evidence of a run that already happened (candidate, config, logs, evidence, environment note) from bytes the caller already holds, into a `BlobStore`.

## Status

Local helper contract (`existing-run-import/1`); the run-record schema is not extended. The implementation has been independently source-reviewed. Targeted synthetic offline verification passed: 22 new unittest methods plus 24 existing regression methods; the English and Japanese synthetic examples each passed once. There is no real model, research, Windows or WSL acceptance, and nothing here has been run on real private data.

## What it does and does not do

- Takes manifest bytes plus a dict `artifact id -> bytes`. It never resolves paths or URLs, never imports or executes supplied code, never normalizes bytes (BOM, CRLF and multibyte text are stored exactly) and never parses logs.
- Compares each artifact with its optional `expected_git_blob_sha1`. Per artifact: `match`, `mismatch` or `unavailable`. A mismatch is reported, never repaired.
- Git blob id = SHA-1 of the header `blob <byte length>` + NUL byte (`\0`) + the exact bytes (`git_blob_sha1`). A separate SHA-256 of the same bytes is the storage key. A trailing newline changes both.
- The expected id must be supplied independently by the caller (for example from a trusted record). A URL or commit attribution is a label, not authentication, and a matching id proves byte equality only, not origin.
- Identities, observations, timings and environment values are caller-asserted labels, not authentication.

## Identity contract (limited)

Identity: `run_id`, `candidate_sha256` (64 lowercase hex), `notebook_version`.

- `run_id` is a globally namespaced label with at least two nonempty `/`-separated segments, e.g. `example.org/run-001`. Use a NEW `run_id` whenever the config, attempt, replicate, project or protocol changes. The check is shape only: it is not uniqueness, and there is no cross-manifest registry. Uniqueness is the caller's responsibility.
- `notebook_version` is null or exactly `owner/slug/version` (three nonempty segments). The same version text under a different owner/slug is a different identity.
- `candidate_sha256` binds the raw supplied candidate bytes only. It covers code plus config only if the caller bundles them into that candidate. A config is optional; its identity is its declared source identity, never inferred from the candidate hash.

## Manifest reference

Strict JSON (no duplicate keys, no NaN); exactly these keys, unknown or missing keys are refused.

| Key | Content |
| --- | --- |
| `version` | `existing-run-import/1` |
| `target` | Identity of the run being described |
| `artifacts` | 1..64 entries: `id`, `kind`, `source` (Identity), `expected_git_blob_sha1` (40 lowercase hex or null) |
| `observations` | 0..64 entries: `category`, `state`, `source_artifact_id`, `source`, `score` |
| `timings` | 0..64 entries: `phase`, `seconds`, `source_artifact_id`, `source`, `method` |
| `environment` | `os`, `python`, `accelerator` (text or null), `source_artifact_id` (an `environment` artifact or null; values need an artifact) |

Artifact `kind`: `candidate`, `config`, `log`, `evidence`, `environment`. Observations: `cpu_simulation` and `real_model` use `not_run`, `completed`, `failed`, `unknown`; `official` uses `not_obtained`, `submitted`, `scored`, `unknown`. `score` is a finite number only for `official`/`scored`, otherwise null; zero is a real score. Official observations other than `not_obtained` need a notebook version.

Cross checks: each observation/timing source must equal its artifact's source; a candidate artifact carries its own SHA-256 as `candidate_sha256`; at least one candidate artifact has a source identical in all three fields to `target`; two configs with the same source identity must have the same SHA-256 (refused before any write); every supplied byte string is referenced and every artifact is supplied.

## Timing and environment

- A timing needs a `method` (how it was measured). `seconds` is null (unknown) or a finite number >= 0; zero is a measurement. Phases: `model_execution`, `gpu_preparation`, `evaluation`, `cleanup`.
- A duplicate source + phase is refused. A phase that is absent is unknown, not zero. Timings are never summed, because phases may overlap.
- Timings are returned with their own sources. Filter by `source == target` before using one as the target's timing.
- The environment is a manually written, sanitized allowlist (`os`, `python`, `accelerator`). Nothing is collected automatically, and the importer cannot guarantee that supplied text or artifacts are free of secrets. Review them before import. The returned environment retains its artifact's source; use it as target provenance only when `result.environment.source == result.target`.

## Current state versus history

All observations are returned unchanged, including conflicts and duplicates. `current` has three summaries built only from observations whose source equals `target`: none gives the default (`not_run`, `not_obtained`) with `defaulted=True` (absence of evidence, not proof); one gives its state and score; two or more, even identical, give `state='ambiguous'`, `score=None`, `defaulted=False`. No score is selected. Scores from another notebook version, owner/slug or `run_id` stay historical and never project onto the target.

## Caps and strictness

Manifest 1 MiB; total supplied bytes 16 MiB; each blob within the store's `max_blob_bytes`; at most 64 supplied artifacts (checked before iterating) and 64 entries per list; strings 1..1024 UTF-8 bytes. Strings containing NUL or surrogates are refused. Any violation is refused with `ImportRefused` before any write. Parse-validation refusals carry no decoder cause or context. Python traceback frames can still contain private inputs: callers must not publish raw tracebacks or frame locals. Booleans are not numbers; these caps are not a depth/CPU/memory sandbox.

## I/O and failure behavior

- Validation failure (`ImportRefused`) happens before any write and leaves nothing behind.
- Writes store artifacts in manifest order, then the manifest bytes last. There is no atomic completion marker or receipt: an existing manifest blob is not proof of a verified import.
- A storage or integrity error (`OSError`, digest mismatch refusal) can leave any subset of immutable blobs. Do not retry blindly; compare the original inputs with the installed blobs.

## Windows boundary and WSL2 steps

Unchanged `BlobStore` needs `os.link`, `fsync`, `O_NOFOLLOW`, `O_DIRECTORY` and `O_EXCL`, plus a filesystem with working immutable hard links and file and directory `fsync`. Native Windows CPython is unsupported and fails closed (missing primitive refuses). The pure strict parser can inspect bytes you already hold, but persistence is not supported there. Do not disable the guards or substitute overwrite/rename.

Workable route (guidance, not tested Windows/WSL acceptance):

1. Use Linux Python inside a WSL2 distribution, not Windows Python.
2. Put the blob root on the distribution's Linux filesystem (ext4-backed recommended). Not `/mnt/c`, NTFS, network shares or a symlink root.
3. The root must be an existing, real, owner-controlled, non-symlink directory with trusted ancestors, written by one writer at a time.
4. Transfer the bytes you already hold in binary (copy, not an editor and not a Git checkout with text conversion). Record SHA-256 of each file before and after.
5. Run the importer from Linux with the example below. No installation and no model rerun is needed.

## Self-contained synthetic example

Save under an absolute path and run with an absolute source root:

```python
import hashlib, json, os, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.environ['SCIENTIST_SRC'])
from ai_agent_scientist.evidence.blob_store import BlobStore
from ai_agent_scientist.evidence.existing_run import git_blob_sha1, import_existing_run

cand = b'synthetic candidate'
ident = {'run_id': 'example.org/exec-001',
         'candidate_sha256': hashlib.sha256(cand).hexdigest(),
         'notebook_version': 'owner/slug/v1'}
manifest = {
    'version': 'existing-run-import/1', 'target': ident,
    'artifacts': [{'id': 'cand', 'kind': 'candidate', 'source': ident,
                   'expected_git_blob_sha1': git_blob_sha1(cand)}],
    'observations': [], 'timings': [],
    'environment': {'os': None, 'python': None, 'accelerator': None,
                    'source_artifact_id': None}}
raw = json.dumps(manifest).encode('utf-8')
with tempfile.TemporaryDirectory() as tmp:
    store = BlobStore(Path(tmp), max_blob_bytes=1 << 20)
    result = import_existing_run(store, raw, {'cand': cand})
    print(result.artifacts[0].git_comparison)
    print([(c.category, c.state, c.defaulted) for c in result.current])
```

```
SCIENTIST_SRC=/absolute/path/to/repo/src python3 -I /absolute/path/to/example.py
```

## Limitations

Caller-asserted identities; no origin authentication; no uniqueness registry; Git comparison needs an independently supplied expected id; no log parsing; no transactionality; POSIX-style filesystem semantics required.

# 既存 run の証跡インポート

English: [38-existing-run-import.md](38-existing-run-import.md)

標準ライブラリのみ・オフラインの補助モジュール `ai_agent_scientist.evidence.existing_run`。すでに実行済みの run の証跡（candidate、config、log、evidence、環境メモ）を、呼び出し側が保持するバイト列から `BlobStore` に取り込みます。

## 状態

ローカル補助契約（`existing-run-import/1`）で、run-record スキーマは拡張しません。実装は独立にソースレビュー済みです。対象を絞った合成データのオフライン検証は通過済みです（新規 unittest 22メソッド、既存回帰24メソッド、日英の合成例を各1回）。実モデル、研究、Windows、WSL での受入れはなく、実際の非公開データでの実行もしていません。

## できること・しないこと

- manifest のバイト列と `artifact id -> bytes` の dict を受け取ります。パスや URL の解決、供給コードの import/実行、バイト列の正規化（BOM・CRLF・マルチバイトはそのまま保存）、ログ解析は行いません。
- 各 artifact を任意の `expected_git_blob_sha1` と比較します。結果は `match` / `mismatch` / `unavailable`。不一致は報告のみで修正しません。
- Git blob id は、ヘッダ `blob <バイト長>` + NUL バイト（`\0`）+ 正確なバイト列の SHA-1 です（`git_blob_sha1`）。保存キーは同じバイト列の別の SHA-256。末尾の改行で両方とも変わります。
- 期待 id は呼び出し側が独立に（信頼できる記録などから）与える必要があります。URL やコミットの帰属はラベルであり認証ではなく、id が一致してもバイトの同一性しか示さず、出所は証明しません。
- identity・observation・timing・environment は呼び出し側が主張するラベルで、認証ではありません。

## identity 契約（限定的）

Identity: `run_id`, `candidate_sha256`（小文字16進64桁）, `notebook_version`。

- `run_id` はグローバルに名前空間化されたラベルで、空でない `/` 区切りセグメントが2つ以上（例 `example.org/run-001`）。config・試行・replicate・project・protocol が変わるたびに新しい `run_id` を使ってください。検査は形式のみで、一意性の検査ではなく、manifest をまたぐ登録簿もありません。一意性は呼び出し側の責任です。
- `notebook_version` は null か、ちょうど `owner/slug/version`（空でない3セグメント）。同じ version 文字列でも owner/slug が違えば別の identity です。
- `candidate_sha256` は供給された candidate の生バイトだけに紐づきます。コードと config の両方を含むのは、呼び出し側がそれらを1つの candidate にまとめた場合だけです。config は任意で、その identity は宣言された source identity であり、candidate のハッシュから推測しません。

## manifest リファレンス

厳密な JSON（キー重複・NaN 不可）。下記のキーのみ。未知・欠落キーは拒否します。

| キー | 内容 |
| --- | --- |
| `version` | `existing-run-import/1` |
| `target` | 対象 run の Identity |
| `artifacts` | 1〜64 件: `id`, `kind`, `source`（Identity）, `expected_git_blob_sha1`（小文字16進40桁または null） |
| `observations` | 0〜64 件: `category`, `state`, `source_artifact_id`, `source`, `score` |
| `timings` | 0〜64 件: `phase`, `seconds`, `source_artifact_id`, `source`, `method` |
| `environment` | `os`, `python`, `accelerator`（文字列または null）, `source_artifact_id`（`environment` artifact または null。値を入れるには artifact が必要） |

artifact の `kind`: `candidate`, `config`, `log`, `evidence`, `environment`。observation: `cpu_simulation`・`real_model` は `not_run`/`completed`/`failed`/`unknown`、`official` は `not_obtained`/`submitted`/`scored`/`unknown`。`score` は `official` かつ `scored` のときのみ有限数、他は null。0 は実際のスコアです。`not_obtained` 以外の official は notebook version が必要です。

相互検査: observation/timing の source は対応 artifact の source と一致。candidate artifact は自身の SHA-256 を `candidate_sha256` に持つ。`target` と3項目すべて同一の source を持つ candidate が最低1つ必要。同一 source identity の config が複数あり SHA-256 が異なる場合は、書き込み前に拒否。供給バイト列はすべて参照され、すべての artifact が供給されている必要があります。

## timing と environment

- timing には `method`（測定方法）が必須。`seconds` は null（不明）または 0 以上の有限数で、0 は計測値。phase: `model_execution`, `gpu_preparation`, `evaluation`, `cleanup`。
- 同じ source + phase の重複は拒否。存在しない phase は 0 ではなく不明。phase は重なり得るため合計はしません。
- timing は自身の source のまま返されます。対象 run の timing として使う前に `source == target` で絞り込んでください。
- environment は手書きでサニタイズ済みの許可リスト（`os`, `python`, `accelerator`）。自動収集はなく、供給したテキストや artifact に秘密情報が含まれないことをインポーターは保証できません。インポート前に確認してください。返却される environment は artifact の source を保持します。対象の出所情報として使うのは `result.environment.source == result.target` の場合だけです。

## 現在状態と履歴

すべての observation は競合や重複も含めそのまま返します。`current` は source が `target` と等しい observation だけから作る3件の要約です。なし → 既定（`not_run`、`not_obtained`）かつ `defaulted=True`（証拠がないだけで、未実行の証明ではない）。1件 → その state と score。2件以上（同一内容でも）→ `state='ambiguous'`、`score=None`、`defaulted=False`。スコアは選びません。他の notebook version・owner/slug・`run_id` のスコアは履歴のままで、対象に投影されません。

## 上限と厳格さ

manifest 1 MiB、供給バイト合計 16 MiB、各 blob はストアの `max_blob_bytes` 以内、供給 artifact は64件まで（反復前に検査）、各リスト64件まで、文字列は UTF-8 で1〜1024バイト。NUL やサロゲートを含む文字列は拒否。違反はすべて書き込み前に `ImportRefused` で拒否されます。パース検証の拒否には decoder の cause/context が付きません。ただし Python の traceback フレームには非公開入力が残り得るため、呼び出し側は生の traceback やフレームのローカル変数を公開しないでください。bool は数値として扱いません。この上限は深さ・CPU・メモリの隔離ではありません。

## I/O と失敗時の挙動

- 検証失敗（`ImportRefused`）は書き込み前に起き、何も残りません。
- 書き込みは manifest の順に artifact、最後に manifest バイト列。アトミックな完了マーカーや受領記録はなく、manifest blob があっても検証済みインポートの証明ではありません。
- ストレージ/整合性エラー（`OSError`、ダイジェスト不一致の拒否）は、任意の blob を残し得ます。盲目的に再試行せず、元の入力とインストール済み blob を照合してください。

## Windows の境界と WSL2 手順

変更していない `BlobStore` は `os.link`、`fsync`、`O_NOFOLLOW`、`O_DIRECTORY`、`O_EXCL` と、不変のハードリンクおよびファイル・ディレクトリ `fsync` が動作するファイルシステムを必要とします。ネイティブ Windows の CPython は非対応で fail closed（プリミティブ欠如で拒否）。厳密パーサーは保持済みのバイト列の検査はできますが、永続化は対応していません。ガードの無効化や上書き/rename での代用はしないでください。

実用的な手順（ガイダンスであり、Windows/WSL の受入れテスト済みではありません）:

1. WSL2 ディストリビューション内の Linux 版 Python を使う（Windows の Python は不可）。
2. blob ルートはディストリビューションの Linux ファイルシステム上（ext4 推奨）に置く。`/mnt/c`、NTFS、ネットワーク共有、シンボリックリンクのルートは不可。
3. ルートは実在し、所有者が管理する非シンボリックリンクのディレクトリで、祖先も信頼でき、同時に書き込むのは1プロセスのみ。
4. 保持済みのバイト列はバイナリのまま転送（エディタや、テキスト変換される Git チェックアウトは使わない）。転送の前後で各ファイルの SHA-256 を記録する。
5. 下の例を Linux から実行する。インストールもモデルの再実行も不要です。

## 自己完結の合成例

絶対パスで保存し、絶対パスのソースルートを指定して実行します。

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

## 制限

identity は呼び出し側の主張。出所の認証なし。一意性の登録簿なし。Git 比較には独立に与えられた期待 id が必要。ログ解析なし。トランザクションなし。POSIX 相当のファイルシステム動作が必要。

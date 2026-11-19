# 既存実験のintake

English: [39-intake-summary.md](39-intake-summary.md)。identityとimport契約を定める[38 既存runのimport](38-existing-run-import.ja.md)を土台にし、それは変更しません。

## 状態

標準ライブラリのみのオフライン補助`ai_agent_scientist.evidence.intake`に、CLIと明示的なステージ結果を実装しました。CLIのケースを含む合成の契約テストは`PYTHONPATH=src python3 -B -m unittest discover -s tests/contracts`で実行します。オフラインの設計チェックは、JSON Schema 2020-12バリデーターが利用できる環境で`python scripts/check_design.py`を実行します。実モデル・GPU・研究・Windows/WSL・公式スコアの受入確認は、これらのローカルチェックの対象外です。

## API

`intake_paths(store, manifest_path, candidate_path, config_path, log_paths, stages_path=None)`は`IntakeResult(imported, stages_sha256, summary)`を返します。`log_paths`はlog idから明示pathへの対応で、開くのはそれだけです（探索・glob・manifest内pathなし）。`stages_path`なしでは全stageがUNKNOWNです。

1. 各ファイルはnonblocking・no-followで開き、descriptorで通常ファイルを確認し、store上限と合計16 MiBで制限します。末尾symlink・ディレクトリ・FIFO・上限超過・`O_NOFOLLOW`/`O_NONBLOCK`の欠如は固定の内容を含まない理由で拒否します。親ディレクトリは信頼前提で、隔離runnerではありません。
2. 書込み前に拒否されるのは入力検証（ファイル・形式・stages・対応）の拒否だけです。
3. candidate・config・log・manifestバイト・stagesバイトを変更せず保存し、各blobを読み戻して比較します。I/O・digest・読戻しの失敗は書込み後にも起き得て、不変blobの一部が残る可能性があります。盲目的に再試行せず照合してください。

storeは既存の非公開・所有者管理・非symlinkのディレクトリ（信頼できる親、単一writer）で、run入力とは別にします。取り込んだ証跡はここに残り、このAPIは何も削除せず、`run_id`の全体一意性も強制しません。configやattemptが変わるたびに新しい`run_id`を使ってください。

## CLI

リポジトリのルートから、既存のstoreと入力ファイルのパスを明示して実行します。

```sh
PYTHONPATH=src python -m ai_agent_scientist.evidence.intake \
  --store /path/to/run/blobs --manifest /path/to/run/in/manifest.json \
  --candidate /path/to/run/in/candidate.py --config /path/to/run/in/config.json \
  --log train /path/to/run/in/train.log --stages /path/to/run/in/stages.json
```

manifestの各logに対して`--log ID PATH`を1回ずつ指定します。logがなければ省略します。`--stages`は任意です。CLIはstoreの上限を16 MiBにして`intake_paths`を呼び、成功時は標準出力にsummaryのJSONオブジェクトを1つ出力します。不正な証跡や保存時のエラーは終了コード1、不正な引数は終了コード2です。いずれも標準エラー出力に固定の診断文を出し、標準出力は空です。パス指定と書き込みの動作はAPIと同じです。

## manifest形式

通常の`existing-run-import/1`で、artifactは`candidate`（kind `candidate`）、`config`（kind `config`）、指定したlog id（kind `log`）だけです。他のidやkindは拒否します。`candidate`と`config`はtarget identityを宣言する必要があり、他のconfigをtargetへ結び付けません。candidateのhashはそのバイトと一致が必要です。logは別runのidentityを宣言でき、履歴です。config identityは宣言ラベルで、candidate hashから導出しません。

## stagesファイル

閉じた別契約`intake-stages/1`で、manifestやrun-recordのwireは変えません。stageは`gpu_environment`、`model_launches`、`tests_collected`、`test_bodies_executed`、`patch_recovery`、`test_pass`を各1回まで。entryのキーは`stage`、`result`、`count`、`stop_reason`、`log_ids`。`target`はmanifestと一致。resultはstageごとの固定集合（`started`/`collected`/`executed`/`recovered`/`passed`、`failed`、`not_started`、`unknown`）。`count`はnullか0〜10^9の整数で、launchとtestのみ（0はnullと別、`unknown`はcountなし）。`stop_reason`は`none`・`not_started`・`interrupted`・`unavailable`・`unknown`。`log_ids`はtargetを宣言する取り込み済みlogを最大8個。

欠落stageと明示`unknown`はどちらも`UNKNOWN`・count nullで表示します。欠落stageのstop_reasonは`unknown`・logなし、明示`unknown`は指定したstop_reasonとlog digestを保持します。stage間の推測はしません（GPU開始は起動を、収集は実行を、回復はpassを意味しません）。logは解析せず、ラベルは呼び出し側の主張です。

### v2の明示的なステージ結果

`version`に`intake-stages/2`を指定すると、`stages`配列に`startup`、`inference`、`tool_handling`、`output_verification`を含められます。v2でも最上位のキー、target identityの一致条件、既存6ステージの契約は同じです。新しいステージは各1回までで、キーは`stage`、`result`、`log_ids`です。`result`には`success`、`failure`、`not_run`、`unknown`のいずれかを指定します。`log_ids`はtargetの重複しないlog IDを最大8個指定でき、該当するlogがなければ`[]`を指定します。

新しいステージには、外部証跡の`declared_evidence_sha256`を任意で指定できます。値は小文字の16進数64桁の文字列かnullで、省略もできます。intakeはdigestの形式を検証して呼び出し側の宣言を保持します。外部証跡のバイト列の取得、保存、ハッシュ計算は行いません。形式が不正なdigestは書き込み前に拒否します。

`output_verification`に限り、任意で`verdict`を指定できます。呼び出し側が`success`または`failure`を宣言した場合、比較判定には`exact_match`、`formatting_mismatch`、`numeric_mismatch`を指定できます。比較判定がなければ`verdict`を省略するかnullにします。数値が同じで末尾改行だけが異なる場合は`formatting_mismatch`と宣言できます。`result`は呼び出し側が自身の検証方針に沿って指定します。intakeはラベルを検証し、実際の出力や期待値そのものを格納するフィールドは受け付けません。

このv2サイドカーでは、呼び出し側がASCIIの2バイト`42`を末尾改行付きの`42`と比較し、実際の出力のSHA-256を宣言します。targetとlogは[合成例](#合成例)と同じです。

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

## summary

JSON互換で、target identity、candidate・configのdigestと宣言identity、manifest・stagesのdigest、artifactのkind・digest・サイズ・Git比較、3つの結果カテゴリ（CPU simulation・実モデル・公式）、6つのstage、`verified_readback`を含みます。targetの証拠が無いカテゴリは`UNKNOWN`です。公式スコアは、targetを宣言する公式observationがちょうど1件で`scored`のときだけ、artifact digestとsource identity付きで出ます。他のcandidate・runのスコアは`imported.observations`に履歴として残ります。logの内容・ローカルpath・環境ラベル・入力エラー文は含みません。

`format`の値は`intake-summary/1`のままで、既存フィールドの構造も同じです。`stage_results`は4つのステージ名をキーとし、各項目に`result`、`verdict`、`declared_evidence_sha256`、`logs`（指定されたtargetのlogのSHA-256）を含みます。宣言されたdigestを省略するか明示的にnullにすると、summaryではnullになります。サイドカー未指定時、v1使用時、またはv2で項目を省略した場合は、結果が`UNKNOWN`、比較判定と宣言されたdigestがnull、log一覧が空になります。明示的な`unknown`は宣言されたdigestと指定されたlogのdigestを保持し、明示的な`not_run`はそのまま表示します。各ステージの結果は独立して報告します。

`stages_sha256`は検証済みサイドカーファイルの正確なバイト列のdigestです。`verified_readback`はintakeが保存したバイト列の読み戻しを確認したことを示します。ステージ結果、比較判定、外部証跡のdigestは、呼び出し側による未検証の宣言です。上記のv2サイドカーの`stage_results`は次のとおりです。

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

## 合成例

完全な実行可能コードは英語版の[Synthetic example](39-intake-summary.md#synthetic-example)と同一です。流れ：（1）`tempfile.mkdtemp()`で実データではない新規の合成ディレクトリを作り、入力用`in`とstore用`blobs`を別に作る。（2）candidate・config・logを末尾改行も含め正確なバイトで書く。（3）6キー（version・target・artifacts・observations・timings・environment）の`existing-run-import/1`manifestを作り、正規id`candidate`/`config`/`train`が同一targetを宣言し、`candidate_sha256`がcandidateのバイトと一致するようにする。（4）同じtargetを持つstagesを書く。（5）`intake_paths`を呼び、パスを表示し、summaryをJSON出力する。storeは読戻し用に残り、既存入力の上書きや削除はなく、モデルもcandidateも実行しません。

## 主張しないこと

CPU simulation・実モデル・公式は別々のままです。GPU・実モデル・研究・公式スコアの成功やネイティブWindowsの対応は主張しません。`BlobStore`はPOSIXの機能が必要なため、[38](38-existing-run-import.ja.md)のとおりLinuxファイルシステム上のWSL2を使ってください。

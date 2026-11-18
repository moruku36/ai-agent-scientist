# 既存実験のintake

English: [39-intake-summary.md](39-intake-summary.md)。identityとimport契約を定める[38 既存runのimport](38-existing-run-import.ja.md)を土台にし、それは変更しません。

## 状態

標準ライブラリのみのオフライン補助`ai_agent_scientist.evidence.intake`です。ソース・合成unittestメソッド8つ・本文書を作成済みで、検査とレビューは保留中です。実モデル・GPU・研究・Windows/WSL・公式スコアの受入は主張せず、実データも使っていません。

## API

`intake_paths(store, manifest_path, candidate_path, config_path, log_paths, stages_path=None)`は`IntakeResult(imported, stages_sha256, summary)`を返します。`log_paths`はlog idから明示pathへの対応で、開くのはそれだけです（探索・glob・manifest内pathなし）。`stages_path`なしでは全stageがUNKNOWNです。

1. 各ファイルはnonblocking・no-followで開き、descriptorで通常ファイルを確認し、store上限と合計16 MiBで制限します。末尾symlink・ディレクトリ・FIFO・上限超過・`O_NOFOLLOW`/`O_NONBLOCK`の欠如は固定の内容を含まない理由で拒否します。親ディレクトリは信頼前提で、隔離runnerではありません。
2. 書込み前に拒否されるのは入力検証（ファイル・形式・stages・対応）の拒否だけです。
3. candidate・config・log・manifestバイト・stagesバイトを変更せず保存し、各blobを読み戻して比較します。I/O・digest・読戻しの失敗は書込み後にも起き得て、不変blobの一部が残る可能性があります。盲目的に再試行せず照合してください。

storeは既存の非公開・所有者管理・非symlinkのディレクトリ（信頼できる親、単一writer）で、run入力とは別にします。取り込んだ証跡はここに残り、このAPIは何も削除せず、`run_id`の全体一意性も強制しません。configやattemptが変わるたびに新しい`run_id`を使ってください。

## manifest形式

通常の`existing-run-import/1`で、artifactは`candidate`（kind `candidate`）、`config`（kind `config`）、指定したlog id（kind `log`）だけです。他のidやkindは拒否します。`candidate`と`config`はtarget identityを宣言する必要があり、他のconfigをtargetへ結び付けません。candidateのhashはそのバイトと一致が必要です。logは別runのidentityを宣言でき、履歴です。config identityは宣言ラベルで、candidate hashから導出しません。

## stagesファイル

閉じた別契約`intake-stages/1`で、manifestやrun-recordのwireは変えません。stageは`gpu_environment`、`model_launches`、`tests_collected`、`test_bodies_executed`、`patch_recovery`、`test_pass`を各1回まで。entryのキーは`stage`、`result`、`count`、`stop_reason`、`log_ids`。`target`はmanifestと一致。resultはstageごとの固定集合（`started`/`collected`/`executed`/`recovered`/`passed`、`failed`、`not_started`、`unknown`）。`count`はnullか0〜10^9の整数で、launchとtestのみ（0はnullと別、`unknown`はcountなし）。`stop_reason`は`none`・`not_started`・`interrupted`・`unavailable`・`unknown`。`log_ids`はtargetを宣言する取り込み済みlogを最大8個。

欠落stageと明示`unknown`はどちらも`UNKNOWN`・count nullで表示します。欠落stageのstop_reasonは`unknown`・logなし、明示`unknown`は指定したstop_reasonとlog digestを保持します。stage間の推測はしません（GPU開始は起動を、収集は実行を、回復はpassを意味しません）。logは解析せず、ラベルは呼び出し側の主張です。

## summary

JSON互換で、target identity、candidate・configのdigestと宣言identity、manifest・stagesのdigest、artifactのkind・digest・サイズ・Git比較、3つの結果カテゴリ（CPU simulation・実モデル・公式）、6つのstage、`verified_readback`を含みます。targetの証拠が無いカテゴリは`UNKNOWN`です。公式スコアは、targetを宣言する公式observationがちょうど1件で`scored`のときだけ、artifact digestとsource identity付きで出ます。他のcandidate・runのスコアは`imported.observations`に履歴として残ります。logの内容・ローカルpath・環境ラベル・入力エラー文は含みません。

## 合成例

完全な実行可能コードは英語版の[Synthetic example](39-intake-summary.md#synthetic-example)と同一です。流れ：（1）`tempfile.mkdtemp()`で実データではない新規の合成ディレクトリを作り、入力用`in`とstore用`blobs`を別に作る。（2）candidate・config・logを末尾改行も含め正確なバイトで書く。（3）6キー（version・target・artifacts・observations・timings・environment）の`existing-run-import/1`manifestを作り、正規id`candidate`/`config`/`train`が同一targetを宣言し、`candidate_sha256`がcandidateのバイトと一致するようにする。（4）同じtargetを持つstagesを書く。（5）`intake_paths`を呼び、パスを表示し、summaryをJSON出力する。storeは読戻し用に残り、既存入力の上書きや削除はなく、モデルもcandidateも実行しません。

## 主張しないこと

CPU simulation・実モデル・公式は別々のままです。GPU・実モデル・研究・公式スコアの成功やネイティブWindowsの対応は主張しません。`BlobStore`はPOSIXの機能が必要なため、[38](38-existing-run-import.ja.md)のとおりLinuxファイルシステム上のWSL2を使ってください。

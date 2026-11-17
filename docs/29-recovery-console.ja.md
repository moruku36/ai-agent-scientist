# 29 ローカル復旧コンソール

日本語 | [English](29-recovery-console.md)

**状態：増分29（2026-11-17）作成済み・未実行（NOT EXECUTED）。** ソースと新規の自己完結テスト6件（K01–K06）を作成しましたが、この増分の検査は一切実行していません。過去の検証bannerは過去の増分のみが対象です。runtime受入ではありません。

`admission/recovery_console.py`の`render_recovery_console(receiver, *, after_request_id=None, limit=100, max_output_bytes=65536)`は、[非公開復旧report](28-recovery-report.ja.md)の1ページを不変の`ConsoleView(text, report_sha256, entry_count, next_after_request_id)`へ変換します。

## 信頼境界

- 構築済みreceiverを持つ、独立に信頼できる呼び出し側によるプロセス内ライブラリ呼び出しです。CLI・receiver構築・ファイル／ネットワーク／プロセス／ツール利用・時計・新schema・default・guard・認証・runtime・dispatchの変更はありません。
- `build_recovery_report`をちょうど1回呼び、その実JSONを解析します。内部的に整合した偽造履歴は検出できません。

## 表示

`PRIVATE LOCAL RECOVERY CONSOLE - NOT AUTHORITY`のヘッダーに続き、予約ごとに1行（request ID、receipt状態／revision、全量outstanding worker-seconds、最新usage、stop・cleanup、ローカルack状態、reason code）を出します。

- usageは`UNKNOWN`／`ZERO`／`KNOWN:n`、stop・cleanupは`unknown`／`false`／`true`（観測なしは`unknown`）、ackは`unknown`／`pending`／`acknowledged`です。UNKNOWNはゼロではなく、releaseやsettlement、実プロセスの真偽は推測しません。
- 出力は決定的な印字可能ASCIIと改行のみです。識別子はJSONエスケープされ、制御文字・DEL・非ASCIIも含むため端末制御を注入できません。
- `report_sha256`は表示テキストではなく元reportバイトのdigestです。

## 非公開性・上限・失敗

出力は非公開の運用者向けで、公開しないでください。各ページは独立した読取snapshotで、cursorは排他的位置でありleaseではありません。`max_output_bytes`は1..1048576の厳密なintで、超過時は全体を拒否（`RecoveryConsoleTooLarge`）し部分テキストを返しません。report側の失敗は伝播し何も返しません。

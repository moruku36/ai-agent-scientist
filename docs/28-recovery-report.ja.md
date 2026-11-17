# 28 上限付き決定的な非公開復旧レポート

> 増分28のcoordinator検査：最初の6メソッドは5成功・F04のfixtureエラー1件で、不変eventの削除が正しく拒否されました。file-onlyテスト修正でtrusted API外の旧形式event欠落を模し、唯一の対象再検査でF01–F06の6件すべて成功（0.050秒）。既存環境の設計checkerは1回成功（620リンク・36言語pair）、空白検査も成功。以下の未実行／保留はworker作成時点で後続検査ではありません。独立レビューは別途記録し、runtime受入ではありません。

[English](28-recovery-report.md) | [ホーム](../README.ja.md) | [実装計画](10-roadmap.ja.md) | [27 復旧triage](27-recovery-triage.ja.md)

**増分28の状態（2026-11-17）：ソースと新規の自己完結unittestメソッドを正確に6つ作成済み、未実行（NOT EXECUTED）。** 3番目の接続された上限付きoffline増分です。既存coordinator bannerは明記された過去の増分だけが対象です。今回はファイルの読取／編集のみで、テスト・checker・build・実装import・network・Git操作・model subcall・process・公開は実行していません。増分28の実行・再現・独立レビュー・runtime受入は保留中です。

[recovery_report.py](../src/ai_agent_scientist/admission/recovery_report.py)は実際の[triage](27-recovery-triage.ja.md)をメモリ内の不変artifactへ接続します。新しい台帳・DB・ファイル・sender・公開exportを作りません。[検査](26-reservation-inspection.ja.md)・受領・予約・観測・schema・正本wire版は維持します。

## 小さな接続API

```python
artifact = build_recovery_report(
    trusted_receiver, after_request_id=None, limit=25, max_output_bytes=65536)
# artifact.data: bytes; artifact.sha256: その厳密バイトの小文字SHA-256
# artifact.after_request_id, limit, next_after_request_id, entry_count: frozen metadata
```

**既存の独立して信頼するreceiver**を渡します。builderは実際の `inspect_recovery_triages` を正確に1回呼び、そのreceiverページは既存の単一読取transactionを使います。射影・直列化・hashは返された不変viewだけを使い、再lookupしません。CLIやconstructor呼出は追加しません。receiverを開くconstructorはschemaを書き込むためです。builderはfilesystem操作・blob読取・時計取得・process／network access・ack・書込・修復を追加しません。委譲先receiverが既存の保持済みSQLite読取とerror処理を行います。

具体的receiver APIだけを受け入れ、caller作成のreport／snapshot／JSON intakeはありません。caller・import・receiver instance／method・scope mapping・private SQLiteは候補の管理外に置きます。厳密型・整合した参照・SHA-256でも、一貫して捏造した履歴を自己認証できません。artifact dataclassの直接構築は来歴APIではありません。これは **PRIVATEの選択metadata** であり、証明・権限・認証済み受領・受付結果・正本wire object・JCSではありません。

## 明示的な射影と診断

実装は許可fieldを個別に列挙し、dataclass全体をdumpしません。各ページentryは次を保持します。

| 部分 | 元の選択された事実 |
|---|---|
| Receipt | project／endpoint・request／message ID・厳密request／payload digest・現在revision／state・保持timestamp |
| Reservation／accounting | 安定予約参照・request ID／digest・元の全量／時刻・allocationとoutstandingの全量 |
| Current status／local ack | 厳密event ID・request／予約／digest／revision・status／量／時刻・独立ack revisionとnullable ack時刻 |
| Latest usage observation | 厳密sequence／observation ID・request／予約／digest・元expected revision／時刻・nullable usage／over-cap・独立stopped／cleanup flag |
| Reasons | 接続triageの全reasonを元の決定的な順序で保持。action／dispositionはなし |

principal識別情報・共有owner namespace／envelope・認可参照・global合計・cap・settled floor・残容量・blob内容・DB path・例外詳細はartifactに入りません。予約参照とdigestは診断locatorで、権限ではありません。event IDと観測sequenceはreceiver内だけの値です。独立して信頼する元receiverとの対応はartifact外で保持します。このartifact自身は元を探索／認証しません。別のsource台帳は追加しません。

既知ゼロ・実行停止・cleanup既知・ローカルack済みでも、返す全予約は全量outstandingです。観測なしはJSON `null`、UNKNOWN観測は `worker_seconds:null` と `over_cap:null` を持つobjectです。既知ゼロは整数 `0`、超過量も元の値です。現在statusなしは `null` と不明local ackのままです。local ackは遠隔配送を意味しません。reasonは説明だけで、retry・release・dispatch・settlement・完了を認可しません。

選択は最大の **ローカル挿入sequence** だけで、最大timestamp・権威ある最新事実・全履歴・累積usage・最大usageではありません。古い完全再送は挿入順を進めず、後で挿入したUNKNOWNはUNKNOWNです。加算や差引はしません。別call／pageは後続commitを見られ、binary request-ID cursorは排他的seek位置でありleaseやページ間固定snapshotではありません。変更entryやcursorより前への挿入を再確認するには `None` から再走査します。空scope／受領のみでは予約entryはなく、欠如も権限を与えません。

## 厳密バイト・上限・失敗

固定の明示的local-only版は `receiver-recovery-report-local/1` です。Python標準 `JSONEncoder` の `sort_keys=True`・`ensure_ascii=True`・`allow_nan=False`・`separators=(',', ':')` を使い、UTF-8、BOM／末尾改行なしにします。object keyは辞書順、arrayはreceiver／reason順、文字列はJSON ASCII escapeです。整数／null／boolの型を保持します。この厳密手順はRFC 8785 JCSではありません。直列化変更には明示的local版変更が必要です。SHA-256は `artifact.data` だけをhashし、そのバイト内には埋め込みません。選択pageの事実とpage引数が同一なら、保持状態を変えずに再openしても同一bytes／hashです。同時変更後のartifactは変わり得ます。

`max_output_bytes` は厳密builtin intの `1..1_048_576` で、bool・subclass・型変換を読取前に拒否します。既定と絶対上限は1 MiBです。cursorと `limit` はtriageの厳密検証と `1..100` のページ上限を引き継ぎます。encodeしたchunkをbufferへ追加する前に検査し、上限と同じバイト数は成功します。超過は値を含まない `RecoveryReportTooLarge` で全artifactを破棄し、部分bytes・digest・成功cursorを返しません。切詰や自動小ページ再試行はありません。これは出力の上限で、DB保持総量やinterpreterの全memoryの上限ではありません。

receiver／storage／scope／triageの失敗は後方rowの失敗も含め伝播し、成功artifactを返しません。例外chainはowner診断用のままで直列化しません。失敗を空／UNKNOWN成功へ変えません。rollbackはbuilderの利用停止と正本状態の保持で、戻すreport書込はありません。非公開取扱と後の選択exportは[09](09-safety-publication.ja.md)の実際の認可に従います。自動exportは実装しません。

## 対応する合成ローカル例

全値が合成で、実artifactや検証済み履歴ではありません。完全な選択JSON形状を読みやすく表示した例で、実bytesは上記compact sorted手順に従います。正本schema／example fileは追加／変更しません。

```json
{
  "local_report_version": "receiver-recovery-report-local/1",
  "visibility": "private",
  "observation_selection": "latest_local_insertion_only",
  "page": {"after_request_id": null, "limit": 1, "next_after_request_id": null},
  "entries": [{
    "receipt": {
      "project_id": "synthetic-project", "sender": "scientist", "recipient": "ctf",
      "request_id": "request-one", "message_id": "message-one",
      "request_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "payload_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "revision": 2, "state": "reconciliation_required",
      "recorded_at": "2026-11-17T12:00:00.000000Z",
      "updated_at": "2026-11-17T12:00:01.000000Z"
    },
    "reservation": {
      "budget_reservation_ref": "reserve-one", "request_id": "request-one",
      "request_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "worker_seconds": 20, "recorded_at": "2026-11-17T12:00:00.000000Z"
    },
    "accounting": {"allocation_worker_seconds": 20, "outstanding_worker_seconds": 20},
    "current_status": {
      "event": {
        "event_id": 2, "request_id": "request-one", "budget_reservation_ref": "reserve-one",
        "request_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "receipt_revision": 2, "status": "reconciliation_required", "worker_seconds": 20,
        "created_at": "2026-11-17T12:00:01.000000Z"
      },
      "ack_revision": 0, "acknowledged_at": null
    },
    "latest_usage_observation": {
      "sequence": 1, "observation_id": "observation-one", "request_id": "request-one",
      "budget_reservation_ref": "reserve-one",
      "request_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "expected_revision": 1, "worker_seconds": null, "execution_stopped": false,
      "cleanup_known": false, "over_cap": null, "observed_at": "2026-11-17T12:00:01.000000Z"
    },
    "reasons": [
      "reservation_fully_outstanding", "receipt_reconciliation_required", "local_ack_pending",
      "latest_insertion_view_only", "usage_unknown", "execution_not_independently_stopped",
      "cleanup_unknown"
    ]
  }]
}
```

## 新規の自己完結テストを正確に6つ作成 — 未実行

[自己完結unittestソース](../tests/contracts/test_recovery_report.py)は実際の一時BlobStore／private SQLite fixtureを使い、過去のテストをimportしません。

| ID | 作成した範囲 |
|---|---|
| F01 | request → reserve → observation → 実triage → bytes・元の厳密参照・allowlist除外・不変artifact／hash |
| F02 | 空ページの厳密golden bytes・Unicode escape・再openの決定性／hash・blob不要 |
| F03 | 実scope別page／cursor・受領のみ除外・cursorより前の挿入・厳密型／上限・sender拒否 |
| F04 | 観測なしとUNKNOWN／ゼロ／超過・独立flag・local ack／statusなし・挿入順と時刻／再送・全量outstanding |
| F05 | 厳密バイト境界・上限と厳密型・全artifact拒否と部分返却なし・任意intakeなし |
| F06 | 単一の実SQLite読取transaction／connection・row／file不変・constructor／書込なし・同時WAL commitを跨ぐページ整合・後方row conflict・実storage失敗 |

リンク・言語pair・JSON例・status整合を含む全実行と[設計検査](../scripts/check_design.py)は、file-only指示により **保留・未実行（NOT EXECUTED）** です。作成したケースから成功・復旧／再現結果・独立レビューは主張しません。

# 34. 現在のリカバリ状態に対する明示的なローカルack

[English](34-recovery-ack.md) | [README](../README.ja.md) | [24 ローカル状態outbox](24-local-status-outbox.ja.md) | [27 リカバリ・トリアージ](27-recovery-triage.ja.md) | [31 リカバリ操作](31-recovery-operator.ja.md) | [33 プレビュー適用](33-recovery-apply.ja.md)

**Scientist increment23・ファイルのみ（2026-11-17）: ソース、新規の自己完結したunittestメソッドちょうど6件、日英ドキュメントを作成済み・未実行。** この増分ではテスト、検査、実装のimport、ビルド、ネットワーク、git、モデル、API、研究実行を行っていません。実行、再現、独立レビュー、ランタイム受け入れは保留中です。以前のコーディネータ検証結果は今回のファイルを検証しません。文書番号34はScientistの増分名および[23 予算予約](23-local-budget-reservation.ja.md)とは別です。

[recovery_ack.py](../src/ai_agent_scientist/admission/recovery_ack.py) は、実際のトリアージによる選択対象の検査1回を、既存のレシーバ内イベントack CASへ接続します。[31](31-recovery-operator.ja.md)の信頼できる呼び出し元による明示操作の形式に従い、[27](27-recovery-triage.ja.md)から実際の[26 予約検査](26-reservation-inspection.ja.md)と[22 永続受領](22-durable-handoff-receipt.ja.md)を使用します。レシーバ生成、別ストア、新規スキーマ、依存、wire版、CLI、通信、時計の取得、再試行、自動操作は追加しません。候補ワーカーは呼び出し元、スコープ、レシーバ、認可、評価器、予算書き込みの境界外に置きます。

## 選択は読み取りスナップショット

```python
selected = select_current_recovery_status(receiver, 'req-1')
```

読み取り前に厳密な要求IDを検証し、実際の `inspect_recovery_triage(receiver, request_id)` をちょうど1回呼びます。この依存先は厳密な具象型 `DurableHandoffReceipts` を要求し、独立して信頼されたスコープと受領・予約・イベントの完全な結び付きを検証します。ダックタイピングのアダプタ、渡されたレポート、レシーバのコンストラクタ、2回目の検査は使いません。既存のレシーバとトリアージのエラーは伝播します。

要求なし、受領のみ、現在の受領リビジョンの状態イベントなしの場合は `None` を返します。古い保留イベントへフォールバックしません。現在のイベントが既にack済みでも `ack_revision=1` として選択できます。選択自体はackを書き込みません。

frozenかつslottedな `RecoveryStatusSelection` は、選択した6フィールド `request_id`、`request_sha256`、`receipt_revision`、`event_id`、`event_receipt_revision`、`ack_revision` をそのままコピーします。自由に生成・置換でき、検証済み来歴でも権限でもありません。frozenはそのインスタンスの通常の変更を防ぎますが、呼び出し元、レシーバ、履歴、人間の意図を認証できません。イベントIDは権威あるDB内のローカルIDです。選択から操作まで独立して信頼された同じレシーバを使ってください。この値はDBの同一性を束縛せず、別レシーバでの操作を認可しません。

## 明示的なスカラー操作

```python
selected = select_current_recovery_status(receiver, 'req-1')
if selected is not None:
    # 信頼できる呼び出し元が別途この操作を選ぶ。選択は自動実行しない。
    acked_event = acknowledge_current_recovery_status(
        receiver,
        request_id=selected.request_id,
        expected_request_sha256=selected.request_sha256,
        expected_receipt_revision=selected.receipt_revision,
        expected_event_id=selected.event_id,
        expected_ack_revision=selected.ack_revision,
        now=injected_utc_now,
    )
```

汎用操作は、選択dataclassを能力として受け取らず、明示的なキーワードの期待値を受け取ります。戻り値は既存の `LocalStatusEntry` です。

1. 読み取り前に組み込みスカラーの厳密な型を要求します。要求IDは空でない1024 UTF-8バイト以内の文字列で、NULと不正Unicodeを含みません。ダイジェストは小文字16進数64文字ちょうどです。期待する受領リビジョンとイベントIDは `1..2**63-1` の整数、期待するackリビジョンは厳密な整数 `0` のみです。bool、整数・文字列のサブクラス、型変換は拒否します。不正スカラーは検査前に値を含まない `RecoveryAckRefused` になります。
2. 以前の選択とは独立して、実際のトリアージ経路で1回だけ選択します。要求ID、要求ダイジェスト、受領リビジョン、現在のイベントID、ackリビジョンを明示的な期待値と一致させます。さらに選択したイベントの受領リビジョンを期待する受領リビジョンへ束縛し、保留中のackリビジョン0を要求します。実際のトリアージはイベントの同一性・ダイジェスト・スコープを受領と予約へ既に束縛しています。要求なし、受領のみ、現在の状態なし、古い期待値、ack済み、偽造した同一性の期待値は、書き込み委譲前に `RecoveryAckRefused('recovery acknowledgement refused')` となります。新しい現在の受領・イベントに対して古い保留イベントのIDを渡してもackできません。
3. `receiver.acknowledge_status_event(selected.event_id, expected_ack_revision=0, now=now)` へ**1回だけ**委譲します。既存のスコープ付きack CAS、時刻検証、エラー型、戻り値を維持します。捕捉・再試行、フォールバック、書き込み後の検査、2回目のackは追加しません。

`now` は注入され、そのまま渡されます。既存レシーバは `tzinfo` が `timezone.utc` の厳密なUTC-aware `datetime` と、選択イベントの生成時刻以降であることを要求します。時刻検証は選択後の委譲先で行うため、不正時刻でも読み取りは成功し得ますが、ackは挿入されません。レシーバのスコープ・ストレージエラー、`InvalidRecoverySnapshot`、`ReceiptRevisionError`、時刻エラーは、成功やUNKNOWNへ変換せず伝播します。

## 読み取りとイベントack CASは別トランザクション

新しいトリアージ検査は1つの読み取りトランザクションです。ackは選択イベントのackリビジョンだけを検査する**別のイベントack CASトランザクション**です。現在の受領・イベントの検査とackが原子的にまとまるわけではありません。

- 操作時の検査より前に受領・イベントが変われば、古い同一性の期待値は委譲前に拒否されます。
- 検査後に競合ackが先にCASを成功させると、この操作の1回の委譲は既存の `ReceiptRevisionError` になります。競合側の変更は残り、この操作は2個目のackを追加しません。
- **検査後、ack前**に新しい受領リビジョンと状態イベントがコミットされても、古いイベントの保留中ackリビジョンは無効になりません。操作は**古いイベント**のackに成功し、**新しい現在のイベントは保留のまま**になり得ます。受領、新イベント、全予約は保持されます。

**戻り値が識別するのはACKしたイベントだけであり、現在の状態・配信・精算ではありません。** 成功を「現在の要求がack済み」「キュー処理済み」「配信済み」「完了」「精算済み」と表示しないでください。その主張をするための追加読み取りは意図的に行いません。後続の検査も別のスナップショットであり、既に更新されている可能性があります。

UNKNOWNの使用量・クリーンアップを含め、全予算割当と全額未解決の予約は変わりません。ackで変えるのは既存イベントの別のローカルack行だけで、受領、不変イベント、観測、認可、精算済み下限、共有予約カウンタは変えません。作業停止も、受け入れ、ディスパッチ、再試行、解放、検証の権限付与も行いません。

## 合成値と競合時の結果

日英で同一の説明用JSONです。新しいwire・スキーマ形式ではありません。IDとダイジェストは合成値です。選択は非公開のローカル値であり、公開エクスポートや保護された検証受領ではありません。

```json
{
  "request_id": "req-1",
  "request_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "receipt_revision": 1,
  "event_id": 1,
  "event_receipt_revision": 1,
  "ack_revision": 0
}
```

操作の新しい検査の後にリビジョン2が生じた場合、次の省略表示は成功時に可能な結果です。Pythonの戻り値は `LocalStatusEntry` 内に古い `LocalStatusEvent` 全体を保持します。下の別途検査した現在のビューは戻り値には含まれません。

```json
{
  "returned_acked_event": {
    "event_id": 1,
    "receipt_revision": 1,
    "ack_revision": 1,
    "acknowledged_at": "2026-11-17T12:00:02.000000Z"
  },
  "separately_inspected_current": {
    "receipt_revision": 2,
    "event_id": 2,
    "event_receipt_revision": 2,
    "ack_revision": 0
  },
  "outstanding_worker_seconds": 20
}
```

## エラー、保持、作成したケース

`RecoveryAckRefused` はack委譲前の値を含まない拒否です。委譲先の失敗は別で、コミット後の応答・closeエラーでは選択イベントが既にack済みの場合があります。不確実な場合は権威あるDBを保持して独立に検査し、会計のリセットや自動再試行をしないでください。ロールバックAPI、ack削除、バックフィル、移行、修復、削除整理、スケジュール、公開、外部通信は追加しません。[既存の非公開SQLiteの信頼前提](22-durable-handoff-receipt.ja.md)が適用され、コード・import・レシーバメソッド・スキーマを信頼する必要があります。同一UIDの敵対コードや一貫して捏造された履歴への防御ではありません。この増分の使用をやめる場合も、すべての事実とackを保持して既存の検査APIを使います。

[test_recovery_ack.py](../tests/contracts/test_recovery_ack.py) には、実際の非公開一時SQLite/BlobStoreフィクスチャをコピーした新規・自己完結のメソッドがちょうど6件あります。過去のテストクラスからはimportしません。

| ID | 作成した対象 |
|---|---|
| K01 | frozenの厳密な選択、実際の読み取り1回、受領リビジョン1と2の操作、ack委譲1回、ack行以外のDB全体不変、全予算・観測・別要求の保持 |
| K02 | 厳密なスカラー型、UTF-8・ハッシュ・整数の境界、サブクラスを読み取り前に拒否。有効な1024バイトID境界 |
| K03 | 古い・偽造ダイジェスト、受領リビジョン、古い・別イベント、ack期待値の拒否。dataclassを能力にしない。実際のトリアージによるイベント受領リビジョン偽造の拒否 |
| K04 | 実際の要求なし・受領のみ・現在の状態なし・ack済み。レガシーのイベント欠落を信頼API外で再現し、古い保留イベントへ戻らない |
| K05 | 競合ack CASは1回で失敗。検査後の新受領・イベントを注入し、古いイベントの正確な戻り値と新しい現在イベントの保留、全予算保持を確認する設計 |
| K06 | 注入した不正・逆行時刻、同じエラーの伝播、再試行・コンストラクタなし、具象レシーバの強制、実コミット後の応答喪失 |

6メソッドすべて、リンク・言語対・JSON・状態の検査、[設計検査](../scripts/check_design.py)、ランタイム検査、再現性検査は、明示的なファイル限定指示により**未実行・保留中**です。合格、再現済み、独立レビュー済み、ランタイム受け入れ済みという結果は主張しません。

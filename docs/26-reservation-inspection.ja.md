# 26 受信者scope内の予約検査と復旧snapshot

> Coordinator検証（2026-11-17）：新規I01–I06の6メソッドが1回offline成功（0.039秒）。既存環境の設計checkerは1回成功（564リンク・34言語pair）、空白検査も成功。固定sourceの独立全体レビューで記載の信頼前提内の実装欠陥はなし。以下の未実行／保留はworkerのfile-only作成時点で、後続coordinator検査ではありません。runtime受入ではありません。

[English](26-reservation-inspection.md) | [ホーム](../README.ja.md) | [実装計画](10-roadmap.ja.md) | [25 usage観測](25-local-usage-observations.ja.md)

**状態（2026-11-17）：実装と新規の自己完結unittestメソッドを正確に6つ作成済み、未実行（NOT EXECUTED）。** 3つの上限付きoffline増分の最初として、保持済み情報の検査だけを追加します。ファイルの読取・編集のみで、テスト、checker、実装import、build、network、Git操作、model呼出、process、service、公開は行っていません。この増分の実行・再現・独立レビュー・runtime受入は保留中です。過去の補助機能の検証は本APIの検証ではありません。

[実装](../src/ai_agent_scientist/admission/durable_handoff.py)は既存の[22 受領](22-durable-handoff-receipt.ja.md)、[23 予約と固定会計](23-local-budget-reservation.ja.md)、[24 outbox](24-local-status-outbox.ja.md)、[25 不変観測](25-local-usage-observations.ja.md)を接続します。観測記録／replayと照合の既存動作を再利用します。正本schemaとwire版は不変です。settlement・release・retry・dispatch・transport・権限resolverは追加しません。

## ローカルAPIと不変view

```python
snapshot = receiver.inspect_reservation('request-one')
page = receiver.inspect_reservations(after_request_id=None, limit=25)
if page.next_after_request_id is not None:
    following = receiver.inspect_reservations(
        after_request_id=page.next_after_request_id, limit=25)
```

`inspect_reservation`はscope内の依頼IDに厳密に対応する保持済み`ReservationSnapshot`を返し、予約がなければ`None`を返します。受領のみの行も`None`で、検査による予約の追加はありません。ページAPIはfrozen・slots付き`ReservationSnapshotPage`を返し、`entries`はtuple、次の位置は`next_after_request_id`です。frozen・slots付き`ReservationSnapshot`の内容は次の通りです。

| field | 保持情報の意味 |
|---|---|
| `receipt` | 未解決revision／stateを含む現在の`DurableReceipt` |
| `reservation` | 元の厳密束縛`DurableReservation` |
| `accounting` | frozenの`ReservationAccounting`。この予約の固定allocationと全量outstanding worker-seconds |
| `current_status` | 現在の受領revisionの`LocalStatusEntry`と別保存のローカルack。対応eventがなければ`None` |
| `latest_usage_observation` | この予約のローカル挿入sequenceが最大の元の`LocalUsageObservation`。観測がなければ`None` |

過去のoutbox履歴を補完しない旧DBではeventがない場合があります。検査はeventを合成せず、以前のrevisionのeventで代用しません。ackは受信者ローカルの記録で、遠隔配送や予約releaseを意味しません。

## 単一読取transactionとUNKNOWN

各APIは既存の`_transaction(write=False)`（`BEGIN`）を正確に1つ開きます。予約選択、現在の受領、固定envelope会計、現在revisionのevent／ack、最新観測を同じ接続・SQLite snapshotで読みます。1ページ内の全entryで一貫したviewを返し、別々の検査APIの合成で代用しません。別ページ・別呼出では後続commitが見える場合があります。既存のprivate SQLiteの信頼、path検査、timeout、commit／close失敗処理、所有者限定の例外原因という前提を維持します。[22](22-durable-handoff-receipt.ja.md)を参照してください。

最新とは`observed_at`が最大という意味ではなく、**最後に挿入された観測**です。古い観測の厳密replayでは挿入sequenceは進みません。観測は独立した事実で、検査は合計・最大usage選択・outstandingからのusage減算・消費推測を行いません。観測なしと`worker_seconds=None`の観測は区別し、どちらも既知usageではありません。以前に既知観測があっても最新UNKNOWNはUNKNOWNのままです。既知のゼロは元のflagを伴う整数ゼロです。超過量は変更しません。実行停止やcleanup既知からsettlementを推測しません。

会計は実際のsingletonの固定算術を読み、予約allocationとの整合を確認します。返すのは`allocation_worker_seconds`と`outstanding_worker_seconds`だけで、両方とも元のallocation全量です。**global合計は公開しません。** owner namespace、envelope ID、共有cap、settled floor、共有reserved合計、残容量、別scopeの予約一覧・件数を含めません。共有会計をscope合計と誤表示せず、別scopeの列挙や観測からの合計算出もしません。固定settled floorと共有reserved counterは変更しません。

## scope・上限・失敗

独立して信頼する受信者の`TrustedHandoffScope`がprincipal／project／recipientを固定します。保持済み予約・受領・status・観測のsenderも確認し、sender変更は別namespaceの作成ではなく`ReceiptScopeError`です。別principal／project／recipientにはそのscopeの行だけが見えます。候補workerはcaller・DB・evaluator・認可・予算書込の境界外に保ちます。scope宣言はcallerの責任で、本APIが認証するわけではありません。

依頼IDと非null cursorは厳密なbuiltinの空でない文字列で、UTF-8で1024 bytes以内、NUL・不正Unicodeを含まないものです。subclassや型変換は拒否します。cursorはSQLiteのbinary昇順の依頼IDを用いた排他的な探索位置で、挿入順・時刻順・global行番号ではありません。存在しない行のIDも使え、credentialにはなりません。`after_request_id=None`で開始します。`limit`は厳密なbuiltin整数`1..100`で、bool・subclassは拒否します。SQLは固定で入力を束縛します。

次ページ確認のため取得する予約行はscope内で最大`limit+1`、構築するsnapshotは最大`limit`です。同じtransactionで次の行がある場合だけ、返した最後の依頼IDを`next_after_request_id`に入れ、末尾・空ページでは`None`にします。過去cursorより前への新規挿入や既読行の変更を見るには`None`から再走査します。ページングは永続scan leaseや呼出間の固定DB viewではありません。内部のrequest／sequence indexで最新観測の探索を選択した依頼に限定し、DB全体の保持・操作数・disk予算は所有者の責任に残します。

束縛／会計不整合は`ReceiptConflict`、filesystem／SQLite失敗は`ReceiptStorageError`です。commit／close失敗で成功snapshotは返しません。後の行が失敗しても部分entryを成功として返さず、ページ全体が失敗します。読取は修復を行いません。期限後の保持metadata検査にもblobアクセス、依頼期限検査、現在権限lookup、新しい時計は不要です。snapshotは継続blobアクセス・作業・replay・予算・評価権限を与えません。

## 合成ローカルprojection

説明用の抜粋で、新しいwire objectや評価／usage受領ではありません。ID・数値はすべて合成です。省略した入れ子fieldは上記の定義に従い、Python APIはこの短縮JSONではなくdataclassを返します。

```json
{
  "request_id": "request-one",
  "receipt_revision": 2,
  "receipt_state": "reconciliation_required",
  "accounting": {
    "allocation_worker_seconds": 20,
    "outstanding_worker_seconds": 20
  },
  "latest_usage_observation": {
    "sequence": 2,
    "worker_seconds": null,
    "execution_stopped": false,
    "cleanup_known": false,
    "over_cap": null
  },
  "next_after_request_id": null
}
```

## 正確に6メソッドを作成済み・未実行

[専用の自己完結unittest](../tests/contracts/test_reservation_inspection.py)は実BlobStoreとprivate一時SQLite fixtureを使い、過去のテストをimportしません。

| ID | 作成した検査範囲 |
|---|---|
| I01 | 厳密lookup／再open、scope内順序付き上限ページ、cursor末尾、frozen view、global／owner非公開 |
| I02 | 不在・受領のみ・観測なし、現在event、blob不在でも保持情報のみで検査 |
| I03 | 既知ゼロとUNKNOWN、超過・cleanup flag、予約全量outstanding維持 |
| I04 | 直接照合、現在revision／ack、時刻より挿入順、古いreplay、観測を合計しないこと |
| I05 | principal／project／recipient分離、sender拒否、ID／cursor／limitの厳密型とbyte境界 |
| I06 | ページあたり単一読取transaction／接続、データ書込なし、後続行の会計不整合・実SQLite読取失敗で部分成功なし |

テスト実行と[設計checker](../scripts/check_design.py)によるリンク・言語pair・JSON例・状態整合の検査は保留中で、file-only指示により**実行していません**。runtime・復旧・再現・耐久性・独立レビューの結果は主張しません。後続増分は今回の範囲外です。

# 24 同じtransactionで記録する受信者ローカル予約状態outbox


**outbox coordinator検証（2026-11-17）：O01〜O06はofflineで1回成功、0.046秒。必須設計checkerも1回成功（504 links、32言語pair）。元の選択workerは600秒timeout、task_complete／finalなし、完了UNKNOWN、再実行なし。以下の作成済み・未実行はworkerのみの活動履歴で、現在のcoordinator検証状態ではありません。live受入は主張しません。**

日本語 | [English](24-local-status-outbox.md) | [ホーム](../README.ja.md)

**状態（2026-11-17）：実装と新規offline unittestシナリオを正確に6つ作成済み。未実行。** レビュー済みcommit `d3245b42dafb0438ebd5a0065e930a3f759004f5`を基点にしています。ファイル読取・編集のみで、test・checker・実装import実行・build・network・install・service・model・研究・dispatchは行っていません。runtime受入・再現・独立レビュー・遠隔配送・耐久性実測は主張しません。以前の部品の結果は今回の検証ではありません。

P1の狭い増分として、[23 予約](23-local-budget-reservation.ja.md)を実際の[22 受領](22-durable-handoff-receipt.ja.md)と[durable_handoff.py](../src/ai_agent_scientist/admission/durable_handoff.py)のtransaction接続点で拡張します。[11](11-harness-boundaries.ja.md)のローカルoutbox記録部分のみです。既存APIと戻り値の型を維持します。この基点の受領／予約APIは`record_and_reserve`ではなく`reserve`です。正本受領の未解決状態はrevision 1の`recorded`とrevision 2の`reconciliation_required`の2つのままです。

## 原子的な事実と安定identity

受領の作成／結合、予約保存、固定worker-seconds envelopeのchargeと**同じ既存の`BEGIN IMMEDIATE` transaction**で、不変の`LocalStatusEvent`を1つ追加します。revision 1は`reservation_retained`のみを記述します。`require_reconciliation` CAS成功時は、**一致する保存予約が既にある場合のみ**、受領更新と同じtransactionでrevision 2の`reconciliation_required`を追加します。受領のみの`record`や照合は予約もeventも作りません。eventは予約保持／照合のみを記述し、受付・dispatch・attempt・完了・検証状態を付与しません。

一意keyは`(principal, project_id, recipient, request_id, receipt_revision)`で、`(budget_reservation_ref, receipt_revision)`も一意です。信頼するsender mapping、予約参照、検証済み厳密バイトの依頼digest、worker-seconds、作成時刻を保持します。senderは`TrustedHandoffScope`と照合し、sender変更で別namespaceを作りません。`event_id`はこの正本DB内で昇順の整数で、wire identityやcredentialではありません。

`reserve` replayも23の現在のloader／binding／authority検査を全て行い、元の予約と現在の受領を返します。inspectionで得るeventは同じで、重複・時刻reset・再charge・ack resetはありません。照合後も両eventを維持します。SQL一意制約とwriter直列化で重複を防ぎ、event UPDATE／DELETE triggerで変更を拒否します。ackは別tableです。

以前のDBを開くと空のoutbox tableを作りますが、履歴を埋めません。古い保存予約を現在の権限で新たにreplayすると、そのtransactionで欠けている**現在revision**のeventを呼出時刻で追加できます。後の照合も現在revisionを記録できます。欠けた過去eventや配送を推測しません。ローカルschema追加であり一般的なmigration／修復機能ではなく、正本schema／wire版は変更しません。

## 上限付きinspectionとack CAS

```python
pending = receiver.inspect_status_events(after_event_id=0, limit=25)
all_local = receiver.inspect_status_events(limit=25, pending_only=False)
ack = receiver.acknowledge_status_event(
    pending[0].event.event_id, expected_ack_revision=0, now=fresh_utc_now,
)
```

inspectionはfrozenの`LocalStatusEntry(event, ack_revision, acknowledged_at)`のtupleを`event_id`昇順で返します。独立して信頼するprincipal／project／recipientに限定し、sender mappingも確認します。保存metadataのみを読むためauthority／access期限後も使えますが、blob accessや継続権限は付与しません。`limit`は正確なbuiltin整数`1..100`、`after_event_id`は正確なbuiltin整数`0..2**63-1`、`pending_only`は正確なbool（既定値true）で、bool／整数subclassを整数として受理しません。cursorは指定IDより後を返すだけで消費やackを行いません。中断後の古いpendingは0から読み直します。scope間でIDが飛ぶことは正常です。

ackなしはrevision 0、時刻nullです。`acknowledge_status_event`は正の上限付き正確な整数event ID、正確な期待ack revision 0、event作成以降の正確なUTC datetimeを要求します。`BEGIN IMMEDIATE`でscope内lookupとrevision 1のack追加1回を直列化します。欠落・他scope・古い／反復ackは`ReceiptRevisionError`、sender mapping変更は`ReceiptScopeError`です。ackはevent単位で、依頼全体cursorや状態上書きではありません。revision 2を先に、revision 1を後にackしても受領は後退せず、別pending／scopeを変更しません。

ackは**受信者ローカルの記録のみ**です。遠隔受領／配送を保証せず、UNKNOWN解決・予約release・会計変更・settlement／refund・retry／dispatch許可を行いません。sender・daemon・polling loop・transport・callback・配送attempt・遠隔ack実装はありません。

## 合成ローカルsnapshot

説明用JSONで正本wire objectではありません。APIはfrozen dataclassを返します。以下のidentifierとdigestは合成値です。

```json
{
  "event": {
    "event_id": 1,
    "principal": "trusted-local-principal",
    "project_id": "p1",
    "recipient": "ctf",
    "request_id": "r1",
    "sender": "scientist",
    "budget_reservation_ref": "b1",
    "request_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "receipt_revision": 1,
    "status": "reservation_retained",
    "worker_seconds": 20,
    "created_at": "2026-11-17T12:00:00.000000Z"
  },
  "ack_revision": 0,
  "acknowledged_at": null
}
```

## 失敗・上限・未解決情報

event書込失敗は実行中の受領／予約／会計transaction全体、または照合遷移全体をrollbackし、孤立eventを残しません。ack書込失敗はそのtransactionのみrollbackします。commit後のcommit／close errorは観測が不確実です。DBを保存し、reopenして元identityをinspectionしてから現在の検査を通じてreplayします。予約応答喪失でもchargeとpending eventを保持します。ローカルack応答喪失時はcommitの有無でrevision 0 pendingまたはrevision 1 ack済みとなり、どちらも予算をreleaseしません。分散atomicityや電源断保証は主張しません。

固定metadataのみを保存し、identifierは既存の1024 UTF-8 bytes、依頼digestは64文字、worker-secondsは符号付き63bit範囲です。受領revisionが2つで一意制約があるため、予約あたりeventとackはそれぞれ最大2行、1pageは最大100件です。DB全体quota・削除／reset／release APIはなく、ownerが総行数・disk／journal容量・操作数を予算化します。[22 private SQLite前提](22-durable-handoff-receipt.ja.md)を維持し、候補workerはcaller・scope・DB／schema／trigger・authority・evaluator・予算書込境界を制御できません。敵対的DBや同一UID攻撃者への防御ではありません。

過去のUNKNOWN結果は未解決のままです。この増分は通貨計測・照合・settlement／refundを行いません。完全な受付・通貨会計・lease／fencing・論理／JCS同一性・dispatch・配送は対象外です。既存runtime／認証／設定／既定値・guard・reviewer・無効な例は変更しません。

## 正確に6つの作成済みシナリオ — 未実行

[専用unittestファイル](../tests/contracts/test_local_status_outbox.py)は実際の一時BlobStore／SQLiteを使う自己完結のファイルで、過去testをimportしません。

| ID | 作成した範囲 |
|---|---|
| O01 | 実loader → 受領 → 予約、対応eventは正確に1つ |
| O02 | replay／reopenでidentity・時刻・会計を維持 |
| O03 | event書込失敗注入で新規／既存envelope transaction全体をrollback |
| O04 | 照合の次event・失敗rollback・古いCASで孤立eventなし。受領のみの照合は予約を作らない |
| O05 | 上限付き昇順scope内inspection、scope内ack CAS、不変event、scope間／状態の後退なし |
| O06 | commit ack喪失／reopenで予約とpendingを保持。失敗／喪失したローカルackも予算をreleaseしない |

6つ全て作成済み・未実行です。ファイルレビューでlink・言語pair・JSON・状態整合を考慮しましたが、ファイルのみの指示に従い[設計checker](../scripts/check_design.py)と全runtime検査は**未実行**です。成功結果は主張しません。

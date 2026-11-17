# 25 不変の受信者ローカルworker-seconds観測

> Coordinator検証（2026-11-17、round3のみ）：新規U01〜U06の6シナリオが1回成功（1.183秒）、既存venvの設計checkerも1回成功（534リンク、33言語pair）。独立レビューは保留中です。以下の作成済み／未実行の文はworkerのfile-only作成時点の履歴で、現在のcoordinator検証状態ではありません。round2の元の生の検証出力は未入手で、round3からその検証を推測しません。

日本語 | [English](25-local-usage-observations.md) | [ホーム](../README.ja.md) | [ロードマップ](10-roadmap.ja.md) | [24 ローカルoutbox](24-local-status-outbox.ja.md)

**作成状態（2026-11-17）：実装と自己完結のunittestメソッドを正確に6つ作成済み。未実行（NOT EXECUTED）。** Scientist round3は、coordinatorから指定された独立source review済みround2 `bf4743970dc48e0e89e2717a2e07c2591c8db129`を基点とします。そのレビューは基点に対するもので今回の増分ではありません。ファイル読取・編集のみで、test・checker・実装import・build・model呼出・network・git変更・install・service・dispatchは行っていません。coordinator検査は保留中です。round3の実行・再現・独立レビュー・runtime受入・耐久性実測は主張しません。

P1の狭い増分として、[23 保存予約](23-local-budget-reservation.ja.md)、既存の[22 照合遷移](22-durable-handoff-receipt.ja.md)、[24 ローカル状態outbox](24-local-status-outbox.ja.md)を[durable_handoff.py](../src/ai_agent_scientist/admission/durable_handoff.py)内で接続し、観測のみを保存します。**これらのAPIでは全予約を常に全量outstandingのまま保持し、固定envelopeのsettled floorとreserved counterを一切変更しません。** 使用量0が既知、実行停止を独立観測済み、cleanup既知でもreleaseしません。settlement・refund・完了・受付・process計測・認証実装はありません。

## 独立して信頼するローカルcaller

callerはprincipal／project／sender／recipient mappingを独立に確立し、同じ正本private DBを選び、使用量・実行停止の有無・cleanup既知の有無を観測します。`TrustedHandoffScope`はcallerの宣言であり認証ではありません。候補workerはcaller・観測・mapping・DB／schema／trigger・認可・予算writer・evaluatorを制御できません。wire sender文字列・報告・参照は独立証拠ではありません。任意senderの観測API・wire拡張・transport・callback・process検査はありません。

信頼するlocal process、journal／sidecar pathを含む[22 private SQLite前提](22-durable-handoff-receipt.ja.md)を維持します。不変triggerはこのschemaを通じた誤変更を拒否しますが、敵対的DBや同一UID攻撃者への防御ではありません。期限後のローカルmetadata保存に現在のauthority／blob lookupは不要ですが、継続access・権限を付与しません。`reserve`の現在のbinding／authority検査は維持します。

## 明示的ローカルAPIと厳密replay

```python
observation = receiver.record_usage_observation(
    'observation-one', request_id='request-one',
    budget_reservation_ref='reserve-one', request_sha256=original_envelope_sha256,
    expected_revision=1, worker_seconds=None,
    execution_stopped=False, cleanup_known=False,
    observed_at=original_observation_utc,
)
page = receiver.inspect_usage_observations(after_sequence=0, limit=25)
```

受信者の固定trusted scopeも束縛に含まれます。既存予約は、指定した予約参照・request ID・元の厳密バイトenvelope digest・senderを含む全scopeと一致し、厳密に対応する保存受領も存在する必要があります。受領のみの行には観測を付けず、予約を捏造しません。予約参照やdigestは権限を付与しません。論理／JCS同一性は変更しません。

identifierは既存の正確なbuiltin非空文字列、NULなし、最大1024 UTF-8 bytesを再利用し、digestは小文字hex正確に64文字です。`expected_revision`は既存の上限付き正確な整数guardを使い、新規観測は現在の受領revision（1または2）と一致する必要があります。`worker_seconds`はbool／subclassを除く正確なbuiltin整数`0..2**63-1`、またはUNKNOWNを表す`None`です。独立観測の2つのflagは正確なboolです。それぞれ別の事実で、一方から他方や使用量の既知を推測しません。

`observed_at`は正確なUTC-aware datetime（`tzinfo is timezone.utc`）で、既存formatterでmicrosecond精度のUTCへ正規化します。**retryの新しい時計ではなく、不変の観測内容**です。新規観測は現在受領の`updated_at`より前にはできません。APIは時計を取得せず、callerの時刻や事実の真実性・新しさを検証しません。

`observation_id`はこの正本DB全体で一意です。厳密replayはscope・予約／依頼／digest束縛・期待revision・使用量・両flag・導出した超過flag・正規化観測時刻の全内容を比較し、元のlocal挿入sequenceを含むfrozen `LocalUsageObservation`を返します。現在revision検査より前に比較するため、自身の遷移で受領がrevision 2へ進んだ後も、元のrevision 1観測をreplayできます。**retryには元の時刻と期待revisionを再利用します。** どちらかを変更すると他の内容が同じでも`ReceiptConflict`です。新しい観測IDで古いrevisionを指定すると`ReceiptRevisionError`、誤scopeは`ReceiptScopeError`、予約欠落や予約／依頼／digest不一致は`ReceiptConflict`です。競合で古い内容を更新しません。

## 同じtransaction・既存遷移・既存event

既存の`BEGIN IMMEDIATE`で束縛lookup・観測ID比較・revision検査・既存`require_reconciliation` CAS／outbox経路・観測挿入を直列化します。既存CAS本体を内部で共有し、nested transactionは開かず、public APIのguard／戻り値は変更しません。記録済み受領は`recorded` revision 1 → `reconciliation_required` revision 2のみを許し、対応する既存予約eventを同じtransactionで追加します。遷移／eventの後に観測を挿入するため、遅い観測書込失敗でも両方rollbackします。

既に照合必須の受領では、**正確な現在revision 2**へ束縛した新観測を、再遷移・受領時刻変更・outbox event追加なしで保存します。観測以前に直接照合した受領も含みます。厳密replayは何も書きません。観測完了・cleanup完了・settlement eventはありません。既存event ackは変更せず、予約releaseもできません。古いDBを開くと空の内部観測table／index／triggerを追加しますが、過去観測の補完やevent修復はしません。

既知使用量は超過も含め**変更せず**保存します。`over_cap`はretryとevaluation／cleanup allowanceを含む、その予約の固定worker-seconds全量との比較であり、process制限判定やenvelope空き容量との比較ではありません。UNKNOWNは`worker_seconds=None`と`over_cap=None`を保持し、0や上限内へ置換しません。複数観測は独立記録で、加算debit・最新値によるsettlement・使用量合算許可ではありません。どの場合も元予約を全量outstandingに保ちます。

commit前の検査・event書込・観測書込失敗は観測／遷移／outboxの実行中transactionをrollbackします。既存SQLite／filesystem errorは`ReceiptStorageError`です。commit後やclose時のerrorではcommit済みの可能性が残ります。DBを保存してreopenし、元の厳密内容でinspection／replayし、不在と推測しません。電源断・敵対的file・backup・migration・分散atomicityは保証しません。

## 上限付きinspectionと合成保存snapshot

`inspect_usage_observations`は受信者のprincipal／project／recipient scope内でsender mappingも確認し、frozen観測のtupleを返します。local挿入`sequence`昇順、exclusiveな`after_sequence` cursor（正確なbuiltin整数`0..2**63-1`）、`limit`は`1..100`で既存上限を再利用します。観測時刻が全行で昇順とは限らず、挿入sequenceがinspection順序です。scope間でIDが飛ぶことは正常です。inspectionは消費／ackせずblob・権限を提供しません。sender指定scope／query fragmentや無制限read APIはありません。

以下はローカルmetadataの説明用JSONで、正本wire objectや保護したusage receiptではありません。digestは合成値で、Python APIはfrozen dataclassを返します。この例で観測値が21でも元の全予約量20を維持します。

```json
{
  "sequence": 1,
  "observation_id": "observation-one",
  "principal": "trusted-local-principal",
  "project_id": "p1",
  "recipient": "ctf",
  "request_id": "r1",
  "sender": "scientist",
  "budget_reservation_ref": "b1",
  "request_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "expected_revision": 1,
  "worker_seconds": 21,
  "execution_stopped": true,
  "cleanup_known": true,
  "over_cap": true,
  "observed_at": "2026-11-17T12:00:01.000000Z"
}
```

fieldと1page最大100件には上限がありますが、予約あたり観測数やDB総量は制限しません。trusted ownerが操作数・disk／journal容量・保持を予算化します。pruning・delete・release・reset APIはありません。過去のUNKNOWN結果はUNKNOWNのままです。通貨計測・照合を行いません。正本schema／wire版・guard・認証・runtime／既定値・reviewer・evaluator・知識昇格権限は変更しません。

## 正確に6つの作成済みメソッド — 未実行

[専用の自己完結unittestファイル](../tests/contracts/test_local_usage_observations.py)は、実際の一時BlobStore／SQLite予約を使う既存fixture形式を再利用し、過去testのimportや隠れたcaseのparameter化は行いません。

| ID | 作成範囲 |
|---|---|
| U01 | 実予約観測／reopen、厳密束縛、上限付きscope内昇順inspection。現在revisionの新観測で遷移／event追加なし |
| U02 | revision進行後の厳密replay、内容／時刻／revision変更の競合、UPDATE／DELETE不変性 |
| U03 | cleanup不明・使用量UNKNOWN・既知0でも全予約とfloorを維持 |
| U04 | 予約／依頼／digest／scope不一致、古いrevision、型上限・時計拒否で観測なし |
| U05 | 決定的な別2接続の競合：SQLite writer lock保持、敗者の上限付きtimeout、古い敗者と勝者厳密replay。遷移1回 |
| U06 | 符号付き63bit最大の超過値を変更せず保持。event／遅い観測失敗注入で観測／遷移／outboxをrollback |

6つ全て作成済み・未実行です。file-only指示に従いtest・import・build・[設計checker](../scripts/check_design.py)は実行していません。coordinatorによるruntime／contract／recovery／再現性およびlink／言語pair／JSON／状態検査は保留中で、source読取だけでは結果を確立できません。以前の成功検査は対応する過去の増分のみに適用されます。

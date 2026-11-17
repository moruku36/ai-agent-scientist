# 23 ローカル永続ワーカー秒予約の前提部品

日本語 | [English](23-local-budget-reservation.md) | [ホーム](../README.ja.md)

**状態（2026-11-17）：実装済み。R01〜R10の10シナリオが1回オフライン成功（0.082秒）。** 選択したworkerがファイルを作成し、coordinatorが全差分をレビューして対象テストを1回実行しました。workerの元実行は600秒でtimeoutし、task_completeとdurable finalは得られず、worker完了は未確認です。再実行はしていません。受入・再現・独立レビュー・実測した耐久性は主張しません。

P1の狭い前提部品として、実際の[22 永続受領](22-durable-handoff-receipt.ja.md)のtransactionへ、実際の[21 束縛loader](21-handoff-payload-binding.ja.md)と[17 純粋算術](17-budget-preflight.ja.md)を接続します。対象は**worker-secondsのみ**。構成・正本schema／wire版・無効な例・runtime設定・過去予算を変更しません。過去の予算・未解決結果を変更しません。

## 所有権と固定namespace

[ソース](../src/ai_agent_scientist/admission/durable_handoff.py)に、frozen／slotsの`WorkerSecondsEnvelope`・`WorkerSecondsAuthority`・`DurableReservation`・`ReservedHandoff`、`ReservationRefused`、`DurableHandoffReceipts.reserve`を追加します。既存の`record`・`inspect`・照合APIは受領のみの動作・戻り値を維持します。

独立した信頼する受信者側callerがprivateな正本DBを選び、このmoduleの外でprincipalを認証し、**毎回**現在のauthority・binding・store・新鮮なUTC時刻を渡します。認証実装や現在権限serviceへのlookupはありません。候補workerはcaller・mapping・DB・envelopeを制御できません。参照はlookup keyでありbearer credentialではありません。

正確なbuiltin dictのkeyは次です。

```python
(principal, project_id, sender, recipient, authorization_ref, budget_reservation_ref)
```

最初の4項は信頼する`TrustedHandoffScope`由来で、project／endpointと両参照を、新たに検証した実依頼に照合します。一致するkeyには正確な`WorkerSecondsAuthority`が必要です。`available is True`で、正確なUTC `expires_at`が`now`より後であることを毎回確認します。mappingなし・失効・期限切れは重複も拒否します。callerは独立した現在情報を更新し、SQLite lock待ちを含む呼出全体でauthority・binding・store変更を直列化します。古いcaller情報や不正な時計は一般には検出できません。

**正本DB一つに固定envelopeは一つ**です。同じ予算の正当なprincipal／project／sender／recipient／参照は全て同じcounterを使います。singleton行は`owner_namespace`・`envelope_id`・cap・settled floor・4つの算術入力を束縛します。最初の予約成功後はreopenを越えて不変です。principal・sender・参照・envelope名を変更しても新しい容量は作れません。共有予算には同じDBを使い、別ファイル選択・行削除・古いDBの復元で会計を迂回してはいけません。予算所有namespaceは受領identityとは独立で、sender入力から導出しません。reset・migration・refund操作はありません。

信頼するcallerがpayloadとは独立に固定の均一allocationを供給します。

`required = (planned_attempts + max_retries) * per_attempt_seconds + evaluation_cleanup_seconds`

実際の純粋preflightを再利用します。retryは全体枠で、評価／cleanupも含みます。異なる予約はそれぞれ同じ固定allocationを消費します。**protocol／planの意味的resolverはありません**。payload内のcapやenabledは権限にならず、allocationが実計画を満たす証拠にもなりません。算術入力・中間値はSQLiteの非負signed-63範囲`0..2**63-1`の正確なbuiltin intとし、cap・attempt数・per-attempt秒は正です。bool・subclass・型変換を拒否し、SQL前にoverflowを保守的に拒否します。settledはcap以下です。

## ローカルAPIと保存例

```python
envelope = WorkerSecondsEnvelope(
    owner_namespace='budget-owner', envelope_id='fixed-study',
    cap_worker_seconds=50, settled_worker_seconds=10,
    planned_attempts=1, max_retries=1, per_attempt_seconds=8,
    evaluation_cleanup_seconds=4,
)
current_authorities = {
    (scope.principal, scope.project_id, scope.sender, scope.recipient, 'a1', 'b1'):
        WorkerSecondsAuthority(envelope, True, authority_expires_at),
}
result = receiver.reserve(
    request_store, verified_envelope_sha256,
    payload_store=payload_store, bindings=current_payload_bindings,
    authorities=current_authorities, now=fresh_utc_now,
)
# result.receipt: 現在の未解決DurableReceipt
# result.reservation: 不変の保存済みDurableReservation
```

次はローカルmetadataの例で、**新しいwire schemaや受付受領ではありません**。実際に検証する依頼にもa1／b1と一致するendpointが必要です。この公開例に実権限はありません。

```json
{
  "budget_reservation_ref": "b1",
  "authorization_ref": "a1",
  "principal": "trusted-local-principal",
  "project_id": "p1",
  "recipient": "ctf",
  "request_id": "r1",
  "sender": "scientist",
  "request_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "worker_seconds": 20,
  "recorded_at": "2026-11-17T12:00:00.000000Z"
}
```

この算術例ではsettled 10と異なる予約20を2つでcap 50に達します。正当な別scopeも同じsingletonを消費します。cap・floor・allocationは固定で、live settlement台帳ではありません。

## 接続したtransactionと重複

重複を含む全`reserve`で実loaderを新たに実行します。上限付きSHA-256検証済みの厳密envelopeバイト、厳格JSON／依頼検査・期限、現在のpayload metadata／アクセス、実際の上限付き検証payload読取を通ります。payloadバイトは破棄します。同一性は元の厳密バイトのままで、空白・key順・transport変更を正規化しません。docs11の部分的ローカルprofileであり、**論理JCS同一性や認証済み受付ではありません**。

一つの`BEGIN IMMEDIATE`で、固定envelope・参照／依頼衝突・残容量を確認し、受領の作成／接続・予約作成・singleton加算を原子的にcommitします。条件は`settled_floor + retained_reservations + new_charge <= fixed_cap`です。権限なし・容量不足・不正入力・衝突では受領・予約・会計行を作りません。constructorによるtable初期化のみ許容し、予算行は作りません。

`budget_reservation_ref`は正本DB全体でauthorization ref／受領scopeを越えて一意です。authorization ref・scope／sender・request ID・厳密envelope digest・chargeと永久に束縛します。一つの受領keyに予約は一つで、envelope digestも全体で一意のため、同じバイトを別principalで再予約できません。別作業への固定参照再利用、同じ依頼の参照変更、固定envelope／allocation変更は衝突です。異なる依頼には異なる固定予約参照を使います。全く別のidentity／バイトで発行した依頼の論理重複を検出するものではありませんが、受けた依頼は全て共有capを消費します。

厳密な重複は容量を使い切っていても現在の未解決受領と元の予約を返し、再加算・timestamp／revision resetをしません。現在権限・アクセス・期限は再確認します。`record`単独では予約しません。受領のみの`recorded`行には、同じ新規検証済みバイト、既存の依頼／参照／digest予約衝突なし、他scopeに同digest受領なしの場合のみ、原子的に予約を接続できます。受領のみの`reconciliation_required`行は曖昧なため拒否します。過去の実作業有無を推測しません。

照合は受領revision／stateのみを変更し、全chargeを維持します。UNKNOWNは未解決利用で、**refund・retry・dispatch APIはありません**。settlement・release・cancel・completion・outbox・runner・admissionも追加しません。`ReservedHandoff`は保存metadataであり作業／replay権限になりません。

## 失敗・信頼条件・残課題

[22のprivateな正本SQLite信頼条件](22-durable-handoff-receipt.ja.md)をそのまま適用します。owner専用POSIX path、信頼するschema／trigger／process／ancestor／sidecar、敵対DB防御なし、ファイル置換なし、1秒lock timeout、`synchronous=FULL`です。固定SQLとbound値のみを使います。DBにはprivateな会計／identity／digest metadataのみ保存し、payload／envelope本体やcredentialは保存しません。ownerによる行数／disk制限は別途必要です。

commit／close失敗は成功を返しません。可能ならactive transactionをrollbackしますが、commit後の応答喪失では全chargeが残り得ます。DBを保存して確認／照合し、失敗を未利用容量と判断しません。後の`reserve`も全ての新しい検査を通り、保存metadataのみ返し、replay権限は付与しません。曖昧な結果でもrefund／resetはありません。commit／reopenは電源断耐久性の実証ではありません。この戻り値からdispatchを構築してはいけません。

金額・token・GPU・memory／disk・経過時間強制・live settlement・fencing・run／manifest／protocol照合は未実装です。完全なSCI-01／04／05／20予約／受付の受入や研究runtimeではありません。一般的なplan mapping・JCS・認可backend・protocol変更はありません。

## シナリオ：1回オフライン成功

[自己完結したscenarioファイル](../tests/contracts/test_budget_reservation.py)は新規10method以内で、過去testをimportしません。

| ID | 作成した対象 |
|---|---|
| R01 | 実読取・純粋算術呼出・独立した現在scope権限／参照照合 |
| R02 | settled baseline・境界／枯渇・別依頼・初回容量不足の無書込 |
| R03 | 正当な別scopeの共有容量・namespace／envelope変更によるreset拒否 |
| R04 | 厳密バイト・参照変更・固定参照衝突・別principal alias |
| R05 | 厳密な受領のみへの接続・reopen／重複・照合状態とcharge維持 |
| R06 | reopen後のowner／envelope／cap／floorと全算術入力の不変性 |
| R07 | 不正型・exact型・overflow・signed-63境界・部分書込なし |
| R08 | 初回／重複の失効・期限・現在mapping／アクセス・改変payload実読取 |
| R09 | 後段insert失敗rollback・既存charge維持・commit応答喪失とcharge保持 |
| R10 | 別接続の実並行重複と容量競合transaction |

coordinatorが許可枠で対象scenarioを1回実行し、10件全て成功（0.082秒）しました。必須設計／schema検査の結果はcoordinatorの記録に別途保存します。以前の補助の結果は履歴であり、この拡張の検証結果ではありません。

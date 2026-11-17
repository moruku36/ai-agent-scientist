# 27 保守的な受信者ローカル復旧triage

[English](27-recovery-triage.md) | [ホーム](../README.ja.md) | [実装計画](10-roadmap.ja.md) | [26 予約検査](26-reservation-inspection.ja.md)

**状態（2026-11-17）：ソース・新規の専用自己完結unittestメソッドを正確に6つ・文書を作成済み。未実行（NOT EXECUTED）。** 3つの接続された上限付きoffline増分の2番目です。checkoutのファイル読取／編集のみ行いました。テスト・checker・実装import・build・network・Git操作・model呼出・公開・process実行は行っていません。coordinator検査・実行・再現・独立レビュー・runtime受入は保留中です。過去の検証bannerは過去の増分だけが対象です。

[recovery_triage.py](../src/ai_agent_scientist/admission/recovery_triage.py)は、[26の実際の検査API](26-reservation-inspection.ja.md)を使い、保持された[22受領](22-durable-handoff-receipt.ja.md)・[23予約](23-local-budget-reservation.ja.md)・[24ローカルstatus／ack](24-local-status-outbox.ja.md)・[25観測](25-local-usage-observations.ja.md)を接続します。証拠の不足を保守的に記述します。**受付・readiness・dispatch・settlement・認可・process制御・復旧実行器ではありません。** retry・完了・releaseの判断は発行しません。正本wire版・schema・既存receiverの動作は不変です。

## 小さいローカルAPI

```python
report = classify_reservation(snapshot, scope=independently_trusted_scope)
report = inspect_recovery_triage(receiver, 'request-one')
page = inspect_recovery_triages(receiver, after_request_id=None, limit=25)
```

`classify_reservation`は純粋かつ決定論的で、storage・現在時刻取得・process・network・権限lookupを行いません。厳密な`ReservationSnapshot`と`TrustedHandoffScope`が必要です。返す`RecoveryTriageReport(snapshot, reasons)`はfrozen／slots dataclassです。`snapshot`は検査した入力全体で、元の完全な`DurableReservation`・受領・allocation会計・現在status／ack・最後に挿入された観測を保持します。会計情報の省略summaryではありません。action／disposition欄はありません。

接続関数は厳密な`DurableHandoffReceipts`のみを受け、duck typingのadapterやcandidate reportは受けません。既存のtrusted scopeを内部で読みます。単件関数は実際の`inspect_reservation`を正確に1回呼び、欠落／受領のみなら`None`です。これは予約はあるが観測がない場合とは異なります。page関数は`inspect_reservations`を正確に1回呼び、そのpageを分類します。個別読取の組合せにはしません。frozen／slotsの`RecoveryTriagePage(entries, next_after_request_id)`は上限付きtupleとcursorを保持します。APIが生成するreportは重複しない固定reason文字列が最大9つ、pageは最大100件です。dataclassの直接構築は検証／出所確認APIではありません。

## 決定論的順序の機械可読reason

| Reason | 保持されたviewでの意味 |
|---|---|
| `reservation_fully_outstanding` | 常に存在。allocationとoutstandingはいずれも予約全量 |
| `receipt_recorded` / `receipt_reconciliation_required` | 厳密な未解決受領状態。作業権限ではない |
| `current_status_missing` | 現在revisionのeventなし。古いeventで代替しない |
| `local_ack_unknown` | 現在statusがなく、そのローカルackは記述できない |
| `local_ack_pending` / `local_acknowledged` | 現在eventのローカルack revisionが0／1。transport／遠隔配送の主張なし |
| `no_observation` | 保持観測なし。UNKNOWN観測がある場合とは異なる |
| `latest_insertion_view_only` | 観測あり。ローカル挿入順はviewを選ぶだけ |
| `usage_unknown` | 観測なし、またはusageが`None`。ゼロへ変換しない |
| `usage_known_zero` / `usage_known_positive` | 保持整数usage。ゼロを明示し、正数はallocation超過もあり得る |
| `execution_not_independently_stopped` | 観測なし、または独立に供給されたstopped flagがfalse |
| `cleanup_unknown` | 観測なし、または独立に供給されたcleanup-known flagがfalse |
| `observed_over_cap` | 保持された既知usageがこの予約の固定allocationを超過 |

順序は予約、受領、status／ack、観測の有無／view、usage、停止の不足、cleanupの不足、超過です。status欠落ならmissing-statusとunknown-ackの両方が付きます。全reasonはローカルの保持事実／不足を記述し、不足reasonの不在を肯定的な復旧判定にはしません。既知ゼロ・両flagがtrue・ローカルack済みでも予約全量がoutstandingです。共有合計・owner識別情報・cap・settled floor・残容量・観測合計は返さず計算もしません。

## 厳密な検証とtrust

不正形式／内部不整合snapshotはsummaryを返す前に値を含まない`InvalidRecoverySnapshot`で拒否します。厳密なdataclass／builtin型でsubclass・暗黙変換・bool整数・独自等値比較objectを拒否します。識別子は空でない厳密な文字列、UTF-8最大1024 bytes、NUL／不正Unicodeなしです。digestは小文字16進64文字です。整数は`0..2**63-1`、allocationとローカルidentityは正数、flagは厳密なboolです。保存時刻は実在する暦値の正規microsecond UTC文字列で、現在時刻や期限判定は追加しません。

受領／予約／status／観測のprincipal・project・recipient・request・sender・envelope digestを相互および独立trusted scopeへ束縛します。予約ref、認可／message／観測識別子、payload digest形式、revision／stateの組、allocation／outstanding全量一致、現在statusのrevision／種別／量、ack revision／時刻の組と順序を検査します。観測は受領revision 2、元expected revision 1または2、有効sequence／identity、独立flag、UNKNOWN／over-capの組、厳密な超過比較が必要です。revision 1の観測時刻は照合遷移時刻と同じ、revision 2の観測はそれ以前になれません。予約／eventの作成時刻から、独立caller時刻や既存行への紐付け／backfillをまたぐ順序は創作しません。

pageでは厳密なcontainer／上限、cursorより後の厳密なbinary UTF-8 request-ID順序、予約／digest／message／event／観測identityの非重複、最終行へのcursor束縛も検査します。後続行1つの不正でも部分成功pageは返しません。receiverのscope／会計／storage例外はそのまま伝えます。storage修復や、失敗をUNKNOWN成功へ置換する処理はありません。

これらは**内部不整合のある偽造**を拒否し、整合した架空履歴を認証するものではありません。digestはバイト同一性であって出所証明ではありません。純粋分類ではSQLite由来や観測内容の真実性は証明できません。独立管理されたreceiver／scope／DB／観測による接続検査を使い、caller・import・receiver instance／method・scope対応・schema・SQLiteファイルをcandidate制御外に保ちます。既存receiverの非公開ローカルtrust前提が適用され、frozen dataclassは同一UIDの敵対コードを隔離しません。wire受付・認証・署名検証・評価受領はありません。

## 並行性・保持・復旧の限界

接続呼出ごとに既存receiverの読取transactionを1つ使います。分類はtransactionを閉じた後の不変snapshot上で行い、並行commitでviewがすでに古くなっている場合があります。別呼出／pageは独立です。request-ID seekは永続leaseでもpage全体を固定するscanでもありません。変更行やcursorの後方へ挿入された行を見るには`None`から再走査します。接続層は書込・ack・CAS・migration・追加snapshot lookupを行いません。

latestは**ローカル挿入sequence最大**であり、権威ある最新の真実・最大時刻・累積計測・観測全体の最大値・矛盾事実の照合ではありません。古い完全一致replayは挿入順を進めません。後から挿入されたUNKNOWNは、以前に既知usageがあってもUNKNOWNです。reportはreceiverが選んだ観測だけを保持し、完全な観測履歴は主張しません。停止／cleanup flagは保持された独立観測で、live process検査ではありません。fencing・取消・資源計測・lease照合・backup／restore・DB間identity保証・分散復旧は未実装です。

巻戻しはtriageの利用を止め、既存検査APIへ戻り、受領・未解決予約・event・ack・観測をすべて維持します。戻すtriage書込も新schemaもありません。エラー時は正本DBを保持して独立調査し、resetや失敗／欠落を予算減額と扱いません。DB総量・操作／disk予算・非公開report管理・保持方針はownerの責務です。pruning・削除・export・schedule・公開経路は追加しません。

## 合成projection 1例

英語版と同じ単一の説明用ケースです。省略したローカル表示で、**新しい正本wire／schema objectでも認証観測でも保護検証受領でもありません。** 全値は合成です。実際のPython reportは完全な予約を含む全nested snapshot欄を保持します。この表示だけscope・束縛・時刻を省略しています。

```json
{
  "request_id": "request-one",
  "reservation_worker_seconds": 20,
  "outstanding_worker_seconds": 20,
  "latest_observation_id": "observation-unknown",
  "latest_worker_seconds": null,
  "reasons": [
    "reservation_fully_outstanding",
    "receipt_reconciliation_required",
    "local_ack_pending",
    "latest_insertion_view_only",
    "usage_unknown",
    "execution_not_independently_stopped",
    "cleanup_unknown"
  ]
}
```

## 新規メソッド正確に6つ — 未実行（NOT EXECUTED）

[test_recovery_triage.py](../tests/contracts/test_recovery_triage.py)は専用・自己完結で、実際の一時BlobStore／非公開SQLite fixtureを使い、既存testはimportしません。

| ID | 作成した検査範囲 |
|---|---|
| T01 | 欠落／受領のみ、純粋・接続結果の決定性、frozen全量保持、再open、blob不在、書込なし |
| T02 | 既知ゼロ対UNKNOWN、独立停止／cleanup flag、超過、全量会計不変 |
| T03 | 直接照合、挿入対時刻、古いreplay、現在ack、現在event欠落 |
| T04 | 実scope page／cursor、具体receiver呼出、上限／厳密型、sender拒否、global合計なし |
| T05 | 不正／偽造snapshotの純粋検査：厳密型・scope／digest／ref／revision／status／会計／観測・ack整合 |
| T06 | 実読取transaction1つ、書込なし、後続会計／ack不正、実SQLite失敗で部分成功なし |

テスト実行と[設計検査](../scripts/check_design.py)（link・言語pair・JSON例・状態整合を含む）はfile-only指示により**保留中・未実行（NOT EXECUTED）**です。coordinator検証は別途です。成功・runtime／復旧結果・再現・独立レビュー結果は主張しません。3番目の増分は対象外です。

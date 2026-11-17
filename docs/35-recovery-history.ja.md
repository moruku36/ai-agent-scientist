# 35. 選択した予約のステータス履歴

[English](35-recovery-history.md) | [README](../README.ja.md) | [24 ローカル outbox](24-local-status-outbox.ja.md) | [26 予約の検査](26-reservation-inspection.ja.md) | [34 復旧 acknowledgement](34-recovery-ack.ja.md)

**Scientist24、ファイル編集のみ（2026-11-17）。指定された Scientist23 pin `56d3be6` を拡張するソース、独立した新規オフライン unittest メソッドちょうど6本、日英ドキュメントを記述済み。未実行（NOT EXECUTED）。** pin は依頼者の指定値であり git で確認していません。この増分ではテスト、チェック、実装の import、ビルド、ネットワーク、git、モデル/API 呼び出し、研究実行を行っていません。実行、再現、独立レビュー、ランタイム受入は保留です。以前の結果は今回の検証ではありません。文書番号35と Scientist の増分番号は別です。

[durable_handoff.py](../src/ai_agent_scientist/admission/durable_handoff.py) に、受信側ローカルの読み取り口を1つ追加します。全体イベントフィードでは、選択したリクエストの現在の予約スナップショットと過去イベントの ack を原子的に組み合わせられません。特に [Scientist23 の読み取りと ack CAS](34-recovery-ack.ja.md) は別トランザクションなので、OLD イベントを ack した時点で NEW 現在イベントが pending の場合があります。今回の読み取り口は、その保持された関係を単一 SQLite 読み取りスナップショットで示します。操作や権限は追加しません。

## 選択対象を1つの読み取りトランザクションで取得

```python
history = receiver.inspect_reservation_status_history(
    'req-1', after_event_id=0, limit=100,
)
```

frozen、slotted な `ReservationStatusHistory` のフィールドは次の3つだけです。

```python
snapshot: ReservationSnapshot
entries: tuple[LocalStatusEntry, ...]
next_after_event_id: int | None
```

トランザクション開始前に、既存の厳密な文字列ガードで request ID を検査します。空でなく、UTF-8 で1024バイト以内、NUL と不正 Unicode を含まない必要があります。`after_event_id` は既存の revision ガードにより `0..2**63-1` の厳密な組み込み整数、`limit` は `1..100` の厳密な組み込み整数でなければなりません。bool、サブクラス、型変換は認めません。値を含まない既存の識別子/revision/limit 例外が伝播します。

既存の `_transaction(write=False)` を1回使用し、バインドした request ID と信頼済み principal/project/recipient で実際の予約を検索します。存在しない場合と receipt だけの場合は `None` です。予約があれば同じ接続で既存の `_reservation_snapshot` に渡します。そのため receipt、予約、現在イベント/ack、最新利用観測、全額 outstanding の割当は既存の検査意味を維持します。

同じトランザクションで、既存の固定 SQL ヘルパーに任意のバインド済み request フィルターだけを加えて履歴を読みます。正確にその request と信頼済み scope を選び、別表のローカル ack を LEFT JOIN します。ACKED と pending の両方を含め、`after_event_id` より大きいイベントをローカル `event_id` 昇順で最大 `limit + 1` 行取得します。全体検査 API や独立した2回目のスナップショットは呼びません。既存の private SQL ヘルパー呼び出しの既定値と動作を維持します。他リクエストを履歴項目として返したり実体化したりしません。既存 index を使う request 条件付き SQL 読み取りであり、新しい実行計画や性能保証は主張しません。

返すのは先頭 `limit` 件までです。**余分な1行がある場合だけ、最後に返したイベント ID** を `next_after_event_id` に設定します。それ以外は、結果がちょうど `limit` 件の場合も `None` です。余分な行は継続判定だけに使い、項目として返しません。最終イベントより先を seek しても、選択した現在スナップショット、空 tuple、次カーソルなしを返します。

## 過去イベントの結合と ack 整合性

返す各過去イベントは、選択した receipt/予約の request ID、digest、principal、project、recipient、sender、予算参照、worker seconds と正確に一致する必要があります。revision/status は revision 1 / `reservation_retained` または revision 2 / `reconciliation_required` の組だけを認め、現在 receipt より新しい revision は拒否します。古い事実には現在 receipt の status を強制せず、そのイベント自身の revision/status の組を検査します。

返す各 ack revision は厳密な整数0または1です。pending の revision 0 では ack 時刻がないこと、revision 1 ではイベント作成時刻以降の文字列時刻であることを要求し、既存の保存済み UTC 文字列順序に従います。sender 不一致は既存の値を含まない `ReceiptScopeError`、その他の過去イベント結合や ack 不整合は値を含まない `ReceiptConflict` です。既存 snapshot/scope/storage エラーも伝播します。不正な保持項目があれば呼び出し全体が失敗し、部分履歴、修復、代替結果、再試行を返しません。

これは[既存の private SQLite 信頼前提](22-durable-handoff-receipt.ja.md)の下でのローカル結合検証です。認証、悪意ある DB 所有者、改変された信頼済みコード/schema、整合的に捏造された履歴への防御ではありません。選択 request/scope の外や seek 位置以前の行を、この有限ページで監査しません。legacy fixture に現在イベントがなければ `snapshot.current_status is None` を維持し、古い履歴を現在イベントとして代用しません。

## seek の意味と結果の解釈

snapshot と返す全履歴項目は同じ SQLite 読み取りトランザクションの状態です。WAL モードで別接続がその途中に commit しても同様です。次ページは独立スナップショットであり、カーソルは seek 位置であって永続的 scan lease や消費トークンではありません。古いイベントの ID を変えずに ack は変化できます。**変更された ack を再確認するには0から再開します。** トランザクション終了後には結果が古くなっている可能性があります。

`None`、空ページ、現在イベント不在は、配送、完了、精算、キュー消化を意味しません。ACKED は受信側ローカルの別 ack 行があることだけです。このメソッドは ack や retry を行わず、利用量、cleanup、receipt revision、ack 状態に関係なく、すべての予約を全額 outstanding のまま維持します。frozen 値は通常の変更を防ぐだけで、自由に構築可能な値であり capability や独立検証済み receipt ではありません。

以下は英語版と同じ、合成 private 値による省略 JSON 例です。新しい wire/schema 形式ではありません。実際の戻り値には既存 snapshot と event の全フィールドが含まれます。

```json
{
  "snapshot": {
    "receipt": {"request_id": "req-1", "revision": 2},
    "current_status": {"event_id": 2, "ack_revision": 0},
    "accounting": {"allocation_worker_seconds": 20, "outstanding_worker_seconds": 20}
  },
  "entries": [
    {"event_id": 1, "receipt_revision": 1, "status": "reservation_retained", "ack_revision": 1},
    {"event_id": 2, "receipt_revision": 2, "status": "reconciliation_required", "ack_revision": 0}
  ],
  "next_after_event_id": null
}
```

OLD ACKED と NEW pending を同時に示しますが、リクエスト自体を ack 済みや完了とは呼びません。`limit=1` なら最初のページはイベント1とカーソル1、次の seek はイベント2とカーソルなしです。イベント2より先を seek しても、履歴項目なしで現在 snapshot を返します。

## 記述した検証と境界

[test_recovery_history.py](../tests/contracts/test_recovery_history.py) に、独立した新規 unittest メソッドをちょうど6本記述しました。private な一時 SQLite/BlobStore fixture コードをローカルにコピーし、過去のテストクラスは import していません。値はすべて合成です。

| ID | 記述した対象 |
|---|---|
| H01 | 正確な frozen/slotted 有限履歴と現在 snapshot、OLD ack/NEW pending、DB/blob バイトの読み取り専用性、全額 outstanding 予算 |
| H02 | 厳密な排他的 seek、limit 1/2/100、余分な行と終端カーソル、ID の隙間、別 request/scope 分離、独立ページと ack 変更時の再開 |
| H03 | 厳密な型、サブクラス、Unicode、バイト数/整数境界の不正値をトランザクション前に拒否し、有効境界は読み取り |
| H04 | 実際の不在、receipt のみ、終端以降、legacy の現在イベント不在と全履歴不在、選択 snapshot の保持 |
| H05 | 過去イベントの sender/digest/参照/秒数/revision/status と ack の破損、正常な先行項目の後の不正履歴、全体拒否と DB/files 不変 |
| H06 | 実際の1接続/1読み取りトランザクションと request 条件付き固定 SQL、snapshot と履歴の間の実 WAL 同時 commit、一貫した旧状態と次回の OLD ack/NEW pending、エラー伝播、実 SQL 障害、読み取り終了障害、constructor/retry なし |

schema、migration、store、index、書き込み経路、transport、authorization、evaluator、精算、retry、時計サンプリング、既定値変更は追加しません。candidate worker は authorization と予算書き込み境界の外に置きます。スケジュール、通信、サービス、公開、外部実行も追加しません。既存 wire version と既存 receipt/予約/event を維持します。この読み取り口の利用をやめる場合も DB を保持して既存の検査 API を使えます。rollback や削除は不要です。

6本のテスト、リンク/言語ペア/JSON/status チェック、[design checker](../scripts/check_design.py)、ランタイム検証と再現性検証は、明示されたファイル編集のみの指示に従い、すべて**未実行（NOT EXECUTED）、保留**です。ソース記述は、合格、再現済み、独立レビュー済み、受入済みという結果ではありません。

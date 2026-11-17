# 36. 復旧操作結果の有界な読み取り専用確認

[English](36-recovery-outcome.md) | [README](../README.ja.md) | [Scientist22 適用](33-recovery-apply.ja.md) | [Scientist23 確認応答](34-recovery-ack.ja.md) | [Scientist24 履歴](35-recovery-history.ja.md)

**Scientist25、ファイルのみ（2026-11-17）：ソース、自己完結した unittest ちょうど6メソッド、日英ドキュメントを作成。NOT EXECUTED（未実行）。** 指定された Scientist24 の pin `45d7fea` は git で確認していない。テスト、チェック、実装の import、ビルド、ネットワーク、git、モデル/API、研究の実行は行っていない。実行、再現、独立レビュー、ランタイム受入れは未完了で、過去の結果は今回のファイルを検証しない。

[recovery_outcome.py](../src/ai_agent_scientist/admission/recovery_outcome.py) は [22 の適用モジュール](../src/ai_agent_scientist/admission/recovery_apply.py) または [23 の確認応答モジュール](../src/ai_agent_scientist/admission/recovery_ack.py) から応答が失われ、結果が不確実な場合の確認手段である。[24](35-recovery-history.ja.md) が [durable_handoff.py](../src/ai_agent_scientist/admission/durable_handoff.py) に追加した実際の `inspect_reservation_status_history` を合成する。操作は呼び出さない。盲目的な再実行は禁止であり、**どの分類も再実行を推奨・許可しない**。

各関数は厳密に具象型 `DurableHandoffReceipts` を要求する。呼出し側は intent 作成から確認まで、独立に信頼する同じ receiver・DB・scope を固定する。イベントIDはそのDB内の値であり、preview のハッシュや selection は receiver を認証・選択しない。[非公開 SQLite の信頼前提](22-durable-handoff-receipt.ja.md) には、import、コード、メソッド、スキーマ、ファイル所有権の信頼を含む。悪意ある同一UIDのコード、DB所有者、整合的に捏造された履歴には対抗しない。候補 worker は評価、認可、予算書込み権限の境界外に置く。

## 読み取り前の intent 検証

```python
view = inspect_reconciliation_outcome(receiver, preview)
view = inspect_acknowledgement_outcome(receiver, original_pending_selection)
```

厳密な `ReconciliationPreview` / `RecoveryStatusSelection` dataclass 型と組込みスカラー型だけを受け入れる。サブクラス、整数代わりの bool、型変換は拒否する。両方の request ID は非空文字列で UTF-8 最大1024バイト、NUL・不正Unicodeを含まないこと。request digest は小文字16進数ちょうど64文字とする。

preview は長さ `1..1048576` の厳密な `bytes`、その正確なバイト列と一致する小文字16進 SHA-256、厳密な整数 `expected_revision=1` を要求する。供給されたバイト列を解析しない。**ここでは preview 全体の一致を確認しない**。preview を再構築しない。形状とハッシュの妥当性は、由来、人の確認、権限の証明ではない。

selection は元の未確認 intent を表すこと。receipt revision は厳密な整数1または2、イベントIDは `1..2**63-1`、event receipt revision は意図した receipt revision と同じ厳密な整数、ack revision は厳密な整数0とする。selector が返せる値でも、ack revision 1 の既確認 selection を未使用 intent として受け入れない。保持された結果の確認には元の pending selection を保存する。

不正な intent はストレージを読む前に値を含まない `RecoveryOutcomeRefused('recovery outcome refused')` を送出する。receiver 型の不正は値を含まない `TypeError` とする。いずれも成功した view を返さない。

## 実際の履歴トランザクション1回

reconciliation は `receiver.inspect_reservation_status_history(request_id, after_event_id=0, limit=1)` をちょうど1回呼ぶ。acknowledgement は `after_event_id=selection.event_id-1, limit=1` でちょうど1回呼ぶ。[24 の実際の履歴API](35-recovery-history.ja.md) が、完全な現在の予約 snapshot と有界な履歴を**同一の SQLite 読み取りトランザクション**で返す。全体フィードや独立した現在状態は読まない。

返された実際の snapshot は既存の純粋関数 [classify_reservation](../src/ai_agent_scientist/admission/recovery_triage.py) に `scope=receiver._scope` を渡して検証する。追加読み取りはない。選択した request ID または現在の request digest が異なる場合は、同じ専用の値を含まない拒否を送出し、view を返さない。ストレージ、履歴の結合、scope、triage の既存エラーは同じまま伝播し、成功への変換、再試行、代替経路、部分出力は追加しない。missing/receipt-only には検証対象の予約 snapshot がなく、下記の分類を返す。

| 操作 | 分類 | ローカルでの意味のみ |
|---|---|---|
| 両方 | `missing_or_receipt_only` | 選択した予約 snapshot がない。完了は判断できない |
| Reconciliation | `receipt_still_recorded` | 一致する receipt は revision 1 / recorded。**安全な再実行の証明ではない** |
| Reconciliation | `reconciliation_transition_observed` | 一致するローカル状態が revision 2 へ進んだ。**因果関係は未証明** |
| Acknowledgement | `target_event_not_found` | seek が空、またはイベントID・意図した receipt revision が一致しない |
| Acknowledgement | `target_ack_pending` | 正確な対象イベントはローカルで未確認 |
| Acknowledgement | `target_ack_retained` | 正確な対象イベントのローカル ack が保持されている |

実際の usage observation や別の呼出し側も、適用操作と同じ reconciliation 遷移を起こせる。revision 2 は、この試行が遷移を引き起こしたこと、正常に返ったこと、作業を実行したことを証明しない。recorded 状態も安全な再試行期間を示さない。

acknowledgement の確認では後続イベントの ack を借用しない。対象イベントIDと意図した event receipt revision の両方が一致した場合だけ pending/retained を返す。`target_event_is_current` は同じ snapshot の正確な現在イベントIDと意図した対象IDを比較する。現在 status が欠ける場合、古い対象 ack が保持されていても `None`（不明）とする。`False` は別の現在イベントIDを観測したという意味で、配送に関する結論ではない。

## 不変な観測値と限界

frozen / slotted の `RecoveryActionOutcome` のフィールドは、`action`、`classification`、`request_id`、`request_sha256`、実際の完全な `snapshot: ReservationSnapshot | None`、`target_status: LocalStatusEntry | None`、`target_event_is_current: bool | None` のみ。操作名は `mark_reconciliation_required` と `acknowledge_status_event` とする。reconciliation は特定イベントを対象としないため、両対象フィールドは `None`。missing/receipt-only にも対象はない。ack 対象が一致しなければ `target_status=None` とするが、現在IDとの比較は選択した snapshot をそのまま表す。実行成功、配送、精算、再試行許可の bool は持たない。frozen 値も自由に構築でき、権限ではない。

以下は英語版と同じ合成値による省略JSONであり、新しい wire format ではない。実際の Python 値は snapshot と対象 entry 全体を保持する。OLD ack / NEW pending は、request の配送・完了を意味しない。

```json
{
  "action": "acknowledge_status_event",
  "classification": "target_ack_retained",
  "request_id": "req-1",
  "request_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "snapshot": {
    "receipt": {"revision": 2},
    "current_status": {"event_id": 2, "ack_revision": 0},
    "accounting": {"allocation_worker_seconds": 20, "outstanding_worker_seconds": 20},
    "latest_usage_observation": null
  },
  "target_status": {"event_id": 1, "receipt_revision": 1, "ack_revision": 1},
  "target_event_is_current": false
}
```

トランザクション終了後、snapshot は既に古くなっている可能性がある。ローカル ack はリモート配送を証明しない。予約額全体を未精算のまま保持し、usage/cleanup の UNKNOWN をゼロや解放済み予算に変えない。receiver 構築、時計取得、操作実行、書込み、精算、スケジュール、通信、公開、依存追加、wire version 変更は行わない。不確実な場合は正本DBと元の intent を保持する。この読み取りは再実行の推奨や新しい権限を提供しない。

[test_recovery_outcome.py](../tests/contracts/test_recovery_outcome.py) は実際の非公開一時 SQLite/BlobStore fixture をローカルに複写し、過去のテストクラスを import しない。作成したメソッドはちょうど6つ。

| ID | 作成済み・未実行の対象 |
|---|---|
| Q01 | recorded、実際の適用コミット後の応答喪失、予算全額保持 |
| Q02 | 実際の UNKNOWN usage observation と別呼出し側による同じ非因果的 revision 2 分類、不透明なバイト列 |
| Q03 | 実際の ack コミット後の応答喪失、OLD ack / NEW pending 競合、保持した過去 selection |
| Q04 | 実際の missing/receipt-only、ID/revision 不一致、対象欠落、digest 拒否、不正 intent の読み取り前拒否と有効な境界値 |
| Q05 | 実際の履歴呼出し・接続・読み取りトランザクション各1回、非ゼロ seek、純粋 triage、独立/全体読み取り・操作・構築なし、DB/全ファイル不変 |
| Q06 | 同じ storage/triage エラーオブジェクト、再試行/構築なし、具象 receiver、実際の純粋 triage 拒否、frozen/slotted 出力、現在イベント欠落の旧形式 fixture |

6メソッドすべて、リンク・言語ペア・JSON・状態整合性のチェック、[design checker](../scripts/check_design.py)、ランタイム・再現性確認は、明示的なファイルのみの指示に従い **NOT EXECUTED・保留**。ソース作成は合格、再現済み、独立レビュー済み、受入れ済みの結果ではない。

# 31. 復旧オペレーターのワークフロー（キュー -> 詳細 -> 明示マーク）

[English](31-recovery-operator.md) | 関連: [29 コンソール](29-recovery-console.ja.md)、[30 キュー](30-recovery-queue.ja.md)

状態: **作成のみ・未実行**。非公開・ローカル・同一プロセス内。権限でも通信形式でもランタイム受入でもない。

## 流れ

1. `render_recovery_queue(receiver, reasons=(...))` が保守的な理由コードで候補を列挙する。
2. `render_recovery_detail(receiver, request_id)` が選んだ1件を表示する（直前のキューページ外でも可）。`RecoveryDetailView(text, request_id, request_sha256, revision, state)`、または不在・receipt のみなら `None` を返す。
3. 信頼された呼び出し側が必要と判断した場合のみマークする。

```python
view = render_recovery_detail(receiver, 'req-1')
receipt = mark_recovery_for_reconciliation(
    receiver, request_id=view.request_id,
    expected_request_sha256=view.request_sha256,
    expected_revision=view.revision, now=injected_now)
```

マークは自動では行われない。キューと詳細は読み取りのみ。

## 詳細の内容

`PRIVATE ... NOT AUTHORITY` ヘッダー、request/payload ダイジェスト、予約参照と未解消の予約額（outstanding worker-seconds）全量、保持された最新の観測（ID・連番・時刻・expected revision）、保持された状態イベント（ID・receipt revision・ack 時刻）、理由付きの通常要約行。表示される `request_sha256` と `payload_sha256` は receipt の識別情報であり、レポートのハッシュでも認可でもない。値はすべて JSON エスケープされた印字可能 ASCII。証拠が無い項目は `UNKNOWN`/`unknown` と表示し、0 とは扱わない。`max_output_bytes`（1..1048576 の int）は切り詰めではなく全体拒否。receiver を構築せず、書き込みもしない。

## マークの意味

- ダイジェスト（小文字16進64文字）とリビジョン（正の整数）の型を、読み取り前に検査する。
- `inspect_recovery_triage` を1回呼び、予約の存在・正確な request ダイジェスト・期待リビジョン・状態 `recorded` を要求する。満たさなければ値を含まない `RecoveryMarkRefused`。receipt のみの要求は拒否。
- その後 `receiver.require_reconciliation(...)` を厳密に1回だけ呼び、既存のアトミック CAS と時刻検証を維持する。`now` は注入され、サンプリングしない。
- 既に reconciliation 要求済みなら、再生成功ではなく拒否。
- 委譲先の既存遷移がreceiptを更新し、既存local status eventを追加する。新store・予約／予算変更・ack・観測の書込みは追加しない。

## スナップショットと競合

検査と CAS は別トランザクション。間に receipt が変わると既存 CAS が失敗し（`ReceiptRevisionError`）、この操作による追加変更はない（並行writerの変更は残る）。原子的ビューを装う再読込はせず、呼び出し側・スコープ・履歴の認証もしない。receiver と呼び出し側は別途信頼されている必要がある。キューと詳細は独立したスナップショット。

## 主張しないこと

マークは信頼されたcallerによる明示的な照合要求を記録するだけで、人間の操作を証明しない。停止、クリーンアップ、予算の解放・精算、認可、受理、ディスパッチ、再試行、完了は一切行わず、予約は全量outstandingのまま残る（未使用という意味ではない）。テストは合成ローカルフィクスチャのみで、運用データベースには触れない。

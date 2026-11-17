# 32. 照合プレビュー

English: [32-recovery-preview.md](32-recovery-preview.md) | [README](../README.md)

## 状態

- 提案・作成済み。**未実行**。この増分についてテスト・チェック・実行は行っていない。
- `tests/contracts/test_recovery_preview.py` に、オフラインの合成 unittest を6件予定している。未消化の予約枠は変更しない。
- P1 の明示的な復旧意図・レビューを進めるもので、ランタイム・スキーマ・wire version・CLI・サービスは追加しない。

## 内容

`src/ai_agent_scientist/admission/recovery_preview.py` の `build_reconciliation_preview(receiver, request_id, *, max_output_bytes=65536)` は、実際に選択された復旧詳細(`render_recovery_detail` を1回だけ呼ぶ)と、呼び出し側が確認できる `mark_reconciliation_required` の説明を結び付ける。不変の `ReconciliationPreview(data, sha256, request_id, request_sha256, expected_revision)` を返す。要求が存在しない、またはレシートのみの場合は `None`。

- バイト上限は 1..1048576 の厳密な組み込み整数で、読み取り前に検証する。全体が上限を超えると `RecoveryPreviewTooLarge` で拒否し、切り詰めない。
- プレビュー対象は state `recorded` のみ。それ以外は値を含まない `RecoveryPreviewRefused`。
- バイト列は決定的: キーはソート、ASCII、コンパクト、末尾改行なし、DEL はエスケープ。
- JSON 項目: private local version `recovery-reconciliation-preview/1`、action、request id、request digest、expected revision、元詳細の SHA-256、元詳細の全文、制限事項の文字列。

## 制限

- 非公開・ローカル。権限ではない。プレビューは実行されず、停止・解放・精算・承認・dispatch を行わず、書き込み・時計参照・receiver 構築もしない。
- `sha256` はプレビューのバイト列のハッシュであり、CAS トークンでも人間による確認の証明でもない。偽造オブジェクトは capability ではなく、信頼された呼び出し側と receiver を前提とする。
- 将来の適用ステップは、既存のレシート CAS の前に再読込して比較する必要がある。プレビューと操作の間のスナップショット競合は残る。
- ストレージ・読み取りエラーはそのまま伝播する。

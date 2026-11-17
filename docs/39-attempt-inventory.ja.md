# 39 ローカルの対応付き試行一覧

[English](39-attempt-inventory.md) | [ホーム](../README.ja.md)

**Scientist28 P1/P2 状態: ソース、自己完結した unittest メソッドちょうど4件、日英文書を作成済み。NOT EXECUTED（未実行）。** この増分ではテスト、import、ビルド、設計・リンク・状態チェック、再現、独立レビューを実行していない。純粋なオフライン分母ヘルパーであり、ランタイム受入れや研究成果を示さない。

[ソース](../src/ai_agent_scientist/records/attempt_inventory.py) と [4シナリオ](../tests/contracts/test_attempt_inventory.py) は、[37](37-run-record.ja.md) の実際の [run-record パーサー](../src/ai_agent_scientist/records/run_record.py) と既存の [厳密 JSON パーサー](../src/ai_agent_scientist/evidence/json_blob.py) を使用する。[run-record スキーマ](../schemas/run-record.schema.json) と [P1/P2 ロードマップ](10-roadmap.ja.md) は変更しない。

`build_attempt_inventory(manifest_data: bytes, records: tuple[RunRecord, ...], *, max_bytes: int = 1048576)` は frozen・slots 付きの `AttemptInventory(data, sha256, project_id, protocol_revision, slots)` を返す。各 `AttemptSlot(spec, record)` と、その `AttemptSpec(run_id, attempt_id, replicate_id, candidate_revision, role)` も frozen・slots 付き。record は元のレコードまたは明示的な `None`。入力レコードの順序にかかわらず、スロットはマニフェスト順を維持する。再シリアライズせず、正確なマニフェストバイト列と SHA-256 を保持する。

以下はローカルの **INTERNAL** 形式であり、狭い対応付きプロファイルである。正規スキーマの変更ではない。この無効な合成例は、利用可能なレコードとは独立に分母全体を宣言する。

```json
{
  "format": "offline-attempt-manifest/1",
  "project_id": "synthetic-project",
  "protocol_revision": "protocol-1",
  "attempts": [
    {"run_id": "run-b", "attempt_id": "attempt-b", "replicate_id": "replicate-1", "candidate_revision": "baseline-1", "role": "baseline"},
    {"run_id": "run-c", "attempt_id": "attempt-c", "replicate_id": "replicate-1", "candidate_revision": "candidate-1", "role": "candidate"}
  ]
}
```

トップと各試行は、このキー集合に厳密一致し、追加キーを許可しない。既存の厳密デコーダーはキー重複、BOM、不正 UTF-8、非有限数を拒否する。bytes/int/tuple は厳密な組込み型のみ。`max_bytes` は1〜1 MiBで、デコード前のマニフェストを制限する。attempts は厳密な list で1〜1024件、records は厳密な tuple で最大1024件。全文字列は厳密な組込み str、空でなく UTF-8 で4096バイト以下、NUL・サロゲートなしとする。

run_id と attempt_id はそれぞれ全体で一意。**各 replicate は baseline と candidate を必ず1件ずつ宣言する。** `(replicate_id, role)` の重複と片側だけの宣言は拒否する。同じ replicate/role に複数候補や再試行を置く用途は対象外。未宣言の試行は推定しない。

供給値は実際の厳密な `RunRecord` 型に限る。自身のバイト列を実際のパーサーの既定1 MiB上限で再解析し、入れ子の型も含む全フィールドの一致を要求する。自由に構築してフィールドを改変した値は拒否する。レコードの run_id 重複・未宣言ID、および project・protocol・run・attempt・replicate・candidate revision の不一致を拒否する。他の試行から借用しない。一致したレコードは同一オブジェクトのまま保持し、failed・unchecked・null usage、metrics、limitations を変更しない。欠測は `None` のまま、スロットを削除せず、成功・スコア・コスト・妥当性を推定しない。

自身の検証・デコーダー・レコード解析エラーは固定の `AttemptInventoryRefused("attempt inventory refused")` のみとする。ハンドラーを抜けてから送出し、ペイロードを含む cause/context を保持しない。バイト数・件数上限は深さ・CPU・メモリの完全な隔離ではない。マニフェストとハッシュは事前登録を認証せず、結果より先に宣言された証明にもならない。完全性は供給されたマニフェストに対するものに限る。

作成した4シナリオは、解析済み完全ペアの同一性と順序の保持、candidate 欠測時の failed・unchecked baseline と null usage の保持、protocol 不一致1件の拒否、マニフェストの attempt identity 重複の拒否。テスト行列はなく、すべて未実行。他の検証分岐も未実行である。ストレージ・ネットワーク・評価器・予算操作は行わず、認可、保護評価、知識昇格、研究上の権限を与えない。既存の DOTS/ChatGPT/Codex 制約と wire version を維持し、実タスク状態は公開リポジトリ外に置く。

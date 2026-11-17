# 37 Run-record 契約

[English](37-run-record.md) | [ホーム](../README.ja.md)

**Scientist26: ソースと限定的な4シナリオを作成済み、NOT EXECUTED（未実行）。**
以下の挙動は静的なソース上の契約記述であり、ランタイム検証ではない。
[P1 レコード契約](10-roadmap.ja.md) の狭い範囲として、既存の
[run-record schema](../schemas/run-record.schema.json) 用の純粋なパーサを追加する。
復旧の確認・操作ツールは研究レコードを実装していない。P1 の他のレコード、永続化、
権限確認、および P2 の runner・保護された評価・再現は別の未完了作業である。
今回の修正ではパーサのソース、依存関係、schema、wire version を変更しない。

[parse_run_record](../src/ai_agent_scientist/records/run_record.py) は厳密な組込み
`bytes` と、1..1048576 の厳密な組込み整数 `max_bytes`（既定 1048576）を受け取る。
既存の [strict JSON parser](../src/ai_agent_scientist/evidence/json_blob.py) を呼ぶ前に
バイト上限を確認する。デコード後のキー重複、BOM、不正 UTF-8/JSON、非有限数を拒否する。

schema の全12フィールドを必須とし、余分なキーを拒否する。artifact と usage も
キーが完全一致する必要がある。map のキーと ID を含む全ての文字列は空でなく、
UTF-8 で4096バイト以下、NUL とサロゲートを含まない。各配列・map は1024要素以下。
artifact のハッシュは小文字16進64文字に限る。同一 artifact tuple を含め、ID の
重複を拒否する。異なる ID が同じハッシュを持つことは許容する。これらは schema を
変更せず、受理するローカルプロファイルを狭める制約である。

frozen・slotted な `RunRecord` は元の `data` オブジェクト、その正確なバイト列の
`sha256`、6つの識別・revision 文字列、status、validity を保持する。artifacts は
frozen・slotted な `ArtifactRef(id, sha256, kind)` の tuple、metrics は入力順の
`(name, value)` tuple、`usage` は `wall_seconds` と `incremental_api_usd` を持つ
frozen・slotted な `Usage`、limitations は文字列 tuple となる。数値は変換せず
組込み `int`/`float` を保持し、bool を拒否する。metrics は負数または null も許容し、
usage は非負数または null とする。不明な usage は null のままで、ゼロにしない。
正規化や再シリアライズは行わない。

以下は英語版と同じ完全な合成 JSON であり、失敗・未確認の要約を示す。
実際の実行や検証済み receipt ではない。

```json
{
  "run_id": "run-1", "attempt_id": "attempt-1", "replicate_id": "replicate-1",
  "project_id": "project-1", "protocol_revision": "protocol-1",
  "candidate_revision": "candidate-1", "status": "failed", "validity": "unchecked",
  "artifacts": [{"id": "log-1", "sha256": "0000000000000000000000000000000000000000000000000000000000000000", "kind": "raw_output"}],
  "metrics": {"delta": -1.5, "score": null},
  "usage": {"wall_seconds": 0, "incremental_api_usd": null},
  "limitations": ["Synthetic fixture; no evaluation performed."]
}
```

6種類の status と4種類の validity は独立に保持し、`failed` と `unchecked` も変えない。
`valid` も入力ラベルにすぎない。パースは artifact の解決、発行者認証、証拠検証、
実行認可、usage の精算、validity・知識の昇格を行わない。値は自由に構築でき、権限を
与えない。[12](12-protocol-and-acceptance.ja.md) の保護された binding はこの要約
パーサの範囲外である。

拒否は固定の `RunRecordRefused("run record refused")` のみで、デコーダの cause/context
や入力値を含むエラー文を保持しない。traceback のフレーム内変数には非公開入力が残り得る
ため、外部に出さない。バイト・要素上限は CPU・メモリ・深さの完全な隔離ではない。

[自己完結した4つの unittest メソッド](../tests/contracts/test_run_record.py) は
**合計4シナリオ**で、各メソッドにインライン入力1つとパーサ呼び出し1回のみを置く。
R01 は負数・null の metrics と null の usage を持つ failed/unchecked レコードで、
元の正確なバイト列・ハッシュ、入れ子の tuple、dataclass の不変性を確認する。
R02 はデコード後のキー重複1件で、固定の拒否文と cause/context がないことを確認する。
R03 は usage の bool 値1件を拒否する。R04 は小さいバイト上限を超える、それ以外は
有効なレコード1件で、パッチしたデコーダを呼ぶ前の拒否を確認する。
4件とも作成済みで **NOT EXECUTED・未実行**。より広い status・構造・境界値の挙動は
静的な契約記述にとどまり、ランタイムでの網羅的な検証は主張しない。
明示的なファイルのみの指示に従い、テスト、import、build、自動のリンク・言語ペア・
JSON・状態整合性チェック、[design checker](../scripts/check_design.py) は実行していない。
ランタイム受入れ、再現、今回の修正の独立レビューは主張しない。runner、モデル/API、
研究実行は開始しない。

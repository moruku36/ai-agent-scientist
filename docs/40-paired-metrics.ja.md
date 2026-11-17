# 40 対応付き指標の観測

[English](40-paired-metrics.md) | [ホーム](../README.ja.md)

**Scientist29 状態: ソース、自己完結した unittest メソッドちょうど4件、日英文書を作成済み。NOT EXECUTED（未実行）。** この増分ではテスト、チェック、import、ビルド、再現、独立レビューを実行していない。オフラインの観測ヘルパーであり、ランタイム受入れや研究成果を示さない。

[ソース](../src/ai_agent_scientist/records/paired_metrics.py) と [4シナリオ](../tests/contracts/test_paired_metrics.py) は実際の [試行一覧](39-attempt-inventory.ja.md) と [run-record パーサー](../src/ai_agent_scientist/records/run_record.py) を使用する。[12](12-protocol-and-acceptance.ja.md) の科学的要件と保護評価要件は別の境界にあり、変更しない。

`compare_paired_metrics(inventory: AttemptInventory, *, metric: str, direction: str)` は frozen・slots 付きの `PairedMetricComparison(inventory, metric, direction, pairs)` を返し、元の inventory を保持する。各 `MetricPair(replicate_id, baseline, candidate, classification, baseline_value, candidate_value, raw_delta, directional_delta)` も frozen・slots 付きで、元の baseline/candidate の `AttemptSlot` を保持する。`pairs` は全宣言 replicate を各1回、マニフェストでの初出順に含む tuple。入力レコードの到着順ではなく、実際の `spec.replicate_id` と role で対応付ける。一覧の検証は各 replicate の両 role を要求する。

inventory は実際の厳密な型に限る。再構築より先に、metric が厳密な組込み str、空でなく UTF-8 で4096バイト以下、NUL・サロゲートなしであることを確認する。direction は厳密な組込み str で `maximize` または `minimize`。再構築は既定の上限で `build_attempt_inventory(inventory.data, tuple(スロット内の非Noneレコード))` を呼ぶ。その後、ハッシュと元のバイト列を含む全 inventory フィールド、slot、spec、record、artifact、usage、tuple と入れ子のスカラーを、型と値の両方で再帰的に照合する。通常の dataclass 等価判定は `1` に対する `True` や `1.0` を受け入れるが、これらの置換と偽造スロットは拒否する。再検証した実際のパーサーの厳密な組込み数値だけを、型変換せずに使う。

分類は次の優先順で、上の条件が常に優先する。

| classification | 条件 | 差分 |
|---|---|---|
| `missing_record` | いずれかの record が欠測 | 両方 `None` |
| `ineligible_status` | 両 record があり、いずれかの status が `completed` 以外 | 両方 `None` |
| `unchecked_validity` | 両方 completed で、いずれかの validity が `valid` 以外 | 両方 `None` |
| `missing_metric` | 両方 completed/valid で、いずれかの指標キーが欠落または null | 両方 `None` |
| `numeric_range_unsupported` | それ以外で、減算・符号計算が `OverflowError` または非有限 float を生じる | 両方 `None` |
| `paired_observation` | 両方 completed/valid、両値があり、計算範囲に対応 | candidate − baseline。maximize は同符号、minimize は反転 |

不適格または範囲外のペアでも、存在する元の値を保持する。キー・record の欠落と null 値は `None`。整数計算は float に変換せず厳密さを保つ。混合型・float の計算は Python 組込み演算に従い、overflow または非有限結果ではペアと元の値を残し、無限大の差分を返さない。ペアを削除せず、欠測を0で補わない。完全性は供給されたマニフェストに対するもので、実際の全試行が宣言された証拠ではない。

以下の無効な合成 JSON は観測の一部フィールドを示す例であり、新しい wire 形式や実行結果ではない。

```json
{
  "metric": "score", "direction": "minimize",
  "pairs": [{"replicate_id": "replicate-1", "classification": "paired_observation",
             "baseline_value": 10, "candidate_value": 11,
             "raw_delta": 1, "directional_delta": -1}]
}
```

自身の検証・再構築エラーは固定の `PairedMetricsRefused("paired metrics refused")` のみとする。ハンドラーを抜けてから送出し、ペイロードを含むデコーダー cause/context を保持しない。既存のバイト数・件数上限は深さ・CPU・メモリの完全な隔離ではない。status と `valid` は呼出元が与えた出典ラベルであり、実行成功の認証や保護検証の証明ではない。`paired_observation` も適格な観測に限り、平均、勝者、成功判定、昇格、統計的推論、評価器を提供しない。

作成した4シナリオは、completed/valid の整数ペア（11対10、minimize の差分1と-1）、failed candidate を差分なしで保持、candidate 欠測時もペアと分母を保持、解析済み整数 `1` を入れ子の `Usage.wall_seconds=True` に置き換えた通常の等価判定を通る偽造の拒否。fixture はローカルで、過去のテストを import せず、テスト内にループ・表・subTest・パラメーターによるシナリオ展開を置かない。全4件とその他の分岐は未実行。ヘルパーは store 読出し、ネットワーク、artifact 解決、ランタイム、モデル/API/科学実行、子プロセス起動を行わない。既存 DOTS/ChatGPT/Codex 制約、依存関係、wire/schema version を維持し、非公開タスク状態は公開リポジトリ外に置く。

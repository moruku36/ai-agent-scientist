# 17 純粋なワーカー予算プリフライト

[English](17-budget-preflight.md) | [ホーム](../README.md)

**状態: オフライン補助関数を実装し、10件のフィクスチャを作成済み(2026-11-17)。B01–B10 は1回のオフライン実行で全件成功。** 実際の実行結果はコーディネーターが外部に記録します。2026-11-17 に B01–B10 の10件を1回だけ実行し、全件成功しました。対象は P1 / SCI-05 の算術部分のみで、完全な admission、runner、ランタイム受け入れではありません。科学的結果・実測結果は主張しません。[CPU パイロット](../examples/cpu-pilot.json)は無効のままです。

## 実装とコマンド

実装済み(オフライン、標準ライブラリのみ、namespace package で `__init__.py` なし):

- `src/ai_agent_scientist/admission/budget_preflight.py`
- `tests/contracts/test_budget_preflight.py`(B01–B10 のちょうど10メソッド、各1ベクトル)

実行済みの再現コマンド(2026-11-17、10件成功):

```
env PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/contracts -p test_budget_preflight.py -v
```

これは SCI-05 の完全な起動拒否でも admission でも runner でもありません。本件では本番への接続、registry、スキーマ、wire バージョンの変更は行いません。

## 内部インターフェース

名前は `check_uniform_worker_budget`。キーワード専用の入力はちょうど5つで、下表の検証順です。値は [evaluation-protocol/1](../schemas/evaluation-protocol.schema.json) の `execution` に由来し、新しい wire 契約ではありません。

| 入力 | 記号 | 定義域 |
|---|---|---|
| `planned_attempts` | P | 正の整数 |
| `max_retries` | R | 非負整数 |
| `per_attempt_seconds` | S | 正の整数 |
| `evaluation_cleanup_seconds` | E | 非負整数 |
| `total_worker_seconds` | T | 正の整数 |

受け付けるのは組み込みの厳密な `int` 型のみです。bool、サブクラス、すべての float(整数に見えるものを含む)、文字列、null、非有限値、定義域外の整数は拒否します。型変換、独自コンバーター、float 変換は行わず、整数の精度を保ちます。コスト不明は 0 ではありません。

有効入力では `required = (P + R) × S + E`、`shortfall = max(required − T, 0)` です。R は試行数 P に掛けず、研究全体で1つの再試行許容量です。E は事前に宣言したオーバーヘッドです。検証・再現の配分は、計画試行またはオーバーヘッドのどちらかで一度だけ固定し、漏れも二重計上もしません。異種の上限は本補助関数の対象外です。

不変の内部結果(frozen dataclass、フィールド順は以下のとおり):

- `outcome`: required <= T なら `fits_arithmetic`、そうでなければ `exceeds_cap`。無効入力は `invalid_input`。
- `required_worker_seconds`、`cap_worker_seconds`、`shortfall_worker_seconds`: 有効入力では正確な整数。
- `invalid_field`、`invalid_reason`: 有効入力では null。無効入力では表の順で最初に無効なフィールドと、理由 `not_integer`(bool を含む)または `below_minimum`。
- 無効入力では required と shortfall は null。cap は T が単独で正の整数の定義域を満たす場合のみ保持し、そうでなければ null。

同一入力は同一結果になります。生の値のログは不要です。ファイル/JSON リーダー、URI 解決、時計、プロセス、環境、認可参照、台帳は入力に含みません。この純粋な計算は状態を変えず、何も起動しません。

## 検証と結果の決定

5つの値すべてを、型変換なしでそれぞれの定義域に照らして検査します。先行フィールドが無効でも T は検査します。各フィールドでは整数要件を先に判定し、非整数は `not_integer`、最小値未満の整数のみ `below_minimum` です。したがって負の float は `below_minimum` ではなく `not_integer` です。

いずれかの定義域に失敗した場合は `invalid_input` とし、P, R, S, E, T の順で最初に失敗したフィールドとその理由だけを返します。required と shortfall はともに null で、有効なフィールドだけの部分合計は計算しません。cap は T が単独で定義域を満たすときのみ T そのもの、そうでなければ null で、どのフィールドが報告されても同じです。5つすべてが通ったときだけ上記の式を適用して `fits_arithmetic` か `exceeds_cap` を選び、無効入力用の2つのメタデータは null になります。

宣言的なエッジ例(**未実行**)。入力順は (P,R,S,E,T)。全行で outcome は `invalid_input`、required と shortfall は null です。cap と報告される単一のフィールド/理由を明示します。

| 入力 | cap | 無効フィールド / 理由 |
|---|---|---|
| 0,-1,1,0,0 | null | planned_attempts / below_minimum |
| 0,0,1,0,10 | 10 | planned_attempts / below_minimum |
| 1,0,1,0,0 | null | total_worker_seconds / below_minimum |
| 1,-1,1,-1,10 | 10 | max_retries / below_minimum |
| 1,0,1,-1,10 | 10 | evaluation_cleanup_seconds / below_minimum |
| 1,-1.0,1,0,10 | 10 | max_retries / not_integer |
| 1,0,1,0,true | null | total_worker_seconds / not_integer |
| 1,0,1,0,10.0 | null | total_worker_seconds / not_integer |

これらの説明用の例は B01–B10 とは別で、追加のフィクスチャでも追加のテスト枠の承認でもありません。1回の実行・10ケース・30秒という今回の枠も拡張しません。

## 10件のフィクスチャ — 1回のオフライン実行で全件成功

入力順は (P,R,S,E,T)。以下のすべてのケースで cap は T と等しく、無効ケースも T が有効なため同様です。有効ケースの無効フィールド/理由は null です。テストは各ケースで結果の全フィールドを検証します。

| ID | 入力 | outcome | required | shortfall | 無効フィールド / 理由 |
|---|---|---|---|---|---|
| B01 / SCI-05 算術 | 72,0,600,0,1800 | exceeds_cap | 43200 | 41400 | — |
| B02 ちょうど境界 | 2,0,600,600,1800 | fits_arithmetic | 1800 | 0 | — |
| B03 全体の再試行許容量 | 2,1,400,100,1300 | fits_arithmetic | 1300 | 0 | — |
| B04 クリーンアップが1超過 | 2,1,400,101,1300 | exceeds_cap | 1301 | 1 | — |
| B05 再試行で判定が変わる | 2,1,600,0,1200 | exceeds_cap | 1800 | 600 | — |
| B06 試行なし | 0,0,1,0,1 | invalid_input | null | null | planned_attempts / below_minimum |
| B07 bool は整数ではない | true,0,1,0,1 | invalid_input | null | null | planned_attempts / not_integer |
| B08 コスト不明 | 1,0,1,null,10 | invalid_input | null | null | evaluation_cleanup_seconds / not_integer |
| B09 型変換なし | 1,0,1.5,0,10 | invalid_input | null | null | per_attempt_seconds / not_integer |
| B10 正確な大きい整数 | 9007199254740993,0,1,0,9007199254740992 | exceeds_cap | 9007199254740993 | 1 | — |

B01 は 12 × 2 × 3 = 72 試行と 1,800 秒スケッチの既存の不整合を保持するもので、その研究の承認や実行ではありません。B08 は算術入力の欠落を試すもので、実際の UNKNOWN 試行の突き合わせではありません。この10ベクトルは定義域を網羅しません。

## 上限・権限・復旧

[実験計画](../schemas/experiment-plan.schema.json)は `limits.per_run_seconds` / `limits.total_seconds` を、プロトコルは `execution.per_attempt_seconds` / `execution.total_worker_seconds` を使います。これらは暗黙には交換できません。ハッシュで束縛された両文書と権威ある envelope の双方を最終的に満たす必要があります。完全な対応付け・衝突解決は本書では未定義で、曖昧または衝突する対応付けは実際の admission を止めます。本補助関数はプロトコルの算術のみを検査します。

`fits_arithmetic` は、admission、認可、予約の成功、残余台帳の妥当性、マニフェストの件数/ハッシュ検証、科学的妥当性、実験の成功、検証レシート、DecisionReceipt の**いずれでもありません**。将来の権威ある admission は、現在の権限、残予算、予約、束縛、隔離をアトミックに再確認する必要があります。権限の欠落・期限切れ・失効、または無効な計画は引き続き起動を止め、enabled=true は権限ではありません。

適合させるために上限や再試行を引き上げたり、クリーンアップを外したり、研究を黙って縮小したりしてはいけません。再計算は予約、レプリケート、ディスパッチの権利を生みません。消費済み予算の払い戻し・リセットも UNKNOWN の解消も行いません。実使用が不明な場合は保守的な予約を維持し、重複するディスパッチや再試行の前に元の試行を突き合わせます。ワーカーによる自己払い戻しと無検証の再実行は引き続き禁止です。

## 検証状況

上記コマンドで B01–B10 の10ケースを1回だけ実行し全件成功(2026-11-17、unittest 表示 0.000 秒、最大30秒枠)。再実行なし。実行記録はコーディネーターも保存。依存関係のインストール、ビルド、全スイート、CI、ネットワーク、モデル/API/GPU、実験プロセスは含みません。過去の予算と UNKNOWN は変わりません。リポジトリの設計チェッカーは今回のドキュメント変更では**未実行**で、設計チェッカーの成功やランタイム受け入れは主張しません。

## 設計の出典

- [06 実験契約](06-experiment-contracts.md): ディスパッチ前に予約、検証/再現/クリーンアップ。
- [10 ロードマップ](10-roadmap.md): P1 と提案中のランタイム構成。
- [11 予算の所有](11-harness-boundaries.md): 確定済み使用量と未解決の予約。
- [12 プロトコルと受け入れ](12-protocol-and-acceptance.md): 一様な上限と SCI-05。
- [13 検証](13-verified-discovery.md)と[14 ライフサイクル](14-sakana-lifecycle.md): 同一の envelope と未解決試行の保全。

SCI-05 の完全な起動拒否、SCI-04/20 の復旧、その他すべてのランタイム受け入れは、本変更では未実装・未実行です。既存の design-1、evaluation-protocol/1、harness-handoff/1、verification-contract/1、verification-report/1、run-record の形は変更しません。

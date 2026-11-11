# 契約の状態

[English](README.md)

JSON Schemaは設計契約で、ランタイムや許可エンジンではありません。CPU例は無効で、実entrypoint・主体・接続先を持ちません。

実装では、実許可と期限、固定ハッシュ・権限、隔離、空き資源とOS制限、総予算予約、データ分割権利、評価主体、状態遷移、取消、秘匿書出を別に強制します。JSON Schemaだけでは保証できません。

run記録は欠測・未確認・判断不能を許し、プロセス完了から科学的成功を推定しません。ハッシュと測定受領も独立確認が必要です。

## 補完契約（設計のみ）

- [handoff.schema.json](handoff.schema.json)：`harness-handoff/1`の参照型message。[例](../examples/handoff.synthetic.json)は合成・2000年に期限切れ・未解決IDと0埋めhashで、配送しない。
- [evaluation-protocol.schema.json](evaluation-protocol.schema.json)：`evaluation-protocol/1`。推定対象・接触・条件・run・予算・解析を固定。[例](../examples/evaluation-protocol.synthetic.json)は無効の探索計画で、記号hashは実データではない。4試行×300秒＋評価／cleanup600秒で、例の総枠1,800秒に収まる。

`design-1`を補完し、自動移行しない。実装側で実hash、条件ID一意・baseline一つとcandidate一つ以上、group分離と接触、run数／再試行／予算、受領issuerを検証し、期限切れ・未認可実行を拒否。算術・時刻順序・参照実在・記録間一致はJSON Schema外の意味検査。formatを有効にし、重複JSONキー・非有限数を拒否。固定local schemaだけを読み、remote `$ref`を解決しない。[受け渡し仕様](../docs/11-harness-boundaries.ja.md)と[評価受入](../docs/12-protocol-and-acceptance.ja.md)を参照。

## 検証契約（既存を補完する設計）

- [verification-contract.schema.json](verification-contract.schema.json)、`verification-contract/1`：[無効の合成例](../examples/verification-contract.synthetic.json)。既存の`design-1`計画と`evaluation-protocol/1`を不変参照で結び、固定仕様、依存／定義の完全な閉包、評価器、toolchain、環境、置換可能な候補componentとinterface、費用モデル、範囲付き主張義務を固定します。`formal_proof`義務では定理manifest、仮定、axiom方針、信頼する検証器も必須です。
- [verification-report.schema.json](verification-report.schema.json)、`verification-report/1`：[無効の合成例](../examples/verification-report.synthetic.json)。正確な契約、候補／設定、run／attempt、入力／依存、評価器／toolchain／環境、発行者、発行時刻を証拠・結果・範囲付き主張へ結びます。成功した形式主張では定理、仮定、axiom監査、証明artifact、toolchain、独立検査受領と検査範囲を必須とします。失敗／不確定の形式主張で資料が不足している場合は`formal_evidence`を省略でき、記載する場合は完全な規定構造に従います。未完了の検査を構造適合させるために参照を捏造しません。

新しい参照はすべて`{id, sha256}`です。実行時に既存アクセス制御の下で解決し、実bytes・期待する文書版／型を照合し、契約・計画・評価計画・受領間の一致を検査します。契約の`experiment_plan`は`design-1`、`evaluation_protocol`は`evaluation-protocol/1`、受領の`contract`は`verification-contract/1`を参照します。依存閉包は主張に必要な推移的定義とimport依存をすべて含む不変manifestで、最上位import一覧だけではありません。IDを取得命令として扱いません。hash・正規化は[11](../docs/11-harness-boundaries.ja.md)に従い、この検査スクリプトではJCSもartifact解決も実装しません。

`allowed_replacements`は候補が所有する実装componentと固定interfaceだけを列挙します。文字列は書込み権限を与えません。信頼する受付／評価実装は、信頼する仕様、定理、仮定、依存閉包、評価器、toolchain、環境、費用モデルと重なる置換、shadowing、import解決変更、実質的な再定義を拒否します。正当な信頼領域変更も新たなレビュー済み契約が必要で、候補による上書きは禁止。候補評価前に契約を固定し、発行元を確認します。

費用モデル参照は単位、集計範囲、workload／入力領域、実測または形式的費用の意味、正しさの前提、閾値を固定します。形式モデルで狭い操作回数の上限を証明しても、実時間・予約・失敗試行・検証費用は別に予算管理します。主張IDは一意で事前の義務に対応し、全体成功には必要な義務の充足が必要です。欠落、差替え、範囲外、矛盾した主張を実行時に拒否し、結合した入力の変更時は受領を再利用できません。

形式受領は候補の制御外にある信頼する検証過程から発行します。その過程は固定定理文と推移的定義を独立に照合し、許可axiom／仮定を監査して、受入済みtoolchainで証明artifactを検査します。この独立性は候補とその書込み領域からの独立で、科学的な独立レビューとは限りません。artifact不足や発行者不明では成功を受入しません。形式証明は仮定の下での形式文だけを保証し、外界の科学的真理、新規性、実測性能を保証しません。

合成受領例は`inconclusive`に制限し、意図的に解決不能なゼロhash、空の証拠、未実行runを使います。`passed`を含む他の構造適合受領も、意味的検査が終わるまでは未信頼の主張です。JSONは権限や評価器隔離を成立させません。[オフライン文書検査](../scripts/README.ja.md)の成功も実行時受入ではありません。

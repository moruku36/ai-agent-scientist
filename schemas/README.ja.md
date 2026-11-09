# 契約の状態

[English](README.md)

JSON Schemaは設計契約で、ランタイムや許可エンジンではありません。CPU例は無効で、実entrypoint・主体・接続先を持ちません。

実装では、実許可と期限、固定ハッシュ・権限、隔離、空き資源とOS制限、総予算予約、データ分割権利、評価主体、状態遷移、取消、秘匿書出を別に強制します。JSON Schemaだけでは保証できません。

run記録は欠測・未確認・判断不能を許し、プロセス完了から科学的成功を推定しません。ハッシュと測定受領も独立確認が必要です。

## 補完契約（設計のみ）

- [handoff.schema.json](handoff.schema.json)：`harness-handoff/1`の参照型message。[例](../examples/handoff.synthetic.json)は合成・2000年に期限切れ・未解決IDと0埋めhashで、配送しない。
- [evaluation-protocol.schema.json](evaluation-protocol.schema.json)：`evaluation-protocol/1`。推定対象・接触・条件・run・予算・解析を固定。[例](../examples/evaluation-protocol.synthetic.json)は無効の探索計画で、記号hashは実データではない。4試行×300秒＋評価／cleanup600秒で、例の総枠1,800秒に収まる。

`design-1`を補完し、自動移行しない。実装側で実hash、条件ID一意・baseline一つとcandidate一つ以上、group分離と接触、run数／再試行／予算、受領issuerを検証し、期限切れ・未認可実行を拒否。算術・時刻順序・参照実在・記録間一致はJSON Schema外の意味検査。formatを有効にし、重複JSONキー・非有限数を拒否。固定local schemaだけを読み、remote `$ref`を解決しない。[受け渡し仕様](../docs/11-harness-boundaries.ja.md)と[評価受入](../docs/12-protocol-and-acceptance.ja.md)を参照。

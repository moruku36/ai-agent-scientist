# 02 研究の下地

[English](02-research-foundations.md) | [ホーム](../README.ja.md)

以下の6件は研究ノートへ保存済みです。2026-11-09にノートと一次資料を参照して設計し、再現実験はしていません。発想を取り入れることと、上流コードを依存採用することは別です。

| 出典 | 関連する知見 | 今回取り込むもの | 限界 |
|---|---|---|---|
| [The AI Scientist](https://arxiv.org/html/2408.06292v3)、[記事](https://sakana.ai/ai-scientist/) | MLテンプレートから着想・実装・実験・執筆・自動査読を接続。 | 各段階の成果物と、測定結果を主張へ結ぶ確認。 | 分野・初期コードは人が用意。誤りが残り、自動査読は独立した科学的受入ではない。2024版とv2を混同しない。 |
| [自律ML開発と簡素なハーネス](https://arxiv.org/html/2609.40303v1) | ML課題で長時間の単一エージェントと複雑な構成を比較。 | 実行・証拠管理の整った単一ワーカーを基準にする。 | 対象モデル・課題・計算量に限定。有意差なしは普遍的同等性や統制不要を意味しない。 |
| [自由なAI研究の評価](https://arxiv.org/html/2607.27191v2) | 2件のshadow evaluationで実装完了と研究の前進を分離。 | 節目の研究評価、代替仮説、打切り・戻り条件。 | 少数例。全AIが研究できないとも、レビュー追加で解決するとも断定しない。 |
| [Evolving Agent Teams](https://arxiv.org/html/2610.36848v1) | 停滞時に役割を再構成し、成果物・履歴を引き継ぐ。 | 実装・測定・批判のどれが不足か診断し、必要な役割だけ追加。 | GPU課題・少数試行。基準構成やモデル記述の不一致が因果解釈を制約。 |
| [DGM](https://arxiv.org/html/2505.22954v3)、[記事](https://sakana.ai/dgm/) | 候補を保存してエージェントのコード変更を探索。基盤重みは固定。 | 系譜、再現可能な比較、保護した評価器。 | 無制限自己改善の証明ではない。得点操作を検査し、本番統括器を自己変更させない。 |
| [AB-MCTS](https://arxiv.org/html/2503.04412v5)、[記事](https://sakana.ai/ab-mcts/) | 外部評価で新候補生成と既存案改善に計算を配分。 | 予算内の任意分岐、候補発見と最終選択の指標分離。 | 有用な評価が必要。研究上の価値はそのまま探索報酬にできず、生成追加にも費用がある。 |

## 保存済みノート

`moruku36/independent-tech-research-notes` 内の日本語版です。

- [AI Scientist](https://github.com/moruku36/independent-tech-research-notes/blob/main/surveys/coding-agents/2024-sakana-ai-scientist.ja.md)
- [簡素なMLハーネス](https://github.com/moruku36/independent-tech-research-notes/blob/main/surveys/coding-agents/2026-ml-engineering-minimal-harness.ja.md)
- [自由な研究の評価](https://github.com/moruku36/independent-tech-research-notes/blob/main/surveys/agent-safety/2026-open-ended-ai-research-shadow-evaluation.ja.md)
- [Evolving Agent Teams](https://github.com/moruku36/independent-tech-research-notes/blob/main/surveys/coding-agents/2026-evolving-agent-teams.ja.md)
- [DGM](https://github.com/moruku36/independent-tech-research-notes/blob/main/surveys/coding-agents/2025-sakana-darwin-godel-machine.ja.md)
- [AB-MCTS](https://github.com/moruku36/independent-tech-research-notes/blob/main/surveys/llm-infrastructure/2025-sakana-adaptive-branching-mcts.ja.md)

## 統合と導入方針

6つのフレームワークを同時導入せず、工程と外部証拠から始めます。自作は台帳、検証、実行上限、決定論的評価に絞り、エージェント基盤は既存DOTS／Codexを使います。今回、上流のscientist／探索基盤はインストールしません。

追加層は同じモデル・課題・資源・終了条件で比較。安価で反復可能な開発指標がある場合だけ、候補保存・木探索へ進みます。研究の重要性と新規性は明示的なレビュー対象。否定的結果、再現失敗、棄却仮説も成果として残します。

コード採用時は版・依存・ライセンス・互換性を固定します。論文内のモデル・機材は実験条件であり、現在の推奨や購入指示として扱いません。

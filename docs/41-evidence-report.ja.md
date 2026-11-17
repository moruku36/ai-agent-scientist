# 41 非公開エビデンスレポート

[English](41-evidence-report.md) | [ホーム](../README.ja.md)

**Scientist30 P2 evidence-to-report audit: ソース、自己完結した unittest
メソッドちょうど4件、日英文書を作成済み。NOT EXECUTED（未実行）。**
file-only 指示に従い、テスト、設計・リンク・言語ペア・JSON・状態整合性を含む
チェック、import、build は実行していない。実行・再現・独立レビュー・runtime
受入れは保留。科学実験、評価器、network、モデル/API、deploy、子起動は行っていない。

[ソース](../src/ai_agent_scientist/records/evidence_report.py) と
[4シナリオ](../tests/contracts/test_evidence_report.py) は実際の
[37 パーサー](37-run-record.ja.md)、[38 非公開 blob 保存アダプター](38-run-store.ja.md)、
[39 一覧](39-attempt-inventory.ja.md)、[40 比較](40-paired-metrics.ja.md) を接続する。
[12](12-protocol-and-acceptance.ja.md) の保護評価と科学的主張の要件は別の境界にある。

`build_private_evidence_report(inventory: AttemptInventory, *, metric: str,
direction: str, max_output_bytes: int = 1048576)` は frozen・slots 付きの
`PrivateEvidenceReport(data, sha256, manifest_sha256, expected_attempts,
present_attempts, missing_attempts)` を返す。最初に上限が1..1048576の厳密な
組込み整数であることを確認し、bool は比較前に拒否する。その後、実際の29の
`compare_paired_metrics` をちょうど1回呼ぶ。一覧・record のバイト列、入れ子の型、
identity、selector の完全な再検証は29に委譲する。2度目の再構築、store 読出し、
caller が渡した比較値による迂回はない。29の例外は同一オブジェクトのまま伝播し、
再試行しない。

内部形式は `offline-evidence-report/1`、scope は
`unverified_private_local_summary`。トップには正確な manifest SHA-256、
project/protocol ID、選択した `metric`/`direction`、expected/present/missing
attempt 件数、`declared_pair_count`、`paired_observation_count` を持つ。
`attempts` は全 slot を manifest 順で保持し、`run_id`、`attempt_id`、
`replicate_id`、`candidate_revision`、`role`、`record_sha256`、`status`、
`validity`、`usage`（`wall_seconds` と `incremental_api_usd` のみ）、
`limitation_count`、選択した `metric_value` を含む。record 欠測時は limitation
件数を含む record 由来フィールドを null とし、欠測・不明 usage は0に置換しない。
他の指標名・値、自由文の limitations、元 record バイト列、artifact 参照・payload、
認可パスは含めない。

全 pair は実際の29の manifest 初出順を保持する。`replicate_id`、
`baseline_run_id`、`candidate_run_id`、`classification`、`baseline_value`、
`candidate_value`、`raw_delta`、`directional_delta` をそのまま投影する。
欠測・不適格 pair も分母に残す。結果による削除、成功順への並べ替え、勝者、
集約推定、推論、証明は追加しない。完全性は供給された manifest に対するものに限る。

以下は欠測 pair と件数を示す無効な合成抜粋。metadata と全2件の `attempts`
配列はこの抜粋だけで省略しており、返却 artifact では省略しない。

```json
{
  "format": "offline-evidence-report/1",
  "scope": "unverified_private_local_summary",
  "metric": "score", "direction": "maximize",
  "expected_attempts": 2, "present_attempts": 1, "missing_attempts": 1,
  "declared_pair_count": 1, "paired_observation_count": 0,
  "pairs": [{"replicate_id": "replicate-1", "baseline_run_id": "run-b",
             "candidate_run_id": "run-c", "classification": "missing_record",
             "baseline_value": 10, "candidate_value": null,
             "raw_delta": null, "directional_delta": null}]
}
```

UTF-8 エンコードに `allow_nan=False`、`sort_keys=True`、
`separators=(',', ':')`、`ensure_ascii=True` を使う。SHA-256 はこの正確な
バイト列に結び付き、JCS・論理的 identity ではない。上限はエンコード後の artifact
全体に適用する。超過・エンコード・overflow 失敗は固定の
`EvidenceReportRefused("evidence report refused")` のみとし、handler を抜けてから
送出して encoder cause/context を残さない。部分・切詰めレポートは返さない。
出力上限はメモリ・CPU・隔離の完全な境界でも、集約入力の上限でもない。

作成した4シナリオは、A 非公開一時 BlobStore で合成 record 2件を実際の27で
保存・読出しし、実際の28からレポートへ接続して、正確な bytes/hash/件数/差分と、
秘密の他指標、自由文、artifact 参照、保存した artifact payload の非掲載を確認
（payload は解決しない）、B candidate 欠測でも全試行・分母を保持、C 有効一覧に
1バイト上限を指定して artifact 全体を拒否、D bool 上限でパッチした29の呼出し前に
拒否、である。各メソッドの report 呼出しは1回。fixture はローカルで、過去の
テスト import、ループ、シナリオ表、subTest、追加入力 variant はない。順序はソース
から確認でき、決定性の確認用に繰り返し実行はしない。

**PRIVATE:** ID と選択した指標も機微情報になり得る。自動公開せず、実エビデンスと
traceback のローカル変数は公開 repository 外に置く。constructor は権限を与えず、
出典の status/validity は認証済み受領ではない。ヘルパーは書込、clock、storage、
network、export、認証、認可、評価を行わない。既存 DOTS/ChatGPT/Codex 制約、依存、
schema/wire version は変更しない。

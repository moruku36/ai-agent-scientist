# 38 Run-record の blob 保存

[English](38-run-store.md) | [ホーム](../README.ja.md)

**Scientist27: ソース、自己完結した unittest メソッドを正確に4つ、日英文書を
作成済み、NOT EXECUTED（未実行）。** 狭い [P1 増分](10-roadmap.ja.md) として、
変更しない [Scientist26 パーサ](37-run-record.ja.md) を既存の
[BlobStore](../src/ai_agent_scientist/evidence/blob_store.py) に接続する。
アーキテクチャ、schema、wire version、依存、既存ファイルは変更しない。

[ソース](../src/ai_agent_scientist/records/run_store.py) は
`store_run_record(store: BlobStore, data: bytes, *, max_bytes=1048576) -> RunRecord`
と `load_run_record(store: BlobStore, sha256: str, *, max_bytes=1048576) -> RunRecord`
を公開する。両方とも厳密な具体型 `BlobStore` と、1..1048576 の厳密な組込み整数の
上限を必須とする。storage 呼出し前に、store の設定上限も 1..max_bytes の厳密な
組込み整数であることを確認する。呼出しごとの上限を持たない実際の `get` をこれで
制限する。大きすぎる store は拒否し、置換・再設定しない。

保存は実際の26パーサで厳密な組込み bytes を storage より先にパースし、caller の
バイト上限を適用する。元の bytes をそのまま `store.put` に正確に1回渡し、返された
厳密な文字列 digest がパース済み SHA-256 と一致することを必須とする。既存 digest
の検証は `BlobStore.put` の意味を維持し、再シリアライズ・上書き・修復をしない。
読取は小文字16進64文字の厳密な組込み文字列を先に検証し、実際の `store.get` を1回
呼び、実際の26パーサでパース後、hash が要求 hash と一致することを確認する。

不正な store・digest・上限、hash 束縛の不一致は固定の
`RunStoreRefused("run store refused")` のみを返す。信頼する `put` の想定外の戻り値も
束縛の拒否となる。パーサエラーは入力を持つ decoder chain を含まず、そのまま伝播する。
storage 例外はオブジェクト同一性を含め変更せず伝播し、包み直し・再試行しない。
traceback のローカル変数には非公開 bytes が残り得るため、非公開のまま扱う。

以下の合成 JSON は要約にすぎず、null の usage は不明のまま保持する。

```json
{
  "run_id": "run-1", "attempt_id": "attempt-1", "replicate_id": "replicate-1",
  "project_id": "project-1", "protocol_revision": "protocol-1",
  "candidate_revision": "candidate-1", "status": "failed", "validity": "unchecked",
  "artifacts": [], "metrics": {"score": null},
  "usage": {"wall_seconds": null, "incremental_api_usd": null},
  "limitations": ["Synthetic; no evaluation."]
}
```

信頼前提は既存の非公開・所有者管理の POSIX filesystem profile であり、信頼する
owner/writer は1つ、root と祖先も信頼し、攻撃者の同時制御を認めない。caller が既存
store を渡し、この補助関数は構築しない。例外・束縛拒否より前に書込が commit 済みの
可能性がある。自動再試行・rollback・削除・修復はない。既知 hash の読取は観測のみで、
書込完了・耐久性の証明ではない。registry・index・論理的な冪等性・run 識別子の一意性は
提供しない。パース済みレコードは自由に構築でき、status/validity は権限を与えない。
dispatch・評価・認証・認可・evaluator の証明は追加しない。実レコードは公開 repository
の外に置く。

[テスト](../tests/contracts/test_run_store.py) は **4メソッド・合計4シナリオ** のみを
作成した。実際の非公開一時 store で null usage を保つ厳密 bytes の保存・読取往復、
不正 run-record を put 前に拒否して書込なし、不正 digest を get 前に拒否、改ざんした
実 final blob の storage integrity error を観測した同一オブジェクトのまま1回の get
で伝播して再試行なし、の4つである。過去のテストクラスや隠れた subcase はない。
file-only 指示に従い、テスト、設計・リンク・言語ペア・JSON・状態整合性を含むチェック、
import、build は未実行。実行・再現・独立レビュー・runtime 受入は保留である。
モデル・API・network・研究・子エージェント・service の実行は行っていない。

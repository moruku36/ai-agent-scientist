# ハンドオフ依頼プレフライト（P1・オフライン）

English: [20-handoff-request-preflight.md](20-handoff-request-preflight.md) · [README](../README.md) に戻る

## 状態

**実装・オフライン確認済み（2026-11-17）。** H01〜H08がPython 3.15.2で1回成功（8テスト・0.006秒）。coordinatorのソースレビューは科学的な独立再現やruntime受入ではありません。実際の依頼の受付・ディスパッチは行いません。

## 内容

`ai_agent_scientist.admission.handoff_request` は次を提供する。

- `validate_handoff_request(value, *, now)`: 構造的に妥当な `harness-handoff/1` の**request**について、切り離された通常の `dict` を返す。
- `load_handoff_request(store, sha256, *, now)`: `load_json_blob`（検証済みバイト列・厳格な UTF-8 JSON）を1回だけ呼び、その結果を検証する。

`now` は信頼できる呼び出し側が渡す `datetime` で、`tzinfo` は厳密に `datetime.timezone.utc` でなければならない。それ以外は一般的なメッセージの `TypeError` になる。

## 検査（request のサブセットのみ）

- 非信頼値は厳密な組み込み `dict`・`str`・`int`・`bool`・`None` のみ。サブクラスは拒否し、`bool` はリビジョンとして受け付けない。
- 必須のトップレベルキーとペイロードキーがすべて存在し、余分なキーがない。
- `schema_version` は厳密に `harness-handoff/1`。`kind` は `request` のみで、他の kind は明示的に拒否する。
- `attempt_id` と `in_reply_to` は `null`。`replicate_id` は `null` か空でない文字列。
- ID・参照の文字列は空でない。`sender`・`recipient`・`classification` は列挙値を確認する。`expected_revision` は 0 以上の整数。
- ペイロードのダイジェストは `[a-f0-9]{64}` に完全一致する必要があり、末尾の改行は拒否する。
- タイムスタンプは厳格なプロファイル `YYYY-MM-DDTHH:MM:SS[.1〜6桁]Z`。オフセット・うるう秒・小文字は不可で、暦と時刻は有効でなければならない。
- `created_at < expires_at` かつ `created_at <= now < expires_at`。期限が `now` と等しい場合は拒否する。

非信頼入力の違反はすべて、固定で値を含まないメッセージの `InvalidHandoffRequest`（`ValueError`）になる。例外の連鎖は抑止するが、トレースバックやフレームには非信頼データが残りうるため、機微として扱う。

## 主張しないこと

- **認可ではない。** `synthetic` は `true`/`false` どちらも受理し、どちらも何も認可しない。構造的に妥当な依頼は承認済みディスパッチではない。
- 汎用の JSON Schema エンジン**ではない**。タイムスタンプのプロファイルはスキーマの `date-time` より狭く、固定プロファイルは正本スキーマ（変更なし）から乖離しうる。
- 論理ダイジェスト、JCS 正規化、送信者認証、レジストリ、レシートは扱わない。
- URL の解析、ペイロードの解決、書き込み、スキーマ取得、ネットワークアクセスは行わない。

## 呼び出し側の責務

送信者を認証し、現在の認可・予約・ペイロード権限を解決する。ディスパッチ前に冪等性・リビジョン・予算を強制する。後続の権限確認が失敗した場合は、返されたスナップショットを破棄する。

## 復旧

ストレージ・改ざん・厳格 JSON のエラーはそのまま伝播する。検証には到達せず、何も書き込まない。証拠を保全し、フェイルクローズする。

## 検証と上限

過去テストを再実行せず、次だけ1回実行しました。

```sh
env PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/contracts -p test_handoff_request.py -v
```

H01: 実storeで正常読取・作成時刻一致。H02: 厳密型・悪意ある等値フック。H03: 版と依頼束縛。H04: payload・列挙・digest。H05: 時刻プロファイル。H06: 期限・順序・信頼時計。H07: 実際の欠落／改ざんと不正／重複JSONが検証前に停止。H08: 切り離しコピー・読取によるバイト不変・公開エラーの値非露出・認可フラグなし。

保存envelopeはBlobStoreのバイト上限に従います。直接検証にはバイト／文字列上限がなく呼び出し側で制限が必要です。両入口ともCPU・メモリ・深さを隔離しません。payload参照は構造検査のみで、参照先の読取・media typeの確認はせず、利用不能でもありえます。厳密バイトの同一性を保ち、論理同一性や重複排除は計算しません。syntheticの両値とも未解決参照で通過しえます。有効期限後の再利用には現在の正本確認が必要です。UTC時計の信頼と巻き戻りは呼び出し側の責務です。日付解析の表示上の例外連鎖は抑止しますが、context／frameには入力が残りえます。上流エラーは元の診断を保持します。

根拠: [P1計画](10-roadmap.ja.md)、[ハンドオフ契約](11-harness-boundaries.ja.md)、[不変の正本schema](../schemas/handoff.schema.json)、[厳格リーダー](19-json-blob-reader.ja.md)。内部profileは初回requestだけを意図的に対象にし、正本のすべての有効envelopeは受け付けません。

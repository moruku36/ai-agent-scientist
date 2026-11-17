# 30. 復旧オペレーターキュー（非公開・未実行で作成）

[English](30-recovery-queue.md) · [29 コンソール](29-recovery-console.ja.md) の拡張。

`recovery_console.py` の `render_recovery_queue(receiver, *, reasons, ...)` は最大 `max_pages` ページ（`page_limit` 1..100、`max_pages` 1..10）の実レポートを走査し、指定した既知の保守的トリアージ理由のいずれかを持つ項目を表示します（理由は重複なしの空でないタプル）。

- ページごとに接続済み `build_recovery_report` を1回呼びます。各ページは別個の読み取りスナップショットで、ページ間の整合性や会計の合算はなく、書き込み・ディスパッチ・予算解放はしません。
- ヘッダにはページごとの元レポート SHA-256 を表示します（表示テキストのハッシュではありません）。
- `next_after_request_id` は最後に走査したページのカーソルで、最後に表示した要求IDではありません。`reached_end` は最後に観測したページのみを指します。
- 一致なしは受信側が空という意味ではありません。UNKNOWN は 0 ではありません。
- 後続ページの失敗、カーソルが進まない場合、バイト超過は全体失敗で、部分表示は返しません。

権限はありません。`tests/contracts/test_recovery_queue.py` は作成のみで未実行です。

# 21 ハンドオフのペイロード束縛（P1・オフライン）

[English](21-handoff-payload-binding.md) | [ホーム](../README.ja.md)

**状態（2026-11-17）：実装済み。新規P01〜P10のunittestシナリオ10件が1回オフライン成功（0.074秒、Python 3.15.2）。** coordinatorは対象テスト前にソースレビューを完了しました。必須設計検査の結果は別途記録します。過去テストは再実行していません。研究依頼の受付・ディスパッチ・再現・独立レビューは行っていません。Python 3.12互換はソースの目標であり、その版での実行確認ではありません。

この限定的な接続は[20 依頼preflight](20-handoff-request-preflight.ja.md)と[18 BlobStore](18-immutable-blob-helper.ja.md)を合成します。既存の[全体構成](03-architecture.ja.md)と[実装計画](10-roadmap.ja.md)の範囲内で、[11 ハンドオフ契約](11-harness-boundaries.ja.md)のローカルなペイロード束縛部分だけを実装します。[正本harness-handoff/1 schema](../schemas/handoff.schema.json)は変更しません。

## 明示的なAPI

[ソース](../src/ai_agent_scientist/admission/handoff_binding.py)：

```python
load_bound_handoff_request(
    request_store, request_sha256, *, payload_store, bindings, now
) -> tuple[dict, bytes]
```

- 両storeは厳密に`BlobStore`の実体とし、信頼する呼び出し側が依頼内容とは独立に選択・設定します。envelopeとpayloadには別store・別上限を使えます。サブクラスやduck typingのadapterは対象外です。
- `bindings`は、現在の信頼できる組込み`dict[str, PayloadBinding]`です。無関係なキーも含め全キーが厳密な組込み文字列である必要があります。依頼のpayload IDは不透明な検索キーにすぎず、パス・URI・ネットワーク宛先・root・store選択に使いません。resolver callbackや参照先取得へのfallbackはありません。
- `PayloadBinding`はfrozenのローカルdataclassです。`id`・`sha256`・`media_type`・`classification`・`max_payload_bytes`・`available`・`access_expires_at`の7項目がすべて必須です。wireオブジェクトや資格情報ではありません。呼び出し側が候補の制御外で表を所有し、対象store・project・recipient・目的に範囲を合わせてから呼びます。
- `now`は今回の呼出し用に信頼する呼び出し側が渡す、厳密な`datetime`で、`tzinfo is timezone.utc`が必要です。システム時計は読みません。`access_expires_at`も同じ厳密なUTC型が必要です。
- 戻り値は既存preflightが返す切り離された通常の依頼dictと、実際のpayload `BlobStore.get`が返す厳密で不変のbytesです。binding記録・保存したアクセス判定・受付／認可フラグ・受領は返しません。payloadを復号・正規化しません。

## 拒否と読取の順序

1. 不正な時計／store引数型はI/O前に、固定メッセージの`TypeError`で拒否します。
2. 既存`load_handoff_request(request_store, request_sha256, now=now)`を1回呼びます。上限付き・digest検証済みのenvelope読取、[厳格JSON](19-json-blob-reader.ja.md)、依頼構造と現在のenvelope期限検査を維持します。失敗時はbinding検索・payload読取へ進みません。
3. 検索前に表とキーの型、比較前に選ばれたbindingと値の型を検査します。ID・SHA-256・media type・classificationの4項目すべての厳密一致を要求します。大小文字の変換やMIME推論はしません。
4. `max_payload_bytes`は厳密な組込み整数で1以上（bool不可）、かつ`payload_store.max_blob_bytes`と一致する必要があります。この新しい読取専用propertyは既存の設定上限を公開するだけで、保存動作は変えません。上限不一致は黙って緩和せず拒否します。適切な上限のstoreは呼出側が準備し、依頼は選択できません。
5. `available is True`かつ`now < access_expires_at`を要求します。binding欠落、取消／利用不能、期限の欠落／不正、nowと同時の期限、期限切れは、監査用bytesが残っていてもpayload `get`前に拒否します。
6. その後だけ`payload_store.get(binding.sha256)`を1回呼びます。BlobStoreは読取中に上限（最大cap+1 bytes）を強制し、SHA-256を検証して返します。過大なオブジェクトは既存`BlobTooLarge`になります。

毎回、すべての検査と実際の検証付き読取を繰り返します。以前の成功でアクセスが継続することはありません。binding違反は`InvalidHandoffBinding(ValueError)`と固定の公開メッセージ`invalid handoff payload binding`になり、表示上の例外連鎖を抑止します。envelope・厳格JSON・基盤ストレージの例外は変更せず伝播し、I/Oを欠落やbinding拒否へ置き換えません。storeへの書込・修復・削除・cache・証拠変更はありません。traceback／contextと上流診断は入力を保持しうるため非公開で扱います。

## 合成宣言例

次のJSONは信頼する呼出側metadataの説明であり、ハンドオフschemaの追加項目・実アクセス状態・MIME検証・認証証明ではありません。digestは空bytesを示し、IDとmetadataはenvelopeの既存`payload`と厳密一致する必要があります。呼出側はJSON文字列ではなくUTC `datetime`を期限として`PayloadBinding`を構築します。この例をdecodeするだけでは信頼されません。

```json
{
  "id": "payload-1",
  "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "media_type": "application/octet-stream",
  "classification": "synthetic",
  "max_payload_bytes": 32,
  "available": true,
  "access_expires_at": "2026-11-17T12:01:00Z"
}
```

信頼する`now=2026-11-17T12:00:00Z`なら期限内です。`12:01:00Z`には空blobが保存されていても拒否します。`text/plain`宣言が非テキストbytesと一致することもあります。metadataは信頼する呼出側の宣言で、内容判定・schema検証・アクセス権の証明ではありません。envelopeの`synthetic`は両値とも構造的に通過しえますが、何も許可しません。

## 1回オフライン実行したシナリオ

[新規テスト](../tests/contracts/test_handoff_binding.py)は計10メソッド、決定論的なsubcaseを含み、過去テストをimportしません。

| ID | 内容 |
|---|---|
| P01 | 実store／envelope、厳密bytes、各境界1読取。両synthetic値・全classification・MIME判定しない宣言 |
| P02 | binding欠落とID・digest・media type・classificationの独立差替えをpayload読取前に拒否 |
| P03 | 成功後の取消・期限切れ／一致・後の注入時刻・binding削除。1マイクロ秒後の有効境界 |
| P04 | envelope欠落／改ざん、不正／重複JSON、request以外・期限切れをbinding／payload処理前に停止 |
| P05 | 実payload欠落／改ざんと注入I/Oエラー。例外伝播・証拠不変 |
| P06 | 必須の厳密な正の上限、store上限不一致、読取専用property、空／上限ちょうど成功、実cap+1拒否 |
| P07 | 悪意ある比較／真偽値・サブクラス・不正なUTCアクセス期限・表キーを安全に拒否 |
| P08 | 不正な注入時計／store型をenvelope・payload I/O前に拒否 |
| P09 | URL／file／path／store風IDはローカル表だけで検索。開いたdigestパスを確認しnetwork helperを禁止 |
| P10 | 依頼・結果bytesの切り離し、毎回の読取、追加権限項目なし、成功後の改ざん検出 |

ソースレビュー後、coordinatorは以下の対象テストを1回だけ実行しました。必須の設計checkerは既存の検証環境を使い、新規installはしません。実装担当は両コマンドを実行していません。

```sh
env PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/contracts -p test_handoff_binding.py -v
/Users/moruku36/.openclaw/workspace-kurotchi-work/.dev-tools/scientist-validation-20261117/bin/python -B scripts/check_design.py
```

過去の依頼／JSON／blob／予算テストは再実行しません。実際の結果は別途記録します。作成済みケースやオフライン設計検査だけではSCI runtime受入にはなりません。

## 限界と呼出側の責務

呼出側が実際に現在のアクセスmetadata・信頼できる新しいUTC時刻・独立に選んだstoreを渡します。呼出し中の表／store設定変更は直列化が必要です。単一所有者のオフライン接続であり、原子的な取消serviceではありません。古い表、信頼側の虚偽、時計巻戻り、渡された時刻後の取消を検出できません。戻ったsnapshotはデータであり持続する権限ではなく、後続利用には実policyに従う現在の確認が必要です。store実体／methodとroot／祖先はdocs 18のPOSIX前提の下で信頼します。

認証・認可証明・identity／revision確認・永続受付・冪等性・予約／予算権限・dispatch・評価／知識昇格・JCS・schema／wire版変更はありません。metadata一致はMIMEやpayloadの意味を証明しません。CPU／メモリ／深さの隔離、同時writer保証、停電／復旧の新しい保証もありません。既存request profileの限界を継承します。非公開アクセス表・実証拠・資格情報・最終解答は公開repositoryへ置きません。巻戻し時は本接続の利用を止め、全blobを保全し、現在のアクセス確認を迂回しません。

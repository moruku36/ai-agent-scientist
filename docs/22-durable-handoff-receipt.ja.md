# 22 永続する厳密バイト束縛ハンドオフ受領（P1・オフライン）

[English](22-durable-handoff-receipt.md) | [ホーム](../README.ja.md)

**状態（2026-11-17）：実装済み、新規D01〜D10の10シナリオが1回オフライン成功（1.172秒）。** 実装者はテスト・設計checker・実行目的の実装import・研究・dispatchを実行していません。coordinatorのソースレビューと対象実行1回は完了し、必須設計検査の結果は別途記録します。再現・独立レビュー・runtime受入・電源断の結果は主張しません。Python 3.12互換はソース上の目標のみです。

[P1](10-roadmap.ja.md)の狭い接続点として、実際の[21 束縛loader](21-handoff-payload-binding.ja.md)、[20 依頼preflight](20-handoff-request-preflight.ja.md)、[19 厳格reader](19-json-blob-reader.ja.md)、[18 BlobStore](18-immutable-blob-helper.ja.md)を標準ライブラリSQLiteへ接続します。アーキテクチャと正本の[harness-handoff/1 schema](../schemas/handoff.schema.json)は変更しません。

## docs11の一部と所有権

[11](11-harness-boundaries.ja.md)のうち、受信者が所有するローカル受領保存と未解決マーカーだけを実装します。同一性は実loaderが検証した**元のenvelopeの厳密バイトに対する`request_sha256`**です。デコードした値やキーを並べたJSONからdigestを計算しません。空白・キー順序・message ID・作成時刻・期限など、同じrequestキーのどのバイト変更も衝突です。transport項目を除外するdocs11全体の論理依頼同一性、RFC 8785 JCS、受付・予約・outbox配送・attempt・fencing・retry・精算は未実装です。これは内部metadataで、新しいwire応答や保護された評価器の受領ではありません。

信頼する呼出側が、envelopeから独立して非公開DBパスと`TrustedHandoffScope(principal, project_id, sender, recipient)`を指定します。`principal`は別途認証したidentityについての**呼出側の申告**です。本moduleは認証せず、**sender真正性を主張しません**。wireの`sender`は論理endpointにすぎず、project・recipientとともに指定mappingへ厳密一致する必要があります。候補入力からmapping・パス・store・アクセス表を作ると信頼境界が失われます。

依頼キーは`(principal, project_id, recipient, request_id)`です。`(principal, project_id, recipient, message_id)`も一意にし、別request／digestへの配送ID再利用を拒否します。senderは保持してmappingと照合し、別namespaceにはしません。異なる信頼principal・project・recipientは別scopeです。principal申告の変更は呼出側の権限判断であり、senderの認証ではありません。

## 明示するローカルAPI

[ソース](../src/ai_agent_scientist/admission/durable_handoff.py)：

```python
scope = TrustedHandoffScope(principal, project_id, sender, recipient)
receiver = DurableHandoffReceipts(db_path, scope=scope)
receipt = receiver.record(
    request_store, request_sha256,
    payload_store=payload_store, bindings=current_bindings, now=fresh_utc_now,
)
retained = receiver.inspect(request_id)  # DurableReceipt または None。metadataのみ
unresolved = receiver.require_reconciliation(
    request_id, expected_revision=receipt.revision, now=fresh_utc_now,
)
```

`scope`は厳密な凍結ローカルdataclassです。4項目とrequest／message ID・参照IDは、空でない厳密な組込みstr、有効なUTF-8、NULなし、UTF-8で1024バイト以下に限ります。endpointは正本のrole enumです。パスは厳密な組込みstrの絶対ローカルパスで、NUL・`..`要素を拒否し、SQLite URIモードを無効にします。SQLは内部固定文と束縛値だけです。ネットワーク・信頼できないSQL／パスresolverはありません。

`now`は厳密な`datetime`で`tzinfo is timezone.utc`とします。呼出側は毎回、新鮮で信頼できる時刻、現在のscope付きbindings、独立選択した厳密な`BlobStore`を渡します。`record`は**作成・再送の毎回**、受領transactionを開く前に`load_bound_handoff_request`を呼びます。上限付き検証済み厳格JSON envelope読取、実際の依頼preflight／期限、現在のbinding一致・アクセス・cap、実際のpayloadバイト検証を通し、payloadバイトは破棄します。scopeと初期revisionも確認します。DBからpayloadを返さず、受領の存在を現在のアクセス権にしません。

初回envelopeはboolを除く厳密な組込みintの`expected_revision=0`だけを受け付け、revision **1**、状態**`recorded`**を作ります。同一バイトの再送は、時刻・未解決マーカーを含む現在の永続受領を返し、リセット・増分を行いません。同じrequestキーの別バイトとmessage衝突は`ReceiptConflict`です。dispatchも予約も行いません。

`require_reconciliation`はwire依頼から独立した受信者ローカルCASです。`recorded` revision 1 → `reconciliation_required` revision 2だけを許可し、両方とも未解決です。存在しない／古いrevisionは`ReceiptRevisionError`、現在revisionでの繰返し遷移は`InvalidReceiptTransition`です。逆行・暗黙retry・取消・完了・精算はありません。revisionは厳密な組込みintの`0..2**63-1`で、bool・派生型を拒否し、最大値の増分はSQLiteへ渡す前に拒否します。遷移の時刻逆行も拒否します。新しいreceiver instanceでも同じ状態を再開します。

`inspect`とローカル照合マーカーは、envelope／アクセスの期限切れ・失効後も保持metadataだけを扱えます。blobアクセス・認可・継続権限は付与しません。後の`record`は依然として現在の全検査を繰り返し、受領が存在しても期限切れ・失効・利用不能を拒否します。

## 合成した保持metadata例

これはローカル受領snapshotの例で、正本envelope・認証証拠・dispatch許可ではありません。digestは合成placeholderで、実APIは凍結した`DurableReceipt`を返します。

```json
{
  "principal": "trusted-local-principal", "project_id": "p1", "recipient": "ctf",
  "request_id": "r1", "sender": "scientist", "message_id": "m1",
  "request_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "payload_sha256": "1111111111111111111111111111111111111111111111111111111111111111",
  "revision": 2, "state": "reconciliation_required",
  "recorded_at": "2026-11-17T12:00:00.000000Z",
  "updated_at": "2026-11-17T12:00:02.000000Z"
}
```

内部SQLite表には、この固定digest・identity・受領metadataだけを保存します。主／一意キーと2状態のrevision制約を持ちます。envelope／payloadバイト、認可／予約レコード、認証情報は保存しません。予算・受付・dispatch・評価器／知識昇格の権限はありません。

## transaction・失敗・ローカル信頼

操作ごとにローカル接続を開閉し、writerは`BEGIN IMMEDIATE`、readerは読取transactionを使います。SQLite lock待ちは1秒、`synchronous=FULL`です。重複／衝突確認・insert・CASをSQLite transactionと制約で直列化し、commit後だけ成功を返します。例外時は有効なtransactionをrollbackし、rollback／close失敗はエラーやnoteで報告して成功扱いにしません。`sqlite3.Error`とfilesystemエラーは、非公開のcauseを持つ`ReceiptStorageError`になります。既存loaderのエラーはそのまま伝播し、新規受領行を作りません。commit・接続・cleanup失敗後の観測結果が不確かな場合は、DBを保持してinspect／現在検査を通す再送で照合し、不在を仮定したりdispatchしたりしません。手動復旧・削除・修復は実装しません。

POSIXのDB親ディレクトリは事前に存在し、現UID所有かつgroup／otherの全permission bitなし（通常0700）を要求します。DBがなければ0600で排他的に作成します。既存DBは同UID所有・非公開・通常ファイル・symlinkでない・link数1を要求します。祖先が実ディレクトリかを確認し、同一receiverの生存中のinode差替えを拒否します。これは設定誤りの検査であり、**悪意のあるDBへの防御ではありません**。全祖先・DB・SQLite journal／sidecarパス・ローカルprocess・module／store methodは候補の制御外で信頼し、並行差替え・権限変更を禁じます。呼出側が境界を構築・維持します。本moduleは実際の制御者を証明せず、DB内容・trigger・既存schemaを認証できません。ネットワークfilesystem、敵対的なファイル競合、同UID攻撃者、破損復旧・migrationの保証はありません。

envelope／payloadのmemoryは呼出側が選ぶBlobStore cap、受領IDは上記capで制限します。行総数・disk／journal容量・操作数・SQLite環境の予算は呼出側の責任です。DB全体quota・CPU／memory隔離・別binding表／BlobStoreとの一体transactionはありません。呼出側は呼出中のアクセス表／store変更を直列化します。指定時刻後の失効・古いmetadata・一般的な時計逆行は検出できません。SQLite commit／再openは保存の接続点ですが、**電源断・hardware耐久性・backupを検証した主張ではありません**。私的な実運用データは公開repoの外に置きます。利用停止時も受領・blobを保持し、retry権限を生みません。

## 1回オフライン実行した検査

[対象テスト](../tests/contracts/test_durable_handoff.py)は新規unittestシナリオmethodをちょうど10個持ち、過去テストをimportしません。

| ID | 1回オフライン成功したシナリオ |
|---|---|
| D01 | 実envelope／payload読取の接続と最小の永続受領 |
| D02 | 再open・同一再送・現在の未解決CAS・古い／繰返し遷移 |
| D03 | 空白・message／時刻／期限・検証済みpayload変更のバイト衝突 |
| D04 | message衝突・独立identity scope・sender mapping変更 |
| D05 | 初期／CAS revision・bool／派生／敵対的値・int overflow・時刻境界 |
| D06 | project／sender／recipient不一致・scope／path型・危険なroot |
| D07 | 毎回のpreflight・厳格JSON・作成前と再送時の期限／失効・保持metadata参照 |
| D08 | 実blob欠落／改竄／oversizeとI/Oエラー伝播 |
| D09 | insert／update／commit障害のrollback・ローカルlock競合・commit後close失敗の再送 |
| D10 | ローカル2接続の同一受領とCASの勝者1つ |

ソースレビュー後、coordinatorが対象を1回実行し、10シナリオが1.172秒で成功しました。必須checkerは既存環境で実行します。利用可能なJSON Schema 2020-12環境を使い、install・過去テスト再実行を行いません。実装者は以下を実行していません。

```sh
env PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/contracts -p test_durable_handoff.py -v
python -B scripts/check_design.py
```

実際の検査結果はcoordinatorレポートに保持します。設計検査は文書リンク・日英対応・JSON例／schema・状態整合の検査であり、runtime／科学的受入ではありません。

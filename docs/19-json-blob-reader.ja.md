# 19. 厳格なJSON blobリーダー

[English](19-json-blob-reader.md) · [Home](../README.md)

状態: **実装済み**。`tests/contracts/test_json_blob.py`のJ01–J08はPython 3.15.2で**1回のオフライン実行に成功**しました（8テスト、0.011秒）。Python 3.12互換はソースの目標であり、同版での実行確認ではありません。

これは入力境界に関する狭いP1の前提作業です。[不変blobヘルパー](18-immutable-blob-helper.ja.md)に保存されたJSONを厳格にデコードして読めるようにし、[ハーネス境界](11-harness-boundaries.ja.md)の重複キー・非有限数の拒否要件に対応します。レコードの受理は**行いません**。

## API(`src/ai_agent_scientist/evidence/json_blob.py`)

- `parse_json_bytes(data: bytes) -> object`: 組み込み`bytes`のみ(サブクラス、`bytearray`、`str`は`TypeError`)。
- `load_json_blob(store, sha256) -> object`: `store.get`を1回呼び、`parse_json_bytes`に渡します。書き込みや副作用はありません。
- `InvalidJSONBlob(ValueError)`: 内容を含まない汎用メッセージ。

## プロファイル(このヘルパー限定、wireバージョン変更なし)

- UTF-8のみ。UTF-8 BOM、UTF-16、UTF-32は拒否。
- JSON文法に厳密に従い、末尾の余分な内容と空入力は拒否。
- 重複キーは再帰的に拒否(エスケープ違いの同値キーを含む)。比較はデコード後のコードポイントで行い、Unicode正規化はしません。
- `NaN`、`Infinity`、`-Infinity`、無限大にあふれる浮動小数(`1e999`)は拒否。
- 整数は任意桁ですが、インタプリタの桁数上限に従います(超過は`InvalidJSONBlob`)。
- 正規化なし。ソート済みJSONはJCSではなく、エスケープされた単独サロゲートが残り得るため、I-JSON/JCS適格性はありません。

## エラー

基盤パーサ、デコード、整数桁数制限、再帰の失敗は元の例外を`__cause__`として`InvalidJSONBlob`に包みます。BOM、重複キー、非有限数の明示的検査は、原因例外を包まずに直接`InvalidJSONBlob`を送出します。包むのは`ValueError`と`RecursionError`のみで、`MemoryError`と`BaseException`は素通しです。保存層のエラー(`InvalidInput`、`BlobTooLarge`、`BlobNotFound`、`BlobIntegrityError`、`BlobIOError`)はそのまま伝播し、パースエラーに変換も隠蔽もしません。読み取り失敗後にパースは実行されません。

公開メッセージは汎用ですが、連鎖した原因は所有者専用です。例えば`JSONDecodeError.doc`は入力を保持し得ます。トレースバックを安全なエクスポートとして扱わないでください。

## 制限

- 正確なバイト列のSHA-256は変わらず、デコード後にダイジェストは再計算しません。空白やオブジェクトのキー順だけが違う表現はバイトダイジェストが異なり、デコード結果は等しくなります。
- ハッシュはアクセス、スキーマ、意味、認証、失効を意味しません。スキーマ検証、レコード受理、レジストリ、JCS、I-JSON、SCI受理はありません。レジストリは、未決定のレコード・リビジョン・JCSの判断待ちのままです。
- バイト上限は`BlobStore`のものだけです。`parse_json_bytes`の直接呼出しにはサイズ上限がなく、呼出し側で入力バイトを制限します。どちらのAPIも深さ・CPU・メモリ隔離の上限を提供しません。
- 信頼できる呼び出し側が具体的なストアを選び、現在のアクセス権を確認します。contains、list、delete、URLの経路はありません。
- docs 18のblob上限と、信頼するシングルライターPOSIXの前提を引き継ぎます。

## 実行済みシナリオ（1回の実行）

J01 往復、J02 重複キーとキー非漏えい、J03 非有限数、J04 エンコーディングとBOM、J05 不正入力・厳密な型・原因連鎖、J06 欠落・改ざんでパースしない、J07 サイズ超過とI/Oエラーの伝播、J08 ダイジェストは異なりオブジェクトは等しい・読み取り専用・再帰の包み込み。

研究の実行は含みません。

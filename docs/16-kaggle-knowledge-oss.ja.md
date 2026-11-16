# 16 Kaggleで必要になる知識とOSS候補

[English](16-kaggle-knowledge-oss.md) | [ホーム](../README.ja.md)

**2026-11-16の設計案です。** [15](15-kaggle-competitions.ja.md)の競技プロファイルを支える知識と、利用候補のOSSをまとめます。OSSは**候補の一覧であり、導入・版固定・ライセンス確認・動作確認はしていません。** コンペの事実は15の確認範囲に基づきます。それ以外の手法の記述は一般的な知識で、今回一次資料を再確認していません。効果は各コンペのローカル評価で測るまで仮説です。

## 共通の知識

### 評価の設計

- **ローカル評価を信頼できる形にするのが最初の仕事。** テストの作り方（未出プロンプト、非公開リポジトリ、隠し課題）を真似た分割にします。分割が甘いとローカルの数値は高く出て、LBで崩れます。
- **Public LBは小さな標本。** 公開部分の件数から標準誤差を見積り、それより小さい差を改善として扱いません。Public LBへ合わせ込むと、Private LBで順位が大きく入れ替わることがあります。
- **ローカル評価とLBの相関を見る。** 少数の提出で両者が同じ向きに動くかを確認します。動かない場合は分割か前処理の差を疑い、提出を重ねる前に原因を調べます。
- **乱数と反復。** seed、fold、学習順を固定して記録し、seedを変えた反復のばらつきと候補間の差を比べます。
- **アンサンブル。** fold外予測を保存しておけば、提出せずに重み付けやスタッキングを比較できます。多様なモデルの平均は単体より安定しますが、推論時間の枠を消費します。

### コードコンペと提出

- **ネットなしの再実行。** 提出時はNotebookが隠しデータで最初から再実行されます。モデル重み、wheel、補助データはKaggle Dataset／Modelとして事前に添付し、`pip install --no-index --find-links`で入れます。
- **時間の見積。** 隠しtestの件数で推論時間を見積り、上限に余裕を残します。対話セッションのtestは数行だけなので、全量を模した入力で別に計ります。
- **形式の事前検査。** 列名、ID、欠損、ラベル集合、ファイル名、ファイル形式を提出前に機械検査します。採点エラーは提出枠を消費することがあります。
- **最終提出の選択。** 多くのコンペでは最終評価に使う提出を締切までに選びます。選択数と既定の挙動は各Rulesで確認します。
- **再現性の資料。** 入賞時にはコード・学習手順・外部データの出所の提示を求められるのが通例です。台帳と証拠の記録がそのまま使えます。

### 共通のOSS候補

| OSS | 用途 | 注意 |
|---|---|---|
| [Kaggle API](https://github.com/Kaggle/kaggle-cli)、[kagglehub](https://github.com/Kaggle/kagglehub) | データ取得、Dataset／Notebookの更新、提出、LB取得 | 認証情報は作業領域の外。提出コマンドは許可と提出台帳を通す |
| [Kaggle docker-python](https://github.com/Kaggle/docker-python) | Notebook実行環境の再現 | イメージが大きい。版はコンペ期間中も更新される |
| [uv](https://github.com/astral-sh/uv)、Docker | 依存の固定、隔離実行。PLEキットとGemmaのsandboxが前提にする | 既存サービスのDockerと作業領域を分ける |
| [scikit-learn](https://github.com/scikit-learn/scikit-learn)、[pandas](https://github.com/pandas-dev/pandas)、[Apache Arrow](https://github.com/apache/arrow) | 分割、指標、parquet入出力 | Kaggleイメージ内の版と合わせる |
| [Optuna](https://github.com/optuna/optuna) | ハイパーパラメータ探索 | 探索はfold内だけ。試行数を予算に入れる |
| [Matplotlib](https://github.com/matplotlib/matplotlib) | Writeup用の図 | 図manifestに生成元runと描画版を記録 |

実験管理の専用サービス、ベクトルDB、分散キューは追加しません。記録は既存の台帳設計を使います。

## Gemma 4 Developer Agent

### 知識

- **SWE-bench型の評価。** 課題文だけを見てリポジトリを修正し、隠したテスト（Fail-to-Pass）が通り、既存テスト（Pass-to-Pass）が壊れないことで合否が決まります。部分点はありません。
- **失敗の主な型。** (1) 修正箇所の特定ミス、(2) 編集ツールの失敗（`old_string`の不一致など）、(3) 再現せずに修正して的外れ、(4) 既存テストを壊す、(5) 同じ操作の繰り返し、(6) 時間切れでpatch未提出、(7) ツール呼出の書式崩れ。軌跡を型別に数え、最も多い型から対処します。
- **小さなモデルで効きやすい工夫。** 手順を固定する（課題文の読解→関連コードの特定→再現テスト→修正→テスト実行→`submit_patch`）、ツールの出力を短く切る、長い履歴を要約する、編集前に対象行を読み直す、早めに暫定patchを提出しておく、といった構造化です。
- **提供されるグラフ道具。** `get_code_neighbors`・`search_similar_code`・`get_code_subgraph`は呼出関係と埋め込みで位置特定を助けます。grep中心の探索と比べてどちらが正答率と時間に効くかはablationの対象です。
- **Skillの使いどころ。** ADK Skillのscriptsはsandbox内で動き、実行時間は予算から引かれます。決定的な処理（失敗テストの抽出、stack traceからの候補ファイル列挙、diffの検査）をスクリプトにし、モデルの手数を減らします。
- **LoRA学習。** 一般的な手順は、成功した修正軌跡を集めて教師あり微調整し、必要なら強化学習で伸ばすものです。学習データが公開129課題と同じ4リポジトリに偏ると、非公開リポジトリで効かない恐れがあります。他モデルで生成した軌跡を学習に使えるかはRulesで確認します。
- **推論設定。** 温度、最大トークン、文脈長、ツール呼出の書式はbase modelの想定と合わせます。量子化済みbaseでの挙動はローカル再現で確認します。
- **時間配分。** 合計12時間を課題数で割った平均と、難問に時間を吸われる分布を考え、課題ごとの上限を決めます。

### OSS候補

| OSS | 用途 | 注意 |
|---|---|---|
| [Google ADK（adk-python）](https://github.com/google/adk-python) | Agent Config（YAML）、Skill、sub-agentの仕様。提出物はADK agentへコンパイルされる | コンペは追加の制限付き。正本は`HARNESS_README.md` |
| コンペ同梱の`swegemma`・`adk-submission`・`adk-eval-core` | ローカル評価CLI、sandboxの2コンテナ構成 | 未読。Data取得後に確認 |
| [PEFT](https://github.com/huggingface/peft)、[Transformers](https://github.com/huggingface/transformers)、[TRL](https://github.com/huggingface/trl) | LoRA学習、`adapter_config.json`と`adapter_model.safetensors`の出力 | 提出形式はsafetensorsのPEFT LoRA |
| [Unsloth](https://github.com/unslothai/unsloth) | 少ないGPUメモリでのLoRA学習 | Gemma 4対応と出力の互換性は未確認 |
| [vLLM](https://github.com/vllm-project/vllm)、[llama.cpp](https://github.com/ggml-org/llama.cpp) | ローカルでのGemma推論、LoRA付き提供 | 採点環境と同じ量子化・テンプレートになるとは限らない |
| [SWE-bench](https://github.com/SWE-bench/SWE-bench) | 評価方法の参照、追加の検証課題 | 公開課題はモデルが学習済みの恐れ。ライセンスと利用条件を確認 |
| [SWE-agent](https://github.com/SWE-agent/SWE-agent)、[mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent)、[OpenHands](https://github.com/OpenHands/OpenHands) | promptと手順、ツール設計の参照 | 提出で使えるのはコンペ提供ツールとsub-agentだけ。考え方の参照に限る |
| [SWE-smith](https://github.com/SWE-bench/SWE-smith)、[SWE-Gym](https://github.com/SWE-Gym/SWE-Gym)、[R2E-Gym](https://github.com/R2E-Gym/R2E-Gym) | 学習用課題・軌跡の生成と環境 | 生成に使うモデルの利用条件とRulesを確認。GPUと時間を大きく使う |
| [NetworkX](https://github.com/networkx/networkx)、[NumPy](https://github.com/numpy/numpy) | 同梱のコードグラフ（JSON）と埋め込み（npz）の分析 | Skill script内で使えるパッケージはsandbox次第 |
| [pytest](https://github.com/pytest-dev/pytest) | 再現テストと検証 | sandboxはPython 3.13。古いテスト向けのshimが同梱される |

## Name That LLM

### 知識

- **課題の性質。** 人間かAIかの判定ではなく、18モデルの著者識別です。話題や長さは手掛かりにならない設計なので、語彙、言い回し、句読点、書式の癖を捉えます。
- **グループ分割。** `prompt_id`でGroupKFoldにします。プロンプトをまたいで学習・検証すると話題を覚えるだけで点が出て、未出プロンプトのテストで落ちます。
- **強い基準。** 文字n-gramと単語n-gramのTF-IDFに線形分類器（ロジスティック回帰、線形SVM）を組み合わせます。学習データは2,699件と小さく、高次元の疎特徴と強い正則化が合います。
- **文体特徴。** 句読点とUnicode文字（ダッシュ、引用符、省略記号）の頻度、文長と段落構成、機能語の比率、Markdown記法の残り、書き出しと締めの定型。モデルの系列ごとに癖が出やすい部分です。
- **言語モデル由来の特徴。** 公開の小型LMで計算したトークン確率やperplexityの統計、文埋め込み。過去のAI生成文検出コンペで有効だった系統ですが、推論時間を使います。
- **微調整。** エンコーダ（DeBERTa系、ModernBERT系）の微調整や、小型LLMに分類ヘッドとLoRAを付ける方法。データが少ないのでfold間のばらつきが大きく、seedを変えた平均が必要です。
- **階層化。** 提供元（6社）→モデルの2段で分ける、同一社内の混同だけを解く専用分類器を足す、といった構成を混同行列から判断します。
- **balanced accuracyへの最適化。** 学習時のクラス重み、fold外予測でのクラス別スケール調整が候補です。テストのクラス比は不均等で公開／非公開でも異なるため、テスト分布への事前確率合わせは行いません。
- **テスト時の適応。** Notebook内でテスト文を使ったTF-IDF語彙の再学習や疑似ラベルは、過去のコードコンペで使われた手法です。規則上の可否と、クラス比の偏りによる害を確認してから比較対象にします。
- **長さへの頑健性。** 40〜250語でランダムに変わるため、学習文を途中で切る拡張で短文性能を確認します。
- **ラベルの点検。** 「軽い書式整形」以外の加工は無いとされます。重複文や極端に短い文を確認します。

### OSS候補

| OSS | 用途 | 注意 |
|---|---|---|
| [scikit-learn](https://github.com/scikit-learn/scikit-learn) | `TfidfVectorizer`、線形分類器、`StratifiedGroupKFold`、`balanced_accuracy_score` | 最初の基準はこれだけで足りる |
| [LightGBM](https://github.com/lightgbm-org/LightGBM)、[XGBoost](https://github.com/dmlc/xgboost) | 文体特徴とfold外予測のスタッキング | 小データでは過学習しやすい |
| [Transformers](https://github.com/huggingface/transformers)、[Sentence Transformers](https://github.com/huggingface/sentence-transformers) | エンコーダ微調整、文埋め込み | 重みをKaggle Dataset／Modelとして添付。ライセンス確認 |
| [PEFT](https://github.com/huggingface/peft) | 小型LLM分類器のLoRA | GPU枠と9時間以内の推論時間 |
| [RAPIDS cuML](https://github.com/NVIDIA/cuml) | GPUでのTF-IDFと線形モデル | CPUで間に合う規模なら不要 |
| [cleanlab](https://github.com/cleanlab/cleanlab) | ラベルと外れ値の点検 | 結果は確認の入口で、自動除外しない |
| [Optuna](https://github.com/optuna/optuna) | 正則化、n-gram範囲、アンサンブル重み | グループ分割のfold内だけで調整 |

## PLE Agent Harness

### 知識

- **採点の二本立て。** 数量計算・CAD／IFC形状・制約は検証スクリプト、自由記述の成果物はLLM judgeが0.0〜1.0で採点します。計算結果だけでなく、根拠条文、前提、単位、結論を成果物として整えます。
- **主催者が挙げる失敗。** 図面注記の読み違い、誤った規格条文の適用、単位換算の脱落、早すぎる終了。提出前の自己検査として、単位の整合、参照条文と版、全成果物の存在、要求項目の網羅を毎回確認する手順を入れます。
- **長時間課題の文脈管理。** 数十ファイルを読むため、最初にファイル目録と要求一覧を作り、作業メモをファイルへ外部化し、要点を引用元付きで残します。本設計の「会話の外に事実を残す」と同じ考え方です。
- **道具の使い分け。** 課題コンテナのローカルMCPサーバ（文書、表計算、メール、CAD）とシェルの両方が使えます。数値は言語モデルに暗算させず、スクリプトで計算して結果ファイルを残します。
- **図面と文書。** PDF図面は文字抽出だけでは寸法や注記の位置関係を失います。ページ画像をモデルに読ませる経路と、ベクタ／テキスト抽出の経路を突き合わせます。
- **IFCと干渉。** IFC4の成果物は、スキーマ検証、要素数、空間構造、干渉検査を提出前に機械的に確認します。
- **費用対性能。** 入賞条件はPareto前線上なので、高価なモデルで点を取るだけでなく、安いモデルで前線に乗る構成も検討対象です。検証の再試行回数、文脈長、並列度を変えた得点対費用の曲線は、Writeupの必須図にもなります。
- **3回実行の平均。** 1回の成功ではなく安定性が点になります。HTTP 400、未回復のクラッシュ、時間切れを起こさない堅牢さを先に固めます。
- **環境の制約。** インストールは`debian:bookworm`で30分以内、`/opt/harness`は圧縮後2 GiB以下で読取専用、書込みは`/tmp`と`$HOME`の1 GB、2 CPU・4 GB RAM。重い依存やローカルモデルは載りません。
- **規格と著作権。** 設計規格の本文は著作物です。Stage 2ではWeb検索が使えないため、必要な条文は課題フォルダの資料から読みます。規格本文を提出リポジトリへ同梱しません。
- **モデル間の比較。** 2系統以上のモデルで同じ変更を試し、全モデルで効く変更と片方だけの変更を分けます。採点基準の15点分に直結します。

### OSS候補

| OSS | 用途 | 注意 |
|---|---|---|
| [google-research/ple](https://github.com/google-research/ple) | キット（`kit check`、`kit artifacts`）、`eval/run.py`、8つのsample_submissions、プロトコル文書 | Apache-2.0。出発点はsubmission-templateかsample |
| Harbor（キットが`harbor==0.20.0`を指定） | dev課題の実行 | 版はキットの指定に従う |
| [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)、[websockets](https://github.com/python-websockets/websockets) | 課題のMCPサーバ呼出、評価器とのWebSocket | プロトコルの正本は`docs/protocol.md` |
| [IfcOpenShell](https://github.com/IfcOpenShell/IfcOpenShell) | IFC4の読み書き、検証、干渉検査 | LGPL系。サイズとbookwormでの導入時間を確認 |
| [ezdxf](https://github.com/mozman/ezdxf) | DXF図面の読み書き | DWGは直接扱えない |
| [pypdf](https://github.com/py-pdf/pypdf)、[pdfplumber](https://github.com/jsvine/pdfplumber)、[PyMuPDF](https://github.com/pymupdf/PyMuPDF) | PDFの文字・表抽出、ページ画像化 | PyMuPDFはAGPL系。提出物のApache-2.0／MIT要件との整合を確認 |
| openpyxl、LibreOffice（headless） | 表計算の読み書き、数式の再計算 | LibreOfficeはサイズが大きい。課題のMCPサーバで足りるか先に確認 |
| [Pint](https://github.com/hgrecco/pint) | 単位付き計算、換算ミスの検出 | 米国慣用単位とSIの混在に対応させる |
| [NumPy](https://github.com/numpy/numpy)、[SciPy](https://github.com/scipy/scipy)、[SymPy](https://github.com/sympy/sympy)、[pandas](https://github.com/pandas-dev/pandas) | 数値計算、式の検算、表処理 | 4 GB RAM内 |
| [Shapely](https://github.com/shapely/shapely)、[trimesh](https://github.com/mikedh/trimesh) | 平面・立体形状の計算、干渉の補助検査 | 精度と許容差を明示 |
| [PyNite](https://github.com/JWock82/Pynite)、[anaStruct](https://github.com/anastruct/anaStruct) | 骨組の構造解析 | 規格照査そのものは別に実装が要る |
| [pandapower](https://github.com/e2nIEE/pandapower) | 電力系統の潮流・短絡計算 | 建築電気の負荷計算・ケーブル選定は表計算が中心の場合が多い |
| [CoolProp](https://github.com/CoolProp/CoolProp)、[fluids](https://github.com/CalebBell/fluids)、[ht](https://github.com/CalebBell/ht) | 熱物性、配管圧損、伝熱 | 冷却塔・冷水配管の検討向け |
| [WNTR](https://github.com/USEPA/WNTR) | 配水管網の水理計算 | 土木の排水・給水検討向け |
| [Matplotlib](https://github.com/matplotlib/matplotlib) | 成果物とWriteupの図 | — |

sample_submissionsには既存エージェント（Hermes Agent、Pi、Antigravity CLI）のアダプタもあります。自作の小さなハーネスと既存エージェントのどちらを土台にするかは、devでの得点・費用・堅牢さで比較して決めます。

## OSS採用の規則

1. 採用時に版、取得元、hash、ライセンスを`sources/index.json`とOfflineBundleへ記録します。
2. 提出物に同梱する場合は、コンペのライセンス要件（PLEはApache-2.0／MIT、Name That LLMは無償公開）と依存のライセンスの整合を確認します。
3. 実行環境のサイズ・時間・メモリ上限に収まることを測ります。
4. 一度に一つ追加し、追加前後を同じ分割・同じ予算で比較します。効果の無い依存は外します。
5. 上の表のURLは2026-11-16に応答だけ確認しました。版、API、ライセンス、各コンペ環境での動作は未確認です。

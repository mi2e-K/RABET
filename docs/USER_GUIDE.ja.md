# RABET ユーザーガイド

このガイドは RABET 1.4.0 向けです。動画を見ながら動物行動を記録し、
複数ファイルの集計、可視化、評価者間・評価者内信頼性の確認、バウト解析、
遷移解析まで行うための基本的な使い方をまとめています。

英語版は [USER_GUIDE.md](USER_GUIDE.md) にあります。

---

## 目次

1. はじめに
2. 動画にアノテーションを付ける
3. アノテーションファイルを解析する
4. バウト解析
5. 遷移解析
6. 可視化
7. 信頼性評価
8. プロジェクトモード
9. 設定とファイル
10. トラブルシューティング
11. 引用とサポート

---

## 1. はじめに

### 1.1 RABET を入手する

最新版のバイナリは
[GitHub Releases](https://github.com/mi2e-K/RABET/releases/latest)
で公開しています。Zenodo の DOI は、引用と長期アーカイブのために用意して
います: [10.5281/zenodo.15313025](https://doi.org/10.5281/zenodo.15313025)。

| OS | ファイル |
| --- | --- |
| Windows インストーラー | `RABET-Windows-1.4.0-Setup.zip` |
| Windows ポータブル版 | `RABET-Windows-1.4.0-portable.zip` |
| macOS Apple Silicon | `RABET-macOS-arm64-1.4.0.dmg` |
| macOS Intel | `RABET-macOS-x86_64-1.4.0.dmg` |
| Linux | `RABET-Linux-x86_64-1.4.0.AppImage` |

配布版には必要な実行環境が同梱されています。通常の利用では、VLC、FFmpeg、
Python、R、scipy、コーデックパックなどを別途インストールする必要はありません。

### 1.2 起動方法

**Windows インストーラー**

1. `RABET-Windows-1.4.0-Setup.zip` を展開します。
2. `RABET-Setup.exe` を実行します。
3. スタートメニューまたはショートカットから RABET を起動します。

**Windows ポータブル版**

1. `RABET-Windows-1.4.0-portable.zip` を展開します。
2. 展開先のフォルダを開きます。
3. `RABET.exe` を実行します。

初回起動時に Windows SmartScreen が警告を出すことがあります。これは
コード署名されていないアプリでよく起こる表示です。入手元を確認したうえで、
**詳細情報** から **実行** を選んでください。

**macOS**

1. CPU に合う DMG を開きます。
2. `RABET.app` を Applications フォルダへドラッグします。
3. 「破損している」「検証できない」と表示される場合は、ターミナルで一度だけ
   次を実行します。

```bash
xattr -dr com.apple.quarantine /Applications/RABET.app
```

その後は通常どおり `RABET.app` を開けます。

**Linux**

```bash
chmod +x RABET-Linux-x86_64-1.4.0.AppImage
./RABET-Linux-x86_64-1.4.0.AppImage
```

### 1.3 初回起動時に作られるもの

RABET は初回起動時に、ユーザー設定用のフォルダを作成します。

| OS | 場所 |
| --- | --- |
| Windows | `%APPDATA%\RABET\` |
| macOS | `~/Library/Application Support/RABET/` |
| Linux | `~/.config/RABET/` |

主な中身は次のとおりです。

- `configs/`: アクションマップ、解析メトリクス、色設定
- `logs/`: トラブルシューティング用の実行ログ
- `projects/`: プロジェクトの既定保存先

ファイル選択ダイアログで最後に開いたフォルダも記憶されます。

### 1.4 画面構成

RABET の主要な作業画面は 5 つのタブに分かれています。

| タブ | 用途 |
| --- | --- |
| Annotation | 動画を開き、行動イベントを記録する |
| Analysis | 複数 CSV の集計、バウト解析、遷移解析を行う |
| Visualization | 複数個体・複数ファイルのラスタープロットを描く |
| Reliability | 評価者間・評価者内の一致度を確認する |
| Project | 動画、アノテーション、解析結果をまとめて管理する |

起動を速くするため、一部の重いタブは初めて開いたときに構築されます。最初の
クリック時だけ短い読み込み表示が出ることがあります。

---

## 2. 動画にアノテーションを付ける

### 2.1 動画を開く

動画は次のいずれかで開けます。

1. `File > Open Video`
2. `File > Open Recent Video`
3. RABET のウィンドウへ動画ファイルをドラッグ&ドロップ

`.mp4`、`.mov`、`.avi`、`.mkv`、`.webm`、`.m4v`、`.wmv`、`.flv`、`.ts`
などの一般的な動画形式に対応しています。拡張子が特殊な場合でも、ファイル
シグネチャの確認と PyAV による試験的なオープンを行うため、中身が通常の動画
であれば開けることがあります。

### 2.2 アクションマップ

アクションマップは、キーボードの 1 つのキーを 1 つの行動ラベルに対応させる
設定です。RABET 1.4.0 では、各行動に **Type** を設定できます。

| Type | 意味 | 記録のされ方 |
| --- | --- | --- |
| State (duration) | 開始と終了を持つ行動 | キーを押すと開始、離すと終了 |
| Point (instant) | 一瞬で発生する行動 | キーを押した瞬間に 1 回記録 |

グルーミング、追跡、接触のように持続時間が意味を持つ行動は State が向いて
います。ヘッドディップ、個別に数える咬みつき、区画への進入など、一瞬の発生
回数を数えたい行動は Point が向いています。

アクションマップの操作:

- **Add**: 新しいキーと行動を追加し、State / Point を選ぶ
- **Edit**: 選択した行動名または Type を変更する
- **Remove**: マッピングを削除する。記録済みイベントは削除されません

古い形式のアクションマップもそのまま使えます。単に `"key": "Behaviour"`
と書かれている項目は State として扱われます。Point 行動だけは JSON 内に
明示的な `kind` が保存されます。

### 2.3 動画操作とショートカット

| 操作 | ショートカット |
| --- | --- |
| 再生 / 一時停止 | `Space` |
| 1 ステップ進む | `Right Arrow` |
| 1 ステップ戻る | `Left Arrow` |
| 直前のアノテーションを取り消す | `Ctrl + Z` |
| 選択中のイベントを削除する | `Delete` または `Backspace` |
| ショートカット一覧を開く | `F1` |

ステップ幅と再生速度は、動画下のコントロールで変更できます。録画中は、
動画時刻に加えて、記録開始からの相対時刻も表示されます。

### 2.4 タイムドセッション

Recording controls でテスト時間を設定し、**Start Recording** を押すと
待機状態になります。実際の記録開始時刻は、開始ボタンを押した瞬間ではなく、
その後に動画が初めて動いた瞬間です。これにより、動画再生と記録時刻がずれ
にくくなります。

基本的な流れ:

1. 動画を開く
2. `00:05:00` などの形式でテスト時間を設定する
3. **Start Recording** を押す
4. `Space` で再生する
5. 行動キーを押してスコアリングする
6. 必要に応じて **Pause**、**Resume**、**Stop** を使う

設定した時間が経過すると、録画は自動で終了し、動画も一時停止します。

### 2.5 巻き戻し時の挙動

**Preserve on rewind** がオフの場合、まだキーを押している途中の State
イベントについて、再生ヘッドをその開始時刻より前へ戻すと、そのイベントは
破棄されます。早く押しすぎたイベントを取り消したいときに便利です。

オンの場合は、そのような途中イベントも保持されます。Point イベントは押した
瞬間に完了するため、アクティブキー一覧には残りません。

### 2.6 タイムライン編集

タイムラインでは、State イベントは横長のバー、Point イベントは細い目印として
表示されます。

主な操作:

- イベントをクリックして選択
- `Delete` または `Backspace` で削除
- `Ctrl + Z` で直前の記録を取り消し
- ズーム操作で密な区間を拡大

### 2.7 アノテーションの保存と読み込み

`File > Export Annotations` で、次の 3 セクションを持つ CSV を保存します。

1. メタデータ
2. イベントログ
3. 行動別サマリー

State イベントは通常 `Offset > Onset` です。Point イベントは
`Onset == Offset` として保存されます。Point の Duration は 0 ですが、
Frequency にはカウントされます。

`File > Import Annotations` で、保存済みの RABET CSV をタイムラインへ
読み込めます。既にイベントが読み込まれている場合は、置き換える前に確認
ダイアログが表示されます。

---

## 3. アノテーションファイルを解析する

Analysis タブでは、複数のアノテーション CSV を集計し、表計算ソフトや統計
ソフトに渡しやすい形にします。

### 3.1 ファイルを読み込む

**Load Files** から CSV を選ぶか、CSV をドラッグ&ドロップします。`animal_id`
はファイル名から自動的に作られます。番号を含むファイル名は自然順で並ぶため、
`RI_2` は `RI_10` より前に表示されます。

読み込んだファイルは **Files** タブで確認できます。

### 3.2 Summary タブ

**Summary** タブには、1 ファイルにつき 1 行の集計結果が表示されます。末尾に
`mean` と `SEM` の行も追加されます。

列の構成:

- `animal_id`
- 行動ごとの `<行動名> (s)`: Duration
- 行動ごとの `<行動名> (n)`: Frequency
- カスタム潜時メトリクス
- カスタム合計時間メトリクス

Point 行動は通常、Duration ではなく Frequency を見る指標です。

### 3.3 インターバル解析

**Enable interval analysis** をオンにし、秒数を指定すると、セッションを
固定長の時間ビンに分けて集計できます。結果は **Intervals** タブに表示されます。

解釈のポイント:

- Duration は重なり時間で計算されます。インターバル境界をまたぐ State
  イベントは、それぞれの区間へ分配されます。
- Frequency は開始時刻で数えます。イベントがどこで始まったかによって、
  1 つのインターバルにだけカウントされます。
- Point イベントは Duration 0 ですが、Frequency には入ります。

### 3.4 カスタムメトリクス

**Configure Metrics...** から、研究に合わせた指標を編集できます。

**Latency メトリクス** は、記録開始から特定行動の最初の発生までの時間です。
その行動が起こらなかった場合は空欄になります。

**Total-time メトリクス** は、複数行動の合計時間です。元のイベント時刻が
利用できる場合、RABET は重複区間をまとめてから合計するため、同時に起きた
行動を二重に数えません。

### 3.5 出力

- **Copy to Clipboard**: 表をタブ区切りでコピーします
- **Export Summary Table**: `summary_table.csv` を保存します。インターバル解析
  が有効なら `summary_intervals.csv` も保存します
- **Visualize**: 読み込んだファイルを Visualization タブへ送ります
- **Bout Analysis...**: バウト解析を開きます
- **Transition Analysis...**: 遷移解析を開きます

バウト解析と遷移解析は、通常の Summary / Intervals 集計とは独立した別ウィンドウ
です。開いても通常のサマリー出力は変更されません。

---

## 4. バウト解析

バウト解析は、同じ行動が短い間隔で繰り返されたとき、それらを 1 つのエピソード
としてまとめる解析です。例えば、短時間に連続する攻撃行動を「1 回の攻撃バウト」
として扱いたい場合に使います。

### 4.1 解析を開く

1. Analysis タブでアノテーション CSV を読み込みます。
2. **Bout Analysis...** を押します。
3. 対象行動にチェックを入れます。
4. **Bout criterion (s)**、つまり BCI を設定します。

同じ行動の連続イベントについて、間隔が BCI 以下なら同じバウトにまとめられます。

State イベントでは、次のイベントの onset から、現在のバウトの最大 offset を
引いた値が間隔です。Point イベントでは onset と offset が同じなので、実質的に
onset-to-onset の間隔になります。

### 4.2 BCI の決め方

BCI は直接入力できます。**Estimate BCI...** を押すと、RABET が参考値を提案
します。この値はあくまで補助であり、研究上の判断を置き換えるものではありません。

推定では、まず 2 成分の対数正規混合モデルを試し、うまく推定できない場合に
broken-stick 法へフォールバックします。イベント数が少ない場合や分布が明瞭に
二峰性でない場合は、安定した推定値が出ないことがあります。

群間比較をする場合は、同じ BCI をすべての群に適用するのが基本です。

### 4.3 Table タブ

Table タブには、選択した `(animal_id, 行動)` ごとに次の値が表示されます。

- イベント数
- バウト数
- 1 バウトあたりの平均イベント数
- バウト持続時間の平均・中央値・合計
- バウト内の実活動時間
- 平均 inter-bout interval
- セッション時間が分かる場合の Bouts/min

表はクリップボードへコピーしたり、CSV として保存したりできます。

### 4.4 Raster タブと図の出力

Raster タブでは、個体ごとのバウトが時系列で表示されます。バーの高さと色は、
そのバウトに含まれるイベント数を表します。

出力できるもの:

- バウトラスタ図: PNG / SVG / PDF
- バウト一覧: CSV

図を出力する前に **DPI** を指定できます。出力完了ダイアログは 1 秒後に
自動で閉じます。

---

## 5. 遷移解析

遷移解析は、「ある行動の次にどの行動が起こりやすいか」を見る 1 次遷移解析です。
行が antecedent、列が consequent です。

### 5.1 解析を開く

1. Analysis タブでアノテーション CSV を読み込みます。
2. **Transition Analysis...** を押します。
3. 個体、または **All animals (pooled)** を選びます。
4. Event レベルか Bout レベルを選びます。
5. 必要に応じて時間窓や self-transition 除外を設定します。

pooled 解析では、まず個体ごとに遷移を数え、その行列を足し合わせます。ある個体の
最後のイベントと次の個体の最初のイベントをつなげるような、人工的な遷移は作りません。

### 5.2 Event レベルと Bout レベル

**Event (each event)** は、記録された各イベントをそのまま 1 トークンとして
扱います。同じ行動が続けば `Attack -> Attack` のような self-transition も
現れます。

**Bout (collapse by BCI)** は、同じ行動のバーストを BCI でバウトにまとめてから、
バウト間の遷移を数えます。短い反復が多く、対角成分だけが大きくなりすぎる場合に
有用です。

### 5.3 時間窓と self-transition

**Window (s, 0=off)** を設定すると、連続するイベント間の間隔がその秒数以内
の場合だけ遷移として数えます。長い空白のあとに起きた行動を、直前行動の結果
として扱いたくない場合に使います。

**Exclude self-transitions** をオンにすると、対角成分を構造的ゼロとして扱います。
この場合、期待度数は行・列の周辺度数に合うよう iterative proportional fitting
で求めます。

### 5.4 Matrix の指標

**Show** でセル内に表示する値を切り替えられます。

| 指標 | 意味 |
| --- | --- |
| Adjusted residual (z) | 偶然期待からのずれを表す z 値。正なら期待より多く、負なら少ない |
| Conditional P(j\|i) | antecedent `i` の後に consequent `j` が来る生の確率 |
| Odds ratio (vs rest) | 他の antecedent / consequent と比べた関連の強さ |
| Counts | 観測された遷移回数 |

セルの色は常に adjusted residual z を表します。太字は `|z| > 1.96` を示し、
大標本近似ではおおよそ `p < .05` に相当します。antecedent の基数が 30 未満
のセルは不安定なので、解釈には注意してください。

### 5.5 Heatmap と CSV 出力

Heatmap タブでは adjusted residual を図として確認できます。PNG / SVG / PDF
で出力でき、DPI も指定できます。

**Export Tidy CSV (all animals)...** は、`animal_id, antecedent, consequent`
ごとの long-format CSV を保存します。観測回数、条件付き確率、期待度数、
adjusted residual、odds ratio、フラグ、レベル、BCI、時間窓が含まれます。

### 5.6 Predictability タブ

Predictability タブは、より焦点を絞った問いに答えます。

> ある target 行動のうち、指定した時間窓内に antecedent 行動が先行していた割合はどれくらいか。

設定するもの:

- target 行動
- antecedent 行動セット
- 時間窓
- target を event として扱うか、bout として扱うか
- chance correction を行うか

chance correction では、antecedent の時刻を円環シフトして、antecedent が単に
多いだけで生じる基準値を推定します。表には個体ごとの observed、chance、
above chance が表示されます。群間比較や統計検定は、エクスポート後に下流の
統計ソフトで行ってください。

棒グラフは PNG / SVG / PDF で出力できます。

---

## 6. 可視化

Visualization タブでは、複数のアノテーションファイルを横並びのラスタープロット
として表示します。

### 6.1 読み込みと絞り込み

Visualization タブで直接 CSV を読み込むことも、Analysis タブの **Visualize**
から移動することもできます。1 ファイルが 1 行になり、イベントは onset の位置に
行動ごとの色で描画されます。

右側のチェックリストで、表示するファイルと行動を切り替えられます。行動名の横の
色見本をクリックすると、配色を変更できます。

### 6.2 表示オプション

主なオプション:

- 縦グリッド・横グリッド
- グリッド色
- x 軸の最大範囲
- ファイル番号の表示
- ファイル間の区切り線
- 自動サイズ調整
- プロット外側の背景透過

行動色の設定は `configs/custom_color_map.json` に保存されます。

### 6.3 図の出力

**Export** から PNG / SVG / PDF で保存できます。PNG では DPI を指定できます。

---

## 7. 信頼性評価

Reliability タブでは、評価者間信頼性と評価者内信頼性のどちらも扱えます。
RABET は「2 つの出力を比較する」だけなので、2 人の評価者でも、同じ評価者の
2 回目のスコアリングでも使い方は同じです。

### 7.1 Summary モード

Summary モードは、Analysis タブから出力した 2 つの `summary_table.csv` を
比較します。通常は評価者ごと、またはスコアリング回ごとに 1 ファイルです。

RABET は `animal_id` で行を対応付け、メトリクスごとに次を計算します。

- ICC(2,1): two-way random、absolute agreement、single-measure の ICC
- Pearson 相関
- 平均絶対差

対応する値に個体間分散がない場合、ICC や Pearson 相関は未定義になります。
これはエラーではありません。定数同士が完全に一致していることと、相関型の統計量が
識別できることは別です。

`docs/reliability/compute_agreement.R` には、Summary モードの ICC、Pearson r、
平均絶対差を R で再現するための参照実装があります。

### 7.2 Detailed モード

Detailed モードは、同じ動画をスコアリングした 2 つのアノテーション CSV を
比較します。指定した bin width で時間を区切り、各ビンに行動が存在するかどうかを
比較します。

行動ごとに次を出力します。

- Cohen's kappa
- 名義尺度としての Krippendorff's alpha
- 生の一致率

両方の評価者で全ビンが 0 の行動では、生の一致率が 100% になることがあります。
ただし、この場合 kappa や alpha は未定義です。RABET はこれを「完全な
chance-corrected reliability」としては扱いません。

不一致レビュー表とラスタオーバーレイを見ると、片方だけ時間がずれている、特定の
行動を見落としている、カテゴリの分け方が違う、といった原因を見つけやすくなります。

### 7.3 解釈の注意

色分けは目安です。Cicchetti の ICC バンドや Landis-Koch の kappa バンドは
よく使われますが、許容できる値は行動の密度、持続時間、研究目的によって変わります。

論文やレポートでは、bin width、解析した行動、サンプル数、Summary / Detailed の
どちらで計算したかを明記してください。

---

## 8. プロジェクトモード

RABET のプロジェクトは、関連ファイルをまとめるための作業単位です。

- 動画
- アノテーション CSV
- アクションマップ
- 解析出力

**New Project** でプロジェクトを作成し、**Add Video**、**Add Annotation**、
**Add Action Map**、**Add Analysis** からファイルを追加します。追加時には、
プロジェクトフォルダへコピーするか、元ファイルへの参照だけを登録するかを選べます。

プロジェクト内の動画を選んで **Annotate** を押すと、Annotation タブに切り替わり、
録画終了後にアノテーションがプロジェクトへ保存されます。その後、自動で Project
タブに戻ります。

プロジェクトのマニフェストは変更のたびに自動保存されます。

---

## 9. 設定とファイル

### 9.1 保存される UI 設定

RABET は次のような設定を次回起動まで保持します。

- ウィンドウ位置とサイズ
- 最後に開いたタブ
- 録画時間
- コマ送り幅と再生速度
- インターバル解析設定
- Preserve on rewind の状態
- 最近開いたファイル
- ファイル選択ダイアログの直近フォルダ

### 9.2 設定ファイル

ユーザーデータフォルダには主に次のファイルが入ります。

- `configs/default_action_map.json`
- `configs/user_action_map.json`
- `configs/default_metrics.json`
- `configs/custom_color_map.json`
- `logs/rabet_<date>.log`

### 9.3 CSV 出力

RABET が出力する主な CSV:

- Annotation タブからのアノテーション CSV
- Analysis タブからの `summary_table.csv`
- インターバル解析が有効な場合の `summary_intervals.csv`
- バウト解析 CSV
- 遷移解析の tidy CSV
- 信頼性評価の結果 CSV

アノテーション CSV、summary CSV、interval summary CSV の仕様は
[CSV_FORMAT.md](CSV_FORMAT.md) を参照してください。

---

## 10. トラブルシューティング

### 動画が開けない

RABET は一般的な動画拡張子、既知の動画ファイルシグネチャ、PyAV で開ける
ファイルを受け付けます。それでも開けない場合は、FFmpeg で変換または remux
してみてください。

```bash
ffmpeg -i input.unknown -c copy output.mp4
```

### macOS で「破損している」と表示される

未署名 DMG では Gatekeeper の quarantine が原因で表示されることがあります。
次を一度だけ実行してください。

```bash
xattr -dr com.apple.quarantine /Applications/RABET.app
```

### 信頼性評価の値が空欄になる

統計量が未定義の場合、空欄になることがあります。例えば、対応する値がすべて同じ
場合は ICC や Pearson 相関が未定義です。また、両評価者が全ビンで 0 の行動では、
kappa や alpha は未定義です。

ソースから実行していて import error が出る場合は、`pyproject.toml` の依存関係を
インストールするか、同梱の conda 環境を使ってください。

### ログを確認する

`Log > View Logs` でログフォルダを開けます。古いログは
`Log > Clean Up Logs` から削除できます。

バグ報告時には、`Help > About` に表示される RABET のバージョンと、該当するログを
添付してください。

---

## 11. 引用とサポート

Issues: <https://github.com/mi2e-K/RABET/issues>

研究で RABET を使った場合は、次のように引用してください。

> Mitsui, K. (2026). *RABET - Real-time Animal Behavior Event Tagger*
> (Version 1.4.0) [Computer software].
> https://github.com/mi2e-K/RABET
> doi:[10.5281/zenodo.15313025](https://doi.org/10.5281/zenodo.15313025)

この DOI は Zenodo の concept DOI です。再現性のため、実際に使った RABET の
バージョンも必ず記録してください。

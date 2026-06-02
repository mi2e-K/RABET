# RABET パフォーマンス・保守性最適化計画

> **この版について（統合レビュー追補 / 2026-06 / rev.2）**
> 本文書は Codex が起草した性能・保守性の最適化計画を骨格とし、別途実施した
> コードレビュー（バグ点検・最適化点検）の結果を重ね合わせた統合版です。
> 追補箇所は **「[統合追補]」** で明示しています。統合の核心は、
> *性能最適化が触る3つの箇所（Timeline index / Analysis正規化 / Video position）
> には正しさバグが同居しているため、同じPRで畳み込んで解消する* という交差視点
> （§2.3 を参照）です。Codexの原則「研究上の意味を変えない」は維持します。
>
> **rev.2 での変更（Codexレビューフィードバックの反映）**:
> - tests/・tools/ が `.gitignore` 対象で CI が ruff のみという計画矛盾を受け、
>   **PR-00「test foundation の versioning と pytest CI」を全ての前提として新設**（§Phase 0）。
> - データ保全バグである seek intent 修正を **Timeline最適化より前の最優先 hotfix** へ繰上げ（§Phase 2.5 / §6.4）。
> - action map 修正案から **Model間直接依存を除去**し、signal + Controller調停へ（§Phase 1.6）。
> - atomic save 周辺を **PR分割**（§Phase 1.4 / §8）。
> - Timeline cache の **所有境界**、Video worker の **ADR**、**計測条件の固定** を明文化。
> - **セキュリティ/脆弱性の節（§12.5）を新設**（CSV formula injection、外部 project.json からの open）。
>
> **関連文書**: 正しさバグの詳細・再現・修正方針は `docs/BUG_AUDIT_REPORT.ja.md`
> （Codex作成、27件）に集約。本書は *性能PRが触る箇所で同居するバグ* のみを交差参照し、
> 純粋なデータ保全バグの一次情報はそちらを参照する。実装者は両文書を併読すること。

## 1. 目的

この文書は、RABET 1.3.3 の現在の実装を前提に、性能、応答性、
保守性、配布サイズを段階的に改善するための実装計画をまとめたものです。

最優先の目標は、研究者が長時間動画や多数の行動イベントを扱うときに、
GUIが固まったように見える時間を減らすことです。単純な高速化だけでなく、
計測可能性、回帰テスト、責務分離も改善対象に含めます。

この計画は機能追加よりも既存挙動の維持を重視します。CSVの意味、
フレーム境界、録画中の状態遷移、Reliabilityの統計定義は変更しません。

## 2. 現状の要約

### 2.1 強み

- `models/video_model.py` はPyAVを使用し、Fractionベースのseek、
  decode時の縮小、container解放を実装しています。
- `models/analysis_model.py` のtotal-time metricは、重複区間を二重加算せず、
  NumPy配列によるsweepで集計します。
- interval analysisの基本行動指標は、behaviorごとの配列を事前生成しており、
  古い `interval x behavior x iterrows` 構造から改善されています。
- `views/disagreement_review_view.py` はQPainterベースのrasterを使用し、
  playhead更新ごとのMatplotlib figure再構築を避けています。
- PyInstallerスクリプトは不要なQt moduleやoptional dependencyを除外し、
  配布サイズを抑える工夫を持っています。

### 2.2 主なボトルネック候補

| 領域 | 現状 | 懸念 |
| --- | --- | --- |
| 起動 | `main.py` がsplash表示前に `AppController` をimport | Visualization、Reliability、Matplotlibのimportコストが初期表示を遅らせる |
| 動画load | `utils/threaded_loader.py` が `QTimer` で段階表示し、実loadはGUI threadで実行 | `av.open()` と最初のdecode中はevent loopが止まる |
| 動画再生 | `VideoModel` のdecode、RGB変換、QImage生成がGUI thread上 | 高解像度・重いcodecで操作応答が落ちる |
| Timeline | repaintごとに全イベントをsortし、全イベントを走査 | 長時間動画・大量eventで再生中負荷が増える |
| Visualization | 設定変更ごとにFigureをclearし、event単位で `Axes.plot()` | 大量CSVで操作ごとの再描画が重い |
| Analysis | intervalごとにDataFrameをcopy・clipし、custom metricを再計算 | interval数とCSV数に比例して不要な処理が増える |
| Reliability | 不一致レビュー候補を同一behavior内の全組合せで生成 | 密な反復行動でO(N x M)になる |
| 保存 | settingsとproject manifestを直接上書き | 性能より堅牢性の問題だが、保存処理の一元化が必要 |
| ログ | Analysisがmetric詳細をINFOで出力 | 大量CSVでI/Oとログ肥大化が発生する |
| 配布 | ReliabilityのためSciPy全submodule収集が必要 | bundleサイズとonefile起動時間が増える |

### 2.3 [統合追補] 性能最適化と正しさバグの交差点

コードレビューで見つかった潜在バグのうち3件は、上表の性能ボトルネックと
**同じコード箇所に同居**しています。性能PRがこれらの挙動を偶発的に変えると
回帰を生むため、最適化と同じPRで畳み込んで解消する方針とします。

> **バグ監査レポートとの対応**: 交差点A は `BUG_AUDIT_REPORT.ja.md` の
> **BUG-027（rewind guard の寿命）** および本書の seek intent 修正に対応。
> 交差点B（df破壊的変更）・交差点C（onset非整列）は監査レポートに独立項目が
> 無い本書固有の指摘で、性能PRと同時に解消する。なお監査レポートの
> **BUG-002（FBF active残留）/ BUG-010（未割当key tracking）/ BUG-022
> （focus loss）** は active-event lifecycle のデータ保全バグであり、性能PRとは
> 独立に Patch 1 で先行修正する（本書の最適化対象ではないが、Timeline/Annotation を
> 触るPRと衝突するため実装順序の調整が必要）。

#### 交差点A: Video worker化（Phase 3）⊗ rewind誤検出

現状の rewind 検出は「`position_changed` の値が前回より減った」という *暗黙の
連続性* に依存します（`controllers/annotation_controller.py` の
`on_position_changed` と `handle_seek`）。`_skip_next_seek_rewind` という
one-shot guard が loader 由来の seek=0 を辛うじて除外しているだけです。

Video を worker 化すると `position_changed` の発火順序・粒度が変わり、
latest-frame queue で間引かれた position が来た瞬間にこのロジックは誤爆します。
さらに現状でも、録画中・FBFモードで `step_backward` すると `handle_seek` 経由で
rewind 判定が走り、`preserve_on_rewind` が無効だと既存アノテーションが消えます
（重大度 High の既知バグ）。

> **必須前提**: Phase 3 の前に rewind 検出を「position の連続性」ではなく
> **「ユーザーの明示的 seek intent」ベース** に作り直す。再生中の
> `position_changed` では rewind 判定しない。これを独立PR
> **「Phase 2.5: seek intent の明示化」** として先行実施する（§Phase 2.5）。

#### 交差点B: Analysis正規化一回化（Phase 1.3）⊗ DataFrame破壊的変更

Phase 1.3 の「load直後に正規化済みDataFrameを保持」は正しい方向ですが、現状
`_calculate_behavior_latency()` が**引数の df を破壊的に書き換えています**
（`df['Onset'] = pd.to_numeric(...)`）。後続メトリックに副作用が伝播します。

> **統合方針**: 「正規化を一回化する」=「以降の analyze 関数は df を *read-only*
> として扱う」と設計原則を明文化する。これで重複変換削減（性能）と副作用除去
> （正しさ）が同じ設計判断で解決し、golden CSV test が不変条件を保証する。

#### 交差点C: Timeline culling（Phase 1.1）⊗ event の onset非整列

Phase 1.1 の「`set_events()` 時に onset順 index を更新」は、別の既知バグも解きます。
現状 `AnnotationModel._events` は終了順（=挿入順）に積まれるため、FBFで先に開いた
イベントが後に閉じると export CSV が onset 順になりません。

> **統合方針**: culling 用 onset順 index と `export_to_csv` の onset sort を
> **1つの「正規化済み event view」に集約**する。性能とデータ整合を一度に解決する。

## 3. 最適化の原則

1. **計測してから変更する。**
   改善前後で同一fixtureを実行し、時間、メモリ、GUI停止時間を比較します。
2. **研究上の意味を変えない。**
   CSV値、seek位置、interval境界、Reliability結果をgolden fixtureで固定します。
3. **GUI threadを短時間で返す。**
   目安として、通常操作のGUI thread占有は50ms未満、重い操作でも
   進捗表示とcancel導線を提供します。
4. **段階導入する。**
   最初に低リスクの計測・cache・debounceを入れ、worker化はその後に行います。
5. **最適化と責務分離を同時に進める。**
   特にVisualizationはViewからrendererとplot stateを分離します。

## 4. 計測基盤

### 4.1 追加するbenchmark fixture

`tests/performance/fixtures/` に生成スクリプトと小さなmanifestを置きます。
巨大fixture本体はGit管理せず、決定的に再生成できる形にします。

| Fixture | 内容 | 用途 |
| --- | --- | --- |
| `video_short_cfr_30fps.mp4` | 30秒、720p、CFR | seekとloadの基準 |
| `video_long_cfr_30fps.mp4` | 60分、1080p、CFR | 長時間seek |
| `video_vfr_sample.mp4` | VFR | フレーム境界回帰 |
| `events_1k.csv` | 10 behaviors、1,000 events | 通常規模 |
| `events_10k.csv` | 20 behaviors、10,000 events | 中規模 |
| `events_100k.csv` | 30 behaviors、100,000 events | stress |
| `batch_100x10k/` | 100 CSV、各10,000 events | Analysis batch |
| `dense_reliability_pair/` | 同一behaviorの短い反復event多数 | 不一致matching |

動画fixtureがCIに重すぎる場合は、ローカルperformance suiteとrelease前QAに限定し、
CIでは短いfixtureまたはmock decoderを使用します。

### 4.2 計測項目

| 指標 | 測定方法 | 初期目標 |
| --- | --- | --- |
| cold start | process開始からmain window表示まで | 開発環境でbaseline比30%以上短縮 |
| first useful paint | splash表示、main window表示、最初の操作可能時刻を記録 | splashを早期表示 |
| video load | load開始から最初のframe表示まで | 720p短編で1秒以内を目標 |
| GUI停止時間 | 50ms超のevent-loop遅延を記録 | 通常操作で100ms超を原則ゼロ |
| seek latency | seek要求からframe表示まで | 95 percentileを記録し継続監視 |
| playback dropped frame | 目標frame数と表示frame数の差 | codec別にbaseline改善 |
| Timeline repaint | 1k / 10k / 100k eventのpaint時間 | 10k eventで16-33ms範囲を目標 |
| raster redraw | CSV数、event数、mode別の描画時間 | 10k eventで操作可能な範囲へ |
| batch analysis | CSV数、interval設定別の完了時間 | baseline比50%以上短縮を狙う |
| Reliability review build | event密度別の候補生成時間 | 高密度fixtureで線形に近づける |
| RSS | 起動後、動画load後、plot後、繰り返し操作後 | 反復操作で増加し続けない |
| package size | OS別archiveと展開後サイズ | baselineを記録し増分をレビュー |

### 4.3 計測コードの配置案

```text
tests/
  performance/
    conftest.py
    test_analysis_performance.py
    test_reliability_performance.py
    test_timeline_performance.py
tools/
  generate_performance_fixtures.py
  benchmark_startup.py
  benchmark_video_pipeline.py
  benchmark_visualization.py
  report_bundle_size.py
```

`pytest-benchmark` の結果はJSONで保存し、release前に前回releaseと比較します。
GUI停止時間は `QElapsedTimer` と短周期 `QTimer` の遅延から観測します。

### 4.4 [統合追補] 計測条件の固定

時間系の数値は環境依存が大きいため、各 baseline reportに以下を必ず併記する。
これが無いと「速くなった」の判定が再現できない。

- 参照マシン: CPU / 物理コア数 / RAM / ストレージ種別（SSD/HDD）
- **ストレージ位置の区別**: ローカルディスク vs OneDrive/クラウド同期配下
  （RABET の既定パスは OneDrive 配下になりがちで I/O 特性が大きく変わる）
- OS とバージョン、Python / PyAV / FFmpeg / PySide6 / pandas / matplotlib のバージョン
- 動画 fixture の codec・解像度・fps・CFR/VFR
- warm-up 回数（最低1回は破棄）、計測反復回数、報告は **median と p95**（平均値単独は禁止）
- 電源プロファイル（ノートPCは「高パフォーマンス」固定）、他プロセス影響の最小化

> **CIでの扱い**: 共有CIランナーは時間が不安定なため、**時間系メトリクスは当面
> report-only（fail判定に使わない）** とする。回帰 fail 判定は管理された参照マシンで
> 行う。CIでは「正しさ（golden / semantic invariant）」と「明らかな計算量退行
> （例: event数に対し O(N^2) になっていないかの相対比較）」のみを fail 条件とする。

## 5. 実装ロードマップ

## Phase 0: Baseline固定

**期間目安:** 1-2日  
**優先度:** P0  
**狙い:** 改善前の数値と研究上の出力を固定する。

### 0.0 [統合追補] PR-00: test foundation の versioning と pytest CI（全Phaseの前提）

**背景（Codexレビュー High-1）**: 現状 `.gitignore` は `tests/`（53行目）と
`tools/`（56行目）を除外し、CI（`.github/workflows/ci.yml`）は **ruff のみ**。
`pytest` / `pytest-benchmark` は `pyproject.toml` の dev extras に既にあり、
ruff も `tests/*` の per-file-ignore を持つため、**基盤はほぼ整っており blocker は
2点だけ**:（a）tests/ が gitignore、（b）pytest job が無い。これを最初に解消しないと、
本計画が前提とする「CIで回す golden / regression テスト」が成立しない。

**作業**

- 小型 fixture と pytest スイートを**追跡対象**にする。**決定済み（2026-06）**:
  **`tests/` を公開リポジトリに含める**（ignore を解除）。これにより公開CIで
  全テストが回り、再現性と外部貢献の容易さが最大化される。巨大な生成物のみ ignore 継続。
- 巨大な生成物（長時間動画など）のみ ignore し、生成スクリプト（`tools/`）と
  manifest は追跡する。`tools/` の ignore も見直す。
- CI に pytest job を追加（ruff job と並列）。時間系 benchmark は **report-only**
  （§4.4）、正しさ系は fail 条件。
- `jsonschema` を導入する場合は dev/runtime いずれの依存にするか決め、bundle 影響を
  §5.3 で計測（Phase 1.4 と連動）。

**完了条件**

- 公開CIで pytest が緑になる（最小でも既存43件 + 本計画で足す回帰テスト）。
- 巨大 fixture を含めずにスイートが再生成・実行できる。

### 作業

1. fixture生成ツールを追加する。
2. cold start、動画load、seek、Timeline、Analysis、Visualization、
   Reliability、RSS、bundleサイズのbaselineを記録する（**§4.4 の計測条件を併記**）。
3. Analysis summary、interval CSV、Reliability結果をgolden fixture化する。
4. Windowsを必須環境とし、macOS / Linuxはrelease前QAで同じ表を埋める。

### [統合追補] golden の二層化（Codexレビュー Medium-4）

golden fixture を作る際、**「旧挙動の性能 baseline」と「正しい挙動を示す
semantic invariant」を必ず分離する**。既知の誤動作（例: FBF時の CSV onset順の乱れ、
RecordingStart の round-trip で 1フレーム化、shallow-copy された config 既定値）を
そのまま golden に焼き込むと、後の正しさ修正が「golden を壊す変更」に見えて修正しづらくなる。

- **性能 baseline**: 現行の出力バイト列をそのまま固定（差分検知用）。既知バグを含んでよいが、
  該当行に「これは BUG-xxx の既知挙動」と注記する。
- **semantic invariant**: 「あるべき正しい不変条件」をテストで表現（例: 「export CSV は
  常に onset 昇順」「RecordingStart は zero-duration を保つ」）。**既知バグはここでは
  xfail/skip として登録**し、修正PRで pass に昇格させる。
- バグ監査レポート（`BUG_AUDIT_REPORT.ja.md`）の BUG-ID を各 invariant にリンクする。

### 完了条件

- baseline reportが `docs/performance/baseline-<version>.md` に残る（計測条件込み）。
- 最適化PRで比較対象となる固定fixtureがある。
- 統計値とCSV出力のgolden testが通る。
- **semantic invariant テストが存在し、既知バグは xfail として明示登録されている。**

## Phase 1: 低リスク改善

**期間目安:** 3-5日  
**優先度:** P0  
**狙い:** worker設計に入る前に、不要な再処理と保存リスクを減らす。

### 1.1 Timelineのsort cacheと可視範囲culling

**対象:** `views/timeline_view.py`

現状は `TimelineCanvas.paintEvent()` ごとに `_compute_event_levels()` と
`draw_order = sorted(...)` を実行し、画面外イベントも描画候補として走査します。

**設計案**

- `TimelineView.set_events()` 時にonset順indexを更新する。
- overlap levelもイベント変更時に計算し、active eventだけ必要時に差分更新する。
- viewportの左右端から可視時間範囲を求め、`bisect` で候補を絞る。
- `RecordingStart` markerも同じindexで管理する。
- zoom、duration、event追加・削除・更新時だけcacheをinvalidateする。

**受け入れ条件**

- 既存描画と選択hit-testが一致する。
- 10k eventで再生中paint時間をbaseline比50%以上削減する。
- 100k eventでも操作不能にならない。

> **[統合追補] 交差点C を畳み込む**: ここで作る onset順 index を
> `AnnotationModel` 側の「正規化済み event view」として共有し、
> `export_to_csv` も同じ順序で出力する。受け入れ条件に
> 「export CSV が常に onset 昇順（FBFで終了順が乱れても）」を追加する。
> regression: FBFで2イベントを開始順と逆順に閉じても CSV が onset 順になること。
>
> **[統合追補] 所有境界の明文化（Codexレビュー Medium-6）**: Model と View が
> cache を共有しすぎると結合が強くなる。所有を次のように分ける。
> - **Model（`AnnotationModel`）が持つもの**: 完了イベントの *onset順 snapshot*
>   と単調増加する *revision 番号* のみ。`get_events_snapshot() -> (events, revision)`。
>   Model は viewport も overlap level も hit-test も知らない。
> - **Timeline（View）が持つもの**: viewport（可視時間範囲）、overlap level、
>   hit-test cache。revision が変わったときだけ再計算する。
> - **active event overlay は completed event と分離**して保持・描画する。active は
>   毎フレーム動く（offset=None で playhead 追従）が、completed snapshot は revision
>   が変わるまで不変。両者を混ぜると毎フレーム全再計算に戻ってしまう。
> - export は Model の onset順 snapshot を使い、Timeline 描画キャッシュには依存しない。

### 1.2 Visualization redraw debounce

**対象:** `views/visualization_view.py`

各spinbox、checkbox、選択変更が即座に `update_plot()` を呼びます。
連続操作では古い描画が無駄になります。

**設計案**

- `schedule_plot_update(reason)` を追加する。
- 100-200msのsingle-shot `QTimer` で最後の変更だけ描画する。
- 明示的Refresh、export直前、初回loadは即時描画可能にする。
- status labelに `Updating plot...` を表示する。

**受け入れ条件**

- slider連続変更で描画回数が大幅に減る。
- export時は最新状態が必ず反映される。
- 通常操作で表示内容が変わらない。

### 1.3 Analysis DataFrame正規化の一回化

**対象:** `models/analysis_model.py`

intervalごとに `_filter_events_for_interval()` がDataFrame全体をcopyし、
`Onset` / `Offset` を再度numeric変換します。

**設計案**

- CSV load直後に正規化済みDataFrameを保持する。
- custom total-time metric用にbehavior別の区間配列を事前生成する。
- intervalごとは配列clipとunion計算だけにする。
- summary-only入力は近似値であることを結果metadataに保持する。

**受け入れ条件**

- batch fixtureのinterval analysisがbaseline比50%以上短縮する。
- golden CSVが一致する。
- invalid timestampのskip件数が従来と一致する。

> **[統合追補] 交差点B を畳み込む**: 設計原則として
> 「正規化後の analyze 関数は受け取った DataFrame を変更しない（read-only）」を
> 明文化する。特に `_calculate_behavior_latency()` の破壊的 `pd.to_numeric` 代入を
> 除去する。受け入れ条件に「同一 df に latency→total_aggression を連続適用しても
> 結果が不変」を追加する。

### 1.4 Atomic save共通化

**対象:** `utils/file_manager.py`, `models/project_model.py`,
`utils/config_manager.py`

**設計案**

- `save_json_atomic(data, path, backup=True)` を追加する。
- 同一directoryへtemporary fileを書き、flush、可能なら `fsync()`、
  `os.replace()` で置換する。
- `project.json` は直前版を `.bak` として保持する。
- settingsはbackup optionalとする。

**受け入れ条件**

- write失敗時に既存manifestが壊れない。
- project新規作成時にmanifest保存失敗を成功扱いしない。
- Windows / macOS / Linuxで置換が通る。

> **[統合追補] PR分割（Codexレビュー Medium-5）**: 当初 atomic save に複数項目を
> 同梱する案だったが、レビューとロールバックを容易にするため **別PRに分割**する。
> | PR | 内容 | 補足 |
> | --- | --- | --- |
> | atomic save | `save_json_atomic()` の導入のみ | temp file + `os.replace` + `.bak` |
> | config schema validation | `ConfigManager.load_config()` の検証 | 壊れた settings.json を明示エラー化 |
> | annotation session reset | `clear_events()` で `_test_duration=None` | import→export での test_duration 引き継ぎ解消 |
> | logging是正（→ Phase 1.5） | INFO/DEBUG 整理 | 独立PR |
>
> **jsonschema 導入の注意**: `jsonschema` は現状 `pyproject.toml` の依存に **無い**。
> 導入するなら（a）runtime 依存にするか dev のみか、（b）PyInstaller bundle サイズへの
> 影響、を §5.3 の枠で計測してから決める。軽量で済むなら手書きの型チェックでも可。

### 1.5 [統合追補] ログレベルの是正

**対象:** `models/analysis_model.py`

§2.2 の「ログ肥大化」をPhase化する。現状 `_analyze_file` 等が 1ファイルあたり
数十行を INFO で出力し、batch analysis で I/O とログ肥大化を招く。

**設計案**

- per-file の metric 明細は DEBUG に格下げし、ファイル単位の集約結果のみ INFO とする。
- latency 計算の逐次トレース（`LATENCY CALCULATION DETAILS` など）も DEBUG へ。

**受け入れ条件**

- 100 CSV batch のログ行数がbaseline比で大幅に減る。
- `--dev` の DEBUG ログでは従来同等の情報が得られる。

### 1.6 [統合追補] action_map 編集と active event の整合（BUG-012）

**対象:** `controllers/annotation_controller.py`（調停役）, `models/action_map_model.py`,
`models/annotation_model.py`

録画中に action_map から mapping を削除すると、`ActionMapModel` は
`_active_behaviors` を `discard` する一方、`AnnotationModel._active_events` には
残骸イベントが残る（タイムラインに stranded bar が出る）。

**設計方針（Codexレビュー High-3 を反映 — Model間直接依存を作らない）**

当初案「`ActionMapModel.remove_mapping()` から `AnnotationModel.discard_active_event()`
を直接呼ぶ」は **却下**。Model 同士に依存を張ると責務分離が崩れ、テストもしづらくなる。
`ActionMapModel` には既に **`mapping_removed` signal**（`models/action_map_model.py:267`）
があるので、これを **Controller（または application service）で調停**する。

さらに、研究用途では **active event の暗黙 discard 自体が危険**（記録途中の行動が
無言で消える）。**決定済み（2026-06）: (A) 録画中は action map 編集を禁止する**。

- session 開始時に action map の snapshot を固定し、**編集UI（Add/Edit/Remove）は
  録画停止までロック**する。これが最もシンプルで、進行中イベントの取り違えが原理的に起きない。
- ロック中はボタンを無効化し、ツールチップで「録画中は行動マップを編集できません」と示す。
- （不採用とした代替案: 削除時に現在位置で finalize する案。確認フローとエッジケースが
  増えるため、まずは編集禁止で運用し、要望があれば将来再検討する。）

調停は Controller が行い、Model 間の直接呼び出しは作らない（`mapping_removed` signal は
保持。録画中ロックにより録画中に発火しなくなるため、残骸 active event の問題も解消する）。

**受け入れ条件**

- 録画中に active な key の mapping を削除しても `_active_events` に残骸が残らない。
- 確定したイベント（方針B）は export に正しく含まれ、暗黙に消えない。
- Model 間の直接依存が増えていない（`ActionMapModel` は `AnnotationModel` を import しない）。

## Phase 2: Visualization renderer改善

**期間目安:** 4-7日  
**優先度:** P1  
**狙い:** 大量eventのraster redrawを高速化し、Viewの責務を減らす。

### 2.1 `Axes.plot()` 反復を `LineCollection` へ置換

**対象:** `views/visualization_view.py`

現在はeventごとに `Axes.plot()` を呼びます。Matplotlib object数がevent数に比例し、
再描画とメモリ使用量が増えます。

**設計案**

- behavior、file、styleごとに線分配列を作る。
- `matplotlib.collections.LineCollection` を使用する。
- overlay、separate、grouped modeのrendererを分離する。
- event filteringとstyle決定をplot state層へ移す。

**分割案**

```text
views/
  visualization_view.py
  visualization_renderer.py
models/
  visualization_plot_state.py
```

**受け入れ条件**

- PNG / SVG / PDF出力が既存見た目と同等。
- 10k event redrawをbaseline比60%以上短縮する。
- redraw反復後にRSSが増加し続けない。

### 2.2 非同期precompute

**設計案**

- CSV load後のevent grouping、recording start抽出、max time計算をworkerへ移す。
- workerはQt widgetやMatplotlib objectに触れない。
- UI threadは完成済みplot payloadを受け取って描画する。
- 新しい操作が来たら古いgenerationの結果を捨てる。

**受け入れ条件**

- 大量CSV load中もcancelと画面切替が反応する。
- stale worker結果で表示が巻き戻らない。

## Phase 2.5: [統合追補] seek intent の明示化（**最優先 hotfix** / Phase 3 の前提）

**期間目安:** 2-4日
**優先度:** P0（**データ保全 hotfix。Timeline最適化 Phase 1.1 より前に実施**）
**狙い:** rewind 検出を position の連続性依存から切り離し、(1) 録画中の step_backward での
アノテーション消失を止め、(2) Video worker化を安全にする。

> **[統合追補] 順序の訂正（Codexレビュー High-2）**: 当初これを優先順位9位/Week2 に
> 置いていたが、**録画中・FBF中の step_backward で既存アノテーションが消えるのは
> 性能課題ではなくデータ保全バグ**であり、本書自身が「重大」と評価している。よって
> **最小限の回帰テストを添えた独立 hotfix として、Timeline最適化（Phase 1.1）より前に
> 着手**する。性能改善のどのPRよりも優先する。

§2.3 交差点A の通り、現状の rewind 検出は `controllers/annotation_controller.py:1220`
の `handle_seek()` で `position_changed` が減少したことを根拠にしている。Video worker化で
発火順序・粒度が変わると誤爆する。さらに録画中・FBFモードの `step_backward` で既存
アノテーションが消える重大バグも同根（`preserve_on_rewind` が無効な場合）。

**対象:** `controllers/video_controller.py`, `controllers/annotation_controller.py`

**設計案**

- `VideoController.handle_seek()` / `handle_step_backward()` が、ユーザー起点の
  シーク操作を **明示的な seek intent イベント** として annotation_controller に通知する。
- `annotation_controller` は再生中の `position_changed` では rewind 判定をしない。
  rewind 判定は seek intent を受けたときだけ行う。
- これにより `_skip_next_seek_rewind` の one-shot guard は不要化を目指す。
- FBFモードの step は明示 seek だが、preserve を意図する操作として扱い、
  「巻き戻しただけでアノテーションが消える」挙動を止める。

**受け入れ条件**

- 録画中・FBF中の step_backward で既存アノテーションが消えない。
- 動画切替時の loader 由来 seek=0 が rewind 扱いされない（既存 regression を維持）。
- `preserve_on_rewind` トグルの明示的 rewind 時の挙動は従来通り。
- Phase 3 の worker化後も同じ regression test が通る。

## Phase 3: 動画loadと再生pipeline

**期間目安:** 1-2週間  
**優先度:** P1  
**狙い:** 動画を開く瞬間と高解像度再生時のGUI停止を減らす。

### 3.1 `ThreadedVideoLoader` の再設計

**対象:** `utils/threaded_loader.py`, `models/video_model.py`,
`controllers/video_controller.py`

現状の `ThreadedVideoLoader` は実threadを作りません。`QTimer` による段階表示後、
GUI thread上で `VideoModel.load_video()` を呼びます。

**設計案**

- worker側でread-only probeを行う。
- probe結果はduration、stream index、fps、time base、最初のframe、
  error情報を含むDTOとして返す。
- GUI thread側でModel stateをcommitする。
- workerがcontainerを保持する設計にする場合は、以後のdecodeも同じworkerへ寄せる。
- cancel時はgeneration tokenを無効化し、返却結果をcommitしない。

**重要な判断点**

PyAV containerをGUI threadへhandoffするよりも、decode workerがcontainerを所有し続ける
設計の方がthread ownershipを明確にできます。Phase 3.2とまとめて設計する方が安全です。

> **[統合追補] エラー細分化を同梱**: worker化で decode エラー処理を書き直す機会に、
> 現状一括 catch している `(av.error.FFmpegError, OSError)` を「codec非対応 /
> ファイル破損 / 権限なし / ストリーム無し」に分解し、研究者向けに *次の操作を示す*
> メッセージを出す（§6.3 の error/log 分離方針と整合）。

### 3.2 Decode workerとlatest-frame queue

**設計案**

- decode workerがPyAV containerとstreamを所有する。
- UI threadはplay、pause、seek、close、target display sizeをcommandとして送る。
- workerはframeをRGB bufferまたは安全に所有権移譲できる画像DTOとして返す。
- queueは上限を持ち、遅れたframeを溜め込まず最新frameを優先する。
- seekにはgeneration IDを付け、古いdecode結果を破棄する。
- annotation timestampの基準は従来どおりvideo positionとする。

**受け入れ条件**

- load中、seek中、4K再生中でもmain windowを移動できる。
- pause後に古いframeが表示されない。
- frame stepが従来のフレーム境界と一致する。
- CFR、VFR、29.97fps fixtureで回帰テストが通る。
- closeと動画切替を100回繰り返してRSSが増加し続けない。

> **[統合追補] 実装前に ADR を書く（Codexレビュー Medium-8）**: container ownership と
> generation ID の方針は妥当だが、worker 化は状態が複雑なので **着手前に
> `docs/adr/` に状態遷移図付きの設計判断記録（ADR）を1枚置く**。最低限、次の境界条件を
> 図と表で固定してから実装する:
> - **`av.open()` がブロックした場合の cancel**: probe 中のキャンセルでどう抜けるか
>   （worker 終了 vs 放置 + token無効化）。
> - **shutdown timeout**: アプリ終了時に worker が decode 中の場合の待機上限と強制終了。
> - **reload 競合**: 連続で別動画を開いたときの旧 worker / container の解放順序。
> - **queue 上限と drop ポリシー**: latest-frame 優先で何フレームまで保持するか。
> - **annotation timestamp の基準**: 従来どおり video position を真とする（worker の
>   wall-clock ではない）ことを明記。
> - 状態: `Idle / Probing / Ready / Playing / Seeking / Closing` の遷移と、各状態で
>   受理する command（play/pause/seek/close/resize）を表にする。

### 3.3 `processEvents()` の削減

**対象:** `controllers/video_controller.py`, `views/visualization_view.py`,
`views/reliability_view.py`

明示的な `processEvents()` はre-entrantなsignal処理を招きやすいため、
worker化とsingle-shot timerで不要になる箇所を削減します。

**受け入れ条件**

- overlay、progress bar、cancel操作が正常。
- 同一操作の二重実行や状態競合がない。

## Phase 4: Reliability最適化

**期間目安:** 3-5日  
**優先度:** P2  
**狙い:** dense eventと複数file比較を扱いやすくする。

### 4.1 不一致候補生成の近傍探索化

**対象:** `models/reliability_model.py`

`_candidate_pairs_for_behavior()` は同一behaviorのreferenceとtraineeを
全組合せ比較します。

**設計案**

- onset順にsortする。
- two-pointerまたはsliding windowで、overlapまたはmatching window内の候補だけを生成する。
- greedy selectionのsort keyは維持し、既存結果を変えない。
- dense fixtureで既存アルゴリズムとの差分を検証する。

**受け入れ条件**

- 既存43件を含むReliability testが通る。
- 通常fixtureのpair結果が一致する。
- dense fixtureで処理時間とpeak memoryが改善する。

### 4.2 Reliability計算のworker化

**対象:** `controllers/reliability_controller.py`

**設計案**

- summary解析とdetailed解析をQt workerへ移す。
- progress、cancel、error、resultをsignalで返す。
- pure function部分はQt非依存のまま維持する。

**受け入れ条件**

- 計算中もタブ移動とcancelが機能する。
- cancel後に古い結果が画面へ反映されない。

## Phase 5: 起動時間と配布サイズ

**期間目安:** 3-6日  
**優先度:** P2  
**狙い:** 通常利用者がAnnotation画面を使い始めるまでの時間を短縮する。

### 5.1 splashの早期表示

**対象:** `main.py`, `controllers/app_controller.py`

現状は `main.py` が `AppController` をmodule top-levelでimportし、
その先でVisualizationとReliabilityのViewをimportします。

**設計案**

- QApplicationとsplashを先に作る。
- `AppController` importをsplash表示後へ移す。
- import段階ごとにprogress messageを更新する。

### 5.2 重いタブのlazy初期化

**対象:** `controllers/app_controller.py`, `views/main_window.py`

**設計案**

- Annotation、Projectを先に生成する。
- VisualizationとReliabilityはplaceholder tabを置き、初回選択時に生成する。
- Analysisのpandas importも必要性と効果を計測する。
- lazy初期化失敗時はタブ内でerrorを表示する。

**受け入れ条件**

- cold startをbaseline比30%以上短縮する。
- 各タブの初回表示が正常。
- lazy tabを開かないAnnotation-only利用では不要moduleをimportしない。

### 5.3 bundleサイズ調査

**対象:** `packaging/`

**設計案**

- OS別にmodule size reportを出す。
- SciPy、statsmodels、seaborn、pingouinの寄与を可視化する。
- ICC(2,1)の結果互換を維持できる軽量backendまたは局所実装の feasibilityを調査する。
- Reliabilityをoptional plugin化する案はv2候補として比較する。

**受け入れ条件**

- archive、展開後、onefile起動時展開時間をreleaseごとに記録する。
- サイズ削減を行う場合、ReliabilityのR参照値cross-validationが通る。

## Phase 6: 保守性改善

**期間目安:** 継続  
**優先度:** P2  
**狙い:** 次の最適化を安全に行える構造へ整える。

### 6.1 Visualization分割

`views/visualization_view.py` は約4,000行あり、dialog、状態、描画、exportが集中しています。

**分離候補**

- `VisualizationPlotState`: 選択、表示mode、色、group、表示範囲
- `VisualizationRenderer`: Matplotlib payload生成と描画
- `VisualizationExportService`: PNG / SVG / PDF保存
- `VisualizationDialogs`: color map、overlay group編集

### 6.2 Video command境界の明確化

`VideoController` が一部で `VideoModel` のprivate属性を直接変更しています。
worker化に合わせて `close_video()`, `reset()`, `seek()`, `set_target_size()` を
public APIとして整理します。

### 6.3 型と例外境界

- worker DTO、plot payload、project manifestに型を付ける。
- `except Exception` はUI境界では維持しつつ、内部処理では狭い例外へ分解する。
- error通知とlogを分け、研究者向けmessageは次の操作を示す。

## 6. 優先順位付き作業一覧

| 順位 | 作業 | 期待効果 | 難度 | 依存 |
| --- | --- | --- | --- | --- |
| 1 | baseline fixtureと計測スクリプト | 改善判断を可能にする | M | なし |
| 2 | Timeline sort cache + culling | 再生中負荷を低減 | M | baseline |
| 3 | Visualization debounce | 小さい変更で体感改善 | S | baseline |
| 4 | Analysis正規化一回化 | batch処理短縮 | M | golden CSV |
| 5 | atomic save共通化 | 保存の堅牢性向上 | S | 保存回帰test |
| 6 | Visualization `LineCollection` 化 | raster描画を大幅改善 | M | debounce |
| 7 | splash早期表示 + lazy tab | 起動時間短縮 | M | cold start計測 |
| 8 | video decode worker | GUI停止を根本改善 | L | video fixture |
| 9 | Reliability候補近傍探索 | dense event改善 | M | dense fixture |
| 10 | bundle backend調査 | 配布サイズ改善余地を定量化 | M | size report |

### 6.4 [統合追補] バグ修正を畳み込んだ改訂優先順位

上表に、コードレビューで見つかった正しさバグ（§2.3 交差点 + バグ監査レポート）を交差させ、
依存関係で再編した版。**rev.2 の構造変更（Codexレビュー反映）**:
- **PR-00（test foundation）を最上位の前提**に（High-1）。
- **seek intent hotfix を順位3へ繰上げ**、Timeline最適化より前に（High-2、データ保全）。
- データ保全バグ（BUG-001/002/003/004 等）は性能とは別トラックの **Patch 1**
  （`BUG_AUDIT_REPORT.ja.md` §10）として並行進行。本表は性能トラック主体で示す。

| 順位 | 作業 | 起点 | 効果 | 難度 |
| --- | --- | --- | --- | --- |
| 0 | **PR-00: tests/・tools/ 追跡 + pytest CI** | High-1 | 計画全体の前提 | S-M |
| 1 | baseline fixture + 計測（条件固定）+ golden 二層化 | Phase 0 + Medium-4/7 | 判断基盤 | M |
| 2 | **AnnotationModel/AnalysisModel の unit test 整備** | 統合追補 | リファクタ前の安全網 | M |
| 3 | **seek intent明示化（hotfix）** | Phase 2.5 + 交差点A | データ保全 + worker化前提 | M |
| 4 | Timeline cache+culling + onset順index共有（所有境界明文化） | Phase 1.1 + 交差点C + Medium-6 | 再生中負荷↓ + CSV整合 | M |
| 5 | Visualization debounce | Phase 1.2 | 体感改善 | S |
| 6 | Analysis正規化一回化（df read-only化） | Phase 1.3 + 交差点B | batch↓ + 副作用解消 | M |
| 7 | atomic save（分割PR） | Phase 1.4 | 保存堅牢化 | S |
| 8 | config schema validation（分割PR） | Phase 1.4 + 追補 | 設定堅牢化 | S |
| 9 | ログレベル是正 / action_map整合（signal調停）| Phase 1.5/1.6 | I/O↓ + データ整合 | S |
| 10 | **CSV出力の硬化（formula injection + UTF-8）** | §12.5 + BUG-005 | データ共有安全性 | S |
| 11 | LineCollection化 + renderer分離 + 非同期precompute | Phase 2 | raster描画↓ | M |
| 12 | splash早期 + lazy tab | Phase 5.1/5.2 | 起動時間↓ | M |
| 13 | video worker（ADR先行）+ processEvents削減 + PyAVエラー細分化 | Phase 3 + Medium-8 | GUI停止根治 | L |
| 14 | Reliability近傍探索 + worker化 | Phase 4 | dense event↓ / UI応答 | M |
| 15 | bundle調査（jsonschema影響含む） | Phase 5.3 | 配布サイズ | M |
| 16 | 保守性（型 / 例外 / magic number / Visualization分割） | Phase 6 | 継続 | 継続 |

## 7. テスト戦略

### 7.1 常時CIで回すテスト

- Analysis golden CSV round-trip
- interval境界、重複event、空interval
- Reliability既存testとdense matching小規模fixture
- Timeline cache invalidationとhit-test
- atomic save失敗時の旧manifest維持
- lazy tab初期化
- worker command順序: load、pause、seek、close、reload

**[統合追補] CIに追加するテスト**（現状 tests/ は Reliability のみで annotation 中核が未カバー）

- AnnotationModel ライフサイクル: start/end、同一キー重複press、release欠落、
  重複release、最小1フレーム補正、offset<onset の clamp
- end_event の `try/finally` で active_events が必ず空になる（"FBF won't stop" 回帰）
- action_map の mapping 削除時に active event が残らない（Phase 1.6 回帰）
- CSV round-trip で onset 昇順が保証される（交差点C 回帰）
- seek intent: 録画中・FBF中の step_backward でアノテーションが消えない（Phase 2.5 回帰）
- 同一 df への latency→total_aggression 連続適用で結果不変（交差点B 回帰）

### 7.2 release前に回すテスト

- Windows / macOS / Linuxの実動画loadとseek
- 日本語、空白、OneDrive配下path
- **[統合追補] 日本語IME ON 状態での behavior キー入力**（`QKeyEvent.text()` が
  空になり全キーが取りこぼされる懸念。`event.key()` からの ASCII フォールバック要検証）
- **[統合追補] 録画中の action_map 編集 / 複数 RecordingStart の latency 計算**
- 4K動画、60分動画、VFR動画
- 100k event Timeline
- 100 CSV batch analysis
- Visualization mode別10k / 100k event export
- Reliability dense event pair
- 動画切替100回、plot redraw100回、Reliability dialog open/close100回のRSS推移
- PyInstaller成果物の起動時間とサイズ

## 8. 変更を分割するPR案

| PR | 内容 | 変更範囲 |
| --- | --- | --- |
| PR-01 | performance fixture、benchmark script、baseline report | `tests/performance/`, `tools/`, `docs/performance/` |
| PR-02 | Timeline cacheと可視範囲culling | `views/timeline_view.py` |
| PR-03 | Visualization debounce | `views/visualization_view.py` |
| PR-04 | Analysis正規化一回化 | `models/analysis_model.py` |
| PR-05 | atomic JSON save | `utils/file_manager.py`, Project、Config |
| PR-06 | Visualization renderer分離と `LineCollection` | Visualization関連 |
| PR-07 | splash早期化、Visualization / Reliability lazy tab | startup関連 |
| PR-08 | Video worker prototype | Video関連 |
| PR-09 | Video worker本導入と回帰test | Video関連 |
| PR-10 | Reliability近傍探索とworker化 | Reliability関連 |
| PR-11 | bundle size reportと採否判断 | `packaging/`, `tools/` |

各PRは、対象領域以外の挙動変更を含めないようにします。特にVideo workerは、
Timeline、Annotation、Project修正と同じPRへ混ぜません。

> **[統合追補] PR分割の補足（rev.2）**
> | PR | 内容 | 変更範囲 |
> | --- | --- | --- |
> | **PR-00** | **tests/・tools/ の追跡 + pytest CI job**（全PRの前提・最初にマージ） | `.gitignore`, `.github/workflows/ci.yml`, `pyproject.toml` |
> | PR-01b | AnnotationModel/AnalysisModel unit test 整備 | `tests/` |
> | **PR-02a** | **seek intent明示化（hotfix・Timeline最適化より前）** | Video、Annotation |
> | PR-05b1 | atomic save | FileManager、Project、Config |
> | PR-05b2 | config schema validation | Config |
> | PR-05b3 | test_durationリセット / ログレベル是正 | Annotation、Analysis |
> | PR-05c | action_map整合（signal調停・Model間依存を作らない） | AnnotationController、ActionMap |
> | PR-10a | **CSV出力硬化（formula injection + UTF-8）** | Annotation、Analysis export |
>
> Codexレビュー反映: PR-00 を最初に。PR-05b 系は **3つに分割**（atomic / schema /
> reset+log）してレビューとロールバックを容易に。seek intent（PR-02a）は video worker
> （PR-08/09）の **前**、かつ Timeline 最適化（PR-02）よりも **前**にマージする。
> action_map 整合（PR-05c）は Model 間直接依存を作らず Controller で調停する。

## 9. リスクと対策

| リスク | 対策 |
| --- | --- |
| worker化でseek後に古いframeが表示される | generation IDでstale frameを破棄 |
| thread終了時にPyAV containerが残る | owner worker内でcloseし、終了待ちをtest |
| Timeline cacheがイベント更新に追従しない | mutationごとのinvalidate test |
| Visualization高速化で見た目が変わる | mode別golden imageとSVG構造のsmoke test |
| Analysis高速化でinterval境界が変わる | closed-open境界のfixtureを固定 |
| Reliability高速化でpair選択が変わる | 現行pair一覧をgolden化し、変更は明示レビュー |
| lazy importで初回タブ表示だけ失敗する | placeholder、error表示、初回表示test |
| bundle削減でReliabilityだけ壊れる | packaged executableでICC / alpha smoke test |

## 10. 最初の2週間で実施する内容

### Week 1

1. **[統合追補・最優先] PR-00 を出す**: `tests/`・`tools/` を追跡対象にし、CI に
   pytest job を追加（既存43件を緑に）。これが無いと以降の golden / regression が
   CI で保証されない（Codexレビュー High-1）。
2. benchmark fixture生成スクリプトを作る（**§4.4 の計測条件を report に固定**）。
3. startup、Timeline、Analysis、Visualization、Reliability、bundleサイズのbaselineを取る。
4. **golden を二層化**: 性能baseline（既知バグ込み・注記付き）と semantic invariant
   （あるべき不変条件・既知バグは xfail）を分離する（Codexレビュー Medium-4）。
5. **[統合追補] AnnotationModel/AnalysisModel の unit test を書く**
   （リファクタ前の安全網。現状 annotation 中核が未カバーのため最優先）。
6. **[統合追補・hotfix] seek intent明示化（Phase 2.5）を実装する**
   （録画中 step_backward のアノテーション消失を止める。**Timeline最適化より前**。
   Codexレビュー High-2）。

### Week 2

1. Timeline cache + culling を実装する（**onset順index共有で交差点Cも解消**、
   **所有境界を Model=snapshot+revision / View=viewport+overlap+hit-test に分離**）。
2. Visualization debounceを実装する。
3. Analysisの正規化一回化とinterval custom metric最適化を行う
   （**df read-only化で交差点B = 破壊的変更バグも同時解消**）。
4. atomic JSON save を導入する（**schema validation・reset+log は別PRに分割**）。
5. action_map整合（**signal + Controller調停**で。Model間直接依存は作らない）。
6. **Video worker の ADR（状態遷移図 + 境界条件）を書く**（実装は次スプリント）。
7. Visualization `LineCollection` prototypeを作り、描画差分を確認する。
8. 2週間時点のbefore / after reportを残す。

> Codexレビュー反映: (1) PR-00 を最初に置き CI 基盤を先に整える。(2) seek intent
> 明示化を **Week1 の hotfix** へ繰上げ（データ保全のため Timeline 最適化より前）。
> (3) Video worker は実装前に ADR を Week2 で固める（着手は次スプリント）。

## 11. 完了の定義

最適化は「コードが速そうに見える」時点では完了としません。次を満たしたときに
対象Phaseを完了とします。

- fixtureと計測方法が再現可能である。
- baselineとの比較値が文書に残っている。
- CSV、統計値、フレーム境界の回帰テストが通る。
- GUI停止時間とRSSが悪化していない。
- Windowsで動作確認し、release対象ならmacOS / Linuxでもsmoke testが通る。
- 新しい複雑性が責務分離またはコメントで説明されている。
- **[統合追補] 正しさ回帰がない**: 性能PRが偶発的に既存の正しさ挙動を変えて
  いないことを、annotation lifecycle / rewind(seek intent) / onset順 の
  regression test で保証する（§2.3 交差点A・B・C への対応）。

## 12. [統合追補] セキュリティ / 脆弱性監査

追加監査で見つかった、性能・正しさとは別軸の **脆弱性** 候補。研究データの
共有（CSV・project フォルダの受け渡し）を前提とすると無視できない。Codex の
バグ監査レポートにも本書 rev.1 にも無かった新規発見。

### 12.5 CSV formula injection（出力時のエスケープ欠如）

**重要度:** Medium（研究データ共有時）
**対象:** `models/annotation_model.py::export_to_csv`,
`models/analysis_model.py::_export_standard_summary / _export_interval_summary`

behavior 名は ActionMapDialog の behavior フィールドで **無制限入力**できる
（`views/action_map_view.py` の validator は *key* のみ単一英数字に制限し、
behavior ラベルは制約なし）。animal_id は CSV ファイル名由来。これらが export 時に
**エスケープなしでそのまま書き込まれる**。

セル値が `=` / `+` / `-` / `@` / TAB / CR で始まると、Excel・LibreOffice・
Google Sheets で開いた瞬間に **数式として評価**される（CSV injection / formula
injection）。研究室間で annotation/summary CSV を共有する文脈では、悪意ある（または
事故的な）behavior 名 `=HYPERLINK(...)` や `=cmd|...` が他者の端末で実行され得る。

**設計案**

- export 時、セル先頭が危険文字（`= + - @` TAB CR）なら **先頭にシングルクォート
  `'` を付与**するか、セル全体をクォートして無害化する。
- behavior 名・animal_id・metric 名・project description など **ユーザー入力由来の
  文字列セル全て**に適用する。数値セルは対象外。
- §Phase 1.4 / 順位10 の「CSV出力硬化」PR で、BUG-005（UTF-8 統一）と同じ
  export 経路の硬化として **同時に**実施する。
- ラウンドトリップ時にクォートを正しく剥がせること（`csv.reader` 前提）を回帰テスト化。

**受け入れ条件**

- `=cmd` で始まる behavior 名を含む CSV を Excel で開いても数式評価されない。
- import→export→import で behavior 名が変化しない（クォートが二重化しない）。

### 12.6 外部 project.json からの任意ファイル起動

**重要度:** Low-Medium
**対象:** `controllers/project_controller.py::_open_with_default_application`

プロジェクトの「ファイルを開く」は `os.startfile()` / `subprocess.run(['open'|'xdg-open', path])`
に **project.json 由来のパスをそのまま渡す**。`_open_video` / `_open_annotation` /
`_open_action_map` / `_open_analysis` が全て同じヘルパに集約され、**拡張子・種別検証が無い**。

共有された（あるいは改ざんされた）project.json が実行ファイルや `.desktop` / `.lnk` を
指していると、ユーザーの「開く」操作で OS ハンドラ経由で起動され得る。

**設計案**

- 開く前に **file_type と拡張子の整合**を検証（videos なら動画拡張子、annotations なら
  `.csv` 等）。想定外の拡張子は警告ダイアログ + 続行確認。
- 解決パスが **プロジェクト配下 or 既知の許可ディレクトリ**にあることを確認。
- 実行可能拡張子（`.exe` `.bat` `.cmd` `.sh` `.desktop` `.lnk` など）は既定で拒否。

**受け入れ条件**

- project.json に仕込んだ実行ファイルパスが「開く」で起動されない。
- 正規の動画/CSV/JSON は従来通り開ける。

### 12.7 メトリクス検証のバイパス（BUG-013 の補強）

**重要度:** Medium
**対象:** `models/analysis_config.py::replace_metrics`

`add_latency_metric` / `add_total_time_metric` は各リスト内の名前重複のみ検査するが、
**メトリクス設定ダイアログのコミット経路 `replace_metrics()` は検証を一切行わない**
（docstring は「将来ここに不変条件を集約」とあるが未実装）。このため latency と
total-time に同名メトリクスを設定でき、`_analyze_file` の
`name.lower().replace(' ', '_')` で生成される slug が衝突し、結果 dict が上書きされる
（`BUG_AUDIT_REPORT.ja.md` BUG-013）。

**設計案**

- 修正は `add_*` ではなく **`replace_metrics()` に置く**（全コミット経路がここを通る）。
- 全カテゴリ横断で **正規化後 slug の一意制約**を検証し、衝突時はエラーを返してダイアログで通知。

**受け入れ条件**

- latency と total-time に同名（または同一 slug 化される名前）を設定するとコミットが拒否される。
- 既存の正当な設定は影響を受けない。


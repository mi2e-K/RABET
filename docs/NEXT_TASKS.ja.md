# RABET 次タスク（バックログ） — v1.3.4 時点

> バージョンは **v1.3.4 据え置き**（`version.py` を変更しない方針）。各タスクは
> 単独で着手・検証（pytest 緑 + ruff clean）できる粒度で記述する。

## 0. 現状

- 現行版: **v1.3.4**。
- ローカル `main` は `origin/main` より先行（**未 push**）。内訳: Phase 4
  (culling / debounce / splash)、Phase 5 (near-neighbor / lazy tabs)、
  schema v2 (PR-S1/S2/S3)、4-B (raster LineCollection 化)、vis Files クリック拡大。
- 全テスト緑・ruff clean。

---

## A. パフォーマンス

### A-1. video decode worker 化 ★最優先の体感改善・規模大
- **目的**: 動画のシーク/デコードを UI スレッドから別スレッド（worker）へ移し、
  再生・シーク時の UI ブロックを解消する。RABET の応答性で最大の伸びしろ。
- **対象**: `controllers/video_controller.py`, `models/video_model.py`（PyAV デコード周辺）。
- **設計要点**: フレーム受け渡し（QThread + signal / QImage コピー）、シークの
  キャンセル/最新優先、再生レート制御、終了時のスレッド停止。seek-intent モデル
  （user/step/loader）との整合。
- **規模/リスク**: 大 / 高（並行性・フレーム同期）。**単独 PR 推奨**。まず PoC で
  1本の動画のシーク応答を計測してから本実装。

### A-2. raster の iterrows ベクトル化（4-B の続き）・小〜中
- **目的**: `_add_event_segments` の `iterrows()` ループを numpy/pandas で
  ベクトル化し、超高密度データでの segment 構築コストをさらに削減。
- **対象**: `views/visualization_view.py::_add_event_segments`。
- **注意**: 現挙動（負値・非数値の除外、bad-timestamp の warning ログ）を保つこと。
  `pd.to_numeric(errors="coerce")` + `np.isfinite` で NaN 化して除外。pandas import 追加。
- **規模**: 小。`tests/test_visualization_linecollection.py` を拡張して回帰を担保。

---

## B. UX

### B-1. file_list の Space キートグル（一貫性）・小
- `CheckableBehaviorTable` は Space でチェックをトグルできる。`ReorderableListWidget`
  （Files リスト）にも `keyPressEvent` で Space トグルを追加し、操作を統一する。
- **対象**: `views/visualization_view.py::ReorderableListWidget`。クリック拡大は実装済み。

### B-2. relink UI の磨き込み・小〜中
- PR-S3 の relink は「missing を1件ずつ QFileDialog」。複数 missing を**一覧で提示**し、
  指定先の `content_hash` が一致するものを**自動マッチ候補**として提示する
  （設計書 `PROJECT_SCHEMA_V2_DESIGN.ja.md` §3.4）。モデル側 API
  （`get_missing_videos` / `content_hash_matches` / `relink_video`）は実装済みなので、
  本タスクは view/controller 中心。

---

## C. リリース運用

### C-1. 未 push コミットの push ・要ユーザー判断
- origin は public repo（Zenodo DOI 連携）。push のタイミングはユーザーが判断。
  GitHub Release を作らない限り新 DOI は発番されない。

### C-2. v1.3.5 の CHANGELOG + GitHub Release ・保留中
- 「CHANGELOG はまだ上げない」指示により保留。次バージョン確定時に、未リリースの
  変更（Phase 4/5・schema v2・4-B・UX 改善）を CHANGELOG に整理してリリース。

---

## 完了済み（参考）

- **Phase 4**: timeline viewport culling、raster redraw debounce、splash 早期表示。
- **Phase 5**: reliability near-neighbor 候補生成、重いタブの lazy 初期化。
- **schema v2 / UUID（BUG-006）**: PR-S1（manifest v2 形状）、PR-S2（UUID 主キー＝
  移動耐性）、PR-S3（content hash + relink）。
- **4-B**: raster を behavior 単位の LineCollection 化（描画コスト削減）。
- **vis Files クリック拡大**: 行（名前ラベル）クリックでチェックをトグル、ドラッグ並べ替えは維持。

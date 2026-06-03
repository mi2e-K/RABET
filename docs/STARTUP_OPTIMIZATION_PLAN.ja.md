# 起動高速化プラン（Annotation-first shell）

> **ステータス**: 計画・着手中（PR-STARTUP-01）。video worker / seek-intent 修正とは
> **別作業**。バージョンは **v1.3.4 据え置き**で進行可。Codex の提案を実測で検証し、
> 優先度を調整した統合版。

## 1. 目的

起動時間の短縮。研究者が起動直後に「動画を開く → annotation 記録」をすぐ始められる
状態（**Annotation-first shell**）にする。Analysis / Visualization / Reliability は
それぞれ初回表示まで完全に遅延する。

## 2. 実測（`python -X importtime`）

`from controllers.app_controller import AppController` が起動時に引き込むもの（cumulative）:

| モジュール | cumulative | 経由 |
| --- | --- | --- |
| **pandas** | **~992ms** | `models.analysis_model`（最重） |
| `views.visualization_view` | ~591ms | matplotlib(~226ms) 込み |
| numpy | ~318ms | av / pandas / matplotlib が依存 |
| av (PyAV) | ~274ms | 動画再生に必須 |

→ **効果の本命は pandas(Analysis) と matplotlib(Visualization) の遅延**。両方で ~1.2s 短縮見込み。

## 3. 方針

- 起動時は動画 / annotation / timeline のみ初期化。
- 重い import（**pandas, matplotlib, pingouin, scipy, statsmodels, seaborn, PIL**）を
  対応タブの初回表示まで遅延する。
- **av / numpy は annotation に必須なので残る**（PyAV が numpy を引く）。Codex の対象
  リストから numpy は実質外す、という前提で進める。
- **importtime regression test を CI ガードに**（退行は容易に起きるため、単発の高速化
  より価値が高い）。StartupProfiler（実行時の段階測定）とは役割が別。
- PyInstaller **onedir / onefile** を実測比較（自己展開 + ウイルス対策スキャンは import
  最適化とは別軸の cold-start 要因）。

## 4. PR 分割（優先度を調整した統合版）

1. **PR-STARTUP-01**: `StartupProfiler` 追加（計測基盤・挙動不変）。← 着手中
2. **PR-STARTUP-02**: Visualization / Reliability の top-level import を `_ensure_*` 内へ
   移動（matplotlib 遅延・変更が小さく安全）。
3. **PR-STARTUP-03（test 前倒し）**: importtime regression test。02 の成果をすぐ固定。
4. **PR-STARTUP-04**: Analysis の lazy 化＝Annotation-first shell（pandas 遅延・**最大効果**・
   構造変更が大きいので test を先に用意）。Analysis→Visualization bridge は Analysis 構築後に接続。
5. **PR-STARTUP-05**: recent files / path 検証のアイドル化（OneDrive / network 遅延対策）。
6. **PR-STARTUP-06**: onedir / onefile の cold/warm start 実測レポート + 配布方針決定。
7. **(P2)**: icon / image ロードの一元キャッシュ・遅延 decode。

> 02 直後に 03(test) を挟むのが調整点。「遅延 → すぐ test で固定 → 次の遅延」で退行を防ぐ。

## 5. リスク

- 循環 import / 型ヒント → `TYPE_CHECKING`。
- 初回タブ表示の一拍遅延（import がそこで走る）→ splash / スピナーで吸収、許容範囲。
- `AnalysisModel` を lazy 化すると Analysis→Visualization bridge の接続順に注意。

## 6. StartupProfiler 設計（PR-STARTUP-01）

- `utils/startup_profiler.py`: `perf_counter()` で milestone を記録する軽量クラス。
- `RABET_STARTUP_PROFILE=1`（env）で詳細ログ、通常起動は1行 summary のみ。
- packaged build でも動く（標準ライブラリのみ）。
- `main.py` に milestone を挿入: process start / logger ready / config ready /
  QApplication / splash shown / theme applied / AppController import start・end /
  AppController init end / MainWindow init end / main window shown。
  （first paint / first interactive は後続で `QTimer.singleShot(0, ...)` を使って近似。）

## 7. 受け入れ条件

- `startup_profile` ログだけで、どの段階が重いか分かる。通常起動のオーバーヘッドはほぼ無し。
- （04 後）annotation-only 起動で pandas / matplotlib が import されない（importtime test 緑）。
- Analysis / Visualization / Reliability は初回表示で正常に構築される。

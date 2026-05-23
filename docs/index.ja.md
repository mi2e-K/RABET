---
title: RABET — Real-time Animal Behavior Event Tagger
hide:
  - navigation
  - toc
---

<div class="rabet-hero" markdown>

# RABET

### 動物行動イベントタガー（リアルタイム）

動物行動の動画アノテーションを行うための、自己完結型デスクトップ
アプリケーション。フレーム単位の精密再生、キーボード駆動のタギング、
複数ファイル CSV 解析、ラスタープロット可視化、評価者間/内信頼性評価
を備えている。

[ダウンロード（各 OS 向け） :material-download:](https://doi.org/10.5281/zenodo.15313025){ .md-button .md-button--primary }
[ユーザーガイドを読む :material-book-open-page-variant:](USER_GUIDE.md){ .md-button }
[GitHub :material-github:](https://github.com/mi2e-K/RABET){ .md-button }

</div>

<p align="center" markdown>
  ![RABET Annotation ビュー](assets/screenshot_annotation.png){ width=900 }
  <br>
  *Annotation ビュー — ビデオプレイヤー、録画操作、アクションマップ、色分けされたタイムライン。*
</p>

---

## RABET の特徴

<div class="grid cards" markdown>

-   :material-video-outline:{ .lg .middle } &nbsp;**フレーム精度の再生**

    ---

    PyAV / FFmpeg ベースのデコーダ。シングルフレーム送り、瞬時の
    シーク。VLC やコーデックパックの別途インストールは不要。

-   :material-keyboard-outline:{ .lg .middle } &nbsp;**キーボード駆動のタギング**

    ---

    設定可能なキー → 行動マッピング。キー押下で開始、リリースで
    終了。モノトニッククロックなので NTP 補正の影響を受けない。

-   :material-chart-timeline-variant:{ .lg .middle } &nbsp;**インタラクティブなタイムライン**

    ---

    色分けされた行動バーと自動スクロールする再生ヘッド。クリック
    で選択、`Delete` で削除、`Ctrl+Z` で取り消し。

-   :material-file-multiple-outline:{ .lg .middle } &nbsp;**複数ファイル解析**

    ---

    アノテーション CSV を集約してセッション全体・時間ビン単位の
    サマリーを生成。カスタム潜時・合計時間メトリクスに対応。
    Excel / JASP / R / SPSS に直接ペースト可能。

-   :material-chart-scatter-plot:{ .lg .middle } &nbsp;**ラスタープロット可視化**

    ---

    動物間を跨ぐラスタープロット。行動別カラーカスタマイズ、
    グリッド線、PNG / SVG / PDF 形式での書き出しに対応。

-   :material-scale-balance:{ .lg .middle } &nbsp;**信頼性評価を内蔵**

    ---

    評価者間／評価者内の一致度を **ICC(2,1)**、**Cohen's κ**、
    **Krippendorff's α** で計算。`psych::ICC` を使った R 言語
    リファレンス実装で検証済み。

</div>

---

## すぐに始める

<div class="grid" markdown>

=== ":material-microsoft-windows: Windows"

    ```text
    1. Zenodo から RABET-Windows-1.3.2.zip をダウンロード
    2. 任意の場所に展開（デスクトップ / Tools フォルダなど）
    3. RABET.exe をダブルクリック
    ```

=== ":material-apple: macOS (Apple Silicon)"

    ```text
    1. Zenodo から RABET-macOS-arm64-1.3.2.zip をダウンロード
    2. 展開して RABET.app を Applications にドラッグ
    3. 初回起動: 右クリック → 開く
    ```

=== ":material-apple: macOS (Intel)"

    ```text
    1. Zenodo から RABET-macOS-x86_64-1.3.2.zip をダウンロード
    2. 展開して RABET.app を Applications にドラッグ
    3. 初回起動: 右クリック → 開く
    ```

=== ":material-linux: Linux"

    ```bash
    tar -xzf RABET-Linux-x86_64-1.3.2.tar.gz
    cd RABET-linux
    ./run_rabet.sh
    ```

</div>

!!! tip "自己完結型バイナリ"
    VLC、FFmpeg、Python、scipy、R などのシステムインストールは
    一切不要である。動画再生、フレームデコード、一致度メトリクス
    計算に必要なすべての依存関係を RABET が同梱している。

---

## RABET の引用

研究に RABET が役立った場合は、ぜひ引用していただきたい。機械可読
な引用情報は [`CITATION.cff`](https://github.com/mi2e-K/RABET/blob/main/CITATION.cff)
に格納されている。人間が読む形式では次のように引用する。

> Mitsui, K. (2026). *RABET — Real-time Animal Behavior Event Tagger*
> (Version 1.3.2). https://github.com/mi2e-K/RABET
> doi:[10.5281/zenodo.15313025](https://doi.org/10.5281/zenodo.15313025)

上の DOI は **コンセプト DOI** で、常に Zenodo 上の最新リリースに
解決される。新バージョン公開後も引用先は変わらない。

RABET を解説する論文を準備中。

---

## ライセンス

[**MIT License**](https://github.com/mi2e-K/RABET/blob/main/LICENSE)
の下で公開している。

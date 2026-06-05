---
title: RABET — Real-time Animal Behavior Event Tagger
hide:
  - navigation
  - toc
---

<div class="rabet-hero" markdown>

# RABET

### Real-time Animal Behavior Event Tagger

動物行動の動画アノテーションに特化した、自己完結型のデスクトップアプリケーション。
フレーム単位での精密な再生、キーボード操作による高速なタグ付け、複数CSVファイルの解析、ラスタープロットによる可視化、評価者間・評価者内信頼性の評価に対応。

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

    PyAV / FFmpeg ベースのデコーダー。1フレームずつのコマ送りや即時シークに対応。
    VLC やコーデックパックの別途インストールは不要。

-   :material-keyboard-outline:{ .lg .middle } &nbsp;**キーボード駆動のタグ付け**

    ---

    キーと行動の対応関係を設定可能。キーを押すと記録が開始され、キーを離すと終了する。
    モノトニッククロックを使用しているため、NTP による時刻補正の影響を受けない。

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

## クイックスタート

<div class="grid" markdown>

=== ":material-microsoft-windows: Windows"

    ```text
    1. Zenodo から RABET-Windows-1.3.5-Setup.exe をダウンロード
    2. 任意の場所に展開（デスクトップ / Tools フォルダなど）
    3. RABET.exe をダブルクリック
    ```

=== ":material-apple: macOS (Apple Silicon)"

    ```text
    1. Zenodo から RABET-macOS-arm64-1.3.5.dmg をダウンロード
    2. 展開して RABET.app を Applications にドラッグ
    3. 初回起動: 右クリック → 開く
    ```

=== ":material-apple: macOS (Intel)"

    ```text
    1. Zenodo から RABET-macOS-x86_64-1.3.5.dmg をダウンロード
    2. 展開して RABET.app を Applications にドラッグ
    3. 初回起動: 右クリック → 開く
    ```

=== ":material-linux: Linux"

    ```bash
    chmod +x RABET-Linux-x86_64-1.3.5.AppImage
    ./RABET-Linux-x86_64-1.3.5.AppImage
    ```

</div>

!!! tip "自己完結型バイナリ"
    VLC、FFmpeg、Python、scipy、R などのシステムインストールは
    一切不要。動画再生、フレームデコード、一致度メトリクス
    計算に必要なすべての依存関係を RABET が同梱済み。

---

## RABET の引用

研究で RABET をご利用いただいた場合は、ぜひ引用をお願いいたします。機械可読形式の引用情報は [`CITATION.cff`](https://github.com/mi2e-K/RABET/blob/main/CITATION.cff)
に記載されています。人間が読みやすい形式の引用例は以下のとおりです。

> Mitsui, K. (2026). *RABET — Real-time Animal Behavior Event Tagger*
> (Version 1.3.5). https://github.com/mi2e-K/RABET
> doi:[10.5281/zenodo.15313025](https://doi.org/10.5281/zenodo.15313025)

上記の DOI は **コンセプト DOI** であり、Zenodo 上の最新リリースに常に紐づきます。新しいバージョンが公開された後も、引用先を変更する必要はありません。

RABET を解説する論文を準備中。

---

## ライセンス

[**MIT License**](https://github.com/mi2e-K/RABET/blob/main/LICENSE)

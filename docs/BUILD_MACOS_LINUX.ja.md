# RABET macOS / Linux ビルドノート

このページは、RABET を macOS または Linux 上で PyInstaller パッケージとして
ビルドするためのメモです。通常のユーザーは
[GitHub Releases](https://github.com/mi2e-K/RABET/releases/latest) から配布版を
ダウンロードすればよく、この手順は必要ありません。

RABET 1.3.1 以降、動画バックエンドは python-vlc ではなく PyAV
（FFmpeg Python bindings）です。PyAV の wheel には FFmpeg が同梱されるため、
作成した RABET パッケージは自己完結型になります。配布先のマシンに VLC や
FFmpeg を別途インストールする必要はありません。

---

## 共通ルール

ビルドは原則として **対象 OS 上で行います**。

- macOS の `.app` は macOS 上で作成します。
- Linux パッケージは Linux 上で作成します。
- できるだけクリーンな仮想環境を使います。
- RABET 1.3.1 以降、ビルド環境にも実行環境にもシステム VLC / FFmpeg は不要です。

---

## macOS

借りた Mac などで最小限にビルドする例です。

```bash
cd /path/to/RABET_1.4.0
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python packaging/build_macos_optimized.py
```

### 出力

- `dist/RABET.app`
- `dist/RABET-macOS.zip`  
  `RABET.app` と `README.txt` を含む zip です。
- `dist/README.txt`

### 主なオプション

```bash
python packaging/build_macos_optimized.py --target-arch arm64
python packaging/build_macos_optimized.py --target-arch x86_64
python packaging/build_macos_optimized.py --console --verbose
python packaging/build_macos_optimized.py --spec-only
```

### メモ

- Apple Silicon Mac では通常 arm64 ビルドになります。
- Intel Mac では通常 x86_64 ビルドになります。
- `--target-arch universal2` は、Python 本体とインストール済み wheel が
  universal2 に対応している場合のみ使えます。
- 未署名アプリは、初回起動時に Gatekeeper に止められることがあります。
- zip で共有したアプリが macOS にブロックされる場合は、受け取った側で次の
  quarantine 解除が必要になることがあります。

```bash
xattr -dr com.apple.quarantine RABET.app
```

---

## Linux / Ubuntu

Ubuntu での例です。

```bash
sudo apt update
# 1.3.1 以降、vlc / libvlc-bin は不要です。
# Qt の xcb platform plugin が必要とする GUI ランタイムライブラリを入れます。
sudo apt install -y \
  python3 \
  python3-venv \
  python3-pip \
  libxcb-cursor0 \
  libxcb-icccm4 \
  libxcb-image0 \
  libxcb-keysyms1 \
  libxcb-render-util0 \
  libxcb-xkb1 \
  libxcb-randr0 \
  libxcb-render0 \
  libxcb-shape0 \
  libxcb-shm0 \
  libxcb-sync1 \
  libxcb-xfixes0 \
  libxkbcommon-x11-0 \
  libxrender1 \
  libx11-xcb1 \
  libsm6 \
  libice6 \
  libglib2.0-0 \
  libfontconfig1 \
  libfreetype6

cd /path/to/RABET_1.4.0
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python packaging/build_linux_optimized.py --onefile
```

### 出力

- `dist/RABET-linux/`
- `dist/RABET-linux-<arch>.tar.gz`

### ローカルで実行する

```bash
cd dist/RABET-linux
./run_rabet.sh
```

### デスクトップランチャーを登録する

現在のユーザー向けにランチャーを登録する場合:

```bash
cd dist/RABET-linux
./install_desktop_entry.sh
```

### 主なオプション

```bash
python packaging/build_linux_optimized.py --console --verbose
python packaging/build_linux_optimized.py
python packaging/build_linux_optimized.py --upx
python packaging/build_linux_optimized.py --spec-only
```

### メモ

- リリースビルドでは `--onefile` を使います。そのため、配布アーカイブ内に
  `_internal/` フォルダは見えない想定です。
- `--onefile` なしの onedir ビルドは、開発時やデバッグ時には便利です。
- `--onefile` は起動時に一時展開を行うため、起動が少し遅くなることがあります。
- Linux の生の実行ファイルは、ファイルマネージャ上でカスタムアイコンが安定して
  表示されません。アイコン付きで使いたい場合は `install_desktop_entry.sh` を
  使ってください。
- `--upx` は UPX がインストールされていればサイズ削減に使えます。ただし Qt
  バイナリは圧縮で壊れることがあるため、必ず実行テストしてください。
- 可能であれば、サポートしたい中で最も古い Ubuntu バージョン上でビルドして
  ください。新しい Linux 上で作ったバイナリは、新しいシステムライブラリに依存
  することがあります。

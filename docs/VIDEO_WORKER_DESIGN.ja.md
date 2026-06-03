# 動画デコードの worker スレッド化 設計（NEXT_TASKS A-1）

> **ステータス**: 設計確定・**未実装**。バージョンは **v1.3.4 据え置き**で進められる。
> リスク高（PyAV のスレッド安全性・再生/シーク回帰）のため **PoC（PR-V1）→ 計測 →
> 本実装** の順で、各段階 pytest 緑 + 手動再生確認を必須とする。

## 1. 目的

動画のシーク・デコード・フレーム変換（libswscale）を **UI スレッドから worker
スレッドへ**移し、再生中のカクつき・シーク時の固まりを解消する。RABET の応答性で
最大の伸びしろ。

## 2. 現状（実装前に理解すること）

`models/video_model.py`（`VideoModel(QObject)`, PyAV backend）:

- `_container` / `_stream` を開いたまま保持。
- 再生は **UI スレッドの `QTimer`**（`_playback_timer`, PreciseTimer）。
  `_on_playback_tick` が毎回 `_decode_next_frame` →（`_reformat_to_rgb` →
  `_frame_to_qimage`）→ `frame_ready.emit(QImage)` を**同期実行**。
- `seek(position_ms)` も UI スレッドで `container.seek(..., backward=True)` +
  複数フレーム decode して「target_pts に最も近いフレーム」を選び emit。
- `_operation_in_progress` は常に False（全 decode が main thread 同期）。
- `_decode_lock = threading.Lock()` は **将来の worker 化を見越して既設**
  （line 191-194 のコメント）。

### 2.1 公開 API（壊してはいけない契約）

- **Signals**: `playback_state_changed(bool)` / `position_changed(int)` /
  `duration_changed(int)` / `video_loaded(str)` / `error_occurred(str)` /
  `frame_ready(QImage)` / `render_load_changed(bool)`。
- **メソッド**: `load_video` / `play` / `pause` / `stop` / `seek` /
  `seek_with_retry` / `step_forward` / `step_backward` / `toggle_play` /
  `set_playback_rate` / `set_target_display_size` / `get_duration` /
  `get_position` / `get_frame_rate` / `is_playing` / `close`。
- **内部属性で外部が読むもの**: `_frame_duration_ms`（`annotation_controller.py`,
  `annotation_model.py` が参照）、`_video_path` / `_duration` /
  `_last_seek_position`（`video_controller.py` が参照）。

### 2.2 Controller 連携（`controllers/video_controller.py`）

- view → model: `play_clicked→play` / `pause_clicked→pause` /
  `seek_requested→handle_seek→seek` / `step_*` / `rate_changed→set_playback_rate` /
  `display_size_changed→set_target_display_size`。
- model → view: `frame_ready→view.display_frame` /
  `position_changed→view.set_position` / `duration_changed→set_duration` /
  `playback_state_changed→set_playing_state` / `render_load_changed→`(scaling)。
- seek-intent モデル（user/step/loader）が `handle_seek` / `notify_seek_intent`
  と連動。worker 化後も intent の発火タイミング（seek 前に origin をタグ）を保つ。

## 3. 制約

- **PyAV の `container` / `stream` はスレッドセーフでない**。全 av 操作
  （open/decode/seek/close）を**単一 worker スレッド**に集約する。UI スレッドは
  一切 av に触れない。
- 上記 API（signals・メソッド名・内部属性）を維持し、View/Controller は原則無改修。
- `frame_ready(QImage)` は cross-thread emit になる（queued connection）。

## 4. 設計: ファサード + worker（moveToThread）

`VideoModel` を **UI スレッド側のファサード**に保ち、内部に
`VideoDecodeWorker(QObject)` を新設して **`QThread` に `moveToThread`** する。

```
[UI thread]                         [worker thread]
VideoModel (facade, QObject)        VideoDecodeWorker (QObject)
  play()/pause()/seek()/...  --->     _container / _stream (PyAV)
    (queued invoke)                   _playback_timer (lives here)
  frame_ready/position_changed <---   decode/reformat/QImage
    (queued signal)                   emits results
```

- **UI→worker**: ファサードの各メソッドは `QMetaObject.invokeMethod(worker,
  "...", Qt.QueuedConnection, ...)`（または worker の slot に繋いだ内部 signal）で
  worker スレッドへ委譲。ファサードは**即座に返る**（UI を待たせない）。
- **worker→UI**: worker が `frame_ready` / `position_changed` /
  `playback_state_changed` / `render_load_changed` / `error_occurred` を emit。
  ファサードはこれを**そのまま再 emit**（または worker の signal を直接 View に接続）
  して既存の接続を生かす。
- **`_playback_timer` は worker スレッドで生成・start**。`moveToThread` 後に
  worker 内で QTimer を作れば tick は worker スレッドで発火する。

### 4.1 seek の最新優先（coalescing）

スライダードラッグ中の大量 seek で worker が詰まらないよう、worker に
`_pending_seek_ms`（最新値1つ）を持たせ、処理直前に最新だけを実行、中間 seek は捨てる。
`invokeMethod` の queue に積むのではなく「最新値を上書き + wake」する方式。

### 4.2 QImage の受け渡し

`_frame_to_qimage` は worker で**毎回新規 QImage**を生成して emit
（現状も新規生成）。implicitly shared だが worker は以後そのバッファを触らないため
read-only な受信側と競合しない。安全側に倒すなら emit 直前に `.copy()`。

### 4.3 安全な停止

`close()` / アプリ終了で worker に stop を投げ、`_playback_timer.stop()` →
`container` close → `QThread.quit()` → `wait(timeout)`。進行中 decode は
`_decode_lock` で保護。`__del__` / `closeEvent` 経路でも join を保証。

## 5. 段階実装（単独 PR、PoC から）

- **PR-V1（PoC・計測）**: `VideoDecodeWorker` + `QThread` スケルトン。`load_video` と
  **単発 seek のみ** worker 化し、シーク応答（要求→`frame_ready`）の前後を計測。
  再生は現状のまま。最小リスクで効果検証 → 本実装の Go/No-Go 判断。
- **PR-V2（再生 worker 化）**: `_playback_timer` と `_on_playback_tick` を worker へ。
  `render_load_changed`（負荷適応）の計測も worker 基準に。
- **PR-V3（仕上げ）**: seek coalescing（§4.1）、`step_forward/backward`、FBF、
  `close` 時の安全停止（§4.3）、エッジケース（load 中 seek、EOF、rate 変更）。

## 6. リスク

- **高**: PyAV スレッド安全性 → 全 av を1スレッドに集約しないとクラッシュ/破損。
- **中**: `QTimer` の moveToThread 後挙動、queued connection の1フレーム遅延、
  QImage の cross-thread 共有、seek-intent の発火順序。
- **回帰**: 再生 / シーク / step / FBF / annotation 連携。各段階で pytest（offscreen）
  + 実動画での手動再生・シーク確認。

## 7. テスト計画

- worker のコマンド委譲（play/pause/seek が worker slot に届く）。
- `frame_ready` が UI スレッドで受信される（queued connection）。
- seek coalescing（連続 seek で最新だけ処理、中間は捨てる）。
- `close` 時にスレッドが join し container が閉じる（リーク/クラッシュなし）。
- 既存 API の後方互換（signals・メソッド・`_frame_duration_ms` 等の属性）。
- 実デコードは CI で重く不安定 → **モック container** か数フレームの極小テスト動画で。

## 8. 変えてはいけないもの

- §2.1 の signals / メソッド名 / 内部属性。
- seek-intent（user/step/loader）の発火タイミングと、preserve-on-rewind の挙動。
- フレーム精度シーク（closest-frame 選択）の結果。

## 9. 実装計画（確定版・ファサード分離）

VideoModel 全体を読み切った結果、ファサード方式を以下で確定する。Controller /
loader は **原則無改修**（理由は 9.4）。

### 9.1 worker = いまの VideoModel をリネーム

`class VideoModel` → `class _VideoDecodeWorker(QObject)`（av ロジックは丸ごと
据え置き）。コマンドメソッドの `@Slot` 状況:

- **既に @Slot**: `load_video(str)` / `play()` / `pause()` / `stop()` /
  `toggle_play()` / `set_target_display_size(int,int)`（設計者の地ならし）。
- **@Slot を追加**: `seek(int)` / `seek_with_retry(int)` / `step_forward(int)` /
  `step_backward(int)` / `set_playback_rate(float)` / `close()`。
- 新 signal `frame_rate_changed(float, int)` を追加し、`_populate_stream_metadata`
  の末尾で `emit(self._frame_rate, self._frame_duration_ms)`。

### 9.2 ファサード = 新 VideoModel（薄い QObject、UI スレッド）

- `__init__`: `_VideoDecodeWorker` を生成 → `QThread` に `moveToThread` →
  `thread.start()`。worker の全 signal を中継スロットへ接続。
- **commands（非同期）**: `play/pause/stop/toggle_play/seek/seek_with_retry/
  step_forward/step_backward/set_playback_rate/set_target_display_size` は
  `QMetaObject.invokeMethod(worker, name, Qt.QueuedConnection, Q_ARG(...))`。
  戻り値は使われていない（`video_controller` は seek/step の戻り値を破棄）。
- **同期が要るもの**: `load_video(str)->bool` と `close()` は
  `Qt.BlockingQueuedConnection`（load は成否を `ThreadedVideoLoader` が受けるため、
  close はスレッド停止前に container を確実に閉じるため）。load の同期待ちは
  現状（UI スレッド load）と同じブロック特性なので許容（A-1 の主目的は再生/シーク）。
- **state reads（同期・スレッド安全）**: `get_position/get_duration/
  get_frame_rate/is_playing` と属性 `_video_path/_duration/_last_seek_position/
  _frame_duration_ms` は **UI 側キャッシュ**を返す。
- **signal 中継**: `position_changed/duration_changed/playback_state_changed/
  video_loaded/frame_rate_changed` を受けてキャッシュ更新 + 自身の同名 signal を
  再 emit。`frame_ready/render_load_changed/error_occurred` は素通し。

### 9.3 ライフサイクル

`close()` → worker.close（Blocking）→ `thread.quit()` → `thread.wait(timeout)`。
ファサードが `QThread` を内包するので、`app_controller`（`VideoModel()`）と
`disagreement_review_view`（別インスタンス）の生成箇所は**無改修**。

### 9.4 Controller / loader を無改修にできる根拠

- `view.play_clicked.connect(model.play)` 等の **signal→slot 接続は、ファサードが
  内部で worker に invoke するので、ファサード側は通常メソッドのまま**。
- 直接呼び出し（`model.seek(...)` / `stop()` / `close()` / `step_*`）も、ファサードの
  メソッド内で invoke するため、呼び出し側は不変。
- `ThreadedVideoLoader._perform_load` の `success = model.load_video(...)` は
  BlockingQueued で同期 bool が返るため不変。

### 9.5 テスト

- ファサード: commands が worker slot に届く（QSignalSpy / フラグ）、frame_ready 等が
  中継される、get_* がキャッシュを返す、close でスレッド join。
- 実 decode はモック worker か極小動画で。既存 video 関連テストの回帰。
- 実機: 再生・シーク・step・FBF・annotation 連携の手動確認（必須）。

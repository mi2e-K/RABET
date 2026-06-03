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

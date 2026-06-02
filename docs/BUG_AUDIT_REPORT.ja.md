# RABET 1.3.3 バグ監査レポート

## 1. 目的

この文書は、RABET 1.3.3 のコード読解と読み取り中心の検証で見つかった
不具合候補、エッジケース、設計上の脆弱な境界を整理した内部向けレポートです。

対象は次の領域です。

- キーボード操作とannotation event lifecycle
- timed recording、pause、resume、rewind、frame-by-frame mode
- CSV import / exportとschema互換性
- action mapとcustom metrics
- Project manifest、copy / link / reference
- settings、OS差、日本語path
- Analysis、Visualization、Reliability
- drag-and-drop、終了処理、長時間運用

コードの根拠がある問題と、追加検証が必要な仮説を分けて記載します。

## 2. 調査方法

### 2.1 読み込んだ主な領域

```text
README.md
docs/
main.py
controllers/
models/
views/
utils/
packaging/
tests/
configs/
.github/workflows/
```

### 2.2 実行した確認

```powershell
python -m pytest -q
python -m ruff check .
```

結果:

- `pytest`: 43件成功
- `ruff`: 全件成功
- コード変更なし

### 2.3 既存テストの注意点

現在ローカルにあるテストはReliability機能を中心としています。
Annotation、Project、CSV round-trip、Video、Analysisの主要境界は十分に
カバーされていません。

また、`.gitignore` は `tests/` を除外しており、CIはruffのみを実行します。
ローカルで43件が成功していても、リポジトリのCIで継続的に保証される状態では
ありません。

## 3. 確証レベル

| 表記 | 意味 |
| --- | --- |
| 再現済み | 小さな一時データまたはstubで、現行コード上の挙動を実行確認した |
| 静的確認済み | コード分岐から挙動が明確である。GUI操作による実機再現は未実施 |
| 仮説 | 壊れやすい境界だが、再現fixtureまたは実機確認が必要 |

## 4. エグゼクティブサマリー

### 4.1 重要度別件数

| 重要度 | 件数 | 備考 |
| --- | ---: | --- |
| Critical | 0 | 即時に全データを破壊する確証済み問題は確認されなかった |
| High | 7 | 研究データ欠落、保存失敗、project関連付け破損、OS間互換性に関係 |
| Medium | 16 | 状態drift、CSV品質、分析値の意味、復旧性、Reliability QAに関係 |
| Low | 4 | 主に外部連携、UX、設定整理 |

### 4.2 最優先で修正する問題

1. Waiting状態でSpaceを押しても録画が始まらず、最初のbehavior keyが失われる。
2. Frame-by-frame modeのactive eventがstop後も残る。
3. ウィンドウの閉じる操作で未保存確認を迂回できる。
4. 壊れたCSVをimportすると、既存annotationが先に消える。
5. UTF-8仕様が複数のCSV / JSON I/O経路で保証されていない。
6. Projectフォルダ移動で内部video IDが変化する。
7. Project manifest保存失敗を新規project作成成功として扱う。

## 5. High: 優先修正が必要な問題

## BUG-001: Waiting後にSpaceで録画が開始されない

| 項目 | 内容 |
| --- | --- |
| 重要度 | High |
| 確証 | 静的確認済み |
| 対象 | `views/main_window.py::keyPressEvent`, `handleSpaceKey`; `views/recording_control_view.py::set_waiting_state` |
| 影響 | 最初のbehavior event欠落、ユーザーガイドとの不一致 |
| 判断 | 即修正 |

### 問題

ユーザーガイドは、Start RecordingをクリックしてWaiting状態に入り、
Spaceで動画を再生するとsessionが開始すると説明しています。

しかし `MainWindow.keyPressEvent()` はSpaceを先に処理してreturnします。
Waiting状態を実録画へ遷移させる分岐は、その後ろにあります。

結果としてSpaceだけでは録画sessionが開始しません。その後に押した最初の
印字可能キーが録画開始トリガーになりますが、そのキー自体はannotationとして
送信されずに捨てられます。

### 再現手順

1. 動画を読み込む。
2. Start Recordingをクリックする。
3. Waiting表示を確認する。
4. Spaceで動画を再生する。
5. 録画状態がWaitingのままであることを確認する。
6. mapped behavior keyを押す。
7. 録画は開始するが、その最初のeventが記録されないことを確認する。

### 修正方針

- session開始契約を一つに決める。
- 推奨: Waiting中にplaybackが開始した時点でsessionを開始する。
- Waiting中のbehavior keyを開始トリガーとして許す場合は、同じkey pressを
  session開始後のannotation処理へ引き渡す。
- ガイド、UI表示、実装を同じ契約へ揃える。

### 追加テスト

- `test_waiting_space_starts_recording_session`
- `test_first_behavior_key_is_recorded_when_it_starts_session`
- `test_waiting_cancel_does_not_create_recording_start`

## BUG-002: FBF active eventがstop後も残る

| 項目 | 内容 |
| --- | --- |
| 重要度 | High |
| 確証 | 再現済み |
| 対象 | `controllers/annotation_controller.py::_handle_fbf_key_press`, `stop_timed_recording`, `pause_recording`, `_complete_recording` |
| 影響 | eventのexport漏れ、stuck event、次sessionへの状態持越し |
| 判断 | 即修正 |

### 問題

Frame-by-frame modeは、最初のkey pressでevent開始、同じkeyの次のpressで終了します。
この開始処理は `AnnotationModel._active_events` にeventを追加しますが、
realtime mode用の `_key_press_times` には追加しません。

一方、manual stop、pause、auto-completeは `_key_press_times` のkeyだけを終了します。
そのためFBF active eventは残ります。

### 再現結果

一時stubで次の状態を確認しました。

```text
active_before_stop = ['a']
active_after_stop  = ['a']
```

### 修正方針

- session終了処理を一か所へ集約する。
- realtime / FBFを問わず、`AnnotationModel.get_active_events()` をsource of truthにする。
- stop、pause、auto-complete、動画切替、アプリ終了で同じcleanup helperを呼ぶ。
- FBF active eventを「終了」するか「破棄」するか、操作別に明示する。
  - manual stop: 現在playheadで終了
  - auto-complete: session末尾で終了
  - cancel: 確認後に破棄

### 追加テスト

- `test_fbf_manual_stop_finalizes_active_event`
- `test_fbf_auto_complete_finalizes_active_event`
- `test_fbf_pause_policy_is_explicit`
- `test_video_switch_cleans_fbf_active_event`

## BUG-003: ウィンドウ終了で未保存確認を迂回できる

| 項目 | 内容 |
| --- | --- |
| 重要度 | High |
| 確証 | 静的確認済み |
| 対象 | `controllers/app_controller.py::handle_exit_action`; `views/main_window.py::closeEvent` |
| 影響 | 未保存project、録画中annotation、未export eventの消失 |
| 判断 | 即修正 |

### 問題

FileメニューのExitは `AppController.handle_exit_action()` を通り、
未保存projectの確認を行います。

しかしOSの閉じるボタンやAlt+F4は `MainWindow.closeEvent()` へ直接入り、
UI settingsを保存した後、そのままcloseします。

さらに、File Exit側もannotation dirty状態と録画中sessionを確認しません。

### 修正方針

- `request_application_close()` を一つだけ用意する。
- File Exit、ウィンドウclose、OS終了要求を同じguardへ通す。
- 確認順序を固定する。
  1. 録画中sessionのstop / cancel
  2. active eventの終了 / 破棄
  3. 未保存annotationのexport / discard / cancel
  4. 未保存project manifestのsave / discard / cancel
  5. settings保存
- cancel時はclose eventを `ignore()` する。

### 追加テスト

- `test_window_close_prompts_for_dirty_annotations`
- `test_window_close_prompts_for_modified_project`
- `test_window_close_can_be_cancelled`
- `test_exit_action_and_window_close_share_guard`

## BUG-004: 不正CSV importが既存annotationを先に削除する

| 項目 | 内容 |
| --- | --- |
| 重要度 | High |
| 確証 | 再現済み |
| 対象 | `models/annotation_model.py::import_from_csv` |
| 影響 | import失敗時の既存データ消失 |
| 判断 | 即修正 |

### 問題

`import_from_csv()` はCSVを検証する前に `clear_events()` を呼びます。
不正CSVや空CSVを選ぶと、importはFalseを返しますが既存eventは失われます。

### 再現結果

```text
import_return = False
events_after  = []
```

import前に存在した `RecordingStart` markerも消えました。

### 修正方針

- parse結果をtemporary listへ格納する。
- metadata、event rows、warning一覧を検証する。
- 1件以上の有効eventがあり、置換可能と判断した後だけcommitする。
- import結果に `imported`, `skipped`, `warnings`, `schema` を持たせる。
- 修復可能なCSVはpreview dialogで確認してから置換する。

### 追加テスト

- `test_invalid_import_preserves_existing_annotations`
- `test_empty_import_preserves_existing_annotations`
- `test_partial_import_reports_skipped_rows_before_commit`
- `test_valid_import_replaces_existing_annotations_once`

## BUG-005: UTF-8仕様が複数I/O経路で保証されない

| 項目 | 内容 |
| --- | --- |
| 重要度 | High |
| 確証 | 静的確認済み。実害はOS locale依存 |
| 対象 | Annotation CSV、Analysis CSV、Action Map JSON、Metrics JSON、FileManager JSON / CSV |
| 影響 | 日本語behavior名、project description、OS間ファイル交換の失敗 |
| 判断 | 即修正 |

### 問題

`docs/CSV_FORMAT.md` は全CSVをUTF-8と定義しています。
しかし複数の `open()` 呼出に `encoding='utf-8'` がありません。
Windowsの既定codepageでは、日本語を含むCSVやJSONが別OSで読めない可能性があります。

### 主な対象

```text
models/annotation_model.py
models/analysis_model.py
models/action_map_model.py
models/analysis_config.py
utils/file_manager.py
utils/config_path_manager.py
```

### 修正方針

- text I/OはUTF-8へ統一する。
- CSVは `newline=''` と `encoding='utf-8'` を併用する。
- Excel利用を重視するexportだけ `utf-8-sig` optionを検討する。
- v0互換importではUTF-8 decode失敗時に明示的なfallbackを提供する。
- silent fallbackではなく、使用したencodingをlogとQA reportへ残す。

### 追加テスト

- `test_annotation_csv_unicode_round_trip`
- `test_action_map_unicode_round_trip`
- `test_project_description_unicode_round_trip`
- `test_analysis_export_unicode_behavior`
- 日本語・空白入りpathのWindows smoke test

## BUG-006: Project移動で内部video IDが変わる

| 項目 | 内容 |
| --- | --- |
| 重要度 | High |
| 確証 | 再現済み |
| 対象 | `models/project_model.py::_normalize_video_reference`, `_get_video_id` |
| 影響 | annotation status、video_annotation_files mappingのorphan化 |
| 判断 | 次のv1.xで修正 |

### 問題

Project内の相対video pathは、一度project rootを含む絶対pathへ変換され、
その値をSHA-1 hashへ入力します。

Projectフォルダを別の場所へ移動すると、同じ `videos/mouse.mp4` でもIDが変わります。

### 再現結果

```text
id_before_move = mouse__c0b4aaeaf47c
id_after_move  = mouse__d2b76341e6f8
stable         = False
```

### 修正方針

- Project内のcopy済み動画はproject-relative canonical pathをID入力にする。
- 外部referenceはmanifest内のstable UUIDを使用する。
- manifestへ `schema_version` とvideo entry objectを導入する。

```json
{
  "schema_version": 2,
  "videos": [
    {
      "id": "uuid",
      "path": "videos/mouse.mp4",
      "storage": "copied"
    }
  ]
}
```

- v1 manifest読込時にmigrationし、旧mappingをUUIDへ移す。

### 追加テスト

- `test_project_copied_video_id_survives_project_relocation`
- `test_project_external_reference_relink_preserves_uuid`
- `test_manifest_v1_to_v2_migration`

## BUG-007: manifest保存失敗をproject作成成功として扱う

| 項目 | 内容 |
| --- | --- |
| 重要度 | High |
| 確証 | 再現済み |
| 対象 | `models/project_model.py::create_project` |
| 影響 | `project.json` がないのにproject open状態になる |
| 判断 | 即修正 |

### 問題

`create_project()` は `_save_project_config(project_dir)` の戻り値を検査しません。
保存に失敗しても `_project_path` を設定し、Trueを返します。

### 再現結果

保存を常にFalseにするFileManager stubで確認しました。

```text
create_project_return = True
manifest_exists       = False
model_open            = True
```

### 修正方針

- manifest保存の戻り値を必ず検査する。
- 失敗時はproject open状態へ遷移しない。
- 新規作成した空directoryを削除するか、復旧案内を表示する。
- 保存はatomic writeへ変更する。

### 追加テスト

- `test_create_project_fails_when_manifest_write_fails`
- `test_create_project_rolls_back_model_state_on_write_failure`
- `test_create_project_does_not_emit_created_signal_on_failure`

## 6. Medium: 早期に整理すべき問題

## BUG-008: stop後のFBF残留eventをEscで救済できない

| 項目 | 内容 |
| --- | --- |
| 重要度 | Medium |
| 確証 | 静的確認済み |
| 対象 | `controllers/annotation_controller.py::abort_all_active_events` |
| 問題 | `_is_recording == False` ならactive eventがあっても即returnする |
| 修正 | active eventの存在を基準に救済可能にする |
| テスト | `test_escape_can_abort_stale_active_event_after_stop` |

## BUG-009: RecordingStart markerがCSV round-tripで1 frame eventになる

| 項目 | 内容 |
| --- | --- |
| 重要度 | Medium |
| 確証 | 再現済み |
| 対象 | `models/annotation_model.py::import_from_csv` |
| 問題 | `offset <= onset` clampがsynthetic markerにも適用される |
| 再現 | `1000ms, 1000ms` がimport後 `1000ms, 1033ms` になった |
| 修正 | `RecordingStart` はzero-durationを維持する |
| テスト | `test_recording_start_remains_zero_duration_after_round_trip` |

## BUG-010: 未割当keyでもcontroller側のpress追跡が残る

| 項目 | 内容 |
| --- | --- |
| 重要度 | Medium |
| 確証 | 再現済み |
| 対象 | `controllers/annotation_controller.py::on_key_pressed` |
| 問題 | `start_event()` 成功前に `_key_press_times[key]` を保存する |
| 再現 | 未割当 `z` を押すとactive eventは空だがtracking dictに `z` が残る |
| 修正 | event開始成功後だけ追跡し、release cleanupは `finally` で行う |
| テスト | `test_unmapped_key_does_not_leave_press_tracking` |

## BUG-011: action mapが重複behavior名を許可する

| 項目 | 内容 |
| --- | --- |
| 重要度 | Medium |
| 確証 | 再現済み |
| 対象 | `models/action_map_model.py::load_from_json`, `add_mapping`; `models/annotation_model.py::_find_key_for_behavior` |
| 問題 | `a` と `b` に同じbehavior名を割当可能。import時は先頭keyだけが選ばれる |
| 修正 | aliasとして正式対応するか、validatorで禁止する |
| テスト | `test_action_map_duplicate_behavior_policy` |

### プロダクト判断

推奨は、v1.xでは重複名を禁止することです。複数key aliasを正式対応する場合は、
CSVがbehavior中心であること、UI表示、active state、summary集約の意味を
明文化する必要があります。

## BUG-012: 録画中のaction map変更でactive状態がずれる可能性がある

| 項目 | 内容 |
| --- | --- |
| 重要度 | Medium |
| 確証 | 仮説 |
| 対象 | `models/action_map_model.py::remove_mapping`; Annotation lifecycle |
| 問題 | active keyのmappingを削除するとActionMap側active表示だけ先に消える |
| 修正 | 録画中はmap編集をlockするか、session開始時にmap snapshotを固定する |
| テスト | `test_remove_mapping_during_active_event_policy` |

## BUG-013: latency metricとtotal-time metricの内部keyが衝突する

| 項目 | 内容 |
| --- | --- |
| 重要度 | Medium |
| 確証 | 再現済み |
| 対象 | `models/analysis_config.py`; `models/analysis_model.py` |
| 問題 | 種別をまたいで同名metricを追加でき、両方が同じslugへ保存される |
| 再現 | latencyとtotal-timeの両方に `Shared Name` を追加できた |
| 修正 | 全カテゴリ横断で正規化後slugのunique制約を設ける |
| テスト | `test_metrics_reject_cross_category_slug_collision` |

## BUG-014: 同一annotationに複数RecordingStartが蓄積する

| 項目 | 内容 |
| --- | --- |
| 重要度 | Medium |
| 確証 | 静的確認済み |
| 対象 | `controllers/annotation_controller.py::start_timed_recording`; `models/analysis_model.py` |
| 問題 | 再録画ごとにmarker追加。intervalは最初のmarker、latencyは別ロジックで選択する |
| 影響 | 同じCSV内でsession意味が曖昧になる |
| 修正 | v1.xでは1 CSV = 1 sessionに制限し、新規録画時にclear / export確認を出す |
| テスト | `test_second_recording_session_requires_explicit_policy` |

## BUG-015: summary parserがquoted commaを扱えない

| 項目 | 内容 |
| --- | --- |
| 重要度 | Medium |
| 確証 | 再現済み |
| 対象 | `models/analysis_model.py::_extract_summary_data` |
| 問題 | `line.split(',')` がCSV quotingを無視する |
| 再現 | `"Investigate, object",1.25,2` を解析できなかった |
| 修正 | `csv.reader` を使う |
| テスト | `test_summary_parser_accepts_quoted_behavior_with_comma` |

## BUG-016: event table header parserが厳密すぎる

| 項目 | 内容 |
| --- | --- |
| 重要度 | Medium |
| 確証 | 再現済み |
| 対象 | `utils/annotation_csv_parser.py::extract_event_dataframe` |
| 問題 | `Event,Onset,Offset` の完全一致だけをsection headerとして認識する |
| 影響 | BOM、空白、列名case、外部ツール出力で列名が正規化されない |
| 修正 | `csv.reader` でheaderをparseし、strip、BOM除去、casefold、未知列許可を行う |
| テスト | `test_event_parser_normalizes_spaced_bom_header` |

## BUG-017: Offsetが空のrowを完了eventとしてimportする

| 項目 | 内容 |
| --- | --- |
| 重要度 | Medium |
| 確証 | 静的確認済み |
| 対象 | `models/annotation_model.py::import_from_csv` |
| 問題 | `offset=None` のeventが `_events` に入るが `_active_events` には入らない |
| 影響 | Timelineはactive風表示、Analysisはrowをdrop、意味が一致しない |
| 修正 | QA warningを出し、skip / repair / incomplete importの方針を選ばせる |
| テスト | `test_import_empty_offset_requires_explicit_repair_policy` |

## BUG-018: Config defaultsがinstance間で共有される

| 項目 | 内容 |
| --- | --- |
| 重要度 | Medium |
| 確証 | 再現済み |
| 対象 | `utils/config_manager.py::__init__`, `reset_to_defaults` |
| 問題 | `DEFAULT_CONFIG.copy()` はshallow copy。nested dict変更がclass defaultを変更する |
| 再現 | instanceでzoomを777へ変更すると `DEFAULT_CONFIG` 側も777になった |
| 修正 | `copy.deepcopy(DEFAULT_CONFIG)` を使う |
| テスト | `test_config_instances_do_not_share_nested_defaults` |

## BUG-019: Project manifestとsettingsが非atomic保存

| 項目 | 内容 |
| --- | --- |
| 重要度 | Medium |
| 確証 | 静的確認済み |
| 対象 | `utils/file_manager.py::save_json`; `models/project_model.py::_save_project_config` |
| 問題 | JSONを直接 `'w'` で上書きするため、中断時に空または途中までのJSONになる |
| 修正 | same-directory temp file、flush、可能ならfsync、`os.replace()`、`.bak` |
| テスト | `test_atomic_json_save_preserves_previous_manifest_on_failure` |

## BUG-020: Reliability summaryの片側だけにあるmetricが結果へ残らない

| 項目 | 内容 |
| --- | --- |
| 重要度 | Medium |
| 確証 | 静的確認済み |
| 対象 | `models/reliability_model.py::compute_from_summaries` |
| 問題 | 共通metric列だけを計算し、片側だけのmetric一覧をresultへ保存しない |
| 影響 | custom metrics設定差に気づきにくい |
| 修正 | `metrics_only_a`, `metrics_only_b` を結果とUI警告へ追加する |
| テスト | `test_summary_reliability_reports_unmatched_metrics` |

## BUG-021: Reliability不一致matchingが密なeventで非最適になる可能性

| 項目 | 内容 |
| --- | --- |
| 重要度 | Medium |
| 確証 | 仮説 |
| 対象 | `models/reliability_model.py::_candidate_pairs_for_behavior`, `build_disagreement_review` |
| 問題 | 全候補をscore後、greedyに採用する。密な反復eventではglobal optimumと異なる可能性 |
| 修正 | dense fixtureを追加し、必要なら最適割当または明示的matching modeを導入する |
| テスト | `test_dense_repeated_events_matching_policy` |

## BUG-022: focus loss時にkey releaseを取りこぼす可能性

| 項目 | 内容 |
| --- | --- |
| 重要度 | Medium |
| 確証 | 仮説 |
| 対象 | `views/main_window.py` のkey event経路、Annotation lifecycle |
| 問題 | keyを押したまま別windowへ移るとreleaseがアプリへ戻らない可能性 |
| 修正 | `ApplicationDeactivate` / focus loss時のactive event policyを導入する |
| テスト | `test_application_deactivate_recovers_active_events` |

### 推奨policy

- realtime recording中: focus loss時点のplayheadでactive eventを終了し、警告を表示。
- FBF mode: active eventを維持するか破棄するかを確認可能にする。
- 常にactive event rescue panelから確認できるようにする。

## BUG-023: summary-only分析でtotal-time metricの意味が変わる

| 項目 | 内容 |
| --- | --- |
| 重要度 | Medium |
| 確証 | 静的確認済み |
| 対象 | `models/analysis_model.py::_analyze_file_with_summary` |
| 問題 | raw eventありでは重複区間をunion計算するが、summary-onlyでは各behavior durationを単純加算する |
| 影響 | 同じ名前のmetricでも入力形式により値が変わる |
| 修正 | summary-onlyではoverlap-aware metricをunavailableまたはapproximateと表示する |
| テスト | `test_summary_only_total_time_is_marked_approximate` |

## 7. Low: 仕様整理または追加確認が必要な問題

## BUG-024: integer timestampの単位が曖昧

| 項目 | 内容 |
| --- | --- |
| 重要度 | Low |
| 確証 | 静的確認済み |
| 対象 | `models/annotation_model.py::_parse_timestamp` |
| 問題 | `12` は12ms、`12.0` は12秒として扱われる |
| 修正 | schema別に単位を固定し、外部CSVでは明示的に選ばせる |
| テスト | `test_timestamp_unit_is_schema_driven` |

## BUG-025: Windows設定pathがLocalとRoamingへ分散する

| 項目 | 内容 |
| --- | --- |
| 重要度 | Low |
| 確証 | 静的確認済み |
| 対象 | `utils/file_manager.py`, `utils/config_path_manager.py`, docs |
| 問題 | settingsはLocal、action maps等はRoaming。ガイドは `%APPDATA%` のみ記載 |
| 修正 | path方針を統一するか、用途と移行方法を明記する |
| テスト | `test_windows_config_path_policy` |

## BUG-026: 一部drop handlerがdrop時に入力を再検証しない

| 項目 | 内容 |
| --- | --- |
| 重要度 | Low |
| 確証 | 静的確認済み |
| 対象 | `views/video_player_view.py::dropEvent`; `views/project_view.py::dropEvent` |
| 問題 | dragEnter時は検査するが、drop時はURLをそのままemitする |
| 修正 | drop時にも `is_video_file()` と存在確認を行う |
| テスト | `test_drop_event_rejects_invalid_video_path` |

## BUG-027: rewind guardの寿命が分かりにくい

| 項目 | 内容 |
| --- | --- |
| 重要度 | Low |
| 確証 | 仮説 |
| 対象 | `controllers/annotation_controller.py::_skip_next_seek_rewind`, `_on_video_loaded`, `handle_seek` |
| 問題 | guardを複数箇所でarmし、loaderのposition signalと明示seek通知が別経路を通る |
| 影響 | 最初の小さなrewindだけ保護処理をskipする可能性 |
| 修正 | seek originをenum化し、loader resetとuser seekを区別する |
| テスト | `test_first_user_rewind_after_load_is_not_swallowed` |

## 8. CSV品質チェック仕様案

CSV関連bugを個別修正するだけでなく、import前のQA checkerを追加します。

### 8.1 検査項目

| 検査 | 扱い |
| --- | --- |
| UTF-8 decode失敗 | error。fallback encoding候補を表示 |
| schema ID未知 | warning。preview後に継続可能 |
| event headerなし | errorまたはsummary-onlyとして明示 |
| 空行 | 許可 |
| 未知column | warning。保持または無視 |
| onset parse失敗 | row warning。skip候補 |
| offset parse失敗 | row warning。repair / skip候補 |
| `offset < onset` | error。自動repairはpreview必須 |
| zero duration | marker以外はwarning |
| 空Offset | incomplete event warning |
| RecordingStartなし | warning |
| RecordingStart複数 | warningまたはerror |
| behavior名重複 | action mapとの照合warning |
| action mapにないbehavior | warning。空keyでimport可能 |
| summaryとraw eventの不一致 | warning |
| test duration外event | warning |

### 8.2 import結果object案

```python
@dataclass
class AnnotationImportResult:
    schema: str | None
    events: list[BehaviorEvent]
    warnings: list[ImportWarning]
    skipped_rows: list[int]
    repaired_rows: list[int]
    encoding: str
```

Modelはparseとcommitを分けます。

```text
parse_csv(path) -> AnnotationImportResult
validate_import(result) -> QA report
replace_events(result.events) -> commit
```

## 9. Project manifest改善仕様案

### 9.1 schema versioning

```json
{
  "schema_version": 2,
  "project_id": "uuid",
  "name": "RI experiment",
  "videos": [
    {
      "id": "uuid",
      "path": "videos/mouse_01.mp4",
      "storage": "copied",
      "annotation_path": "annotations/mouse_01_annotations.csv",
      "annotation_status": "annotated"
    }
  ]
}
```

### 9.2 読込時の処理順

1. JSONをdecodeする。
2. schema versionを確認する。
3. 必須keyと型を検証する。
4. v1ならmemory上でv2へmigrationする。
5. missing fileを一覧化する。
6. userへrepair / relink候補を表示する。
7. user確認後にatomic saveする。

### 9.3 保存時の処理順

1. memory上のmanifestをvalidateする。
2. temporary fileへUTF-8で書く。
3. flushし、可能ならfsyncする。
4. 旧 `project.json` を `.bak` として保持する。
5. `os.replace()` で置換する。
6. 再読込してdecode可能か確認する。

## 10. 修正ロードマップ

## Patch 1: データ欠落防止

**対象release:** 直近のpatch release  
**期間目安:** 2-4日

### 対象

- BUG-001 Waiting / Space開始
- BUG-002 FBF active残留
- BUG-003 終了guard
- BUG-004 transactional CSV import
- BUG-008 Esc救済
- BUG-009 RecordingStart round-trip
- BUG-010 未割当key tracking

### 完了条件

- Annotation lifecycle testが追加される。
- stop、pause、cancel、auto-complete、動画切替、アプリ終了のcleanup契約が揃う。
- 不正CSV importで既存annotationが変化しない。

## Patch 2: 文字コードとCSV整合性

**対象release:** 直近または次のpatch release  
**期間目安:** 2-4日

### 対象

- BUG-005 UTF-8統一
- BUG-015 quoted comma parser
- BUG-016 header正規化
- BUG-017 empty Offset
- BUG-024 timestamp単位
- CSV QA checker

### 完了条件

- 日本語behavior、空白入りpath、quoted comma、v0 / v1 fixtureが通る。
- import前previewでwarningを確認できる。

## Patch 3: Project堅牢化

**対象release:** 次のminor release候補  
**期間目安:** 4-7日

### 対象

- BUG-006 project移動
- BUG-007 manifest保存失敗
- BUG-019 atomic save
- BUG-025 path整理

### 完了条件

- manifest schema v2とmigration testがある。
- projectフォルダ移動後もstatusとannotation mappingが残る。
- write失敗で旧manifestが壊れない。

## Patch 4: Map、Analysis、Reliability QA

**対象release:** 次のminor release候補  
**期間目安:** 3-5日

### 対象

- BUG-011 behavior重複policy
- BUG-012 録画中map編集policy
- BUG-013 metrics slug衝突
- BUG-014 複数RecordingStart
- BUG-020 Reliability missing metrics
- BUG-023 summary-only近似値

### 完了条件

- map、metrics、analysis入力にvalidatorがある。
- UIが近似値と欠損metricを明示する。
- session契約がガイドへ反映される。

## 11. 追加するテスト一覧

### 11.1 Unit test

| テスト | 対象bug | 優先 |
| --- | --- | --- |
| `test_recording_start_remains_zero_duration_after_round_trip` | BUG-009 | P0 |
| `test_unmapped_key_does_not_leave_press_tracking` | BUG-010 | P0 |
| `test_action_map_duplicate_behavior_policy` | BUG-011 | P0 |
| `test_metrics_reject_cross_category_slug_collision` | BUG-013 | P0 |
| `test_summary_parser_accepts_quoted_behavior_with_comma` | BUG-015 | P0 |
| `test_event_parser_normalizes_spaced_bom_header` | BUG-016 | P1 |
| `test_config_instances_do_not_share_nested_defaults` | BUG-018 | P0 |
| `test_timestamp_unit_is_schema_driven` | BUG-024 | P1 |

### 11.2 Controller integration test

| テスト | 対象bug | 優先 |
| --- | --- | --- |
| `test_waiting_space_starts_recording_session` | BUG-001 | P0 |
| `test_first_behavior_key_is_recorded_when_it_starts_session` | BUG-001 | P0 |
| `test_fbf_manual_stop_finalizes_active_event` | BUG-002 | P0 |
| `test_fbf_auto_complete_finalizes_active_event` | BUG-002 | P0 |
| `test_escape_can_abort_stale_active_event_after_stop` | BUG-008 | P0 |
| `test_application_deactivate_recovers_active_events` | BUG-022 | P1 |
| `test_first_user_rewind_after_load_is_not_swallowed` | BUG-027 | P1 |

### 11.3 CSV integration test

| テスト | 対象bug | 優先 |
| --- | --- | --- |
| `test_invalid_import_preserves_existing_annotations` | BUG-004 | P0 |
| `test_annotation_csv_unicode_round_trip` | BUG-005 | P0 |
| `test_csv_v0_v1_compatibility_matrix` | CSV互換 | P0 |
| `test_import_empty_offset_requires_explicit_repair_policy` | BUG-017 | P1 |
| `test_raw_and_summary_consistency_warning` | CSV QA | P1 |

### 11.4 Project test

| テスト | 対象bug | 優先 |
| --- | --- | --- |
| `test_create_project_fails_when_manifest_write_fails` | BUG-007 | P0 |
| `test_project_copied_video_id_survives_project_relocation` | BUG-006 | P0 |
| `test_manifest_v1_to_v2_migration` | BUG-006 | P0 |
| `test_atomic_json_save_preserves_previous_manifest_on_failure` | BUG-019 | P0 |
| `test_project_relink_external_reference` | Project QA | P1 |

### 11.5 Reliability test

| テスト | 対象bug | 優先 |
| --- | --- | --- |
| `test_summary_reliability_reports_unmatched_metrics` | BUG-020 | P1 |
| `test_dense_repeated_events_matching_policy` | BUG-021 | P2 |
| `test_constant_and_missing_columns_report_reason` | Reliability QA | P1 |

## 12. 実機確認マトリクス

| ケース | Windows | macOS | Linux |
| --- | --- | --- | --- |
| 日本語pathの動画load | 必須 | 必須 | 必須 |
| 空白入りproject path | 必須 | 必須 | 必須 |
| OneDrive / cloud sync配下project | 必須 | 任意 | 任意 |
| 外部diskへproject移動 | 必須 | 必須 | 必須 |
| 30fps / 29.97fps / VFR | 必須 | 必須 | 必須 |
| FBF start、stop、cancel | 必須 | 必須 | 必須 |
| Window close、Alt+F4、File Exit | 必須 | 同等操作 | 同等操作 |
| UTF-8 behavior名export / import | 必須 | 必須 | 必須 |
| 壊れたmanifestからbackup復旧 | 必須 | 必須 | 必須 |

## 13. バグ修正PRの分割案

| PR | 内容 | 対象 |
| --- | --- | --- |
| PR-B01 | Annotation lifecycle回帰test | Waiting、FBF、pause、stop、close |
| PR-B02 | Waiting / Spaceと最初のkey欠落修正 | BUG-001 |
| PR-B03 | active event cleanup一元化 | BUG-002、BUG-008、BUG-010、BUG-022 |
| PR-B04 | transactional CSV parserとmarker修正 | BUG-004、BUG-009、BUG-015、BUG-016、BUG-017、BUG-024 |
| PR-B05 | UTF-8 I/O統一 | BUG-005 |
| PR-B06 | 終了guard一元化 | BUG-003 |
| PR-B07 | manifest保存失敗、atomic save | BUG-007、BUG-019 |
| PR-B08 | manifest schema v2とUUID migration | BUG-006 |
| PR-B09 | action mapとmetrics validator | BUG-011、BUG-012、BUG-013 |
| PR-B10 | Analysis / Reliability QA表示 | BUG-014、BUG-020、BUG-023 |

## 14. 今すぐ着手するならこの5つ

1. Annotation lifecycle testをversion管理し、CIで実行する。
2. Waiting / Space開始とFBF active event残留を修正する。
3. 終了guardを一元化し、録画中・未保存annotation・未保存projectを保護する。
4. CSV importをtransactional化し、UTF-8とRecordingStart round-tripを修正する。
5. Project manifest保存失敗を正しく伝播し、atomic saveを導入する。

## 15. 追加調査が必要な点

- 複数RecordingStartを複数sessionとして正式に扱うか、1 CSV = 1 sessionへ制限するか。**【決定済み 2026-06 → §16-1】**
- 同一behaviorへの複数keyをaliasとして認めるか、誤設定として禁止するか。**【決定済み 2026-06 → §16-2】**
- focus loss時にactive eventを自動終了するか、破棄するか、確認dialogを出すか。**【決定済み 2026-06 → §16-3】**
- v0 CSVの実在fixtureを収集し、単位、encoding、column差を一覧化する。**【対応不要 2026-06: v0 スキーマを使用した RABET は未公開・未配布のため、ユーザーが v0 CSV に遭遇することはない】**
- copied video、external link、network path、OneDrive pathのproject移動要件。**【決定済み 2026-06 → §16-5】**
- Reliability不一致reviewでgreedy matchingを仕様として維持するか、最適割当を追加するか。**【決定済み 2026-06 → §16-6】**
- summary-only入力のoverlap-aware metricを非表示にするか、近似値として出すか。**【決定済み 2026-06 → §16-4】**

## 16. 確定した仕様判断（2026-06）

実装着手前にプロダクト判断が必要だった論点のうち、4件を確定した。各決定は
該当 BUG の「修正方針」を上書きする確定仕様であり、関連テストもここに紐付ける。

| # | 論点 | 決定 | 関連 |
| --- | --- | --- | --- |
| 16-1 | 複数 RecordingStart | **許容しない（1 CSV = 1 session）** | BUG-014 |
| 16-2 | 同一名称 behavior への複数 key | **禁止（誤設定として弾く）** | BUG-011 |
| 16-3 | focus loss 時の active event | **realtime: finalize + pause + 警告 / FBF: 維持** | BUG-022 |
| 16-4 | summary-only の overlap-aware metric | **複数-behavior 合算のみ近似値として明示** | BUG-023 |
| 16-5 | project 移動（copied/external/network/OneDrive） | **ID とパスを分離。UUID 主キー + content hash 補助、copied を推奨デフォルト、relink UI、schema v2** | BUG-006、BUG-029 |
| 16-6 | Reliability 不一致 review のマッチング | **greedy 既定維持 + near-neighbor 高速化（結果不変）。最適割当はオプトインモードで追加** | BUG-021 |

### 16-1. 複数 RecordingStart は許容しない（1 CSV = 1 session）

- `start_timed_recording` 冒頭で、既に `RecordingStart` を含むアノテーションがある場合は
  「新しい録画を開始すると現在のアノテーションが置き換わります。先にエクスポートしますか?」
  を確認し、続行時は `clear_events()` してから新セッションを開始する。
- これにより `models/analysis_model.py` の latency 計算にあった「複数 RecordingStart から
  最適なものを選ぶ」分岐（`_calculate_behavior_latency`）と interval 起点選択を**単純化**できる
  （常に唯一の RecordingStart を使う）。
- 既存 CSV に複数 RecordingStart があった場合の解析は「最初の1つを採用 + warning」に統一。
- テスト: `test_second_recording_session_requires_explicit_clear_or_export`、
  `test_single_recording_start_invariant_after_new_session`。

### 16-2. 同一名称 behavior への複数 key 割り当ては禁止

- `ActionMapModel.add_mapping()` / `load_from_json()` で、**既存と重複する behavior 名**を
  検出したら拒否（load 時はエラーにし、最初の1件だけ採用する暗黙挙動を廃止）。
- ActionMapDialog 側でも追加・編集時に重複 behavior 名を弾き、理由を表示する。
- これにより `_find_key_for_behavior()` の「複数 key のうち先頭だけ選ぶ」曖昧さ（BUG-011）が
  原理的に消え、CSV import の key 逆引きが一意になる。
- テスト: `test_action_map_rejects_duplicate_behavior_name`、
  `test_import_key_lookup_is_unambiguous_under_unique_behavior_names`。

### 16-3. focus loss 時の active event（realtime と FBF で分ける）

- **realtime**: アプリ全体の非アクティブ化を検知したら、その時点の playhead で active events を
  **finalize（end_event）**し、**録画を pause**、目立つ警告を表示する。focus loss 中に動画再生で
  duration が際限なく伸びる「データ捏造」を防ぐのが目的。
  - **実装上の必須要件**: トリガーは `QApplication.applicationStateChanged` の
    `Qt.ApplicationInactive` に限定する。`QEvent.WindowDeactivate` やウィジェット間 FocusOut で
    発火させると spinbox クリック等の**ウィンドウ内移動で誤発火**するため使わない。
- **FBF**: active event は press/press 方式で時間により伸びないため**維持**。情報通知のみ。
- 既存の **Esc abort**（`abort_all_active_events`）を「進行中アノテーションの救済導線」として
  常時案内する。finalize 位置はフレーム精度に限界があるので、復帰後に末尾イベントを
  timeline で微調整できることを案内（将来の D&D 編集と接続）。
- discard 案は不採用（realtime では finalize の方がデータを残せて保守的）。
- テスト: `test_application_inactive_finalizes_realtime_active_events_and_pauses`、
  `test_application_inactive_keeps_fbf_active_events`、
  `test_window_internal_focus_change_does_not_finalize`。

### 16-4. summary-only 入力の overlap-aware metric は近似値として明示

- **単一 behavior の duration は summary 値のまま正確**（flat `_active_events` 設計で同一
  behavior の自己重複が起きないため）→ approximate 扱いにしない。
- **複数 behavior を合算する total-time metric（Total Aggression 等）のみ**、summary-only 入力
  （raw event 無し）では overlap を二重計上しうる（`_analyze_file_with_summary` の単純加算）
  → **`(approx)` と明示**する。値は捨てない。
- 実装: 結果に **per-metric `approximate` フラグ**を持たせ、
  - Summary タブで該当セルを脚注/淡色/`~` で区別
  - export CSV では列名サフィックス or metadata 注記で approximate を伝える
  - ログに「summary-only入力のため <metric> は overlap 非考慮の近似値」と warning
  - Reliability 比較にもフラグを伝播し、将来 approx と exact を混在比較しない警告に使える
- **拒否（N/A 化）はしない**: RABET 自身の export は raw event セクションを含むため、
  summary-only になるのは他ツール由来 CSV の edge case。連携を阻害しない。
- テスト: `test_summary_only_multi_behavior_metric_marked_approximate`、
  `test_summary_only_single_behavior_metric_is_exact`、
  `test_raw_event_metric_not_marked_approximate`。

### 16-5. project 移動要件（ID とパスの分離）

現状 `_get_video_id` は `project_path` を結合した絶対パスを SHA-1 する（`models/project_model.py`）
ため、project フォルダ移動や OneDrive のユーザー名差で **ID が変わり annotation 紐付けが切れる**
（BUG-006）。OneDrive 配下は特に実害が出やすい（既定保存先になりがち）。

- **ID とパスを完全分離する**。
  - **主キー = ランダム UUID**（manifest の video entry に保存）。
  - **補助 = content hash**（先頭/末尾 数MB の部分 SHA-1）。scorer 間で「同じ動画か」検証
    （機能提案 D1）と統合でき、relink 候補提示にも使う。
- **copied 動画**: ID 入力に **project-relative パスをそのまま**使い `project_path` と結合しない
  → 移動不変。あわせて **`add_video` の copy_to_project を推奨デフォルト**にする（現状 False で
  絶対パス保存になり portability が低い＝BUG-029）。
- **external / network / OneDrive**: パスは「在り処ヒント」に格下げし、紐付けは UUID で維持。
  解決不能なら **relink UI**（content hash でマッチ候補提示）。
- **schema v2 + v1→v2 migration**、ロード時に **missing file 一覧表示**（§9.2 の処理順と整合）。
- **OneDrive 特有の注意**: Files On-Demand の placeholder は `os.path.exists` が True でも
  `av.open` でストール/ダウンロードを誘発する。存在チェックを「開ける」と誤認しない実装にする。
- テスト: `test_copied_video_id_survives_relocation`、`test_external_video_relink_by_content_hash`、
  `test_manifest_v1_to_v2_migration`、`test_missing_files_listed_on_load`。

### 16-6. Reliability 不一致 review のマッチング（greedy 既定維持 + optimal はオプトイン）

**決定的根拠**: kappa / alpha は **bin-based** で算出され（`compute_from_annotations`）、
event matching とは独立している。disagreement review の matching は「人間のレビュー用
ナビゲーション」であって統計値ではない。**matching 方式を変えても κ/α は不変**で、変わるのは
レビューリストのペアと並びだけ。よって optimal を安全に**オプション追加**できる。

- **今すぐ（安全・結果不変）**: greedy を維持したまま、候補生成を **near-neighbor 化**
  （onset ソート + two-pointer。`_candidate_pairs_for_behavior` の O(N×M) を解消）。dense でも軽くなる。
- **将来（オプトイン）**: `scipy.optimize.linear_sum_assignment` による最適割当モードを追加。
  **scipy は pingouin 経由で既に依存**のため追加依存なし。既定 OFF。
- **再現性**: matching mode を結果と export CSV に必ず記録する。デフォルトを optimal に変えるのは、
  dense fixture で greedy との差分（何ペア変わるか）を定量化してから判断する。
- テスト: `test_near_neighbor_candidate_generation_matches_bruteforce`、
  `test_matching_mode_recorded_in_export`、`test_kappa_alpha_invariant_across_matching_modes`、
  `test_dense_repeated_events_optimal_vs_greedy_diff`。


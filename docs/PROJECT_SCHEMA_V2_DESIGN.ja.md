# Project manifest schema v2 / UUID 設計（BUG-006 / §16-5）

> **ステータス**: **実装済み（PR-S1 / PR-S2 / PR-S3、v1.3.4）**。本書は実装の設計根拠
> として保持する。実装と差異のある箇所は §7 に追記した。
> （元の意図: 本書だけで実装者が着手できるよう、影響範囲・migration 手順・テストを網羅する。）

## 1. 目的

`project.json`（ProjectModel）の動画識別を **移動耐性のある UUID** に切り替え、
プロジェクトフォルダの移動・OneDrive 同期によるユーザー名差・外部ディスクへの
移設で **annotation の紐付けが切れる問題（BUG-006）** を解消する。

## 2. 現状の問題（実装前に必ず理解すること）

### 2.1 video_id が絶対パス hash 依存

`ProjectModel._get_video_id(video_path)`:

```
legacy_id = basename(path) without ext
normalized = _normalize_video_reference(path)   # project_path と結合して絶対化
video_id = f"{legacy_id}__{sha1(normalized)[:12]}"
```

`_normalize_video_reference` は **相対パス（copied video "videos/mouse.mp4"）を
project_path と結合して絶対パス化**してから hash する。よってプロジェクトを移動して
`project_path` が変わると、同じ `videos/mouse.mp4` でも video_id が変わり、
`video_annotation_status` / `video_annotation_files`（key = video_id）が orphan 化する。

### 2.2 migration のタイミング問題（重要な制約）

旧 video_id は「**保存時の** project_path での絶対パス hash」。プロジェクトを移動した
**後**に開くと、旧 video_id を再計算しても（新しい project_path を使うため）保存値と
一致しない。したがって **v1→v2 migration は「移動前＝現在の場所」で1回行う**必要がある。
移動後の初回ロードでの migration は status を復元できない（その場合は not_annotated に
落ちる縮退で許容するが、ドキュメントで明示すること）。

### 2.3 `_normalize_video_reference` の二用途

このメソッドは (a) **ID 入力の正規化** と (b) **2つのパスが同一動画か判定**
（`_resolve_video_reference`, `find_same_name_video_conflict`）の両方で使われる。
v2 では (a) を UUID に置き換えるため、(b) 用の純粋なパス正規化は別関数に分離すること。

## 3. v2 設計

### 3.1 manifest 形状

```json
{
  "schema_version": 2,
  "project_id": "<uuid>",
  "name": "RI experiment",
  "description": "",
  "created_date": "...",
  "modified_date": "...",
  "videos": [
    {
      "id": "<uuid>",
      "path": "videos/mouse_01.mp4",
      "storage": "copied",            // "copied" (project配下) | "external"
      "content_hash": "<sha1>",       // 先頭/末尾 数MB の部分 sha1（任意・relink用）
      "annotation_status": "annotated",
      "annotation_path": "annotations/mouse_01_annotations.csv"
    }
  ],
  "annotations": [...],
  "action_maps": [...],
  "analyses": [...]
}
```

- **id（UUID）が主キー**。path は「現在の在り処ヒント」に格下げ。
- `video_annotation_status` / `video_annotation_files` は **video entry に内包**
  （`annotation_status` / `annotation_path`）するか、UUID をキーにしたマップとして保持。
  内包方式の方が一貫性が高く推奨。
- `content_hash` は relink（後述）とスコアラー間の「同一動画か」検証（機能提案 D1）に使う。
  計算コストを避けるため先頭+末尾 N MB の部分 hash（例 N=8）。

### 3.2 ID とパスの分離

- `get_video_id(path_or_ref)` → entry.id（UUID）を返す。
- copied / external いずれも UUID で紐付くため、移動・移設に強い。
- external のパスが解決できない場合は **relink**（§3.4）。

### 3.3 v1 → v2 migration（現在の場所で1回）

ロード時 `schema_version` が無い/1 のとき:

1. `project_id` を UUID 生成。
2. 各 v1 video（文字列パス）について:
   a. `old_id = _get_video_id_v1(path)`（**旧ロジックを保存**しておく。現在の
      project_path で計算 = 移動前なら保存値と一致）。
   b. `uuid = uuid4()`。
   c. `storage = "copied" if not isabs(path) else "external"`。
   d. `content_hash = compute_partial_hash(resolve(path))`（解決できれば）。
   e. v1 の `video_annotation_status[old_id]` → entry.annotation_status。
      `video_annotation_files[old_id]` → entry.annotation_path。
      （legacy basename キーの縮退も現行 `_migrate_video_annotation_status` 同様に拾う）
3. `schema_version = 2` をセットし、**atomic save**（Phase 3 の `save_json_atomic`、
   `.bak` 付き）で確定。
4. migration 後は旧 `video_annotation_status` / `video_annotation_files` トップレベル
   キーを削除。

### 3.4 relink（パス解決失敗時）

- ロード時、entry.path が解決できない動画を一覧化（`get_missing_videos()`）。
- ユーザーに「場所を指定」UI を提示。指定先の content_hash が entry.content_hash と
  一致すれば自動マッチ候補として提示。
- relink は entry.path を更新するだけ（id は不変なので annotation 紐付けは保たれる）。

## 4. 影響メソッド一覧（ProjectModel、約17）

各メソッドを UUID 主キーに合わせて改修する。表は変更方針。

| メソッド | 変更方針 |
| --- | --- |
| `_get_video_id` | entry.id（UUID）を返す。path→entry 解決を介す |
| `_get_legacy_video_id` | 表示・relink 補助に残すが ID には使わない |
| `_normalize_video_reference` | **パス一致判定専用**に縮退（ID 入力から外す） |
| `_resolve_video_reference` | path/絶対/UUID → entry を解決 |
| `_get_video_by_exact_id` | UUID 一致で entry 検索 |
| `get_video_id` | 公開: ref → UUID |
| `get_video_by_id` | UUID → path（後方互換で legacy basename も許容） |
| `add_video` | UUID 採番 + entry object 追加 + content_hash 計算 |
| `remove_file`(videos) | entry を id で除去 |
| `get_videos` | path リストを返す（UI 後方互換）。内部は entry 走査 |
| `get_video_annotation_status` | entry.annotation_status を参照 |
| `set_video_annotation_status` | entry.annotation_status を更新 |
| `get_annotation_relative_path_for_video` | entry.annotation_path（無ければ採番） |
| `_make_unique_annotation_relative_path` | entry ベースで重複回避 |
| `find_same_name_video_conflict` | **純粋パス正規化**で同名別パス判定 |
| `_migrate_video_annotation_status` | v1→v2 migration に統合・置換 |
| `_update_annotation_status` | entry.annotation_status を更新する形に |

加えて呼び出し側:
- `controllers/project_controller.py`, `controllers/annotation_controller.py`
  （`set_current_video_id`, auto-export パス）は **UUID または stored path** を渡す前提に
  揃える。現行は stored path / legacy id 混在なので、`get_video_id` 経由に統一する。
- `controllers/video_controller.py::_warn_on_project_same_name_conflict` は
  `find_same_name_video_conflict`（純パス正規化版）を使う。

## 5. content hash 仕様

```
def compute_partial_hash(path, head=8*1024*1024, tail=8*1024*1024):
    # sha1(file size + first head bytes + last tail bytes)
    # 大動画でも O(16MB) で安定。1バイト変化で別 hash。
```

- 目的: relink 候補提示 + スコアラー間の同一動画検証（D1）。ID には使わない
  （内容が変わると別物になり migration を壊すため、ID は UUID 固定）。

## 6. テスト計画

- `test_manifest_v1_to_v2_migration`: v1 manifest（文字列 videos + 旧 status）を現在の
  場所でロード → v2（UUID entry）に migrate。status が UUID に移る。
- `test_copied_video_id_survives_relocation`: copied video を v2 化後、project_path を
  変えて再ロード → UUID 不変、status 維持。
- `test_external_video_relink_by_content_hash`: external のパスを壊し、別パスの同一内容
  ファイルを content_hash で relink 候補に。
- `test_missing_files_listed_on_load`: 解決不能 entry が一覧化される。
- `test_v2_save_is_atomic_with_bak`: Phase 3 の atomic save + `.bak` で保存。
- 既存 project テスト（BUG-007 等）が v2 でも通る回帰。

## 7. 段階実装の結果（v1.3.4 で完了）

1. **PR-S1 ✅**: `schema_version` + video entry object 化 + v1→v2 migration（status/files の
   内包化）。内部表現（path リスト + status/files マップ）は温存。load 時に v1 を
   検出すると dirty 扱いにし、保存で v2 へ移行。
2. **PR-S2 ✅**: UUID 主キー化。`_get_video_id` は永続マップ `_video_id_by_path`
   （stored-path → 安定 id）参照に変更し、`add_video` が `_mint_video_id` で id を採番、
   `create/close` でマップをリセット、`_load_into_internal` が v2(entry.id)/v1(legacy hash)
   から再構築。**実装差異**: `_normalize_video_reference` の完全な二用途分離は行わず、
   `_stored_path_for`（id を介さずパス解決）で id↔path の再帰を回避する形にした
   （マップ方式で移動耐性が満たせたため）。
3. **PR-S3 ✅**: content hash + relink。`utils/content_hash.compute_partial_hash`
   （size + 先頭/末尾 8MB の sha1）、`ProjectModel.get_missing_videos` /
   `relink_video` / `content_hash_matches`、load 後に `ProjectController` が再リンクを
   誘導（content hash 不一致は強制確認）。content_hash は v2 entry に内包・round-trip。

各 PR で `tests/` の project 回帰を緑に維持（最終 **169 テスト緑・ruff clean**）。
移動耐性の核は PR-S2、external 動画の救済が PR-S3。

## 8. 既存挙動で変えてはいけないもの

- `get_videos()` / `get_annotations()` 等が返す **相対パス文字列の形式**（UI 表示・
  既存 CSV 連携が依存）。
- annotation CSV のファイル名規則（`<base>_annotations.csv`）。
- atomic save / `.bak`（Phase 3 で導入済み）を migration・保存に必ず使う。

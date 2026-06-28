# RABET CSV ファイル形式仕様

このページでは、RABET が読み書きする CSV ファイルの形式を説明します。
通常の利用で関係する CSV は次の 3 種類です。

1. **アノテーション CSV**  
   動画 1 本、または 1 回の記録セッションにつき 1 ファイル作成されます。
   Annotation ビューの `Export Annotations` やプロジェクト内の自動保存で
   出力され、Annotation ビューの `Import Annotations` と Analysis ビューで
   読み込まれます。

2. **Summary CSV**  
   Analysis ビューから出力される、1 行 = 1 個体 / 1 ファイルの集計表です。
   インターバル解析が無効な場合も有効な場合も出力されます。

3. **Interval Summary CSV**  
   インターバル解析が有効な場合に出力される、1 行 = 1 個体 × 1 時間区間の
   集計表です。

すべて UTF-8、カンマ区切り、改行は Python 標準の `csv` モジュールで書き出される
`\n` です。

---

## 1. アノテーション CSV

アノテーション CSV は、空行で区切られた 3 つのセクションから成ります。

### 1.1 全体レイアウト

```csv
Metadata
RABET Version,<X.Y.Z>
Test Duration (seconds),<float>

Event,Onset,Offset
RecordingStart,<float>,<float>
<behavior>,<float>,<float>
...

Behavior,Duration,Frequency
<behavior>,<float>,<int>
...
```

### 1.2 Metadata セクション

| 行 | 型 | 説明 |
| --- | --- | --- |
| `Metadata` | 文字列 | セクション開始を示す固定行です。常に存在します。 |
| `RABET Version,<X.Y.Z>` | 文字列 | このファイルを書き出した RABET のバージョンです。 |
| `Test Duration (seconds),<float>` | 数値 | タイムドセッションの長さです。タイムド記録を行っていない場合は `0` になります。 |

### 1.3 Event セクション

| 列 | 型 | 説明 |
| --- | --- | --- |
| `Event` | 文字列 | アクションマップで設定した行動名です。記録開始マーカーは `RecordingStart` として出力されます。 |
| `Onset` | 秒 | 動画開始からの onset 時刻です。小数点以下 4 桁で出力されます。 |
| `Offset` | 秒 | offset 時刻です。通常は数値ですが、まれに未終了イベントでは空欄になることがあります。 |

イベントは確定された順に並びます。`RecordingStart` は合成マーカーで、
`Onset` と `Offset` が同じ値になります。RABET 内部ではミリ秒で保持し、CSV
出力時に秒へ変換します。

RABET 1.4.0 以降、行動は **State** と **Point** のどちらかに設定できます。

| 種類 | CSV 上の表現 | 解釈 |
| --- | --- | --- |
| State | 通常は `Offset > Onset` | 持続時間を持つ行動です。キーを押して開始し、離して終了します。 |
| Point | `Offset == Onset` | 一瞬の発生を表す行動です。キーを押した瞬間に 1 回記録されます。 |

列構成は従来と同じなので、古い下流パーサーでも基本的には読み込めます。

### 1.4 Summary セクション

| 列 | 型 | 説明 |
| --- | --- | --- |
| `Behavior` | 文字列 | 行動名です。イベントが 0 回でも、設定済み行動は表示されることがあります。 |
| `Duration` | 秒 | 全イベントの `Offset - Onset` の合計です。 |
| `Frequency` | 整数 | 行動が記録された回数です。onset を基準に数えます。 |

`RecordingStart` は Summary セクションには含まれません。Point 行動は
`Frequency` にはカウントされますが、`Duration` への寄与は 0 秒です。

### 1.5 例

```csv
Metadata
RABET Version,1.4.0
Test Duration (seconds),60

Event,Onset,Offset
RecordingStart,0.0000,0.0000
Attack bites,1.0000,1.5000
Head dip,1.8000,1.8000
Sideways threats,2.0000,2.2000
Attack bites,3.0000,3.4000

Behavior,Duration,Frequency
Attack bites,0.90,2
Head dip,0.00,1
Sideways threats,0.20,1
Tail rattles,0.00,0
Chasing,0.00,0
Social contact,0.00,0
Self-grooming,0.00,0
Locomotion,0.00,0
Rearing,0.00,0
```

---

## 2. Summary CSV

Summary CSV は Analysis ビューのセッション全体集計です。インターバル解析が
有効な場合も、Interval Summary CSV と一緒に出力されます。

### 2.1 レイアウト

概念的には次のような表です。

```csv
,<Duration band: behaviors...>,<spacer>,<Frequency band: behaviors...>,<spacer>,<custom metric names...>
animal_id,<behavior cols>,<empty>,<behavior cols>,<empty>,<custom metric values>
...
```

実際のヘッダーには、Duration、Frequency、カスタムメトリクスが読みやすいように
帯状に並びます。

### 2.2 列の意味

- **Duration band** と **Frequency band** には、同じ順序の行動名が並びます。
- Duration は秒、Frequency は回数です。
- Point 行動は通常、Duration ではなく Frequency を主に見ます。
- カスタムメトリクスは Metrics ダイアログで設定した順に末尾へ追加されます。
- カスタムメトリクスには **latency** と **total-time** の 2 種類があります。

### 2.3 カスタムメトリクス

**Latency メトリクス** は、記録開始から対象行動の最初の発生までの秒数です。
その行動が発生しなかった場合は空欄になります。

**Total-time メトリクス** は、複数行動の合計時間です。元のイベント onset /
offset が利用できる場合、RABET は重複区間をまとめてから合計します。そのため、
同時に起きた行動を二重に数えません。

### 2.4 `animal_id` の決まり方

`animal_id` は、読み込んだアノテーション CSV のファイル名から拡張子を除いた
ものです。末尾が `_annotations` の場合は、その部分を除きます。

例:

```text
mouse_05_annotations.csv -> mouse_05
RI_010.csv               -> RI_010
```

---

## 3. Interval Summary CSV

Interval Summary CSV は、Analysis ビューで **Enable interval analysis** が
有効な場合に出力されます。先頭ヘッダーには、インターバル幅が秒で記録されます。

### 3.1 レイアウト

```csv
Interval analysis (<N>-second intervals)
<...,Duration band,<spacer>,Frequency,...>
animal_id,Interval,Time (sec),<spacer>,<behaviors duration>,<spacer>,<behaviors freq>,<spacer>,<custom metrics>
...rows: one per (animal, interval) pair...
```

### 3.2 重要な意味づけ

- **Duration** は、その行動がインターバルと重なっている秒数です。
- **Frequency** は、onset がそのインターバル内にあるイベント数です。
- **`Time (sec)`** は `0.0-60.0` のような文字列です。記録開始からの時間区間を
  表します。
- イベントがない空のインターバルも、値 0 の行として出力されます。
- 個体の間には空行が入ります。

### 3.3 解釈例

60 秒インターバルの境界をまたぐ State イベントがある場合、Duration は前後の
インターバルへ分配されます。一方、Frequency は onset が含まれるインターバルに
1 回だけ入ります。

Point イベントは Duration が 0 なので、インターバル解析でも Frequency として
解釈してください。

### 3.4 ヘッダー例

```csv
Interval analysis (60-second intervals)
,,,,Duration,,,,,,,,Frequency,,,,,,,,
animal_id,Interval,Time (sec),,Attack bites,Sideways threats,...,,Attack bites,Sideways threats,...,,Total Aggression
```

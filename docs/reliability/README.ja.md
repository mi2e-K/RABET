# 信頼性評価リファレンス

RABET 1.3.2 で **Reliability** タブが追加され、評価者間信頼性と評価者内信頼性を
アプリ内で計算できるようになりました。計算には Python パッケージ
[`pingouin`](https://pingouin-stats.org/) を使用しています。

このフォルダには、Summary モードの結果を R で再現するための独立した参照実装が
含まれています。目的は次の 2 つです。

1. **別言語での再現性確認**  
   R で統計解析パイプラインを組んでいる研究者が、RABET アプリ内の値を
   R 側でも再計算できるようにするためです。R 版では主に
   [`psych`](https://cran.r-project.org/package=psych) を使います。

2. **査読・報告時の透明性**  
   RABET で得た信頼性指標を論文やレポートに載せる場合、アプリ内の
   pingouin 実装だけでなく、独立した R スクリプトでも再現できることを示すと、
   計算が特定実装に依存していないことを説明しやすくなります。

---

## 含まれるファイル

| ファイル | 目的 |
| --- | --- |
| `compute_agreement.R` | 2 つの `summary_table.csv` を読み込み、`animal_id` で行を対応付け、メトリクスごとに **ICC(2,1)**、Pearson r、平均絶対差を計算する単独実行可能な R スクリプトです。RABET の **Summary モード** と同じ計算を再現します。 |

Detailed モード、つまり時間ビン化した Cohen's kappa / Krippendorff's alpha の
R 参照実装は、今後のリリースで追加予定です。現時点では、RABET アプリ内の実装が
Detailed モードの正式な計算です。

---

## クイックスタート

```bash
# 依存パッケージを一度だけインストールします
Rscript -e 'install.packages(c("psych"))'

# Summary モードの一致度表を R で再計算します
Rscript docs/reliability/compute_agreement.R \
        path/to/scorer_A_summary.csv \
        path/to/scorer_B_summary.csv \
        reliability_summary_R.csv
```

スクリプトはメトリクスごとの一致度表を標準出力に表示し、CSV にも保存します。
3 つ目の引数を省略した場合、現在の作業ディレクトリに
`reliability_summary_R.csv` が作成されます。

---

## 定義

### ICC(2,1)

ここでの ICC(2,1) は、Pingouin の `ICC2` 出力に対応します。R の
`psych::ICC` では `ICC2` 行に相当する、単一評価者・absolute agreement の ICC
です。

ICC の表記は、文献やソフトウェアによって対応関係が分かりにくい場合があります。
Shrout and Fleiss / Pingouin の慣例では、`ICC2` は評価者を random effect として
扱い、`ICC3` は fixed effect として扱います。一方、McGraw and Wong 系の表記では、
同じ数式が two-way random または two-way mixed の absolute agreement と説明される
ことがあります。

そのため RABET では、ソフトウェア上のラベルである `ICC2` と、一般的な形式名である
ICC(2,1) の両方を明記します。評価者を random と見るか fixed と見るかは、研究デザイン
に沿って解釈してください。

### Pearson r

対応付けられた個体間で、同じメトリクスの値を用いて計算する通常の Pearson の積率
相関係数です。

### 平均絶対差

両方の summary ファイルに存在する個体について、`mean(abs(A - B))` を計算した値です。
単位は元のメトリクスの単位に依存します。Duration や latency の場合は秒です。

---

## RABET アプリ内出力との期待される差

R 参照実装と RABET アプリ内出力は、ICC と Pearson r ではおおむね `1e-6` 程度以内、
平均絶対差では完全一致することを想定しています。

それより大きくずれる場合、よくある原因は次のとおりです。

- 片方のファイルにしか存在しない `animal_id` がある  
  RABET の `unmatched_a` / `unmatched_b` 表示と、R スクリプトの標準出力を確認して
  ください。
- すべて 0 などの退化的な列がある  
  線形混合モデルや分散成分の扱いで、ソフトウェア間にごく小さな数値差が出ることが
  あります。

明らかに大きな不一致がある場合は、2 つの CSV を添えて
<https://github.com/mi2e-K/RABET/issues> に報告してください。

---

## RABET で信頼性指標を報告するとき

論文やレポートでは、少なくとも次を記録しておくことを勧めます。

- 使用した RABET のバージョン
- Summary モードか Detailed モードか
- Summary モードの場合、解析した `summary_table.csv` の作成条件
- Detailed モードの場合、bin width と対象行動
- 比較した個体数、または動画数
- 欠損・未対応の `animal_id` があったかどうか

これらを明記しておくと、後から同じ CSV で値を再計算しやすくなります。

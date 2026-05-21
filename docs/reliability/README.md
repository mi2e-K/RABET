# Reliability reference scripts

RABET 1.3.2 introduced the **Reliability tab**, which computes inter-rater
and intra-rater agreement entirely inside the application using the
[`pingouin`](https://pingouin-stats.org/) Python package. This folder
contains an independent R implementation that exists for two reasons:

1. **Cross-language reproducibility.** Researchers who run their statistics
   pipeline in R can verify the in-app numbers by re-computing the same
   agreement matrix with the canonical R packages
   ([`psych`](https://cran.r-project.org/package=psych) and optionally
   [`irr`](https://cran.r-project.org/package=irr)).

2. **Reviewer transparency.** When publishing reliability numbers from
   RABET, citing both the in-app pingouin computation and an independent R
   reference reassures reviewers that the agreement matrix is implementation-
   neutral.

## What is provided

| File | Purpose |
| --- | --- |
| `compute_agreement.R` | Stand-alone R script. Loads two `summary_table.csv` files, matches rows by `animal_id`, computes per-metric **ICC(2,1)**, Pearson r, mean absolute difference, and writes a results CSV. Mirrors RABET's **Summary mode**. |

A Detailed-mode (time-window Cohen's kappa / Krippendorff's alpha) R
reference will follow in a later release. The pingouin implementation
inside RABET is the authoritative computation in the meantime.

## Quick start

```bash
# Install dependencies (once):
Rscript -e 'install.packages(c("psych"))'

# Reproduce the Summary-mode agreement matrix:
Rscript docs/reliability/compute_agreement.R \
        path/to/scorer_A_summary.csv \
        path/to/scorer_B_summary.csv \
        reliability_summary_R.csv
```

The script prints the per-metric agreement table and writes it to the
output CSV (defaults to `reliability_summary_R.csv` next to the current
working directory if no third argument is given).

## Definitions

ICC(2,1) here is **pingouin's `ICC2`** = `psych::ICC` row labelled
**`ICC2`** = "two-way mixed, absolute agreement, single rater".

Pearson r is the standard product-moment correlation across the matched
animals.

Mean absolute difference is `mean(abs(A - B))` over animals present in
both summary files.

## Expected differences from RABET's in-app output

The two implementations should agree to within ~1e-6 for ICC and r, and
exactly for mean absolute difference. Larger discrepancies usually mean:

- One side dropped an animal that the other kept (check `unmatched_a` /
  `unmatched_b` in RABET's status panel and the R script's stdout).
- Numerical precision differences in how the underlying linear-mixed
  model solver handles degenerate inputs (e.g. all-zero columns).

If the values diverge by more than that, please open an issue at
https://github.com/mi2e-K/RABET/issues with both CSVs attached.

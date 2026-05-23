# compute_agreement.R - R reference implementation for RABET Reliability tab
#
# RABET v1.3.2 computes inter-rater agreement in Python via the pingouin
# library. This R script reproduces the same numbers using the canonical
# `psych` and `irr` packages, so studies that prefer R for their stats
# pipeline can verify (or replace) the in-app numbers.
#
# Usage:
#
#   Rscript compute_agreement.R <scorer_A_summary.csv> <scorer_B_summary.csv>
#
# The script:
#   1. Parses both summary_table.csv files (two-banded layout).
#   2. Matches rows on `animal_id`.
#   3. For each common metric column, reports
#        - ICC(2,1)  (psych::ICC, two-way mixed, absolute agreement, single rater)
#        - Pearson r
#        - Mean absolute difference
#   4. Writes one combined results CSV next to the inputs.
#
# Dependencies:
#   install.packages(c("psych", "irr"))
#
# These numbers should match RABET's Reliability tab to within rounding.
# If they diverge, please open an issue at
# https://github.com/mi2e-K/RABET/issues.

# ----------------------------------------------------------------------- #
# Dependencies
# ----------------------------------------------------------------------- #
suppressPackageStartupMessages({
  if (!requireNamespace("psych", quietly = TRUE)) {
    stop("Package 'psych' is required. Install with install.packages('psych').")
  }
  library(psych)
})

# ----------------------------------------------------------------------- #
# Argument parsing
# ----------------------------------------------------------------------- #
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop(
    "Usage: Rscript compute_agreement.R <scorer_A_summary.csv> <scorer_B_summary.csv> [output.csv]"
  )
}
path_a <- args[1]
path_b <- args[2]
output_path <- if (length(args) >= 3) args[3] else "reliability_summary_R.csv"

stopifnot(file.exists(path_a), file.exists(path_b))

# ----------------------------------------------------------------------- #
# Helpers for the two-banded summary_table.csv layout
# ----------------------------------------------------------------------- #

# Parse one summary_table.csv into a data.frame keyed by animal_id, with
# column names like "Attack bites (Duration)", "Attack bites (Frequency)",
# "Attack Latency", etc.
parse_summary <- function(path) {
  raw <- read.csv(path, header = FALSE, stringsAsFactors = FALSE,
                  check.names = FALSE, colClasses = "character",
                  na.strings = "")
  if (nrow(raw) < 3L) {
    stop(sprintf("File '%s' does not have enough rows.", path))
  }

  band_row <- trimws(as.character(raw[1, ]))
  header_row <- trimws(as.character(raw[2, ]))
  data <- raw[-c(1L, 2L), , drop = FALSE]
  rownames(data) <- NULL

  metric_labels <- character(length(band_row))
  metric_labels[1] <- "animal_id"
  last_band <- ""
  inside_band <- FALSE

  for (i in seq_along(band_row)[-1]) {
    band_cell <- band_row[i]
    header_cell <- header_row[i]
    band_cell <- if (is.na(band_cell)) "" else band_cell
    header_cell <- if (is.na(header_cell)) "" else header_cell

    if (band_cell %in% c("Duration", "Frequency")) {
      last_band <- band_cell
      inside_band <- TRUE
      metric_labels[i] <- if (nzchar(header_cell)) {
        sprintf("%s (%s)", header_cell, last_band)
      } else {
        sprintf("__spacer_%d", i)
      }
    } else if (!nzchar(header_cell)) {
      inside_band <- FALSE
      last_band <- ""
      metric_labels[i] <- sprintf("__spacer_%d", i)
    } else if (inside_band) {
      metric_labels[i] <- sprintf("%s (%s)", header_cell, last_band)
    } else {
      metric_labels[i] <- header_cell
    }
  }

  colnames(data) <- metric_labels
  keep <- !grepl("^__spacer_", metric_labels)
  data <- data[, keep, drop = FALSE]

  data$animal_id <- trimws(data$animal_id)
  data <- data[nzchar(data$animal_id), , drop = FALSE]
  data <- data[!(tolower(data$animal_id) %in% c("mean", "sem")), , drop = FALSE]

  for (col in setdiff(colnames(data), "animal_id")) {
    data[[col]] <- suppressWarnings(as.numeric(data[[col]]))
  }
  data
}

# ICC(2,1) reproducing pingouin's "ICC2": two-way mixed, absolute
# agreement, single rater.
icc_two_way_single <- function(values_a, values_b) {
  ok <- is.finite(values_a) & is.finite(values_b)
  va <- values_a[ok]
  vb <- values_b[ok]
  n <- length(va)
  if (n < 2L) return(NA_real_)
  # Identical sequences -> perfect agreement; avoid the divide-by-zero
  # in psych::ICC.
  if (isTRUE(all.equal(va, vb))) return(1.0)
  # Both sequences flat but unequal -> ICC undefined.
  if (length(unique(va)) == 1L && length(unique(vb)) == 1L) return(NA_real_)

  mat <- cbind(va, vb)
  fit <- tryCatch(
    suppressWarnings(psych::ICC(mat, missing = TRUE, lmer = FALSE)),
    error = function(e) NULL
  )
  if (is.null(fit)) return(NA_real_)
  row <- fit$results[fit$results$type == "ICC2", , drop = FALSE]
  if (nrow(row) == 0L) return(NA_real_)
  as.numeric(row$ICC[1])
}

pearson_r <- function(va, vb) {
  ok <- is.finite(va) & is.finite(vb)
  va <- va[ok]; vb <- vb[ok]
  if (length(va) < 2L) return(NA_real_)
  if (sd(va) == 0 || sd(vb) == 0) {
    return(if (isTRUE(all.equal(va, vb))) 1.0 else NA_real_)
  }
  as.numeric(cor(va, vb))
}

mean_abs_diff <- function(va, vb) {
  ok <- is.finite(va) & is.finite(vb)
  if (!any(ok)) return(NA_real_)
  mean(abs(va[ok] - vb[ok]))
}

# ----------------------------------------------------------------------- #
# Main
# ----------------------------------------------------------------------- #
df_a <- parse_summary(path_a)
df_b <- parse_summary(path_b)

matched <- intersect(df_a$animal_id, df_b$animal_id)
if (length(matched) == 0L) {
  stop("No animal_id values are shared between the two summary tables.")
}

df_a_m <- df_a[match(matched, df_a$animal_id), , drop = FALSE]
df_b_m <- df_b[match(matched, df_b$animal_id), , drop = FALSE]
common_metrics <- intersect(colnames(df_a_m), colnames(df_b_m))
common_metrics <- setdiff(common_metrics, "animal_id")

results <- data.frame(
  Metric        = character(),
  n_pairs       = integer(),
  ICC_2_1       = numeric(),
  Pearson_r     = numeric(),
  Mean_abs_diff = numeric(),
  Mean_A        = numeric(),
  Mean_B        = numeric(),
  stringsAsFactors = FALSE
)

for (metric in common_metrics) {
  va <- df_a_m[[metric]]
  vb <- df_b_m[[metric]]
  ok <- is.finite(va) & is.finite(vb)
  n <- sum(ok)
  results <- rbind(results, data.frame(
    Metric        = metric,
    n_pairs       = n,
    ICC_2_1       = icc_two_way_single(va, vb),
    Pearson_r     = pearson_r(va, vb),
    Mean_abs_diff = mean_abs_diff(va, vb),
    Mean_A        = if (n > 0) mean(va[ok]) else NA_real_,
    Mean_B        = if (n > 0) mean(vb[ok]) else NA_real_,
    stringsAsFactors = FALSE
  ))
}

cat(sprintf("Matched animals: %s\n", paste(matched, collapse = ", ")))
unmatched_a <- setdiff(df_a$animal_id, df_b$animal_id)
unmatched_b <- setdiff(df_b$animal_id, df_a$animal_id)
if (length(unmatched_a)) {
  cat(sprintf("Only in scorer A: %s\n", paste(unmatched_a, collapse = ", ")))
}
if (length(unmatched_b)) {
  cat(sprintf("Only in scorer B: %s\n", paste(unmatched_b, collapse = ", ")))
}

print(results, row.names = FALSE)
write.csv(results, output_path, row.names = FALSE)
cat(sprintf("\nResults written to %s\n", output_path))

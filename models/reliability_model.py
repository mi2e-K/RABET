# models/reliability_model.py - Inter-rater / intra-rater reliability calculations
"""
ReliabilityModel - compute agreement statistics between two RABET outputs.

Two operating modes are supported:

* **Summary mode** (preferred for routine use) accepts two
  ``summary_table.csv`` files produced by the Analysis view, matches
  rows by ``animal_id``, and computes ICC(2,1), Pearson correlation,
  and mean absolute difference for each behaviour x metric cell.

* **Detailed mode** accepts two annotation CSV files (assumed to be
  scored on the same video) and computes time-window-binned Cohen's
  kappa, Krippendorff's alpha, and a raster-overlay dataset for the
  Pairwise Raster sub-view.

The computation backend is ``pingouin`` for ICC / kappa / alpha, with
``numpy`` and ``pandas`` for the data shuffling.

The model emits Qt signals so the controller / view can stay decoupled
from the heavy work; the computation methods themselves are
synchronous, but the controller may dispatch them to a worker thread if
performance becomes an issue. For the dataset sizes typical of an
RI study (<50 animals, <500 events per video) the synchronous path is
fast enough.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from PySide6.QtCore import QObject, Signal

from utils.annotation_csv_parser import load_event_dataframe

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------- #
# Result containers
# -------------------------------------------------------------------- #


@dataclass
class SummaryAgreementRow:
    """One row of the Summary-mode results table."""
    metric: str          # e.g. "Attack bites (Frequency)"
    n_pairs: int          # number of animals contributing
    icc: Optional[float]  # ICC(2,1), None if not computable
    pearson_r: Optional[float]
    mean_abs_diff: Optional[float]
    mean_a: Optional[float]
    mean_b: Optional[float]


@dataclass
class SummaryAgreementResult:
    """Full result of a Summary-mode computation."""
    rows: List[SummaryAgreementRow] = field(default_factory=list)
    matched_animals: List[str] = field(default_factory=list)
    unmatched_a: List[str] = field(default_factory=list)
    unmatched_b: List[str] = field(default_factory=list)
    # Per-metric scatter data: metric -> (animals, values_a, values_b)
    scatter_data: Dict[str, Tuple[List[str], List[float], List[float]]] = (
        field(default_factory=dict)
    )


@dataclass
class DetailedAgreementRow:
    """One row of the Detailed-mode results table."""
    behavior: str
    n_bins: int            # total time-window bins compared
    n_active_a: int        # bins where scorer A marked the behaviour
    n_active_b: int        # bins where scorer B marked the behaviour
    cohen_kappa: Optional[float]
    krippendorff_alpha: Optional[float]
    raw_agreement: float    # simple percentage agreement


@dataclass
class DetailedAgreementResult:
    """Full result of a Detailed-mode computation."""
    rows: List[DetailedAgreementRow] = field(default_factory=list)
    behaviors: List[str] = field(default_factory=list)
    bin_seconds: float = 1.0
    test_duration_seconds: float = 0.0
    events_a: List[Tuple[str, float, float]] = field(default_factory=list)
    events_b: List[Tuple[str, float, float]] = field(default_factory=list)
    label_a: str = "Scorer A"
    label_b: str = "Scorer B"


# -------------------------------------------------------------------- #
# Helpers for the somewhat unusual summary_table.csv layout
# -------------------------------------------------------------------- #


def _parse_summary_table(path: str) -> pd.DataFrame:
    """Parse RABET's two-banded summary_table.csv into a tidy long DataFrame.

    The on-disk layout is:

        ,Duration,,,,,,,,,,Frequency,,,,,,,,,,,,custom_1,custom_2,...
        animal_id,beh1,beh2,...,behN,,beh1,beh2,...,behN,,custom_1,custom_2,...
        animal1,...,...

    where the two empty cells separate the Duration band, the Frequency
    band, and the custom-metrics tail. We collapse this into a long-form
    DataFrame with columns ``animal_id``, ``metric``, ``value``.

    The returned DataFrame is suitable for ``pivot``-based comparison
    against another scorer's parsed summary.
    """
    # Read header row (row 0 is the band labels, row 1 is the column
    # headers, data starts at row 2).
    raw = pd.read_csv(path, header=None, dtype=str, keep_default_na=False)
    if raw.shape[0] < 3:
        raise ValueError(
            f"summary_table.csv at {path} does not have enough rows."
        )

    band_row = raw.iloc[0].tolist()
    header_row = raw.iloc[1].tolist()
    data = raw.iloc[2:].reset_index(drop=True)

    # Walk band-row and header-row in tandem and decide each column's label
    # in one pass. The key observation is that the two main bands
    # (Duration, Frequency) are separated from each other and from the
    # custom-metric tail by a *spacer column* (empty band cell + empty
    # header cell). A spacer therefore ends the current band; columns past
    # the last spacer that have a non-empty header are custom metrics with
    # no band suffix.
    metric_labels: List[str] = []
    last_band = ""
    inside_band = False

    for col_idx, (band_cell, header_cell) in enumerate(zip(band_row, header_row, strict=False)):
        band_cell = (band_cell or "").strip()
        header_cell = (header_cell or "").strip()

        if col_idx == 0:
            metric_labels.append("animal_id")
            continue

        if band_cell in ("Duration", "Frequency"):
            # A new band starts here.
            last_band = band_cell
            inside_band = True
            if header_cell:
                metric_labels.append(f"{header_cell} ({last_band})")
            else:
                # Band marker without a column header - treat as spacer.
                metric_labels.append(f"__spacer_{col_idx}")
            continue

        if not header_cell:
            # Empty header => spacer column. Drop the band.
            inside_band = False
            last_band = ""
            metric_labels.append(f"__spacer_{col_idx}")
            continue

        if inside_band:
            metric_labels.append(f"{header_cell} ({last_band})")
        else:
            # Custom-metric column: the header itself is the metric name.
            metric_labels.append(header_cell)

    data.columns = metric_labels
    data = data.loc[:, ~data.columns.str.startswith("__spacer_")]

    # Coerce numeric columns. animal_id stays as string.
    for col in data.columns:
        if col == "animal_id":
            data[col] = data[col].astype(str).str.strip()
            continue
        data[col] = pd.to_numeric(data[col], errors="coerce")

    # Drop fully empty rows (e.g. a trailing blank line).
    data = data[data["animal_id"].astype(bool)].reset_index(drop=True)

    # Warn about and de-duplicate repeated animal_id values. Pandas would
    # silently keep the last occurrence after set_index later in the
    # pipeline; the explicit pre-pass makes that behaviour visible.
    duplicates = data.loc[data["animal_id"].duplicated(keep=False), "animal_id"]
    if not duplicates.empty:
        unique_ids = sorted(set(duplicates))
        logger.warning(
            "Duplicate animal_id values in %s: %s. Keeping the last row for "
            "each duplicated id.", path, unique_ids,
        )
        data = data.drop_duplicates(
            subset=["animal_id"], keep="last"
        ).reset_index(drop=True)

    return data


# -------------------------------------------------------------------- #
# Statistical helpers (thin wrappers around pingouin)
# -------------------------------------------------------------------- #


def _icc_two_way_single(values_a: np.ndarray, values_b: np.ndarray) -> Optional[float]:
    """ICC(2,1), two-way mixed, absolute agreement, single rater.

    Pingouin's formula divides msbetween / mserror, which becomes 0/0
    when the two scorers happen to agree exactly (mserror = 0). We
    short-circuit those degenerate cases:

    * Perfect agreement (values_a == values_b) -> ICC = 1.0
    * Both scorers gave a constant (zero variance) but disagree -> None
    * Fewer than 2 pairs -> None
    """
    if len(values_a) < 2 or len(values_b) < 2:
        return None

    # Perfect agreement short-circuit (any element count).
    if np.allclose(values_a, values_b):
        return 1.0

    # Zero-variance disagreement: both raters internally constant but
    # different from each other.
    if (np.allclose(values_a, values_a[0])
            and np.allclose(values_b, values_b[0])):
        return None

    try:
        import pingouin as pg
    except Exception as exc:
        # Capture ANY exception (not just ImportError) so a bundled
        # build with a missing transitive dependency tells us exactly
        # what failed instead of pretending pingouin is uninstalled.
        logger.error("pingouin import failed: %s", exc, exc_info=True)
        return None

    n = len(values_a)
    df = pd.DataFrame({
        "target": list(range(n)) * 2,
        "rater": ["A"] * n + ["B"] * n,
        "rating": np.concatenate([values_a, values_b]),
    })
    try:
        icc_df = pg.intraclass_corr(
            data=df, targets="target", raters="rater", ratings="rating"
        )
        # ICC2 = two-way mixed, absolute agreement, single rater
        row = icc_df.loc[icc_df["Type"] == "ICC2"]
        if row.empty:
            return None
        value = float(row["ICC"].iloc[0])
        if not np.isfinite(value):
            return None
        return value
    except Exception as exc:
        logger.debug("ICC computation failed: %s", exc)
        return None


def _cohen_kappa(values_a: np.ndarray, values_b: np.ndarray) -> Optional[float]:
    """Cohen's kappa for two binary sequences of equal length.

    Computed directly from the definition rather than via a third-party
    library, because the binary case is short and pingouin no longer
    exposes ``cohen_kappa`` in the 0.5.x line. Reproduces ``scikit-
    learn``'s ``cohen_kappa_score`` and R's ``irr::kappa2`` numerically.

    Returns ``None`` when kappa is undefined: zero-length input, mismatched
    lengths, or expected agreement equal to 1 with non-perfect observed
    agreement (degenerate flat sequences that disagree). Returns ``1.0``
    when both sequences are flat AND equal (degenerate-but-perfect case).
    """
    if len(values_a) == 0 or len(values_a) != len(values_b):
        return None

    a = np.asarray(values_a, dtype=np.int64)
    b = np.asarray(values_b, dtype=np.int64)
    n = len(a)

    # Observed agreement
    p_o = float(np.mean(a == b))

    # Expected agreement (chance) over the union of label values seen.
    labels = np.union1d(a, b)
    p_e = 0.0
    for label in labels:
        p_e += float(np.mean(a == label)) * float(np.mean(b == label))

    if np.isclose(p_e, 1.0):
        # Degenerate: both rasters concentrated on a single label.
        return 1.0 if p_o == 1.0 else None

    value = (p_o - p_e) / (1.0 - p_e)
    if not np.isfinite(value):
        return None
    return value


def _krippendorff_alpha(values_a: np.ndarray, values_b: np.ndarray) -> Optional[float]:
    """Krippendorff's alpha for two binary sequences of equal length.

    Uses the standalone ``krippendorff`` package (Pereyra & Cabrera 2023,
    https://github.com/pln-fing-udelar/fast-krippendorff). The pingouin
    library no longer exposes a Krippendorff implementation in the 0.5+
    line, so a dedicated package is the cleanest dependency. Returns
    ``None`` when the package is unavailable or the computation cannot
    produce a finite value (e.g., both raters constant)."""
    if len(values_a) == 0 or len(values_a) != len(values_b):
        return None
    try:
        import krippendorff  # type: ignore
    except Exception as exc:
        logger.error(
            "krippendorff import failed: %s", exc, exc_info=True,
        )
        return None

    try:
        data = np.vstack([
            np.asarray(values_a, dtype=np.int64),
            np.asarray(values_b, dtype=np.int64),
        ])
        # API: alpha(reliability_data=<2D array>, level_of_measurement=...)
        value = float(
            krippendorff.alpha(
                reliability_data=data, level_of_measurement="nominal"
            )
        )
    except Exception as exc:
        logger.debug("Krippendorff's alpha computation failed: %s", exc)
        return None
    if not np.isfinite(value):
        return None
    return value


# -------------------------------------------------------------------- #
# Annotation event helpers
# -------------------------------------------------------------------- #


def _load_annotation_events(
    path: str,
) -> Tuple[List[Tuple[str, float, float]], float]:
    """Return ``(events, test_duration_seconds)``.

    ``events`` is a list of (behavior, onset_seconds, offset_seconds)
    tuples in the order they appear, excluding the synthetic
    ``RecordingStart`` marker. ``test_duration_seconds`` is taken from
    the metadata section if present; otherwise it falls back to the
    largest offset observed in the event log.
    """
    # Extract the Event section using the utility shipped with RABET.
    events_df = load_event_dataframe(path)
    test_duration = 0.0

    # Also peek at the metadata section for Test Duration. Use a regex so
    # subtle spelling variations ("Test  Duration", "TEST DURATION", an
    # extra unit suffix, etc.) all parse the same way.
    test_duration_re = re.compile(
        r"^\s*test\s*duration\b[^,]*,\s*([0-9]*\.?[0-9]+)", re.IGNORECASE
    )
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for _ in range(10):
                line = fh.readline()
                if not line:
                    break
                match = test_duration_re.search(line)
                if match:
                    try:
                        test_duration = float(match.group(1))
                    except ValueError:
                        pass
                    break
    except OSError:
        pass

    events: List[Tuple[str, float, float]] = []
    if events_df is None or events_df.empty:
        return events, test_duration

    for _, row in events_df.iterrows():
        behavior = str(row.get("Event", "")).strip()
        if not behavior or behavior == "RecordingStart":
            continue
        try:
            onset = float(row.get("Onset", "nan"))
            offset = float(row.get("Offset", "nan"))
        except (TypeError, ValueError):
            continue
        if not np.isfinite(onset) or not np.isfinite(offset):
            continue
        events.append((behavior, onset, offset))
        if offset > test_duration:
            test_duration = offset

    return events, test_duration


def _bin_events(
    events: List[Tuple[str, float, float]],
    behaviors: List[str],
    duration_seconds: float,
    bin_seconds: float,
) -> Dict[str, np.ndarray]:
    """Return ``{behavior: binary_array}`` indicating, for each
    fixed-width time bin, whether the behaviour was active at any
    moment inside the bin."""
    if duration_seconds <= 0 or bin_seconds <= 0:
        return {beh: np.zeros(0, dtype=np.uint8) for beh in behaviors}

    n_bins = int(np.ceil(duration_seconds / bin_seconds))
    bins: Dict[str, np.ndarray] = {
        beh: np.zeros(n_bins, dtype=np.uint8) for beh in behaviors
    }
    for behavior, onset, offset in events:
        if behavior not in bins:
            continue
        if offset < onset:
            onset, offset = offset, onset
        start_idx = max(0, int(np.floor(onset / bin_seconds)))
        # Clamp the end index on both sides: the (offset - 1e-9) shift can
        # push a tiny / zero-duration event below zero, and a future offset
        # value beyond duration_seconds could exceed n_bins - 1.
        end_idx = min(
            n_bins - 1,
            max(0, int(np.floor((offset - 1e-9) / bin_seconds))),
        )
        if end_idx < start_idx:
            end_idx = start_idx
        bins[behavior][start_idx : end_idx + 1] = 1
    return bins


# -------------------------------------------------------------------- #
# ReliabilityModel
# -------------------------------------------------------------------- #


class ReliabilityModel(QObject):
    """Compute inter-rater / intra-rater reliability between two RABET
    outputs. See module docstring for the two supported modes."""

    summary_results_ready = Signal(object)   # SummaryAgreementResult
    detailed_results_ready = Signal(object)  # DetailedAgreementResult
    error_occurred = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)

    # ---------------------- Mode 1: Summary ---------------------- #

    def compute_from_summaries(
        self,
        summary_path_a: str,
        summary_path_b: str,
    ) -> Optional[SummaryAgreementResult]:
        """Match two summary_table.csv files by ``animal_id`` and compute
        per-metric ICC(2,1), Pearson r, and mean absolute difference."""
        try:
            df_a = _parse_summary_table(summary_path_a)
            df_b = _parse_summary_table(summary_path_b)
        except Exception as exc:
            msg = f"Could not parse summary CSV: {exc}"
            self.logger.error(msg)
            self.error_occurred.emit(msg)
            return None

        animals_a = set(df_a["animal_id"])
        animals_b = set(df_b["animal_id"])
        matched = sorted(animals_a & animals_b)
        unmatched_a = sorted(animals_a - animals_b)
        unmatched_b = sorted(animals_b - animals_a)

        if not matched:
            msg = (
                "No animal_id values are shared between the two summary "
                "tables; cannot compute agreement."
            )
            self.error_occurred.emit(msg)
            return None

        # Restrict and align on animal_id.
        df_a_m = df_a.set_index("animal_id").loc[matched]
        df_b_m = df_b.set_index("animal_id").loc[matched]

        # Use the intersection of metric columns. Custom metrics that
        # only appear in one file are reported as unmatched but skipped.
        common_metrics = [
            c for c in df_a_m.columns if c in df_b_m.columns
        ]

        result = SummaryAgreementResult(
            matched_animals=matched,
            unmatched_a=unmatched_a,
            unmatched_b=unmatched_b,
        )

        for metric in common_metrics:
            values_a = df_a_m[metric].to_numpy(dtype=float)
            values_b = df_b_m[metric].to_numpy(dtype=float)

            mask = np.isfinite(values_a) & np.isfinite(values_b)
            n = int(mask.sum())
            if n == 0:
                result.rows.append(SummaryAgreementRow(
                    metric=metric, n_pairs=0,
                    icc=None, pearson_r=None, mean_abs_diff=None,
                    mean_a=None, mean_b=None,
                ))
                continue

            va = values_a[mask]
            vb = values_b[mask]

            icc = _icc_two_way_single(va, vb)

            pearson_r: Optional[float]
            if n >= 2 and np.std(va) > 0 and np.std(vb) > 0:
                pearson_r = float(np.corrcoef(va, vb)[0, 1])
            elif n >= 2 and np.allclose(va, vb):
                pearson_r = 1.0
            else:
                pearson_r = None

            mean_abs_diff = float(np.mean(np.abs(va - vb)))

            result.rows.append(SummaryAgreementRow(
                metric=metric,
                n_pairs=n,
                icc=icc,
                pearson_r=pearson_r,
                mean_abs_diff=mean_abs_diff,
                mean_a=float(np.mean(va)),
                mean_b=float(np.mean(vb)),
            ))

            # Scatter-plot data: only include matched-and-finite animals.
            scatter_animals = [a for a, ok in zip(matched, mask, strict=False) if ok]
            result.scatter_data[metric] = (
                scatter_animals,
                va.tolist(),
                vb.tolist(),
            )

        self.summary_results_ready.emit(result)
        return result

    # ---------------------- Mode 2: Detailed ---------------------- #

    def compute_from_annotations(
        self,
        annotation_path_a: str,
        annotation_path_b: str,
        bin_seconds: float = 1.0,
        label_a: str = "Scorer A",
        label_b: str = "Scorer B",
    ) -> Optional[DetailedAgreementResult]:
        """Time-window-bin two annotation CSVs and compute per-behavior
        Cohen's kappa, Krippendorff's alpha, and raw percentage agreement.

        Returns the raw events as well so the caller can render a
        pairwise raster overlay."""
        if bin_seconds <= 0:
            self.error_occurred.emit("Bin width must be positive.")
            return None

        try:
            events_a, dur_a = _load_annotation_events(annotation_path_a)
            events_b, dur_b = _load_annotation_events(annotation_path_b)
        except Exception as exc:
            msg = f"Could not parse annotation CSV: {exc}"
            self.logger.error(msg)
            self.error_occurred.emit(msg)
            return None

        if not events_a and not events_b:
            self.error_occurred.emit(
                "Both annotation files are empty after parsing."
            )
            return None

        duration = max(dur_a, dur_b)
        if duration <= 0:
            self.error_occurred.emit(
                "Could not determine the test duration from the annotation "
                "files. Make sure they contain a Test Duration metadata row "
                "or at least one event."
            )
            return None

        behaviors = sorted(
            {beh for beh, _, _ in events_a} | {beh for beh, _, _ in events_b}
        )

        bins_a = _bin_events(events_a, behaviors, duration, bin_seconds)
        bins_b = _bin_events(events_b, behaviors, duration, bin_seconds)

        result = DetailedAgreementResult(
            behaviors=behaviors,
            bin_seconds=bin_seconds,
            test_duration_seconds=duration,
            events_a=events_a,
            events_b=events_b,
            label_a=label_a,
            label_b=label_b,
        )

        for behavior in behaviors:
            va = bins_a[behavior]
            vb = bins_b[behavior]

            kappa = _cohen_kappa(va, vb)
            alpha = _krippendorff_alpha(va, vb)
            raw = float(np.mean(va == vb)) if len(va) > 0 else 0.0

            result.rows.append(DetailedAgreementRow(
                behavior=behavior,
                n_bins=int(len(va)),
                n_active_a=int(va.sum()),
                n_active_b=int(vb.sum()),
                cohen_kappa=kappa,
                krippendorff_alpha=alpha,
                raw_agreement=raw,
            ))

        self.detailed_results_ready.emit(result)
        return result

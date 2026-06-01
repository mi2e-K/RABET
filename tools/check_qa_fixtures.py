"""Quick sanity check: load the QA fixtures into ReliabilityModel and
print the per-metric ICC banding. Used by maintainers to confirm the
fixtures still exercise green / amber / red after edits."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QCoreApplication
import models.reliability_model as rm


def _band(icc):
    if icc is None:
        return "N/A"
    if icc >= 0.75:
        return "green"
    if icc >= 0.50:
        return "amber"
    return "red"


def main() -> None:
    app = QCoreApplication([])  # noqa: F841 - required for QObject lifetimes
    model = rm.ReliabilityModel()

    base = Path("tests/fixtures/reliability_qa")
    print("=== Summary mode (scorer A vs scorer B) ===")
    summary = model.compute_from_summaries(
        str(base / "qa_summary_scorerA.csv"),
        str(base / "qa_summary_scorerB.csv"),
    )
    print(f"Matched animals: {len(summary.matched_animals)}")
    print()
    print(f"{'Metric':<55}{'ICC':>8}{'Band':>10}")
    print("-" * 73)
    for row in summary.rows:
        icc_str = f"{row.icc:>8.3f}" if row.icc is not None else f"{'N/A':>8}"
        print(f"{row.metric:<55}{icc_str}{_band(row.icc):>10}")

    print()
    print("=== Detailed mode (annotation pair) ===")
    detailed = model.compute_from_annotations(
        str(base / "qa_annotation_scorerA.csv"),
        str(base / "qa_annotation_scorerB.csv"),
        bin_seconds=1.0,
    )
    print(f"Duration: {detailed.test_duration_seconds:.1f}s  bin: {detailed.bin_seconds:.2f}s")
    print()
    print(f"{'Behaviour':<22}{'kappa':>8}{'alpha':>8}{'raw':>8}{'Band':>10}")
    print("-" * 56)
    for row in detailed.rows:
        kappa_str = f"{row.cohen_kappa:>8.3f}" if row.cohen_kappa is not None else f"{'N/A':>8}"
        alpha_str = f"{row.krippendorff_alpha:>8.3f}" if row.krippendorff_alpha is not None else f"{'N/A':>8}"
        # Use Landis & Koch bands for kappa.
        if row.cohen_kappa is None:
            kappa_band = "N/A"
        elif row.cohen_kappa >= 0.70:
            kappa_band = "green"
        elif row.cohen_kappa >= 0.40:
            kappa_band = "amber"
        else:
            kappa_band = "red"
        print(f"{row.behavior:<22}{kappa_str}{alpha_str}{row.raw_agreement:>8.3f}{kappa_band:>10}")


if __name__ == "__main__":
    main()

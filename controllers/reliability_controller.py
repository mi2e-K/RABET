# controllers/reliability_controller.py - Mediator for the Reliability tab
"""
ReliabilityController - mediates between ReliabilityView and ReliabilityModel.

Computations are dispatched synchronously: typical RABET datasets (tens
of animals, hundreds of events per video) finish in well under a second.
If performance becomes a concern, the computation calls below can be
wrapped in a QThread without altering the public signal surface.
"""

from __future__ import annotations

import csv
import logging
from typing import Optional

from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QFileDialog, QMessageBox, QDialog

from models.reliability_model import (
    ReliabilityModel,
    SummaryAgreementResult,
    DetailedAgreementResult,
)
from views.reliability_view import ReliabilityView, SummaryMatchDialog


logger = logging.getLogger(__name__)


class ReliabilityController(QObject):
    """Glue object that owns a ReliabilityModel and drives ReliabilityView."""

    def __init__(self, view: ReliabilityView, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._view = view
        self._model = ReliabilityModel(self)
        # Optional ConfigManager handle for directory-persistence. Wired by
        # AppController via set_config_manager() once construction is done.
        self._config_manager = None

        # View -> controller
        self._view.compute_summary_requested.connect(self.on_compute_summary)
        self._view.compute_detailed_requested.connect(self.on_compute_detailed)
        self._view.export_summary_requested.connect(self.on_export_summary)
        self._view.export_detailed_requested.connect(self.on_export_detailed)

        # Each file picker emits path_changed when the user finishes the
        # Browse dialog. We listen so the chosen directory can be saved
        # and restored across sessions.
        self._view.summary_picker_a.path_changed.connect(
            lambda p: self._remember_dir("reliability_summary", p)
        )
        self._view.summary_picker_b.path_changed.connect(
            lambda p: self._remember_dir("reliability_summary", p)
        )
        self._view.detailed_picker_a.path_changed.connect(
            lambda p: self._remember_dir("reliability_annotation", p)
        )
        self._view.detailed_picker_b.path_changed.connect(
            lambda p: self._remember_dir("reliability_annotation", p)
        )

        # Model -> view
        self._model.summary_results_ready.connect(self._view.show_summary_results)
        self._model.detailed_results_ready.connect(self._view.show_detailed_results)
        self._model.error_occurred.connect(self._view.show_error)

    # ---------------------------------------------------------------- #
    # ConfigManager wiring
    # ---------------------------------------------------------------- #

    def set_config_manager(self, config_manager) -> None:
        """Receive the application's ConfigManager and restore the last
        directories used in the Summary and Detailed picker pairs."""
        self._config_manager = config_manager
        try:
            summary_dir = config_manager.get_last_directory("reliability_summary")
        except Exception:  # pragma: no cover - defensive
            summary_dir = ""
        try:
            detailed_dir = config_manager.get_last_directory("reliability_annotation")
        except Exception:  # pragma: no cover - defensive
            detailed_dir = ""

        if summary_dir:
            self._view.summary_picker_a.set_initial_dir(summary_dir)
            self._view.summary_picker_b.set_initial_dir(summary_dir)
        if detailed_dir:
            self._view.detailed_picker_a.set_initial_dir(detailed_dir)
            self._view.detailed_picker_b.set_initial_dir(detailed_dir)

    def _remember_dir(self, directory_type: str, path: str) -> None:
        """Persist the parent directory of ``path`` for next-session restore."""
        if self._config_manager is None or not path:
            return
        import os
        parent = os.path.dirname(path)
        if not parent:
            return
        try:
            self._config_manager.update_last_directory(directory_type, parent)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(
                "ConfigManager.update_last_directory failed for %s: %s",
                directory_type, exc,
            )

    # ---------------------------------------------------------------- #
    # Compute slots
    # ---------------------------------------------------------------- #

    @Slot(str, str)
    def on_compute_summary(self, path_a: str, path_b: str) -> None:
        logger.info("Computing Summary-mode agreement: %s vs %s", path_a, path_b)
        match_plan = self._model.build_summary_match_plan(path_a, path_b)
        if match_plan is None:
            return

        manual_pairs = []
        if match_plan.unmatched_a or match_plan.unmatched_b:
            self._view.summary_status.setText("Review animal_id matching...")
            dialog = SummaryMatchDialog(
                match_plan.auto_pairs,
                match_plan.unmatched_a,
                match_plan.unmatched_b,
                self._view,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                self._view.reset_summary_compute_state(
                    "Summary agreement cancelled."
                )
                return
            manual_pairs = dialog.manual_pairs()

        self._model.compute_from_summaries(
            path_a,
            path_b,
            manual_pairs=manual_pairs,
        )

    @Slot(str, str, float)
    def on_compute_detailed(
        self, path_a: str, path_b: str, bin_seconds: float
    ) -> None:
        logger.info(
            "Computing Detailed-mode agreement (bin=%.2fs): %s vs %s",
            bin_seconds, path_a, path_b,
        )
        self._model.compute_from_annotations(
            path_a, path_b, bin_seconds=bin_seconds
        )

    # ---------------------------------------------------------------- #
    # Export slots
    # ---------------------------------------------------------------- #

    @Slot()
    def on_export_summary(self) -> None:
        result = self._view.current_summary_result()
        if result is None or not result.rows:
            QMessageBox.information(
                self._view, "Reliability",
                "No summary results to export. Run Compute first."
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self._view,
            "Export summary agreement results",
            "reliability_summary.csv",
            "CSV files (*.csv)",
        )
        if not path:
            return

        try:
            self._write_summary_csv(result, path)
        except OSError as exc:
            QMessageBox.warning(
                self._view, "Reliability",
                f"Could not write {path}:\n{exc}",
            )
            return
        QMessageBox.information(
            self._view, "Reliability",
            f"Summary agreement results exported to:\n{path}",
        )

    @Slot()
    def on_export_detailed(self) -> None:
        result = self._view.current_detailed_result()
        if result is None or not result.rows:
            QMessageBox.information(
                self._view, "Reliability",
                "No detailed results to export. Run Compute first."
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self._view,
            "Export detailed agreement results",
            "reliability_detailed.csv",
            "CSV files (*.csv)",
        )
        if not path:
            return

        try:
            self._write_detailed_csv(result, path)
        except OSError as exc:
            QMessageBox.warning(
                self._view, "Reliability",
                f"Could not write {path}:\n{exc}",
            )
            return
        QMessageBox.information(
            self._view, "Reliability",
            f"Detailed agreement results exported to:\n{path}",
        )

    # ---------------------------------------------------------------- #
    # Private writers
    # ---------------------------------------------------------------- #

    @staticmethod
    def _write_summary_csv(result: SummaryAgreementResult, path: str) -> None:
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow([
                "Metric", "n_pairs", "ICC(2,1)", "Pearson_r",
                "Mean_abs_diff", "Mean_A", "Mean_B",
            ])
            for row in result.rows:
                writer.writerow([
                    row.metric,
                    row.n_pairs,
                    "" if row.icc is None else f"{row.icc:.6f}",
                    "" if row.pearson_r is None else f"{row.pearson_r:.6f}",
                    "" if row.mean_abs_diff is None else f"{row.mean_abs_diff:.6f}",
                    "" if row.mean_a is None else f"{row.mean_a:.6f}",
                    "" if row.mean_b is None else f"{row.mean_b:.6f}",
                ])
            writer.writerow([])
            writer.writerow(["Matched animals", *result.matched_animals])
            if result.unmatched_a:
                writer.writerow(["Only in scorer A", *result.unmatched_a])
            if result.unmatched_b:
                writer.writerow(["Only in scorer B", *result.unmatched_b])
            if result.matched_pairs:
                writer.writerow([])
                writer.writerow(["Matched animal pairs"])
                writer.writerow([
                    "match_id", "animal_id_a", "animal_id_b", "source",
                ])
                for pair in result.matched_pairs:
                    writer.writerow([
                        pair.match_id,
                        pair.animal_id_a,
                        pair.animal_id_b,
                        pair.source,
                    ])

    @staticmethod
    def _write_detailed_csv(result: DetailedAgreementResult, path: str) -> None:
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow([
                "Bin width (s)", f"{result.bin_seconds:.3f}",
                "Test duration (s)", f"{result.test_duration_seconds:.3f}",
            ])
            writer.writerow([])
            writer.writerow([
                "Behaviour", "Bins_total", "Bins_active_A", "Bins_active_B",
                "Cohen_kappa", "Krippendorff_alpha", "Raw_percent_agreement",
            ])
            for row in result.rows:
                writer.writerow([
                    row.behavior,
                    row.n_bins,
                    row.n_active_a,
                    row.n_active_b,
                    "" if row.cohen_kappa is None else f"{row.cohen_kappa:.6f}",
                    "" if row.krippendorff_alpha is None else f"{row.krippendorff_alpha:.6f}",
                    f"{row.raw_agreement:.6f}",
                ])

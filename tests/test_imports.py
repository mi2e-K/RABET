"""Smoke tests: every non-GUI module must import cleanly."""
from __future__ import annotations

import importlib
import pytest


# GUI views are intentionally excluded — importing them constructs widgets
# that need a QApplication and a display server. Smoke-import the
# data/model/utility layer instead, which is what the analysis stack
# actually exercises in tests.
MODULES = [
    "version",
    "models.action_map_model",
    "models.annotation_model",
    "models.analysis_config",
    "models.analysis_model",
    "models.project_model",
    "models.video_model",
    "utils.annotation_csv_parser",
    "utils.auto_close_message",
    "utils.config_manager",
    "utils.config_path_manager",
    "utils.directory_init",
    "utils.file_manager",
    "utils.in_memory_log_handler",
    "utils.loading_overlay",
    "utils.log_manager",
    "utils.logger",
    "utils.theme_manager",
    "utils.threaded_loader",
]


@pytest.mark.parametrize("module_name", MODULES)
def test_module_imports(module_name, qt_app):
    """Importing the module must not raise."""
    module = importlib.import_module(module_name)
    assert module is not None

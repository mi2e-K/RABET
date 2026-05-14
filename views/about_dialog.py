"""Rich "About RABET" dialog.

Replaces the v1.2.0 plain-text ``QMessageBox.information`` with a small
``QDialog`` that supports HTML / Markdown style content, clickable
external links, and a Copy-to-Clipboard button for the citation BibTeX
snippet. The text is reflowed via ``QTextBrowser`` so long lines are
not truncated by the parent window's width.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QHBoxLayout,
)

from version import __version__ as _RABET_VERSION


_REPOSITORY_URL = "https://github.com/mi2e-K/RABET"
_CONCEPT_DOI_URL = "https://doi.org/10.5281/zenodo.15313025"


def _bibtex_snippet(version: str) -> str:
    """Return a minimal BibTeX entry for the current RABET release."""
    return (
        "@software{rabet_"
        + version.replace(".", "_")
        + ",\n"
        "  author       = {Mitsui, Koshiro},\n"
        "  title        = {RABET --- Real-time Animal Behavior Event Tagger},\n"
        f"  version      = {{{version}}},\n"
        "  year         = {2026},\n"
        "  url          = {" + _REPOSITORY_URL + "},\n"
        "  doi          = {10.5281/zenodo.15313025}\n"
        "}\n"
    )


class AboutDialog(QDialog):
    """Rich-content About dialog with link support."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About RABET")
        self.resize(560, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        # Header / title
        header = QLabel(
            f"<h2 style='margin-bottom:2px;'>RABET</h2>"
            f"<div style='color:#888;'>Real-time Animal Behavior Event Tagger</div>"
            f"<div style='margin-top:6px;'><b>Version:</b> {_RABET_VERSION}</div>"
        )
        header.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(header)

        # Main content (HTML, clickable external links).
        body = QTextBrowser(self)
        body.setOpenExternalLinks(False)
        body.anchorClicked.connect(self._on_anchor_clicked)
        body.setHtml(self._build_body_html())
        layout.addWidget(body, 1)

        # Citation footer with BibTeX preview + Copy button.
        cite_label = QLabel("BibTeX")
        cite_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(cite_label)

        self._bibtex_view = QTextBrowser(self)
        self._bibtex_view.setLineWrapMode(QTextBrowser.LineWrapMode.NoWrap)
        self._bibtex_view.setMaximumHeight(140)
        self._bibtex_view.setPlainText(_bibtex_snippet(_RABET_VERSION))
        self._bibtex_view.setOpenExternalLinks(False)
        layout.addWidget(self._bibtex_view)

        footer = QHBoxLayout()

        copy_button = QPushButton("Copy BibTeX")
        copy_button.setToolTip("Copy the BibTeX snippet above to the clipboard")
        copy_button.clicked.connect(self._copy_bibtex)
        footer.addWidget(copy_button)

        footer.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.clicked.connect(self.accept)
        footer.addWidget(buttons)

        layout.addLayout(footer)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _build_body_html(self) -> str:
        return (
            "<p>RABET is a desktop application for behavioural annotation of "
            "animal videos. Researchers play back recordings, tag behaviours "
            "with configurable keyboard shortcuts in real time, visualise "
            "event timelines and export per-session and per-interval "
            "summaries for downstream statistical analysis.</p>"
            "<h3>Features</h3>"
            "<ul>"
            "<li>Video playback with frame-by-frame navigation</li>"
            "<li>Keyboard-based real-time annotation</li>"
            "<li>Timeline visualisation of behaviour events</li>"
            "<li>Timed recording with pause / resume capability</li>"
            "<li>Export annotations to CSV with summary statistics</li>"
            "<li>Analyse multiple annotation files to aggregate behavioural data</li>"
            "<li>Project management for organising research assets</li>"
            "<li>Data visualisation with customisable raster plots</li>"
            "</ul>"
            "<h3>Author</h3>"
            "<p>Koshiro Mitsui &nbsp;"
            "<a href='https://orcid.org/0009-0009-0556-3906'>"
            "ORCID 0009-0009-0556-3906</a></p>"
            "<h3>License</h3>"
            "<p>Released under the MIT License - see the bundled "
            "<tt>LICENSE</tt> file for details.</p>"
            "<h3>Links</h3>"
            "<ul>"
            f"<li>Repository: <a href='{_REPOSITORY_URL}'>{_REPOSITORY_URL}</a></li>"
            f"<li>DOI (all versions): <a href='{_CONCEPT_DOI_URL}'>{_CONCEPT_DOI_URL}</a></li>"
            "</ul>"
            "<p style='color:#888;'>&copy; 2026 Koshiro Mitsui</p>"
        )

    def _on_anchor_clicked(self, url):
        """Open external links in the system browser."""
        QDesktopServices.openUrl(url)

    def _copy_bibtex(self):
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._bibtex_view.toPlainText())

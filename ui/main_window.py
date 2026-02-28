"""Main application window — parameter panel + drawing canvas."""
from __future__ import annotations
import os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QHBoxLayout, QWidget, QFileDialog, QMessageBox,
    QStatusBar,
)
from core.parameters import CoilParameters
from core.layout_engine import generate_layout
from export.export_dxf import export_dxf
from export.export_pdf import export_pdf
from ui.parameter_panel import ParameterPanel
from ui.drawing_view import DrawingView


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Helvix — Parametric Coil Drafting")
        self.resize(1400, 900)

        # Central widget
        central = QWidget()
        hbox = QHBoxLayout(central)
        hbox.setContentsMargins(4, 4, 4, 4)

        self._panel = ParameterPanel()
        self._canvas = DrawingView()

        hbox.addWidget(self._panel)
        hbox.addWidget(self._canvas, 1)
        self.setCentralWidget(central)

        # Status bar
        self._status = QStatusBar()
        self.setStatusBar(self._status)

        # Connections
        self._panel.generate_requested.connect(self._on_generate)
        self._panel.export_dxf_requested.connect(self._on_export_dxf)
        self._panel.export_pdf_requested.connect(self._on_export_pdf)

        # Auto-generate on start
        self._on_generate(CoilParameters())

    # ── slots ─────────────────────────────────────────────────────────────
    def _on_generate(self, params: CoilParameters):
        try:
            layout = generate_layout(params)
            self._canvas.set_layout(layout)
            self._status.showMessage("Drawing generated.", 3000)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _on_export_dxf(self):
        layout = self._canvas.get_layout()
        if layout is None:
            QMessageBox.warning(self, "No Drawing", "Generate a drawing first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export DXF", "coil_output.dxf", "DXF Files (*.dxf)"
        )
        if path:
            try:
                export_dxf(layout, path)
                self._status.showMessage(f"DXF saved: {path}", 5000)
            except Exception as exc:
                QMessageBox.critical(self, "Export Error", str(exc))

    def _on_export_pdf(self):
        layout = self._canvas.get_layout()
        if layout is None:
            QMessageBox.warning(self, "No Drawing", "Generate a drawing first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PDF", "coil_output.pdf", "PDF Files (*.pdf)"
        )
        if path:
            try:
                export_pdf(layout, path)
                self._status.showMessage(f"PDF saved: {path}", 5000)
            except Exception as exc:
                QMessageBox.critical(self, "Export Error", str(exc))

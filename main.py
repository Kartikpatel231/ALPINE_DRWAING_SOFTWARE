"""Helvix — Parametric Coil Drafting Software

Entry point: launch the Qt application.
"""

from __future__ import annotations
import sys
import os

# Ensure package imports resolve when running from the coil_cad/ directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Helvix Coil CAD")
    app.setOrganizationName("Helvix")

    # Global exception hook so crashes are visible
    def _excepthook(etype, value, tb):
        import traceback
        traceback.print_exception(etype, value, tb)
        sys.__excepthook__(etype, value, tb)
    sys.excepthook = _excepthook

    # Global stylesheet for a clean engineering look
    app.setStyleSheet(
        """
        QMainWindow { background: #F0F0F0; }
        QGroupBox {
            font-weight: bold;
            border: 1px solid #CCCCCC;
            border-radius: 4px;
            margin-top: 10px;
            padding-top: 14px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
        }
        QDoubleSpinBox, QSpinBox {
            padding: 2px 4px;
        }
        """
    )

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

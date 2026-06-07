"""
main.py  —  Coil Helvix Launcher (Tabbed Version with PyInstaller support)
==================================================
Single password check, then opens a unified window with tabs:
    • Front View
    • Side View
    • Header View
    • Top View

Works both as normal script and as PyInstaller --onefile executable.
"""

import sys
import os
import hmac
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── PyQt6 imports ────────────────────────────────────────────────────────────
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QMainWindow,
    QTabWidget,
    QWidget,
    QVBoxLayout,
)
from PyQt6.QtCore import Qt

# ── Fix for PyInstaller: add _MEIPASS to sys.path if frozen ──────────────────
if getattr(sys, 'frozen', False):
    # Running as bundled executable
    base_path = sys._MEIPASS
else:
    # Running as normal script
    base_path = Path(__file__).resolve().parent

# Ensure the base path is in sys.path so imports find the view modules
if str(base_path) not in sys.path:
    sys.path.insert(0, str(base_path))

_HERE = Path(base_path)

# ── Access / password helpers (unchanged) ────────────────────────────────────
ACCESS_WINDOW_DAYS = 30
DEFAULT_PASSWORD_SHA256 = hashlib.sha256("coilhelvix".encode("utf-8")).hexdigest()


def _access_state_path() -> Path:
    appdata = os.getenv("APPDATA")
    base_dir = Path(appdata) if appdata else (Path.home() / ".coil_helvix")
    access_dir = base_dir / "CoilHelvix"
    access_dir.mkdir(parents=True, exist_ok=True)
    return access_dir / "access_state.json"


def _load_or_create_first_run() -> datetime:
    state_file = _access_state_path()
    now_utc = datetime.now(timezone.utc)
    if not state_file.exists():
        state_file.write_text(
            json.dumps({"first_run_utc": now_utc.isoformat()}, indent=2),
            encoding="utf-8",
        )
        return now_utc
    try:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
        raw = str(payload.get("first_run_utc", "")).strip()
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        state_file.write_text(
            json.dumps({"first_run_utc": now_utc.isoformat()}, indent=2),
            encoding="utf-8",
        )
        return now_utc


def _resolve_expiry(first_run: datetime) -> datetime:
    fixed = os.getenv("COIL_HELVIX_EXPIRY_DATE", "").strip()
    if fixed:
        try:
            d = datetime.strptime(fixed, "%Y-%m-%d").date()
            return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc)
        except ValueError:
            pass
    return first_run + timedelta(days=ACCESS_WINDOW_DAYS)


def _is_password_valid(entered: str) -> bool:
    expected = os.getenv(
        "COIL_HELVIX_PASSWORD_SHA256", DEFAULT_PASSWORD_SHA256
    ).strip().lower()
    return hmac.compare_digest(
        hashlib.sha256(entered.encode("utf-8")).hexdigest().lower(), expected
    )


def _enforce_access() -> bool:
    """
    Returns True if access should be granted.
    """
    first_run = _load_or_create_first_run()
    expiry = _resolve_expiry(first_run)
    now = datetime.now(timezone.utc)

    if now <= expiry:
        return True

    password, ok = QInputDialog.getText(
        None,
        "Coil Helvix — Access Required",
        "Enter password to launch all views:",
        QLineEdit.EchoMode.Password,
    )
    if not ok:
        return False
    if not _is_password_valid(password):
        QMessageBox.critical(
            None, "Access Denied", "Invalid password. Application will close."
        )
        return False
    return True


# ── Patch sub‑module access checks ──────────────────────────────────────────
def _patch_module_access(mod) -> None:
    def _always_allow():
        return True, None
    if hasattr(mod, "_enforce_startup_access"):
        mod._enforce_startup_access = _always_allow


def _extract_central_widget(module_name: str) -> QWidget:
    """
    Import the module, patch its access guard, create its MainWindow,
    extract the central widget, hide/destroy the MainWindow,
    and return the central widget as a standalone widget.
    """
    try:
        import importlib
        mod = importlib.import_module(module_name)
        _patch_module_access(mod)

        main_win = mod.MainWindow()
        central = main_win.centralWidget()

        if central is None:
            central = main_win

        central.setParent(None)
        main_win.hide()
        setattr(central, "_hidden_main_window", main_win)

        return central
    except Exception as exc:
        error_widget = QWidget()
        layout = QVBoxLayout(error_widget)
        from PyQt6.QtWidgets import QLabel
        label = QLabel(f"Failed to load {module_name}.py\n\n{exc}")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        return error_widget


class CoilHelvixTabs(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Coil Helvix — Unified View")
        self.resize(1200, 800)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.view_defs = [
            ("frontview", "Front View"),
            ("sideview", "Side View"),
            ("side_view", "Header View"),
            ("topview", "Top View"),
        ]

        for module_name, title in self.view_defs:
            widget = _extract_central_widget(module_name)
            self.tabs.addTab(widget, title)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Coil Helvix Drawing Suite")
    app.setOrganizationName("Coil Helvix")
    app.setFont(QFont("Segoe UI", 10))

    if not _enforce_access():
        sys.exit(0)

    window = CoilHelvixTabs()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
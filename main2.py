"""
main.py  —  Coil Helvix Launcher (Tabbed Version)
==================================================
Single password check, then opens a unified window with tabs:
    • Front View
    • Side View
    • Header View
    • Top View

Usage:
    python main.py
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

# ── Make the script's own directory importable ───────────────────────────────
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

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

    Logic:
      - Within trial period (now <= expiry): grant access WITHOUT password.
      - After trial period (now > expiry):   require password.
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


# ── Patch sub‑module access checks so they never block or prompt ──────────────
def _patch_module_access(mod) -> None:
    """Replace the sub-module's access guard with a no-op that always allows."""
    def _always_allow():
        return True, None
    if hasattr(mod, "_enforce_startup_access"):
        mod._enforce_startup_access = _always_allow


# ── Extract a view's central widget from its MainWindow ──────────────────────
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

        # Instantiate the view's main window
        main_win = mod.MainWindow()
        central = main_win.centralWidget()

        if central is None:
            # No central widget – fallback: return the main window itself
            central = main_win

        # Reparent the central widget so it can live inside a tab
        central.setParent(None)          # break old parent relationship
        main_win.hide()                  # hide the original window
        # Keep a reference to main_win to avoid garbage collection
        # (some signals might still be needed by the central widget)
        setattr(central, "_hidden_main_window", main_win)

        return central
    except Exception as exc:
        # Create a simple error widget
        error_widget = QWidget()
        layout = QVBoxLayout(error_widget)
        from PyQt6.QtWidgets import QLabel
        label = QLabel(f"Failed to load {module_name}.py\n\n{exc}")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        return error_widget


# ── Tabbed main window ───────────────────────────────────────────────────────
class CoilHelvixTabs(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Coil Helvix — Unified View")
        self.resize(1200, 800)

        # Create tab widget
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Define views (module name, display name)
        self.view_defs = [
            ("frontview", "Front View"),
            ("sideview", "Side View"),
            ("side_view", "Header View"),
            ("topview", "Top View"),
        ]

        # Build each tab
        for module_name, title in self.view_defs:
            widget = _extract_central_widget(module_name)
            self.tabs.addTab(widget, title)


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Coil Helvix Drawing Suite")
    app.setOrganizationName("Coil Helvix")
    app.setFont(QFont("Segoe UI", 10))

    # Single access check for the whole suite
    if not _enforce_access():
        sys.exit(0)

    # Create and show the tabbed window
    window = CoilHelvixTabs()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
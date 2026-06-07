"""
main.py  —  Coil Helvix Launcher
=========================================
Single password check, then opens three
separate independent windows:
    1. Front View   (frontview.py)
    2. Side View    (sideview.py)
    3. Top View     (topview.py)

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

# ── Make the script's own directory importable ────────────────────────────────
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QInputDialog,
    QLineEdit,
    QMessageBox,
)

# ── Access / password helpers ─────────────────────────────────────────────────

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

    NOTE: The sub-modules have this logic INVERTED (a known bug in those files).
    We handle access here and patch around sub-module checks below.
    """
    first_run = _load_or_create_first_run()
    expiry    = _resolve_expiry(first_run)
    now       = datetime.now(timezone.utc)

    if now <= expiry:
        # Still within free trial — grant access directly, no password needed
        return True

    # Trial expired — require password
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


# ── Patch sub-module access checks so they never block or prompt ──────────────
#
# Each sub-module defines _enforce_startup_access().
# We monkey-patch it AFTER import so it always returns (True, None),
# preventing any second password prompt or silent failure.

def _patch_module_access(mod) -> None:
    """Replace the sub-module's access guard with a no-op that always allows."""
    def _always_allow():
        return True, None
    if hasattr(mod, "_enforce_startup_access"):
        mod._enforce_startup_access = _always_allow


# ── Individual window openers ─────────────────────────────────────────────────

def _open_window(module_name: str, title: str) -> object:
    """
    Import module_name, patch its access guard, instantiate MainWindow,
    show it and return it (caller must hold reference to keep it alive).
    """
    try:
        import importlib
        mod = importlib.import_module(module_name)
        _patch_module_access(mod)          # disable sub-module password prompt
        win = mod.MainWindow()
        win.setWindowTitle(f"Coil Helvix — {title}")
        win.show()
        return win
    except Exception as exc:
        QMessageBox.warning(
            None,
            f"{title} — Load Error",
            f"Could not open {module_name}.py:\n\n{exc}\n\n"
            f"Make sure {module_name}.py is in the same folder as main.py.",
        )
        return None


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Coil Helvix Drawing Suite")
    app.setOrganizationName("Coil Helvix")
    app.setFont(QFont("Segoe UI", 10))

    # ── One access check covers all three windows ─────────────────────────────
    if not _enforce_access():
        sys.exit(0)

    # ── Open all three windows — keep references so Python doesn't GC them ────
    windows = []

    for module_name, title in [
        ("frontview", "Front View"),
        ("sideview",  "Side View"),
        ("side_view",  "Header View"),
        ("topview",   "Top View"),
    ]:
        win = _open_window(module_name, title)
        if win is not None:
            windows.append(win)

    if not windows:
        QMessageBox.critical(
            None,
            "Nothing Loaded",
            "None of the view files could be opened.\n\n"
            "Make sure these files are in the same folder as main.py:\n"
            "  • frontview.py\n"
            "  • sideview.py\n"
            "  • side_view.py\n"
            "  • topview.py",
        )
        sys.exit(1)

    # All windows open — run event loop until all are closed
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
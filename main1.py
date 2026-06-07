"""
main.py — Coil Helvix Launcher (Debug Version)
"""
import sys
import os
import traceback
import hmac
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication, QInputDialog, QLineEdit, QMessageBox, QErrorMessage
)

# ====================== CONFIG ======================
ACCESS_WINDOW_DAYS = 30
DEFAULT_PASSWORD_SHA256 = hashlib.sha256("coilhelvix".encode("utf-8")).hexdigest()


def _access_state_path() -> Path:
    appdata = os.getenv("APPDATA") or str(Path.home() / ".coil_helvix")
    base_dir = Path(appdata) / "CoilHelvix"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / "access_state.json"


def _load_or_create_first_run():
    state_file = _access_state_path()
    now = datetime.now(timezone.utc)
    if not state_file.exists():
        state_file.write_text(json.dumps({"first_run_utc": now.isoformat()}, indent=2))
        return now
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        return datetime.fromisoformat(str(data.get("first_run_utc"))).replace(tzinfo=timezone.utc)
    except:
        state_file.write_text(json.dumps({"first_run_utc": now.isoformat()}, indent=2))
        return now


def _enforce_access():
    first_run = _load_or_create_first_run()
    expiry = first_run + timedelta(days=ACCESS_WINDOW_DAYS)
    if datetime.now(timezone.utc) <= expiry:
        return True

    password, ok = QInputDialog.getText(None, "Access Required", "Enter password:", QLineEdit.EchoMode.Password)
    if not ok:
        return False
    if not hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest().lower(),
                               DEFAULT_PASSWORD_SHA256.lower()):
        QMessageBox.critical(None, "Access Denied", "Invalid password!")
        return False
    return True


def _open_window(module_name: str, title: str):
    try:
        mod = __import__(module_name)
        # Patch access check if exists
        if hasattr(mod, "_enforce_startup_access"):
            mod._enforce_startup_access = lambda: (True, None)

        win = mod.MainWindow()
        win.setWindowTitle(f"Coil Helvix — {title}")
        win.show()
        return win
    except Exception as e:
        error_msg = f"Failed to load {module_name}.py\n\n{traceback.format_exc()}"
        print(error_msg)                    # Print to console
        QMessageBox.critical(None, f"Load Error - {title}", error_msg)
        return None


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Coil Helvix")

    if not _enforce_access():
        sys.exit(0)

    windows = []
    for module_name, title in [ ("side_view", "Side View"),
                               ("topview", "Side View")
                              ]:
        win = _open_window(module_name, title)
        if win:
            windows.append(win)

    if not windows:
        QMessageBox.critical(None, "Launch Failed", 
                           "None of the three view files could be opened.\n"
                           "Check the error messages above.")
    else:
        print(f"✅ Successfully opened {len(windows)} window(s)")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
# Coil Helvix Offline App (PyQt)

Desktop offline application to reproduce the shared technical drawing layout (TOP / FRONT / HEADER SIDE / RETURN END SIDE), with editable dimensions and print/export support.

## Features

- Parametric drawing that follows the uploaded layout style.
- Live dimension editing from the left control panel.
- Derived dimensions shown automatically:
  - `FL` (fin length)
  - `FH` (fin height)
- Print support using Qt print dialog.
- Export drawing to PNG.
- Export drawing to DXF/DFX for CAD use.

## Requirements

- Python 3.10+
- Windows/macOS/Linux desktop environment

## Install

```powershell
pip install -r requirements.txt
```

## Run

```powershell
python app.py
```

## Startup Access Protection

- On startup, the app asks for a password before opening the main window.
- Access expires after 10 days from first run unless a fixed expiry date is provided.
- Expired access message: `Software access expired. Contact administrator.`

### Configure password (recommended for production)

- Set SHA-256 password hash in environment variable `COIL_HELVIX_PASSWORD_SHA256`.
- Example hash generation:

```powershell
python -c "import hashlib; print(hashlib.sha256('your_password_here'.encode('utf-8')).hexdigest())"
```

### Configure fixed expiry date (optional)

- Set `COIL_HELVIX_EXPIRY_DATE` in format `YYYY-MM-DD`.
- If not set, expiry is `first_run + 10 days`.

### Data storage location

- Access state is stored in `%APPDATA%\CoilHelvix\access_state.json` (or `~/.coil_helvix/CoilHelvix/access_state.json` if `%APPDATA%` is unavailable).

## Notes

- The app is fully offline.
- The drawing is generated from dimensions, so you can tune values and immediately see updated geometry and dimension annotations.

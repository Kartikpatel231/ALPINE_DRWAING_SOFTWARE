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

## Notes

- The app is fully offline.
- The drawing is generated from dimensions, so you can tune values and immediately see updated geometry and dimension annotations.

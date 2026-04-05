# Coil Helvix Project Documentation

Generated on: 2026-04-02

## 1. Project Overview

Coil Helvix is an offline desktop engineering application built with PyQt6. It is used to generate and edit parametric coil drawings with the following views:

- TOP
- FRONT
- HEADER SIDE
- RETURN END SIDE

The application supports live dimension editing and drawing export workflows for both image and CAD usage.

## 2. Repository Structure

- app.py: Main application source code, UI, drawing engine, import/export, startup access control.
- README.md: Quick start, feature summary, and startup access notes.
- requirements.txt: Python dependencies.
- 90.dxf: Existing DXF sample asset in workspace.
- coil_drawing.dxf: Existing DXF output/sample file in workspace.
- scripts/generate_project_docs_pdf.py: Utility script to generate this documentation PDF.
- PROJECT_DOCUMENTATION.md: Source markdown for this documentation.
- PROJECT_DOCUMENTATION.pdf: Final generated PDF output.

## 3. Technology Stack

- Python 3.10+
- PyQt6 (UI, rendering, printing)
- ezdxf (DXF/DFX import and export)
- Standard library modules for data handling, security hashing, and file management

## 4. Core Architecture

The project is implemented as a single-file application centered around the classes below.

### 4.1 Access Control Layer

Startup protection is enforced before opening the main window.

- Access window duration is controlled by ACCESS_WINDOW_DAYS (currently 30 days).
- First run timestamp is persisted in application data storage.
- Optional fixed expiry can be supplied via environment variable.
- Password validation uses SHA-256 and constant-time comparison.

Primary functions:

- _access_state_path
- _load_or_create_first_run
- _resolve_expiry_datetime
- _is_password_valid
- _enforce_startup_access

### 4.2 Data Model

The CoilDimensions dataclass stores all editable and computed geometry values.

Responsibilities:

- Keep drawing input values in one structured model
- Provide derived properties (for example fin length, fin height, top lead span)
- Sanitize and clamp values to valid ranges
- Normalize text fields and connection side values

### 4.3 Rendering and Export Layer

CoilDrawingWidget handles drawing, zoom, pan, and export rendering.

Key responsibilities:

- Compute layout coordinates for multiple views
- Draw geometry, dimensions, labels, notes, and annotations
- Render into widget, printer, PNG image, and DXF adapter target

DxfPainterAdapter mimics key painter operations and emits DXF entities.

### 4.4 Application Window and UI Composition

MainWindow builds the left-side control panels and connects all user actions.

UI groups include:

- Order Details
- Main Specs (As Diagram)
- PITCH
- Plate / Overall
- First Bend
- Additional / Existing Inputs
- Derived
- Direct Dimension Edit

Action buttons include:

- Apply
- Reset
- Print
- Export PNG
- Import DFX/DXF
- Export DXF

## 5. Functional Workflows

### 5.1 Startup Flow

1. Application starts and access checks run.
2. Password dialog is displayed.
3. On valid access, main window is shown.
4. On invalid/expired access, app exits with error dialog.

### 5.2 Drawing Update Flow

1. User modifies input values in left panel controls.
2. Inputs are collected into CoilDimensions.
3. Values are sanitized and derived fields recomputed.
4. Drawing widget receives updated dimensions.
5. Canvas redraws with the new geometry and dimensions.

### 5.3 Export and Print Flow

- Print: Uses Qt printer dialog and renders the full drawing scene.
- PNG Export: Renders to high-resolution image and saves PNG.
- DXF Export: Uses DxfPainterAdapter and embeds dimension metadata for future re-import.

### 5.4 DXF Import Flow

- Attempts metadata-based reconstruction first.
- Falls back to parsing visible labels if metadata is missing.
- Synchronizes imported values back into UI controls.

## 6. Security and Access Configuration

### 6.1 Password Hash Variable

Environment variable:

- COIL_HELVIX_PASSWORD_SHA256

If not set, a default built-in hash is used.

### 6.2 Fixed Expiry Variable

Environment variable:

- COIL_HELVIX_EXPIRY_DATE in YYYY-MM-DD format

If not set, expiry is first run date plus configured access window days.

### 6.3 Access State Storage

Stored path:

- %APPDATA%/CoilHelvix/access_state.json

Fallback path if APPDATA is unavailable:

- ~/.coil_helvix/CoilHelvix/access_state.json

## 7. Build and Run Instructions

Install dependencies:

pip install -r requirements.txt

Run application:

python app.py

## 8. Dependency Summary

From requirements.txt:

- PyQt6>=6.7
- ezdxf>=1.3

## 9. Current Project Notes

- Application is offline-first and file-based.
- Drawing logic is heavily geometry-driven and deterministic from CoilDimensions.
- Most implementation is intentionally concentrated in app.py for ease of distribution.
- Existing workspace contains sample/output DXF artifacts.

## 10. Known Constraints

- Project is currently monolithic (single large source file), which can make long-term maintenance and testing harder.
- No automated test suite is currently present in the repository.
- Import quality depends on availability and consistency of DXF metadata or recognizable labels.

## 11. Suggested Next Improvements

- Split app.py into modules: access, model, rendering, UI, import/export.
- Add unit tests for CoilDimensions sanitization and derived formulas.
- Add regression image snapshots for rendering verification.
- Add CI checks for linting and syntax validation.

## 12. License and Distribution

No explicit license file was found in the current workspace snapshot.

If this project is shared externally, add a LICENSE file and versioning strategy.

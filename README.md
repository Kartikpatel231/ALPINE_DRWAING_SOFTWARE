# Helvix — Parametric Coil Drafting Software

> A desktop CAD application for generating **parametric engineering drawings** of heat-exchanger coils. Built with **Python**, **PySide6 (Qt)**, and **ezdxf**.

---

## Table of Contents

1. [Overview](#overview)
2. [Key Features](#key-features)
3. [Tech Stack](#tech-stack)
4. [Architecture & Project Structure](#architecture--project-structure)
5. [How It Works — End-to-End Flow](#how-it-works--end-to-end-flow)
6. [Engineering Views Generated](#engineering-views-generated)
7. [Input Parameters](#input-parameters)
8. [Screenshots / Output](#screenshots--output)
9. [Installation & Setup](#installation--setup)
10. [Running the Application](#running-the-application)
11. [Export Formats](#export-formats)
12. [Future Improvements](#future-improvements)

---

## Overview

**Helvix** automates the creation of multi-view engineering drawings for HVAC heat-exchanger coils. Instead of manually drafting each drawing in AutoCAD, an engineer enters coil specifications (fin length, tube diameter, rows, etc.) into a GUI, and Helvix instantly generates a **Third-Angle Projection** sheet with four orthographic views, dimensioning, notes, and a title block — ready to export as **DXF** (AutoCAD) or **PDF**.

### Problem It Solves

- Manual coil drawings take **hours** per specification change.
- Repetitive geometry (tubes, fins, bends) is error-prone when drawn by hand.
- Helvix reduces drawing time to **seconds** and eliminates human calculation errors.

---

## Key Features

| Feature | Description |
|---|---|
| **Parametric Input** | Change any parameter and regenerate the entire drawing instantly |
| **4 Orthographic Views** | Top, Front, Header Side, and Return End Side views in Third-Angle Projection |
| **Auto-Dimensioning** | All critical dimensions are automatically placed with proper extension lines and arrows |
| **Staggered Tube Grid** | Accurate tube-hole pattern with staggered rows (as used in real coils) |
| **Connection Pipes** | IN/OUT pipe stubs with fittings shown in the Top view (LHS/RHS selectable) |
| **Return Bend Arcs** | U-bend arcs between adjacent tube rows |
| **Notes & Title Block** | Manufacturing notes, tolerances, and company title block auto-populated |
| **DXF Export** | Industry-standard AutoCAD DXF (R2010) with proper layers |
| **PDF Export** | High-resolution PDF rendering via Qt's print engine |
| **Zoom & Pan** | Interactive canvas with mouse wheel zoom and click-drag panning |
| **Input Validation** | Parameter validation before drawing generation |

---

## Tech Stack

| Component | Technology |
|---|---|
| **Language** | Python 3.10+ |
| **GUI Framework** | PySide6 (Qt 6) |
| **DXF Generation** | ezdxf |
| **Numerical Computation** | NumPy |
| **Rendering** | Qt QPainter (2D vector rendering) |
| **PDF Export** | Qt QPrinter |

---

## Architecture & Project Structure

```
helvix_Cad/
├── README.md
├── requirements.txt              # Python dependencies
│
├── coil_cad/                     # Main application package
│   ├── main.py                   # Entry point — launches Qt application
│   │
│   ├── core/                     # Business logic (no UI code)
│   │   ├── parameters.py         # CoilParameters dataclass + validation
│   │   ├── geometry_engine.py    # Pure geometry computation for all 4 views
│   │   ├── dimension_engine.py   # Dimension annotation coordinates
│   │   └── layout_engine.py      # Arranges views into a drawing sheet
│   │
│   ├── rendering/                # Qt-based rendering
│   │   └── qt_renderer.py        # Draws geometry & dimensions via QPainter
│   │
│   ├── export/                   # File export modules
│   │   ├── export_dxf.py         # DXF export via ezdxf (AutoCAD compatible)
│   │   └── export_pdf.py         # PDF export via Qt QPrinter
│   │
│   ├── ui/                       # User interface widgets
│   │   ├── main_window.py        # Main application window
│   │   ├── parameter_panel.py    # Left sidebar — parameter input form
│   │   └── drawing_view.py       # Zoomable/pannable drawing canvas
│   │
│   ├── test_layout.py            # Quick test script
│   ├── coil_output.dxf           # Sample DXF output
│   └── test_output.dxf           # Test DXF output
│
├── read_pdf.py                   # Utility: extract text from PDF templates
└── read_pdf2.py                  # Utility: extract drawing info from PDFs
```

### Design Principles

- **Separation of Concerns** — Core geometry/dimension logic is completely independent of UI and rendering.
- **Renderer-Agnostic** — Geometry and dimension engines output plain coordinate data (dicts, tuples). Any renderer (Qt, SVG, DXF) can consume them.
- **Dataclass-Driven** — All coil parameters are encapsulated in a single `CoilParameters` dataclass with computed properties.

---

## How It Works — End-to-End Flow

```
User Input (GUI)
      │
      ▼
┌─────────────────────┐
│  CoilParameters      │   ← Validated dataclass with all coil specs
│  (parameters.py)     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Geometry Engine     │   ← Computes coordinates for all 4 views
│  (geometry_engine.py)│      (rects, tubes, arcs, pipes, etc.)
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Dimension Engine    │   ← Generates dimension lines, extension lines,
│  (dimension_engine.py)│     arrowheads, and text positions
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Layout Engine       │   ← Arranges 4 views + notes + title block
│  (layout_engine.py)  │      into a drawing sheet with offsets
└──────────┬──────────┘
           │
     ┌─────┴──────┐
     ▼            ▼
┌──────────┐ ┌──────────┐
│ Qt Canvas │ │ DXF/PDF  │
│ (render)  │ │ (export) │
└──────────┘ └──────────┘
```

### Step-by-Step:

1. **Parameter Collection** — The `ParameterPanel` (left sidebar) collects inputs like Fin Length, Tube OD, Rows, etc.
2. **Validation** — `validate_parameters()` checks for invalid/impossible values.
3. **Geometry Generation** — Four functions compute all geometry:
   - `generate_front_geometry()` — Casing rectangle, fin rectangle, representative fin lines
   - `generate_top_geometry()` — Plan view with tube rows, connection pipes, return bends
   - `generate_header_geometry()` — Header plate with staggered tube-hole circles
   - `generate_return_geometry()` — Return-end plate with tube-hole circles
4. **Dimension Generation** — Four functions add engineering dimensions (FL, FH, casing width, depths, pitches, etc.)
5. **Layout Assembly** — Views are positioned in Third-Angle Projection arrangement with gaps, and notes + title block are placed.
6. **Rendering** — `QtRenderer` draws everything on the canvas using `QPainter`.
7. **Export** — User can export the same layout data to DXF (via `ezdxf`) or PDF (via `QPrinter`).

---

## Engineering Views Generated

The drawing follows **Third-Angle Projection** standard:

```
                    ┌──────────────┐
                    │   TOP VIEW   │
                    │  (Plan View) │
                    └──────┬───────┘
                           │
┌──────────────┐   ┌──────────────┐   ┌──────────────────┐
│ HEADER SIDE  │   │  FRONT VIEW  │   │ RETURN END SIDE  │
│ (Tube Holes) │   │  (Elevation) │   │   (U-Bends)      │
└──────────────┘   └──────────────┘   └──────────────────┘
                                       ┌──────────────────┐
     NOTES                             │   TITLE BLOCK    │
                                       └──────────────────┘
```

### View Details

| View | Shows | Key Elements |
|---|---|---|
| **Front View** | Coil from the front | Casing outline, fin area, representative fin lines, FPI label |
| **Top View** | Coil from above (plan) | Tube row pairs, connection pipes (IN/OUT), return bend arcs, zone dividers |
| **Header Side** | Header plate face | Staggered tube-hole circles, plate offset lines |
| **Return End Side** | Return bend plate | Tube-hole circles, plate offset lines |

---

## Input Parameters

| Parameter | Default | Description |
|---|---|---|
| Fin Length (FL) | 1330 mm | Length of the fin pack |
| Fin Height (FH) | 1400 mm | Height of the fin pack |
| Tube OD | 5/8" (15.875 mm) | Outer diameter of copper tubes |
| No. of Rows (NR) | 6 | Number of tube rows (depth direction) |
| Tubes per Row (TPR) | 35 | Tubes in each row (height direction) |
| Fins per Inch (FPI) | 13 | Fin density |
| No. of Circuits (NC) | 35 | Refrigerant circuits |
| Top Plate | 65 mm | Distance from FH top edge to first tube center |
| Bottom Plate | 35 mm | Distance from FH bottom edge to last tube center |
| Casing Left | 35 mm | Casing extension on header side |
| Casing Right | 65 mm | Casing extension on return side |
| Casing Top/Bottom | 15 mm | Casing extension above/below fin area |
| Casing Thickness | 1.5 mm | Sheet metal thickness (GI) |
| Coil Depth | 207.6 mm | Fin coil pack depth |
| Header Depth | 320 mm | Header plate assembly width |
| Return Depth | 320 mm | Return end assembly width |
| Connection Side | LHS | Pipe connection side (LHS or RHS) |

### Computed Properties (Auto-Calculated)

| Property | Formula |
|---|---|
| Casing Width | `casing_left + fin_length + casing_right` |
| Casing Height | `casing_bottom + fin_height + casing_top` |
| Vertical Pitch | `(FH - top_plate - bottom_plate) / (TPR - 1)` |
| Row Pitch | `coil_depth / no_of_rows` |
| Drawing Title | `5/8"x1330FLx1400FHx6Rx35TPRx13FPIx35NC - LHS` |

---

## Screenshots / Output

### Drawing Title Format
```
5/8"x1330FLx1400FHx6Rx35TPRx13FPIx35NC - LHS
```

### DXF Layer Structure

| Layer | Color | Content |
|---|---|---|
| CASING | Red | Outer casing rectangles |
| COIL | White | Fin area rectangles |
| TUBES | Green | Tube-hole circles |
| BENDS | Magenta | Return bend arcs |
| FINS | Dark Grey | Fin lines, tube row lines |
| PLATES | Blue | Plate offset lines |
| DIMS | Cyan | Dimension lines, arrows, text |
| LABELS | Yellow | View labels, pipe labels |
| NOTES | Yellow | Manufacturing notes |
| PIPES | White | Connection pipe lines/circles |
| TITLEBLOCK | White | Title block border and text |

---

## Installation & Setup

### Prerequisites

- **Python 3.10** or higher
- **pip** package manager

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/your-username/helvix_Cad.git
cd helvix_Cad

# 2. Create a virtual environment (recommended)
python -m venv .venv

# 3. Activate the virtual environment
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt
```

### Dependencies

| Package | Version | Purpose |
|---|---|---|
| PySide6 | >= 6.6 | Qt 6 GUI framework |
| ezdxf | >= 1.1 | DXF file read/write |
| numpy | >= 1.26 | Numerical computation |

---

## Running the Application

```bash
# Navigate to the coil_cad directory
cd coil_cad

# Run the application
python main.py
```

### Usage

1. The application opens with a **default drawing** already generated.
2. Modify parameters in the **left sidebar** (Fin Length, Rows, Tube OD, etc.).
3. Click **"Generate Drawing"** to update the canvas.
4. Use **mouse wheel** to zoom in/out and **click-drag** to pan.
5. Click **"Export DXF"** to save as AutoCAD-compatible DXF file.
6. Click **"Export PDF"** to save as a high-resolution PDF.

---

## Export Formats

### DXF (AutoCAD)
- Format: **DXF R2010** (compatible with AutoCAD 2010+)
- Proper layer separation for easy editing in AutoCAD
- All geometry, dimensions, notes, and title block included
- Generated via `ezdxf` library

### PDF
- High-resolution vector PDF
- Auto-calculated page size based on drawing extents
- Generated via Qt's `QPrinter` engine
- Suitable for printing and sharing

---

## Future Improvements

- [ ] Add more tube OD sizes and coil configurations
- [ ] Support for multi-circuit routing visualization
- [ ] Undo/Redo for parameter changes
- [ ] Template save/load (JSON parameter presets)
- [ ] SVG export option
- [ ] Dark mode UI theme
- [ ] Unit tests for geometry and dimension engines
- [ ] Packaging as standalone `.exe` via PyInstaller
- [ ] Web-based version using Flask + SVG rendering

---

## Author

Developed by **Archit** as a parametric engineering CAD tool for the HVAC coil manufacturing industry.

---

## License

This project is proprietary. All rights reserved.

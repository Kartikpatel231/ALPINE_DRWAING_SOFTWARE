"""Export drawing to AutoCAD-compatible DXF via ezdxf."""

from __future__ import annotations
import math
from typing import Any

import ezdxf
from ezdxf.enums import TextEntityAlignment

from core.dimension_engine import arrowhead_lines
from core.layout_engine import DrawingLayout


def export_dxf(
    layout: DrawingLayout,
    filepath: str = "coil_output.dxf",
) -> str:
    """Write geometry to a DXF R2010 file.  Returns the file path written."""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # ── Layer setup ───────────────────────────────────────────────────────
    doc.layers.add("CASING", color=1)      # red
    doc.layers.add("COIL", color=7)        # white / black
    doc.layers.add("TUBES", color=3)       # green
    doc.layers.add("BENDS", color=6)       # magenta
    doc.layers.add("FINS", color=8)        # dark grey
    doc.layers.add("PLATES", color=5)      # blue
    doc.layers.add("DIMS", color=4)        # cyan
    doc.layers.add("LABELS", color=2)      # yellow
    doc.layers.add("NOTES", color=2)       # yellow
    doc.layers.add("PIPES", color=7)       # white
    doc.layers.add("TITLEBLOCK", color=7)  # white

    # ── Draw each view ────────────────────────────────────────────────────
    for view in layout.views:
        ox = view.offset_x
        oy = view.offset_y
        geo = view.geometry

        def t(x: float, y: float):
            return (x + ox, y + oy)

        # Outer casing rect
        if "outer_rect" in geo:
            x, y, w, h = geo["outer_rect"]
            _add_rect(msp, t(x, y), w, h, "CASING")

        # Fin rect
        if "fin_rect" in geo:
            x, y, w, h = geo["fin_rect"]
            _add_rect(msp, t(x, y), w, h, "COIL")

        if "header_block_rect" in geo:
            x, y, w, h = geo["header_block_rect"]
            _add_rect(msp, t(x, y), w, h, "CASING")

        # Inner tube-grid rect
        if "inner_rect" in geo:
            x, y, w, h = geo["inner_rect"]
            _add_rect(msp, t(x, y), w, h, "COIL")

        # Plate offset lines
        for seg in geo.get("offset_lines", []):
            x1, y1, x2, y2 = seg
            msp.add_line(t(x1, y1), t(x2, y2), dxfattribs={"layer": "PLATES"})

        # Fin lines
        for seg in geo.get("fin_lines", []):
            x1, y1, x2, y2 = seg
            msp.add_line(t(x1, y1), t(x2, y2), dxfattribs={"layer": "FINS"})

        # Tube lines (top view)
        for seg in geo.get("tube_lines", []):
            x1, y1, x2, y2 = seg
            msp.add_line(t(x1, y1), t(x2, y2), dxfattribs={"layer": "FINS"})

        # Zone lines
        for seg in geo.get("zone_lines", []):
            x1, y1, x2, y2 = seg
            msp.add_line(t(x1, y1), t(x2, y2), dxfattribs={"layer": "PLATES"})

        # Tubes
        for cx, cy, r in geo.get("tubes", []):
            msp.add_circle(t(cx, cy), r, dxfattribs={"layer": "TUBES"})

        # Bend arcs
        for arc in geo.get("bend_arcs", []):
            cx, cy, r, start, span = arc
            end = start + span
            msp.add_arc(
                t(cx, cy), r,
                start_angle=start,
                end_angle=end,
                dxfattribs={"layer": "BENDS"},
            )

        # Connection pipes
        for pipe in geo.get("connection_pipes", []):
            x1, y1, x2, y2 = pipe["line"]
            msp.add_line(t(x1, y1), t(x2, y2), dxfattribs={"layer": "PIPES"})
            lx, ly = pipe["label_pos"]
            msp.add_text(
                pipe["label"], height=4.0,
                dxfattribs={"layer": "LABELS"},
            ).set_placement(t(lx, ly), align=TextEntityAlignment.MIDDLE_CENTER)

        # Pipe circles (fittings)
        for cx, cy, r in geo.get("pipe_circles", []):
            msp.add_circle(t(cx, cy), r, dxfattribs={"layer": "PIPES"})

        # Pipe stubs
        for seg in geo.get("pipe_stubs", []):
            x1, y1, x2, y2 = seg
            msp.add_line(t(x1, y1), t(x2, y2), dxfattribs={"layer": "PIPES"})

        # Return assembly rect
        if "return_rect" in geo:
            x, y, w, h = geo["return_rect"]
            _add_rect(msp, t(x, y), w, h, "CASING")

        # Top-right box
        if "top_right_box" in geo:
            x, y, w, h = geo["top_right_box"]
            _add_rect(msp, t(x, y), w, h, "CASING")

        # Dimensions
        for dim in view.dimensions:
            for seg in dim.get("lines", []):
                x1, y1, x2, y2 = seg
                msp.add_line(t(x1, y1), t(x2, y2), dxfattribs={"layer": "DIMS"})
            for tip_x, tip_y, angle in dim.get("arrows", []):
                for seg in arrowhead_lines(tip_x, tip_y, angle):
                    ax1, ay1, ax2, ay2 = seg
                    msp.add_line(t(ax1, ay1), t(ax2, ay2),
                                 dxfattribs={"layer": "DIMS"})
            for tx, ty, text, angle in dim.get("texts", []):
                msp.add_text(
                    text, height=3.0,
                    dxfattribs={"layer": "DIMS", "rotation": angle},
                ).set_placement(t(tx, ty), align=TextEntityAlignment.MIDDLE_CENTER)

        # View label
        rect = geo.get("outer_rect", (0, 0, 0, 0))
        label_x = ox + rect[0] + rect[2] / 2
        label_y = oy + rect[1] + rect[3] + 15
        msp.add_text(
            view.label, height=5.0,
            dxfattribs={"layer": "LABELS"},
        ).set_placement((label_x, label_y), align=TextEntityAlignment.MIDDLE_CENTER)

    # ── Notes ─────────────────────────────────────────────────────────────
    nx, ny = layout.notes_offset
    for i, line in enumerate(layout.notes.get("notes_lines", [])):
        h = 4.0 if i == 0 else 3.0
        msp.add_text(
            line, height=h,
            dxfattribs={"layer": "NOTES"},
        ).set_placement((nx, ny + i * 8), align=TextEntityAlignment.LEFT)

    footer_y = ny + len(layout.notes.get("notes_lines", [])) * 8 + 10
    for i, line in enumerate(layout.notes.get("footer_lines", [])):
        msp.add_text(
            line, height=2.5,
            dxfattribs={"layer": "NOTES"},
        ).set_placement((nx, footer_y + i * 6), align=TextEntityAlignment.LEFT)

    # ── Title block ───────────────────────────────────────────────────────
    tx, ty = layout.title_block_offset
    tb = layout.title_block
    tb_w, tb_h = 350, 80
    _add_rect(msp, (tx, ty), tb_w, tb_h, "TITLEBLOCK")

    # Dividers
    msp.add_line((tx, ty + 20), (tx + tb_w, ty + 20), dxfattribs={"layer": "TITLEBLOCK"})
    msp.add_line((tx, ty + 40), (tx + tb_w, ty + 40), dxfattribs={"layer": "TITLEBLOCK"})
    mid_x = tx + tb_w * 0.35
    msp.add_line((mid_x, ty), (mid_x, ty + 40), dxfattribs={"layer": "TITLEBLOCK"})

    # Company name
    msp.add_text(
        tb.get("company_name", ""), height=5.0,
        dxfattribs={"layer": "TITLEBLOCK"},
    ).set_placement((tx + tb_w * 0.175, ty + 10), align=TextEntityAlignment.MIDDLE_CENTER)

    # Drawing title
    dtx = mid_x + (tb_w * 0.65) / 2
    msp.add_text(
        "DRAWING TITLE:", height=2.5,
        dxfattribs={"layer": "TITLEBLOCK"},
    ).set_placement((dtx, ty + 5), align=TextEntityAlignment.MIDDLE_CENTER)
    msp.add_text(
        tb.get("drawing_title", ""), height=3.0,
        dxfattribs={"layer": "TITLEBLOCK"},
    ).set_placement((dtx, ty + 15), align=TextEntityAlignment.MIDDLE_CENTER)

    doc.saveas(filepath)
    return filepath


def _add_rect(msp, origin, w, h, layer):
    x, y = origin
    pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]
    msp.add_lwpolyline(pts, dxfattribs={"layer": layer})

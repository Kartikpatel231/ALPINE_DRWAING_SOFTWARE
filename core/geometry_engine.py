"""Pure geometry computation for all four engineering views.

Views (Third Angle Projection):
  1. FRONT      — coil from front  (casing_width x casing_height)
  2. HEADER SIDE — header plate with tube holes (header_depth x casing_height)
  3. RETURN END SIDE — return bends  (return_depth x casing_height)
  4. TOP         — plan view  (extended_width x total_depth)

No drawing / rendering code here — only coordinate data.
"""
from __future__ import annotations
import math
from typing import Any
from core.parameters import CoilParameters


# ══════════════════════════════════════════════════════════════════════════════
#  FRONT VIEW
# ══════════════════════════════════════════════════════════════════════════════

def generate_front_geometry(params: CoilParameters) -> dict[str, Any]:
    """Front view — casing rect, fin rect, representative fins, FPI label.

    Origin (0,0) at bottom-left of casing.
    """
    CW = params.casing_width
    CH = params.casing_height
    cl = params.casing_left
    cr = params.casing_right
    ct = params.casing_top
    cb = params.casing_bottom
    FL = params.fin_length
    FH = params.fin_height

    outer_rect = (0.0, 0.0, CW, CH)
    fin_rect = (cl, cb, FL, FH)

    # Representative fin lines (horizontal, inside fin rect)
    fin_lines: list[tuple[float, float, float, float]] = []
    fin_spacing = 25.4 / params.fpi
    n_fins = int(FH / fin_spacing)
    step = max(1, n_fins // 40)
    for i in range(0, n_fins, step):
        y = cb + i * fin_spacing
        if y < cb + FH:
            fin_lines.append((cl, y, cl + FL, y))

    return {
        "view_type": "FRONT",
        "outer_rect": outer_rect,
        "fin_rect": fin_rect,
        "fin_lines": fin_lines,
        "params": params,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  HEADER SIDE — tube-hole plate
# ══════════════════════════════════════════════════════════════════════════════

def generate_header_geometry(params: CoilParameters) -> dict[str, Any]:
    """Header plate view — staggered tube holes.

    Origin (0,0) at bottom-left.  Width = header_depth, Height = casing_height.
    """
    HD = params.header_depth
    TP = params.top_plate
    BP = params.bottom_plate
    NR = params.no_of_rows
    TPR = params.tubes_per_row
    VP = params.vertical_pitch
    RP = params.row_pitch
    tube_r = params.tube_diameter / 2.0

    # Per side-view rule sheet:
    # height = (TPR x Vertical Pitch) + Top Plate + Bottom Plate
    CH = (TPR * VP) + TP + BP

    outer_rect = (0.0, 0.0, HD, CH)

    # Plate offset lines (bottom-plate line and top-plate line inside casing)
    bp_y = BP
    tp_y = CH - TP
    offset_lines = [
        (0.0, bp_y, HD, bp_y),
        (0.0, tp_y, HD, tp_y),
    ]

    # Step 4: inner grid box (W = HP * rows, H = TPR * VP), centered in X,
    # and based from bottom offset line in Y.
    grid_w = RP * NR
    grid_h = TPR * VP
    grid_x = (HD - grid_w) / 2.0
    grid_y = bp_y
    inner_rect = (grid_x, grid_y, grid_w, grid_h)

    # Steps 5-8: staggered rows with first center at (HP/2, VP/4),
    # then alternating +VP/2 and -VP/2 for subsequent rows.
    tubes: list[tuple[float, float, float]] = []
    for row in range(NR):
        cx = grid_x + RP / 2.0 + row * RP
        y_start = grid_y + (VP / 4.0 if row % 2 == 0 else 3.0 * VP / 4.0)
        for t in range(TPR):
            cy = y_start + t * VP
            tubes.append((cx, cy, tube_r))

    return {
        "view_type": "HEADER_SIDE",
        "outer_rect": outer_rect,
        "inner_rect": inner_rect,
        "offset_lines": offset_lines,
        "tubes": tubes,
        "params": params,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  RETURN END SIDE
# ══════════════════════════════════════════════════════════════════════════════

def generate_return_geometry(params: CoilParameters) -> dict[str, Any]:
    """Return-end view — tube ends and U-bends.

    Origin (0,0) at bottom-left.  Width = return_depth, Height = casing_height.
    """
    RD = params.return_depth
    TP = params.top_plate
    BP = params.bottom_plate
    NR = params.no_of_rows
    TPR = params.tubes_per_row
    VP = params.vertical_pitch
    RP = params.row_pitch
    tube_r = params.tube_diameter / 2.0

    # Mirror of left side view with same side-view height rule.
    CH = (TPR * VP) + TP + BP

    outer_rect = (0.0, 0.0, RD, CH)

    bp_y = BP
    tp_y = CH - TP
    offset_lines = [
        (0.0, bp_y, RD, bp_y),
        (0.0, tp_y, RD, tp_y),
    ]

    grid_w = RP * NR
    grid_h = TPR * VP
    grid_x = (RD - grid_w) / 2.0
    grid_y = bp_y
    inner_rect = (grid_x, grid_y, grid_w, grid_h)

    tubes: list[tuple[float, float, float]] = []
    for row in range(NR):
        # Mirror image of left-view row progression.
        cx = grid_x + grid_w - (RP / 2.0 + row * RP)
        y_start = grid_y + (VP / 4.0 if row % 2 == 0 else 3.0 * VP / 4.0)
        for t in range(TPR):
            cy = y_start + t * VP
            tubes.append((cx, cy, tube_r))

    return {
        "view_type": "RETURN_END",
        "outer_rect": outer_rect,
        "inner_rect": inner_rect,
        "offset_lines": offset_lines,
        "tubes": tubes,
        "params": params,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  TOP VIEW
# ══════════════════════════════════════════════════════════════════════════════

def generate_top_geometry(params: CoilParameters) -> dict[str, Any]:
    """Top / plan view — looking down.

    Origin (0,0) at top-left of casing.
    X = length direction (casing_width = cl + FL + cr).
    Y = depth direction  (total = header_depth = return_depth).

    The coil / fin pack (coil_depth=207.6) is centred in Y within the
    header/return depth (320).  Margin each side = (HD - CD) / 2 = 56.2.

        Extensions beyond the casing are parameter driven.
    """
    CW = params.casing_width              # 1430
    cl = params.casing_left               # 35
    cr = params.casing_right              # 65
    FL = params.fin_length                # 1330
    HD = params.header_depth              # 320  (total Y span)
    CD = params.coil_depth                # 207.6
    RD = params.return_depth              # 320
    NR = params.no_of_rows                # 6
    RP = params.row_pitch                 # 34.6
    tube_r = params.tube_diameter / 2.0   # ~7.9

    margin = (HD - CD) / 2.0              # 56.2
    pipe_ext = params.connection_extension
    pipe_gap = params.connection_vertical_gap
    header_block_len = min(params.top_header_block_length, CW)
    return_ext = params.top_return_extension
    top_right_step = params.top_right_step
    fit_outer_off = params.top_pipe_fitting_outer_offset
    fit_inner_off = params.top_pipe_fitting_inner_offset
    stub_center_off = params.top_pipe_stub_center_offset
    stub_spacing = params.top_pipe_stub_spacing

    # ── Main casing rectangle (visible from top) ─────────────────────────
    outer_rect = (0.0, 0.0, CW, HD)

    # ── Left header block feature (as in template) ───────────────────────
    header_block_rect = (0.0, margin, min(header_block_len, CW), CD)

    # ── Fin / coil zone (centred in Y) ───────────────────────────────────
    fin_rect = (cl, margin, FL, CD)

    # ── Zone divider lines (top & bottom of coil zone) ───────────────────
    zone_lines: list[tuple[float, float, float, float]] = [
        (header_block_len, margin, CW, margin),             # upper coil boundary
        (header_block_len, margin + CD, CW, margin + CD),   # lower coil boundary
    ]

    # ── Tube row lines (pairs: top/bottom of each tube) ──────────────────
    tube_lines: list[tuple[float, float, float, float]] = []
    for row in range(NR):
        yc = margin + RP / 2.0 + row * RP
        tube_lines.append((header_block_len, yc - tube_r, CW, yc - tube_r))  # tube top
        tube_lines.append((header_block_len, yc + tube_r, CW, yc + tube_r))  # tube bottom

    # ── Connection pipe stubs (LHS / RHS) ────────────────────────────────
    pipe_r     = tube_r    # pipe fitting circle radius
    y_centre   = HD / 2.0
    pipe_y_in  = y_centre - pipe_gap / 2.0
    pipe_y_out = y_centre + pipe_gap / 2.0

    connection_pipes: list[dict] = []
    pipe_circles: list[tuple[float, float, float]] = []
    pipe_stubs: list[tuple[float, float, float, float]] = []

    if params.connection_side == "LHS":
        # --- IN pipe ---
        connection_pipes.append({
            "line": (-pipe_ext, pipe_y_in, header_block_len, pipe_y_in),
            "label": "IN", "label_pos": (-pipe_ext - 20, pipe_y_in),
        })
        pipe_circles.append((-pipe_ext + fit_outer_off, pipe_y_in, pipe_r))
        pipe_circles.append((header_block_len - fit_inner_off, pipe_y_in, pipe_r))
        pipe_stubs.append((-pipe_ext + stub_center_off - stub_spacing / 2.0, pipe_y_in - pipe_r,
                           -pipe_ext + stub_center_off - stub_spacing / 2.0, pipe_y_in + pipe_r))
        pipe_stubs.append((-pipe_ext + stub_center_off + stub_spacing / 2.0, pipe_y_in - pipe_r,
                           -pipe_ext + stub_center_off + stub_spacing / 2.0, pipe_y_in + pipe_r))
        # --- OUT pipe ---
        connection_pipes.append({
            "line": (-pipe_ext, pipe_y_out, header_block_len, pipe_y_out),
            "label": "OUT", "label_pos": (-pipe_ext - 25, pipe_y_out),
        })
        pipe_circles.append((-pipe_ext + fit_outer_off, pipe_y_out, pipe_r))
        pipe_circles.append((header_block_len - fit_inner_off, pipe_y_out, pipe_r))
        pipe_stubs.append((-pipe_ext + stub_center_off - stub_spacing / 2.0, pipe_y_out - pipe_r,
                           -pipe_ext + stub_center_off - stub_spacing / 2.0, pipe_y_out + pipe_r))
        pipe_stubs.append((-pipe_ext + stub_center_off + stub_spacing / 2.0, pipe_y_out - pipe_r,
                           -pipe_ext + stub_center_off + stub_spacing / 2.0, pipe_y_out + pipe_r))
    else:   # RHS
        connection_pipes.append({
            "line": (CW - header_block_len, pipe_y_in, CW + pipe_ext, pipe_y_in),
            "label": "IN", "label_pos": (CW + pipe_ext + 15, pipe_y_in),
        })
        pipe_circles.append((CW + pipe_ext - fit_outer_off, pipe_y_in, pipe_r))
        pipe_circles.append((CW - header_block_len + fit_inner_off, pipe_y_in, pipe_r))
        connection_pipes.append({
            "line": (CW - header_block_len, pipe_y_out, CW + pipe_ext, pipe_y_out),
            "label": "OUT", "label_pos": (CW + pipe_ext + 15, pipe_y_out),
        })
        pipe_circles.append((CW + pipe_ext - fit_outer_off, pipe_y_out, pipe_r))
        pipe_circles.append((CW - header_block_len + fit_inner_off, pipe_y_out, pipe_r))

    # ── Return-end assembly (RIGHT side) ─────────────────────────────────
    # Return assembly box (spans coil zone height)
    return_rect = (CW, margin, return_ext, CD)

    # Return bend arcs – semicircles opening to the RIGHT at x = CW
    bend_arcs: list[tuple[float, float, float, float, float]] = []
    for row in range(0, NR - 1, 2):
        y1 = margin + RP / 2.0 + row * RP
        y2 = margin + RP / 2.0 + (row + 1) * RP
        mid_y = (y1 + y2) / 2.0
        r = (y2 - y1) / 2.0
        bend_arcs.append((CW + cr, mid_y, r, -90.0, 180.0))

    # ── Small box at top-right corner (12 mm offset feature) ─────────────
    top_right_box = (CW, 0.0, top_right_step, margin)  # small casing extension

    # Convenience values stored for the dimension engine
    total_width = pipe_ext + CW + return_ext   # 1745

    return {
        "view_type": "TOP",
        "outer_rect": outer_rect,
        "header_block_rect": header_block_rect,
        "fin_rect": fin_rect,
        "zone_lines": zone_lines,
        "tube_lines": tube_lines,
        "connection_pipes": connection_pipes,
        "pipe_circles": pipe_circles,
        "pipe_stubs": pipe_stubs,
        "bend_arcs": bend_arcs,
        "return_rect": return_rect,
        "top_right_box": top_right_box,
        "pipe_ext": pipe_ext,
        "return_ext": return_ext,
        "margin": margin,
        "total_width": total_width,
        "header_block_len": header_block_len,
        "pipe_gap": pipe_gap,
        "top_right_step": top_right_step,
        "params": params,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  NOTES & TITLE BLOCK
# ══════════════════════════════════════════════════════════════════════════════

def generate_notes(params: CoilParameters) -> dict[str, Any]:
    return {
        "notes_lines": [
            "NOTE:",
            f"1. FIN MATERIAL SHOULD BE {params.fin_material.upper()} "
            f"({params.fin_thickness}MM THICKNESS) & WITHOUT ANY COATING.",
            f"2. CASING MATERIAL SHOULD BE G.I. - {params.casing_thickness}MM THICKNESS.",
            f"3. {params.tube_od_inch}\" COPPER TUBE WALL THICKNESS SHOULD BE "
            f"{params.tube_wall_thickness} MM.",
        ],
        "footer_lines": [
            "ALL DIMENSIONS ARE IN MM,",
            "UNLESS OTHERWISE SPECIFIED.",
            "GENERAL TOLERANCE : \u00b12MM",
            "THIRD ANGLE PROJECTION",
        ],
    }


def generate_title_block(params: CoilParameters) -> dict[str, Any]:
    return {
        "company_name": "alpine coils",
        "company_sub": "industry l.l.c",
        "company_tag": "air cooling experts",
        "drawing_title": params.drawing_title,
        "scale": "NTS",
        "qty": "1 NO.",
    }

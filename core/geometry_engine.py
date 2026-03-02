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
    X = length direction  (casing_width = cl + FL + cr).
    Y = depth direction   (total = header_depth).

    Coil pack (coil_depth) is centred in Y within header_depth.
    Margin each side = (HD - CD) / 2.

    Geometry matches reference template:
      - Left:  pipe connector assembly (body block + open port circle)
      - Centre: tube row pairs (top/bottom edge lines + centre-line)
      - Right: U-bend coil-spring spirals (concentric arcs)
      - Dimensions: 350/170/180 top, 56.2/320 right, 35/FL/65/1430/1575/1745 bottom
    """
    CW   = params.casing_width              # 1430
    cl   = params.casing_left               # 35
    cr   = params.casing_right              # 65
    FL   = params.fin_length                # 1330
    HD   = params.header_depth              # 320
    CD   = params.coil_depth                # 207.6
    NR   = params.no_of_rows                # 6
    RP   = params.row_pitch                 # 34.6
    tube_r = params.tube_diameter / 2.0     # ~7.9

    margin           = (HD - CD) / 2.0             # 56.2
    pipe_ext         = params.connection_extension  # 170
    pipe_gap         = params.connection_vertical_gap  # 75
    header_block_len = min(params.top_header_block_length, CW)  # 180
    return_ext       = params.top_return_extension  # 145
    top_right_step   = params.top_right_step        # 12
    # Pipe connector layout params
    fit_outer_off    = params.top_pipe_fitting_outer_offset   # open-circle from pipe tip
    fit_inner_off    = params.top_pipe_fitting_inner_offset   # inner circle from header block
    stub_center_off  = params.top_pipe_stub_center_offset     # body centre from pipe tip
    stub_spacing     = params.top_pipe_stub_spacing           # body half-width

    # ── Main casing rectangle ─────────────────────────────────────────────
    outer_rect = (0.0, 0.0, CW, HD)

    # ── Left header block rect (the vertical divider feature) ─────────────
    header_block_rect = (0.0, margin, header_block_len, CD)

    # ── Fin / coil zone ───────────────────────────────────────────────────
    fin_rect = (cl, margin, FL, CD)

    # ── Zone boundary lines (dash-dot, top & bottom of coil pack) ─────────
    zone_lines: list[tuple[float, float, float, float]] = [
        (header_block_len, margin,      CW, margin),
        (header_block_len, margin + CD, CW, margin + CD),
    ]

    # ── Tube run lines (one red dashed line per row) ──────────────────────
    tube_lines: list[tuple[float, float, float, float]] = []
    # Keep helper center lines empty for TOP (not shown in reference)
    tube_center_lines: list[tuple[float, float, float, float]] = []
    for row in range(NR):
        yc = margin + RP / 2.0 + row * RP
        tube_lines.append((header_block_len, yc, CW, yc))

    # ── Pipe connector assembly ───────────────────────────────────────────
    # Geometry per pipe (IN and OUT):
    #   pipe line: from pipe_tip to casing
    #   body rect: centred at stub_center_off from pipe tip, half-width=stub_spacing
    #   body stubs: two vertical lines at body left/right edges  (the bracket detail)
    #   center dot: small filled circle at body centre
    #   open circle: port fitting circle at fit_outer_off from pipe tip
    #   inner circle: small circle near casing at fit_inner_off from header_block_len
    y_centre   = HD / 2.0
    pipe_y_in  = y_centre - pipe_gap / 2.0
    pipe_y_out = y_centre + pipe_gap / 2.0
    body_h     = pipe_gap * 0.28   # body height (fraction of pipe gap)

    connection_pipes: list[dict] = []
    pipe_circles:     list[tuple] = []   # open port circles
    pipe_stubs:       list[tuple] = []   # body edge vertical lines
    pipe_bodies:      list[tuple] = []   # (x, y, w, h) body rectangles
    pipe_center_dots: list[tuple] = []   # (cx, cy, r)
    pipe_ribs:        list[tuple] = []   # rib lines at the connector tip

    def _add_pipe_lhs(py: float, lbl: str, label_off: float):
        circle_r = tube_r * 1.15
        circle_x = -pipe_ext
        body_hh = body_h / 2.0

        neck_w = tube_r * 1.35
        body_w = max(18.0, stub_spacing * 3.2)
        tip_w = max(10.0, tube_r * 1.8)

        circle_left = circle_x - circle_r
        neck_left = circle_left - neck_w
        body_left = neck_left - body_w
        tip_left = body_left - tip_w
        tip_right = body_left

        connection_pipes.append({
            "line": (tip_left, py, header_block_len, py),
            "label": lbl,
            "label_pos": (tip_left + label_off, py),
        })

        # Tip (ribbed), body, neck
        pipe_bodies.append((tip_left, py - body_hh, tip_w, body_hh * 2.0))
        pipe_bodies.append((body_left, py - body_hh, body_w, body_hh * 2.0))
        pipe_bodies.append((neck_left, py - body_hh * 0.9, neck_w, body_hh * 1.8))

        # Ribs inside tip block (as in reference)
        rib_count = 4
        rib_dx = tip_w / (rib_count + 1)
        for i in range(1, rib_count + 1):
            rx = tip_left + i * rib_dx
            pipe_ribs.append((rx, py - body_hh, rx, py + body_hh))

        # Divider line between body and neck
        pipe_stubs.append((neck_left, py - body_hh, neck_left, py + body_hh))

        # Centre dot inside body
        pipe_center_dots.append((body_left + body_w * 0.48, py, tube_r * 0.42))

        # Open circle at 170 reference and inner fitting near header block
        pipe_circles.append((circle_x, py, circle_r))
        pipe_circles.append((header_block_len - fit_inner_off, py, tube_r * 1.0))

    def _add_pipe_rhs(py: float, lbl: str, label_off: float):
        circle_r = tube_r * 1.15
        circle_x = CW + pipe_ext
        body_hh = body_h / 2.0

        neck_w = tube_r * 1.35
        body_w = max(18.0, stub_spacing * 3.2)
        tip_w = max(10.0, tube_r * 1.8)

        circle_right = circle_x + circle_r
        neck_right = circle_right + neck_w
        body_right = neck_right + body_w
        tip_right = body_right + tip_w
        tip_left = body_right

        connection_pipes.append({
            "line": (CW - header_block_len, py, tip_right, py),
            "label": lbl,
            "label_pos": (tip_right + label_off, py),
        })

        pipe_bodies.append((tip_left, py - body_hh, tip_w, body_hh * 2.0))
        pipe_bodies.append((neck_right, py - body_hh * 0.9, neck_w, body_hh * 1.8))
        pipe_bodies.append((neck_right + neck_w, py - body_hh, body_w, body_hh * 2.0))

        rib_count = 4
        rib_dx = tip_w / (rib_count + 1)
        for i in range(1, rib_count + 1):
            rx = tip_left + i * rib_dx
            pipe_ribs.append((rx, py - body_hh, rx, py + body_hh))

        pipe_stubs.append((neck_right + neck_w, py - body_hh, neck_right + neck_w, py + body_hh))
        pipe_center_dots.append((neck_right + neck_w + body_w * 0.52, py, tube_r * 0.42))
        pipe_circles.append((circle_x, py, circle_r))
        pipe_circles.append((CW - header_block_len + fit_inner_off, py, tube_r * 1.0))

    if params.connection_side == "LHS":
        _add_pipe_lhs(pipe_y_in,  "IN",  -25.0)   # label sits left of pipe tip
        _add_pipe_lhs(pipe_y_out, "OUT", -30.0)
    else:
        _add_pipe_rhs(pipe_y_in,  "IN",  15.0)
        _add_pipe_rhs(pipe_y_out, "OUT", 15.0)

    # ── Return-end assembly box ───────────────────────────────────────────
    return_rect = (CW, margin, return_ext, CD)

    # ── Top-right step notch ──────────────────────────────────────────────
    top_right_box = (CW, 0.0, top_right_step, margin)

    # ── Return-bend U-bends ────────────────────────────────────────────────
    # Draw one lobe for EVERY consecutive row pair.
    # Example: NR=6 => 5 lobes (1-2, 2-3, 3-4, 4-5, 5-6), matching reference.
    # Each lobe has: 2 solid semicircles (tube walls) + 1 red centre arc.
    bend_arcs: list[tuple] = []          # solid tube-wall arcs
    bend_center_arcs: list[tuple] = []   # red dash-dot centre-line arcs
    for row in range(NR - 1):
        y1 = margin + RP / 2.0 + row * RP
        y2 = margin + RP / 2.0 + (row + 1) * RP
        mid_y = (y1 + y2) / 2.0
        base_r = (y2 - y1) / 2.0
        # Inner tube wall
        bend_arcs.append((CW, mid_y, max(1.0, base_r - tube_r), -90.0, 180.0))
        # Outer tube wall
        bend_arcs.append((CW, mid_y, max(1.0, base_r + tube_r), -90.0, 180.0))
        # Centre-line (red dash-dot) between inner and outer walls
        bend_center_arcs.append((CW, mid_y, max(1.0, base_r), -90.0, 180.0))

    total_width = pipe_ext + CW + return_ext

    return {
        "view_type": "TOP",
        "outer_rect":         outer_rect,
        "header_block_rect":  header_block_rect,
        "fin_rect":           fin_rect,
        "zone_lines":         zone_lines,
        "tube_lines":         tube_lines,
        "tube_center_lines":  tube_center_lines,
        "connection_pipes":   connection_pipes,
        "pipe_circles":       pipe_circles,
        "pipe_stubs":         pipe_stubs,
        "pipe_bodies":        pipe_bodies,
        "pipe_center_dots":   pipe_center_dots,
        "pipe_ribs":          pipe_ribs,
        "bend_arcs":          bend_arcs,
        "bend_center_arcs":   bend_center_arcs,
        "return_rect":        return_rect,
        "top_right_box":      top_right_box,
        "pipe_ext":           pipe_ext,
        "return_ext":         return_ext,
        "margin":             margin,
        "total_width":        total_width,
        "header_block_len":   header_block_len,
        "pipe_gap":           pipe_gap,
        "top_right_step":     top_right_step,
        "params":             params,
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

"""Dimension annotation geometry — pure coordinate data.

Renderer-agnostic: returns dicts with lines, arrows, texts.
"""
from __future__ import annotations
import math
from typing import Any

ARROW_LEN = 3.0
ARROW_ANGLE = 25.0
EXT_GAP = 2.0
EXT_OVER = 3.0
DIM_OFF = 15.0


def arrowhead_lines(tx: float, ty: float, a_deg: float):
    a = math.radians(a_deg)
    ha = math.radians(ARROW_ANGLE)
    out = []
    for s in (1, -1):
        dx = -ARROW_LEN * math.cos(a + s * ha)
        dy = -ARROW_LEN * math.sin(a + s * ha)
        out.append((tx, ty, tx + dx, ty + dy))
    return out


def _hdim(p1, p2, offset, text, above=False):
    """Horizontal dimension."""
    if text is None:
        text = f"{abs(p2[0]-p1[0]):.1f}"
    sign = 1 if above else -1
    dy = sign * abs(offset)
    dim_y = p1[1] + dy
    lines = [
        (p1[0], p1[1] + sign * EXT_GAP, p1[0], dim_y + sign * EXT_OVER),
        (p2[0], p2[1] + sign * EXT_GAP, p2[0], dim_y + sign * EXT_OVER),
        (p1[0], dim_y, p2[0], dim_y),
    ]
    arrows = [(p1[0], dim_y, 0.0), (p2[0], dim_y, 180.0)]
    texts = [((p1[0]+p2[0])/2, dim_y, text, 0.0)]
    return {"lines": lines, "arrows": arrows, "texts": texts}


def _vdim(p1, p2, offset, text, right=False):
    """Vertical dimension."""
    if text is None:
        text = f"{abs(p2[1]-p1[1]):.1f}"
    sign = 1 if right else -1
    dx = sign * abs(offset)
    dim_x = p1[0] + dx
    lines = [
        (p1[0] + sign * EXT_GAP, p1[1], dim_x + sign * EXT_OVER, p1[1]),
        (p2[0] + sign * EXT_GAP, p2[1], dim_x + sign * EXT_OVER, p2[1]),
        (dim_x, p1[1], dim_x, p2[1]),
    ]
    arrows = [(dim_x, p1[1], 90.0), (dim_x, p2[1], 270.0)]
    texts = [(dim_x, (p1[1]+p2[1])/2, text, 90.0)]
    return {"lines": lines, "arrows": arrows, "texts": texts}


# ══════════════════════════════════════════════════════════════════════════════
#  Per-view dimension generators
# ══════════════════════════════════════════════════════════════════════════════

def generate_front_dimensions(geo: dict) -> list[dict]:
    dims = []
    p = geo.get("params")
    if not p:
        return dims
    ox, oy, ow, oh = geo["outer_rect"]
    fx, fy, fw, fh = geo["fin_rect"]

    # Bottom: FL and casing width
    dims.append(_hdim((fx, oy), (fx + fw, oy), 25, f"{fw:.0f} (FL)"))
    dims.append(_hdim((ox, oy), (ox + ow, oy), 40, f"{ow:.0f}"))

    # Bottom: left margin (casing_left) and right margin (casing_right)
    dims.append(_hdim((ox, oy), (fx, oy), 12, f"{p.casing_left:.0f}"))
    dims.append(_hdim((fx + fw, oy), (ox + ow, oy), 12, f"{p.casing_right:.0f}"))

    # Right side: FH and casing height
    dims.append(_vdim((ox + ow, fy), (ox + ow, fy + fh), 25, f"{fh:.0f} (FH)", right=True))
    dims.append(_vdim((ox + ow, oy), (ox + ow, oy + oh), 40, f"{oh:.0f}", right=True))

    # Right side: top and bottom casing extensions
    dims.append(_vdim((ox + ow, oy), (ox + ow, fy), 12, f"{p.casing_bottom:.0f}", right=True))
    dims.append(_vdim((ox + ow, fy + fh), (ox + ow, oy + oh), 12, f"{p.casing_top:.0f}", right=True))

    # Left side: configurable reference dimension from fin bottom
    dims.append(_vdim((ox, fy),
                      (ox, fy + p.bottom_plate + p.front_left_reference_extra),
                      15,
                      f"{p.bottom_plate + p.front_left_reference_extra:.0f}"))

    # FPI label (centre of front view)
    dims.append({"lines": [], "arrows": [],
                 "texts": [(fx + fw/2, fy + fh/2, f"{p.fpi} FPI", 0.0)]})

    return dims


def generate_header_dimensions(geo: dict) -> list[dict]:
    dims = []
    p = geo.get("params")
    if not p:
        return dims
    ox, oy, ow, oh = geo["outer_rect"]
    ix, iy, iw, ih = geo.get("inner_rect", (ox, oy, 0.0, 0.0))

    # Bottom: header depth
    dims.append(_hdim((ox, oy), (ox + ow, oy), 25, f"{ow:.0f}"))

    # Right: side-view total height
    dims.append(_vdim((ox + ow, oy), (ox + ow, oy + oh), 35, f"{oh:.1f}", right=True))

    # Right: top & bottom plate distances
    dims.append(_vdim((ox + ow, oy), (ox + ow, iy), 12, f"{p.bottom_plate:.0f}", right=True))
    dims.append(_vdim((ox + ow, iy + ih), (ox + ow, oy + oh), 12, f"{p.top_plate:.0f}", right=True))

    # Bottom: inner grid width (horizontal pitch x rows)
    dims.append(_hdim((ix, oy), (ix + iw, oy), 40, f"{iw:.1f}"))

    # Left: inner grid height (TPR x VP)
    dims.append(_vdim((ox, iy), (ox, iy + ih), 20, f"{ih:.1f}"))

    return dims


def generate_return_dimensions(geo: dict) -> list[dict]:
    dims = []
    p = geo.get("params")
    if not p:
        return dims
    ox, oy, ow, oh = geo["outer_rect"]
    ix, iy, iw, ih = geo.get("inner_rect", (ox, oy, 0.0, 0.0))

    # Bottom: return depth
    dims.append(_hdim((ox, oy), (ox + ow, oy), 25, f"{ow:.0f}"))

    # Right: side-view total height
    dims.append(_vdim((ox + ow, oy), (ox + ow, oy + oh), 35, f"{oh:.1f}", right=True))

    # Right: top & bottom plate distances
    dims.append(_vdim((ox + ow, oy), (ox + ow, iy), 12, f"{p.bottom_plate:.0f}", right=True))
    dims.append(_vdim((ox + ow, iy + ih), (ox + ow, oy + oh), 12, f"{p.top_plate:.0f}", right=True))

    # Bottom: inner grid width (horizontal pitch x rows)
    dims.append(_hdim((ix, oy), (ix + iw, oy), 40, f"{iw:.1f}"))

    # Left: inner grid height (TPR x VP)
    dims.append(_vdim((ox, iy), (ox, iy + ih), 20, f"{ih:.1f}"))

    return dims


def generate_top_dimensions(geo: dict) -> list[dict]:
    """Dimensions matching the template TOP view image."""
    dims = []
    p = geo.get("params")
    if not p:
        return dims
    ox, oy, ow, oh = geo["outer_rect"]       # 0, 0, CW, HD
    fx, fy, fw, fh = geo["fin_rect"]         # cl, margin, FL, CD
    pipe_ext   = geo.get("pipe_ext", p.connection_extension)
    return_ext = geo.get("return_ext", p.top_return_extension)
    margin     = geo.get("margin", 56.2)
    total_w    = geo.get("total_width", ow + pipe_ext + return_ext)
    header_block_len = geo.get("header_block_len", p.top_header_block_length)
    pipe_gap = geo.get("pipe_gap", p.connection_vertical_gap)
    top_right_step = geo.get("top_right_step", p.top_right_step)

    btm = oy + oh   # bottom of the casing rect

    # ══════════════════════════════════════════════════════════════════════
    #  BOTTOM – stacked horizontal dimensions
    # ══════════════════════════════════════════════════════════════════════

    # Row 1 (closest): casing_left | FL | casing_right
    dims.append(_hdim((ox,       btm), (fx,       btm), 12,
                      f"{p.casing_left:.0f}"))
    dims.append(_hdim((fx,       btm), (fx + fw,  btm), 25,
                      f"{fw:.0f} (FL)"))
    dims.append(_hdim((fx + fw,  btm), (ox + ow,  btm), 12,
                      f"{p.casing_right:.0f}"))

    # Row 2: casing width  1430
    dims.append(_hdim((ox,       btm), (ox + ow,  btm), 40,
                      f"{ow:.0f}"))

    # Row 3: pipe_ext   170  (measured from pipe tip to casing left)
    dims.append(_hdim((-pipe_ext, btm), (ox,       btm), 55,
                      f"{pipe_ext:.0f}"))

    # Row 4: 1575  (casing + return_ext)
    dims.append(_hdim((ox,       btm), (ox + ow + return_ext, btm), 70,
                      f"{ow + return_ext:.0f}"))

    # Row 5: total 1745
    dims.append(_hdim((-pipe_ext, btm), (ox + ow + return_ext, btm), 85,
                      f"{total_w:.0f}"))

    # ══════════════════════════════════════════════════════════════════════
    #  TOP – pipe run dimension  350  (170 + 180)
    # ══════════════════════════════════════════════════════════════════════
    dims.append(_hdim((-pipe_ext, oy), (ox + header_block_len, oy), -15,
                      f"{pipe_ext + header_block_len:.0f}", above=True))
    dims.append(_hdim((-pipe_ext, oy), (ox,         oy), -28,
                      f"{pipe_ext:.0f}", above=True))
    dims.append(_hdim((ox,        oy), (ox + header_block_len, oy), -28,
                      f"{header_block_len:.0f}", above=True))

    # ══════════════════════════════════════════════════════════════════════
    #  LEFT – vertical dimensions
    # ══════════════════════════════════════════════════════════════════════

    # Coil depth  207.6
    dims.append(_vdim((ox + header_block_len, fy), (ox + header_block_len, fy + fh), 15,
                      f"{p.coil_depth:.1f}"))

    # Pipe gap  75
    y_centre = oh / 2.0
    pipe_y_in  = y_centre - pipe_gap / 2.0
    pipe_y_out = y_centre + pipe_gap / 2.0
    dims.append(_vdim((-pipe_ext - 5, pipe_y_in),
                      (-pipe_ext - 5, pipe_y_out), 10,
                      f"{pipe_gap:.0f}"))

    # ══════════════════════════════════════════════════════════════════════
    #  RIGHT – vertical dimensions
    # ══════════════════════════════════════════════════════════════════════

    # Total depth  320
    dims.append(_vdim((ox + ow + return_ext, oy),
                      (ox + ow + return_ext, oy + oh), 25,
                      f"{oh:.0f}", right=True))

    # Upper margin  56.2  (casing top to coil zone)
    dims.append(_vdim((ox + ow, oy), (ox + ow, fy), 12,
                      f"{margin:.1f}", right=True))

    # Lower margin  56.2  (coil zone to casing bottom)
    dims.append(_vdim((ox + ow, fy + fh), (ox + ow, oy + oh), 12,
                      f"{margin:.1f}", right=True))

    # Small 12 mm box at top-right
    dims.append(_vdim((ox + ow + return_ext, oy),
                      (ox + ow + return_ext, oy + top_right_step), 12,
                      f"{top_right_step:.0f}", right=True))

    return dims

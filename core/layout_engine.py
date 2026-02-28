"""Layout engine — arranges 4 views matching the template.

Layout (Third-Angle Projection):

                         TOP VIEW
                         ─────────
    HEADER SIDE  |  FRONT VIEW  |  RETURN END SIDE
    ────────────    ──────────    ─────────────────
    NOTE:                         TITLE BLOCK
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from core.parameters import CoilParameters
from core.geometry_engine import (
    generate_front_geometry,
    generate_header_geometry,
    generate_return_geometry,
    generate_top_geometry,
    generate_notes,
    generate_title_block,
)
from core.dimension_engine import (
    generate_front_dimensions,
    generate_header_dimensions,
    generate_return_dimensions,
    generate_top_dimensions,
)

VIEW_GAP = 80.0


@dataclass
class ViewDescriptor:
    label: str
    offset_x: float
    offset_y: float
    geometry: dict[str, Any]
    dimensions: list[dict[str, Any]]


@dataclass
class DrawingLayout:
    views: list[ViewDescriptor]
    notes: dict[str, Any]
    title_block: dict[str, Any]
    notes_offset: tuple[float, float]
    title_block_offset: tuple[float, float]


def generate_layout(params: CoilParameters) -> DrawingLayout:
    front_geo = generate_front_geometry(params)
    header_geo = generate_header_geometry(params)
    return_geo = generate_return_geometry(params)
    top_geo = generate_top_geometry(params)
    notes_data = generate_notes(params)
    tb_data = generate_title_block(params)

    front_dims = generate_front_dimensions(front_geo)
    header_dims = generate_header_dimensions(header_geo)
    return_dims = generate_return_dimensions(return_geo)
    top_dims = generate_top_dimensions(top_geo)

    _, _, front_w, front_h = front_geo["outer_rect"]
    _, _, header_w, header_h = header_geo["outer_rect"]
    _, _, return_w, return_h = return_geo["outer_rect"]
    _, _, top_w, top_h = top_geo["outer_rect"]

    # ── Bottom row: HEADER | FRONT | RETURN ──────────────────────────────
    bottom_y = top_h + VIEW_GAP  # below the TOP view

    header_x = 0.0
    front_x = header_w + VIEW_GAP
    return_x = front_x + front_w + VIEW_GAP

    # ── TOP view: aligned with FRONT, above it ───────────────────────────
    top_x = front_x    # align left edge with FRONT
    top_y = 0.0

    views = [
        ViewDescriptor("TOP", top_x, top_y, top_geo, top_dims),
        ViewDescriptor("HEADER SIDE", header_x, bottom_y, header_geo, header_dims),
        ViewDescriptor("FRONT", front_x, bottom_y, front_geo, front_dims),
        ViewDescriptor("RETURN END SIDE", return_x, bottom_y, return_geo, return_dims),
    ]

    # Notes: below header side
    notes_y = bottom_y + max(front_h, header_h, return_h) + VIEW_GAP / 2
    notes_offset = (header_x, notes_y)

    # Title block: bottom-right area
    tb_offset = (return_x, notes_y)

    return DrawingLayout(views, notes_data, tb_data, notes_offset, tb_offset)

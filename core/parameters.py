"""Coil parameter definitions and validation.

Template title format:
    Tube_OD x FL x FH x NR x TPR x FPI x NC  - Side
e.g. 5/8"x1330FLx1400FHx6Rx35TPRx13FPIx35NC - LHS
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class CoilParameters:
    """All dimensional inputs defining a heat-exchanger coil."""

    # ── Primary dimensions (mm) ───────────────────────────────────────────
    fin_length: float = 1330.0          # FL
    fin_height: float = 1400.0          # FH

    # Tube grid
    no_of_rows: int = 6                 # NR  (depth direction)
    tubes_per_row: int = 35             # TPR (height direction)

    # Tube
    tube_od_inch: str = "5/8"           # display string
    tube_diameter: float = 15.875       # mm (5/8" = 15.875)

    # Fins
    fpi: int = 13                       # fins per inch

    # Circuits
    no_of_circuits: int = 35            # NC

    # ── Plate distances from FH edge to first/last tube centres ──────────
    top_plate: float = 65.0             # mm from top of FH to top tube row
    bottom_plate: float = 35.0          # mm from bottom of FH to bottom tube row

    # ── Casing extensions beyond fin area ────────────────────────────────
    casing_left: float = 35.0           # mm (header side)
    casing_right: float = 65.0          # mm (return end side)
    casing_top: float = 15.0            # mm
    casing_bottom: float = 15.0         # mm
    casing_thickness: float = 1.5       # sheet metal (mm)

    # ── Depth geometry ───────────────────────────────────────────────────
    coil_depth: float = 207.6           # fin coil pack depth (mm)
    header_depth: float = 320.0         # header plate assembly width (mm)
    return_depth: float = 320.0         # return end assembly width (mm)

    # ── Connection ───────────────────────────────────────────────────────
    connection_side: str = "LHS"        # LHS or RHS
    connection_extension: float = 170.0  # pipe extension beyond casing (top view)
    connection_vertical_gap: float = 75.0  # IN-OUT centre spacing (top view)

    # ── Top-view feature dimensions ─────────────────────────────────────
    top_header_block_length: float = 180.0  # left-side header block feature
    top_return_extension: float = 145.0     # right-side return assembly extension
    top_right_step: float = 12.0            # top-right notch/step dimension
    top_pipe_fitting_outer_offset: float = 50.0  # from outer pipe tip to first fitting center
    top_pipe_fitting_inner_offset: float = 25.0  # from header-block edge to inner fitting center
    top_pipe_stub_center_offset: float = 50.0    # from outer pipe tip to stub center
    top_pipe_stub_spacing: float = 12.0          # distance between stub lines

    # ── Front-view helper dimension ─────────────────────────────────────
    front_left_reference_extra: float = 150.0    # extra added to bottom_plate reference dim

    # ── Manufacturing ────────────────────────────────────────────────────
    fin_material: str = "Plain Aluminium"
    fin_thickness: float = 0.11         # mm
    tube_wall_thickness: float = 0.4    # mm

    # ── Computed ─────────────────────────────────────────────────────────
    @property
    def casing_width(self) -> float:
        return self.casing_left + self.fin_length + self.casing_right

    @property
    def casing_height(self) -> float:
        return self.casing_bottom + self.fin_height + self.casing_top

    @property
    def vertical_pitch(self) -> float:
        """VP = usable height / (TPR - 1)."""
        if self.tubes_per_row <= 1:
            return 0.0
        return (self.fin_height - self.top_plate - self.bottom_plate) / (self.tubes_per_row - 1)

    @property
    def row_pitch(self) -> float:
        """Depth spacing between tube rows."""
        if self.no_of_rows <= 1:
            return 0.0
        return self.coil_depth / self.no_of_rows

    @property
    def drawing_title(self) -> str:
        return (
            f'{self.tube_od_inch}"x{self.fin_length:.0f}FL'
            f"x{self.fin_height:.0f}FH"
            f"x{self.no_of_rows}R"
            f"x{self.tubes_per_row}TPR"
            f"x{self.fpi}FPI"
            f"x{self.no_of_circuits}NC"
            f" - {self.connection_side}"
        )


def validate_parameters(params: CoilParameters) -> list[str]:
    errors: list[str] = []
    for name in ("fin_length", "fin_height", "tube_diameter",
                 "casing_top", "casing_bottom", "casing_left", "casing_right",
                 "casing_thickness", "coil_depth", "header_depth",
                 "connection_extension", "connection_vertical_gap",
                 "top_header_block_length", "top_return_extension", "top_right_step",
                 "top_pipe_fitting_outer_offset", "top_pipe_fitting_inner_offset",
                 "top_pipe_stub_center_offset", "top_pipe_stub_spacing",
                 "front_left_reference_extra"):
        if getattr(params, name) <= 0:
            errors.append(f"{name} must be positive")
    for name in ("no_of_rows", "tubes_per_row", "fpi"):
        if getattr(params, name) < 1:
            errors.append(f"{name} must be >= 1")
    if params.top_plate + params.bottom_plate >= params.fin_height:
        errors.append("Top plate + Bottom plate must be < Fin Height")
    return errors

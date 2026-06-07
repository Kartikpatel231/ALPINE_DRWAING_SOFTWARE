import math
import sys
import json
import os
import hmac
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dataclasses import dataclass, fields, replace

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPolygonF
from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QInputDialog,
    QLineEdit, QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget,
)

ACCESS_WINDOW_DAYS = 30
DEFAULT_PASSWORD_SHA256 = hashlib.sha256("coilhelvix".encode("utf-8")).hexdigest()


def _access_state_path() -> Path:
    appdata = os.getenv("APPDATA")
    base_dir = Path(appdata) if appdata else (Path.home() / ".coil_helvix")
    access_dir = base_dir / "CoilHelvix"
    access_dir.mkdir(parents=True, exist_ok=True)
    return access_dir / "access_state.json"


def _load_or_create_first_run() -> datetime:
    state_file = _access_state_path()
    now_utc = datetime.now(timezone.utc)
    if not state_file.exists():
        state_file.write_text(json.dumps({"first_run_utc": now_utc.isoformat()}, indent=2), encoding="utf-8")
        return now_utc
    try:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
        raw = str(payload.get("first_run_utc", "")).strip()
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        state_file.write_text(json.dumps({"first_run_utc": now_utc.isoformat()}, indent=2), encoding="utf-8")
        return now_utc


def _resolve_expiry_datetime(first_run_utc: datetime) -> datetime:
    fixed = os.getenv("COIL_HELVIX_EXPIRY_DATE", "").strip()
    if fixed:
        try:
            d = datetime.strptime(fixed, "%Y-%m-%d").date()
            return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc)
        except ValueError:
            pass
    return first_run_utc + timedelta(days=ACCESS_WINDOW_DAYS)


def _is_password_valid(entered: str) -> bool:
    expected = os.getenv("COIL_HELVIX_PASSWORD_SHA256", DEFAULT_PASSWORD_SHA256).strip().lower()
    return hmac.compare_digest(hashlib.sha256(entered.encode("utf-8")).hexdigest().lower(), expected)


def _enforce_startup_access() -> tuple[bool, str | None]:
    first_run = _load_or_create_first_run()
    expiry = _resolve_expiry_datetime(first_run)
    if datetime.now(timezone.utc) <= expiry:
        return False, "Software access expired. Contact administrator."
    password, ok = QInputDialog.getText(None, "Access Required", "Enter password:", QLineEdit.EchoMode.Password)
    if not ok or not _is_password_valid(password):
        return False, "Invalid password. Application will close."
    return True, None


@dataclass
class CoilDimensions:
    top_total_length: float = 1745.0
    top_intermediate_length: float = 1575.0
    front_total_width: float = 1430.0
    front_total_height: float = 1430.0
    left_panel_width: float = 35.0
    right_panel_width: float = 65.0
    fin_length_override: float = 1330.0
    top_bottom_margin: float = 15.0
    top_plate: float = 15.0
    bottom_plate: float = 15.0
    core_width: float = 320.0
    left_pipe_offset: float = 170.0
    left_pipe_length: float = 185.0
    header_extension_length: float = 260.0
    nozzle_projection: float = 75.0
    header_box_height: float = 207.6
    right_cap_thickness: float = 12.0
    front_header_band_width: float = 185.0
    top_small_offset_1: float = 56.2
    top_small_offset_2: float = 56.2
    fpi: float = 13.0
    tube_dia_inch: float = 0.625
    pitch_vertical: float = 40.0
    pitch_horizontal: float = 34.64
    connection_side: str = "LHS"
    job_order_no: str = "252600912"
    coil_unique_id: str = "25001232"
    coil_type: str = "CHW"
    circle_diameter: float = 8.4
    tubes_per_row: float = 35.0
    number_of_rows: float = 6.0
    number_of_circuits: float = 13.0
    header_dia: float = 12.7
    blank_off_bend: float = 12.0
    top_feature_tube_dia: float = 15.88
    top_feature_tube_height: float = 173.2
    top_feature_pipe_length: float = 33.0
    top_feature_pitch_vertical: float = 40.0
    top_feature_pitch_horizontal: float = 34.64
    top_feature_circle_1_dia: float = 15.88
    top_feature_circle_2_dia: float = 14.5
    # Side-view specific circle diameters (separate from top-view)
    side_plate_outer_circle_dia: float = 15.88
    side_plate_inner_circle_dia: float = 14.5
    sheet_metal_thickness: float = 1.5
    first_bend_header_side: float = 12.0
    first_bend_return_side: float = 12.0
    first_bend_top_plate: float = 12.0
    first_bend_bottom_plate: float = 12.0
    first_bend_blank_off: float = 12.0
    first_bend_intermediate_plate: float = 12.0

    @property
    def fin_length(self) -> float:
        return max(20.0, self.fin_length_override)

    @property
    def fin_height(self) -> float:
        return max(20.0, self.front_total_height - self.top_plate - self.bottom_plate)

    @property
    def top_lead_span(self) -> float:
        return self.left_pipe_offset + self.left_pipe_length

    @property
    def calculated_top_intermediate_length(self) -> float:
        bow = max(self.left_panel_width, min(self.front_header_band_width, self.left_panel_width + self.fin_length))
        return max(100.0, self.front_total_width - self.left_panel_width + bow)

    @property
    def calculated_top_total_length(self) -> float:
        return max(500.0, self.left_pipe_offset + self.top_intermediate_length)

    # ── Return Bend Plate (side view) computed dimensions ────────────────────
    @property
    def return_plate_total_width(self) -> float:
        """Formula: Coil Width + 2*((Return Side Plate + First Bend Return) - (4 * sheet thickness))"""
        return self.core_width + 2.0 * (
            (self.right_panel_width + self.first_bend_return_side) - (4.0 * self.sheet_metal_thickness)
        )

    @property
    def return_plate_lifting_hole_side_dist(self) -> float:
        """Formula: (Return Side Plate / 2) + (first_bend_return - 2 * sheet_thickness)"""
        return (self.right_panel_width / 2.0) + (self.first_bend_return_side - 2.0 * self.sheet_metal_thickness)

    @property
    def return_plate_small_hole_pitch(self) -> float:
        """Formula: (total_width - 40) / 4"""
        return (self.return_plate_total_width - 40.0) / 4.0

    # ── Header Plate computed dimensions ────────────────────────────────────
    @property
    def header_plate_total_width(self) -> float:
        """Formula: Coil Width + 2*((Header Side Plate + First Bend Header) - (4 * sheet thickness))
           Example: 280 + 2*((35+12)-(4*1.5)) = 362 mm
        """
        return self.core_width + 2.0 * (
            (self.left_panel_width + self.first_bend_header_side) - (4.0 * self.sheet_metal_thickness)
        )

    @property
    def header_plate_lifting_hole_side_dist(self) -> float:
        """Formula: (Header Side Plate / 2) + (first_bend_header - 2 * sheet_thickness)
           Example: 35/2 + (12 - 2*1.5) = 26.5 mm
        """
        return (self.left_panel_width / 2.0) + (self.first_bend_header_side - 2.0 * self.sheet_metal_thickness)

    @property
    def header_plate_small_hole_pitch(self) -> float:
        """Formula: (total_width - 40) / 4"""
        return (self.header_plate_total_width - 40.0) / 4.0

    @property
    def header_plate_blank_off_hole_count(self) -> int:
        """Formula: round(Total Height / 150)"""
        return max(1, round(self.front_total_height / 150.0))

    def sanitized(self) -> "CoilDimensions":
        v = replace(self)
        v.top_total_length = max(500.0, v.top_total_length)
        v.front_total_width = max(200.0, v.front_total_width)
        v.front_total_height = max(300.0, v.front_total_height)
        v.core_width = max(80.0, v.core_width)
        v.top_intermediate_length = max(100.0, min(v.top_intermediate_length, v.top_total_length))
        v.left_panel_width = max(5.0, min(v.left_panel_width, 2000.0))
        v.right_panel_width = max(5.0, min(v.right_panel_width, 2000.0))
        v.fin_length_override = max(20.0, min(v.fin_length_override, 6000.0))
        v.front_total_width = max(200.0, v.left_panel_width + v.fin_length + v.right_panel_width)
        min_top_total = v.front_total_width - v.left_panel_width + 20.0
        v.top_total_length = max(v.top_total_length, min_top_total)
        ml = (v.front_total_height / 2.0) - 10.0
        lm = max(5.0, min(v.top_bottom_margin, ml))
        if (abs(v.top_plate - CoilDimensions.top_plate) < 1e-6
                and abs(v.bottom_plate - CoilDimensions.bottom_plate) < 1e-6
                and abs(lm - CoilDimensions.top_bottom_margin) > 1e-6):
            v.top_plate = lm
            v.bottom_plate = lm
        v.top_plate = max(5.0, min(v.top_plate, ml))
        v.bottom_plate = max(5.0, min(v.bottom_plate, ml))
        pl = max(10.0, v.front_total_height - 20.0)
        pt = v.top_plate + v.bottom_plate
        if pt > pl:
            r = pl / pt
            v.top_plate = max(5.0, v.top_plate * r)
            v.bottom_plate = max(5.0, v.bottom_plate * r)
        v.top_bottom_margin = (v.top_plate + v.bottom_plate) / 2.0
        v.front_header_band_width = max(v.left_panel_width + 20.0,
                                        min(v.front_header_band_width, v.front_total_width - 20.0))
        v.top_intermediate_length = v.calculated_top_intermediate_length
        v.top_total_length = max(min_top_total, v.calculated_top_total_length)
        v.left_pipe_offset = max(0.0, min(v.left_pipe_offset, 3000.0))
        v.left_pipe_length = max(10.0, min(v.left_pipe_length, 3000.0))
        v.nozzle_projection = max(15.0, v.nozzle_projection)
        v.header_extension_length = max(v.nozzle_projection + 5.0, v.header_extension_length)
        v.right_cap_thickness = max(2.0, min(v.right_cap_thickness, v.core_width / 2.0))
        el = max(5.0, v.core_width - 2.0 * v.right_cap_thickness - 10.0)
        v.top_small_offset_1 = max(5.0, min(v.top_small_offset_1, el))
        v.top_small_offset_2 = max(5.0, min(v.top_small_offset_2, el))
        pl2 = max(12.0, v.core_width - 2.0 * v.right_cap_thickness - 20.0)
        st = v.top_small_offset_1 + v.top_small_offset_2
        if st > pl2:
            r = pl2 / st
            v.top_small_offset_1 = max(5.0, v.top_small_offset_1 * r)
            v.top_small_offset_2 = max(5.0, v.top_small_offset_2 * r)
        v.fpi = max(1.0, min(v.fpi, 60.0))
        v.tube_dia_inch = max(0.1, min(v.tube_dia_inch, 2.0))
        v.pitch_vertical = max(5.0, min(v.pitch_vertical, 120.0))
        v.pitch_horizontal = max(5.0, min(v.pitch_horizontal, 120.0))
        v.circle_diameter = max(2.0, min(v.circle_diameter, 40.0))
        v.tubes_per_row = max(1.0, min(v.tubes_per_row, 300.0))
        v.number_of_rows = max(1.0, min(v.number_of_rows, 40.0))
        v.number_of_circuits = max(1.0, min(v.number_of_circuits, 100.0))
        v.header_dia = max(2.0, min(v.header_dia, 500.0))
        v.blank_off_bend = max(0.0, min(v.blank_off_bend, 200.0))
        v.top_feature_tube_dia = max(2.0, min(v.top_feature_tube_dia, 80.0))
        v.top_feature_pipe_length = max(2.0, min(v.top_feature_pipe_length, 200.0))
        v.top_feature_pitch_vertical = max(5.0, min(v.top_feature_pitch_vertical, 200.0))
        v.top_feature_pitch_horizontal = max(5.0, min(v.top_feature_pitch_horizontal, 200.0))
        v.top_feature_circle_1_dia = max(2.0, min(v.top_feature_circle_1_dia, 80.0))
        v.top_feature_circle_2_dia = max(2.0, min(v.top_feature_circle_2_dia, 80.0))
        v.side_plate_outer_circle_dia = max(2.0, min(v.side_plate_outer_circle_dia, 80.0))
        v.side_plate_inner_circle_dia = max(2.0, min(v.side_plate_inner_circle_dia,
                                                      v.side_plate_outer_circle_dia - 0.4))
        v.sheet_metal_thickness = max(0.5, min(v.sheet_metal_thickness, 10.0))
        for attr in ("first_bend_header_side", "first_bend_return_side", "first_bend_top_plate",
                     "first_bend_bottom_plate", "first_bend_blank_off", "first_bend_intermediate_plate"):
            setattr(v, attr, max(0.0, min(getattr(v, attr), 200.0)))
        if (abs(v.first_bend_blank_off - CoilDimensions.first_bend_blank_off) < 1e-6
                and abs(v.blank_off_bend - CoilDimensions.blank_off_bend) > 1e-6):
            v.first_bend_blank_off = max(0.0, min(v.blank_off_bend, 200.0))
        v.blank_off_bend = v.first_bend_blank_off
        hp = max(5.0, v.pitch_horizontal)
        v.top_feature_tube_height = hp * (v.number_of_rows - 1.0)
        v.header_box_height = hp * v.number_of_rows
        v.front_total_height = v.tubes_per_row * v.pitch_vertical + v.top_plate + v.bottom_plate
        conn = str(v.connection_side).strip().upper()
        v.connection_side = conn if conn in {"LHS", "RHS"} else "LHS"
        v.job_order_no = str(v.job_order_no).strip() or CoilDimensions.job_order_no
        v.coil_unique_id = str(v.coil_unique_id).strip() or CoilDimensions.coil_unique_id
        v.coil_type = str(v.coil_type).strip().upper() or CoilDimensions.coil_type
        return v


class SideViewDrawingWidget(QWidget):
    """
    Draws both side views side by side:
      LEFT  → Return End Side  (mirror, wider outer box, lifting holes, small band holes)
      RIGHT → Header Side      (normal, dimensions shown)
    """

    BACKGROUND   = QColor("#f2f2f2")
    OBJECT_COLOR = QColor("#111111")
    DIM_COLOR    = QColor("#ff6a00")
    TUBE_COLOR   = QColor("#ff1a1a")   # outer hole ring (red)
    MAGENTA      = QColor("#b000ff")
    OBJECT_LINE_WIDTH = 1.7
    DIM_LINE_WIDTH    = 1.05

    LIFTING_HOLE_DIA  = 20.0   # mm  (from Excel: dia 20 mm)
    LIFTING_HOLE_TOP  = 50.0   # mm  (from Excel: distance from top = 50 mm)
    SMALL_HOLE_DIA    = 6.0    # mm  (from Excel: dia 6 mm)
    SMALL_HOLE_EDGE   = 20.0   # mm  (first hole 20 mm from edge)

    def __init__(self, dimensions: CoilDimensions | None = None) -> None:
        super().__init__()
        self._dims = (dimensions or CoilDimensions()).sanitized()
        self._zoom = 1.0
        self._min_zoom = 0.25
        self._max_zoom = 6.0
        self._pan_offset = QPointF(0.0, 0.0)
        self._is_panning = False
        self._last_pan_pos: QPointF | None = None
        self.setMinimumSize(900, 700)

    def set_dimensions(self, dimensions: CoilDimensions) -> None:
        self._dims = dimensions.sanitized()
        self.update()

    def zoom_by(self, factor: float) -> None:
        c = max(self._min_zoom, min(self._zoom * factor, self._max_zoom))
        if abs(c - self._zoom) > 1e-6:
            self._zoom = c
            self.update()

    def reset_view(self) -> None:
        self._zoom = 1.0
        self._pan_offset = QPointF(0.0, 0.0)
        self.update()

    def zoom_percent(self) -> int:
        return int(round(self._zoom * 100.0))

    # ── Qt events ────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        self.render_to_painter(p, QRectF(self.rect()), self.BACKGROUND, True)

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        layout = self._layout_data()
        rect = QRectF(self.rect())
        bs, bx, by = self._calc_transform(rect, layout["world_w"], layout["world_h"], True)
        cur = event.position()
        wx, wy = (cur.x() - bx) / bs, (cur.y() - by) / bs
        factor = 1.12 if delta > 0 else 1.0 / 1.12
        old = self._zoom
        self._zoom = max(self._min_zoom, min(self._zoom * factor, self._max_zoom))
        if abs(self._zoom - old) < 1e-6:
            event.accept()
            return
        ns, nx, ny = self._calc_transform(rect, layout["world_w"], layout["world_h"], True)
        self._pan_offset = QPointF(
            self._pan_offset.x() + cur.x() - (nx + wx * ns),
            self._pan_offset.y() + cur.y() - (ny + wy * ns),
        )
        self.update()
        event.accept()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_panning = True
            self._last_pan_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._is_panning and self._last_pan_pos is not None:
            d = event.position() - self._last_pan_pos
            self._pan_offset += QPointF(d.x(), d.y())
            self._last_pan_pos = event.position()
            self.update()
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_panning = False
            self._last_pan_pos = None
            self.unsetCursor()
            event.accept()

    # ── Rendering ────────────────────────────────────────────────────────────

    def render_to_painter(self, painter: QPainter, target_rect: QRectF,
                          background: QColor, apply_view_transform: bool = False) -> None:
        if not isinstance(target_rect, QRectF):
            target_rect = QRectF(target_rect)
        layout = self._layout_data()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.fillRect(target_rect, background)
        scale, ox, oy = self._calc_transform(
            target_rect, layout["world_w"], layout["world_h"], apply_view_transform)
        painter.translate(ox, oy)
        painter.scale(scale, scale)
        self._draw_both_sides(painter, layout)
        painter.restore()

    def _calc_transform(self, target_rect, world_w, world_h, apply_view):
        margin = 20.0
        aw = max(10.0, target_rect.width() - 2 * margin)
        ah = max(10.0, target_rect.height() - 2 * margin)
        fit = min(aw / world_w, ah / world_h)
        scale = fit * self._zoom if apply_view else fit
        px = self._pan_offset.x() if apply_view else 0.0
        py = self._pan_offset.y() if apply_view else 0.0
        ox = target_rect.x() + (target_rect.width() - world_w * scale) / 2.0 + px
        oy = target_rect.y() + (target_rect.height() - world_h * scale) / 2.0 + py
        return scale, ox, oy

    def _layout_data(self) -> dict:
        dims = self._dims
        gap = 200.0
        margin_left = 100.0
        margin_top = 80.0
        top_proj_gap = 280.0   # vertical gap between side views and top projection

        # Inner core height (formula driven)
        h_inner = dims.tubes_per_row * dims.pitch_vertical + dims.top_plate + dims.bottom_plate

        # Return End outer box is wider than core_width
        w_return_outer = dims.return_plate_total_width
        w_core = dims.core_width

        return_end_x  = margin_left
        header_side_x = margin_left + w_return_outer + gap

        # Top projection sits below the two side views.
        # It is drawn starting from margin_left and spans:
        #   fin_length (main box) + flanges + stub/header on left + blank-off on right
        # We give it enough left margin for the header assembly sticking out left.
        header_assembly_extra = dims.nozzle_projection + dims.header_extension_length + dims.left_pipe_length + dims.header_dia + 120.0
        top_proj_x = margin_left + header_assembly_extra
        top_proj_y = margin_top + h_inner + top_proj_gap

        # top-projection height = horizontal_pitch * number_of_rows  (depth of coil)
        tp_h = max(5.0, dims.pitch_horizontal) * max(1, int(round(dims.number_of_rows)))

        # total world width: must fit side views, top projection AND header plate
        side_views_w     = margin_left + w_return_outer + gap + w_core + 220.0
        top_proj_total_w = top_proj_x + dims.fin_length_override + dims.right_panel_width + dims.left_panel_width + 160.0
        hp_right_edge    = (top_proj_x + dims.fin_length_override + dims.right_panel_width + 200.0
                            + dims.header_plate_total_width + 220.0)
        world_w = max(side_views_w, top_proj_total_w, hp_right_edge)

        world_h = top_proj_y + tp_h + 340.0

        return {
            "return_end_x":   return_end_x,
            "header_side_x":  header_side_x,
            "y":              margin_top,
            "h_inner":        h_inner,
            "w_return_outer": w_return_outer,
            "w_core":         w_core,
            "top_proj_x":     top_proj_x,
            "top_proj_y":     top_proj_y,
            "tp_h":           tp_h,
            # Header Plate view — placed to the right of the top projection
            "hp_x":           top_proj_x + dims.fin_length_override + dims.right_panel_width + 200.0,
            "hp_y":           top_proj_y,
            "hp_h":           h_inner,
            "hp_w":           dims.header_plate_total_width,
            "world_w":        world_w,
            "world_h":        world_h,
        }

    # ── Scene ─────────────────────────────────────────────────────────────────

    def _draw_both_sides(self, painter: QPainter, layout: dict) -> None:
        # Return End Side — uses wider outer box + lifting holes + small holes
        self._draw_return_end_side(painter, layout["return_end_x"], layout["y"],
                                   layout["w_return_outer"], layout["h_inner"])
        # Header Side — standard core_width box + full dimensions
        self._draw_one_side(painter, layout["header_side_x"], layout["y"],
                            layout["w_core"], layout["h_inner"],
                            label="HEADER SIDE", show_vertical_dims=True, mirror=True)
        # Top projection (coil depth view) — below both side views
        self._draw_top_projection(painter, layout)
        # Header Plate — beside the top projection
        self._draw_header_plate(painter, layout)
        self._draw_notes(painter, layout)

    # ── Return End Side (complete per Excel spec) ────────────────────────────

    def _draw_return_end_side(self, painter: QPainter, x: float, y: float,
                               w_outer: float, h: float) -> None:
        """
        Draws the Return End Side with:
        - Wider outer box  (formula: core_width + 2*((RSP+FB_RS)-(4*t)))
        - Inner tube-layout identical to header side (mirrored)
        - Double-circle tube holes (red outer + black inner)
        - Magenta dashed band lines + 5 marker dots each band
        - 2 lifting holes dia=20mm at top=50mm, side=41.5mm from outer edge
        - 4 small holes (dia=6mm) on top band at pitch=(w_outer-40)/4
        - 4 small holes (dia=6mm) on bottom band at same pitch
        - Outer-box width dimension shown
        - Lifting-hole position dimensions (50 top, side dist)
        """
        dims = self._dims

        # ── Core inner geometry (mirrored) ────────────────────────────────────
        rows_in_width    = max(1, int(round(dims.number_of_rows)))
        tubes_per_row    = max(1, int(round(dims.tubes_per_row)))
        horizontal_pitch = max(5.0, dims.pitch_horizontal)
        vertical_pitch   = max(5.0, dims.pitch_vertical)

        tube_layout_w = rows_in_width * horizontal_pitch
        tube_layout_h = max(0.0, tubes_per_row * vertical_pitch)

        # The inner coil is centred inside the wider outer box
        inner_x_offset = (w_outer - dims.core_width) / 2.0   # extra margin each side

        def map_x(lx: float) -> float:
            # mirror within core_width, then shift right by inner_x_offset
            return x + inner_x_offset + (dims.core_width - lx)

        obj_pen       = QPen(self.OBJECT_COLOR, self.OBJECT_LINE_WIDTH)
        inner_rect_pen = QPen(QColor("#222222"), 1.8)

        # ── Outer wider box ───────────────────────────────────────────────────
        painter.setPen(obj_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(x, y, w_outer, h))

        # ── Plate lines (inside core area) ────────────────────────────────────
        top_offset_y    = y + dims.top_plate
        bottom_offset_y = y + h - dims.bottom_plate
        painter.setPen(QPen(self.OBJECT_COLOR, 1.0))
        lx0 = x + inner_x_offset
        lx1 = lx0 + dims.core_width
        painter.drawLine(QPointF(lx0, top_offset_y),    QPointF(lx1, top_offset_y))
        painter.drawLine(QPointF(lx0, bottom_offset_y), QPointF(lx1, bottom_offset_y))

        # ── Inner tube-layout box ─────────────────────────────────────────────
        tb_left = (dims.core_width - tube_layout_w) / 2.0
        tb_top  = h - dims.bottom_plate - tube_layout_h
        tb_x1   = map_x(tb_left)
        tb_x2   = map_x(tb_left + tube_layout_w)
        painter.setPen(inner_rect_pen)
        painter.drawRect(QRectF(min(tb_x1, tb_x2), y + tb_top, tube_layout_w, tube_layout_h))

        # ── Circle sizes ──────────────────────────────────────────────────────
        dia_limit       = min(horizontal_pitch, vertical_pitch) * 0.90
        circle_1_dia    = max(2.0, min(dims.side_plate_outer_circle_dia, dia_limit))
        circle_2_dia    = max(2.0, min(dims.side_plate_inner_circle_dia, dia_limit))
        circle_1_radius = circle_1_dia / 2.0
        circle_2_radius = max(1.0, (circle_2_dia / 2.0) - 0.6)

        # ── Magenta dashed band lines ─────────────────────────────────────────
        mg_pen = QPen(self.MAGENTA, 1.1)
        mg_pen.setStyle(Qt.PenStyle.DashLine)
        mg_pen.setDashPattern([8.0, 5.0])
        painter.setPen(mg_pen)
        bm            = 8.0
        top_band_y    = dims.top_plate * 0.5
        bottom_band_y = h - dims.bottom_plate * 0.5
        # band lines span full outer width
        painter.drawLine(QPointF(x + bm,          y + top_band_y),
                         QPointF(x + w_outer - bm, y + top_band_y))
        painter.drawLine(QPointF(x + bm,          y + bottom_band_y),
                         QPointF(x + w_outer - bm, y + bottom_band_y))

        # ── Band marker dots (5 per band, spaced over inner core width) ───────
        marker_radius = max(1.2, min(3.5, horizontal_pitch * 0.12))
        marker_pen    = QPen(self.OBJECT_COLOR, 1.6)
        m_start = inner_x_offset + bm + marker_radius
        m_end   = inner_x_offset + dims.core_width - bm - marker_radius
        if m_end > m_start:
            m_step = (m_end - m_start) / 4.0
            marker_positions = [m_start + i * m_step for i in range(5)]
        else:
            marker_positions = [(m_start + m_end) / 2.0]
        painter.save()
        painter.setPen(marker_pen)
        for mp in marker_positions:
            painter.drawEllipse(QPointF(x + mp, y + top_band_y),    marker_radius, marker_radius)
            painter.drawEllipse(QPointF(x + mp, y + bottom_band_y), marker_radius, marker_radius)
        painter.restore()

        # ── Double-circle tube holes ──────────────────────────────────────────
        outer_hole_pen = QPen(self.TUBE_COLOR,   1.1)
        inner_hole_pen = QPen(self.OBJECT_COLOR, 1.1)

        first_center_x   = tb_left + horizontal_pitch * 0.5
        y_start_from_bot = dims.bottom_plate + vertical_pitch * 0.5
        y_bottom_limit   = dims.bottom_plate
        y_top_limit      = h - dims.top_plate

        for row_index in range(rows_in_width):
            row_center_x = first_center_x + row_index * horizontal_pitch
            row_shift    = (vertical_pitch * 0.5) if (row_index % 2 == 1) else 0.0
            hole_radius  = circle_1_radius
            x_min = tb_left + hole_radius
            x_max = tb_left + tube_layout_w - hole_radius
            if row_center_x < x_min or row_center_x > x_max:
                continue
            y_r_bot = y_bottom_limit + hole_radius
            y_r_top = y_top_limit - hole_radius
            if y_r_top < y_r_bot:
                continue
            for tube_index in range(tubes_per_row):
                y_from_bot = y_start_from_bot + row_shift + tube_index * vertical_pitch
                if y_from_bot < y_r_bot or y_from_bot > y_r_top:
                    continue
                centre = QPointF(map_x(row_center_x), y + h - y_from_bot)
                painter.save()
                painter.setPen(outer_hole_pen)
                painter.drawEllipse(centre, circle_1_radius, circle_1_radius)
                painter.setPen(inner_hole_pen)
                painter.drawEllipse(centre, circle_2_radius, circle_2_radius)
                painter.restore()

        # ── Lifting holes (dia=20, top=50, side=lifting_hole_side_dist) ───────
        #
        # Excel formula: side dist = (Return Side Plate/2) + (FB_return - 2*t)
        # These are drawn from OUTER edge of the wider box.
        lifting_r    = self.LIFTING_HOLE_DIA / 2.0
        lift_top_y   = y + self.LIFTING_HOLE_TOP          # 50 mm from top
        side_dist    = dims.return_plate_lifting_hole_side_dist  # e.g. 41.5 mm
        lift_left_x  = x + side_dist                      # from left outer edge
        lift_right_x = x + w_outer - side_dist            # from right outer edge

        painter.save()
        painter.setPen(QPen(self.OBJECT_COLOR, self.OBJECT_LINE_WIDTH))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(lift_left_x,  lift_top_y), lifting_r, lifting_r)
        painter.drawEllipse(QPointF(lift_right_x, lift_top_y), lifting_r, lifting_r)
        painter.restore()

        # ── Small holes on top band (dia=6, 4 holes, pitch=(w_outer-40)/4) ────
        #
        # Excel: "Draw 4 holes with pitch formula = (total width - 40) / 4"
        # First hole at 20mm from outer left edge
        small_r    = self.SMALL_HOLE_DIA / 2.0
        hole_pitch = dims.return_plate_small_hole_pitch
        small_top_y    = y + top_band_y
        small_bottom_y = y + bottom_band_y
        first_hole_x   = x + self.SMALL_HOLE_EDGE          # 20 mm from left edge

        painter.save()
        painter.setPen(QPen(self.OBJECT_COLOR, 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(4):
            hx = first_hole_x + i * hole_pitch
            painter.drawEllipse(QPointF(hx, small_top_y),    small_r, small_r)
            painter.drawEllipse(QPointF(hx, small_bottom_y), small_r, small_r)
        painter.restore()

        # ── Dimensions ────────────────────────────────────────────────────────
        # 1. Overall outer width
        self._dim_h(painter, x, x + w_outer, y, -45.0, f"{w_outer:.0f}")

        # 2. Lifting hole top distance (50 mm)
        self._dim_v(painter, y, lift_top_y, x, -48.0, f"{self.LIFTING_HOLE_TOP:.0f}")

        # 3. Lifting hole side distance
        self._dim_h(painter, x, lift_left_x, y + h, 45.0, f"{side_dist:.1f}")

        # ── Circle annotation ─────────────────────────────────────────────────
        painter.setPen(QPen(self.DIM_COLOR, self.DIM_LINE_WIDTH))
        painter.setFont(QFont("Arial", 9))
        painter.drawText(QRectF(x, y - 22.0, w_outer, 16.0), Qt.AlignmentFlag.AlignCenter,
            f"C1 Ø {circle_1_dia:.2f}   C2 Ø {circle_2_dia:.2f}")

        # ── View label ────────────────────────────────────────────────────────
        painter.setPen(obj_pen)
        painter.setFont(QFont("Arial", 13))
        painter.drawText(QRectF(x, y + h + 79.0, w_outer, 30.0),
                         Qt.AlignmentFlag.AlignCenter, "RETURN END SIDE")

    # ── Header Side (standard) ────────────────────────────────────────────────

    def _draw_one_side(self, painter: QPainter, x: float, y: float,
                       w: float, h: float,
                       label: str, show_vertical_dims: bool, mirror: bool) -> None:
        dims = self._dims
        rows_in_width    = max(1, int(round(dims.number_of_rows)))
        tubes_per_row    = max(1, int(round(dims.tubes_per_row)))
        horizontal_pitch = max(5.0, dims.pitch_horizontal)
        vertical_pitch   = max(5.0, dims.pitch_vertical)
        tube_layout_w    = rows_in_width * horizontal_pitch
        tube_layout_h    = max(0.0, tubes_per_row * vertical_pitch)

        def map_x(lx: float) -> float:
            return x + (w - lx if mirror else lx)

        obj_pen       = QPen(self.OBJECT_COLOR, self.OBJECT_LINE_WIDTH)
        inner_rect_pen = QPen(QColor("#222222"), 1.8)

        painter.setPen(obj_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(x, y, w, h))

        top_offset_y    = y + dims.top_plate
        bottom_offset_y = y + h - dims.bottom_plate
        painter.setPen(QPen(self.OBJECT_COLOR, 1.0))
        painter.drawLine(QPointF(map_x(0.0), top_offset_y),    QPointF(map_x(w), top_offset_y))
        painter.drawLine(QPointF(map_x(0.0), bottom_offset_y), QPointF(map_x(w), bottom_offset_y))

        tb_left = (w - tube_layout_w) / 2.0
        tb_top  = h - dims.bottom_plate - tube_layout_h
        tb_x1   = map_x(tb_left)
        tb_x2   = map_x(tb_left + tube_layout_w)
        painter.setPen(inner_rect_pen)
        painter.drawRect(QRectF(min(tb_x1, tb_x2), y + tb_top, tube_layout_w, tube_layout_h))

        dia_limit       = min(horizontal_pitch, vertical_pitch) * 0.90
        circle_1_dia    = max(2.0, min(dims.side_plate_outer_circle_dia, dia_limit))
        circle_2_dia    = max(2.0, min(dims.side_plate_inner_circle_dia, dia_limit))
        circle_1_radius = circle_1_dia / 2.0
        circle_2_radius = max(1.0, (circle_2_dia / 2.0) - 0.6)

        mg_pen = QPen(self.MAGENTA, 1.1)
        mg_pen.setStyle(Qt.PenStyle.DashLine)
        mg_pen.setDashPattern([8.0, 5.0])
        painter.setPen(mg_pen)
        bm            = 8.0
        top_band_y    = dims.top_plate * 0.5
        bottom_band_y = h - dims.bottom_plate * 0.5
        painter.drawLine(QPointF(map_x(bm),     y + top_band_y),
                         QPointF(map_x(w - bm), y + top_band_y))
        painter.drawLine(QPointF(map_x(bm),     y + bottom_band_y),
                         QPointF(map_x(w - bm), y + bottom_band_y))

        # Band marker dots
        marker_radius = max(1.2, min(3.5, horizontal_pitch * 0.12))
        marker_pen    = QPen(self.OBJECT_COLOR, 1.6)
        m_start = bm + marker_radius
        m_end   = w - bm - marker_radius
        if m_end > m_start:
            m_step = (m_end - m_start) / 4.0
            marker_positions = [m_start + i * m_step for i in range(5)]
        else:
            marker_positions = [(m_start + m_end) / 2.0]
        painter.save()
        painter.setPen(marker_pen)
        for mp in marker_positions:
            painter.drawEllipse(QPointF(map_x(mp), y + top_band_y),    marker_radius, marker_radius)
            painter.drawEllipse(QPointF(map_x(mp), y + bottom_band_y), marker_radius, marker_radius)
        painter.restore()

        # Double-circle tube holes
        outer_hole_pen   = QPen(self.TUBE_COLOR,   1.1)
        inner_hole_pen   = QPen(self.OBJECT_COLOR, 1.1)
        first_center_x   = tb_left + horizontal_pitch * 0.5
        y_start_from_bot = dims.bottom_plate + vertical_pitch * 0.5
        y_bottom_limit   = dims.bottom_plate
        y_top_limit      = h - dims.top_plate

        for row_index in range(rows_in_width):
            row_center_x = first_center_x + row_index * horizontal_pitch
            row_shift    = (vertical_pitch * 0.5) if (row_index % 2 == 1) else 0.0
            hole_radius  = circle_1_radius
            x_min = tb_left + hole_radius
            x_max = tb_left + tube_layout_w - hole_radius
            if row_center_x < x_min or row_center_x > x_max:
                continue
            y_r_bot = y_bottom_limit + hole_radius
            y_r_top = y_top_limit - hole_radius
            if y_r_top < y_r_bot:
                continue
            for tube_index in range(tubes_per_row):
                y_from_bot = y_start_from_bot + row_shift + tube_index * vertical_pitch
                if y_from_bot < y_r_bot or y_from_bot > y_r_top:
                    continue
                centre = QPointF(map_x(row_center_x), y + h - y_from_bot)
                painter.save()
                painter.setPen(outer_hole_pen)
                painter.drawEllipse(centre, circle_1_radius, circle_1_radius)
                painter.setPen(inner_hole_pen)
                painter.drawEllipse(centre, circle_2_radius, circle_2_radius)
                painter.restore()

        # Horizontal dim
        self._dim_h(painter, x, x + w, y + h, 45.0, f"{w:.0f}")

        # Vertical dims (header side only)
        if show_vertical_dims:
            iy = y + tb_top
            self._dim_v(painter, iy, iy + tube_layout_h, x + w, 49.0, f"{tube_layout_h:.0f}")
            self._dim_v(painter, y, y + h,               x + w, 89.0, f"{h:.0f}")
            self._dim_v(painter, y, y + dims.top_plate,  x + w, 127.0, f"{dims.top_plate:.0f}")
            self._dim_v(painter, y + h - dims.bottom_plate, y + h, x + w, 127.0, f"{dims.bottom_plate:.0f}")
            if rows_in_width > 1:
                self._internal_dim_h(painter,
                    map_x(first_center_x),
                    map_x(first_center_x + horizontal_pitch),
                    y + h + 20.0,
                    f"HP {horizontal_pitch:.2f}")
            if tubes_per_row > 1:
                vp_y1  = y + (h - y_start_from_bot)
                vp_y2  = y + (h - (y_start_from_bot + vertical_pitch))
                vp_off = 58.0 if mirror else -58.0
                self._dim_v(painter, vp_y1, vp_y2, map_x(first_center_x), vp_off,
                            f"VP {vertical_pitch:.2f}")

        # Circle annotation
        painter.setPen(QPen(self.DIM_COLOR, self.DIM_LINE_WIDTH))
        painter.setFont(QFont("Arial", 9))
        painter.drawText(QRectF(x, y - 22.0, w, 16.0), Qt.AlignmentFlag.AlignCenter,
            f"C1 Ø {circle_1_dia:.2f}   C2 Ø {circle_2_dia:.2f}")

        # View label
        painter.setPen(obj_pen)
        painter.setFont(QFont("Arial", 13))
        painter.drawText(QRectF(x, y + h + 79.0, w, 30.0), Qt.AlignmentFlag.AlignCenter, label)

    # ── Header Plate (Excel spec steps 1-6) ──────────────────────────────────

    def _draw_header_plate(self, painter: QPainter, layout: dict) -> None:
        """
        Header Plate drawing per Excel spec:

        Step 1 : Same as End Plate steps 1-8 (tube holes grid) + steps 10-13
                 (top/bottom band small holes ø6).  Steps 14 & 15 NOT required.
        Step 2 : Wider outer box:
                 width = Coil Width + 2*((Header Side Plate + FB_Header) - (4*t))
                 Example: 280 + 2*((35+12)-(4*1.5)) = 362 mm
        Step 3 : Lifting hole ø20 mm — top dist = 50 mm,
                 side dist = (Header Side Plate/2) + (FB_Header - 2*t)
                 Example: 35/2 + (12 - 2*1.5) = 26.5 mm
        Step 4 : Mirror lifting hole on the other side.
        Step 5 : Blank-off holes ø6 mm — first hole 25 mm from lifting hole centre,
                 subsequent holes every 150 mm.
        Step 6 : No. of blank-off holes = round(Total Height / 150)
        """
        dims = self._dims
        x    = layout["hp_x"]
        y    = layout["hp_y"]
        h    = layout["hp_h"]        # (TPR × VP) + Top Plate + Bottom Plate
        w    = layout["hp_w"]        # header_plate_total_width

        # ── Geometry helpers ─────────────────────────────────────────────────
        rows_in_width    = max(1, int(round(dims.number_of_rows)))
        tubes_per_row    = max(1, int(round(dims.tubes_per_row)))
        horizontal_pitch = max(5.0, dims.pitch_horizontal)
        vertical_pitch   = max(5.0, dims.pitch_vertical)
        tube_layout_w    = rows_in_width * horizontal_pitch
        tube_layout_h    = max(0.0, tubes_per_row * vertical_pitch)

        obj_pen       = QPen(self.OBJECT_COLOR, self.OBJECT_LINE_WIDTH)
        inner_rect_pen = QPen(QColor("#222222"), 1.8)

        # ── Step 2: Main outer box (wider than core_width) ───────────────────
        painter.setPen(obj_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(x, y, w, h))

        # ── Step 1 / End Plate steps 2-3: Top and bottom plate offset lines ──
        # The inner core is centred inside the wider box.
        inner_offset_x = (w - dims.core_width) / 2.0
        top_offset_y    = y + dims.top_plate
        bottom_offset_y = y + h - dims.bottom_plate
        painter.setPen(QPen(self.OBJECT_COLOR, 1.0))
        painter.drawLine(QPointF(x,     top_offset_y),    QPointF(x + w, top_offset_y))
        painter.drawLine(QPointF(x,     bottom_offset_y), QPointF(x + w, bottom_offset_y))

        # ── Step 1 / End Plate step 4: Inner tube layout box ─────────────────
        # Box centred on the outer box, aligned to bottom offset line.
        tb_left_local = (w - tube_layout_w) / 2.0
        tb_top        = h - dims.bottom_plate - tube_layout_h
        painter.setPen(inner_rect_pen)
        painter.drawRect(QRectF(x + tb_left_local, y + tb_top, tube_layout_w, tube_layout_h))

        # ── Step 1 / End Plate steps 5-8: Double-circle tube holes ──────────
        dia_limit       = min(horizontal_pitch, vertical_pitch) * 0.90
        circle_1_dia    = max(2.0, min(dims.side_plate_outer_circle_dia, dia_limit))
        circle_2_dia    = max(2.0, min(dims.side_plate_inner_circle_dia, dia_limit))
        circle_1_r      = circle_1_dia / 2.0
        circle_2_r      = max(1.0, (circle_2_dia / 2.0) - 0.6)

        outer_hole_pen = QPen(self.TUBE_COLOR,   1.1)
        inner_hole_pen = QPen(self.OBJECT_COLOR, 1.1)

        first_cx      = tb_left_local + horizontal_pitch * 0.5
        y_start_frbot = dims.bottom_plate + vertical_pitch * 0.5
        y_bot_lim     = dims.bottom_plate
        y_top_lim     = h - dims.top_plate

        for row_i in range(rows_in_width):
            rcx       = first_cx + row_i * horizontal_pitch
            row_shift = (vertical_pitch * 0.5) if (row_i % 2 == 1) else 0.0
            xmin = tb_left_local + circle_1_r
            xmax = tb_left_local + tube_layout_w - circle_1_r
            if rcx < xmin or rcx > xmax:
                continue
            y_r_bot = y_bot_lim + circle_1_r
            y_r_top = y_top_lim - circle_1_r
            if y_r_top < y_r_bot:
                continue
            for ti in range(tubes_per_row):
                y_fb = y_start_frbot + row_shift + ti * vertical_pitch
                if y_fb < y_r_bot or y_fb > y_r_top:
                    continue
                centre = QPointF(x + rcx, y + h - y_fb)
                painter.save()
                painter.setPen(outer_hole_pen)
                painter.drawEllipse(centre, circle_1_r, circle_1_r)
                painter.setPen(inner_hole_pen)
                painter.drawEllipse(centre, circle_2_r, circle_2_r)
                painter.restore()

        # ── Step 1 / End Plate step 10-13: Band small holes ø6 (top + bottom) ─
        # Step 10: hole ø6 at width=20, height=Top Plate/2 from top
        # Step 11: 4 holes, pitch=(w - 40)/4
        # Step 12: same at bottom (height = Bottom Plate/2 from bottom)
        # Step 13: same 4 holes at bottom
        small_r     = 3.0                                    # ø6 mm
        top_hole_y  = y + dims.top_plate / 2.0
        bot_hole_y  = y + h - dims.bottom_plate / 2.0
        edge_dist   = 20.0                                   # first hole 20 mm from left edge
        s_pitch     = max(1.0, (w - 40.0) / 4.0)            # (total_width - 40) / 4

        painter.setPen(obj_pen)
        for hi in range(5):      # edge hole + 4 pitched holes = 5 total
            hx = x + edge_dist + hi * s_pitch
            painter.drawEllipse(QPointF(hx, top_hole_y), small_r, small_r)
            painter.drawEllipse(QPointF(hx, bot_hole_y), small_r, small_r)

        # ── Steps 3-4: Lifting holes ø20 at top=50 mm, side=lifting_side_dist ─
        lift_r    = 10.0                                     # ø20 mm radius
        lift_top_y = y + 50.0
        side_dist = dims.header_plate_lifting_hole_side_dist  # e.g. 26.5 mm
        lift_lx   = x + side_dist
        lift_rx   = x + w - side_dist

        painter.save()
        painter.setPen(QPen(self.OBJECT_COLOR, self.OBJECT_LINE_WIDTH))
        painter.drawEllipse(QPointF(lift_lx, lift_top_y), lift_r, lift_r)
        painter.drawEllipse(QPointF(lift_rx, lift_top_y), lift_r, lift_r)
        painter.restore()

        # ── Steps 5-6: Blank-off holes ø6 ────────────────────────────────────
        # First hole at 25 mm from lifting hole centre (downward).
        # All other holes at 150 mm intervals.
        # Number of holes = round(Total Height / 150).
        bo_hole_count = dims.header_plate_blank_off_hole_count
        bo_hole_r     = 3.0                                  # ø6 mm
        bo_first_y    = lift_top_y + 25.0                    # 25 mm below lifting hole
        bo_pitch      = 150.0

        painter.save()
        painter.setPen(QPen(self.OBJECT_COLOR, 1.2))
        for bi in range(bo_hole_count):
            bhy = bo_first_y + bi * bo_pitch
            if bhy > y + h - 5.0:
                break
            # Draw on both sides (left column and right column)
            painter.drawEllipse(QPointF(lift_lx, bhy), bo_hole_r, bo_hole_r)
            painter.drawEllipse(QPointF(lift_rx, bhy), bo_hole_r, bo_hole_r)
        painter.restore()

        # ── Magenta dashed band lines + 5 marker dots ────────────────────────
        mg_pen = QPen(self.MAGENTA, 1.1)
        mg_pen.setStyle(Qt.PenStyle.DashLine)
        mg_pen.setDashPattern([8.0, 5.0])
        painter.setPen(mg_pen)
        bm            = 8.0
        top_band_y    = dims.top_plate * 0.5
        bottom_band_y = h - dims.bottom_plate * 0.5
        painter.drawLine(QPointF(x + bm,      y + top_band_y),
                         QPointF(x + w - bm,  y + top_band_y))
        painter.drawLine(QPointF(x + bm,      y + bottom_band_y),
                         QPointF(x + w - bm,  y + bottom_band_y))

        marker_r = max(1.2, min(3.5, horizontal_pitch * 0.12))
        m_start  = inner_offset_x + bm + marker_r
        m_end    = inner_offset_x + dims.core_width - bm - marker_r
        if m_end > m_start:
            m_step = (m_end - m_start) / 4.0
            mpos   = [m_start + i * m_step for i in range(5)]
        else:
            mpos   = [(m_start + m_end) / 2.0]
        painter.save()
        painter.setPen(QPen(self.OBJECT_COLOR, 1.6))
        for mp in mpos:
            painter.drawEllipse(QPointF(x + mp, y + top_band_y),    marker_r, marker_r)
            painter.drawEllipse(QPointF(x + mp, y + bottom_band_y), marker_r, marker_r)
        painter.restore()

        # ── Dimensions ────────────────────────────────────────────────────────
        # Overall width
        self._dim_h(painter, x, x + w, y, -45.0, f"{w:.0f}")
        # Total height
        self._dim_v(painter, y, y + h, x + w, 50.0, f"{h:.0f}")
        # Top plate
        self._dim_v(painter, y, y + dims.top_plate, x + w, 90.0, f"{dims.top_plate:.0f}")
        # Bottom plate
        self._dim_v(painter, y + h - dims.bottom_plate, y + h, x + w, 90.0, f"{dims.bottom_plate:.0f}")
        # Lifting hole top distance
        self._dim_v(painter, y, lift_top_y, x, -50.0, "50")
        # Lifting hole side distance
        self._dim_h(painter, x, lift_lx, y + h, 45.0, f"{side_dist:.1f}")
        # Blank-off hole count annotation
        painter.setPen(QPen(self.DIM_COLOR, self.DIM_LINE_WIDTH))
        painter.setFont(QFont("Arial", 9))
        painter.drawText(
            QRectF(x, y - 38.0, w, 14.0), Qt.AlignmentFlag.AlignCenter,
            f"Blank-off holes: {bo_hole_count} × ø6 @ 150mm pitch",
        )
        # Circle annotation
        painter.drawText(
            QRectF(x, y - 22.0, w, 14.0), Qt.AlignmentFlag.AlignCenter,
            f"C1 Ø {circle_1_dia:.2f}   C2 Ø {circle_2_dia:.2f}",
        )

        # ── View label (file name hint) ───────────────────────────────────────
        painter.setPen(obj_pen)
        self._draw_underlined_label(
            painter,
            QRectF(x, y + h + 50.0, w, 30.0),
            f"HEADER PLATE  ({dims.coil_unique_id}-HP)",
        )

    # ── Top Projection (coil depth view — Excel steps 1-16) ──────────────────

    def _draw_top_projection(self, painter: QPainter, layout: dict) -> None:
        """
        Draws the coil as seen from above (depth cross-section), implementing
        Excel Top View steps 1-16:

        Step 1 : Main box  — Length = Fin Length,  Width = HP × No. of rows
        Step 2 : Dashed row lines (HP/2 offset from bottom) + small tube-dia box at right end
        Step 3 : Repeat for every row (No. of rows total dashed lines)
        Step 4 : Right-end semi-circle bends  R1=(HP+tube_dia)/2  R2=(HP-tube_dia)/2
        Step 5 : Repeat for all pairs
        Step 6 : Left/right side flanges extending by Total Width (core_width) centred
        Step 7 : Header-side flange lines (left_panel_width)
        Step 8 : Header-side first-bend lines
        Step 9 : Return-side flange lines (right_panel_width)
        Step 10: Return-side first-bend lines
        Step 11: Blank-off line (horizontal, from header side)
        Step 12: Blank-off bend (vertical tick)
        Step 13: Stub lines from 1st/last dashed row to circle centre
        Step 14: Header circles (diameter = header_dia)
        Step 15: Header body rectangle (nozzle_projection length)
        Step 16: Dimension annotations
        """
        dims   = self._dims
        x0     = layout["top_proj_x"]   # left edge of main fin box
        y0     = layout["top_proj_y"]   # top edge of main fin box
        hp     = max(5.0, dims.pitch_horizontal)
        nor    = max(1, int(round(dims.number_of_rows)))
        fl     = max(20.0, dims.fin_length_override)
        tube_d = max(2.0, dims.top_feature_tube_dia)

        # ── Step 1: main box ──────────────────────────────────────────────────
        box_h = hp * nor          # width of coil (depth)
        box_w = fl                # length of coil (fin length)

        obj_pen  = QPen(self.OBJECT_COLOR, self.OBJECT_LINE_WIDTH)
        dim_pen  = QPen(self.DIM_COLOR,    self.DIM_LINE_WIDTH)
        dash_pen = QPen(self.TUBE_COLOR,   1.4)
        dash_pen.setStyle(Qt.PenStyle.DashLine)
        dash_pen.setDashPattern([10.0, 6.0])

        painter.setPen(obj_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(x0, y0, box_w, box_h))

        # ── Steps 2-3: dashed row lines + small box at right end ──────────────
        # First line offset from TOP by HP/2, then every HP after that.
        # "Bottom" in Excel = top in screen coords (y increases downward).
        # Row line y positions inside box:
        row_ys: list[float] = []
        for ri in range(nor):
            ry = y0 + (hp / 2.0) + ri * hp
            row_ys.append(ry)
            painter.setPen(dash_pen)
            painter.drawLine(QPointF(x0, ry), QPointF(x0 + box_w, ry))

            # small tube-dia box at RIGHT end of each dashed line
            painter.setPen(obj_pen)
            box_len = 20.0
            painter.drawRect(QRectF(x0 + box_w - box_len, ry - tube_d / 2.0, box_len, tube_d))

        # ── Steps 4-5: semi-circle bends at return (right) end ───────────────
        # Between each pair of adjacent row lines draw 2 semi-circles (right side)
        r1 = (hp + tube_d) / 2.0
        r2 = (hp - tube_d) / 2.0
        bend_x = x0 + box_w          # right face of box

        painter.setPen(obj_pen)
        for pi in range(nor - 1):
            ya = row_ys[pi]
            yb = row_ys[pi + 1]
            cy = (ya + yb) / 2.0
            # Semi-circles open to the RIGHT (span = -180° → 0°, i.e. right half)
            # Qt: 0° = 3-o'clock, angles in 1/16 degree, CCW positive
            rect1 = QRectF(bend_x - r1, cy - r1, 2 * r1, 2 * r1)
            rect2 = QRectF(bend_x - r2, cy - r2, 2 * r2, 2 * r2)
            # Draw right semi-circle: start=-90*16, span=-180*16 (bottom to top going right)
            painter.drawArc(rect1, -90 * 16, -180 * 16)
            painter.drawArc(rect2, -90 * 16, -180 * 16)

        # ── Step 6: side extension lines (core_width = total width of coil) ──
        # Two long lines on each face of the main box, centred on box_h.
        # Length = right_panel_width (return side) and left_panel_width (header side)
        # but Step 6 says "length = total width" centred — meaning they extend
        # left and right by the plate widths.
        left_plate  = dims.left_panel_width    # header side
        right_plate = dims.right_panel_width   # return side
        fb_header   = dims.first_bend_header_side
        fb_return   = dims.first_bend_return_side
        blank_off_w = max(left_plate, min(dims.front_header_band_width, left_plate + fl))
        blank_off_bend_len = max(0.0, dims.first_bend_blank_off)

        # The main box top/bottom lines already drawn by drawRect.
        # Step 6: extend top line LEFT by left_plate and RIGHT by right_plate.
        top_y    = y0
        bottom_y = y0 + box_h

        # Left extensions (header side)
        hdr_left_x = x0 - left_plate
        painter.setPen(obj_pen)
        painter.drawLine(QPointF(hdr_left_x, top_y),    QPointF(x0, top_y))
        painter.drawLine(QPointF(hdr_left_x, bottom_y), QPointF(x0, bottom_y))

        # Right extensions (return side)
        ret_right_x = x0 + box_w + right_plate
        painter.drawLine(QPointF(x0 + box_w, top_y),    QPointF(ret_right_x, top_y))
        painter.drawLine(QPointF(x0 + box_w, bottom_y), QPointF(ret_right_x, bottom_y))

        # Vertical closing lines at flange ends
        painter.drawLine(QPointF(hdr_left_x, top_y),    QPointF(hdr_left_x, bottom_y))
        painter.drawLine(QPointF(ret_right_x, top_y),   QPointF(ret_right_x, bottom_y))

        # ── Steps 7-8: Header side first-bend lines ───────────────────────────
        # Step 7: 2 lines of length = Header Side Plate (already drawn as flange above)
        # Step 8: 2 tick lines at ends of header-side flange = First Bend length
        if fb_header > 0:
            fb_hdr_x = hdr_left_x - fb_header
            painter.drawLine(QPointF(fb_hdr_x, top_y),    QPointF(hdr_left_x, top_y))
            painter.drawLine(QPointF(fb_hdr_x, bottom_y), QPointF(hdr_left_x, bottom_y))
            # Vertical ticks
            painter.drawLine(QPointF(fb_hdr_x, top_y),    QPointF(fb_hdr_x, top_y    + fb_header * 0.4))
            painter.drawLine(QPointF(fb_hdr_x, bottom_y), QPointF(fb_hdr_x, bottom_y - fb_header * 0.4))
        else:
            fb_hdr_x = hdr_left_x

        # ── Steps 9-10: Return side first-bend lines ──────────────────────────
        if fb_return > 0:
            fb_ret_x = ret_right_x + fb_return
            painter.drawLine(QPointF(ret_right_x, top_y),    QPointF(fb_ret_x, top_y))
            painter.drawLine(QPointF(ret_right_x, bottom_y), QPointF(fb_ret_x, bottom_y))
            painter.drawLine(QPointF(fb_ret_x, top_y),    QPointF(fb_ret_x, top_y    + fb_return * 0.4))
            painter.drawLine(QPointF(fb_ret_x, bottom_y), QPointF(fb_ret_x, bottom_y - fb_return * 0.4))

        # ── Steps 11-12: Blank-off line + bend tick ───────────────────────────
        # Step 11: horizontal line from header-side bottom end, length = blank_off_w
        bo_start_x = hdr_left_x
        bo_end_x   = bo_start_x + blank_off_w        # extends rightward into fin area
        painter.drawLine(QPointF(bo_start_x, bottom_y), QPointF(bo_end_x, bottom_y))
        # Step 12: vertical tick downward = blank_off_bend
        if blank_off_bend_len > 0:
            painter.drawLine(QPointF(bo_start_x, bottom_y),
                             QPointF(bo_start_x, bottom_y + blank_off_bend_len))

        # ── Steps 13-15: Stub + header circles + header body ─────────────────
        # Step 13: from 1st and last dashed row lines, draw lines leftward
        #          length = stub_length + header_dia/2  (to reach circle centre)
        stub_len  = max(10.0, dims.left_pipe_length)
        hdr_dia   = max(2.0,  dims.header_dia)
        hdr_r     = hdr_dia / 2.0
        nozzle_proj = max(15.0, dims.nozzle_projection)
        hdr_ext   = max(nozzle_proj + 5.0, dims.header_extension_length)
        neck_h    = max(8.0, min(hdr_dia - 2.0, hdr_dia * 0.78))
        thread_len = min(28.0, max(16.0, nozzle_proj * 0.34))

        first_row_y = row_ys[0]
        last_row_y  = row_ys[-1]

        for ry in [first_row_y, last_row_y]:
            # Step 13: stub line from face_left going leftward
            stub_end_x   = hdr_left_x               # at the plate wall
            stub_start_x = stub_end_x - stub_len     # circle right tangent
            circle_cx    = stub_start_x - hdr_r      # circle centre
            circle_lx    = circle_cx    - hdr_r      # circle left tangent
            body_end_x   = circle_lx   - hdr_ext     # right edge of body rect
            body_start_x = body_end_x  - nozzle_proj # left edge of body rect
            neck_start_x = body_end_x
            neck_end_x   = circle_lx

            # Stub centre line
            painter.setPen(obj_pen)
            painter.drawLine(QPointF(stub_start_x, ry), QPointF(stub_end_x, ry))

            # Step 14: Header circle
            painter.drawEllipse(QPointF(circle_cx, ry), hdr_r, hdr_r)

            # Step 15: Header body rect + neck
            body_rect = QRectF(body_start_x, ry - hdr_dia / 2.0,
                               max(8.0, nozzle_proj), hdr_dia)
            painter.drawRect(body_rect)

            if neck_end_x > neck_start_x + 0.5:
                neck_rect = QRectF(neck_start_x, ry - neck_h / 2.0,
                                   max(2.0, neck_end_x - neck_start_x), neck_h)
                painter.drawRect(neck_rect)

            # Thread ribs on body
            rib_x = body_start_x + 4.0
            rib_end = min(body_start_x + thread_len, body_end_x - 2.0)
            while rib_x <= rib_end:
                painter.drawLine(QPointF(rib_x, body_rect.top()),
                                 QPointF(rib_x, body_rect.bottom()))
                rib_x += 6.0

            # Small centre dot on body
            painter.drawEllipse(QPointF(body_start_x + nozzle_proj * 0.62, ry), 2.4, 2.4)

            # IN / OUT label
            lbl = "IN" if ry == first_row_y else "OUT"
            painter.setFont(QFont("Arial", 10))
            painter.drawText(
                QRectF(body_start_x - 70.0, ry - 14.0, 60.0, 28.0),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                lbl,
            )

        # ── Step 16: Dimensions ───────────────────────────────────────────────
        dim_y_below = bottom_y + 50.0
        dim_y_below2 = bottom_y + 90.0
        dim_y_below3 = bottom_y + 130.0
        dim_y_above  = top_y - 45.0

        # Fin length
        self._dim_h(painter, x0, x0 + box_w, top_y, -45.0, f"{fl:.0f} (FL)")
        # Header side plate width
        self._dim_h(painter, hdr_left_x, x0, bottom_y, 48.0, f"{left_plate:.0f}")
        # Return side plate width
        self._dim_h(painter, x0 + box_w, ret_right_x, bottom_y, 48.0, f"{right_plate:.0f}")
        # Horizontal pitch (depth)
        self._dim_v(painter, top_y, top_y + hp, x0, -55.0, f"HP {hp:.2f}")
        # Total depth (box_h)
        self._dim_v(painter, top_y, bottom_y, ret_right_x, 50.0, f"{box_h:.0f}")
        # Stub length
        stub_end_x_dim   = hdr_left_x
        stub_start_x_dim = stub_end_x_dim - stub_len
        self._dim_h(painter, stub_start_x_dim, stub_end_x_dim, top_y, -45.0, f"{stub_len:.0f} (SL)")
        # Header dia
        circle_cx_dim = stub_start_x_dim - hdr_r
        self._dim_h(painter, circle_cx_dim - hdr_r, circle_cx_dim + hdr_r, top_y, -45.0, f"Ø{hdr_dia:.1f}")
        # Nozzle projection
        body_end_dim   = circle_cx_dim - hdr_r - hdr_ext
        body_start_dim = body_end_dim - nozzle_proj
        self._dim_h(painter, body_start_dim, body_end_dim, top_y, -45.0, f"{nozzle_proj:.0f}")

        # View label
        painter.setPen(obj_pen)
        self._draw_underlined_label(
            painter,
            QRectF(x0 - 150.0, bottom_y + 200.0, box_w + 300.0, 30.0),
            "TOP (DEPTH VIEW)",
        )

    def _draw_underlined_label(self, painter, rect, text):
        painter.save()
        painter.setPen(QPen(self.OBJECT_COLOR, self.OBJECT_LINE_WIDTH))
        painter.setFont(QFont("Arial", 13))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        lw = min(rect.width() * 0.22, 120.0)
        ly = rect.y() + rect.height() - 3.0
        cx = rect.x() + rect.width() / 2.0
        painter.drawLine(QPointF(cx - lw / 2.0, ly), QPointF(cx + lw / 2.0, ly))
        painter.restore()

    def _draw_notes(self, painter: QPainter, layout: dict) -> None:
        dims = self._dims
        nx = layout["return_end_x"]
        # Place notes below the top projection
        ny = layout["top_proj_y"] + layout["tp_h"] + 240.0
        painter.save()
        painter.setPen(QPen(self.OBJECT_COLOR, self.OBJECT_LINE_WIDTH))
        painter.setFont(QFont("Arial", 10))
        for i, line in enumerate([
            f"Job Order No.: {dims.job_order_no}",
            f"Coil Unique ID: {dims.coil_unique_id}",
            f"Coil Type: {dims.coil_type}",
            f"Connection: {dims.connection_side}",
        ]):
            painter.drawText(QRectF(nx, ny + i * 22.0, 460.0, 20.0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line)
        ty = ny + 4 * 22.0 + 18.0
        painter.setFont(QFont("Arial", 11))
        painter.drawText(QRectF(nx, ty, 460.0, 22.0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Notes:-")
        painter.setFont(QFont("Arial", 10))
        for i, line in enumerate([
            "1. FIN MATERIAL SHOULD BE PLAIN ALUMINIUM (0.11MM THICKNESS).",
            f"2. CASING MATERIAL SHOULD BE G.I. - {dims.sheet_metal_thickness:.2f}MM THICKNESS.",
            "3. 5/8\" COPPER TUBE WALL THICKNESS SHOULD BE 0.4 MM.",
        ]):
            painter.drawText(QRectF(nx, ty + 24.0 + i * 24.0, 600.0, 22.0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line)
        painter.restore()

    # ── Dimension helpers ─────────────────────────────────────────────────────

    def _internal_dim_h(self, painter, x1, x2, y, label):
        xl, xr = min(x1, x2), max(x1, x2)
        painter.save()
        painter.setPen(QPen(self.DIM_COLOR, self.DIM_LINE_WIDTH))
        painter.setFont(QFont("Arial", 10))
        painter.drawLine(QPointF(xl, y), QPointF(xr, y))
        self._arrowhead(painter, QPointF(xl, y), (-1.0, 0.0), 6.8)
        self._arrowhead(painter, QPointF(xr, y), (1.0, 0.0), 6.8)
        painter.drawText(QRectF(xl, y - 22.0, max(10.0, xr - xl), 18.0),
                         Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()

    def _dim_h(self, painter, x1, x2, y_ref, offset, label):
        xl, xr = min(x1, x2), max(x1, x2)
        y = y_ref + offset
        painter.save()
        painter.setPen(QPen(self.DIM_COLOR, self.DIM_LINE_WIDTH))
        painter.setFont(QFont("Arial", 10))
        painter.drawLine(QPointF(xl, y_ref), QPointF(xl, y))
        painter.drawLine(QPointF(xr, y_ref), QPointF(xr, y))
        painter.drawLine(QPointF(xl, y),     QPointF(xr, y))
        self._arrowhead(painter, QPointF(xl, y), (-1.0, 0.0))
        self._arrowhead(painter, QPointF(xr, y), (1.0, 0.0))
        ty = y - 21.0 if offset < 0 else y + 4.0
        painter.drawText(QRectF(xl, ty, max(10.0, xr - xl), 18.0),
                         Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()

    def _dim_v(self, painter, y1, y2, x_ref, offset, label):
        yt, yb = min(y1, y2), max(y1, y2)
        x = x_ref + offset
        painter.save()
        painter.setPen(QPen(self.DIM_COLOR, self.DIM_LINE_WIDTH))
        painter.setFont(QFont("Arial", 10))
        wg = 2.0
        wx = x_ref + wg if offset >= 0 else x_ref - wg
        painter.drawLine(QPointF(wx, yt), QPointF(x, yt))
        painter.drawLine(QPointF(wx, yb), QPointF(x, yb))
        painter.drawLine(QPointF(x,  yt), QPointF(x, yb))
        span = max(0.1, yb - yt)
        sz   = 7.5 if span >= 7.5 * 2.2 else max(2.8, span * 0.35)
        self._arrowhead(painter, QPointF(x, yt), (0.0, -1.0), sz)
        self._arrowhead(painter, QPointF(x, yb), (0.0,  1.0), sz)
        tx = x + (12.0 if offset >= 0 else -12.0)
        ty = yt - 16.0 if span <= 24.0 else (yt + yb) / 2.0
        painter.save()
        painter.translate(tx, ty)
        painter.rotate(-90.0 if offset >= 0 else 90.0)
        painter.drawText(QRectF(-28.0, -9.0, 56.0, 18.0), Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()
        painter.restore()

    def _arrowhead(self, painter, tip, direction, size=7.5):
        dx, dy = direction
        ln = math.hypot(dx, dy)
        if ln == 0:
            return
        dx /= ln; dy /= ln
        px, py = -dy, dx
        p1 = QPointF(tip.x() - dx * size + px * size * 0.45,
                     tip.y() - dy * size + py * size * 0.45)
        p2 = QPointF(tip.x() - dx * size - px * size * 0.45,
                     tip.y() - dy * size - py * size * 0.45)
        ob = painter.brush()
        painter.setBrush(painter.pen().color())
        painter.drawPolygon(QPolygonF([tip, p1, p2]))
        painter.setBrush(ob)

    def export_png(self, file_path: str) -> bool:
        dims = self._dims
        iw = int(max(1600, dims.return_plate_total_width * 3 + 800))
        ih = int(max(1200, dims.front_total_height * 2 + 600))
        img = QImage(iw, ih, QImage.Format.Format_ARGB32)
        img.fill(QColor("white"))
        p = QPainter(img)
        self.render_to_painter(p, QRectF(0.0, 0.0, float(iw), float(ih)), QColor("white"))
        p.end()
        return img.save(file_path)


# ═══════════════════════════════════════════════════════════════════════════════
#  Main Window
# ═══════════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Coil Helvix - SIDE VIEWS (Return End & Header Side)")
        self.resize(1580, 940)
        self.default_dims = CoilDimensions()
        self._spin_boxes: dict[str, QDoubleSpinBox] = {}
        self._direct_spin_boxes: dict[str, QDoubleSpinBox] = {}
        self._text_inputs: dict[str, QLineEdit] = {}
        self._connection_side_combo: QComboBox | None = None
        self._is_syncing_inputs = False
        self._is_syncing_direct_inputs = False
        self.drawing_widget = SideViewDrawingWidget(self.default_dims)
        self._fl_label  = QLabel()
        self._fh_label  = QLabel()
        self._rp_w_label  = QLabel()   # Return plate computed width
        self._rp_s_label  = QLabel()   # Return plate lifting hole side dist
        self._hp_w_label  = QLabel()   # Header plate computed width
        self._hp_s_label  = QLabel()   # Header plate lifting hole side dist
        self._hp_n_label  = QLabel()   # Header plate blank-off hole count
        self._zoom_label = QLabel("100%")
        self._build_ui()
        self._apply_changes()

    def _build_ui(self) -> None:
        sp = QSplitter(Qt.Orientation.Horizontal)
        sp.addWidget(self._build_controls_panel())
        sp.addWidget(self.drawing_widget)
        sp.setStretchFactor(1, 1)
        sp.setSizes([360, 1200])
        self.setCentralWidget(sp)

    def _build_controls_panel(self) -> QWidget:
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)
        for grp in [self._build_identity_group(), self._build_main_specs_group(),
                    self._build_pitch_group(),     self._build_plate_group(),
                    self._build_first_bend_group(),self._build_additional_group(),
                    self._build_direct_group(),    self._build_derived_group()]:
            lay.addWidget(grp)
        lay.addLayout(self._build_buttons_row())
        lay.addLayout(self._build_zoom_row())
        lay.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.setMinimumWidth(330)
        return scroll

    # ── Group builders ────────────────────────────────────────────────────────

    def _build_identity_group(self):
        g = QGroupBox("Order Details"); f = QFormLayout(g)
        self._add_text(f, "job_order_no",   "Job Order No.",  self.default_dims.job_order_no)
        self._add_text(f, "coil_unique_id", "Coil Unique ID", self.default_dims.coil_unique_id)
        self._add_text(f, "coil_type",      "Coil Type",      self.default_dims.coil_type)
        return g

    def _build_main_specs_group(self):
        g = QGroupBox("Main Specs"); f = QFormLayout(g)
        self._add_dspin(f, "fin_length_direct","Fin Length",       self.default_dims.fin_length, 20.0, 6000.0)
        self._add_spin(f,  "tubes_per_row",    "Tubes per row",    self.default_dims.tubes_per_row, 1, 300, 0)
        self._add_spin(f,  "number_of_rows",   "No. of Rows",      self.default_dims.number_of_rows, 1, 40, 0)
        self._add_spin(f,  "number_of_circuits","No. of Circuits", self.default_dims.number_of_circuits, 1, 100, 0)
        self._add_spin(f,  "fpi",              "FPI",              self.default_dims.fpi, 1, 60, 0)
        self._add_spin(f,  "tube_dia_inch",    "Tube Dia (inch)",  self.default_dims.tube_dia_inch, 0.1, 2.0, 3)
        self._add_spin(f,  "header_dia",       "Header Dia",       self.default_dims.header_dia, 2.0, 500.0)
        return g

    def _build_pitch_group(self):
        g = QGroupBox("Pitch"); f = QFormLayout(g)
        self._add_spin(f, "top_feature_tube_dia",         "Tube Dia",     self.default_dims.top_feature_tube_dia, 2.0, 80.0, 2)
        self._add_spin(f, "top_feature_pitch_vertical",   "Vertical",     self.default_dims.top_feature_pitch_vertical, 5.0, 200.0, 2)
        self._add_spin(f, "top_feature_pitch_horizontal", "Horizontal",   self.default_dims.top_feature_pitch_horizontal, 5.0, 200.0, 2)
        self._add_spin(f, "top_feature_circle_1_dia",     "Circle 1 Dia", self.default_dims.top_feature_circle_1_dia, 2.0, 80.0, 2)
        self._add_spin(f, "top_feature_circle_2_dia",     "Circle 2 Dia", self.default_dims.top_feature_circle_2_dia, 2.0, 80.0, 2)
        return g

    def _build_plate_group(self):
        g = QGroupBox("Plate / Overall"); f = QFormLayout(g)
        self._add_spin(f, "sheet_metal_thickness",    "Sheet Metal Thickness",  self.default_dims.sheet_metal_thickness, 0.5, 10.0, 2)
        self._add_spin(f, "right_panel_width",        "Return Side Plate",      self.default_dims.right_panel_width, 5, 2000)
        self._add_spin(f, "left_panel_width",         "Header Side Plate",      self.default_dims.left_panel_width, 5, 2000)
        # Side-view circles (separate inputs)
        self._add_spin(f, "side_plate_outer_circle_dia", "Side Outer Circle Ø", self.default_dims.side_plate_outer_circle_dia, 2.0, 80.0, 2)
        self._add_spin(f, "side_plate_inner_circle_dia", "Side Inner Circle Ø", self.default_dims.side_plate_inner_circle_dia, 2.0, 80.0, 2)
        self._add_spin(f, "top_plate",                "Top Plate",              self.default_dims.top_plate, 5, 1000)
        self._add_spin(f, "bottom_plate",             "Bottom Plate",           self.default_dims.bottom_plate, 5, 1000)
        self._add_spin(f, "front_header_band_width",  "Blank Off Width",        self.default_dims.front_header_band_width, 20, 3000)
        self._add_spin(f, "core_width",               "Total Width (Core)",     self.default_dims.core_width, 60, 3000)
        self._add_spin(f, "front_total_height",       "Total Height",           self.default_dims.front_total_height, 200, 6000)
        self._spin_boxes["front_total_height"].setReadOnly(True)
        self._spin_boxes["front_total_height"].setToolTip("Calculated: (TPR × VP) + Top Plate + Bottom Plate")
        self._add_spin(f, "left_pipe_offset", "Header Extension", self.default_dims.left_pipe_offset, 0, 2000)
        return g

    def _build_first_bend_group(self):
        g = QGroupBox("First Bend"); f = QFormLayout(g)
        self._add_spin(f, "first_bend_header_side",       "Header Side Plate",  self.default_dims.first_bend_header_side, 0, 200)
        self._add_spin(f, "first_bend_return_side",       "Return Side Plate",  self.default_dims.first_bend_return_side, 0, 200)
        self._add_spin(f, "first_bend_top_plate",         "Top Plate",          self.default_dims.first_bend_top_plate, 0, 200)
        self._add_spin(f, "first_bend_bottom_plate",      "Bottom Plate",       self.default_dims.first_bend_bottom_plate, 0, 200)
        self._add_spin(f, "first_bend_blank_off",         "Blank Off",          self.default_dims.first_bend_blank_off, 0, 200)
        self._add_spin(f, "first_bend_intermediate_plate","Intermediate Plate", self.default_dims.first_bend_intermediate_plate, 0, 200)
        return g

    def _build_additional_group(self):
        g = QGroupBox("Additional Inputs"); f = QFormLayout(g)
        self._add_spin(f, "top_total_length",      "Top Total Length",      self.default_dims.top_total_length, 500, 6000)
        self._spin_boxes["top_total_length"].setReadOnly(True)
        self._add_spin(f, "top_intermediate_length","Top Intermediate Len", self.default_dims.top_intermediate_length, 100, 6000)
        self._spin_boxes["top_intermediate_length"].setReadOnly(True)
        self._add_spin(f, "front_total_width",     "Front Total Width",     self.default_dims.front_total_width, 200, 6000)
        self._spin_boxes["front_total_width"].setReadOnly(True)
        self._add_spin(f, "left_pipe_length",      "Stub Length",           self.default_dims.left_pipe_length, 10, 3000)
        self._add_spin(f, "nozzle_projection",     "Nozzle Projection",     self.default_dims.nozzle_projection, 10, 500)
        self._add_spin(f, "header_extension_length","Header Ext. Length",   self.default_dims.header_extension_length, 20, 3000)
        self._add_spin(f, "header_box_height",     "Header Box Height",     self.default_dims.header_box_height, 40, 2000)
        self._spin_boxes["header_box_height"].setReadOnly(True)
        self._add_spin(f, "right_cap_thickness",   "Header Flange 1st Bend",self.default_dims.right_cap_thickness, 2, 400)
        self._add_spin(f, "circle_diameter",       "Circle Diameter",       self.default_dims.circle_diameter, 2.0, 40.0, 2)
        self._add_spin(f, "blank_off_bend",        "Blank Off Bend",        self.default_dims.blank_off_bend, 0.0, 200.0)
        self._add_spin(f, "top_feature_tube_height","Feature Tube Height",  self.default_dims.top_feature_tube_height, 10.0, 400.0, 2)
        self._spin_boxes["top_feature_tube_height"].setReadOnly(True)
        self._add_spin(f, "top_feature_pipe_length","Feature Pipe Length",  self.default_dims.top_feature_pipe_length, 2.0, 200.0, 2)
        cb = QComboBox()
        cb.addItems(["LHS", "RHS"])
        cb.setCurrentText(self.default_dims.connection_side)
        cb.currentTextChanged.connect(self._apply_changes)
        self._connection_side_combo = cb
        f.addRow("Connection", cb)
        return g

    def _build_derived_group(self):
        g = QGroupBox("Derived / Computed")
        f = QFormLayout(g)
        f.addRow("Fin Length (FL)",         self._fl_label)
        f.addRow("Fin Height (FH)",         self._fh_label)
        f.addRow("Return Plate Width",       self._rp_w_label)
        f.addRow("Return Lifting Side Dist", self._rp_s_label)
        f.addRow("Header Plate Width",       self._hp_w_label)
        f.addRow("Header Lifting Side Dist", self._hp_s_label)
        f.addRow("Header Blank-off Holes",   self._hp_n_label)
        return g

    def _build_direct_group(self):
        g = QGroupBox("Direct Dimension Edit"); f = QFormLayout(g)
        self._add_dspin(f, "top_lead_span",    "Top Lead Span",  self.default_dims.top_lead_span, 20.0, 6000.0)
        self._direct_spin_boxes["top_lead_span"].setReadOnly(True)
        self._add_dspin(f, "fin_height_direct","Fin Height (FH)",self.default_dims.fin_height, 20.0, 6000.0)
        return g

    def _build_buttons_row(self):
        lay = QHBoxLayout()
        for lbl, slot in [("Apply", self._apply_changes), ("Reset", self._reset_defaults),
                          ("Print", self._print_drawing),  ("Export PNG", self._export_png)]:
            b = QPushButton(lbl); b.clicked.connect(slot); lay.addWidget(b)
        return lay

    def _build_zoom_row(self):
        lay = QHBoxLayout()
        zm = QPushButton("Zoom -"); zp = QPushButton("Zoom +"); zr = QPushButton("Reset View")
        zm.clicked.connect(lambda: self._do_zoom(-1))
        zp.clicked.connect(lambda: self._do_zoom(1))
        zr.clicked.connect(self._zoom_reset)
        self._zoom_label.setMinimumWidth(55)
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for w in [zm, zp, zr, self._zoom_label]:
            lay.addWidget(w)
        return lay

    def _do_zoom(self, d):
        self.drawing_widget.zoom_by(1.15 if d > 0 else 1.0 / 1.15)
        self._zoom_label.setText(f"{self.drawing_widget.zoom_percent()}%")

    def _zoom_reset(self):
        self.drawing_widget.reset_view()
        self._zoom_label.setText(f"{self.drawing_widget.zoom_percent()}%")

    # ── Widget factories ──────────────────────────────────────────────────────

    def _add_spin(self, form, key, label, default_value, minimum, maximum, decimals=1):
        s = QDoubleSpinBox()
        s.setDecimals(decimals); s.setRange(minimum, maximum); s.setValue(default_value)
        s.setSingleStep(1.0); s.setKeyboardTracking(False)
        s.valueChanged.connect(self._apply_changes)
        self._spin_boxes[key] = s; form.addRow(label, s)

    def _add_dspin(self, form, key, label, default_value, minimum, maximum, decimals=1):
        s = QDoubleSpinBox()
        s.setDecimals(decimals); s.setRange(minimum, maximum); s.setValue(default_value)
        s.setSingleStep(1.0); s.setKeyboardTracking(False)
        s.valueChanged.connect(self._apply_direct_changes)
        self._direct_spin_boxes[key] = s; form.addRow(label, s)

    def _add_text(self, form, key, label, default_value):
        t = QLineEdit(); t.setText(str(default_value))
        t.textChanged.connect(self._apply_changes)
        self._text_inputs[key] = t; form.addRow(label, t)

    # ── Dimension collection ──────────────────────────────────────────────────

    def _collect_dimensions(self) -> CoilDimensions:
        conn  = self._connection_side_combo.currentText() if self._connection_side_combo else self.default_dims.connection_side
        job   = self._text_inputs.get("job_order_no",   QLineEdit()).text() or self.default_dims.job_order_no
        uid   = self._text_inputs.get("coil_unique_id", QLineEdit()).text() or self.default_dims.coil_unique_id
        ctype = self._text_inputs.get("coil_type",      QLineEdit()).text() or self.default_dims.coil_type
        tp    = self._spin_boxes["top_plate"].value()
        bp    = self._spin_boxes["bottom_plate"].value()
        tpr   = self._spin_boxes["tubes_per_row"].value()
        vp    = self._spin_boxes["top_feature_pitch_vertical"].value()
        hp    = self._spin_boxes["top_feature_pitch_horizontal"].value()
        nor   = self._spin_boxes["number_of_rows"].value()
        lpo   = self._spin_boxes["left_pipe_offset"].value()
        lpw   = self._spin_boxes["left_panel_width"].value()
        rpw   = self._spin_boxes["right_panel_width"].value()
        fl    = max(20.0, self._direct_spin_boxes["fin_length_direct"].value())
        ftw   = lpw + fl + rpw
        fhbw  = self._spin_boxes["front_header_band_width"].value()
        bow   = max(lpw, min(fhbw, lpw + fl))
        til   = max(100.0, ftw - lpw + bow)
        ttl   = max(500.0, lpo + til)
        fbb   = self._spin_boxes["first_bend_blank_off"].value()
        cur   = getattr(self.drawing_widget, "_dims", self.default_dims)
        return CoilDimensions(
            top_total_length=max(self._spin_boxes["top_total_length"].value(), ttl),
            top_intermediate_length=til, front_total_width=ftw,
            front_total_height=tpr * vp + tp + bp,
            left_panel_width=lpw, right_panel_width=rpw, fin_length_override=fl,
            top_bottom_margin=(tp + bp) / 2.0, top_plate=tp, bottom_plate=bp,
            core_width=self._spin_boxes["core_width"].value(),
            left_pipe_offset=lpo,
            left_pipe_length=self._spin_boxes["left_pipe_length"].value(),
            nozzle_projection=self._spin_boxes["nozzle_projection"].value(),
            header_extension_length=self._spin_boxes["header_extension_length"].value(),
            header_box_height=hp * nor,
            right_cap_thickness=self._spin_boxes["right_cap_thickness"].value(),
            front_header_band_width=fhbw,
            top_small_offset_1=cur.top_small_offset_1,
            top_small_offset_2=cur.top_small_offset_2,
            fpi=self._spin_boxes["fpi"].value(),
            tube_dia_inch=self._spin_boxes["tube_dia_inch"].value(),
            pitch_vertical=vp, pitch_horizontal=hp,
            connection_side=conn, job_order_no=job, coil_unique_id=uid, coil_type=ctype,
            circle_diameter=self._spin_boxes["circle_diameter"].value(),
            tubes_per_row=tpr, number_of_rows=nor,
            number_of_circuits=self._spin_boxes["number_of_circuits"].value(),
            header_dia=self._spin_boxes["header_dia"].value(),
            blank_off_bend=fbb,
            top_feature_tube_dia=self._spin_boxes["top_feature_tube_dia"].value(),
            top_feature_tube_height=hp * (nor - 1.0),
            top_feature_pipe_length=self._spin_boxes["top_feature_pipe_length"].value(),
            top_feature_pitch_vertical=vp, top_feature_pitch_horizontal=hp,
            top_feature_circle_1_dia=self._spin_boxes["top_feature_circle_1_dia"].value(),
            top_feature_circle_2_dia=self._spin_boxes["top_feature_circle_2_dia"].value(),
            side_plate_outer_circle_dia=self._spin_boxes["side_plate_outer_circle_dia"].value(),
            side_plate_inner_circle_dia=self._spin_boxes["side_plate_inner_circle_dia"].value(),
            sheet_metal_thickness=self._spin_boxes["sheet_metal_thickness"].value(),
            first_bend_header_side=self._spin_boxes["first_bend_header_side"].value(),
            first_bend_return_side=self._spin_boxes["first_bend_return_side"].value(),
            first_bend_top_plate=self._spin_boxes["first_bend_top_plate"].value(),
            first_bend_bottom_plate=self._spin_boxes["first_bend_bottom_plate"].value(),
            first_bend_blank_off=fbb,
            first_bend_intermediate_plate=self._spin_boxes["first_bend_intermediate_plate"].value(),
        )

    # ── Apply / sync ──────────────────────────────────────────────────────────

    def _apply_changes(self) -> None:
        if self._is_syncing_inputs:
            return
        dims = self._collect_dimensions().sanitized()
        self._sync_spins(dims)
        self._sync_dspins(dims)
        self._fl_label.setText(f"{dims.fin_length:.1f}")
        self._fh_label.setText(f"{dims.fin_height:.1f}")
        self._rp_w_label.setText(f"{dims.return_plate_total_width:.1f} mm")
        self._rp_s_label.setText(f"{dims.return_plate_lifting_hole_side_dist:.1f} mm")
        self.drawing_widget.set_dimensions(dims)
        self._zoom_label.setText(f"{self.drawing_widget.zoom_percent()}%")

    def _apply_direct_changes(self) -> None:
        if self._is_syncing_direct_inputs or self._is_syncing_inputs:
            return
        dims = self._collect_dimensions().sanitized()
        fl   = self._direct_spin_boxes["fin_length_direct"].value()
        fh   = self._direct_spin_boxes["fin_height_direct"].value()
        dims.fin_length_override = max(20.0, fl)
        dims.front_total_width   = dims.left_panel_width + dims.fin_length + dims.right_panel_width
        tps  = max(10.0, dims.front_total_height - fh)
        prev = max(0.001, dims.top_plate + dims.bottom_plate)
        tr   = max(0.0, min(dims.top_plate / prev, 1.0))
        dims.top_plate    = tps * tr
        dims.bottom_plate = tps - dims.top_plate
        dims.top_bottom_margin = (dims.top_plate + dims.bottom_plate) / 2.0
        dims = dims.sanitized()
        self._sync_spins(dims)
        self._apply_changes()

    def _sync_spins(self, dims: CoilDimensions) -> None:
        vals = {
            "top_total_length": dims.top_total_length,
            "top_intermediate_length": dims.top_intermediate_length,
            "front_total_width": dims.front_total_width,
            "front_total_height": dims.front_total_height,
            "left_panel_width": dims.left_panel_width,
            "right_panel_width": dims.right_panel_width,
            "top_plate": dims.top_plate, "bottom_plate": dims.bottom_plate,
            "core_width": dims.core_width, "left_pipe_offset": dims.left_pipe_offset,
            "left_pipe_length": dims.left_pipe_length,
            "nozzle_projection": dims.nozzle_projection,
            "header_extension_length": dims.header_extension_length,
            "header_box_height": dims.header_box_height,
            "right_cap_thickness": dims.right_cap_thickness,
            "front_header_band_width": dims.front_header_band_width,
            "fpi": dims.fpi, "tube_dia_inch": dims.tube_dia_inch,
            "circle_diameter": dims.circle_diameter,
            "tubes_per_row": dims.tubes_per_row, "number_of_rows": dims.number_of_rows,
            "number_of_circuits": dims.number_of_circuits, "header_dia": dims.header_dia,
            "blank_off_bend": dims.blank_off_bend,
            "top_feature_tube_dia": dims.top_feature_tube_dia,
            "top_feature_tube_height": dims.top_feature_tube_height,
            "top_feature_pipe_length": dims.top_feature_pipe_length,
            "top_feature_pitch_vertical": dims.top_feature_pitch_vertical,
            "top_feature_pitch_horizontal": dims.top_feature_pitch_horizontal,
            "top_feature_circle_1_dia": dims.top_feature_circle_1_dia,
            "top_feature_circle_2_dia": dims.top_feature_circle_2_dia,
            "side_plate_outer_circle_dia": dims.side_plate_outer_circle_dia,
            "side_plate_inner_circle_dia": dims.side_plate_inner_circle_dia,
            "sheet_metal_thickness": dims.sheet_metal_thickness,
            "first_bend_header_side": dims.first_bend_header_side,
            "first_bend_return_side": dims.first_bend_return_side,
            "first_bend_top_plate": dims.first_bend_top_plate,
            "first_bend_bottom_plate": dims.first_bend_bottom_plate,
            "first_bend_blank_off": dims.first_bend_blank_off,
            "first_bend_intermediate_plate": dims.first_bend_intermediate_plate,
        }
        self._is_syncing_inputs = True
        try:
            for k, v in vals.items():
                s = self._spin_boxes.get(k)
                if s and abs(s.value() - v) > 1e-6:
                    s.blockSignals(True); s.setValue(v); s.blockSignals(False)
        finally:
            self._is_syncing_inputs = False

    def _sync_dspins(self, dims: CoilDimensions) -> None:
        vals = {"top_lead_span": dims.top_lead_span,
                "fin_length_direct": dims.fin_length,
                "fin_height_direct": dims.fin_height}
        self._is_syncing_direct_inputs = True
        try:
            for k, v in vals.items():
                s = self._direct_spin_boxes.get(k)
                if s and abs(s.value() - v) > 1e-6:
                    s.blockSignals(True); s.setValue(v); s.blockSignals(False)
        finally:
            self._is_syncing_direct_inputs = False

    def _reset_defaults(self) -> None:
        self._sync_spins(self.default_dims.sanitized())
        self._apply_changes()

    def _print_drawing(self) -> None:
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        p = QPainter(printer)
        self.drawing_widget.render_to_painter(p, QRectF(p.viewport()), QColor("white"))
        p.end()

    def _export_png(self) -> None:
        fp, _ = QFileDialog.getSaveFileName(self, "Export Side Views", "side_views.png", "PNG Image (*.png)")
        if not fp:
            return
        if not fp.lower().endswith(".png"):
            fp += ".png"
        if not self.drawing_widget.export_png(fp):
            QMessageBox.warning(self, "Export Failed", "Could not save PNG.")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Coil Helvix - Side Views")
    access_ok, msg = _enforce_startup_access()
    if not access_ok:
        if msg:
            QMessageBox.critical(None, "Access Denied", msg)
        sys.exit(1)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
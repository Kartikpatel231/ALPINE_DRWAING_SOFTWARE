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
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPolygonF, QTransform
from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QInputDialog,
    QLineEdit, QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget,
)

try:
    import ezdxf
except Exception:
    ezdxf = None

try:
    from ezdxf.enums import TextEntityAlignment
except Exception:
    TextEntityAlignment = None

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
    entered_hash = hashlib.sha256(entered.encode("utf-8")).hexdigest().lower()
    return hmac.compare_digest(entered_hash, expected)


def _enforce_startup_access() -> tuple[bool, str | None]:
    first_run = _load_or_create_first_run()
    expiry = _resolve_expiry_datetime(first_run)
    now = datetime.now(timezone.utc)
    if now <= expiry:
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
        blank_off_w = max(self.left_panel_width, min(self.front_header_band_width, self.left_panel_width + self.fin_length))
        return max(100.0, self.front_total_width - self.left_panel_width + blank_off_w)

    @property
    def calculated_top_total_length(self) -> float:
        return max(500.0, self.left_pipe_offset + self.top_intermediate_length)

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
        margin_limit = (v.front_total_height / 2.0) - 10.0
        legacy_margin = max(5.0, min(v.top_bottom_margin, margin_limit))
        if (abs(v.top_plate - CoilDimensions.top_plate) < 1e-6
                and abs(v.bottom_plate - CoilDimensions.bottom_plate) < 1e-6
                and abs(legacy_margin - CoilDimensions.top_bottom_margin) > 1e-6):
            v.top_plate = legacy_margin
            v.bottom_plate = legacy_margin
        v.top_plate = max(5.0, min(v.top_plate, margin_limit))
        v.bottom_plate = max(5.0, min(v.bottom_plate, margin_limit))
        pair_limit = max(10.0, v.front_total_height - 20.0)
        pair_total = v.top_plate + v.bottom_plate
        if pair_total > pair_limit:
            ratio = pair_limit / pair_total
            v.top_plate = max(5.0, v.top_plate * ratio)
            v.bottom_plate = max(5.0, v.bottom_plate * ratio)
        v.top_bottom_margin = (v.top_plate + v.bottom_plate) / 2.0
        min_header = v.left_panel_width + 20.0
        v.front_header_band_width = max(min_header, min(v.front_header_band_width, v.front_total_width - 20.0))
        v.top_intermediate_length = v.calculated_top_intermediate_length
        v.top_total_length = max(min_top_total, v.calculated_top_total_length)
        v.left_pipe_offset = max(0.0, min(v.left_pipe_offset, 3000.0))
        v.left_pipe_length = max(10.0, min(v.left_pipe_length, 3000.0))
        v.nozzle_projection = max(15.0, v.nozzle_projection)
        v.header_extension_length = max(v.nozzle_projection + 5.0, v.header_extension_length)
        v.right_cap_thickness = max(2.0, min(v.right_cap_thickness, v.core_width / 2.0))
        each_limit = max(5.0, v.core_width - 2.0 * v.right_cap_thickness - 10.0)
        v.top_small_offset_1 = max(5.0, min(v.top_small_offset_1, each_limit))
        v.top_small_offset_2 = max(5.0, min(v.top_small_offset_2, each_limit))
        pair_lim2 = max(12.0, v.core_width - 2.0 * v.right_cap_thickness - 20.0)
        pt = v.top_small_offset_1 + v.top_small_offset_2
        if pt > pair_lim2:
            r = pair_lim2 / pt
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
        v.sheet_metal_thickness = max(0.5, min(v.sheet_metal_thickness, 10.0))
        for attr in ("first_bend_header_side","first_bend_return_side","first_bend_top_plate",
                     "first_bend_bottom_plate","first_bend_blank_off","first_bend_intermediate_plate"):
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


class FrontViewDrawingWidget(QWidget):
    BACKGROUND = QColor("#f2f2f2")
    OBJECT_COLOR = QColor("#111111")
    DIM_COLOR = QColor("#ff6a00")
    ACCENT_GREEN = QColor("#12b312")
    OBJECT_LINE_WIDTH = 1.7
    DIM_LINE_WIDTH = 1.05

    def __init__(self, dimensions: CoilDimensions | None = None) -> None:
        super().__init__()
        self._dims = (dimensions or CoilDimensions()).sanitized()
        self._zoom = 1.0
        self._min_zoom = 0.25
        self._max_zoom = 6.0
        self._pan_offset = QPointF(0.0, 0.0)
        self._is_panning = False
        self._last_pan_pos: QPointF | None = None
        self.setMinimumSize(800, 700)

    def set_dimensions(self, dimensions: CoilDimensions) -> None:
        self._dims = dimensions.sanitized()
        self.update()

    def zoom_by(self, factor: float) -> None:
        clamped = max(self._min_zoom, min(self._zoom * factor, self._max_zoom))
        if abs(clamped - self._zoom) > 1e-6:
            self._zoom = clamped
            self.update()

    def reset_view(self) -> None:
        self._zoom = 1.0
        self._pan_offset = QPointF(0.0, 0.0)
        self.update()

    def zoom_percent(self) -> int:
        return int(round(self._zoom * 100.0))

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        self.render_to_painter(painter, QRectF(self.rect()), self.BACKGROUND, apply_view_transform=True)

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        layout = self._layout_data()
        rect = QRectF(self.rect())
        bs, box, boy = self._calc_transform(rect, layout["world_w"], layout["world_h"], True)
        cursor = event.position()
        wx = (cursor.x() - box) / bs
        wy = (cursor.y() - boy) / bs
        factor = 1.12 if delta > 0 else 1.0 / 1.12
        old = self._zoom
        self._zoom = max(self._min_zoom, min(self._zoom * factor, self._max_zoom))
        if abs(self._zoom - old) < 1e-6:
            event.accept()
            return
        ns, nox, noy = self._calc_transform(rect, layout["world_w"], layout["world_h"], True)
        ncx = nox + wx * ns
        ncy = noy + wy * ns
        self._pan_offset = QPointF(self._pan_offset.x() + cursor.x() - ncx, self._pan_offset.y() + cursor.y() - ncy)
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

    def render_to_painter(self, painter: QPainter, target_rect: QRectF, background: QColor, apply_view_transform: bool = False) -> None:
        if not isinstance(target_rect, QRectF):
            target_rect = QRectF(target_rect)
        layout = self._layout_data()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.fillRect(target_rect, background)
        scale, ox, oy = self._calc_transform(target_rect, layout["world_w"], layout["world_h"], apply_view_transform)
        painter.translate(ox, oy)
        painter.scale(scale, scale)
        self._draw_front_view(painter, layout)
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
        margin_top = 80.0
        margin_left = 60.0
        world_w = margin_left + dims.front_total_width + 220.0
        world_h = margin_top + dims.front_total_height + 220.0
        return {"x": margin_left, "y": margin_top, "world_w": world_w, "world_h": world_h}

    def _draw_front_view(self, painter: QPainter, layout: dict) -> None:
        dims = self._dims
        x = layout["x"]
        y = layout["y"]

        fin_w = max(20.0, dims.fin_length)
        total_h = dims.front_total_height
        top_plate = dims.top_plate
        bottom_plate = dims.bottom_plate
        header_side_w = dims.left_panel_width
        return_side_w = dims.right_panel_width
        blank_off_w = max(header_side_w, min(dims.front_header_band_width, header_side_w + fin_w))
        left_extension_w = max(0.0, blank_off_w - header_side_w)

        outer_left = x
        outer_top = y
        outer_bottom = outer_top + total_h

        face_left = outer_left + left_extension_w
        fin_left = outer_left + blank_off_w
        fin_right = fin_left + fin_w
        outer_right = fin_right + return_side_w

        fin_top = outer_top + top_plate
        fin_bottom = outer_bottom - bottom_plate
        fin_h = max(0.0, fin_bottom - fin_top)

        object_pen = QPen(self.OBJECT_COLOR, self.OBJECT_LINE_WIDTH)
        painter.setPen(object_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Outer frame
        painter.drawRect(QRectF(outer_left, outer_top, outer_right - outer_left, total_h))
        # Left side and right side plate strips
        painter.drawRect(QRectF(face_left, outer_top, header_side_w, total_h))
        painter.drawRect(QRectF(fin_right, outer_top, return_side_w, total_h))
        # Blank-off section
        painter.drawRect(QRectF(outer_left, outer_top, blank_off_w, total_h))
        # Top and bottom plates over fin length
        painter.drawRect(QRectF(fin_left, outer_top, fin_w, top_plate))
        painter.drawRect(QRectF(fin_left, outer_bottom - bottom_plate, fin_w, bottom_plate))
        # Key edges
        painter.drawLine(QPointF(face_left, outer_top), QPointF(face_left, outer_bottom))
        painter.drawLine(QPointF(fin_left, outer_top), QPointF(fin_left, outer_bottom))
        painter.drawLine(QPointF(fin_right, outer_top), QPointF(fin_right, outer_bottom))
        painter.drawLine(QPointF(fin_left, fin_top), QPointF(fin_right, fin_top))
        painter.drawLine(QPointF(fin_left, fin_bottom), QPointF(fin_right, fin_bottom))

        # Ellipse centred at fin centre
        center_x = fin_left + fin_w / 2.0
        center_y = outer_top + total_h / 2.0
        ellipse_w = max(90.0, min(280.0, fin_w * 0.42))
        ellipse_h = max(50.0, min(170.0, max(1.0, fin_h) * 0.32))

        ellipse_base = QPainterPath()
        ellipse_base.addEllipse(QRectF(-ellipse_w / 2.0, -ellipse_h / 2.0, ellipse_w, ellipse_h))
        transform = QTransform()
        transform.translate(center_x, center_y)
        transform.rotate(35.0)
        ellipse_path = transform.map(ellipse_base)

        painter.save()
        painter.setPen(QPen(self.OBJECT_COLOR, 1.8))
        painter.drawPath(ellipse_path)

        # FPI lines clipped inside ellipse
        painter.setClipPath(ellipse_path)
        painter.setPen(QPen(self.ACCENT_GREEN, 1.5))
        fin_pitch = 25.4 / max(1.0, dims.fpi)
        lx = center_x - ellipse_w / 2.0
        lx_end = center_x + ellipse_w / 2.0
        count = 0
        while lx <= lx_end and count < 4000:
            painter.drawLine(QPointF(lx, fin_top), QPointF(lx, fin_bottom))
            lx += fin_pitch
            count += 1
        painter.restore()

        # FPI label
        painter.setPen(object_pen)
        text_x = center_x + 18.0
        text_y = center_y - 98.0
        painter.drawText(QRectF(text_x - 70.0, text_y - 18.0, 140.0, 35.0), Qt.AlignmentFlag.AlignCenter, f"{dims.fpi:.0f} FPI")

        # FPI leader arrow
        leader_tip = QPointF(center_x + 28.0, center_y - 16.0)
        leader_start = QPointF(text_x + 2.0, text_y + 18.0)
        painter.save()
        painter.setPen(QPen(self.DIM_COLOR, self.DIM_LINE_WIDTH))
        painter.drawLine(leader_start, leader_tip)
        self._draw_arrow_head(painter, leader_tip, (leader_tip.x() - leader_start.x(), leader_tip.y() - leader_start.y()), 6.2)
        painter.restore()

        # Dimensions
        if blank_off_w > 0.001:
            self._draw_dim_h(painter, outer_left, fin_left, outer_top, -45.0, f"{blank_off_w:.0f}")
        self._draw_dim_h(painter, face_left, fin_left, outer_bottom, 45.0, f"{header_side_w:.0f}")
        self._draw_dim_h(painter, fin_left, fin_right, outer_bottom, 45.0, f"{fin_w:.0f} (FL)")
        self._draw_dim_h(painter, fin_right, outer_right, outer_bottom, 45.0, f"{return_side_w:.0f}")
        self._draw_dim_h(painter, face_left, outer_right, outer_bottom, 122.0, f"{dims.front_total_width:.0f}")
        self._draw_dim_v(painter, fin_top, fin_bottom, outer_right, 50.0, f"{fin_h:.0f}", text_vertical=True)
        self._draw_dim_v(painter, outer_top, outer_bottom, outer_right, 85.0, f"{total_h:.0f}", text_vertical=True)
        self._draw_dim_v(painter, outer_top, outer_top + top_plate, outer_right, 129.0, f"{top_plate:.0f}", text_vertical=True)
        self._draw_dim_v(painter, outer_bottom - bottom_plate, outer_bottom, outer_right, 129.0, f"{bottom_plate:.0f}", text_vertical=True)

        # Notes block
        painter.setPen(object_pen)
        self._draw_underlined_label(painter, QRectF(outer_left, outer_bottom + 120.0, outer_right - outer_left, 30.0), "FRONT")

        # Info block below label
        notes_x = outer_left
        notes_y = outer_bottom + 168.0
        painter.setFont(QFont("Arial", 10))
        info_lines = [
            f"Job Order No.: {dims.job_order_no}",
            f"Coil Unique ID: {dims.coil_unique_id}",
            f"Coil Type: {dims.coil_type}",
            f"Connection: {dims.connection_side}",
        ]
        for i, line in enumerate(info_lines):
            painter.drawText(QRectF(notes_x, notes_y + i * 22.0, 400.0, 20.0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line)

        notes_title_y = notes_y + len(info_lines) * 22.0 + 18.0
        painter.setFont(QFont("Arial", 11))
        painter.drawText(QRectF(notes_x, notes_title_y, 400.0, 22.0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Notes:-")
        painter.setFont(QFont("Arial", 10))
        note_lines = [
            "1. FIN MATERIAL SHOULD BE PLAIN ALUMINIUM (0.11MM THICKNESS).",
            f"2. CASING MATERIAL SHOULD BE G.I. - {dims.sheet_metal_thickness:.2f}MM THICKNESS.",
            "3. 5/8\" COPPER TUBE WALL THICKNESS SHOULD BE 0.4 MM.",
        ]
        for i, line in enumerate(note_lines):
            painter.drawText(QRectF(notes_x, notes_title_y + 24.0 + i * 24.0, 500.0, 22.0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line)

    def _draw_underlined_label(self, painter, rect, text):
        painter.save()
        painter.setPen(QPen(self.OBJECT_COLOR, self.OBJECT_LINE_WIDTH))
        painter.setFont(QFont("Arial", 13))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        lw = min(rect.width() * 0.22, 80.0)
        ly = rect.y() + rect.height() - 3.0
        cx = rect.x() + rect.width() / 2.0
        painter.drawLine(QPointF(cx - lw / 2.0, ly), QPointF(cx + lw / 2.0, ly))
        painter.restore()

    def _draw_dim_h(self, painter, x1, x2, y_ref, offset, label):
        xl, xr = min(x1, x2), max(x1, x2)
        y = y_ref + offset
        painter.save()
        painter.setPen(QPen(self.DIM_COLOR, self.DIM_LINE_WIDTH))
        painter.setFont(QFont("Arial", 10))
        painter.drawLine(QPointF(xl, y_ref), QPointF(xl, y))
        painter.drawLine(QPointF(xr, y_ref), QPointF(xr, y))
        painter.drawLine(QPointF(xl, y), QPointF(xr, y))
        self._draw_arrow_head(painter, QPointF(xl, y), (-1.0, 0.0))
        self._draw_arrow_head(painter, QPointF(xr, y), (1.0, 0.0))
        ty = y - 21.0 if offset < 0 else y + 4.0
        painter.drawText(QRectF(xl, ty, max(10.0, xr - xl), 18.0), Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()

    def _draw_dim_v(self, painter, y1, y2, x_ref, offset, label, arrows_inside=True, arrow_size=None, text_vertical=False):
        yt, yb = min(y1, y2), max(y1, y2)
        x = x_ref + offset
        painter.save()
        painter.setPen(QPen(self.DIM_COLOR, self.DIM_LINE_WIDTH))
        painter.setFont(QFont("Arial", 10))
        gap = 2.0
        wx = x_ref + gap if offset >= 0 else x_ref - gap
        painter.drawLine(QPointF(wx, yt), QPointF(x, yt))
        painter.drawLine(QPointF(wx, yb), QPointF(x, yb))
        painter.drawLine(QPointF(x, yt), QPointF(x, yb))
        span = max(0.1, yb - yt)
        size = 7.5 if arrow_size is None else arrow_size
        if span < size * 2.2:
            size = max(2.8, span * 0.35)
        self._draw_arrow_head(painter, QPointF(x, yt), (0.0, -1.0), size)
        self._draw_arrow_head(painter, QPointF(x, yb), (0.0, 1.0), size)
        if text_vertical:
            tx = x + (12.0 if offset >= 0 else -12.0)
            ty = yt - 16.0 if span <= 24.0 else (yt + yb) / 2.0
            painter.save()
            painter.translate(tx, ty)
            painter.rotate(-90.0 if offset >= 0 else 90.0)
            painter.drawText(QRectF(-28.0, -9.0, 56.0, 18.0), Qt.AlignmentFlag.AlignCenter, label)
            painter.restore()
        else:
            if offset >= 0:
                tr = QRectF(x + 7.0, yt, 95.0, max(12.0, yb - yt))
                al = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            else:
                tr = QRectF(x - 102.0, yt, 95.0, max(12.0, yb - yt))
                al = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
            painter.drawText(tr, al, label)
        painter.restore()

    def _draw_arrow_head(self, painter, tip, direction, size=7.5):
        dx, dy = direction
        ln = math.hypot(dx, dy)
        if ln == 0:
            return
        dx /= ln; dy /= ln
        px, py = -dy, dx
        p1 = QPointF(tip.x() - dx * size + px * size * 0.45, tip.y() - dy * size + py * size * 0.45)
        p2 = QPointF(tip.x() - dx * size - px * size * 0.45, tip.y() - dy * size - py * size * 0.45)
        ob = painter.brush()
        painter.setBrush(painter.pen().color())
        painter.drawPolygon(QPolygonF([tip, p1, p2]))
        painter.setBrush(ob)

    def export_png(self, file_path: str) -> bool:
        dims = self._dims
        w = int(max(1200, dims.front_total_width * 2 + 600))
        h = int(max(1600, dims.front_total_height * 2 + 800))
        image = QImage(w, h, QImage.Format.Format_ARGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        self.render_to_painter(painter, QRectF(0.0, 0.0, float(w), float(h)), QColor("white"))
        painter.end()
        return image.save(file_path)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Coil Helvix - FRONT VIEW")
        self.resize(1580, 940)
        self.default_dims = CoilDimensions()
        self._spin_boxes: dict[str, QDoubleSpinBox] = {}
        self._direct_spin_boxes: dict[str, QDoubleSpinBox] = {}
        self._text_inputs: dict[str, QLineEdit] = {}
        self._connection_side_combo: QComboBox | None = None
        self._is_syncing_inputs = False
        self._is_syncing_direct_inputs = False
        self.drawing_widget = FrontViewDrawingWidget(self.default_dims)
        self._fl_label = QLabel()
        self._fh_label = QLabel()
        self._zoom_label = QLabel("100%")
        self._build_ui()
        self._apply_changes()

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_controls_panel())
        splitter.addWidget(self.drawing_widget)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([360, 1200])
        self.setCentralWidget(splitter)

    def _build_controls_panel(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        layout.addWidget(self._build_identity_group())
        layout.addWidget(self._build_main_specs_group())
        layout.addWidget(self._build_pitch_group())
        layout.addWidget(self._build_plate_group())
        layout.addWidget(self._build_first_bend_group())
        layout.addWidget(self._build_additional_group())
        layout.addWidget(self._build_direct_group())
        layout.addWidget(self._build_derived_group())
        layout.addLayout(self._build_buttons_row())
        layout.addLayout(self._build_zoom_row())
        layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.setMinimumWidth(330)
        return scroll

    def _build_identity_group(self):
        g = QGroupBox("Order Details"); f = QFormLayout(g)
        self._add_text_input(f, "job_order_no", "Job Order No.", self.default_dims.job_order_no)
        self._add_text_input(f, "coil_unique_id", "Coil Unique ID", self.default_dims.coil_unique_id)
        self._add_text_input(f, "coil_type", "Coil Type", self.default_dims.coil_type)
        return g

    def _build_main_specs_group(self):
        g = QGroupBox("Main Specs"); f = QFormLayout(g)
        self._add_direct_spin(f, "fin_length_direct", "Fin Length", self.default_dims.fin_length, 20.0, 6000.0)
        self._add_spin(f, "tubes_per_row", "Tubes per row (TPR)", self.default_dims.tubes_per_row, 1.0, 300.0, decimals=0)
        self._add_spin(f, "number_of_rows", "No. of Rows", self.default_dims.number_of_rows, 1.0, 40.0, decimals=0)
        self._add_spin(f, "number_of_circuits", "No. of Circuits", self.default_dims.number_of_circuits, 1.0, 100.0, decimals=0)
        self._add_spin(f, "fpi", "FPI", self.default_dims.fpi, 1, 60, decimals=0)
        self._add_spin(f, "tube_dia_inch", "Tube Dia (inch)", self.default_dims.tube_dia_inch, 0.1, 2.0, decimals=3)
        self._add_spin(f, "header_dia", "Header Dia", self.default_dims.header_dia, 2.0, 500.0)
        return g

    def _build_pitch_group(self):
        g = QGroupBox("Pitch"); f = QFormLayout(g)
        self._add_spin(f, "top_feature_tube_dia", "Tube Dia", self.default_dims.top_feature_tube_dia, 2.0, 80.0, decimals=2)
        self._add_spin(f, "top_feature_pitch_vertical", "Vertical", self.default_dims.top_feature_pitch_vertical, 5.0, 200.0, decimals=2)
        self._add_spin(f, "top_feature_pitch_horizontal", "Horizontal", self.default_dims.top_feature_pitch_horizontal, 5.0, 200.0, decimals=2)
        self._add_spin(f, "top_feature_circle_1_dia", "Circle 1 Dia", self.default_dims.top_feature_circle_1_dia, 2.0, 80.0, decimals=2)
        self._add_spin(f, "top_feature_circle_2_dia", "Circle 2 Dia", self.default_dims.top_feature_circle_2_dia, 2.0, 80.0, decimals=2)
        return g

    def _build_plate_group(self):
        g = QGroupBox("Plate / Overall"); f = QFormLayout(g)
        self._add_spin(f, "sheet_metal_thickness", "Sheet Metal Thickness", self.default_dims.sheet_metal_thickness, 0.5, 10.0, decimals=2)
        self._add_spin(f, "right_panel_width", "Return Side Plate", self.default_dims.right_panel_width, 5, 2000)
        self._add_spin(f, "left_panel_width", "Header Side Plate", self.default_dims.left_panel_width, 5, 2000)
        self._add_spin(f, "top_plate", "Top Plate", self.default_dims.top_plate, 5, 1000)
        self._add_spin(f, "bottom_plate", "Bottom Plate", self.default_dims.bottom_plate, 5, 1000)
        self._add_spin(f, "front_header_band_width", "Blank Off Width", self.default_dims.front_header_band_width, 20, 3000)
        self._add_spin(f, "core_width", "Total Width", self.default_dims.core_width, 60, 3000)
        self._add_spin(f, "front_total_height", "Total Height", self.default_dims.front_total_height, 200, 6000)
        self._spin_boxes["front_total_height"].setReadOnly(True)
        self._spin_boxes["front_total_height"].setToolTip("Calculated: (TPR × Vertical Pitch) + Top Plate + Bottom Plate")
        self._add_spin(f, "left_pipe_offset", "Header Extension", self.default_dims.left_pipe_offset, 0, 2000)
        return g

    def _build_first_bend_group(self):
        g = QGroupBox("First Bend"); f = QFormLayout(g)
        self._add_spin(f, "first_bend_header_side", "Header Side Plate", self.default_dims.first_bend_header_side, 0.0, 200.0)
        self._add_spin(f, "first_bend_return_side", "Return Side Plate", self.default_dims.first_bend_return_side, 0.0, 200.0)
        self._add_spin(f, "first_bend_top_plate", "Top Plate", self.default_dims.first_bend_top_plate, 0.0, 200.0)
        self._add_spin(f, "first_bend_bottom_plate", "Bottom Plate", self.default_dims.first_bend_bottom_plate, 0.0, 200.0)
        self._add_spin(f, "first_bend_blank_off", "Blank Off", self.default_dims.first_bend_blank_off, 0.0, 200.0)
        self._add_spin(f, "first_bend_intermediate_plate", "Intermediate Plate", self.default_dims.first_bend_intermediate_plate, 0.0, 200.0)
        return g

    def _build_additional_group(self):
        g = QGroupBox("Additional Inputs"); f = QFormLayout(g)
        self._add_spin(f, "top_total_length", "Top Total Length", self.default_dims.top_total_length, 500, 6000)
        self._spin_boxes["top_total_length"].setReadOnly(True)
        self._add_spin(f, "top_intermediate_length", "Top Intermediate Length", self.default_dims.top_intermediate_length, 100, 6000)
        self._spin_boxes["top_intermediate_length"].setReadOnly(True)
        self._add_spin(f, "front_total_width", "Front Total Width", self.default_dims.front_total_width, 200, 6000)
        self._spin_boxes["front_total_width"].setReadOnly(True)
        self._add_spin(f, "left_pipe_length", "Stub Length", self.default_dims.left_pipe_length, 10, 3000)
        self._add_spin(f, "nozzle_projection", "Nozzle Projection", self.default_dims.nozzle_projection, 10, 500)
        self._add_spin(f, "header_extension_length", "Header Ext. Length", self.default_dims.header_extension_length, 20, 3000)
        self._add_spin(f, "header_box_height", "Header Box Height", self.default_dims.header_box_height, 40, 2000)
        self._spin_boxes["header_box_height"].setReadOnly(True)
        self._add_spin(f, "right_cap_thickness", "Header Flange First Bend", self.default_dims.right_cap_thickness, 2, 400)
        self._add_spin(f, "circle_diameter", "Circle Diameter", self.default_dims.circle_diameter, 2.0, 40.0, decimals=2)
        self._add_spin(f, "blank_off_bend", "Blank Off Bend", self.default_dims.blank_off_bend, 0.0, 200.0)
        self._add_spin(f, "top_feature_tube_height", "Feature Tube Height", self.default_dims.top_feature_tube_height, 10.0, 400.0, decimals=2)
        self._spin_boxes["top_feature_tube_height"].setReadOnly(True)
        self._add_spin(f, "top_feature_pipe_length", "Feature Pipe Length", self.default_dims.top_feature_pipe_length, 2.0, 200.0, decimals=2)
        combo = QComboBox()
        combo.addItems(["LHS", "RHS"])
        combo.setCurrentText(self.default_dims.connection_side)
        combo.currentTextChanged.connect(self._apply_changes)
        self._connection_side_combo = combo
        f.addRow("Connection", combo)
        return g

    def _build_derived_group(self):
        g = QGroupBox("Derived"); f = QFormLayout(g)
        f.addRow("Fin Length (FL)", self._fl_label)
        f.addRow("Fin Height (FH)", self._fh_label)
        return g

    def _build_direct_group(self):
        g = QGroupBox("Direct Dimension Edit"); f = QFormLayout(g)
        self._add_direct_spin(f, "top_lead_span", "Top Lead Span", self.default_dims.top_lead_span, 20.0, 6000.0)
        self._direct_spin_boxes["top_lead_span"].setReadOnly(True)
        self._add_direct_spin(f, "fin_height_direct", "Fin Height (FH)", self.default_dims.fin_height, 20.0, 6000.0)
        return g

    def _build_buttons_row(self):
        layout = QHBoxLayout()
        for label, slot in [("Apply", self._apply_changes), ("Reset", self._reset_defaults),
                             ("Print", self._print_drawing), ("Export PNG", self._export_png)]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            layout.addWidget(btn)
        return layout

    def _build_zoom_row(self):
        layout = QHBoxLayout()
        zm = QPushButton("Zoom -"); zp = QPushButton("Zoom +"); zr = QPushButton("Reset View")
        zm.clicked.connect(lambda: self._do_zoom(-1))
        zp.clicked.connect(lambda: self._do_zoom(1))
        zr.clicked.connect(self._zoom_reset)
        self._zoom_label.setMinimumWidth(55)
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for w in [zm, zp, zr, self._zoom_label]:
            layout.addWidget(w)
        return layout

    def _do_zoom(self, d):
        self.drawing_widget.zoom_by(1.15 if d > 0 else 1.0 / 1.15)
        self._zoom_label.setText(f"{self.drawing_widget.zoom_percent()}%")

    def _zoom_reset(self):
        self.drawing_widget.reset_view()
        self._zoom_label.setText(f"{self.drawing_widget.zoom_percent()}%")

    def _add_spin(self, form, key, label, default_value, minimum, maximum, decimals=1):
        spin = QDoubleSpinBox()
        spin.setDecimals(decimals); spin.setRange(minimum, maximum); spin.setValue(default_value)
        spin.setSingleStep(1.0); spin.setKeyboardTracking(False)
        spin.valueChanged.connect(self._apply_changes)
        self._spin_boxes[key] = spin; form.addRow(label, spin)

    def _add_direct_spin(self, form, key, label, default_value, minimum, maximum, decimals=1):
        spin = QDoubleSpinBox()
        spin.setDecimals(decimals); spin.setRange(minimum, maximum); spin.setValue(default_value)
        spin.setSingleStep(1.0); spin.setKeyboardTracking(False)
        spin.valueChanged.connect(self._apply_direct_changes)
        self._direct_spin_boxes[key] = spin; form.addRow(label, spin)

    def _add_text_input(self, form, key, label, default_value):
        ti = QLineEdit(); ti.setText(str(default_value))
        ti.textChanged.connect(self._apply_changes)
        self._text_inputs[key] = ti; form.addRow(label, ti)

    def _collect_dimensions(self) -> CoilDimensions:
        conn = self._connection_side_combo.currentText() if self._connection_side_combo else self.default_dims.connection_side
        job = self._text_inputs.get("job_order_no", QLineEdit()).text() or self.default_dims.job_order_no
        uid = self._text_inputs.get("coil_unique_id", QLineEdit()).text() or self.default_dims.coil_unique_id
        ctype = self._text_inputs.get("coil_type", QLineEdit()).text() or self.default_dims.coil_type
        tp = self._spin_boxes["top_plate"].value()
        bp = self._spin_boxes["bottom_plate"].value()
        tpr = self._spin_boxes["tubes_per_row"].value()
        vp = self._spin_boxes["top_feature_pitch_vertical"].value()
        hp = self._spin_boxes["top_feature_pitch_horizontal"].value()
        nor = self._spin_boxes["number_of_rows"].value()
        calc_h = tpr * vp + tp + bp
        calc_fth = hp * (nor - 1.0)
        calc_hbh = hp * nor
        lpo = self._spin_boxes["left_pipe_offset"].value()
        lpw = self._spin_boxes["left_panel_width"].value()
        rpw = self._spin_boxes["right_panel_width"].value()
        fl_spin = self._direct_spin_boxes.get("fin_length_direct")
        fl = max(20.0, fl_spin.value()) if fl_spin else 20.0
        ftw = lpw + fl + rpw
        fhbw = self._spin_boxes["front_header_band_width"].value()
        bow = max(lpw, min(fhbw, lpw + fl))
        calc_til = max(100.0, ftw - lpw + bow)
        calc_ttl = max(500.0, lpo + calc_til)
        ttl = self._spin_boxes["top_total_length"].value()
        fbb = self._spin_boxes["first_bend_blank_off"].value()
        cur = getattr(self.drawing_widget, "_dims", self.default_dims)
        return CoilDimensions(
            top_total_length=max(ttl, calc_ttl), top_intermediate_length=calc_til,
            front_total_width=ftw, front_total_height=calc_h,
            left_panel_width=lpw, right_panel_width=rpw, fin_length_override=fl,
            top_bottom_margin=(tp + bp) / 2.0, top_plate=tp, bottom_plate=bp,
            core_width=self._spin_boxes["core_width"].value(),
            left_pipe_offset=lpo, left_pipe_length=self._spin_boxes["left_pipe_length"].value(),
            nozzle_projection=self._spin_boxes["nozzle_projection"].value(),
            header_extension_length=self._spin_boxes["header_extension_length"].value(),
            header_box_height=calc_hbh, right_cap_thickness=self._spin_boxes["right_cap_thickness"].value(),
            front_header_band_width=fhbw, top_small_offset_1=cur.top_small_offset_1,
            top_small_offset_2=cur.top_small_offset_2, fpi=self._spin_boxes["fpi"].value(),
            tube_dia_inch=self._spin_boxes["tube_dia_inch"].value(),
            pitch_vertical=vp, pitch_horizontal=hp, connection_side=conn,
            job_order_no=job, coil_unique_id=uid, coil_type=ctype,
            circle_diameter=self._spin_boxes["circle_diameter"].value(),
            tubes_per_row=tpr, number_of_rows=nor,
            number_of_circuits=self._spin_boxes["number_of_circuits"].value(),
            header_dia=self._spin_boxes["header_dia"].value(), blank_off_bend=fbb,
            top_feature_tube_dia=self._spin_boxes["top_feature_tube_dia"].value(),
            top_feature_tube_height=calc_fth,
            top_feature_pipe_length=self._spin_boxes["top_feature_pipe_length"].value(),
            top_feature_pitch_vertical=vp, top_feature_pitch_horizontal=hp,
            top_feature_circle_1_dia=self._spin_boxes["top_feature_circle_1_dia"].value(),
            top_feature_circle_2_dia=self._spin_boxes["top_feature_circle_2_dia"].value(),
            sheet_metal_thickness=self._spin_boxes["sheet_metal_thickness"].value(),
            first_bend_header_side=self._spin_boxes["first_bend_header_side"].value(),
            first_bend_return_side=self._spin_boxes["first_bend_return_side"].value(),
            first_bend_top_plate=self._spin_boxes["first_bend_top_plate"].value(),
            first_bend_bottom_plate=self._spin_boxes["first_bend_bottom_plate"].value(),
            first_bend_blank_off=fbb,
            first_bend_intermediate_plate=self._spin_boxes["first_bend_intermediate_plate"].value(),
        )

    def _apply_changes(self) -> None:
        if self._is_syncing_inputs:
            return
        dims = self._collect_dimensions().sanitized()
        self._sync_spin_values(dims)
        self._sync_direct_spin_values(dims)
        self._fl_label.setText(f"{dims.fin_length:.1f}")
        self._fh_label.setText(f"{dims.fin_height:.1f}")
        self.drawing_widget.set_dimensions(dims)
        self._zoom_label.setText(f"{self.drawing_widget.zoom_percent()}%")

    def _apply_direct_changes(self) -> None:
        if self._is_syncing_direct_inputs or self._is_syncing_inputs:
            return
        dims = self._collect_dimensions().sanitized()
        fl = self._direct_spin_boxes["fin_length_direct"].value()
        fh = self._direct_spin_boxes["fin_height_direct"].value()
        dims.fin_length_override = max(20.0, fl)
        dims.front_total_width = dims.left_panel_width + dims.fin_length + dims.right_panel_width
        tps = max(10.0, dims.front_total_height - fh)
        prev = max(0.001, dims.top_plate + dims.bottom_plate)
        tr = max(0.0, min(dims.top_plate / prev, 1.0))
        dims.top_plate = tps * tr
        dims.bottom_plate = tps - dims.top_plate
        dims.top_bottom_margin = (dims.top_plate + dims.bottom_plate) / 2.0
        dims = dims.sanitized()
        self._sync_spin_values(dims)
        self._apply_changes()

    def _sync_spin_values(self, dims: CoilDimensions) -> None:
        vals = {
            "top_total_length": dims.top_total_length, "top_intermediate_length": dims.top_intermediate_length,
            "front_total_width": dims.front_total_width, "front_total_height": dims.front_total_height,
            "left_panel_width": dims.left_panel_width, "right_panel_width": dims.right_panel_width,
            "top_plate": dims.top_plate, "bottom_plate": dims.bottom_plate, "core_width": dims.core_width,
            "left_pipe_offset": dims.left_pipe_offset, "left_pipe_length": dims.left_pipe_length,
            "nozzle_projection": dims.nozzle_projection, "header_extension_length": dims.header_extension_length,
            "header_box_height": dims.header_box_height, "right_cap_thickness": dims.right_cap_thickness,
            "front_header_band_width": dims.front_header_band_width, "fpi": dims.fpi,
            "tube_dia_inch": dims.tube_dia_inch, "circle_diameter": dims.circle_diameter,
            "tubes_per_row": dims.tubes_per_row, "number_of_rows": dims.number_of_rows,
            "number_of_circuits": dims.number_of_circuits, "header_dia": dims.header_dia,
            "blank_off_bend": dims.blank_off_bend, "top_feature_tube_dia": dims.top_feature_tube_dia,
            "top_feature_tube_height": dims.top_feature_tube_height,
            "top_feature_pipe_length": dims.top_feature_pipe_length,
            "top_feature_pitch_vertical": dims.top_feature_pitch_vertical,
            "top_feature_pitch_horizontal": dims.top_feature_pitch_horizontal,
            "top_feature_circle_1_dia": dims.top_feature_circle_1_dia,
            "top_feature_circle_2_dia": dims.top_feature_circle_2_dia,
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

    def _sync_direct_spin_values(self, dims: CoilDimensions) -> None:
        vals = {"top_lead_span": dims.top_lead_span, "fin_length_direct": dims.fin_length, "fin_height_direct": dims.fin_height}
        self._is_syncing_direct_inputs = True
        try:
            for k, v in vals.items():
                s = self._direct_spin_boxes.get(k)
                if s and abs(s.value() - v) > 1e-6:
                    s.blockSignals(True); s.setValue(v); s.blockSignals(False)
        finally:
            self._is_syncing_direct_inputs = False

    def _reset_defaults(self) -> None:
        self._sync_spin_values(self.default_dims.sanitized())
        self._apply_changes()

    def _print_drawing(self) -> None:
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        painter = QPainter(printer)
        self.drawing_widget.render_to_painter(painter, QRectF(painter.viewport()), QColor("white"))
        painter.end()

    def _export_png(self) -> None:
        fp, _ = QFileDialog.getSaveFileName(self, "Export Front View", "front_view.png", "PNG Image (*.png)")
        if not fp:
            return
        if not fp.lower().endswith(".png"):
            fp += ".png"
        if not self.drawing_widget.export_png(fp):
            QMessageBox.warning(self, "Export Failed", "Could not save PNG.")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Coil Helvix - Front View")
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
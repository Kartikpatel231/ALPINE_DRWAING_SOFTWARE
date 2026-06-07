import math
import sys
import json
import re
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
        raw_first_run = str(payload.get("first_run_utc", "")).strip()
        parsed = datetime.fromisoformat(raw_first_run)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        state_file.write_text(json.dumps({"first_run_utc": now_utc.isoformat()}, indent=2), encoding="utf-8")
        return now_utc


def _resolve_expiry_datetime(first_run_utc: datetime) -> datetime:
    fixed_expiry = os.getenv("COIL_HELVIX_EXPIRY_DATE", "").strip()
    if fixed_expiry:
        try:
            expiry_date = datetime.strptime(fixed_expiry, "%Y-%m-%d").date()
            expiry_local = datetime(expiry_date.year, expiry_date.month, expiry_date.day, 23, 59, 59)
            return expiry_local.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return first_run_utc + timedelta(days=ACCESS_WINDOW_DAYS)


def _is_password_valid(entered_password: str) -> bool:
    expected_hash = os.getenv("COIL_HELVIX_PASSWORD_SHA256", DEFAULT_PASSWORD_SHA256).strip().lower()
    entered_hash = hashlib.sha256(entered_password.encode("utf-8")).hexdigest().lower()
    return hmac.compare_digest(entered_hash, expected_hash)


def _enforce_startup_access() -> tuple[bool, str | None]:
    first_run_utc = _load_or_create_first_run()
    expiry_utc = _resolve_expiry_datetime(first_run_utc)
    now_utc = datetime.now(timezone.utc)
    if now_utc <= expiry_utc:
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
    def calculated_total_height(self) -> float:
        return (self.tubes_per_row * self.pitch_vertical) + self.top_plate + self.bottom_plate

    @property
    def calculated_top_intermediate_length(self) -> float:
        blank_off_w = max(self.left_panel_width, min(self.front_header_band_width, self.left_panel_width + self.fin_length))
        intermediate_length = self.front_total_width - self.left_panel_width + blank_off_w
        return max(100.0, intermediate_length)

    @property
    def calculated_top_total_length(self) -> float:
        return max(500.0, self.left_pipe_offset + self.top_intermediate_length)

    def sanitized(self) -> "CoilDimensions":
        value = replace(self)
        value.top_total_length = max(500.0, value.top_total_length)
        value.front_total_width = max(200.0, value.front_total_width)
        value.front_total_height = max(300.0, value.front_total_height)
        value.core_width = max(80.0, value.core_width)
        value.top_intermediate_length = max(100.0, min(value.top_intermediate_length, value.top_total_length))
        value.left_panel_width = max(5.0, min(value.left_panel_width, 2000.0))
        value.right_panel_width = max(5.0, min(value.right_panel_width, 2000.0))
        value.fin_length_override = max(20.0, min(value.fin_length_override, 6000.0))
        value.front_total_width = max(200.0, value.left_panel_width + value.fin_length + value.right_panel_width)
        min_top_total = value.front_total_width - value.left_panel_width + 20.0
        value.top_total_length = max(value.top_total_length, min_top_total)
        margin_limit = (value.front_total_height / 2.0) - 10.0
        legacy_margin = max(5.0, min(value.top_bottom_margin, margin_limit))
        default_top_plate = CoilDimensions.top_plate
        default_bottom_plate = CoilDimensions.bottom_plate
        if (abs(value.top_plate - default_top_plate) < 1e-6 and abs(value.bottom_plate - default_bottom_plate) < 1e-6
                and abs(legacy_margin - CoilDimensions.top_bottom_margin) > 1e-6):
            value.top_plate = legacy_margin
            value.bottom_plate = legacy_margin
        value.top_plate = max(5.0, min(value.top_plate, margin_limit))
        value.bottom_plate = max(5.0, min(value.bottom_plate, margin_limit))
        pair_margin_limit = max(10.0, value.front_total_height - 20.0)
        pair_margin_total = value.top_plate + value.bottom_plate
        if pair_margin_total > pair_margin_limit:
            ratio = pair_margin_limit / pair_margin_total
            value.top_plate = max(5.0, value.top_plate * ratio)
            value.bottom_plate = max(5.0, value.bottom_plate * ratio)
        value.top_bottom_margin = (value.top_plate + value.bottom_plate) / 2.0
        min_header = value.left_panel_width + 20.0
        value.front_header_band_width = max(min_header, min(value.front_header_band_width, value.front_total_width - 20.0))
        value.top_intermediate_length = value.calculated_top_intermediate_length
        value.top_total_length = max(min_top_total, value.calculated_top_total_length)
        value.left_pipe_offset = max(0.0, min(value.left_pipe_offset, 3000.0))
        value.left_pipe_length = max(10.0, min(value.left_pipe_length, 3000.0))
        value.nozzle_projection = max(15.0, value.nozzle_projection)
        value.header_extension_length = max(value.nozzle_projection + 5.0, value.header_extension_length)
        value.right_cap_thickness = max(2.0, min(value.right_cap_thickness, value.core_width / 2.0))
        each_limit = max(5.0, value.core_width - (2.0 * value.right_cap_thickness) - 10.0)
        value.top_small_offset_1 = max(5.0, min(value.top_small_offset_1, each_limit))
        value.top_small_offset_2 = max(5.0, min(value.top_small_offset_2, each_limit))
        pair_limit = max(12.0, value.core_width - (2.0 * value.right_cap_thickness) - 20.0)
        pair_total = value.top_small_offset_1 + value.top_small_offset_2
        if pair_total > pair_limit:
            ratio = pair_limit / pair_total
            value.top_small_offset_1 = max(5.0, value.top_small_offset_1 * ratio)
            value.top_small_offset_2 = max(5.0, value.top_small_offset_2 * ratio)
        value.fpi = max(1.0, min(value.fpi, 60.0))
        value.tube_dia_inch = max(0.1, min(value.tube_dia_inch, 2.0))
        value.pitch_vertical = max(5.0, min(value.pitch_vertical, 120.0))
        value.pitch_horizontal = max(5.0, min(value.pitch_horizontal, 120.0))
        value.circle_diameter = max(2.0, min(value.circle_diameter, 40.0))
        value.tubes_per_row = max(1.0, min(value.tubes_per_row, 300.0))
        value.number_of_rows = max(1.0, min(value.number_of_rows, 40.0))
        value.number_of_circuits = max(1.0, min(value.number_of_circuits, 100.0))
        value.header_dia = max(2.0, min(value.header_dia, 500.0))
        value.blank_off_bend = max(0.0, min(value.blank_off_bend, 200.0))
        value.top_feature_tube_dia = max(2.0, min(value.top_feature_tube_dia, 80.0))
        max_tube_height = max(10.0, value.core_width - (2.0 * value.right_cap_thickness))
        value.top_feature_tube_height = max(10.0, min(value.top_feature_tube_height, max_tube_height))
        value.top_feature_pipe_length = max(2.0, min(value.top_feature_pipe_length, 200.0))
        value.top_feature_pitch_vertical = max(5.0, min(value.top_feature_pitch_vertical, 200.0))
        value.top_feature_pitch_horizontal = max(5.0, min(value.top_feature_pitch_horizontal, 200.0))
        value.top_feature_circle_1_dia = max(2.0, min(value.top_feature_circle_1_dia, 80.0))
        value.top_feature_circle_2_dia = max(2.0, min(value.top_feature_circle_2_dia, 80.0))
        value.sheet_metal_thickness = max(0.5, min(value.sheet_metal_thickness, 10.0))
        value.first_bend_header_side = max(0.0, min(value.first_bend_header_side, 200.0))
        value.first_bend_return_side = max(0.0, min(value.first_bend_return_side, 200.0))
        value.first_bend_top_plate = max(0.0, min(value.first_bend_top_plate, 200.0))
        value.first_bend_bottom_plate = max(0.0, min(value.first_bend_bottom_plate, 200.0))
        value.first_bend_blank_off = max(0.0, min(value.first_bend_blank_off, 200.0))
        value.first_bend_intermediate_plate = max(0.0, min(value.first_bend_intermediate_plate, 200.0))
        if (abs(value.first_bend_blank_off - CoilDimensions.first_bend_blank_off) < 1e-6
                and abs(value.blank_off_bend - CoilDimensions.blank_off_bend) > 1e-6):
            value.first_bend_blank_off = max(0.0, min(value.blank_off_bend, 200.0))
        value.blank_off_bend = value.first_bend_blank_off
        row_count = value.number_of_rows
        horizontal_pitch = max(5.0, value.pitch_horizontal)
        value.top_feature_tube_height = horizontal_pitch * (row_count - 1.0)
        value.header_box_height = horizontal_pitch * row_count
        value.front_total_height = (value.tubes_per_row * value.pitch_vertical) + value.top_plate + value.bottom_plate
        normalized_connection = str(value.connection_side).strip().upper()
        if normalized_connection not in {"LHS", "RHS"}:
            normalized_connection = "LHS"
        value.connection_side = normalized_connection
        value.job_order_no = str(value.job_order_no).strip() or CoilDimensions.job_order_no
        value.coil_unique_id = str(value.coil_unique_id).strip() or CoilDimensions.coil_unique_id
        value.coil_type = str(value.coil_type).strip().upper() or CoilDimensions.coil_type
        return value


class TopViewDrawingWidget(QWidget):
    BACKGROUND = QColor("#f2f2f2")
    OBJECT_COLOR = QColor("#111111")
    DIM_COLOR = QColor("#ff6a00")
    TUBE_COLOR = QColor("#ff1a1a")
    ACCENT_GREEN = QColor("#12b312")
    MAGENTA = QColor("#b000ff")
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
        self.setMinimumSize(1000, 500)

    def set_dimensions(self, dimensions: CoilDimensions) -> None:
        self._dims = dimensions.sanitized()
        self.update()

    def zoom_by(self, factor: float) -> None:
        self.set_zoom(self._zoom * factor)

    def set_zoom(self, value: float) -> None:
        clamped = max(self._min_zoom, min(value, self._max_zoom))
        if abs(clamped - self._zoom) < 1e-6:
            return
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
        before_scale, before_offset_x, before_offset_y = self._calculate_transform(rect, layout["world_w"], layout["world_h"], True)
        cursor = event.position()
        world_x = (cursor.x() - before_offset_x) / before_scale
        world_y = (cursor.y() - before_offset_y) / before_scale
        factor = 1.12 if delta > 0 else (1.0 / 1.12)
        old_zoom = self._zoom
        self._zoom = max(self._min_zoom, min(self._zoom * factor, self._max_zoom))
        if abs(self._zoom - old_zoom) < 1e-6:
            event.accept()
            return
        after_scale, after_offset_x, after_offset_y = self._calculate_transform(rect, layout["world_w"], layout["world_h"], True)
        new_cursor_x = after_offset_x + (world_x * after_scale)
        new_cursor_y = after_offset_y + (world_y * after_scale)
        self._pan_offset = QPointF(self._pan_offset.x() + (cursor.x() - new_cursor_x), self._pan_offset.y() + (cursor.y() - new_cursor_y))
        self.update()
        event.accept()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_panning = True
            self._last_pan_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._is_panning and self._last_pan_pos is not None:
            delta = event.position() - self._last_pan_pos
            self._pan_offset = QPointF(self._pan_offset.x() + delta.x(), self._pan_offset.y() + delta.y())
            self._last_pan_pos = event.position()
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_panning = False
            self._last_pan_pos = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def render_to_painter(self, painter: QPainter, target_rect: QRectF, background: QColor, apply_view_transform: bool = False) -> None:
        if not isinstance(target_rect, QRectF):
            target_rect = QRectF(target_rect)
        layout = self._layout_data()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.fillRect(target_rect, background)
        scale, offset_x, offset_y = self._calculate_transform(target_rect, layout["world_w"], layout["world_h"], apply_view_transform)
        painter.translate(offset_x, offset_y)
        painter.scale(scale, scale)
        self._draw_top_view(painter, layout)
        painter.restore()

    def _calculate_transform(self, target_rect, world_w, world_h, apply_view_transform):
        margin = 20.0
        available_w = max(10.0, target_rect.width() - (2 * margin))
        available_h = max(10.0, target_rect.height() - (2 * margin))
        fit_scale = min(available_w / world_w, available_h / world_h)
        scale = fit_scale * self._zoom if apply_view_transform else fit_scale
        pan_x = self._pan_offset.x() if apply_view_transform else 0.0
        pan_y = self._pan_offset.y() if apply_view_transform else 0.0
        offset_x = target_rect.x() + ((target_rect.width() - (world_w * scale)) / 2.0) + pan_x
        offset_y = target_rect.y() + ((target_rect.height() - (world_h * scale)) / 2.0) + pan_y
        return scale, offset_x, offset_y

    def _layout_data(self) -> dict:
        dims = self._dims
        x0 = 0.0
        y0 = 160.0  # top margin for above-axis dims
        total_end = x0 + dims.top_total_length
        world_w = total_end + 160.0
        world_h = y0 + dims.core_width + 280.0
        return {"x0": x0, "y0": y0, "world_w": world_w, "world_h": world_h}

    def _draw_top_view(self, painter: QPainter, layout: dict) -> None:
        dims = self._dims
        x0 = layout["x0"]
        y0 = layout["y0"]

        total_end = x0 + dims.top_total_length
        face_start = total_end - dims.front_total_width
        face_end = total_end
        fin_start = face_start + dims.left_panel_width
        fin_end = face_end - dims.right_panel_width
        intermediate_start = total_end - dims.top_intermediate_length

        top_h = dims.core_width
        header_h = min(dims.header_box_height, top_h)
        header_y = y0 + ((top_h - header_h) / 2.0)
        cap_top_y = y0 + dims.right_cap_thickness
        cap_bottom_y = y0 + top_h - dims.right_cap_thickness
        left_gap_top_y = y0
        left_gap_bottom_y = y0 + top_h

        object_pen = QPen(self.OBJECT_COLOR, self.OBJECT_LINE_WIDTH)
        painter.setPen(object_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        painter.drawLine(QPointF(fin_start, header_y), QPointF(fin_end, header_y))
        painter.drawLine(QPointF(fin_start, header_y + header_h), QPointF(fin_end, header_y + header_h))

        header_side_bend = max(0.0, min(dims.first_bend_header_side, top_h * 0.35))
        return_side_bend = max(0.0, min(dims.first_bend_return_side, top_h * 0.35))
        top_plate_bend = max(0.0, min(dims.first_bend_top_plate, top_h * 0.35))
        bottom_plate_bend = max(0.0, min(dims.first_bend_bottom_plate, top_h * 0.35))
        blank_off_bend = max(0.0, min(dims.first_bend_blank_off, top_h * 0.35))

        left_stub = max(0.0, header_side_bend)
        blank_off_w = max(dims.left_panel_width, min(dims.front_header_band_width, dims.left_panel_width + dims.fin_length))
        bottom_cover_start = max(x0, fin_start - blank_off_w)
        painter.drawLine(QPointF(face_start, left_gap_top_y), QPointF(fin_start, left_gap_top_y))
        if left_stub > 0.0:
            painter.drawLine(QPointF(face_start, left_gap_top_y), QPointF(face_start, left_gap_top_y + left_stub))
        painter.drawLine(QPointF(bottom_cover_start, left_gap_bottom_y), QPointF(fin_start, left_gap_bottom_y))
        if blank_off_bend > 0.0:
            painter.drawLine(QPointF(bottom_cover_start, left_gap_bottom_y - blank_off_bend), QPointF(bottom_cover_start, left_gap_bottom_y))
        painter.drawLine(QPointF(fin_start, y0), QPointF(fin_start, y0 + top_h))

        right_tick = max(0.0, return_side_bend)
        painter.drawLine(QPointF(fin_end, left_gap_top_y), QPointF(fin_end, left_gap_bottom_y))
        painter.drawLine(QPointF(fin_end, left_gap_top_y), QPointF(face_end, left_gap_top_y))
        if right_tick > 0.0:
            painter.drawLine(QPointF(face_end, left_gap_top_y), QPointF(face_end, left_gap_top_y + right_tick))
        painter.drawLine(QPointF(fin_end, left_gap_bottom_y), QPointF(face_end, left_gap_bottom_y))
        if right_tick > 0.0:
            painter.drawLine(QPointF(face_end, left_gap_bottom_y - right_tick), QPointF(face_end, left_gap_bottom_y))

        if top_plate_bend > 0.0:
            painter.drawLine(QPointF(fin_start, header_y), QPointF(fin_start, header_y + top_plate_bend))
            painter.drawLine(QPointF(fin_end, header_y), QPointF(fin_end, header_y + top_plate_bend))
        if bottom_plate_bend > 0.0:
            bottom_y = header_y + header_h
            painter.drawLine(QPointF(fin_start, bottom_y - bottom_plate_bend), QPointF(fin_start, bottom_y))
            painter.drawLine(QPointF(fin_end, bottom_y - bottom_plate_bend), QPointF(fin_end, bottom_y))

        tube_count = max(2, int(round(dims.number_of_rows)))
        tube_top_target = cap_top_y + dims.top_small_offset_1
        tube_bottom_target = cap_bottom_y - dims.top_small_offset_2
        if tube_bottom_target <= tube_top_target + 10.0:
            mid_y = (cap_top_y + cap_bottom_y) / 2.0
            half_span = max(20.0, (cap_bottom_y - cap_top_y - 12.0) / 2.0)
            tube_top = mid_y - half_span
            tube_bottom = mid_y + half_span
        else:
            tube_top = tube_top_target
            tube_bottom = tube_bottom_target

        feature_step = max(5.0, dims.top_feature_pitch_horizontal)
        feature_span = feature_step * max(1, tube_count - 1)
        available_span = max(0.0, tube_bottom - tube_top)
        if feature_span <= available_span and tube_count > 1:
            center_y = (tube_top + tube_bottom) / 2.0
            tube_top = center_y - (feature_span / 2.0)
            tube_bottom = center_y + (feature_span / 2.0)

        max_tube_height = max(10.0, cap_bottom_y - cap_top_y)
        requested_tube_height = max(10.0, min(dims.top_feature_tube_height, max_tube_height))
        center_y = (tube_top + tube_bottom) / 2.0
        top_limit = cap_top_y
        bottom_limit = cap_bottom_y - requested_tube_height
        tube_top = min(max(center_y - (requested_tube_height / 2.0), top_limit), bottom_limit)
        tube_bottom = tube_top + requested_tube_height
        tube_step = (tube_bottom - tube_top) / max(1, tube_count - 1)

        available_header_dia = max(10.0, cap_bottom_y - cap_top_y)
        body_h = max(10.0, min(dims.header_dia, available_header_dia))
        neck_h = max(8.0, min(body_h - 2.0, body_h * 0.78))
        thread_len = min(28.0, max(16.0, dims.nozzle_projection * 0.34))
        flange_radius = body_h / 2.0

        stub_end_x = fin_start
        stub_start_x = stub_end_x - dims.left_pipe_length
        flange_center_x = stub_start_x - flange_radius
        circle_left_x = flange_center_x - flange_radius
        body_end_x = circle_left_x - dims.header_extension_length
        body_start_x = body_end_x - dims.nozzle_projection
        neck_start_x = body_end_x
        neck_end_x = circle_left_x

        ext_len_span = dims.header_extension_length + flange_radius
        stub_len_span = dims.left_pipe_length + flange_radius
        total_span = stub_end_x - body_start_x

        nozzle_y_positions = [tube_top, tube_bottom]
        for nozzle_y, name in zip(nozzle_y_positions, ["IN", "OUT"]):
            body_rect = QRectF(body_start_x, nozzle_y - (body_h / 2.0), max(8.0, dims.nozzle_projection), body_h)
            neck_rect = QRectF(neck_start_x, nozzle_y - (neck_h / 2.0), max(2.0, neck_end_x - neck_start_x), neck_h)
            painter.drawRect(body_rect)
            if neck_end_x > neck_start_x + 0.5:
                painter.drawRect(neck_rect)
            painter.drawEllipse(QPointF(flange_center_x, nozzle_y), flange_radius, flange_radius)
            rib_start = body_start_x + 4.0
            rib_end = min(body_start_x + thread_len, body_end_x - 2.0)
            rib_x = rib_start
            while rib_x <= rib_end:
                painter.drawLine(QPointF(rib_x, body_rect.top()), QPointF(rib_x, body_rect.bottom()))
                rib_x += 6.0
            painter.drawEllipse(QPointF(body_start_x + (dims.nozzle_projection * 0.62), nozzle_y), 2.4, 2.4)
            arrow_left_x = body_start_x - 90.0
            painter.save()
            painter.setPen(QPen(self.OBJECT_COLOR, self.OBJECT_LINE_WIDTH))
            painter.drawLine(QPointF(stub_start_x, nozzle_y), QPointF(stub_end_x, nozzle_y))
            painter.restore()
            painter.drawText(QRectF(arrow_left_x - 58.0, nozzle_y - 14.0, 52.0, 28.0),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, name)

        tube_pen = QPen(self.TUBE_COLOR, 1.5)
        tube_pen.setStyle(Qt.PenStyle.DashLine)
        tube_pen.setDashPattern([8.0, 5.0])
        painter.setPen(tube_pen)
        tube_ys: list[float] = []
        for tube_index in range(tube_count):
            y_tube = tube_top + (tube_index * tube_step)
            tube_ys.append(y_tube)
            painter.drawLine(QPointF(fin_start, y_tube), QPointF(fin_end, y_tube))

        painter.setPen(object_pen)
        painter.drawLine(QPointF(fin_end, tube_ys[0]), QPointF(fin_end, tube_ys[-1]))
        right_clearance = max(3.0, face_end - fin_end - 2.0)
        max_arc_width = right_clearance * 2.0
        for loop_index in range(tube_count - 1):
            y_a = tube_ys[loop_index]
            y_b = tube_ys[loop_index + 1]
            loop_dia = abs(y_b - y_a)
            y_top = min(y_a, y_b)
            y_mid = (y_a + y_b) / 2.0
            tube_wall_visual = max(2.0, min(6.0, dims.top_feature_tube_dia * 0.22))
            wall_thickness = min(tube_wall_visual, loop_dia * 0.28)
            outer_dia = loop_dia + wall_thickness
            inner_dia = max(2.0, loop_dia - wall_thickness)
            outer_w_target = max(2.0, dims.top_feature_circle_1_dia)
            inner_w_target = max(1.4, min(dims.top_feature_circle_2_dia, outer_w_target - 0.6))
            outer_w = max(2.0, min(outer_w_target, max_arc_width))
            inner_w = max(1.4, min(inner_w_target, outer_w - 0.6, max_arc_width))
            flow_w = max(1.2, min((outer_w + inner_w) / 2.0, max_arc_width))
            max_pipe_len = max(2.0, right_clearance - 1.0)
            neck_len = min(max(2.0, dims.top_feature_pipe_length), max_pipe_len)
            bend_axis_x = min(face_end - 1.0, fin_end + neck_len)
            outer_top_y = y_mid - (outer_dia / 2.0)
            outer_bottom_y = y_mid + (outer_dia / 2.0)
            inner_top_y = y_mid - (inner_dia / 2.0)
            inner_bottom_y = y_mid + (inner_dia / 2.0)
            painter.drawLine(QPointF(fin_end, outer_top_y), QPointF(bend_axis_x, outer_top_y))
            painter.drawLine(QPointF(fin_end, outer_bottom_y), QPointF(bend_axis_x, outer_bottom_y))
            painter.drawLine(QPointF(fin_end, inner_top_y), QPointF(bend_axis_x, inner_top_y))
            painter.drawLine(QPointF(fin_end, inner_bottom_y), QPointF(bend_axis_x, inner_bottom_y))
            loop_rect_outer = QRectF(bend_axis_x - (outer_w / 2.0), y_mid - (outer_dia / 2.0), outer_w, outer_dia)
            loop_rect_inner = QRectF(bend_axis_x - (inner_w / 2.0), y_mid - (inner_dia / 2.0), inner_w, inner_dia)
            loop_rect_flow = QRectF(bend_axis_x - (flow_w / 2.0), y_top, flow_w, loop_dia)
            painter.drawArc(loop_rect_outer, 90 * 16, -180 * 16)
            painter.drawArc(loop_rect_inner, 90 * 16, -180 * 16)
            painter.save()
            painter.setPen(tube_pen)
            painter.drawArc(loop_rect_flow, 90 * 16, -180 * 16)
            painter.restore()

        # Dimensions
        self._draw_dim_h(painter, face_start, fin_start, y0 + top_h, 48.0, f"{dims.left_panel_width:.0f}")
        self._draw_dim_h(painter, fin_start, fin_end, y0 + top_h, 48.0, f"{dims.fin_length:.0f} (FL)")
        self._draw_dim_h(painter, fin_end, face_end, y0 + top_h, 48.0, f"{dims.right_panel_width:.0f}")
        self._draw_dim_h(painter, x0, intermediate_start, y0 + top_h, 84.0, f"{intermediate_start - x0:.0f}")
        self._draw_dim_h(painter, face_start, face_end, y0 + top_h, 112.0, f"{dims.front_total_width:.0f}")
        self._draw_dim_h(painter, intermediate_start, face_end, y0 + top_h, 142.0, f"{dims.top_intermediate_length:.0f}")
        self._draw_dim_h(painter, x0, face_end, y0 + top_h, 200.0, f"{dims.top_total_length:.0f}")
        self._draw_dim_h(painter, body_start_x, body_end_x, y0, -35.0, f"{dims.nozzle_projection:.0f}")
        self._draw_dim_h(painter, flange_center_x, stub_end_x, y0, -99.0, f"{stub_len_span:.0f}")
        self._draw_dim_h(painter, flange_center_x, body_end_x, y0, -67.0, f"{ext_len_span:.0f}")
        self._draw_dim_h(painter, body_start_x, stub_end_x, y0, -131.0, f"{total_span:.0f}")
        self._draw_dim_v(painter, left_gap_top_y, left_gap_bottom_y, fin_start, -48.0, f"{top_h:.0f}")
        self._draw_dim_v(painter, y0, y0 + top_h, face_end, 88.0, f"{top_h:.0f}", text_vertical=True)
        self._draw_dim_v(painter, y0, y0 + dims.right_cap_thickness, fin_end, 54.0, f"{dims.right_cap_thickness:.0f}",
            arrows_inside=False, arrow_size=4.8, text_vertical=True)
        top_offset_1 = max(0.0, header_y - y0)
        top_offset_2 = max(0.0, (y0 + top_h) - (header_y + header_h))
        self._draw_dim_v(painter, y0, header_y, fin_end, -102.0, f"{top_offset_1:.1f}", text_vertical=True)
        self._draw_dim_v(painter, header_y + header_h, y0 + top_h, fin_end, -102.0, f"{top_offset_2:.1f}", text_vertical=True)

        painter.setPen(object_pen)
        self._draw_underlined_label(painter, QRectF(x0, y0 + top_h + 248.0, dims.top_total_length, 30.0), "TOP")

    def _draw_underlined_label(self, painter, rect, text):
        painter.save()
        painter.setPen(QPen(self.OBJECT_COLOR, self.OBJECT_LINE_WIDTH))
        painter.setFont(QFont("Arial", 13))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        line_w = min(rect.width() * 0.22, 80.0)
        line_y = rect.y() + rect.height() - 3.0
        center_x = rect.x() + (rect.width() / 2.0)
        painter.drawLine(QPointF(center_x - (line_w / 2.0), line_y), QPointF(center_x + (line_w / 2.0), line_y))
        painter.restore()

    def _draw_dim_h(self, painter, x1, x2, y_ref, offset, label):
        x_left = min(x1, x2)
        x_right = max(x1, x2)
        y = y_ref + offset
        painter.save()
        painter.setPen(QPen(self.DIM_COLOR, self.DIM_LINE_WIDTH))
        painter.setFont(QFont("Arial", 10))
        painter.drawLine(QPointF(x_left, y_ref), QPointF(x_left, y))
        painter.drawLine(QPointF(x_right, y_ref), QPointF(x_right, y))
        painter.drawLine(QPointF(x_left, y), QPointF(x_right, y))
        self._draw_arrow_head(painter, QPointF(x_left, y), (-1.0, 0.0))
        self._draw_arrow_head(painter, QPointF(x_right, y), (1.0, 0.0))
        text_y = y - 21.0 if offset < 0 else y + 4.0
        painter.drawText(QRectF(x_left, text_y, max(10.0, x_right - x_left), 18.0), Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()

    def _draw_dim_v(self, painter, y1, y2, x_ref, offset, label, arrows_inside=True, arrow_size=None, text_vertical=False):
        y_top = min(y1, y2)
        y_bottom = max(y1, y2)
        x = x_ref + offset
        painter.save()
        painter.setPen(QPen(self.DIM_COLOR, self.DIM_LINE_WIDTH))
        painter.setFont(QFont("Arial", 10))
        witness_gap = 2.0
        witness_start_x = x_ref + witness_gap if offset >= 0 else x_ref - witness_gap
        painter.drawLine(QPointF(witness_start_x, y_top), QPointF(x, y_top))
        painter.drawLine(QPointF(witness_start_x, y_bottom), QPointF(x, y_bottom))
        painter.drawLine(QPointF(x, y_top), QPointF(x, y_bottom))
        span = max(0.1, y_bottom - y_top)
        size = 7.5 if arrow_size is None else arrow_size
        if span < (size * 2.2):
            size = max(2.8, span * 0.35)
        self._draw_arrow_head(painter, QPointF(x, y_top), (0.0, -1.0), size)
        self._draw_arrow_head(painter, QPointF(x, y_bottom), (0.0, 1.0), size)
        if text_vertical:
            text_x = x + (12.0 if offset >= 0 else -12.0)
            text_y = y_top - 16.0 if span <= 24.0 else (y_top + y_bottom) / 2.0
            painter.save()
            painter.translate(text_x, text_y)
            painter.rotate(-90.0 if offset >= 0 else 90.0)
            painter.drawText(QRectF(-28.0, -9.0, 56.0, 18.0), Qt.AlignmentFlag.AlignCenter, label)
            painter.restore()
        else:
            if offset >= 0:
                text_rect = QRectF(x + 7.0, y_top, 95.0, max(12.0, y_bottom - y_top))
                align = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            else:
                text_rect = QRectF(x - 102.0, y_top, 95.0, max(12.0, y_bottom - y_top))
                align = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
            painter.drawText(text_rect, align, label)
        painter.restore()

    def _draw_arrow_head(self, painter, tip, direction, size=7.5):
        dx, dy = direction
        length = math.hypot(dx, dy)
        if length == 0:
            return
        dx /= length
        dy /= length
        px, py = -dy, dx
        p1 = QPointF(tip.x() - (dx * size) + (px * size * 0.45), tip.y() - (dy * size) + (py * size * 0.45))
        p2 = QPointF(tip.x() - (dx * size) - (px * size * 0.45), tip.y() - (dy * size) - (py * size * 0.45))
        old_brush = painter.brush()
        painter.setBrush(painter.pen().color())
        painter.drawPolygon(QPolygonF([tip, p1, p2]))
        painter.setBrush(old_brush)

    def export_png(self, file_path: str) -> bool:
        image = QImage(2800, 1200, QImage.Format.Format_ARGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        self.render_to_painter(painter, QRectF(0.0, 0.0, float(image.width()), float(image.height())), QColor("white"))
        painter.end()
        return image.save(file_path)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Coil Helvix - TOP VIEW")
        self.resize(1580, 760)
        self.default_dims = CoilDimensions()
        self._spin_boxes: dict[str, QDoubleSpinBox] = {}
        self._direct_spin_boxes: dict[str, QDoubleSpinBox] = {}
        self._text_inputs: dict[str, QLineEdit] = {}
        self._connection_side_combo: QComboBox | None = None
        self._is_syncing_inputs = False
        self._is_syncing_direct_inputs = False
        self.drawing_widget = TopViewDrawingWidget(self.default_dims)
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
        group = QGroupBox("Order Details")
        form = QFormLayout(group)
        self._add_text_input(form, "job_order_no", "Job Order No.", self.default_dims.job_order_no)
        self._add_text_input(form, "coil_unique_id", "Coil Unique ID", self.default_dims.coil_unique_id)
        self._add_text_input(form, "coil_type", "Coil Type", self.default_dims.coil_type)
        return group

    def _build_main_specs_group(self):
        group = QGroupBox("Main Specs")
        form = QFormLayout(group)
        self._add_direct_spin(form, "fin_length_direct", "Fin Length", self.default_dims.fin_length, 20.0, 6000.0)
        self._add_spin(form, "tubes_per_row", "Tubes per row (TPR)", self.default_dims.tubes_per_row, 1.0, 300.0, decimals=0)
        self._add_spin(form, "number_of_rows", "No. of Rows", self.default_dims.number_of_rows, 1.0, 40.0, decimals=0)
        self._add_spin(form, "number_of_circuits", "No. of Circuits", self.default_dims.number_of_circuits, 1.0, 100.0, decimals=0)
        self._add_spin(form, "fpi", "FPI", self.default_dims.fpi, 1, 60, decimals=0)
        self._add_spin(form, "tube_dia_inch", "Tube Dia (inch)", self.default_dims.tube_dia_inch, 0.1, 2.0, decimals=3)
        self._add_spin(form, "header_dia", "Header Dia", self.default_dims.header_dia, 2.0, 500.0)
        return group

    def _build_pitch_group(self):
        group = QGroupBox("Pitch")
        form = QFormLayout(group)
        self._add_spin(form, "top_feature_tube_dia", "Tube Dia", self.default_dims.top_feature_tube_dia, 2.0, 80.0, decimals=2)
        self._add_spin(form, "top_feature_pitch_vertical", "Vertical", self.default_dims.top_feature_pitch_vertical, 5.0, 200.0, decimals=2)
        self._add_spin(form, "top_feature_pitch_horizontal", "Horizontal", self.default_dims.top_feature_pitch_horizontal, 5.0, 200.0, decimals=2)
        self._add_spin(form, "top_feature_circle_1_dia", "Circle 1 Dia", self.default_dims.top_feature_circle_1_dia, 2.0, 80.0, decimals=2)
        self._add_spin(form, "top_feature_circle_2_dia", "Circle 2 Dia", self.default_dims.top_feature_circle_2_dia, 2.0, 80.0, decimals=2)
        return group

    def _build_plate_group(self):
        group = QGroupBox("Plate / Overall")
        form = QFormLayout(group)
        self._add_spin(form, "sheet_metal_thickness", "Sheet Metal Thickness", self.default_dims.sheet_metal_thickness, 0.5, 10.0, decimals=2)
        self._add_spin(form, "right_panel_width", "Return Side Plate", self.default_dims.right_panel_width, 5, 2000)
        self._add_spin(form, "left_panel_width", "Header Side Plate", self.default_dims.left_panel_width, 5, 2000)
        self._add_spin(form, "top_plate", "Top Plate", self.default_dims.top_plate, 5, 1000)
        self._add_spin(form, "bottom_plate", "Bottom Plate", self.default_dims.bottom_plate, 5, 1000)
        self._add_spin(form, "front_header_band_width", "Blank Off Width", self.default_dims.front_header_band_width, 20, 3000)
        self._add_spin(form, "core_width", "Total Width", self.default_dims.core_width, 60, 3000)
        self._add_spin(form, "front_total_height", "Total Height", self.default_dims.front_total_height, 200, 6000)
        self._spin_boxes["front_total_height"].setReadOnly(True)
        self._spin_boxes["front_total_height"].setToolTip("Calculated: (TPR × Vertical Pitch) + Top Plate + Bottom Plate")
        self._add_spin(form, "left_pipe_offset", "Header Extension", self.default_dims.left_pipe_offset, 0, 2000)
        return group

    def _build_first_bend_group(self):
        group = QGroupBox("First Bend")
        form = QFormLayout(group)
        self._add_spin(form, "first_bend_header_side", "Header Side Plate", self.default_dims.first_bend_header_side, 0.0, 200.0)
        self._add_spin(form, "first_bend_return_side", "Return Side Plate", self.default_dims.first_bend_return_side, 0.0, 200.0)
        self._add_spin(form, "first_bend_top_plate", "Top Plate", self.default_dims.first_bend_top_plate, 0.0, 200.0)
        self._add_spin(form, "first_bend_bottom_plate", "Bottom Plate", self.default_dims.first_bend_bottom_plate, 0.0, 200.0)
        self._add_spin(form, "first_bend_blank_off", "Blank Off", self.default_dims.first_bend_blank_off, 0.0, 200.0)
        self._add_spin(form, "first_bend_intermediate_plate", "Intermediate Plate", self.default_dims.first_bend_intermediate_plate, 0.0, 200.0)
        return group

    def _build_additional_group(self):
        group = QGroupBox("Additional Inputs")
        form = QFormLayout(group)
        self._add_spin(form, "top_total_length", "Top Total Length", self.default_dims.top_total_length, 500, 6000)
        self._spin_boxes["top_total_length"].setReadOnly(True)
        self._add_spin(form, "top_intermediate_length", "Top Intermediate Length", self.default_dims.top_intermediate_length, 100, 6000)
        self._spin_boxes["top_intermediate_length"].setReadOnly(True)
        self._add_spin(form, "front_total_width", "Front Total Width", self.default_dims.front_total_width, 200, 6000)
        self._spin_boxes["front_total_width"].setReadOnly(True)
        self._add_spin(form, "left_pipe_length", "Stub Length", self.default_dims.left_pipe_length, 10, 3000)
        self._add_spin(form, "nozzle_projection", "Nozzle Projection", self.default_dims.nozzle_projection, 10, 500)
        self._add_spin(form, "header_extension_length", "Header Ext. Length", self.default_dims.header_extension_length, 20, 3000)
        self._add_spin(form, "header_box_height", "Header Box Height", self.default_dims.header_box_height, 40, 2000)
        self._spin_boxes["header_box_height"].setReadOnly(True)
        self._add_spin(form, "right_cap_thickness", "Header Flange First Bend", self.default_dims.right_cap_thickness, 2, 400)
        self._add_spin(form, "circle_diameter", "Circle Diameter", self.default_dims.circle_diameter, 2.0, 40.0, decimals=2)
        self._add_spin(form, "blank_off_bend", "Blank Off Bend", self.default_dims.blank_off_bend, 0.0, 200.0)
        self._add_spin(form, "top_feature_tube_height", "Feature Tube Height", self.default_dims.top_feature_tube_height, 10.0, 400.0, decimals=2)
        self._spin_boxes["top_feature_tube_height"].setReadOnly(True)
        self._add_spin(form, "top_feature_pipe_length", "Feature Pipe Length", self.default_dims.top_feature_pipe_length, 2.0, 200.0, decimals=2)
        connection_combo = QComboBox()
        connection_combo.addItems(["LHS", "RHS"])
        connection_combo.setCurrentText(self.default_dims.connection_side)
        connection_combo.currentTextChanged.connect(self._apply_changes)
        self._connection_side_combo = connection_combo
        form.addRow("Connection", connection_combo)
        return group

    def _build_derived_group(self):
        group = QGroupBox("Derived")
        form = QFormLayout(group)
        form.addRow("Fin Length (FL)", self._fl_label)
        form.addRow("Fin Height (FH)", self._fh_label)
        return group

    def _build_direct_group(self):
        group = QGroupBox("Direct Dimension Edit")
        form = QFormLayout(group)
        self._add_direct_spin(form, "top_lead_span", "Top Lead Span", self.default_dims.top_lead_span, 20.0, 6000.0)
        self._direct_spin_boxes["top_lead_span"].setReadOnly(True)
        self._add_direct_spin(form, "fin_height_direct", "Fin Height (FH)", self.default_dims.fin_height, 20.0, 6000.0)
        return group

    def _build_buttons_row(self):
        layout = QHBoxLayout()
        apply_btn = QPushButton("Apply")
        reset_btn = QPushButton("Reset")
        print_btn = QPushButton("Print")
        export_btn = QPushButton("Export PNG")
        apply_btn.clicked.connect(self._apply_changes)
        reset_btn.clicked.connect(self._reset_defaults)
        print_btn.clicked.connect(self._print_drawing)
        export_btn.clicked.connect(self._export_png)
        layout.addWidget(apply_btn)
        layout.addWidget(reset_btn)
        layout.addWidget(print_btn)
        layout.addWidget(export_btn)
        return layout

    def _build_zoom_row(self):
        layout = QHBoxLayout()
        zoom_out = QPushButton("Zoom -")
        zoom_in = QPushButton("Zoom +")
        zoom_reset = QPushButton("Reset View")
        zoom_out.clicked.connect(lambda: self._zoom(-1))
        zoom_in.clicked.connect(lambda: self._zoom(1))
        zoom_reset.clicked.connect(self._zoom_reset)
        self._zoom_label.setMinimumWidth(55)
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(zoom_out)
        layout.addWidget(zoom_in)
        layout.addWidget(zoom_reset)
        layout.addWidget(self._zoom_label)
        return layout

    def _zoom(self, direction):
        factor = 1.15 if direction > 0 else (1.0 / 1.15)
        self.drawing_widget.zoom_by(factor)
        self._zoom_label.setText(f"{self.drawing_widget.zoom_percent()}%")

    def _zoom_reset(self):
        self.drawing_widget.reset_view()
        self._zoom_label.setText(f"{self.drawing_widget.zoom_percent()}%")

    def _add_spin(self, form, key, label, default_value, minimum, maximum, decimals=1):
        spin = QDoubleSpinBox()
        spin.setDecimals(decimals)
        spin.setRange(minimum, maximum)
        spin.setValue(default_value)
        spin.setSingleStep(1.0)
        spin.setKeyboardTracking(False)
        spin.valueChanged.connect(self._apply_changes)
        self._spin_boxes[key] = spin
        form.addRow(label, spin)

    def _add_direct_spin(self, form, key, label, default_value, minimum, maximum, decimals=1):
        spin = QDoubleSpinBox()
        spin.setDecimals(decimals)
        spin.setRange(minimum, maximum)
        spin.setValue(default_value)
        spin.setSingleStep(1.0)
        spin.setKeyboardTracking(False)
        spin.valueChanged.connect(self._apply_direct_changes)
        self._direct_spin_boxes[key] = spin
        form.addRow(label, spin)

    def _add_text_input(self, form, key, label, default_value):
        text_input = QLineEdit()
        text_input.setText(str(default_value))
        text_input.textChanged.connect(self._apply_changes)
        self._text_inputs[key] = text_input
        form.addRow(label, text_input)

    def _collect_dimensions(self) -> CoilDimensions:
        connection_side = self.default_dims.connection_side
        if self._connection_side_combo is not None:
            connection_side = self._connection_side_combo.currentText()
        job_order_no = self._text_inputs.get("job_order_no", QLineEdit()).text() or self.default_dims.job_order_no
        coil_unique_id = self._text_inputs.get("coil_unique_id", QLineEdit()).text() or self.default_dims.coil_unique_id
        coil_type = self._text_inputs.get("coil_type", QLineEdit()).text() or self.default_dims.coil_type
        top_plate_value = self._spin_boxes["top_plate"].value()
        bottom_plate_value = self._spin_boxes["bottom_plate"].value()
        tubes_per_row_value = self._spin_boxes["tubes_per_row"].value()
        vertical_pitch_value = self._spin_boxes["top_feature_pitch_vertical"].value()
        horizontal_pitch_value = self._spin_boxes["top_feature_pitch_horizontal"].value()
        number_of_rows_value = self._spin_boxes["number_of_rows"].value()
        calculated_total_height = (tubes_per_row_value * vertical_pitch_value) + top_plate_value + bottom_plate_value
        calculated_feature_tube_height = horizontal_pitch_value * (number_of_rows_value - 1.0)
        calculated_header_box_height = horizontal_pitch_value * number_of_rows_value
        left_pipe_offset_value = self._spin_boxes["left_pipe_offset"].value()
        left_panel_width_value = self._spin_boxes["left_panel_width"].value()
        right_panel_width_value = self._spin_boxes["right_panel_width"].value()
        fin_length_spin = self._direct_spin_boxes.get("fin_length_direct")
        fin_length_value = max(20.0, fin_length_spin.value()) if fin_length_spin else 20.0
        front_total_width_value = left_panel_width_value + fin_length_value + right_panel_width_value
        front_header_band_width_value = self._spin_boxes["front_header_band_width"].value()
        blank_off_w_value = max(left_panel_width_value, min(front_header_band_width_value, left_panel_width_value + fin_length_value))
        calculated_top_intermediate_length = max(100.0, front_total_width_value - left_panel_width_value + blank_off_w_value)
        calculated_top_total_length = max(500.0, left_pipe_offset_value + calculated_top_intermediate_length)
        top_total_length_value = self._spin_boxes["top_total_length"].value()
        first_bend_blank_off = self._spin_boxes["first_bend_blank_off"].value()
        current_dims = getattr(self.drawing_widget, "_dims", self.default_dims)
        return CoilDimensions(
            top_total_length=max(top_total_length_value, calculated_top_total_length),
            top_intermediate_length=calculated_top_intermediate_length,
            front_total_width=front_total_width_value,
            front_total_height=calculated_total_height,
            left_panel_width=left_panel_width_value,
            right_panel_width=right_panel_width_value,
            fin_length_override=fin_length_value,
            top_bottom_margin=(top_plate_value + bottom_plate_value) / 2.0,
            top_plate=top_plate_value,
            bottom_plate=bottom_plate_value,
            core_width=self._spin_boxes["core_width"].value(),
            left_pipe_offset=left_pipe_offset_value,
            left_pipe_length=self._spin_boxes["left_pipe_length"].value(),
            nozzle_projection=self._spin_boxes["nozzle_projection"].value(),
            header_extension_length=self._spin_boxes["header_extension_length"].value(),
            header_box_height=calculated_header_box_height,
            right_cap_thickness=self._spin_boxes["right_cap_thickness"].value(),
            front_header_band_width=front_header_band_width_value,
            top_small_offset_1=current_dims.top_small_offset_1,
            top_small_offset_2=current_dims.top_small_offset_2,
            fpi=self._spin_boxes["fpi"].value(),
            tube_dia_inch=self._spin_boxes["tube_dia_inch"].value(),
            pitch_vertical=vertical_pitch_value,
            pitch_horizontal=horizontal_pitch_value,
            connection_side=connection_side,
            job_order_no=job_order_no,
            coil_unique_id=coil_unique_id,
            coil_type=coil_type,
            circle_diameter=self._spin_boxes["circle_diameter"].value(),
            tubes_per_row=tubes_per_row_value,
            number_of_rows=number_of_rows_value,
            number_of_circuits=self._spin_boxes["number_of_circuits"].value(),
            header_dia=self._spin_boxes["header_dia"].value(),
            blank_off_bend=first_bend_blank_off,
            top_feature_tube_dia=self._spin_boxes["top_feature_tube_dia"].value(),
            top_feature_tube_height=calculated_feature_tube_height,
            top_feature_pipe_length=self._spin_boxes["top_feature_pipe_length"].value(),
            top_feature_pitch_vertical=vertical_pitch_value,
            top_feature_pitch_horizontal=horizontal_pitch_value,
            top_feature_circle_1_dia=self._spin_boxes["top_feature_circle_1_dia"].value(),
            top_feature_circle_2_dia=self._spin_boxes["top_feature_circle_2_dia"].value(),
            sheet_metal_thickness=self._spin_boxes["sheet_metal_thickness"].value(),
            first_bend_header_side=self._spin_boxes["first_bend_header_side"].value(),
            first_bend_return_side=self._spin_boxes["first_bend_return_side"].value(),
            first_bend_top_plate=self._spin_boxes["first_bend_top_plate"].value(),
            first_bend_bottom_plate=self._spin_boxes["first_bend_bottom_plate"].value(),
            first_bend_blank_off=first_bend_blank_off,
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
        fin_length = self._direct_spin_boxes["fin_length_direct"].value()
        fin_height = self._direct_spin_boxes["fin_height_direct"].value()
        dims.fin_length_override = max(20.0, fin_length)
        dims.front_total_width = dims.left_panel_width + dims.fin_length + dims.right_panel_width
        total_plate_span = max(10.0, dims.front_total_height - fin_height)
        previous_total = max(0.001, dims.top_plate + dims.bottom_plate)
        top_ratio = max(0.0, min(dims.top_plate / previous_total, 1.0))
        dims.top_plate = total_plate_span * top_ratio
        dims.bottom_plate = total_plate_span - dims.top_plate
        dims.top_bottom_margin = (dims.top_plate + dims.bottom_plate) / 2.0
        dims = dims.sanitized()
        self._sync_spin_values(dims)
        self._apply_changes()

    def _sync_spin_values(self, dims: CoilDimensions) -> None:
        values = {
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
            "top_feature_tube_height": dims.top_feature_tube_height, "top_feature_pipe_length": dims.top_feature_pipe_length,
            "top_feature_pitch_vertical": dims.top_feature_pitch_vertical, "top_feature_pitch_horizontal": dims.top_feature_pitch_horizontal,
            "top_feature_circle_1_dia": dims.top_feature_circle_1_dia, "top_feature_circle_2_dia": dims.top_feature_circle_2_dia,
            "sheet_metal_thickness": dims.sheet_metal_thickness, "first_bend_header_side": dims.first_bend_header_side,
            "first_bend_return_side": dims.first_bend_return_side, "first_bend_top_plate": dims.first_bend_top_plate,
            "first_bend_bottom_plate": dims.first_bend_bottom_plate, "first_bend_blank_off": dims.first_bend_blank_off,
            "first_bend_intermediate_plate": dims.first_bend_intermediate_plate,
        }
        self._is_syncing_inputs = True
        try:
            for key, value in values.items():
                spin = self._spin_boxes.get(key)
                if spin is None or abs(spin.value() - value) < 1e-6:
                    continue
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)
        finally:
            self._is_syncing_inputs = False

    def _sync_direct_spin_values(self, dims: CoilDimensions) -> None:
        values = {"top_lead_span": dims.top_lead_span, "fin_length_direct": dims.fin_length, "fin_height_direct": dims.fin_height}
        self._is_syncing_direct_inputs = True
        try:
            for key, value in values.items():
                spin = self._direct_spin_boxes.get(key)
                if spin is None or abs(spin.value() - value) < 1e-6:
                    continue
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)
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
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Top View", "top_view.png", "PNG Image (*.png)")
        if not file_path:
            return
        if not file_path.lower().endswith(".png"):
            file_path += ".png"
        if not self.drawing_widget.export_png(file_path):
            QMessageBox.warning(self, "Export Failed", "Could not save PNG.")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Coil Helvix - Top View")
    access_ok, access_message = _enforce_startup_access()
    if not access_ok:
        if access_message:
            QMessageBox.critical(None, "Access Denied", access_message)
        sys.exit(1)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
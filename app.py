import math
import sys
import json
import re
from dataclasses import dataclass, fields, replace

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPolygonF, QTransform
from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

try:
    import ezdxf
except Exception:
    ezdxf = None

try:
    from ezdxf.enums import TextEntityAlignment
except Exception:
    TextEntityAlignment = None


@dataclass
class CoilDimensions:
    top_total_length: float = 1745.0
    top_intermediate_length: float = 1575.0
    front_total_width: float = 1430.0
    front_total_height: float = 1430.0
    left_panel_width: float = 35.0
    right_panel_width: float = 65.0
    top_bottom_margin: float = 15.0
    top_plate: float = 15.0
    bottom_plate: float = 15.0
    core_width: float = 320.0
    left_pipe_offset: float = 170.0
    left_pipe_length: float = 180.0
    nozzle_projection: float = 75.0
    header_box_height: float = 207.6
    right_cap_thickness: float = 12.0
    front_header_band_width: float = 185.0
    top_small_offset_1: float = 56.2
    top_small_offset_2: float = 56.2
    fpi: float = 13.0
    tube_dia_inch: float = 0.625
    pitch_vertical: float = 33.4
    pitch_horizontal: float = 35.2
    connection_side: str = "LHS"
    circle_diameter: float = 8.4
    tubes_per_row: float = 42.0
    number_of_rows: float = 6.0
    number_of_circuits: float = 13.0
    header_dia: float = 170.0
    blank_off_bend: float = 12.0

    @property
    def fin_length(self) -> float:
        return max(20.0, self.front_total_width - self.left_panel_width - self.right_panel_width)

    @property
    def fin_height(self) -> float:
        return max(20.0, self.front_total_height - self.top_plate - self.bottom_plate)

    @property
    def top_lead_span(self) -> float:
        return self.top_total_length - self.front_total_width + self.left_panel_width

    def sanitized(self) -> "CoilDimensions":
        value = replace(self)
        value.top_total_length = max(500.0, value.top_total_length)
        value.front_total_width = max(300.0, value.front_total_width)
        value.front_total_height = max(300.0, value.front_total_height)
        value.core_width = max(80.0, value.core_width)
        value.top_intermediate_length = max(100.0, min(value.top_intermediate_length, value.top_total_length))

        panel_limit = max(40.0, value.front_total_width - 60.0)
        value.left_panel_width = max(5.0, min(value.left_panel_width, panel_limit - 5.0))

        min_top_total = value.front_total_width - value.left_panel_width + 20.0
        value.top_total_length = max(value.top_total_length, min_top_total)

        value.right_panel_width = max(5.0, min(value.right_panel_width, panel_limit - value.left_panel_width))

        margin_limit = (value.front_total_height / 2.0) - 10.0
        legacy_margin = max(5.0, min(value.top_bottom_margin, margin_limit))

        default_top_plate = CoilDimensions.top_plate
        default_bottom_plate = CoilDimensions.bottom_plate
        if (
            abs(value.top_plate - default_top_plate) < 1e-6
            and abs(value.bottom_plate - default_bottom_plate) < 1e-6
            and abs(legacy_margin - CoilDimensions.top_bottom_margin) > 1e-6
        ):
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

        value.left_pipe_offset = max(0.0, min(value.left_pipe_offset, value.top_total_length - 10.0))
        value.left_pipe_length = max(
            10.0,
            min(value.left_pipe_length, value.top_total_length - value.left_pipe_offset),
        )

        value.header_box_height = max(40.0, min(value.header_box_height, value.core_width))
        value.nozzle_projection = max(15.0, value.nozzle_projection)
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
        value.header_dia = max(20.0, min(value.header_dia, 500.0))
        value.blank_off_bend = max(0.0, min(value.blank_off_bend, 200.0))

        normalized_connection = str(value.connection_side).strip().upper()
        if normalized_connection not in {"LHS", "RHS"}:
            normalized_connection = "LHS"
        value.connection_side = normalized_connection
        return value


class DxfPainterAdapter:
    METADATA_LAYER = "COIL_META"
    METADATA_PREFIX = "COIL_HELVIX_DIMS:"

    def __init__(self, file_path: str, canvas_height: float) -> None:
        if ezdxf is None:
            raise RuntimeError("DXF export requires the 'ezdxf' package.")

        self._file_path = file_path
        self._canvas_height = canvas_height
        self._doc = ezdxf.new("R2010")
        self._doc.units = 4
        self._msp = self._doc.modelspace()

        self._ensure_layer("DRAWING", 7)
        self._ensure_layer("TEXT", 7)
        self._ensure_layer(self.METADATA_LAYER, 8)
        self._ensure_linetype("DASHED")

        self._pen = QPen(QColor("#111111"), 1.0)
        self._brush = Qt.BrushStyle.NoBrush
        self._font = QFont("Arial", 10)
        self._clip_enabled = False

        self._matrix = self._identity_matrix()
        self._stack: list[tuple[QPen, object, QFont, bool, list[list[float]]]] = []

    def save_to_file(self) -> None:
        self._doc.saveas(self._file_path)

    def _ensure_layer(self, name: str, color: int) -> None:
        if name not in self._doc.layers:
            self._doc.layers.add(name, color=color)

    def _ensure_linetype(self, name: str) -> None:
        if name in self._doc.linetypes:
            return
        if name == "DASHED":
            self._doc.linetypes.new(name, dxfattribs={"description": "Dashed __ __", "pattern": [0.5, 0.25, -0.25]})

    def save(self) -> None:
        matrix_copy = [row[:] for row in self._matrix]
        self._stack.append((QPen(self._pen), self._brush, QFont(self._font), self._clip_enabled, matrix_copy))

    def restore(self) -> None:
        if not self._stack:
            return
        pen, brush, font, clip_enabled, matrix = self._stack.pop()
        self._pen = pen
        self._brush = brush
        self._font = font
        self._clip_enabled = clip_enabled
        self._matrix = matrix

    def setRenderHint(self, *_args, **_kwargs) -> None:
        return

    def fillRect(self, *_args, **_kwargs) -> None:
        return

    def setPen(self, pen) -> None:
        if isinstance(pen, QPen):
            self._pen = QPen(pen)
        elif isinstance(pen, QColor):
            self._pen = QPen(pen, self._pen.widthF())

    def pen(self) -> QPen:
        return self._pen

    def setBrush(self, brush) -> None:
        self._brush = brush

    def brush(self):
        return self._brush

    def setFont(self, font: QFont) -> None:
        self._font = QFont(font)

    def setClipPath(self, _path: QPainterPath) -> None:
        self._clip_enabled = True

    def translate(self, dx: float, dy: float) -> None:
        self._matrix = self._matrix_multiply(self._matrix, [[1.0, 0.0, dx], [0.0, 1.0, dy], [0.0, 0.0, 1.0]])

    def scale(self, sx: float, sy: float | None = None) -> None:
        sy_value = sx if sy is None else sy
        self._matrix = self._matrix_multiply(self._matrix, [[sx, 0.0, 0.0], [0.0, sy_value, 0.0], [0.0, 0.0, 1.0]])

    def rotate(self, angle_deg: float) -> None:
        angle = math.radians(angle_deg)
        c = math.cos(angle)
        s = math.sin(angle)
        rotation = [[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]]
        self._matrix = self._matrix_multiply(self._matrix, rotation)

    def drawLine(self, *args) -> None:
        if self._clip_enabled:
            return

        if len(args) == 2 and isinstance(args[0], QPointF) and isinstance(args[1], QPointF):
            x1, y1 = args[0].x(), args[0].y()
            x2, y2 = args[1].x(), args[1].y()
        elif len(args) == 4:
            x1, y1, x2, y2 = map(float, args)
        else:
            return

        p1 = self._transform_point(x1, y1)
        p2 = self._transform_point(x2, y2)
        self._msp.add_line(self._to_dxf(p1), self._to_dxf(p2), dxfattribs=self._line_attribs())

    def drawRect(self, rect: QRectF) -> None:
        x = rect.x()
        y = rect.y()
        w = rect.width()
        h = rect.height()
        self.drawLine(QPointF(x, y), QPointF(x + w, y))
        self.drawLine(QPointF(x + w, y), QPointF(x + w, y + h))
        self.drawLine(QPointF(x + w, y + h), QPointF(x, y + h))
        self.drawLine(QPointF(x, y + h), QPointF(x, y))

    def drawEllipse(self, *args) -> None:
        if len(args) == 1 and isinstance(args[0], QRectF):
            rect = args[0]
            cx = rect.x() + (rect.width() / 2.0)
            cy = rect.y() + (rect.height() / 2.0)
            rx = rect.width() / 2.0
            ry = rect.height() / 2.0
        elif len(args) == 3 and isinstance(args[0], QPointF):
            center = args[0]
            cx = center.x()
            cy = center.y()
            rx = float(args[1])
            ry = float(args[2])
        else:
            return

        pts = self._ellipse_points(cx, cy, rx, ry, 72)
        self._add_polyline(pts, close=True)

    def drawArc(self, rect: QRectF, start_angle: int, span_angle: int) -> None:
        cx = rect.x() + (rect.width() / 2.0)
        cy = rect.y() + (rect.height() / 2.0)
        rx = rect.width() / 2.0
        ry = rect.height() / 2.0

        start_deg = start_angle / 16.0
        span_deg = span_angle / 16.0
        segments = max(16, int(abs(span_deg) / 7.0))
        points: list[tuple[float, float]] = []
        for index in range(segments + 1):
            t = index / segments
            ang = math.radians(start_deg + (span_deg * t))
            x = cx + (rx * math.cos(ang))
            y = cy - (ry * math.sin(ang))
            points.append(self._transform_point(x, y))

        self._add_polyline(points, close=False)

    def drawText(self, *args) -> None:
        if len(args) != 3:
            return

        rect, _flags, text = args
        if not isinstance(rect, QRectF):
            return

        x = rect.x() + (rect.width() / 2.0)
        y = rect.y() + (rect.height() / 2.0)
        anchor = self._transform_point(x, y)
        rotation = self._rotation_deg()

        font_size = self._font.pointSizeF()
        if font_size <= 0:
            font_size = float(max(9, self._font.pointSize()))

        entity = self._msp.add_text(
            str(text),
            dxfattribs={
                "layer": "TEXT",
                "height": max(8.0, font_size),
                "rotation": rotation,
                "true_color": self._rgb_to_true_color(self._pen.color()),
            },
        )

        anchor_pt = self._to_dxf(anchor)
        if TextEntityAlignment is not None:
            try:
                entity.set_placement(anchor_pt, align=TextEntityAlignment.MIDDLE_CENTER)
                return
            except Exception:
                pass

        try:
            entity.set_pos(anchor_pt, align="MIDDLE_CENTER")
        except Exception:
            entity.dxf.insert = anchor_pt

    def drawPolygon(self, polygon: QPolygonF) -> None:
        points = [self._transform_point(point.x(), point.y()) for point in polygon]
        self._add_polyline(points, close=True)

    def drawPath(self, path: QPainterPath) -> None:
        if self._clip_enabled:
            return
        if not isinstance(path, QPainterPath):
            return

        subpaths = path.toSubpathPolygons()
        for polygon in subpaths:
            points = [self._transform_point(point.x(), point.y()) for point in polygon]
            if len(points) < 2:
                continue

            first_x, first_y = points[0]
            last_x, last_y = points[-1]
            is_closed = math.hypot(last_x - first_x, last_y - first_y) <= 1e-6
            if is_closed:
                points = points[:-1]
            if len(points) < 2:
                continue

            self._add_polyline(points, close=is_closed)

    def write_dimensions_metadata(self, dims: CoilDimensions) -> None:
        payload: dict[str, object] = {}
        for field_info in fields(CoilDimensions):
            field_value = getattr(dims, field_info.name)
            if isinstance(field_value, (int, float, str, bool)):
                payload[field_info.name] = field_value
            else:
                payload[field_info.name] = str(field_value)

        metadata_text = f"{self.METADATA_PREFIX}{json.dumps(payload, separators=(',', ':'), sort_keys=True)}"
        entity = self._msp.add_text(
            metadata_text,
            dxfattribs={
                "layer": self.METADATA_LAYER,
                "height": 2.5,
                "true_color": self._rgb_to_true_color(QColor("#666666")),
            },
        )
        entity.dxf.insert = (0.0, -1000000.0)

    def _line_attribs(self) -> dict:
        style = self._pen.style()
        linetype = "CONTINUOUS"
        if style in {
            Qt.PenStyle.DashLine,
            Qt.PenStyle.DashDotLine,
            Qt.PenStyle.DashDotDotLine,
            Qt.PenStyle.CustomDashLine,
        }:
            linetype = "DASHED"

        return {
            "layer": "DRAWING",
            "true_color": self._rgb_to_true_color(self._pen.color()),
            "linetype": linetype,
        }

    def _add_polyline(self, points: list[tuple[float, float]], close: bool) -> None:
        if len(points) < 2:
            return
        dxf_points = [self._to_dxf(point) for point in points]
        self._msp.add_lwpolyline(dxf_points, close=close, dxfattribs=self._line_attribs())

    def _ellipse_points(
        self,
        cx: float,
        cy: float,
        rx: float,
        ry: float,
        segments: int,
    ) -> list[tuple[float, float]]:
        points: list[tuple[float, float]] = []
        for index in range(segments + 1):
            t = (2.0 * math.pi) * (index / segments)
            x = cx + (rx * math.cos(t))
            y = cy + (ry * math.sin(t))
            points.append(self._transform_point(x, y))
        return points

    def _rotation_deg(self) -> float:
        p0 = self._transform_point(0.0, 0.0)
        p1 = self._transform_point(1.0, 0.0)
        vx = p1[0] - p0[0]
        vy = p1[1] - p0[1]
        return math.degrees(math.atan2(-vy, vx))

    def _rgb_to_true_color(self, color: QColor) -> int:
        return (int(color.red()) << 16) + (int(color.green()) << 8) + int(color.blue())

    def _to_dxf(self, point: tuple[float, float]) -> tuple[float, float]:
        x, y = point
        return float(x), float(self._canvas_height - y)

    def _transform_point(self, x: float, y: float) -> tuple[float, float]:
        tx = (self._matrix[0][0] * x) + (self._matrix[0][1] * y) + self._matrix[0][2]
        ty = (self._matrix[1][0] * x) + (self._matrix[1][1] * y) + self._matrix[1][2]
        return tx, ty

    @staticmethod
    def _identity_matrix() -> list[list[float]]:
        return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]

    @staticmethod
    def _matrix_multiply(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
        return [
            [
                (a[0][0] * b[0][0]) + (a[0][1] * b[1][0]) + (a[0][2] * b[2][0]),
                (a[0][0] * b[0][1]) + (a[0][1] * b[1][1]) + (a[0][2] * b[2][1]),
                (a[0][0] * b[0][2]) + (a[0][1] * b[1][2]) + (a[0][2] * b[2][2]),
            ],
            [
                (a[1][0] * b[0][0]) + (a[1][1] * b[1][0]) + (a[1][2] * b[2][0]),
                (a[1][0] * b[0][1]) + (a[1][1] * b[1][1]) + (a[1][2] * b[2][1]),
                (a[1][0] * b[0][2]) + (a[1][1] * b[1][2]) + (a[1][2] * b[2][2]),
            ],
            [
                (a[2][0] * b[0][0]) + (a[2][1] * b[1][0]) + (a[2][2] * b[2][0]),
                (a[2][0] * b[0][1]) + (a[2][1] * b[1][1]) + (a[2][2] * b[2][1]),
                (a[2][0] * b[0][2]) + (a[2][1] * b[1][2]) + (a[2][2] * b[2][2]),
            ],
        ]


class CoilDrawingWidget(QWidget):
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
        self.setMinimumSize(1000, 700)

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
        before_scale, before_offset_x, before_offset_y = self._calculate_transform(
            rect,
            layout["world_w"],
            layout["world_h"],
            apply_view_transform=True,
        )

        cursor = event.position()
        world_x = (cursor.x() - before_offset_x) / before_scale
        world_y = (cursor.y() - before_offset_y) / before_scale

        factor = 1.12 if delta > 0 else (1.0 / 1.12)
        old_zoom = self._zoom
        self._zoom = max(self._min_zoom, min(self._zoom * factor, self._max_zoom))
        if abs(self._zoom - old_zoom) < 1e-6:
            event.accept()
            return

        after_scale, after_offset_x, after_offset_y = self._calculate_transform(
            rect,
            layout["world_w"],
            layout["world_h"],
            apply_view_transform=True,
        )
        new_cursor_x = after_offset_x + (world_x * after_scale)
        new_cursor_y = after_offset_y + (world_y * after_scale)

        self._pan_offset = QPointF(
            self._pan_offset.x() + (cursor.x() - new_cursor_x),
            self._pan_offset.y() + (cursor.y() - new_cursor_y),
        )
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

    def render_to_painter(
        self,
        painter: QPainter,
        target_rect: QRectF,
        background: QColor,
        apply_view_transform: bool = False,
    ) -> None:
        if not isinstance(target_rect, QRectF):
            target_rect = QRectF(target_rect)

        layout = self._layout_data()
        world_w = layout["world_w"]
        world_h = layout["world_h"]

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.fillRect(target_rect, background)

        scale, offset_x, offset_y = self._calculate_transform(
            target_rect,
            world_w,
            world_h,
            apply_view_transform=apply_view_transform,
        )

        painter.translate(offset_x, offset_y)
        painter.scale(scale, scale)
        self._draw_scene(painter, layout)
        painter.restore()

    def _calculate_transform(
        self,
        target_rect: QRectF,
        world_w: float,
        world_h: float,
        apply_view_transform: bool,
    ) -> tuple[float, float, float]:
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

    def _layout_data(self) -> dict[str, float]:
        dims = self._dims
        left_side_x = 50.0
        top_view_y = 40.0
        gap = 300.0

        front_x = left_side_x + dims.core_width + gap
        left_extension = max(0.0, dims.front_header_band_width - dims.left_panel_width)
        front_face_left = front_x + left_extension
        front_total_draw_w = left_extension + dims.front_total_width
        front_y = top_view_y + dims.core_width + 265.0
        right_side_x = front_x + front_total_draw_w + gap

        top_x = front_face_left + ((dims.front_total_width - dims.top_total_length) / 2.0)

        world_w = right_side_x + dims.core_width + 90.0
        world_h = front_y + dims.front_total_height + 240.0

        return {
            "left_side_x": left_side_x,
            "right_side_x": right_side_x,
            "top_x": top_x,
            "top_y": top_view_y,
            "front_x": front_x,
            "front_y": front_y,
            "world_w": world_w,
            "world_h": world_h,
        }

    def _draw_scene(self, painter: QPainter, layout: dict[str, float]) -> None:
        self._draw_top_view(painter, layout)
        self._draw_front_view(painter, layout)
        self._draw_side_view(
            painter,
            x=layout["left_side_x"],
            y=layout["front_y"],
            label="HEADER SIDE",
            show_vertical_dims=False,
            mirror=False,
        )
        self._draw_side_view(
            painter,
            x=layout["right_side_x"],
            y=layout["front_y"],
            label="RETURN END SIDE",
            show_vertical_dims=True,
            mirror=True,
        )

    def export_to_dxf(self, file_path: str) -> None:
        layout = self._layout_data()
        dxf_painter = DxfPainterAdapter(file_path=file_path, canvas_height=layout["world_h"] + 260.0)
        self._draw_scene(dxf_painter, layout)
        dxf_painter.write_dimensions_metadata(self._dims)
        dxf_painter.save_to_file()

    def _draw_top_view(self, painter: QPainter, layout: dict[str, float]) -> None:
        dims = self._dims
        x0 = layout["top_x"]
        y0 = layout["top_y"]

        total_end = x0 + dims.top_total_length
        face_start = total_end - dims.front_total_width
        face_end = total_end
        fin_start = face_start + dims.left_panel_width
        fin_end = face_end - dims.right_panel_width
        intermediate_start = total_end - dims.top_intermediate_length

        pipe_start = x0 + dims.left_pipe_offset
        pipe_end = pipe_start + dims.left_pipe_length

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

        left_stub = max(2.0, min(dims.blank_off_bend, top_h * 0.25))
        bottom_cover_start = min(face_start, intermediate_start)
        painter.drawLine(QPointF(face_start, left_gap_top_y), QPointF(fin_start, left_gap_top_y))
        painter.drawLine(QPointF(face_start, left_gap_top_y), QPointF(face_start, left_gap_top_y + left_stub))
        painter.drawLine(QPointF(bottom_cover_start, left_gap_bottom_y), QPointF(fin_start, left_gap_bottom_y))
        painter.drawLine(
            QPointF(bottom_cover_start, left_gap_bottom_y - left_stub),
            QPointF(bottom_cover_start, left_gap_bottom_y),
        )
        painter.drawLine(QPointF(fin_start, y0), QPointF(fin_start, y0 + top_h))

        painter.drawLine(QPointF(fin_end, cap_top_y), QPointF(fin_end, cap_bottom_y))
        painter.drawLine(QPointF(fin_end, cap_top_y), QPointF(face_end, cap_top_y))
        painter.drawLine(QPointF(fin_end, cap_bottom_y), QPointF(face_end, cap_bottom_y))

        nozzle_y_positions = [header_y + (header_h * 0.30), header_y + (header_h * 0.72)]
        for nozzle_y, name in zip(nozzle_y_positions, ["IN", "OUT"]):
            body_h = max(10.0, min(30.0, dims.header_dia / 9.5))
            neck_h = max(8.0, min(body_h - 2.0, body_h * 0.78))
            thread_len = min(28.0, max(16.0, dims.nozzle_projection * 0.34))
            body_end_x = x0 + dims.nozzle_projection

            flange_radius = body_h / 2.0
            flange_center_x = pipe_start
            neck_start_x = body_end_x
            neck_end_x = flange_center_x - flange_radius

            if neck_end_x < neck_start_x + 4.0:
                neck_end_x = neck_start_x + 4.0

            body_rect = QRectF(x0, nozzle_y - (body_h / 2.0), max(8.0, body_end_x - x0), body_h)
            neck_rect = QRectF(neck_start_x, nozzle_y - (neck_h / 2.0), max(4.0, neck_end_x - neck_start_x), neck_h)

            painter.drawRect(body_rect)
            painter.drawRect(neck_rect)
            painter.drawEllipse(QPointF(flange_center_x, nozzle_y), flange_radius, flange_radius)
            painter.drawLine(QPointF(flange_center_x + flange_radius, nozzle_y), QPointF(fin_start, nozzle_y))

            rib_start = x0 + 4.0
            rib_end = min(x0 + thread_len, body_end_x - 2.0)
            rib_x = rib_start
            while rib_x <= rib_end:
                painter.drawLine(QPointF(rib_x, body_rect.top()), QPointF(rib_x, body_rect.bottom()))
                rib_x += 6.0

            painter.drawEllipse(QPointF(x0 + (dims.nozzle_projection * 0.62), nozzle_y), 2.4, 2.4)

            arrow_left_x = x0 - 90.0
            arrow_right_x = x0 - 10.0
            painter.save()
            painter.setPen(QPen(self.DIM_COLOR, self.DIM_LINE_WIDTH))
            painter.drawLine(QPointF(arrow_left_x, nozzle_y), QPointF(arrow_right_x, nozzle_y))
            self._draw_arrow_head(painter, QPointF(arrow_right_x, nozzle_y), (1.0, 0.0), 7.0)
            painter.restore()

            painter.drawText(
                QRectF(arrow_left_x - 58.0, nozzle_y - 14.0, 52.0, 28.0),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                name,
            )

        tube_pen = QPen(self.TUBE_COLOR, 1.5)
        tube_pen.setStyle(Qt.PenStyle.DashLine)
        tube_pen.setDashPattern([8.0, 5.0])
        painter.setPen(tube_pen)

        tube_count = 6
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

        tube_step = (tube_bottom - tube_top) / max(1, tube_count - 1)
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

            tube_wall_visual = max(2.0, min(6.0, dims.tube_dia_inch * 7.36))
            wall_thickness = min(tube_wall_visual, loop_dia * 0.28)
            outer_dia = loop_dia + wall_thickness
            inner_dia = max(2.0, loop_dia - wall_thickness)

            outer_w = max(2.0, min(outer_dia, max_arc_width))
            inner_w = max(1.4, min(inner_dia, outer_w - 1.0, max_arc_width))
            flow_w = max(1.2, min((outer_w + inner_w) / 2.0, max_arc_width))

            loop_rect_outer = QRectF(fin_end - (outer_w / 2.0), y_mid - (outer_dia / 2.0), outer_w, outer_dia)
            loop_rect_inner = QRectF(fin_end - (inner_w / 2.0), y_mid - (inner_dia / 2.0), inner_w, inner_dia)
            loop_rect_flow = QRectF(fin_end - (flow_w / 2.0), y_top, flow_w, loop_dia)

            painter.drawArc(loop_rect_outer, 90 * 16, -180 * 16)
            painter.drawArc(loop_rect_inner, 90 * 16, -180 * 16)

            painter.save()
            painter.setPen(tube_pen)
            painter.drawArc(loop_rect_flow, 90 * 16, -180 * 16)
            painter.restore()

        self._draw_dim_h(painter, x0, fin_start, y0, -35.0, f"{fin_start - x0:.0f}")
        self._draw_dim_h(painter, x0, pipe_start, y0, -67.0, f"{dims.left_pipe_offset:.0f}")
        self._draw_dim_h(painter, pipe_start, pipe_end, y0, -67.0, f"{dims.left_pipe_length:.0f}")

        self._draw_dim_h(
            painter,
            x0,
            x0 + dims.nozzle_projection,
            y0 + top_h,
            48.0,
            f"{dims.nozzle_projection:.0f}",
        )
        self._draw_dim_h(painter, fin_start, fin_end, y0 + top_h, 48.0, f"{dims.fin_length:.0f} (FL)")
        self._draw_dim_h(painter, face_start, face_end, y0 + top_h, 86.0, f"{dims.front_total_width:.0f}")
        self._draw_dim_h(
            painter,
            intermediate_start,
            face_end,
            y0 + top_h,
            123.0,
            f"{dims.top_intermediate_length:.0f}",
        )
        self._draw_dim_h(painter, x0, face_end, y0 + top_h, 160.0, f"{dims.top_total_length:.0f}")
        self._draw_dim_h(painter, x0, intermediate_start, y0 + top_h, 86.0, f"{intermediate_start - x0:.0f}")
        self._draw_dim_h(painter, face_start, fin_start, y0 + top_h, 48.0, f"{dims.left_panel_width:.0f}")
        self._draw_dim_h(painter, fin_end, face_end, y0 + top_h, 48.0, f"{dims.right_panel_width:.0f}")

        self._draw_dim_v(painter, left_gap_top_y, left_gap_bottom_y, fin_start, -48.0, f"{top_h:.0f}")
        self._draw_dim_v(painter, y0, y0 + top_h, face_end, 50.0, f"{top_h:.0f}")
        self._draw_dim_v(
            painter,
            y0,
            y0 + dims.right_cap_thickness,
            face_end,
            89.0,
            f"{dims.right_cap_thickness:.0f}",
            arrows_inside=True,
            arrow_size=4.8,
        )
        self._draw_dim_v(painter, cap_top_y, tube_ys[0], fin_end, 40.0, f"{dims.top_small_offset_1:.1f}")
        self._draw_dim_v(
            painter,
            tube_ys[-1],
            cap_bottom_y,
            fin_end,
            40.0,
            f"{dims.top_small_offset_2:.1f}",
        )

        painter.setPen(object_pen)
        self._draw_underlined_label(painter, QRectF(x0, y0 + top_h + 182.0, dims.top_total_length, 30.0), "TOP")

    def _draw_front_view(self, painter: QPainter, layout: dict[str, float]) -> None:
        dims = self._dims
        x = layout["front_x"]
        y = layout["front_y"]
        face_w = dims.front_total_width
        left_extension = max(0.0, dims.front_header_band_width - dims.left_panel_width)
        total_w = left_extension + face_w
        h = dims.front_total_height
        face_left = x + left_extension
        face_right = face_left + face_w

        inner_x = x + dims.front_header_band_width
        inner_y = y + dims.top_plate
        inner_right_x = face_right - dims.right_panel_width
        inner_w = max(20.0, inner_right_x - inner_x)
        inner_h = dims.fin_height

        object_pen = QPen(self.OBJECT_COLOR, self.OBJECT_LINE_WIDTH)
        painter.setPen(object_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        painter.drawRect(QRectF(x, y, total_w, h))
        inner_bottom_y = inner_y + inner_h

        painter.drawLine(QPointF(face_left, y), QPointF(face_left, y + h))
        painter.drawLine(QPointF(inner_x, y), QPointF(inner_x, y + h))
        painter.drawLine(QPointF(inner_right_x, y), QPointF(inner_right_x, y + h))
        painter.drawLine(QPointF(inner_x, inner_y), QPointF(inner_right_x, inner_y))
        painter.drawLine(QPointF(inner_x, inner_bottom_y), QPointF(inner_right_x, inner_bottom_y))

        center_x = inner_x + (inner_w * 0.52)
        center_y = inner_y + (inner_h * 0.58)
        ellipse_w = 190.0
        ellipse_h = 90.0
        ellipse_rotation = 35.0

        ellipse_base = QPainterPath()
        ellipse_base.addEllipse(QRectF(-(ellipse_w / 2.0), -(ellipse_h / 2.0), ellipse_w, ellipse_h))
        transform = QTransform()
        transform.translate(center_x, center_y)
        transform.rotate(ellipse_rotation)
        ellipse_path = transform.map(ellipse_base)

        painter.save()
        painter.setPen(QPen(self.OBJECT_COLOR, 1.8))
        painter.drawPath(ellipse_path)

        painter.setClipPath(ellipse_path)
        painter.setPen(QPen(self.ACCENT_GREEN, 1.5))
        hatch_count = 8
        hatch_span = ellipse_w * 0.74
        hatch_start_x = center_x - (hatch_span / 2.0)
        hatch_step = hatch_span / max(1, hatch_count - 1)
        for hatch_index in range(hatch_count):
            hatch_x = hatch_start_x + (hatch_index * hatch_step)
            painter.drawLine(
                QPointF(hatch_x, center_y - (ellipse_h * 0.95)),
                QPointF(hatch_x, center_y + (ellipse_h * 0.95)),
            )
        painter.restore()

        painter.setPen(object_pen)
        text_x = center_x + 18.0
        text_y = center_y - 98.0
        painter.drawText(
            QRectF(text_x - 70.0, text_y - 18.0, 140.0, 35.0),
            Qt.AlignmentFlag.AlignCenter,
            f"{dims.fpi:.0f} FPI",
        )

        leader_tip = QPointF(center_x + 28.0, center_y - 16.0)
        leader_start = QPointF(text_x + 2.0, text_y + 18.0)
        painter.save()
        painter.setPen(QPen(self.DIM_COLOR, self.DIM_LINE_WIDTH))
        painter.drawLine(leader_start, leader_tip)
        self._draw_arrow_head(painter, leader_tip, (leader_tip.x() - leader_start.x(), leader_tip.y() - leader_start.y()), 6.2)
        painter.restore()

        self._draw_internal_dim_h(
            painter,
            x,
            inner_x,
            y + 185.0,
            f"{dims.front_header_band_width:.0f}",
        )
        self._draw_dim_h(painter, face_left, inner_x, y + h, 45.0, f"{dims.left_panel_width:.0f}")
        self._draw_dim_h(painter, inner_x, inner_x + inner_w, y + h, 45.0, f"{inner_w:.0f} (FL)")
        self._draw_dim_h(painter, inner_x + inner_w, face_right, y + h, 45.0, f"{dims.right_panel_width:.0f}")
        self._draw_dim_h(painter, face_left, face_right, y + h, 82.0, f"{face_w:.0f}")

        self._draw_dim_v(
            painter,
            inner_y,
            inner_y + inner_h,
            face_right,
            50.0,
            f"{inner_h:.0f} (FH)",
            text_vertical=True,
        )
        self._draw_dim_v(painter, y, y + h, face_right, 90.0, f"{h:.0f}", text_vertical=True)
        self._draw_dim_v(
            painter,
            y,
            y + dims.top_plate,
            face_right,
            129.0,
            f"{dims.top_plate:.0f}",
            text_vertical=True,
        )
        self._draw_dim_v(
            painter,
            y + h - dims.bottom_plate,
            y + h,
            face_right,
            129.0,
            f"{dims.bottom_plate:.0f}",
            text_vertical=True,
        )

        painter.setPen(object_pen)
        self._draw_underlined_label(painter, QRectF(face_left, y + h + 120.0, face_w, 30.0), "FRONT")

    def _draw_side_view(
        self,
        painter: QPainter,
        x: float,
        y: float,
        label: str,
        show_vertical_dims: bool,
        mirror: bool = False,
    ) -> None:
        dims = self._dims
        w = dims.core_width
        h = dims.front_total_height

        def map_x(local_x: float) -> float:
            return x + (w - local_x if mirror else local_x)

        object_pen = QPen(self.OBJECT_COLOR, self.OBJECT_LINE_WIDTH)
        painter.setPen(object_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(x, y, w, h))

        magenta_pen = QPen(self.MAGENTA, 1.1)
        magenta_pen.setStyle(Qt.PenStyle.DashLine)
        magenta_pen.setDashPattern([8.0, 5.0])
        painter.setPen(magenta_pen)
        band_margin_x = 8.0
        band_offset_y = 7.0
        painter.drawLine(
            QPointF(map_x(band_margin_x), y + band_offset_y),
            QPointF(map_x(w - band_margin_x), y + band_offset_y),
        )
        painter.drawLine(
            QPointF(map_x(band_margin_x), y + h - band_offset_y),
            QPointF(map_x(w - band_margin_x), y + h - band_offset_y),
        )

        painter.setPen(QPen(self.OBJECT_COLOR, 1.2))
        frame_hole_radius = 2.9
        base_frame_holes = [8.0, 44.0, 98.0, 160.0, 222.0, 276.0, 312.0]
        frame_hole_positions = [(value / 320.0) * w for value in base_frame_holes]
        for hole_x in frame_hole_positions:
            painter.drawEllipse(QPointF(map_x(hole_x), y + 8.0), frame_hole_radius, frame_hole_radius)
            painter.drawEllipse(QPointF(map_x(hole_x), y + h - 8.0), frame_hole_radius, frame_hole_radius)

        rows_in_width = max(1, int(round(dims.number_of_rows)))
        tubes_per_row = max(1, int(round(dims.tubes_per_row)))

        requested_horizontal_pitch = max(5.0, dims.pitch_horizontal)
        requested_vertical_pitch = max(5.0, dims.pitch_vertical)

        available_w = max(20.0, w - 28.0)
        available_h = max(60.0, h - 28.0)
        horizontal_pitch = min(requested_horizontal_pitch, available_w / max(1, rows_in_width))
        vertical_pitch = min(requested_vertical_pitch, available_h / max(1.0, tubes_per_row - 0.25))

        matrix_w = rows_in_width * horizontal_pitch
        matrix_h = (tubes_per_row - 0.25) * vertical_pitch

        hole_box_left = max(14.0, (w - matrix_w) / 2.0)
        hole_box_top = max(14.0, (h - matrix_h) / 2.0)

        effective_dia_limit = min(horizontal_pitch, vertical_pitch) * 0.86
        hole_diameter = max(2.0, min(dims.circle_diameter, effective_dia_limit))
        hole_radius = hole_diameter / 2.0

        # First center from top-left of hole matrix => (HP/2, VP/4).
        first_center_x = hole_box_left + (horizontal_pitch * 0.5)
        first_center_y = hole_box_top + (vertical_pitch * 0.25)

        for row_index in range(rows_in_width):
            row_center_x = first_center_x + (row_index * horizontal_pitch)

            # Steps-6/7: alternate row starts by +VP/2 then -VP/2.
            if row_index % 2 == 0:
                row_start_y = first_center_y
            else:
                row_start_y = first_center_y + (vertical_pitch * 0.5)

            for tube_index in range(tubes_per_row):
                hole_y = row_start_y + (tube_index * vertical_pitch)
                if hole_y > (hole_box_top + matrix_h + 0.001):
                    continue
                painter.drawEllipse(QPointF(map_x(row_center_x), y + hole_y), hole_radius, hole_radius)

        self._draw_dim_h(painter, x, x + w, y + h, 45.0, f"{w:.0f}")

        if show_vertical_dims:
            inner_y = y + dims.top_plate
            inner_h = dims.fin_height
            self._draw_dim_v(painter, inner_y, inner_y + inner_h, x + w, 49.0, f"{inner_h:.0f} (FH)")
            self._draw_dim_v(painter, y, y + h, x + w, 89.0, f"{h:.0f}")
            self._draw_dim_v(painter, y, y + dims.top_plate, x + w, 127.0, f"{dims.top_plate:.0f}")
            self._draw_dim_v(
                painter,
                y + h - dims.bottom_plate,
                y + h,
                x + w,
                127.0,
                f"{dims.bottom_plate:.0f}",
            )

        painter.setPen(object_pen)
        painter.drawText(QRectF(x, y + h + 79.0, w, 30.0), Qt.AlignmentFlag.AlignCenter, label)

    def _draw_underlined_label(self, painter: QPainter, rect: QRectF, text: str) -> None:
        painter.save()
        painter.setPen(QPen(self.OBJECT_COLOR, self.OBJECT_LINE_WIDTH))
        painter.setFont(QFont("Arial", 13))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        line_w = min(rect.width() * 0.22, 80.0)
        line_y = rect.y() + rect.height() - 3.0
        center_x = rect.x() + (rect.width() / 2.0)
        painter.drawLine(QPointF(center_x - (line_w / 2.0), line_y), QPointF(center_x + (line_w / 2.0), line_y))
        painter.restore()

    def _draw_internal_dim_h(
        self,
        painter: QPainter,
        x1: float,
        x2: float,
        y: float,
        label: str,
    ) -> None:
        x_left = min(x1, x2)
        x_right = max(x1, x2)

        painter.save()
        painter.setPen(QPen(self.DIM_COLOR, self.DIM_LINE_WIDTH))
        painter.setFont(QFont("Arial", 10))
        painter.drawLine(QPointF(x_left, y), QPointF(x_right, y))
        self._draw_arrow_head(painter, QPointF(x_left, y), (1.0, 0.0), 6.8)
        self._draw_arrow_head(painter, QPointF(x_right, y), (-1.0, 0.0), 6.8)
        painter.drawText(
            QRectF(x_left, y - 22.0, max(10.0, x_right - x_left), 18.0),
            Qt.AlignmentFlag.AlignCenter,
            label,
        )
        painter.restore()

    def _draw_dim_h(
        self,
        painter: QPainter,
        x1: float,
        x2: float,
        y_ref: float,
        offset: float,
        label: str,
    ) -> None:
        x_left = min(x1, x2)
        x_right = max(x1, x2)
        y = y_ref + offset

        painter.save()
        painter.setPen(QPen(self.DIM_COLOR, self.DIM_LINE_WIDTH))
        painter.setFont(QFont("Arial", 10))

        painter.drawLine(QPointF(x_left, y_ref), QPointF(x_left, y))
        painter.drawLine(QPointF(x_right, y_ref), QPointF(x_right, y))
        painter.drawLine(QPointF(x_left, y), QPointF(x_right, y))

        self._draw_arrow_head(painter, QPointF(x_left, y), (1.0, 0.0))
        self._draw_arrow_head(painter, QPointF(x_right, y), (-1.0, 0.0))

        text_y = y - 21.0 if offset < 0 else y + 4.0
        painter.drawText(
            QRectF(x_left, text_y, max(10.0, x_right - x_left), 18.0),
            Qt.AlignmentFlag.AlignCenter,
            label,
        )
        painter.restore()

    def _draw_dim_v(
        self,
        painter: QPainter,
        y1: float,
        y2: float,
        x_ref: float,
        offset: float,
        label: str,
        arrows_inside: bool = True,
        arrow_size: float | None = None,
        text_vertical: bool = False,
    ) -> None:
        y_top = min(y1, y2)
        y_bottom = max(y1, y2)
        x = x_ref + offset

        painter.save()
        painter.setPen(QPen(self.DIM_COLOR, self.DIM_LINE_WIDTH))
        painter.setFont(QFont("Arial", 10))

        painter.drawLine(QPointF(x_ref, y_top), QPointF(x, y_top))
        painter.drawLine(QPointF(x_ref, y_bottom), QPointF(x, y_bottom))
        painter.drawLine(QPointF(x, y_top), QPointF(x, y_bottom))

        span = max(0.1, y_bottom - y_top)
        size = 7.5 if arrow_size is None else arrow_size
        if arrows_inside and span < (size * 2.2):
            size = max(2.8, span * 0.35)

        if arrows_inside:
            top_direction = (0.0, 1.0)
            bottom_direction = (0.0, -1.0)
        else:
            top_direction = (0.0, -1.0)
            bottom_direction = (0.0, 1.0)

        self._draw_arrow_head(painter, QPointF(x, y_top), top_direction, size)
        self._draw_arrow_head(painter, QPointF(x, y_bottom), bottom_direction, size)

        if text_vertical:
            text_x = x + (12.0 if offset >= 0 else -12.0)
            text_y = (y_top + y_bottom) / 2.0
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

    def _draw_arrow_head(
        self,
        painter: QPainter,
        tip: QPointF,
        direction: tuple[float, float],
        size: float = 7.5,
    ) -> None:
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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Coil Helvix - Offline Qt Designer")
        self.resize(1580, 940)

        self.default_dims = CoilDimensions()
        self._spin_boxes: dict[str, QDoubleSpinBox] = {}
        self._direct_spin_boxes: dict[str, QDoubleSpinBox] = {}
        self._connection_side_combo: QComboBox | None = None
        self._is_syncing_inputs = False
        self._is_syncing_direct_inputs = False

        self.drawing_widget = CoilDrawingWidget(self.default_dims)
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
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(10)

        content_layout.addWidget(self._build_top_group())
        content_layout.addWidget(self._build_front_group())
        content_layout.addWidget(self._build_side_group())
        content_layout.addWidget(self._build_spec_group())
        content_layout.addWidget(self._build_direct_group())
        content_layout.addWidget(self._build_derived_group())
        content_layout.addLayout(self._build_buttons_row())
        content_layout.addLayout(self._build_zoom_row())
        content_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.setMinimumWidth(330)
        return scroll

    def _build_top_group(self) -> QGroupBox:
        group = QGroupBox("Top View Dimensions")
        form = QFormLayout(group)

        self._add_spin(form, "top_total_length", "Top Total Length", self.default_dims.top_total_length, 500, 6000)
        self._add_spin(
            form,
            "top_intermediate_length",
            "Top Intermediate Length",
            self.default_dims.top_intermediate_length,
            100,
            6000,
        )
        self._add_spin(form, "left_pipe_offset", "Header Extension", self.default_dims.left_pipe_offset, 0, 2000)
        self._add_spin(form, "left_pipe_length", "Stub Length", self.default_dims.left_pipe_length, 10, 3000)
        self._add_spin(form, "nozzle_projection", "Nozzle Projection", self.default_dims.nozzle_projection, 10, 500)
        self._add_spin(form, "header_box_height", "Header Box Height", self.default_dims.header_box_height, 40, 2000)
        self._add_spin(
            form,
            "right_cap_thickness",
            "Header Flange First Bend",
            self.default_dims.right_cap_thickness,
            2,
            400,
        )
        self._add_spin(form, "top_small_offset_1", "Top Small Offset 1", self.default_dims.top_small_offset_1, 5, 500)
        self._add_spin(form, "top_small_offset_2", "Top Small Offset 2", self.default_dims.top_small_offset_2, 5, 500)
        return group

    def _build_front_group(self) -> QGroupBox:
        group = QGroupBox("Front View Dimensions")
        form = QFormLayout(group)

        self._add_spin(form, "front_total_width", "Front Total Width", self.default_dims.front_total_width, 200, 6000)
        self._add_spin(form, "front_total_height", "Front Total Height", self.default_dims.front_total_height, 200, 6000)
        self._add_spin(form, "left_panel_width", "Header Side Flange", self.default_dims.left_panel_width, 5, 2000)
        self._add_spin(form, "right_panel_width", "Return Side Flange", self.default_dims.right_panel_width, 5, 2000)
        self._add_spin(form, "top_plate", "Top Plate", self.default_dims.top_plate, 5, 1000)
        self._add_spin(form, "bottom_plate", "Bottom Plate", self.default_dims.bottom_plate, 5, 1000)
        self._add_spin(
            form,
            "front_header_band_width",
            "Blank Off Width",
            self.default_dims.front_header_band_width,
            20,
            3000,
        )
        self._add_spin(form, "fpi", "FPI", self.default_dims.fpi, 1, 60, decimals=0)
        return group

    def _build_side_group(self) -> QGroupBox:
        group = QGroupBox("Side View Dimensions")
        form = QFormLayout(group)
        self._add_spin(form, "core_width", "Side Width / Top Height", self.default_dims.core_width, 60, 3000)
        return group

    def _build_spec_group(self) -> QGroupBox:
        group = QGroupBox("Tube & Circuit Specs")
        form = QFormLayout(group)

        self._add_spin(form, "tube_dia_inch", "Tube Dia (inch)", self.default_dims.tube_dia_inch, 0.1, 2.0, decimals=3)
        self._add_spin(form, "pitch_vertical", "Vertical Pitch", self.default_dims.pitch_vertical, 5.0, 120.0)
        self._add_spin(form, "pitch_horizontal", "Horizontal Pitch", self.default_dims.pitch_horizontal, 5.0, 120.0)

        connection_combo = QComboBox()
        connection_combo.addItems(["LHS", "RHS"])
        connection_combo.setCurrentText(self.default_dims.connection_side)
        connection_combo.currentTextChanged.connect(self._apply_changes)
        self._connection_side_combo = connection_combo
        form.addRow("Connection", connection_combo)

        self._add_spin(form, "circle_diameter", "Circle Diameter", self.default_dims.circle_diameter, 2.0, 40.0, decimals=2)
        self._add_spin(form, "tubes_per_row", "Tubes per row (TPR)", self.default_dims.tubes_per_row, 1.0, 300.0, decimals=0)
        self._add_spin(form, "number_of_rows", "No. of Rows", self.default_dims.number_of_rows, 1.0, 40.0, decimals=0)
        self._add_spin(
            form,
            "number_of_circuits",
            "No. of Circuits",
            self.default_dims.number_of_circuits,
            1.0,
            100.0,
            decimals=0,
        )
        self._add_spin(form, "header_dia", "Header Dia", self.default_dims.header_dia, 20.0, 500.0)
        self._add_spin(form, "blank_off_bend", "Blank Off Bend", self.default_dims.blank_off_bend, 0.0, 200.0)
        return group

    def _build_derived_group(self) -> QGroupBox:
        group = QGroupBox("Derived")
        form = QFormLayout(group)
        form.addRow("Fin Length (FL)", self._fl_label)
        form.addRow("Fin Height (FH)", self._fh_label)
        return group

    def _build_direct_group(self) -> QGroupBox:
        group = QGroupBox("Direct Dimension Edit")
        form = QFormLayout(group)
        self._add_direct_spin(
            form,
            "top_lead_span",
            "Top Lead Span",
            self.default_dims.top_lead_span,
            20.0,
            6000.0,
        )
        self._add_direct_spin(
            form,
            "fin_length_direct",
            "Fin Length (FL)",
            self.default_dims.fin_length,
            20.0,
            6000.0,
        )
        self._add_direct_spin(
            form,
            "fin_height_direct",
            "Fin Height (FH)",
            self.default_dims.fin_height,
            20.0,
            6000.0,
        )
        return group

    def _build_buttons_row(self) -> QHBoxLayout:
        layout = QHBoxLayout()

        apply_button = QPushButton("Apply")
        reset_button = QPushButton("Reset")
        print_button = QPushButton("Print")
        export_button = QPushButton("Export PNG")
        import_dxf_button = QPushButton("Import DFX/DXF")
        export_dxf_button = QPushButton("Export DXF")

        apply_button.clicked.connect(self._apply_changes)
        reset_button.clicked.connect(self._reset_defaults)
        print_button.clicked.connect(self._print_drawing)
        export_button.clicked.connect(self._export_png)
        import_dxf_button.clicked.connect(self._import_dxf)
        export_dxf_button.clicked.connect(self._export_dxf)

        layout.addWidget(apply_button)
        layout.addWidget(reset_button)
        layout.addWidget(print_button)
        layout.addWidget(export_button)
        layout.addWidget(import_dxf_button)
        layout.addWidget(export_dxf_button)
        return layout

    def _build_zoom_row(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        zoom_out_button = QPushButton("Zoom -")
        zoom_in_button = QPushButton("Zoom +")
        zoom_reset_button = QPushButton("Reset View")

        zoom_out_button.clicked.connect(self._zoom_out)
        zoom_in_button.clicked.connect(self._zoom_in)
        zoom_reset_button.clicked.connect(self._zoom_reset)

        self._zoom_label.setMinimumWidth(55)
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(zoom_out_button)
        layout.addWidget(zoom_in_button)
        layout.addWidget(zoom_reset_button)
        layout.addWidget(self._zoom_label)
        return layout

    def _add_spin(
        self,
        form: QFormLayout,
        key: str,
        label: str,
        default_value: float,
        minimum: float,
        maximum: float,
        decimals: int = 1,
    ) -> None:
        spin = QDoubleSpinBox()
        spin.setDecimals(decimals)
        spin.setRange(minimum, maximum)
        spin.setValue(default_value)
        spin.setSingleStep(1.0)
        spin.setKeyboardTracking(False)
        spin.valueChanged.connect(self._apply_changes)
        self._spin_boxes[key] = spin
        form.addRow(label, spin)

    def _add_direct_spin(
        self,
        form: QFormLayout,
        key: str,
        label: str,
        default_value: float,
        minimum: float,
        maximum: float,
        decimals: int = 1,
    ) -> None:
        spin = QDoubleSpinBox()
        spin.setDecimals(decimals)
        spin.setRange(minimum, maximum)
        spin.setValue(default_value)
        spin.setSingleStep(1.0)
        spin.setKeyboardTracking(False)
        spin.valueChanged.connect(self._apply_direct_changes)
        self._direct_spin_boxes[key] = spin
        form.addRow(label, spin)

    def _collect_dimensions(self) -> CoilDimensions:
        connection_side = self.default_dims.connection_side
        if self._connection_side_combo is not None:
            connection_side = self._connection_side_combo.currentText()

        top_plate_value = self._spin_boxes["top_plate"].value()
        bottom_plate_value = self._spin_boxes["bottom_plate"].value()

        return CoilDimensions(
            top_total_length=self._spin_boxes["top_total_length"].value(),
            top_intermediate_length=self._spin_boxes["top_intermediate_length"].value(),
            front_total_width=self._spin_boxes["front_total_width"].value(),
            front_total_height=self._spin_boxes["front_total_height"].value(),
            left_panel_width=self._spin_boxes["left_panel_width"].value(),
            right_panel_width=self._spin_boxes["right_panel_width"].value(),
            top_bottom_margin=(top_plate_value + bottom_plate_value) / 2.0,
            top_plate=top_plate_value,
            bottom_plate=bottom_plate_value,
            core_width=self._spin_boxes["core_width"].value(),
            left_pipe_offset=self._spin_boxes["left_pipe_offset"].value(),
            left_pipe_length=self._spin_boxes["left_pipe_length"].value(),
            nozzle_projection=self._spin_boxes["nozzle_projection"].value(),
            header_box_height=self._spin_boxes["header_box_height"].value(),
            right_cap_thickness=self._spin_boxes["right_cap_thickness"].value(),
            front_header_band_width=self._spin_boxes["front_header_band_width"].value(),
            top_small_offset_1=self._spin_boxes["top_small_offset_1"].value(),
            top_small_offset_2=self._spin_boxes["top_small_offset_2"].value(),
            fpi=self._spin_boxes["fpi"].value(),
            tube_dia_inch=self._spin_boxes["tube_dia_inch"].value(),
            pitch_vertical=self._spin_boxes["pitch_vertical"].value(),
            pitch_horizontal=self._spin_boxes["pitch_horizontal"].value(),
            connection_side=connection_side,
            circle_diameter=self._spin_boxes["circle_diameter"].value(),
            tubes_per_row=self._spin_boxes["tubes_per_row"].value(),
            number_of_rows=self._spin_boxes["number_of_rows"].value(),
            number_of_circuits=self._spin_boxes["number_of_circuits"].value(),
            header_dia=self._spin_boxes["header_dia"].value(),
            blank_off_bend=self._spin_boxes["blank_off_bend"].value(),
        )

    def _apply_changes(self) -> None:
        if self._is_syncing_inputs:
            return

        dims = self._collect_dimensions().sanitized()
        self._sync_spin_values(dims)
        self._sync_connection_side(dims)
        self._sync_direct_spin_values(dims)
        self._fl_label.setText(f"{dims.fin_length:.1f}")
        self._fh_label.setText(f"{dims.fin_height:.1f}")
        self.drawing_widget.set_dimensions(dims)
        self._refresh_zoom_label()

    def _apply_direct_changes(self) -> None:
        if self._is_syncing_direct_inputs or self._is_syncing_inputs:
            return

        dims = self._collect_dimensions().sanitized()
        lead_span = self._direct_spin_boxes["top_lead_span"].value()
        fin_length = self._direct_spin_boxes["fin_length_direct"].value()
        fin_height = self._direct_spin_boxes["fin_height_direct"].value()

        dims.top_total_length = lead_span + dims.front_total_width - dims.left_panel_width
        dims.right_panel_width = dims.front_total_width - dims.left_panel_width - fin_length
        total_plate_span = max(10.0, dims.front_total_height - fin_height)
        previous_total = max(0.001, dims.top_plate + dims.bottom_plate)
        top_ratio = dims.top_plate / previous_total
        top_ratio = max(0.0, min(top_ratio, 1.0))
        dims.top_plate = total_plate_span * top_ratio
        dims.bottom_plate = total_plate_span - dims.top_plate
        dims.top_bottom_margin = (dims.top_plate + dims.bottom_plate) / 2.0
        dims = dims.sanitized()

        self._sync_spin_values(dims)
        self._apply_changes()

    def _sync_spin_values(self, dims: CoilDimensions) -> None:
        values = {
            "top_total_length": dims.top_total_length,
            "top_intermediate_length": dims.top_intermediate_length,
            "front_total_width": dims.front_total_width,
            "front_total_height": dims.front_total_height,
            "left_panel_width": dims.left_panel_width,
            "right_panel_width": dims.right_panel_width,
            "top_plate": dims.top_plate,
            "bottom_plate": dims.bottom_plate,
            "core_width": dims.core_width,
            "left_pipe_offset": dims.left_pipe_offset,
            "left_pipe_length": dims.left_pipe_length,
            "nozzle_projection": dims.nozzle_projection,
            "header_box_height": dims.header_box_height,
            "right_cap_thickness": dims.right_cap_thickness,
            "front_header_band_width": dims.front_header_band_width,
            "top_small_offset_1": dims.top_small_offset_1,
            "top_small_offset_2": dims.top_small_offset_2,
            "fpi": dims.fpi,
            "tube_dia_inch": dims.tube_dia_inch,
            "pitch_vertical": dims.pitch_vertical,
            "pitch_horizontal": dims.pitch_horizontal,
            "circle_diameter": dims.circle_diameter,
            "tubes_per_row": dims.tubes_per_row,
            "number_of_rows": dims.number_of_rows,
            "number_of_circuits": dims.number_of_circuits,
            "header_dia": dims.header_dia,
            "blank_off_bend": dims.blank_off_bend,
        }

        self._is_syncing_inputs = True
        try:
            for key, value in values.items():
                spin = self._spin_boxes.get(key)
                if spin is None:
                    continue
                if abs(spin.value() - value) < 1e-6:
                    continue
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)
        finally:
            self._is_syncing_inputs = False

    def _sync_connection_side(self, dims: CoilDimensions) -> None:
        if self._connection_side_combo is None:
            return

        current_text = self._connection_side_combo.currentText().strip().upper()
        next_text = dims.connection_side.strip().upper()
        if current_text == next_text:
            return

        self._connection_side_combo.blockSignals(True)
        self._connection_side_combo.setCurrentText(next_text)
        self._connection_side_combo.blockSignals(False)

    def _sync_direct_spin_values(self, dims: CoilDimensions) -> None:
        values = {
            "top_lead_span": dims.top_lead_span,
            "fin_length_direct": dims.fin_length,
            "fin_height_direct": dims.fin_height,
        }

        self._is_syncing_direct_inputs = True
        try:
            for key, value in values.items():
                spin = self._direct_spin_boxes.get(key)
                if spin is None:
                    continue
                if abs(spin.value() - value) < 1e-6:
                    continue
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)
        finally:
            self._is_syncing_direct_inputs = False

    def _reset_defaults(self) -> None:
        default_values = self.default_dims.sanitized()
        self._sync_spin_values(default_values)
        self._sync_connection_side(default_values)
        self._apply_changes()

    def _zoom_in(self) -> None:
        self.drawing_widget.zoom_by(1.15)
        self._refresh_zoom_label()

    def _zoom_out(self) -> None:
        self.drawing_widget.zoom_by(1.0 / 1.15)
        self._refresh_zoom_label()

    def _zoom_reset(self) -> None:
        self.drawing_widget.reset_view()
        self._refresh_zoom_label()

    def _refresh_zoom_label(self) -> None:
        self._zoom_label.setText(f"{self.drawing_widget.zoom_percent()}%")

    def _print_drawing(self) -> None:
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        painter = QPainter(printer)
        target = QRectF(painter.viewport())
        self.drawing_widget.render_to_painter(painter, target, QColor("white"))
        painter.end()

    def _export_png(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Coil Drawing",
            "coil_drawing.png",
            "PNG Image (*.png)",
        )
        if not file_path:
            return

        if not file_path.lower().endswith(".png"):
            file_path += ".png"

        image = QImage(2800, 1800, QImage.Format.Format_ARGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        self.drawing_widget.render_to_painter(
            painter,
            QRectF(0.0, 0.0, float(image.width()), float(image.height())),
            QColor("white"),
        )
        painter.end()

        if not image.save(file_path):
            QMessageBox.warning(self, "Export Failed", "Could not save the PNG file.")

    def _import_dxf(self) -> None:
        if ezdxf is None:
            QMessageBox.information(
                self,
                "Import DFX/DXF",
                "DFX/DXF import needs the 'ezdxf' package.\nInstall with: pip install ezdxf",
            )
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Coil Drawing from DFX/DXF",
            "",
            "CAD DXF/DFX (*.dxf *.dfx)",
        )
        if not file_path:
            return

        try:
            imported_dims = self._extract_dimensions_from_dxf(file_path)
            if imported_dims is None:
                QMessageBox.warning(
                    self,
                    "Import Failed",
                    "Could not find compatible dimensions data in this file.",
                )
                return

            self._sync_spin_values(imported_dims)
            self._sync_connection_side(imported_dims)
            self._apply_changes()
            QMessageBox.information(self, "Import Successful", "Dimensions imported successfully from DFX/DXF.")
        except Exception as error:
            QMessageBox.warning(self, "Import Failed", f"Could not import DFX/DXF.\n{error}")

    def _extract_dimensions_from_dxf(self, file_path: str) -> CoilDimensions | None:
        doc = ezdxf.readfile(file_path)

        metadata_dims = self._extract_dimensions_from_metadata(doc)
        if metadata_dims is not None:
            return metadata_dims

        return self._extract_dimensions_from_labels(doc)

    def _extract_dimensions_from_metadata(self, doc) -> CoilDimensions | None:
        metadata_layer = DxfPainterAdapter.METADATA_LAYER.upper()
        metadata_prefix = DxfPainterAdapter.METADATA_PREFIX

        for entity in doc.modelspace():
            entity_type = entity.dxftype()
            if entity_type not in {"TEXT", "MTEXT"}:
                continue

            layer_name = str(getattr(entity.dxf, "layer", "")).upper()
            if layer_name != metadata_layer:
                continue

            if entity_type == "TEXT":
                raw_text = str(getattr(entity.dxf, "text", ""))
            else:
                if hasattr(entity, "plain_text"):
                    raw_text = str(entity.plain_text())
                else:
                    raw_text = str(getattr(entity, "text", ""))

            raw_text = raw_text.strip()
            if not raw_text.startswith(metadata_prefix):
                continue

            payload = json.loads(raw_text[len(metadata_prefix) :])
            if not isinstance(payload, dict):
                continue
            return self._build_dimensions_from_payload(payload)

        return None

    def _extract_dimensions_from_labels(self, doc) -> CoilDimensions | None:
        defaults = CoilDimensions()
        plain_values: list[float] = []
        all_values: list[float] = []
        fin_length_tag: float | None = None
        fin_height_tag: float | None = None
        fpi_tag: float | None = None
        connection_side_hint: str | None = None

        for entity in doc.modelspace():
            entity_type = entity.dxftype()
            if entity_type not in {"TEXT", "MTEXT"}:
                continue

            if entity_type == "TEXT":
                raw_text = str(getattr(entity.dxf, "text", ""))
            else:
                if hasattr(entity, "plain_text"):
                    raw_text = str(entity.plain_text())
                else:
                    raw_text = str(getattr(entity, "text", ""))

            text = raw_text.strip()
            if not text:
                continue
            if text.startswith(DxfPainterAdapter.METADATA_PREFIX):
                continue

            first_match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
            if first_match is None:
                continue

            number = float(first_match.group(0))
            all_values.append(number)

            upper_text = text.upper()
            if "FPI" in upper_text and fpi_tag is None:
                fpi_tag = number
            if "(FL)" in upper_text and fin_length_tag is None:
                fin_length_tag = number
            if "(FH)" in upper_text and fin_height_tag is None:
                fin_height_tag = number
            if "RHS" in upper_text:
                connection_side_hint = "RHS"
            elif "LHS" in upper_text:
                connection_side_hint = "LHS"

            if re.search(r"[A-Za-z]", text) is None:
                plain_values.append(number)

        if not all_values:
            return None

        used_indices: set[int] = set()

        def pick_nearest(target: float, minimum: float, maximum: float, consume: bool = True) -> float | None:
            best_index: int | None = None
            best_distance: float | None = None
            for index, value in enumerate(plain_values):
                if index in used_indices:
                    continue
                if value < minimum or value > maximum:
                    continue
                distance = abs(value - target)
                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    best_index = index

            if best_index is None:
                return None

            if consume:
                used_indices.add(best_index)
            return plain_values[best_index]

        fin_length = fin_length_tag if fin_length_tag is not None else defaults.fin_length
        fin_height = fin_height_tag if fin_height_tag is not None else defaults.fin_height
        fpi = fpi_tag if fpi_tag is not None else defaults.fpi

        left_panel_width = pick_nearest(defaults.left_panel_width, 5.0, 2000.0) or defaults.left_panel_width
        right_panel_width = pick_nearest(defaults.right_panel_width, 5.0, 2000.0) or defaults.right_panel_width

        front_total_width = pick_nearest(defaults.front_total_width, 300.0, 6000.0)
        if front_total_width is None:
            front_total_width = left_panel_width + right_panel_width + fin_length
        elif fin_length_tag is not None:
            expected_width = left_panel_width + right_panel_width + fin_length
            if abs(front_total_width - expected_width) > 5.0:
                front_total_width = expected_width

        top_total_length = pick_nearest(defaults.top_total_length, 500.0, 6000.0) or defaults.top_total_length
        top_intermediate_length = (
            pick_nearest(defaults.top_intermediate_length, 100.0, top_total_length) or defaults.top_intermediate_length
        )

        top_plate = pick_nearest(defaults.top_plate, 5.0, 1000.0) or defaults.top_plate
        bottom_plate = pick_nearest(defaults.bottom_plate, 5.0, 1000.0) or defaults.bottom_plate
        legacy_margin = pick_nearest(defaults.top_bottom_margin, 5.0, 1000.0, consume=False)
        if legacy_margin is not None:
            if abs(top_plate - defaults.top_plate) < 1e-6:
                top_plate = legacy_margin
            if abs(bottom_plate - defaults.bottom_plate) < 1e-6:
                bottom_plate = legacy_margin

        top_bottom_margin = (top_plate + bottom_plate) / 2.0
        front_total_height = pick_nearest(defaults.front_total_height, 300.0, 6000.0)
        if front_total_height is None:
            front_total_height = fin_height + top_plate + bottom_plate
        elif fin_height_tag is not None:
            expected_height = fin_height + top_plate + bottom_plate
            if abs(front_total_height - expected_height) > 5.0:
                front_total_height = expected_height

        core_width = pick_nearest(defaults.core_width, 60.0, 3000.0) or defaults.core_width
        left_pipe_offset = pick_nearest(defaults.left_pipe_offset, 0.0, 2000.0) or defaults.left_pipe_offset
        left_pipe_length = pick_nearest(defaults.left_pipe_length, 10.0, 3000.0) or defaults.left_pipe_length
        nozzle_projection = pick_nearest(defaults.nozzle_projection, 10.0, 500.0) or defaults.nozzle_projection

        header_box_candidate = pick_nearest(defaults.header_box_height, 40.0, 3000.0)
        if header_box_candidate is None or abs(header_box_candidate - defaults.header_box_height) > 60.0:
            header_box_height = core_width
        else:
            header_box_height = header_box_candidate

        right_cap_candidate = pick_nearest(defaults.right_cap_thickness, 2.0, 400.0)
        if right_cap_candidate is None or abs(right_cap_candidate - defaults.right_cap_thickness) > 20.0:
            right_cap_thickness = defaults.right_cap_thickness
        else:
            right_cap_thickness = right_cap_candidate

        front_header_band_width = (
            pick_nearest(defaults.front_header_band_width, 20.0, 3000.0) or defaults.front_header_band_width
        )

        top_small_offset_1 = pick_nearest(defaults.top_small_offset_1, 5.0, 500.0) or defaults.top_small_offset_1
        top_small_offset_2 = pick_nearest(defaults.top_small_offset_2, 5.0, 500.0) or top_small_offset_1

        tube_dia_inch = defaults.tube_dia_inch
        pitch_vertical = pick_nearest(defaults.pitch_vertical, 5.0, 120.0, consume=False) or defaults.pitch_vertical
        pitch_horizontal = pick_nearest(defaults.pitch_horizontal, 5.0, 120.0, consume=False) or defaults.pitch_horizontal
        connection_side = connection_side_hint or defaults.connection_side
        circle_diameter = pick_nearest(defaults.circle_diameter, 2.0, 40.0, consume=False) or defaults.circle_diameter
        tubes_per_row = pick_nearest(defaults.tubes_per_row, 1.0, 300.0, consume=False) or defaults.tubes_per_row
        number_of_rows = pick_nearest(defaults.number_of_rows, 1.0, 40.0, consume=False) or defaults.number_of_rows
        number_of_circuits = (
            pick_nearest(defaults.number_of_circuits, 1.0, 100.0, consume=False) or defaults.number_of_circuits
        )
        header_dia = pick_nearest(defaults.header_dia, 20.0, 500.0, consume=False) or defaults.header_dia
        blank_off_bend = pick_nearest(defaults.blank_off_bend, 0.0, 200.0, consume=False) or defaults.blank_off_bend

        reconstructed = CoilDimensions(
            top_total_length=top_total_length,
            top_intermediate_length=top_intermediate_length,
            front_total_width=front_total_width,
            front_total_height=front_total_height,
            left_panel_width=left_panel_width,
            right_panel_width=right_panel_width,
            top_bottom_margin=top_bottom_margin,
            top_plate=top_plate,
            bottom_plate=bottom_plate,
            core_width=core_width,
            left_pipe_offset=left_pipe_offset,
            left_pipe_length=left_pipe_length,
            nozzle_projection=nozzle_projection,
            header_box_height=header_box_height,
            right_cap_thickness=right_cap_thickness,
            front_header_band_width=front_header_band_width,
            top_small_offset_1=top_small_offset_1,
            top_small_offset_2=top_small_offset_2,
            fpi=fpi,
            tube_dia_inch=tube_dia_inch,
            pitch_vertical=pitch_vertical,
            pitch_horizontal=pitch_horizontal,
            connection_side=connection_side,
            circle_diameter=circle_diameter,
            tubes_per_row=tubes_per_row,
            number_of_rows=number_of_rows,
            number_of_circuits=number_of_circuits,
            header_dia=header_dia,
            blank_off_bend=blank_off_bend,
        ).sanitized()

        return reconstructed

    def _build_dimensions_from_payload(self, payload: dict) -> CoilDimensions:
        defaults = CoilDimensions()
        values: dict[str, object] = {}

        for field_info in fields(CoilDimensions):
            fallback = getattr(defaults, field_info.name)
            raw_value = payload.get(field_info.name, fallback)
            if isinstance(fallback, str):
                values[field_info.name] = str(raw_value)
                continue

            try:
                values[field_info.name] = float(raw_value)
            except (TypeError, ValueError):
                values[field_info.name] = fallback

        return CoilDimensions(**values).sanitized()

    def _export_dxf(self) -> None:
        if ezdxf is None:
            QMessageBox.information(
                self,
                "DXF Export",
                "DXF export needs the 'ezdxf' package.\nInstall with: pip install ezdxf",
            )
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Coil Drawing as DXF",
            "coil_drawing.dxf",
            "CAD DXF/DFX (*.dxf *.dfx)",
        )
        if not file_path:
            return

        lower = file_path.lower()
        if not lower.endswith(".dxf") and not lower.endswith(".dfx"):
            file_path += ".dxf"

        try:
            self.drawing_widget.export_to_dxf(file_path)
        except Exception as error:
            QMessageBox.warning(self, "Export Failed", f"Could not export DXF/DFX.\n{error}")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Coil Helvix Offline Designer")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

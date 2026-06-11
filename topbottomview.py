import math
import sys
import json
import os
import hmac
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dataclasses import dataclass, replace, fields

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPolygonF, QPainterPath
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
    return hmac.compare_digest(hashlib.sha256(entered.encode("utf-8")).hexdigest().lower(), expected)


def _enforce_startup_access() -> tuple[bool, str | None]:
    first_run = _load_or_create_first_run()
    expiry = _resolve_expiry_datetime(first_run)
    now = datetime.now(timezone.utc)
    if now <= expiry:
        return True, None  # Fixed logic: allow access if not expired
    password, ok = QInputDialog.getText(None, "Access Required", "Enter password:", QLineEdit.EchoMode.Password)
    if not ok or not _is_password_valid(password):
        return False, "Invalid password. Application will close."
    return True, None


@dataclass
class TopPlateDimensions:
    # Identity
    job_order_no: str = "252600912"
    coil_unique_id: str = "25001232"
    coil_type: str = "CHW"
    connection_side: str = "LHS"

    # Core inputs
    coil_width: float = 280.0          # mm
    top_plate: float = 15.0            # mm
    first_bend_top_plate: float = 12.0 # mm
    fin_length: float = 2200.0         # mm
    number_of_splits: float = 3.0      # integer splits
    sheet_metal_thickness: float = 1.5 # mm

    # ── Computed properties ──────────────────────────────────────────────────

    @property
    def total_width(self) -> float:
        """Width = Coil Width + 2 * ((top_plate + first_bend) - (4 * t))"""
        return self.coil_width + 2.0 * (
            (self.top_plate + self.first_bend_top_plate) - (4.0 * self.sheet_metal_thickness)
        )

    @property
    def total_height(self) -> float:
        """Height = (fin_length / splits - (splits-2)*t) + 2*top_plate - 4*t"""
        splits = max(1.0, self.number_of_splits)
        return (self.fin_length / splits - (splits - 2.0) * self.sheet_metal_thickness) + \
               2.0 * self.top_plate - 4.0 * self.sheet_metal_thickness

    @property
    def circle_x_offset(self) -> float:
        """Circle centre x from left edge = 20 + (top_plate - 2t) + (first_bend - 2t)"""
        return 20.0 + (self.top_plate - 2.0 * self.sheet_metal_thickness) + \
               (self.first_bend_top_plate - 2.0 * self.sheet_metal_thickness)

    @property
    def hole_pitch(self) -> float:
        """Pitch = (total_width - 2 * circle_x_offset) / 4"""
        return (self.total_width - 2.0 * self.circle_x_offset) / 4.0

    @property
    def corner_notch_height(self) -> float:
        """Height = top_plate - sheet_thickness"""
        return self.top_plate - self.sheet_metal_thickness

    @property
    def corner_notch_width(self) -> float:
        """Width = (top_plate + first_bend) - 3*t"""
        return (self.top_plate + self.first_bend_top_plate) - 3.0 * self.sheet_metal_thickness

    def sanitized(self) -> "TopPlateDimensions":
        v = replace(self)
        v.coil_width = max(80.0, v.coil_width)
        v.top_plate = max(5.0, v.top_plate)
        v.first_bend_top_plate = max(1.0, v.first_bend_top_plate)
        v.fin_length = max(100.0, v.fin_length)
        v.number_of_splits = max(1.0, min(v.number_of_splits, 20.0))
        v.sheet_metal_thickness = max(0.5, min(v.sheet_metal_thickness, 10.0))
        v.job_order_no = str(v.job_order_no).strip() or "252600912"
        v.coil_unique_id = str(v.coil_unique_id).strip() or "25001232"
        v.coil_type = str(v.coil_type).strip().upper() or "CHW"
        conn = str(v.connection_side).strip().upper()
        v.connection_side = conn if conn in {"LHS", "RHS"} else "LHS"
        return v


# ═══════════════════════════════════════════════════════════════════════════════
#  Top/Bottom Plate Drawing Widget
# ═══════════════════════════════════════════════════════════════════════════════
class DxfPainterAdapter:
    METADATA_LAYER = "COIL_META"
    METADATA_PREFIX = "COIL_HELVIX_DIMS:"

    def __init__(self, file_path: str, canvas_height: float) -> None:
        if ezdxf is None:
            raise RuntimeError("DXF export requires the 'ezdxf' package. Install with: pip install ezdxf")

        self._file_path = file_path
        self._canvas_height = canvas_height
        self._doc = ezdxf.new("R2010")
        self._doc.units = 4  # mm
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

    def write_dimensions_metadata(self, dims: TopPlateDimensions) -> None:
        payload: dict[str, object] = {}
        for field_info in fields(TopPlateDimensions):
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


class TopBottomPlateDrawingWidget(QWidget):
    BACKGROUND        = QColor("#f2f2f2")
    OBJECT_COLOR      = QColor("#111111")
    DIM_COLOR         = QColor("#ff6a00")
    NOTCH_COLOR       = QColor("#444444")
    OBJECT_LINE_WIDTH = 1.7
    DIM_LINE_WIDTH    = 1.05

    def __init__(self, dimensions: TopPlateDimensions | None = None) -> None:
        super().__init__()
        self._dims = (dimensions or TopPlateDimensions()).sanitized()
        self._zoom = 1.0
        self._min_zoom = 0.15
        self._max_zoom = 6.0
        self._pan_offset = QPointF(0.0, 0.0)
        self._is_panning = False
        self._last_pan_pos: QPointF | None = None
        self.setMinimumSize(700, 600)

    def set_dimensions(self, dimensions: TopPlateDimensions) -> None:
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
        self._draw_top_plate(painter, layout)
        self._draw_notes(painter, layout)
        painter.restore()

    def _calc_transform(self, target_rect, world_w, world_h, apply_view):
        margin = 40.0
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
        margin_left = 120.0
        margin_top  = 80.0
        w = dims.total_width
        h = dims.total_height
        world_w = margin_left + w + 300.0
        world_h = margin_top  + h + 320.0
        return {
            "tp_x":    margin_left,
            "tp_y":    margin_top,
            "tp_w":    w,
            "tp_h":    h,
            "world_w": world_w,
            "world_h": world_h,
        }

    # ── Top Plate drawing ─────────────────────────────────────────────────────

    def _draw_top_plate(self, painter: QPainter, layout: dict) -> None:
        dims = self._dims
        x = layout["tp_x"]
        y = layout["tp_y"]
        w = layout["tp_w"]
        h = layout["tp_h"]

        obj_pen = QPen(self.OBJECT_COLOR, self.OBJECT_LINE_WIDTH)

        # ── Step 1: Main outer rectangle ──────────────────────────────────────
        painter.setPen(obj_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(x, y, w, h))

        # ── Top plate band line ────────────────────────────────────────────────
        top_band_y    = y + dims.top_plate
        bottom_band_y = y + h - dims.top_plate
        painter.setPen(QPen(self.OBJECT_COLOR, 1.0))
        painter.drawLine(QPointF(x, top_band_y),    QPointF(x + w, top_band_y))
        painter.drawLine(QPointF(x, bottom_band_y), QPointF(x + w, bottom_band_y))

        # ── Steps 2 & 3: Small holes ø6 top band ─────────────────────────────
        hole_r   = 3.0
        cx_first = dims.circle_x_offset          # from left edge
        pitch    = dims.hole_pitch
        hole_y_top = y + dims.top_plate / 2.0
        hole_y_bot = y + h - dims.top_plate / 2.0

        hole_xs = [cx_first + i * pitch for i in range(5)]

        painter.setPen(obj_pen)
        for hx in hole_xs:
            painter.drawEllipse(QPointF(x + hx, hole_y_top), hole_r, hole_r)
            # Step 4: repeat on bottom
            painter.drawEllipse(QPointF(x + hx, hole_y_bot), hole_r, hole_r)

        # ── Step 5: Corner notch rectangles (filled dark) ─────────────────────
        nw = dims.corner_notch_width
        nh = dims.corner_notch_height
        notch_pen   = QPen(self.NOTCH_COLOR, self.OBJECT_LINE_WIDTH)
        notch_brush = QColor("#444444")

        painter.save()
        painter.setPen(notch_pen)
        painter.setBrush(notch_brush)
        # Top-left
        painter.drawRect(QRectF(x,         y,         nw, nh))
        # Top-right
        painter.drawRect(QRectF(x + w - nw, y,         nw, nh))
        # Bottom-left
        painter.drawRect(QRectF(x,          y + h - nh, nw, nh))
        # Bottom-right
        painter.drawRect(QRectF(x + w - nw,  y + h - nh, nw, nh))
        painter.restore()

        # Re-draw outer box on top
        painter.setPen(obj_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(x, y, w, h))

        # ── Dimensions ────────────────────────────────────────────────────────
        # Overall width (top)
        self._dim_h(painter, x, x + w, y, -45.0, f"{w:.1f}")
        # Overall height (right)
        self._dim_v(painter, y, y + h, x + w, 50.0, f"{h:.1f}")
        # Top plate band height (right, offset further)
        self._dim_v(painter, y, y + dims.top_plate, x + w, 90.0, f"{dims.top_plate:.1f}")
        # Corner notch width
        self._dim_h(painter, x + w - nw, x + w, y, -70.0, f"{nw:.1f}")
        # Corner notch height
        self._dim_v(painter, y, y + nh, x + w, 130.0, f"{nh:.1f}")

        # Formula annotations
        dim_pen = QPen(self.DIM_COLOR, self.DIM_LINE_WIDTH)
        painter.setPen(dim_pen)
        painter.setFont(QFont("Arial", 9))
        # painter.drawText(
        #     QRectF(x, y - 52.0, w, 14.0), Qt.AlignmentFlag.AlignCenter,
        #     f"Width = {dims.coil_width:.0f} + 2×(({dims.top_plate:.0f}+{dims.first_bend_top_plate:.0f}) − 4×{dims.sheet_metal_thickness:.1f}) = {w:.1f} mm",
        # )
        # splits = dims.number_of_splits
        # painter.drawText(
        #     QRectF(x, y - 36.0, w, 14.0), Qt.AlignmentFlag.AlignCenter,
        #     f"Height = ({dims.fin_length:.0f}/{splits:.0f} − ({splits:.0f}−2)×{dims.sheet_metal_thickness:.1f}) + 2×{dims.top_plate:.0f} − 4×{dims.sheet_metal_thickness:.1f} = {h:.1f} mm",
        # )
        # painter.drawText(
        #     QRectF(x, y - 20.0, w, 14.0), Qt.AlignmentFlag.AlignCenter,
        #     f"Circle X = 20 + ({dims.top_plate:.0f}−2×{dims.sheet_metal_thickness:.1f}) + ({dims.first_bend_top_plate:.0f}−2×{dims.sheet_metal_thickness:.1f}) = {dims.circle_x_offset:.1f} mm  |  Pitch = {dims.hole_pitch:.2f} mm",
        # )

        # View label
        painter.setPen(obj_pen)
        self._draw_underlined_label(
            painter,
            QRectF(x, y + h + 50.0, w, 30.0),
            f"TOP / BOTTOM PLATE  ({dims.coil_unique_id}-TP)",
        )

    def _draw_notes(self, painter: QPainter, layout: dict) -> None:
        dims = self._dims
        nx = layout["tp_x"]
        ny = layout["tp_y"] + layout["tp_h"] + 100.0
        painter.save()
        painter.setPen(QPen(self.OBJECT_COLOR, self.OBJECT_LINE_WIDTH))
        painter.setFont(QFont("Arial", 10))
        for i, line in enumerate([
            f"Job Order No.: {dims.job_order_no}",
            f"Coil Unique ID: {dims.coil_unique_id}",
            f"Coil Type: {dims.coil_type}",
            f"Connection: {dims.connection_side}",
            f"File Name: {dims.coil_unique_id}-TP",
        ]):
            painter.drawText(QRectF(nx, ny + i * 22.0, 460.0, 20.0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line)
        ty = ny + 5 * 22.0 + 18.0
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

    # ── Dimension helpers ─────────────────────────────────────────────────────

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
        iw = int(max(1200, dims.total_width * 4 + 600))
        ih = int(max(900,  dims.total_height * 2 + 500))
        img = QImage(iw, ih, QImage.Format.Format_ARGB32)
        img.fill(QColor("white"))
        p = QPainter(img)
        self.render_to_painter(p, QRectF(0.0, 0.0, float(iw), float(ih)), QColor("white"))
        p.end()
        return img.save(file_path)

    def export_dxf(self, file_path: str) -> bool:
        """Export the drawing to DXF using the adapter."""
        try:
            layout = self._layout_data()
            canvas_height = layout["world_h"]
            adapter = DxfPainterAdapter(file_path, canvas_height)
            
            # Simulate the rendering process for DXF
            adapter.save()
            scale = 1.0  # DXF uses real units (mm)
            ox = layout["tp_x"]
            oy = layout["tp_y"]
            
            # We need to call the draw methods directly on adapter
            self._draw_top_plate_dxf(adapter, layout)
            self._draw_notes_dxf(adapter, layout)
            
            adapter.write_dimensions_metadata(self._dims)
            adapter.save_to_file()
            return True
        except Exception as e:
            print(f"DXF Export Error: {e}")
            return False

    def _draw_top_plate_dxf(self, painter: DxfPainterAdapter, layout: dict) -> None:
        """Adapted version of _draw_top_plate for DXF adapter."""
        dims = self._dims
        x = layout["tp_x"]
        y = layout["tp_y"]
        w = layout["tp_w"]
        h = layout["tp_h"]

        obj_pen = QPen(self.OBJECT_COLOR, self.OBJECT_LINE_WIDTH)
        painter.setPen(obj_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(x, y, w, h))

        # Top plate band line
        top_band_y    = y + dims.top_plate
        bottom_band_y = y + h - dims.top_plate
        painter.setPen(QPen(self.OBJECT_COLOR, 1.0))
        painter.drawLine(QPointF(x, top_band_y),    QPointF(x + w, top_band_y))
        painter.drawLine(QPointF(x, bottom_band_y), QPointF(x + w, bottom_band_y))

        # Holes
        hole_r   = 3.0
        cx_first = dims.circle_x_offset
        pitch    = dims.hole_pitch
        hole_y_top = y + dims.top_plate / 2.0
        hole_y_bot = y + h - dims.top_plate / 2.0
        hole_xs = [cx_first + i * pitch for i in range(5)]

        painter.setPen(obj_pen)
        for hx in hole_xs:
            painter.drawEllipse(QPointF(x + hx, hole_y_top), hole_r, hole_r)
            painter.drawEllipse(QPointF(x + hx, hole_y_bot), hole_r, hole_r)

        # Corner notches
        nw = dims.corner_notch_width
        nh = dims.corner_notch_height
        notch_pen   = QPen(self.NOTCH_COLOR, self.OBJECT_LINE_WIDTH)
        notch_brush = QColor("#444444")

        painter.save()
        painter.setPen(notch_pen)
        painter.setBrush(notch_brush)
        painter.drawRect(QRectF(x, y, nw, nh))
        painter.drawRect(QRectF(x + w - nw, y, nw, nh))
        painter.drawRect(QRectF(x, y + h - nh, nw, nh))
        painter.drawRect(QRectF(x + w - nw, y + h - nh, nw, nh))
        painter.restore()

        painter.setPen(obj_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(x, y, w, h))

        # Dimensions (simplified for DXF)
        self._dim_h_dxf(painter, x, x + w, y, -45.0, f"{w:.1f}")
        self._dim_v_dxf(painter, y, y + h, x + w, 50.0, f"{h:.1f}")

        # Labels
        painter.setPen(obj_pen)
        self._draw_underlined_label_dxf(painter, QRectF(x, y + h + 50.0, w, 30.0), f"TOP / BOTTOM PLATE  ({dims.coil_unique_id}-TP)")

    def _draw_notes_dxf(self, painter: DxfPainterAdapter, layout: dict) -> None:
        dims = self._dims
        nx = layout["tp_x"]
        ny = layout["tp_y"] + layout["tp_h"] + 100.0
        painter.setPen(QPen(self.OBJECT_COLOR, self.OBJECT_LINE_WIDTH))
        painter.setFont(QFont("Arial", 10))
        
        notes = [
            f"Job Order No.: {dims.job_order_no}",
            f"Coil Unique ID: {dims.coil_unique_id}",
            f"Coil Type: {dims.coil_type}",
            f"Connection: {dims.connection_side}",
        ]
        for i, line in enumerate(notes):
            rect = QRectF(nx, ny + i * 22.0, 460.0, 20.0)
            painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line)  # Note: drawText signature may need adjustment

    def _dim_h_dxf(self, painter, x1, x2, y_ref, offset, label):
        # Simplified dimension for DXF - just lines and text
        y = y_ref + offset
        painter.setPen(QPen(self.DIM_COLOR, self.DIM_LINE_WIDTH))
        painter.drawLine(QPointF(x1, y_ref), QPointF(x1, y))
        painter.drawLine(QPointF(x2, y_ref), QPointF(x2, y))
        painter.drawLine(QPointF(x1, y), QPointF(x2, y))
        painter.drawText(QRectF(x1, y - 25, x2 - x1, 20), Qt.AlignmentFlag.AlignCenter, label)

    def _dim_v_dxf(self, painter, y1, y2, x_ref, offset, label):
        x = x_ref + offset
        painter.setPen(QPen(self.DIM_COLOR, self.DIM_LINE_WIDTH))
        painter.drawLine(QPointF(x_ref, y1), QPointF(x, y1))
        painter.drawLine(QPointF(x_ref, y2), QPointF(x, y2))
        painter.drawLine(QPointF(x, y1), QPointF(x, y2))
        painter.drawText(QRectF(x + 5, (y1+y2)/2 - 10, 100, 20), Qt.AlignmentFlag.AlignLeft, label)

    def _draw_underlined_label_dxf(self, painter, rect, text):
        painter.setPen(QPen(self.OBJECT_COLOR, self.OBJECT_LINE_WIDTH))
        painter.setFont(QFont("Arial", 13))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)


# ═══════════════════════════════════════════════════════════════════════════════
#  Main Window
# ═══════════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Coil Helvix - TOP / BOTTOM PLATE")
        self.resize(1280, 860)
        self.default_dims = TopPlateDimensions()
        self._spin_boxes: dict[str, QDoubleSpinBox] = {}
        self._text_inputs: dict[str, QLineEdit] = {}
        self._is_syncing_inputs = False
        self.drawing_widget = TopBottomPlateDrawingWidget(self.default_dims)

        # Derived labels
        self._tp_w_label   = QLabel()
        self._tp_h_label   = QLabel()
        self._tp_cx_label  = QLabel()
        self._tp_pit_label = QLabel()
        self._tp_nw_label  = QLabel()
        self._tp_nh_label  = QLabel()
        self._zoom_label   = QLabel("100%")

        self._build_ui()
        self._apply_changes()

    def _build_ui(self) -> None:
        sp = QSplitter(Qt.Orientation.Horizontal)
        sp.addWidget(self._build_controls_panel())
        sp.addWidget(self.drawing_widget)
        sp.setStretchFactor(1, 1)
        sp.setSizes([340, 920])
        self.setCentralWidget(sp)

    def _build_controls_panel(self) -> QWidget:
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)
        for grp in [
            self._build_identity_group(),
            self._build_main_specs_group(),
            self._build_derived_group(),
        ]:
            lay.addWidget(grp)
        lay.addLayout(self._build_buttons_row())
        lay.addLayout(self._build_zoom_row())
        lay.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.setMinimumWidth(320)
        return scroll

    def _build_identity_group(self):
        g = QGroupBox("Order Details"); f = QFormLayout(g)
        self._add_text(f, "job_order_no",   "Job Order No.",  self.default_dims.job_order_no)
        self._add_text(f, "coil_unique_id", "Coil Unique ID", self.default_dims.coil_unique_id)
        self._add_text(f, "coil_type",      "Coil Type",      self.default_dims.coil_type)
        return g

    def _build_main_specs_group(self):
        g = QGroupBox("Dimensions"); f = QFormLayout(g)
        self._add_spin(f, "coil_width",             "Coil Width (mm)",          self.default_dims.coil_width, 80, 6000, 1)
        self._add_spin(f, "top_plate",              "Top Plate (mm)",           self.default_dims.top_plate, 5, 500, 1)
        self._add_spin(f, "first_bend_top_plate",   "First Bend - Top Plate",   self.default_dims.first_bend_top_plate, 1, 200, 1)
        self._add_spin(f, "fin_length",             "Fin Length (mm)",          self.default_dims.fin_length, 100, 20000, 1)
        self._add_spin(f, "number_of_splits",       "No. of Splits",            self.default_dims.number_of_splits, 1, 20, 0)
        self._add_spin(f, "sheet_metal_thickness",  "Sheet Metal Thickness",    self.default_dims.sheet_metal_thickness, 0.5, 10, 2)
        return g

    def _build_derived_group(self):
        g = QGroupBox("Derived / Computed"); f = QFormLayout(g)
        f.addRow("Total Width",         self._tp_w_label)
        f.addRow("Total Height",        self._tp_h_label)
        f.addRow("Circle X Offset",     self._tp_cx_label)
        f.addRow("Hole Pitch",          self._tp_pit_label)
        f.addRow("Corner Notch Width",  self._tp_nw_label)
        f.addRow("Corner Notch Height", self._tp_nh_label)
        return g

    def _build_buttons_row(self):
        lay = QHBoxLayout()
        for lbl, slot in [("Apply", self._apply_changes), ("Reset", self._reset_defaults),
                          ("Print", self._print_drawing),  ("Export PNG", self._export_png),
                          ("Export DXF", self._export_dxf)]:
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

    def _add_spin(self, form, key, label, default_value, minimum, maximum, decimals=1):
        s = QDoubleSpinBox()
        s.setDecimals(decimals); s.setRange(minimum, maximum); s.setValue(default_value)
        s.setSingleStep(1.0); s.setKeyboardTracking(False)
        s.valueChanged.connect(self._apply_changes)
        self._spin_boxes[key] = s; form.addRow(label, s)

    def _add_text(self, form, key, label, default_value):
        t = QLineEdit(); t.setText(str(default_value))
        t.textChanged.connect(self._apply_changes)
        self._text_inputs[key] = t; form.addRow(label, t)

    def _collect_dimensions(self) -> TopPlateDimensions:
        return TopPlateDimensions(
            job_order_no=self._text_inputs["job_order_no"].text() or self.default_dims.job_order_no,
            coil_unique_id=self._text_inputs["coil_unique_id"].text() or self.default_dims.coil_unique_id,
            coil_type=self._text_inputs["coil_type"].text() or self.default_dims.coil_type,
            connection_side=self.default_dims.connection_side,
            coil_width=self._spin_boxes["coil_width"].value(),
            top_plate=self._spin_boxes["top_plate"].value(),
            first_bend_top_plate=self._spin_boxes["first_bend_top_plate"].value(),
            fin_length=self._spin_boxes["fin_length"].value(),
            number_of_splits=self._spin_boxes["number_of_splits"].value(),
            sheet_metal_thickness=self._spin_boxes["sheet_metal_thickness"].value(),
        )

    def _apply_changes(self) -> None:
        if self._is_syncing_inputs:
            return
        dims = self._collect_dimensions().sanitized()
        self._tp_w_label.setText(f"{dims.total_width:.1f} mm")
        self._tp_h_label.setText(f"{dims.total_height:.1f} mm")
        self._tp_cx_label.setText(f"{dims.circle_x_offset:.1f} mm")
        self._tp_pit_label.setText(f"{dims.hole_pitch:.2f} mm")
        self._tp_nw_label.setText(f"{dims.corner_notch_width:.1f} mm")
        self._tp_nh_label.setText(f"{dims.corner_notch_height:.1f} mm")
        self.drawing_widget.set_dimensions(dims)
        self._zoom_label.setText(f"{self.drawing_widget.zoom_percent()}%")

    def _reset_defaults(self) -> None:
        d = self.default_dims
        self._is_syncing_inputs = True
        try:
            for k, v in {
                "coil_width": d.coil_width,
                "top_plate": d.top_plate,
                "first_bend_top_plate": d.first_bend_top_plate,
                "fin_length": d.fin_length,
                "number_of_splits": d.number_of_splits,
                "sheet_metal_thickness": d.sheet_metal_thickness,
            }.items():
                s = self._spin_boxes.get(k)
                if s:
                    s.blockSignals(True); s.setValue(v); s.blockSignals(False)
        finally:
            self._is_syncing_inputs = False
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
        dims = self.drawing_widget._dims
        default_name = f"{dims.coil_unique_id}-TP.png"
        fp, _ = QFileDialog.getSaveFileName(
            self, "Export Top/Bottom Plate", default_name, "PNG Image (*.png)"
        )
        if not fp:
            return
        if not fp.lower().endswith(".png"):
            fp += ".png"
        if not self.drawing_widget.export_png(fp):
            QMessageBox.warning(self, "Export Failed", "Could not save PNG.")

    def _export_dxf(self) -> None:
        dims = self.drawing_widget._dims
        default_name = f"{dims.coil_unique_id}-TP.dxf"
        fp, _ = QFileDialog.getSaveFileName(
            self, "Export DXF", default_name, "DXF Files (*.dxf)"
        )
        if not fp:
            return
        if not fp.lower().endswith(".dxf"):
            fp += ".dxf"
        if not self.drawing_widget.export_dxf(fp):
            QMessageBox.warning(self, "Export Failed", "Could not save DXF. Make sure ezdxf is installed (pip install ezdxf).")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Coil Helvix - Top/Bottom Plate")
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

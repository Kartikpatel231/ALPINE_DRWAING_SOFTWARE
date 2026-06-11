import math
import sys
import json
import os
import hmac
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dataclasses import dataclass, replace



from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPolygonF, QPainterPath
from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QInputDialog,
    QLineEdit, QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget,
)

# ── ezdxf import (robust) ────────────────────────────────────────────────────
try:
    import ezdxf
    _EZDXF_OK = True
except ImportError:
    ezdxf = None
    _EZDXF_OK = False

try:
    from ezdxf.enums import TextEntityAlignment
except Exception:
    try:
        from ezdxf.entities import TextEntityAlignment
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
    right_panel_width: float = 65.0          # Return Side Plate
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
    side_plate_outer_circle_dia: float = 15.88
    side_plate_inner_circle_dia: float = 14.5
    sheet_metal_thickness: float = 1.5
    first_bend_header_side: float = 12.0
    first_bend_return_side: float = 12.0     # First Bend of Return Side Plate
    first_bend_top_plate: float = 12.0
    first_bend_bottom_plate: float = 12.0
    first_bend_blank_off: float = 12.0
    first_bend_intermediate_plate: float = 25.0

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

    # ── Return Bend Plate computed dimensions ────────────────────────────────

    @property
    def rp_total_width(self) -> float:
        return self.core_width + 2.0 * (
            (self.right_panel_width + self.first_bend_return_side) - (4.0 * self.sheet_metal_thickness)
        )

    @property
    def rp_lifting_hole_side_dist(self) -> float:
        return (self.right_panel_width / 2.0) + (self.first_bend_return_side - 2.0 * self.sheet_metal_thickness)

    @property
    def rp_blank_off_hole_count(self) -> int:
        return max(1, round(self.front_total_height / 150.0))

    # ── Shared properties ────────────────────────────────────────────────────

    @property
    def header_plate_total_width(self) -> float:
        return self.core_width + 2.0 * (
            (self.left_panel_width + self.first_bend_header_side) - (4.0 * self.sheet_metal_thickness)
        )

    @property
    def header_plate_lifting_hole_side_dist(self) -> float:
        return (self.left_panel_width / 2.0) + (self.first_bend_header_side - 2.0 * self.sheet_metal_thickness)

    @property
    def header_plate_blank_off_hole_count(self) -> int:
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


# ═══════════════════════════════════════════════════════════════════════════════
#  DXF Painter Adapter  (same pattern as bottomplate.py)
# ═══════════════════════════════════════════════════════════════════════════════

class DxfPainterAdapter:
    """Drop-in QPainter replacement that writes to a DXF file."""

    METADATA_LAYER  = "COIL_META"
    METADATA_PREFIX = "COIL_HELVIX_DIMS:"

    def __init__(self, file_path: str, canvas_height: float) -> None:
        if not _EZDXF_OK:
            raise RuntimeError(
                "ezdxf is not importable. "
                "Run:  pip install --upgrade ezdxf"
            )
        self._file_path     = file_path
        self._canvas_height = canvas_height
        self._doc           = ezdxf.new("R2010")
        self._doc.units     = 4          # mm
        self._msp           = self._doc.modelspace()

        self._ensure_layer("DRAWING",           7)
        self._ensure_layer("DIM",               1)   # red – dimension lines
        self._ensure_layer("TUBES",             3)   # green – tube circles
        self._ensure_layer("TEXT",              7)
        self._ensure_layer(self.METADATA_LAYER, 8)
        self._ensure_linetype("DASHED")

        self._pen          = QPen(QColor("#111111"), 1.0)
        self._brush        = Qt.BrushStyle.NoBrush
        self._font         = QFont("Arial", 10)
        self._clip_enabled = False
        self._matrix       = self._identity_matrix()
        self._stack: list   = []

    def save_to_file(self) -> None:
        self._doc.saveas(self._file_path)

    # ── layer / linetype setup ────────────────────────────────────

    def _ensure_layer(self, name: str, color: int) -> None:
        if name not in self._doc.layers:
            self._doc.layers.add(name, color=color)

    def _ensure_linetype(self, name: str) -> None:
        if name in self._doc.linetypes:
            return
        if name == "DASHED":
            self._doc.linetypes.new(name, dxfattribs={
                "description": "Dashed __ __",
                "pattern": [0.5, 0.25, -0.25],
            })

    # ── state stack ───────────────────────────────────────────────

    def save(self) -> None:
        self._stack.append((
            QPen(self._pen), self._brush, QFont(self._font),
            self._clip_enabled, [row[:] for row in self._matrix],
        ))

    def restore(self) -> None:
        if not self._stack:
            return
        pen, brush, font, clip, matrix = self._stack.pop()
        self._pen          = pen
        self._brush        = brush
        self._font         = font
        self._clip_enabled = clip
        self._matrix       = matrix

    # ── no-ops matching QPainter API ──────────────────────────────

    def setRenderHint(self, *_a, **_kw): return
    def fillRect(self,    *_a, **_kw):   return
    def setClipPath(self, _p):           self._clip_enabled = True

    # ── pen / brush / font ────────────────────────────────────────

    def setPen(self, pen) -> None:
        if isinstance(pen, QPen):
            self._pen = QPen(pen)
        elif isinstance(pen, QColor):
            self._pen = QPen(pen, self._pen.widthF())

    def pen(self) -> QPen:    return self._pen
    def setBrush(self, b):    self._brush = b
    def brush(self):          return self._brush
    def setFont(self, f):     self._font = QFont(f)

    # ── transforms ───────────────────────────────────────────────

    def translate(self, dx: float, dy: float) -> None:
        self._matrix = self._mm(
            self._matrix, [[1,0,dx],[0,1,dy],[0,0,1]])

    def scale(self, sx: float, sy: float | None = None) -> None:
        sv = sx if sy is None else sy
        self._matrix = self._mm(
            self._matrix, [[sx,0,0],[0,sv,0],[0,0,1]])

    def rotate(self, deg: float) -> None:
        a = math.radians(deg)
        c, s = math.cos(a), math.sin(a)
        self._matrix = self._mm(
            self._matrix, [[c,s,0],[-s,c,0],[0,0,1]])

    # ── drawing primitives ────────────────────────────────────────

    def drawLine(self, *args) -> None:
        if self._clip_enabled:
            return
        if len(args) == 2 and isinstance(args[0], QPointF):
            x1,y1,x2,y2 = args[0].x(),args[0].y(),args[1].x(),args[1].y()
        elif len(args) == 4:
            x1,y1,x2,y2 = map(float, args)
        else:
            return
        p1 = self._tp(x1, y1)
        p2 = self._tp(x2, y2)
        self._msp.add_line(self._dxf(p1), self._dxf(p2),
                           dxfattribs=self._lattribs())

    def drawRect(self, rect: QRectF) -> None:
        x,y,w,h = rect.x(),rect.y(),rect.width(),rect.height()
        self.drawLine(QPointF(x,   y  ), QPointF(x+w, y  ))
        self.drawLine(QPointF(x+w, y  ), QPointF(x+w, y+h))
        self.drawLine(QPointF(x+w, y+h), QPointF(x,   y+h))
        self.drawLine(QPointF(x,   y+h), QPointF(x,   y  ))

    def drawEllipse(self, *args) -> None:
        if len(args) == 1 and isinstance(args[0], QRectF):
            r  = args[0]
            cx = r.x() + r.width()  / 2.0
            cy = r.y() + r.height() / 2.0
            rx, ry = r.width()/2.0, r.height()/2.0
        elif len(args) == 3 and isinstance(args[0], QPointF):
            cx, cy = args[0].x(), args[0].y()
            rx, ry = float(args[1]), float(args[2])
        else:
            return
        pts = self._ellipse_pts(cx, cy, rx, ry, 72)
        self._polyline(pts, close=True)

    def drawArc(self, rect: QRectF, start_angle: int, span_angle: int) -> None:
        cx = rect.x() + rect.width()  / 2.0
        cy = rect.y() + rect.height() / 2.0
        rx = rect.width()  / 2.0
        ry = rect.height() / 2.0
        start_deg = start_angle / 16.0
        span_deg  = span_angle  / 16.0
        segs = max(16, int(abs(span_deg) / 7.0))
        pts = []
        for i in range(segs + 1):
            ang = math.radians(start_deg + span_deg * i / segs)
            pts.append(self._tp(cx + rx*math.cos(ang),
                                cy - ry*math.sin(ang)))
        self._polyline(pts, close=False)

    def drawText(self, *args) -> None:
        if len(args) != 3:
            return
        rect, _flags, text = args
        if not isinstance(rect, QRectF):
            return
        x      = rect.x() + rect.width()  / 2.0
        y      = rect.y() + rect.height() / 2.0
        anchor = self._tp(x, y)
        rot    = self._rot_deg()
        fs     = self._font.pointSizeF()
        if fs <= 0:
            fs = float(max(9, self._font.pointSize()))
        entity = self._msp.add_text(
            str(text),
            dxfattribs={
                "layer":      "TEXT",
                "height":     max(8.0, fs),
                "rotation":   rot,
                "true_color": self._rgb(self._pen.color()),
            },
        )
        apt = self._dxf(anchor)
        if TextEntityAlignment is not None:
            try:
                entity.set_placement(apt, align=TextEntityAlignment.MIDDLE_CENTER)
                return
            except Exception:
                pass
        try:
            entity.set_pos(apt, align="MIDDLE_CENTER")
        except Exception:
            entity.dxf.insert = apt

    def drawPolygon(self, polygon: QPolygonF) -> None:
        pts = [self._tp(pt.x(), pt.y()) for pt in polygon]
        self._polyline(pts, close=True)

    def drawPath(self, path: QPainterPath) -> None:
        if self._clip_enabled:
            return
        for polygon in path.toSubpathPolygons():
            pts = [self._tp(pt.x(), pt.y()) for pt in polygon]
            if len(pts) < 2:
                continue
            fx,fy = pts[0]; lx,ly = pts[-1]
            closed = math.hypot(lx-fx, ly-fy) <= 1e-6
            if closed:
                pts = pts[:-1]
            if len(pts) >= 2:
                self._polyline(pts, close=closed)

    def write_metadata(self, vals: dict) -> None:
        meta = f"{self.METADATA_PREFIX}{json.dumps(vals, separators=(',',':'), sort_keys=True)}"
        ent = self._msp.add_text(
            meta,
            dxfattribs={
                "layer":      self.METADATA_LAYER,
                "height":     2.5,
                "true_color": self._rgb(QColor("#666666")),
            },
        )
        ent.dxf.insert = (0.0, -1000000.0)

    # ── internals ─────────────────────────────────────────────────

    def _lattribs(self) -> dict:
        style = self._pen.style()
        lt = "CONTINUOUS"
        if style in {Qt.PenStyle.DashLine, Qt.PenStyle.DashDotLine,
                     Qt.PenStyle.DashDotDotLine, Qt.PenStyle.CustomDashLine}:
            lt = "DASHED"
        return {"layer": "DRAWING",
                "true_color": self._rgb(self._pen.color()),
                "linetype": lt}

    def _polyline(self, pts, close: bool) -> None:
        if len(pts) < 2:
            return
        self._msp.add_lwpolyline(
            [self._dxf(p) for p in pts],
            close=close,
            dxfattribs=self._lattribs())

    def _ellipse_pts(self, cx, cy, rx, ry, n):
        return [self._tp(cx + rx*math.cos(2*math.pi*i/n),
                         cy + ry*math.sin(2*math.pi*i/n))
                for i in range(n + 1)]

    def _rot_deg(self) -> float:
        p0 = self._tp(0, 0); p1 = self._tp(1, 0)
        return math.degrees(math.atan2(-(p1[1]-p0[1]), p1[0]-p0[0]))

    def _rgb(self, c: QColor) -> int:
        return (c.red() << 16) + (c.green() << 8) + c.blue()

    def _dxf(self, pt: tuple) -> tuple:
        return float(pt[0]), float(self._canvas_height - pt[1])

    def _tp(self, x: float, y: float) -> tuple:
        m = self._matrix
        return (m[0][0]*x + m[0][1]*y + m[0][2],
                m[1][0]*x + m[1][1]*y + m[1][2])

    @staticmethod
    def _identity_matrix():
        return [[1,0,0],[0,1,0],[0,0,1]]

    @staticmethod
    def _mm(a, b):
        return [
            [a[r][0]*b[0][c]+a[r][1]*b[1][c]+a[r][2]*b[2][c]
             for c in range(3)]
            for r in range(3)
        ]


# ═══════════════════════════════════════════════════════════════════════════════
#  Return Bend Plate Drawing Widget
# ═══════════════════════════════════════════════════════════════════════════════

class ReturnBendPlateDrawingWidget(QWidget):
    """
    Draws the Return Bend Plate view.

    Spec:
      Step 1 : End-plate steps 1-13 + step 15 (blank-off holes).
               Mirror image only — tube grid row stagger is reversed (odd rows shift DOWN).
               Point 14 (standard header lifting holes) not required.
      Step 2 : Width = Coil Width + 2 * ((Return Side Plate + FB_Return) - (4 * t))
               Example: 280 + 2*((65+12)-(4*1.5)) = 422 mm
      Step 3 : Lifting hole ø20 — top dist=50 mm,
               side dist = (Return Side Plate/2) + (FB_Return - 2*t)
               Example: 65/2 + (12 - 2*1.5) = 41.5 mm
      Step 4 : Mirror lifting hole on other side.
      Step 5 : File name = {coil_unique_id}-RP
    """

    BACKGROUND        = QColor("#f2f2f2")
    OBJECT_COLOR      = QColor("#111111")
    DIM_COLOR         = QColor("#ff6a00")
    TUBE_COLOR        = QColor("#ff1a1a")
    MAGENTA           = QColor("#b000ff")
    OBJECT_LINE_WIDTH = 1.7
    DIM_LINE_WIDTH    = 1.05

    def __init__(self, dimensions: CoilDimensions | None = None) -> None:
        super().__init__()
        self._dims = (dimensions or CoilDimensions()).sanitized()
        self._zoom = 1.0
        self._min_zoom = 0.25
        self._max_zoom = 6.0
        self._pan_offset = QPointF(0.0, 0.0)
        self._is_panning = False
        self._last_pan_pos: QPointF | None = None
        self.setMinimumSize(700, 600)

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
        self._draw_return_bend_plate(painter, layout)
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

        h_inner = dims.tubes_per_row * dims.pitch_vertical + dims.top_plate + dims.bottom_plate
        w       = dims.rp_total_width

        world_w = margin_left + w + 300.0
        world_h = margin_top + h_inner + 320.0

        return {
            "rp_x":    margin_left,
            "rp_y":    margin_top,
            "rp_h":    h_inner,
            "rp_w":    w,
            "world_w": world_w,
            "world_h": world_h,
        }

    # ── Return Bend Plate drawing ─────────────────────────────────────────────

    def _draw_return_bend_plate(self, painter, layout: dict) -> None:
        dims = self._dims
        x    = layout["rp_x"]
        y    = layout["rp_y"]
        h    = layout["rp_h"]
        w    = layout["rp_w"]

        rows_in_width    = max(1, int(round(dims.number_of_rows)))
        tubes_per_row    = max(1, int(round(dims.tubes_per_row)))
        horizontal_pitch = max(5.0, dims.pitch_horizontal)
        vertical_pitch   = max(5.0, dims.pitch_vertical)
        tube_layout_w    = rows_in_width * horizontal_pitch
        tube_layout_h    = max(0.0, tubes_per_row * vertical_pitch)

        obj_pen        = QPen(self.OBJECT_COLOR, self.OBJECT_LINE_WIDTH)
        inner_rect_pen = QPen(QColor("#222222"), 1.8)

        # Step 2: Main outer box
        painter.setPen(obj_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(x, y, w, h))

        # Top and bottom plate offset lines
        top_offset_y    = y + dims.top_plate
        bottom_offset_y = y + h - dims.bottom_plate
        painter.setPen(QPen(self.OBJECT_COLOR, 1.0))
        painter.drawLine(QPointF(x,     top_offset_y),    QPointF(x + w, top_offset_y))
        painter.drawLine(QPointF(x,     bottom_offset_y), QPointF(x + w, bottom_offset_y))

        # Inner tube layout box
        tb_left_local = (w - tube_layout_w) / 2.0
        tb_top        = h - dims.bottom_plate - tube_layout_h
        painter.setPen(inner_rect_pen)
        painter.drawRect(QRectF(x + tb_left_local, y + tb_top, tube_layout_w, tube_layout_h))

        # Step 1 (Mirror): Double-circle tube holes with REVERSED stagger
        dia_limit    = min(horizontal_pitch, vertical_pitch) * 0.90
        circle_1_dia = max(2.0, min(dims.side_plate_outer_circle_dia, dia_limit))
        circle_2_dia = max(2.0, min(dims.side_plate_inner_circle_dia, dia_limit))
        circle_1_r   = circle_1_dia / 2.0
        circle_2_r   = max(1.0, (circle_2_dia / 2.0) - 0.6)

        outer_hole_pen = QPen(self.TUBE_COLOR,   1.1)
        inner_hole_pen = QPen(self.OBJECT_COLOR, 1.1)

        first_cx      = tb_left_local + horizontal_pitch * 0.5
        y_start_frbot = dims.bottom_plate + vertical_pitch * 0.5
        y_bot_lim     = dims.bottom_plate
        y_top_lim     = h - dims.top_plate

        for row_i in range(rows_in_width):
            rcx = first_cx + row_i * horizontal_pitch
            row_shift = (vertical_pitch * 0.5) if (row_i % 2 == 0) else 0.0
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

        # Band small holes ø6 (top + bottom, points 10-13)
        small_r    = 3.0
        top_hole_y = y + dims.top_plate / 2.0
        bot_hole_y = y + h - dims.bottom_plate / 2.0
        edge_dist  = 20.0
        s_pitch    = max(1.0, (w - 40.0) / 4.0)

        painter.setPen(obj_pen)
        for hi in range(5):
            hx = x + edge_dist + hi * s_pitch
            painter.drawEllipse(QPointF(hx, top_hole_y), small_r, small_r)
            painter.drawEllipse(QPointF(hx, bot_hole_y), small_r, small_r)

        # Magenta dashed band lines + 5 marker dots
        mg_pen = QPen(self.MAGENTA, 1.1)
        mg_pen.setStyle(Qt.PenStyle.DashLine)
        mg_pen.setDashPattern([8.0, 5.0])
        painter.setPen(mg_pen)
        bm            = 8.0
        top_band_y    = dims.top_plate * 0.5
        bottom_band_y = h - dims.bottom_plate * 0.5
        painter.drawLine(QPointF(x + bm,     y + top_band_y),
                         QPointF(x + w - bm, y + top_band_y))
        painter.drawLine(QPointF(x + bm,     y + bottom_band_y),
                         QPointF(x + w - bm, y + bottom_band_y))

        inner_offset_x = (w - dims.core_width) / 2.0
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

        # Point 15: Blank-off holes ø6
        bo_count   = dims.rp_blank_off_hole_count
        bo_r       = 3.0
        lift_top_y = y + 50.0
        side_dist  = dims.rp_lifting_hole_side_dist
        lift_lx    = x + side_dist
        lift_rx    = x + w - side_dist
        bo_first_y = lift_top_y + 25.0
        bo_pitch   = 150.0

        # Steps 3-4: Lifting holes ø20
        lift_r = 10.0

        painter.save()
        painter.setPen(QPen(self.OBJECT_COLOR, self.OBJECT_LINE_WIDTH))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(lift_lx, lift_top_y), lift_r, lift_r)
        painter.drawEllipse(QPointF(lift_rx, lift_top_y), lift_r, lift_r)
        painter.restore()

        # Dimensions
        self._dim_h(painter, x, x + w, y, -45.0, f"{w:.0f}")
        self._dim_v(painter, y, y + h, x + w, 50.0, f"{h:.0f}")
        self._dim_v(painter, y, y + dims.top_plate, x + w, 90.0, f"{dims.top_plate:.0f}")
        self._dim_v(painter, y + h - dims.bottom_plate, y + h, x + w, 90.0, f"{dims.bottom_plate:.0f}")
        self._dim_v(painter, y, lift_top_y, x, -50.0, "50")
        self._dim_h(painter, x, lift_lx, y + h, 45.0, f"{side_dist:.1f}")

        # Annotations
        dim_pen = QPen(self.DIM_COLOR, self.DIM_LINE_WIDTH)
        painter.setPen(dim_pen)
        painter.setFont(QFont("Arial", 9))
        painter.drawText(
            QRectF(x, y - 52.0, w, 14.0), Qt.AlignmentFlag.AlignCenter,
            f"Width = Core ({dims.core_width:.0f}) + 2×((RSP ({dims.right_panel_width:.0f}) + FB ({dims.first_bend_return_side:.0f})) − 4×t ({dims.sheet_metal_thickness:.1f})) = {w:.0f} mm",
        )
        painter.drawText(
            QRectF(x, y - 36.0, w, 14.0), Qt.AlignmentFlag.AlignCenter,
            f"Lifting hole side dist = RSP/2 + (FB − 2t) = {side_dist:.1f} mm",
        )
        painter.drawText(
            QRectF(x, y - 20.0, w, 14.0), Qt.AlignmentFlag.AlignCenter,
            f"Blank-off holes: {bo_count} × ø6 @ 150mm pitch  |  C1 Ø {circle_1_dia:.2f}   C2 Ø {circle_2_dia:.2f}",
        )

        # View label
        painter.setPen(obj_pen)
        self._draw_underlined_label(
            painter,
            QRectF(x, y + h + 50.0, w, 30.0),
            f"RETURN BEND PLATE  ({dims.coil_unique_id}-RP)",
        )

    def _draw_notes(self, painter, layout: dict) -> None:
        dims = self._dims
        nx = layout["rp_x"]
        ny = layout["rp_y"] + layout["rp_h"] + 100.0
        painter.save()
        painter.setPen(QPen(self.OBJECT_COLOR, self.OBJECT_LINE_WIDTH))
        painter.setFont(QFont("Arial", 10))
        for i, line in enumerate([
            f"Job Order No.: {dims.job_order_no}",
            f"Coil Unique ID: {dims.coil_unique_id}",
            f"Coil Type: {dims.coil_type}",
            f"Connection: {dims.connection_side}",
            f"File Name: {dims.coil_unique_id}-RP",
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
        iw = int(max(1200, dims.rp_total_width * 4 + 600))
        ih = int(max(900,  dims.front_total_height * 3 + 500))
        img = QImage(iw, ih, QImage.Format.Format_ARGB32)
        img.fill(QColor("white"))
        p = QPainter(img)
        self.render_to_painter(p, QRectF(0.0, 0.0, float(iw), float(ih)), QColor("white"))
        p.end()
        return img.save(file_path)

    # ── DXF Export ────────────────────────────────────────────────────────────

    def export_dxf(self, file_path: str) -> bool:
        """Export the Return Bend Plate drawing to a DXF file (mm units)."""
        try:
            layout        = self._layout_data()
            canvas_height = layout["world_h"]
            adapter       = DxfPainterAdapter(file_path, canvas_height)

            # Replicate render_to_painter with scale=1 (real mm) and no view transform
            adapter.translate(0.0, 0.0)   # no pan/zoom offset for export
            self._draw_return_bend_plate(adapter, layout)
            self._draw_notes(adapter, layout)

            # Embed dimension metadata
            dims = self._dims
            meta = {
                "coil_unique_id":         dims.coil_unique_id,
                "job_order_no":           dims.job_order_no,
                "coil_type":              dims.coil_type,
                "connection_side":        dims.connection_side,
                "rp_total_width":         dims.rp_total_width,
                "front_total_height":     dims.front_total_height,
                "core_width":             dims.core_width,
                "right_panel_width":      dims.right_panel_width,
                "first_bend_return_side": dims.first_bend_return_side,
                "sheet_metal_thickness":  dims.sheet_metal_thickness,
                "top_plate":              dims.top_plate,
                "bottom_plate":           dims.bottom_plate,
                "tubes_per_row":          dims.tubes_per_row,
                "number_of_rows":         dims.number_of_rows,
                "pitch_vertical":         dims.pitch_vertical,
                "pitch_horizontal":       dims.pitch_horizontal,
            }
            adapter.write_metadata(meta)
            adapter.save_to_file()
            return True
        except Exception as exc:
            print(f"DXF Export Error: {exc}")
            return False


# ═══════════════════════════════════════════════════════════════════════════════
#  Main Window
# ═══════════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Coil Helvix - RETURN BEND PLATE")
        self.resize(1280, 860)
        self.default_dims = CoilDimensions()
        self._spin_boxes: dict[str, QDoubleSpinBox] = {}
        self._text_inputs: dict[str, QLineEdit] = {}
        self._is_syncing_inputs = False
        self.drawing_widget = ReturnBendPlateDrawingWidget(self.default_dims)
        self._rp_w_label  = QLabel()
        self._rp_s_label  = QLabel()
        self._rp_n_label  = QLabel()
        self._zoom_label  = QLabel("100%")
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
            self._build_pitch_group(),
            self._build_plate_group(),
            self._build_first_bend_group(),
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

    # ── Group builders ────────────────────────────────────────────────────────

    def _build_identity_group(self):
        g = QGroupBox("Order Details"); f = QFormLayout(g)
        self._add_text(f, "job_order_no",   "Job Order No.",  self.default_dims.job_order_no)
        self._add_text(f, "coil_unique_id", "Coil Unique ID", self.default_dims.coil_unique_id)
        self._add_text(f, "coil_type",      "Coil Type",      self.default_dims.coil_type)
        return g

    def _build_main_specs_group(self):
        g = QGroupBox("Main Specs"); f = QFormLayout(g)
        self._add_spin(f, "tubes_per_row",      "Tubes per Row",   self.default_dims.tubes_per_row, 1, 300, 0)
        self._add_spin(f, "number_of_rows",     "No. of Rows",     self.default_dims.number_of_rows, 1, 40, 0)
        self._add_spin(f, "number_of_circuits", "No. of Circuits", self.default_dims.number_of_circuits, 1, 100, 0)
        self._add_spin(f, "fpi",                "FPI",             self.default_dims.fpi, 1, 60, 0)
        self._add_spin(f, "tube_dia_inch",      "Tube Dia (inch)", self.default_dims.tube_dia_inch, 0.1, 2.0, 3)
        self._add_spin(f, "header_dia",         "Header Dia",      self.default_dims.header_dia, 2.0, 500.0)
        return g

    def _build_pitch_group(self):
        g = QGroupBox("Pitch & Circles"); f = QFormLayout(g)
        self._add_spin(f, "top_feature_pitch_vertical",   "Pitch Vertical",   self.default_dims.top_feature_pitch_vertical, 5.0, 200.0, 2)
        self._add_spin(f, "top_feature_pitch_horizontal", "Pitch Horizontal", self.default_dims.top_feature_pitch_horizontal, 5.0, 200.0, 2)
        self._add_spin(f, "side_plate_outer_circle_dia",  "Outer Circle Ø",   self.default_dims.side_plate_outer_circle_dia, 2.0, 80.0, 2)
        self._add_spin(f, "side_plate_inner_circle_dia",  "Inner Circle Ø",   self.default_dims.side_plate_inner_circle_dia, 2.0, 80.0, 2)
        return g

    def _build_plate_group(self):
        g = QGroupBox("Plate / Overall"); f = QFormLayout(g)
        self._add_spin(f, "sheet_metal_thickness", "Sheet Metal Thickness", self.default_dims.sheet_metal_thickness, 0.5, 10.0, 2)
        self._add_spin(f, "right_panel_width",     "Return Side Plate",     self.default_dims.right_panel_width, 5, 2000)
        self._add_spin(f, "core_width",            "Core Width",            self.default_dims.core_width, 60, 3000)
        self._add_spin(f, "top_plate",             "Top Plate",             self.default_dims.top_plate, 5, 1000)
        self._add_spin(f, "bottom_plate",          "Bottom Plate",          self.default_dims.bottom_plate, 5, 1000)
        self._add_spin(f, "front_total_height",    "Total Height",          self.default_dims.front_total_height, 200, 6000)
        self._spin_boxes["front_total_height"].setReadOnly(True)
        self._spin_boxes["front_total_height"].setToolTip("Calculated: (TPR × VP) + Top Plate + Bottom Plate")
        return g

    def _build_first_bend_group(self):
        g = QGroupBox("First Bend"); f = QFormLayout(g)
        self._add_spin(f, "first_bend_return_side", "Return Side Plate (FB_RS)",
                       self.default_dims.first_bend_return_side, 0, 200, 1)
        return g

    def _build_derived_group(self):
        g = QGroupBox("Derived / Computed"); f = QFormLayout(g)
        f.addRow("RP Total Width",         self._rp_w_label)
        f.addRow("Lifting Hole Side Dist", self._rp_s_label)
        f.addRow("No. of Blank-off Holes", self._rp_n_label)
        return g

    def _build_buttons_row(self):
        lay = QHBoxLayout()
        for lbl, slot in [
            ("Apply",      self._apply_changes),
            ("Reset",      self._reset_defaults),
            ("Print",      self._print_drawing),
            ("Export PNG", self._export_png),
            ("Export DXF", self._export_dxf),
        ]:
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

    def _add_text(self, form, key, label, default_value):
        t = QLineEdit(); t.setText(str(default_value))
        t.textChanged.connect(self._apply_changes)
        self._text_inputs[key] = t; form.addRow(label, t)

    # ── Dimension collection ──────────────────────────────────────────────────

    def _collect_dimensions(self) -> CoilDimensions:
        job   = self._text_inputs.get("job_order_no",   QLineEdit()).text() or self.default_dims.job_order_no
        uid   = self._text_inputs.get("coil_unique_id", QLineEdit()).text() or self.default_dims.coil_unique_id
        ctype = self._text_inputs.get("coil_type",      QLineEdit()).text() or self.default_dims.coil_type
        tp    = self._spin_boxes["top_plate"].value()
        bp    = self._spin_boxes["bottom_plate"].value()
        tpr   = self._spin_boxes["tubes_per_row"].value()
        vp    = self._spin_boxes["top_feature_pitch_vertical"].value()
        hp    = self._spin_boxes["top_feature_pitch_horizontal"].value()
        nor   = self._spin_boxes["number_of_rows"].value()
        rsp   = self._spin_boxes["right_panel_width"].value()
        fb_rs = self._spin_boxes["first_bend_return_side"].value()
        t     = self._spin_boxes["sheet_metal_thickness"].value()
        return CoilDimensions(
            top_total_length=self.default_dims.top_total_length,
            top_intermediate_length=self.default_dims.top_intermediate_length,
            front_total_width=self.default_dims.front_total_width,
            front_total_height=tpr * vp + tp + bp,
            left_panel_width=self.default_dims.left_panel_width,
            right_panel_width=rsp,
            fin_length_override=self.default_dims.fin_length_override,
            top_bottom_margin=(tp + bp) / 2.0,
            top_plate=tp,
            bottom_plate=bp,
            core_width=self._spin_boxes["core_width"].value(),
            left_pipe_offset=self.default_dims.left_pipe_offset,
            left_pipe_length=self.default_dims.left_pipe_length,
            nozzle_projection=self.default_dims.nozzle_projection,
            header_extension_length=self.default_dims.header_extension_length,
            header_box_height=hp * nor,
            right_cap_thickness=self.default_dims.right_cap_thickness,
            front_header_band_width=self.default_dims.front_header_band_width,
            top_small_offset_1=self.default_dims.top_small_offset_1,
            top_small_offset_2=self.default_dims.top_small_offset_2,
            fpi=self._spin_boxes["fpi"].value(),
            tube_dia_inch=self._spin_boxes["tube_dia_inch"].value(),
            pitch_vertical=vp,
            pitch_horizontal=hp,
            connection_side=self.default_dims.connection_side,
            job_order_no=job,
            coil_unique_id=uid,
            coil_type=ctype,
            circle_diameter=self.default_dims.circle_diameter,
            tubes_per_row=tpr,
            number_of_rows=nor,
            number_of_circuits=self._spin_boxes["number_of_circuits"].value(),
            header_dia=self._spin_boxes["header_dia"].value(),
            blank_off_bend=self.default_dims.blank_off_bend,
            top_feature_tube_dia=self.default_dims.top_feature_tube_dia,
            top_feature_tube_height=hp * (nor - 1.0),
            top_feature_pipe_length=self.default_dims.top_feature_pipe_length,
            top_feature_pitch_vertical=vp,
            top_feature_pitch_horizontal=hp,
            top_feature_circle_1_dia=self.default_dims.top_feature_circle_1_dia,
            top_feature_circle_2_dia=self.default_dims.top_feature_circle_2_dia,
            side_plate_outer_circle_dia=self._spin_boxes["side_plate_outer_circle_dia"].value(),
            side_plate_inner_circle_dia=self._spin_boxes["side_plate_inner_circle_dia"].value(),
            sheet_metal_thickness=t,
            first_bend_header_side=self.default_dims.first_bend_header_side,
            first_bend_return_side=fb_rs,
            first_bend_top_plate=self.default_dims.first_bend_top_plate,
            first_bend_bottom_plate=self.default_dims.first_bend_bottom_plate,
            first_bend_blank_off=self.default_dims.first_bend_blank_off,
            first_bend_intermediate_plate=self.default_dims.first_bend_intermediate_plate,
        )

    # ── Apply / sync ──────────────────────────────────────────────────────────

    def _apply_changes(self) -> None:
        if self._is_syncing_inputs:
            return
        dims = self._collect_dimensions().sanitized()
        self._sync_spins(dims)
        self._rp_w_label.setText(f"{dims.rp_total_width:.1f} mm")
        self._rp_s_label.setText(f"{dims.rp_lifting_hole_side_dist:.1f} mm")
        self._rp_n_label.setText(str(dims.rp_blank_off_hole_count))
        self.drawing_widget.set_dimensions(dims)
        self._zoom_label.setText(f"{self.drawing_widget.zoom_percent()}%")

    def _sync_spins(self, dims: CoilDimensions) -> None:
        vals = {
            "front_total_height":            dims.front_total_height,
            "right_panel_width":             dims.right_panel_width,
            "core_width":                    dims.core_width,
            "top_plate":                     dims.top_plate,
            "bottom_plate":                  dims.bottom_plate,
            "fpi":                           dims.fpi,
            "tube_dia_inch":                 dims.tube_dia_inch,
            "tubes_per_row":                 dims.tubes_per_row,
            "number_of_rows":                dims.number_of_rows,
            "number_of_circuits":            dims.number_of_circuits,
            "header_dia":                    dims.header_dia,
            "top_feature_pitch_vertical":    dims.top_feature_pitch_vertical,
            "top_feature_pitch_horizontal":  dims.top_feature_pitch_horizontal,
            "side_plate_outer_circle_dia":   dims.side_plate_outer_circle_dia,
            "side_plate_inner_circle_dia":   dims.side_plate_inner_circle_dia,
            "sheet_metal_thickness":         dims.sheet_metal_thickness,
            "first_bend_return_side":        dims.first_bend_return_side,
        }
        self._is_syncing_inputs = True
        try:
            for k, v in vals.items():
                s = self._spin_boxes.get(k)
                if s and abs(s.value() - v) > 1e-6:
                    s.blockSignals(True); s.setValue(v); s.blockSignals(False)
        finally:
            self._is_syncing_inputs = False

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
        dims = self.drawing_widget._dims
        default_name = f"{dims.coil_unique_id}-RP.png"
        fp, _ = QFileDialog.getSaveFileName(
            self, "Export Return Bend Plate", default_name, "PNG Image (*.png)"
        )
        if not fp:
            return
        if not fp.lower().endswith(".png"):
            fp += ".png"
        if not self.drawing_widget.export_png(fp):
            QMessageBox.warning(self, "Export Failed", "Could not save PNG.")

    def _export_dxf(self) -> None:
        dims = self.drawing_widget._dims
        default_name = f"{dims.coil_unique_id}-RP.dxf"
        fp, _ = QFileDialog.getSaveFileName(
            self, "Export Return Bend Plate DXF", default_name, "DXF Files (*.dxf)"
        )
        if not fp:
            return
        if not fp.lower().endswith(".dxf"):
            fp += ".dxf"
        if not self.drawing_widget.export_dxf(fp):
            QMessageBox.warning(
                self, "Export Failed",
                "Could not save DXF.\n\n"
                "Make sure ezdxf is installed:\n"
                "  pip install --upgrade ezdxf"
            )


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Coil Helvix - Return Bend Plate")
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

import math
import sys
import json
from dataclasses import dataclass, fields
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPolygonF, QPainterPath
from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
from PyQt6.QtWidgets import (
    QApplication, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
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


# ═══════════════════════════════════════════════════════════════════
#  Formulas
# ═══════════════════════════════════════════════════════════════════

def bp_width(coil_w, bottom_plate, first_bend, sheet_t):
    """Width = Coil Width + 2 * ((BP + FB) - (4 * t))"""
    return coil_w + 2.0 * ((bottom_plate + first_bend) - (4.0 * sheet_t))


def bp_height(fin_length, num_splits, bottom_plate, sheet_t):
    """Height = (Fin Length / Splits - (Splits-2)*t) + 2*BP - 4*t"""
    splits = max(1, num_splits)
    return (fin_length / splits - (splits - 2) * sheet_t) + (2.0 * bottom_plate) - (4.0 * sheet_t)


def bp_circle_x(bottom_plate, first_bend, sheet_t):
    """Circle X offset = 20 + (BP - 2t) + (FB - 2t)"""
    return 20.0 + (bottom_plate - 2.0 * sheet_t) + (first_bend - 2.0 * sheet_t)


def bp_hole_pitch(total_width, circle_x):
    """Pitch = (Width - 2 * circle_x) / 4  (5 holes, 4 gaps)"""
    return (total_width - 2.0 * circle_x) / 4.0


def bp_notch_width(bottom_plate, first_bend, sheet_t):
    """Corner notch W = (BP + FB) - 3*t"""
    return (bottom_plate + first_bend) - 3.0 * sheet_t


def bp_notch_height(bottom_plate, sheet_t):
    """Corner notch H = BP - t"""
    return bottom_plate - sheet_t


# ═══════════════════════════════════════════════════════════════════
#  DXF Painter Adapter
# ═══════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════
#  Drawing Widget
# ═══════════════════════════════════════════════════════════════════

class BottomPlateWidget(QWidget):
    BG        = QColor("#f5f5f5")
    LINE_COL  = QColor("#111111")
    DIM_COL   = QColor("#e06000")
    HOLE_COL  = QColor("#cc2222")
    NOTCH_COL = QColor("#555555")
    DASH_COL  = QColor("#888888")
    LINE_W    = 1.6
    DIM_W     = 1.0

    def __init__(self):
        super().__init__()
        self._vals = {}
        self._zoom = 1.0
        self._pan = QPointF(0, 0)
        self._panning = False
        self._last_pan = None
        self.setMinimumSize(500, 480)
        self.update_values(
            coil_w=280, bottom_plate=15, first_bend=12,
            fin_length=2200, num_splits=3, sheet_t=1.5,
            coil_id="25001232"
        )

    def update_values(self, **kw):
        self._vals = kw
        self.update()

    # ── Qt events ──────────────────────────────────────────────────

    def paintEvent(self, _):
        p = QPainter(self)
        self._render(p, QRectF(self.rect()), self.BG, True)

    def wheelEvent(self, e):
        delta = e.angleDelta().y()
        if not delta:
            return
        factor = 1.12 if delta > 0 else 1.0 / 1.12
        old = self._zoom
        self._zoom = max(0.15, min(self._zoom * factor, 8.0))
        if abs(self._zoom - old) < 1e-6:
            return
        cur = e.position()
        sc, ox, oy = self._transform(QRectF(self.rect()), True)
        wx = (cur.x() - ox) / sc
        wy = (cur.y() - oy) / sc
        sc2, ox2, oy2 = self._transform(QRectF(self.rect()), True)
        self._pan += QPointF(cur.x() - (ox2 + wx * sc2),
                             cur.y() - (oy2 + wy * sc2))
        self.update()
        e.accept()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._panning = True
            self._last_pan = e.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if self._panning and self._last_pan:
            d = e.position() - self._last_pan
            self._pan += QPointF(d.x(), d.y())
            self._last_pan = e.position()
            self.update()

    def mouseReleaseEvent(self, e):
        self._panning = False
        self._last_pan = None
        self.unsetCursor()

    def zoom_by(self, f):
        self._zoom = max(0.15, min(self._zoom * f, 8.0))
        self.update()

    def reset_view(self):
        self._zoom = 1.0
        self._pan = QPointF(0, 0)
        self.update()

    def zoom_pct(self):
        return int(round(self._zoom * 100))

    # ── Layout ─────────────────────────────────────────────────────

    def _layout(self):
        v = self._vals
        W     = bp_width(v["coil_w"], v["bottom_plate"], v["first_bend"], v["sheet_t"])
        H     = bp_height(v["fin_length"], v["num_splits"], v["bottom_plate"], v["sheet_t"])
        cx    = bp_circle_x(v["bottom_plate"], v["first_bend"], v["sheet_t"])
        pitch = bp_hole_pitch(W, cx)
        nw    = bp_notch_width(v["bottom_plate"], v["first_bend"], v["sheet_t"])
        nh    = bp_notch_height(v["bottom_plate"], v["sheet_t"])
        margin_left = 80.0
        margin_top  = 60.0
        return dict(
            W=W, H=H, cx=cx, pitch=pitch, nw=nw, nh=nh,
            bp=v["bottom_plate"], coil_id=v["coil_id"],
            ox=margin_left, oy=margin_top,
            world_w=margin_left + W + 200.0,
            world_h=margin_top  + H + 250.0,
        )

    def _transform(self, rect, apply_view):
        L   = self._layout()
        m   = 55.0
        aw  = max(10, rect.width()  - 2*m)
        ah  = max(10, rect.height() - 2*m)
        fit = min(aw / L["world_w"], ah / L["world_h"])
        sc  = fit * self._zoom if apply_view else fit
        px  = self._pan.x() if apply_view else 0.0
        py  = self._pan.y() if apply_view else 0.0
        ox  = rect.x() + (rect.width()  - L["world_w"] * sc) / 2 + px
        oy  = rect.y() + (rect.height() - L["world_h"] * sc) / 2 + py
        return sc, ox, oy

    # ── Rendering ──────────────────────────────────────────────────

    def _render(self, painter, rect, bg, apply_view):
        L = self._layout()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(rect, bg)
        sc, ox, oy = self._transform(rect, apply_view)
        painter.translate(ox, oy)
        painter.scale(sc, sc)
        # shift drawing origin to plate top-left
        painter.translate(L["ox"], L["oy"])
        self._draw(painter, L)
        painter.restore()

    def _draw(self, p, L):
        W, H, bp = L["W"], L["H"], L["bp"]
        cx, pitch = L["cx"], L["pitch"]
        nw, nh = L["nw"], L["nh"]

        obj_pen = QPen(self.LINE_COL, self.LINE_W)
        dim_pen = QPen(self.DIM_COL,  self.DIM_W)

        # Outer rectangle
        p.setPen(obj_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(0, 0, W, H))

        # Dashed plate lines
        dash_pen = QPen(self.DASH_COL, 0.7)
        dash_pen.setStyle(Qt.PenStyle.DashLine)
        dash_pen.setDashPattern([6.0, 4.0])
        p.setPen(dash_pen)
        p.drawLine(QPointF(0, bp),   QPointF(W, bp))
        p.drawLine(QPointF(0, H-bp), QPointF(W, H-bp))

        # Corner notch rectangles
        p.setPen(QPen(self.NOTCH_COL, 1.0))
        p.setBrush(QColor("#555555"))
        for rx, ry in [(0,0),(W-nw,0),(0,H-nh),(W-nw,H-nh)]:
            p.drawRect(QRectF(rx, ry, nw, nh))

        # Re-draw outer border on top
        p.setPen(obj_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(0, 0, W, H))

        # Holes – 5 top + 5 bottom
        hole_r = 3.0
        hole_xs = [cx + i * pitch for i in range(5)]
        p.setPen(QPen(self.HOLE_COL, 1.1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for hx in hole_xs:
            for hy in [bp / 2.0, H - bp / 2.0]:
                p.drawEllipse(QPointF(hx, hy), hole_r, hole_r)

        # Dimensions
        p.setPen(dim_pen)
        p.setFont(QFont("Arial", 10))
        self._dim_h(p, 0, W, 0, -30, f"{W:.1f}")
        self._dim_v(p, 0, H, W, 32,  f"{H:.1f}")
        self._dim_h(p, W-nw, W, 0, -50, f"{nw:.1f}")
        self._dim_v(p, 0, nh, W, 65, f"{nh:.1f}")

        # Formula annotation
        p.setPen(dim_pen)
        p.setFont(QFont("Arial", 8))
        v = self._vals
        splits = max(1, v['num_splits'])
        ann1 = (f"W = {v['coil_w']:.0f} + 2×(({v['bottom_plate']:.0f}+{v['first_bend']:.0f})"
                f"−4×{v['sheet_t']:.1f}) = {W:.1f} mm")
        ann2 = (f"H = ({v['fin_length']:.0f}÷{splits}−({splits}−2)×{v['sheet_t']:.1f})"
                f"+2×{v['bottom_plate']:.0f}−4×{v['sheet_t']:.1f} = {H:.1f} mm")
        p.drawText(QRectF(0, -24, W, 12), Qt.AlignmentFlag.AlignCenter, ann1)
        p.drawText(QRectF(0, -11, W, 12), Qt.AlignmentFlag.AlignCenter, ann2)

        # View label
        p.setPen(obj_pen)
        p.setFont(QFont("Arial", 12))
        label   = f"BOTTOM PLATE  ({L['coil_id']}-BP)"
        label_r = QRectF(0, H + 18, W, 24)
        p.drawText(label_r, Qt.AlignmentFlag.AlignCenter, label)
        lw  = min(W * 0.3, 130.0)
        ly  = label_r.y() + label_r.height() - 2
        cx_ = W / 2
        p.drawLine(QPointF(cx_ - lw/2, ly), QPointF(cx_ + lw/2, ly))

    # ── Dimension helpers ───────────────────────────────────────────

    def _dim_h(self, p, x1, x2, y_ref, offset, label):
        y = y_ref + offset
        p.drawLine(QPointF(x1, y_ref), QPointF(x1, y))
        p.drawLine(QPointF(x2, y_ref), QPointF(x2, y))
        p.drawLine(QPointF(x1, y),     QPointF(x2, y))
        self._arrow(p, QPointF(x1, y), (-1, 0))
        self._arrow(p, QPointF(x2, y), ( 1, 0))
        ty = y - 18 if offset < 0 else y + 4
        p.drawText(QRectF(x1, ty, max(10, x2-x1), 16),
                   Qt.AlignmentFlag.AlignCenter, label)

    def _dim_v(self, p, y1, y2, x_ref, offset, label):
        x = x_ref + offset
        p.drawLine(QPointF(x_ref, y1), QPointF(x, y1))
        p.drawLine(QPointF(x_ref, y2), QPointF(x, y2))
        p.drawLine(QPointF(x, y1),     QPointF(x, y2))
        self._arrow(p, QPointF(x, y1), (0, -1))
        self._arrow(p, QPointF(x, y2), (0,  1))
        span = max(0.1, y2 - y1)
        tx = x + 12
        ty = y1 - 14 if span <= 22 else (y1 + y2) / 2
        p.save()
        p.translate(tx, ty)
        p.rotate(-90)
        p.drawText(QRectF(-25, -8, 50, 16), Qt.AlignmentFlag.AlignCenter, label)
        p.restore()

    def _arrow(self, p, tip, direction, size=7.0):
        dx, dy = direction
        ln = math.hypot(dx, dy)
        if ln == 0:
            return
        dx /= ln; dy /= ln
        px_, py_ = -dy, dx
        p1 = QPointF(tip.x() - dx*size + px_*size*0.4,
                     tip.y() - dy*size + py_*size*0.4)
        p2 = QPointF(tip.x() - dx*size - px_*size*0.4,
                     tip.y() - dy*size - py_*size*0.4)
        ob = p.brush()
        p.setBrush(p.pen().color())
        p.drawPolygon(QPolygonF([tip, p1, p2]))
        p.setBrush(ob)

    # ── Export ─────────────────────────────────────────────────────

    def export_png(self, path: str) -> bool:
        L  = self._layout()
        iw = int(max(1000, L["W"] * 4 + 400))
        ih = int(max(800,  L["H"] * 3 + 400))
        img = QImage(iw, ih, QImage.Format.Format_ARGB32)
        img.fill(QColor("white"))
        painter = QPainter(img)
        self._render(painter, QRectF(0, 0, iw, ih), QColor("white"), False)
        painter.end()
        return img.save(path)

    def export_dxf(self, path: str) -> bool:
        """Export the bottom-plate drawing to a DXF file (mm units)."""
        try:
            L             = self._layout()
            canvas_height = L["world_h"]
            adapter       = DxfPainterAdapter(path, canvas_height)

            # Replicate _render: translate to plate origin, scale=1 (real mm)
            adapter.translate(L["ox"], L["oy"])
            self._draw(adapter, L)

            # Write metadata
            adapter.write_metadata({k: v for k, v in self._vals.items()
                                    if isinstance(v, (int, float, str, bool))})
            adapter.save_to_file()
            return True
        except Exception as exc:
            print(f"DXF Export Error: {exc}")
            return False


# ═══════════════════════════════════════════════════════════════════
#  Main Window
# ═══════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Coil Helvix – Bottom Plate")
        self.resize(1100, 720)
        self._spins: dict[str, QDoubleSpinBox] = {}
        self._texts: dict[str, QLineEdit]      = {}
        self._syncing = False
        self.drawing  = BottomPlateWidget()
        self._zoom_lbl = QLabel("100%")
        self._derived_labels: dict[str, QLabel] = {}
        self._build_ui()
        self._apply()

    def _build_ui(self):
        sp = QSplitter(Qt.Orientation.Horizontal)
        sp.addWidget(self._build_panel())
        sp.addWidget(self.drawing)
        sp.setStretchFactor(1, 1)
        sp.setSizes([300, 780])
        self.setCentralWidget(sp)

    def _build_panel(self):
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        # Inputs
        g = QGroupBox("Bottom Plate Inputs")
        f = QFormLayout(g)
        self._spin(f, "coil_w",       "Coil Width (mm)",             280,  50,  5000, 1)
        self._spin(f, "bottom_plate", "Bottom Plate (mm)",            15,   5,   500, 1)
        self._spin(f, "first_bend",   "First Bend – BP (mm)",         12,   0,   200, 1)
        self._spin(f, "fin_length",   "Fin Length (mm)",            2200, 100, 10000, 1)
        self._spin(f, "num_splits",   "No. of Splits",                 3,   1,    20, 0)
        self._spin(f, "sheet_t",      "Sheet Thickness (mm)",        1.5, 0.5,    10, 2)
        self._text(f, "coil_id",      "Coil Unique ID",         "25001232")
        lay.addWidget(g)

        # Computed
        g2 = QGroupBox("Computed")
        f2 = QFormLayout(g2)
        for key, lbl in [
            ("width",   "Width"),
            ("height",  "Height"),
            ("circ_x",  "Circle X offset"),
            ("pitch",   "Hole pitch"),
            ("notch_w", "Corner notch W"),
            ("notch_h", "Corner notch H"),
        ]:
            lb = QLabel("—")
            self._derived_labels[key] = lb
            f2.addRow(lbl, lb)
        lay.addWidget(g2)

        # Buttons
        btn_row = QHBoxLayout()
        for lbl, slot in [
            ("Apply",      self._apply),
            ("Reset",      self._reset),
            ("Print",      self._print),
            ("Export PNG", self._export_png),
            ("Export DXF", self._export_dxf),   # ← new
        ]:
            b = QPushButton(lbl); b.clicked.connect(slot); btn_row.addWidget(b)
        lay.addLayout(btn_row)

        # Zoom
        zoom_row = QHBoxLayout()
        for lbl, fn in [("−", lambda: self._zoom(-1)),
                        ("+", lambda: self._zoom( 1)),
                        ("Reset View", self._zoom_reset)]:
            b = QPushButton(lbl); b.clicked.connect(fn); zoom_row.addWidget(b)
        self._zoom_lbl.setMinimumWidth(50)
        self._zoom_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zoom_row.addWidget(self._zoom_lbl)
        lay.addLayout(zoom_row)
        lay.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.setMinimumWidth(290)
        return scroll

    # ── Widget factories ───────────────────────────────────────────

    def _spin(self, form, key, label, default, mn, mx, dec):
        s = QDoubleSpinBox()
        s.setDecimals(dec); s.setRange(mn, mx); s.setValue(default)
        s.setSingleStep(1.0); s.setKeyboardTracking(False)
        s.valueChanged.connect(self._apply)
        self._spins[key] = s; form.addRow(label, s)

    def _text(self, form, key, label, default):
        t = QLineEdit(default)
        t.textChanged.connect(self._apply)
        self._texts[key] = t; form.addRow(label, t)

    # ── Apply ──────────────────────────────────────────────────────

    def _apply(self):
        if self._syncing:
            return
        v = {k: s.value() for k, s in self._spins.items()}
        v["coil_id"] = self._texts["coil_id"].text().strip() or "COIL"

        W  = bp_width(v["coil_w"], v["bottom_plate"], v["first_bend"], v["sheet_t"])
        H  = bp_height(v["fin_length"], int(v["num_splits"]), v["bottom_plate"], v["sheet_t"])
        cx = bp_circle_x(v["bottom_plate"], v["first_bend"], v["sheet_t"])
        pt = bp_hole_pitch(W, cx)
        nw = bp_notch_width(v["bottom_plate"], v["first_bend"], v["sheet_t"])
        nh = bp_notch_height(v["bottom_plate"], v["sheet_t"])

        self._derived_labels["width"].setText(f"{W:.1f} mm")
        self._derived_labels["height"].setText(f"{H:.1f} mm")
        self._derived_labels["circ_x"].setText(f"{cx:.1f} mm")
        self._derived_labels["pitch"].setText(f"{pt:.1f} mm")
        self._derived_labels["notch_w"].setText(f"{nw:.1f} mm")
        self._derived_labels["notch_h"].setText(f"{nh:.1f} mm")

        self.drawing.update_values(**v)
        self._zoom_lbl.setText(f"{self.drawing.zoom_pct()}%")

    def _reset(self):
        defaults = dict(coil_w=280, bottom_plate=15, first_bend=12,
                        fin_length=2200, num_splits=3, sheet_t=1.5)
        self._syncing = True
        for k, val in defaults.items():
            s = self._spins.get(k)
            if s:
                s.blockSignals(True); s.setValue(val); s.blockSignals(False)
        self._syncing = False
        self._texts["coil_id"].setText("25001232")
        self._apply()

    # ── Zoom ───────────────────────────────────────────────────────

    def _zoom(self, d):
        self.drawing.zoom_by(1.15 if d > 0 else 1.0/1.15)
        self._zoom_lbl.setText(f"{self.drawing.zoom_pct()}%")

    def _zoom_reset(self):
        self.drawing.reset_view()
        self._zoom_lbl.setText(f"{self.drawing.zoom_pct()}%")

    # ── Print / Export ─────────────────────────────────────────────

    def _print(self):
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        painter = QPainter(printer)
        self.drawing._render(painter, QRectF(painter.viewport()), QColor("white"), False)
        painter.end()

    def _export_png(self):
        coil_id      = self._texts["coil_id"].text().strip() or "COIL"
        default_name = f"{coil_id}-BP.png"
        fp, _ = QFileDialog.getSaveFileName(
            self, "Export PNG", default_name, "PNG Image (*.png)")
        if not fp:
            return
        if not fp.lower().endswith(".png"):
            fp += ".png"
        if not self.drawing.export_png(fp):
            QMessageBox.warning(self, "Export Failed", "Could not save PNG file.")

    def _export_dxf(self):
        coil_id      = self._texts["coil_id"].text().strip() or "COIL"
        default_name = f"{coil_id}-BP.dxf"
        fp, _ = QFileDialog.getSaveFileName(
            self, "Export DXF", default_name, "DXF Files (*.dxf)")
        if not fp:
            return
        if not fp.lower().endswith(".dxf"):
            fp += ".dxf"
        if not self.drawing.export_dxf(fp):
            QMessageBox.warning(
                self, "Export Failed",
                "Could not save DXF.\n\n"
                "Make sure ezdxf is installed:\n"
                "  pip install --upgrade ezdxf",
            )


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Coil Helvix - Bottom Plate")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
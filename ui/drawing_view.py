"""Drawing canvas — renders the full coil layout with zoom & pan."""
from __future__ import annotations
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QWheelEvent, QMouseEvent, QColor
from PySide6.QtWidgets import QWidget

from core.layout_engine import DrawingLayout
from rendering.qt_renderer import QtRenderer


class DrawingView(QWidget):
    """Zoomable / pannable 2-D canvas that paints a DrawingLayout."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(600, 400)
        self.setMouseTracking(True)
        self._layout: DrawingLayout | None = None
        self._scale = 0.45
        self._offset = QPointF(80, 40)
        self._dragging = False
        self._last_pos = QPointF()

    # ── public API ────────────────────────────────────────────────────────
    def set_layout(self, layout: DrawingLayout):
        self._layout = layout
        self.update()

    def get_layout(self) -> DrawingLayout | None:
        return self._layout

    # ── paint ─────────────────────────────────────────────────────────────
    def paintEvent(self, event):
        if self._layout is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#FFFFFF"))

        p.translate(self._offset)
        p.scale(self._scale, self._scale)

        renderer = QtRenderer(p)

        for v in self._layout.views:
            p.save()
            p.translate(v.offset_x, v.offset_y)
            renderer.render_geometry(v.geometry)
            renderer.render_dimensions(v.dimensions)
            p.restore()

            # View label below the view
            r = v.geometry.get("outer_rect", (0, 0, 0, 0))
            renderer.render_view_label(
                v.label,
                v.offset_x + r[0],
                v.offset_y + r[1] + r[3],
                r[2],
            )

        renderer.render_notes(self._layout.notes, *self._layout.notes_offset)
        renderer.render_title_block(
            self._layout.title_block, *self._layout.title_block_offset
        )
        p.end()

    # ── zoom ──────────────────────────────────────────────────────────────
    def wheelEvent(self, event: QWheelEvent):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._scale *= factor
        self._scale = max(0.05, min(self._scale, 10.0))
        self.update()

    # ── pan ───────────────────────────────────────────────────────────────
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._last_pos = event.position()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging:
            delta = event.position() - self._last_pos
            self._offset += delta
            self._last_pos = event.position()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False

"""Qt QPainter renderer — draws geometry dicts produced by the engines."""
from __future__ import annotations
import math
from typing import Any
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QFontMetricsF
from core.dimension_engine import arrowhead_lines

# ── Pens ──────────────────────────────────────────────────────────────────────
_PEN_CASING  = QPen(QColor("#333333"), 0.7, Qt.PenStyle.SolidLine)
_PEN_OBJ     = QPen(QColor("#222222"), 0.5, Qt.PenStyle.SolidLine)
_PEN_FIN     = QPen(QColor("#CC0000"), 0.15, Qt.PenStyle.DashDotLine)
_PEN_TUBE    = QPen(QColor("#008800"), 0.4, Qt.PenStyle.SolidLine)
_PEN_DIM     = QPen(QColor("#FF4400"), 0.25, Qt.PenStyle.SolidLine)
_PEN_EXT     = QPen(QColor("#00CC00"), 0.2, Qt.PenStyle.SolidLine)
_PEN_PLATE   = QPen(QColor("#0055AA"), 0.3, Qt.PenStyle.DashLine)
_PEN_ZONE    = QPen(QColor("#888888"), 0.2, Qt.PenStyle.DashDotLine)
_PEN_PIPE    = QPen(QColor("#222222"), 0.6, Qt.PenStyle.SolidLine)
_PEN_BEND    = QPen(QColor("#666666"), 0.3, Qt.PenStyle.SolidLine)

_FONT_DIM    = QFont("Arial", 7)
_FONT_LABEL  = QFont("Arial", 9, QFont.Weight.Bold)
_FONT_SM     = QFont("Arial", 5)
_FONT_TITLE  = QFont("Arial", 8, QFont.Weight.Bold)
_FONT_CO     = QFont("Arial", 10, QFont.Weight.Bold)
_FONT_NOTE   = QFont("Arial", 6)
_FONT_PIPE   = QFont("Arial", 6, QFont.Weight.Bold)


class QtRenderer:
    def __init__(self, painter: QPainter):
        self._p = painter

    # ── primitives ────────────────────────────────────────────────────────
    def _line(self, x1, y1, x2, y2):
        self._p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def _circle(self, cx, cy, r):
        self._p.drawEllipse(QPointF(cx, cy), r, r)

    def _arc(self, cx, cy, r, start, span):
        self._p.drawArc(QRectF(cx-r, cy-r, 2*r, 2*r), int(start*16), int(span*16))

    def _rect(self, x, y, w, h):
        self._p.drawRect(QRectF(x, y, w, h))

    def _text(self, x, y, s, angle=0.0, font=None, align="center"):
        self._p.save()
        if font:
            self._p.setFont(font)
        self._p.translate(x, y)
        if angle:
            self._p.rotate(-angle)
        fm = QFontMetricsF(self._p.font())
        tw, th = fm.horizontalAdvance(s), fm.height()
        dx = -tw/2 if align == "center" else (0 if align == "left" else -tw)
        self._p.drawText(QPointF(dx, th/4), s)
        self._p.restore()

    # ── composite: geometry ───────────────────────────────────────────────
    def render_geometry(self, geo: dict[str, Any]):
        if "outer_rect" in geo:
            self._p.setPen(_PEN_CASING)
            self._rect(*geo["outer_rect"])
        if "fin_rect" in geo:
            self._p.setPen(_PEN_OBJ)
            self._rect(*geo["fin_rect"])
        if "header_block_rect" in geo:
            self._p.setPen(_PEN_CASING)
            self._rect(*geo["header_block_rect"])
        if "inner_rect" in geo:
            self._p.setPen(_PEN_OBJ)
            self._rect(*geo["inner_rect"])
        if "offset_lines" in geo:
            self._p.setPen(_PEN_PLATE)
            for seg in geo["offset_lines"]:
                self._line(*seg)
        if "fin_lines" in geo:
            self._p.setPen(_PEN_FIN)
            for seg in geo["fin_lines"]:
                self._line(*seg)
        if "tube_lines" in geo:
            self._p.setPen(_PEN_FIN)
            for seg in geo["tube_lines"]:
                self._line(*seg)
        if "zone_lines" in geo:
            self._p.setPen(_PEN_ZONE)
            for seg in geo["zone_lines"]:
                self._line(*seg)
        if "tubes" in geo:
            self._p.setPen(_PEN_TUBE)
            for cx, cy, r in geo["tubes"]:
                self._circle(cx, cy, r)
        if "bend_arcs" in geo:
            self._p.setPen(_PEN_BEND)
            for arc in geo["bend_arcs"]:
                self._arc(*arc)
        if "connection_pipes" in geo:
            for pipe in geo["connection_pipes"]:
                self._p.setPen(_PEN_PIPE)
                self._line(*pipe["line"])
                self._p.setPen(_PEN_DIM)
                self._text(*pipe["label_pos"], pipe["label"], font=_FONT_PIPE)
                self._p.setPen(_PEN_PIPE)
        if "pipe_circles" in geo:
            self._p.setPen(_PEN_PIPE)
            for cx, cy, r in geo["pipe_circles"]:
                self._circle(cx, cy, r)
        if "pipe_stubs" in geo:
            self._p.setPen(_PEN_PIPE)
            for seg in geo["pipe_stubs"]:
                self._line(*seg)
        if "return_rect" in geo:
            self._p.setPen(_PEN_CASING)
            self._rect(*geo["return_rect"])
        if "top_right_box" in geo:
            self._p.setPen(_PEN_CASING)
            self._rect(*geo["top_right_box"])

    # ── composite: dimensions ─────────────────────────────────────────────
    def render_dimensions(self, dims: list[dict]):
        for dim in dims:
            # Extension + dimension lines
            self._p.setPen(_PEN_EXT)
            for seg in dim.get("lines", []):
                self._line(*seg)
            # Arrowheads
            self._p.setPen(_PEN_DIM)
            for tx, ty, a in dim.get("arrows", []):
                for seg in arrowhead_lines(tx, ty, a):
                    self._line(*seg)
            # Dim line (orange)
            lines = dim.get("lines", [])
            if len(lines) >= 3:
                self._p.setPen(_PEN_DIM)
                self._line(*lines[2])  # the actual dimension line
            # Texts
            self._p.setPen(_PEN_DIM)
            for tx, ty, s, a in dim.get("texts", []):
                self._text(tx, ty, s, a, _FONT_DIM)

    # ── notes ─────────────────────────────────────────────────────────────
    def render_notes(self, notes: dict, x: float, y: float):
        self._p.setPen(QPen(QColor("#333333"), 0.3))
        lh = 8.0
        for i, ln in enumerate(notes.get("notes_lines", [])):
            f = _FONT_LABEL if i == 0 else _FONT_NOTE
            self._text(x, y + i * lh, ln, font=f, align="left")
        fy = y + len(notes.get("notes_lines", [])) * lh + 10
        for i, ln in enumerate(notes.get("footer_lines", [])):
            self._text(x, fy + i * lh, ln, font=_FONT_SM, align="left")

    # ── title block ───────────────────────────────────────────────────────
    def render_title_block(self, tb: dict, x: float, y: float):
        self._p.setPen(_PEN_CASING)
        bw, bh = 350.0, 80.0
        self._rect(x, y, bw, bh)
        self._line(x, y+20, x+bw, y+20)
        self._line(x, y+40, x+bw, y+40)
        self._line(x, y+55, x+bw, y+55)
        mx = x + bw * 0.35
        self._line(mx, y, mx, y+40)
        self._p.setPen(QPen(QColor("#333333"), 0.3))
        cx = x + bw * 0.175
        self._text(cx, y+8, tb.get("company_name", ""), font=_FONT_CO)
        self._text(cx, y+16, tb.get("company_sub", ""), font=_FONT_NOTE)
        self._text(cx, y+32, tb.get("company_tag", ""), font=_FONT_SM)
        tx = mx + (bw * 0.65) / 2
        self._text(tx, y+6, "DRAWING TITLE:", font=_FONT_SM)
        self._text(tx, y+16, tb.get("drawing_title", ""), font=_FONT_NOTE)
        self._text(tx, y+32, f"SCALE: {tb.get('scale', 'NTS')}", font=_FONT_SM)
        self._text(x+40, y+48, "DRAWN", font=_FONT_SM)
        self._text(x+120, y+48, "CHECKED", font=_FONT_SM)
        self._text(x+200, y+48, "DATE", font=_FONT_SM)
        self._text(x+300, y+48, f"QTY.: {tb.get('qty','')}", font=_FONT_SM)
        self._text(x+40, y+68, "THIRD ANGLE PROJECTION", font=_FONT_SM)

    # ── view label ────────────────────────────────────────────────────────
    def render_view_label(self, label: str, x: float, y: float, w: float):
        self._p.setPen(_PEN_DIM)
        self._text(x + w / 2, y + 12, label, font=_FONT_LABEL)

"""Export drawing to PDF via Qt QPrinter."""
from __future__ import annotations
from PySide6.QtCore import QMarginsF, QSizeF, Qt
from PySide6.QtGui import QPainter, QPageLayout, QPageSize
from PySide6.QtWidgets import QApplication
from PySide6.QtPrintSupport import QPrinter

from core.layout_engine import DrawingLayout
from rendering.qt_renderer import QtRenderer


def export_pdf(layout: DrawingLayout, filepath: str = "coil_output.pdf") -> str:
    """Render the full drawing to a PDF file.  Returns the path written."""
    # Compute bounding box across all views + notes + title block
    min_x, min_y = 1e9, 1e9
    max_x, max_y = -1e9, -1e9

    for v in layout.views:
        r = v.geometry.get("outer_rect", (0, 0, 0, 0))
        x0 = v.offset_x + r[0]
        y0 = v.offset_y + r[1]
        x1 = x0 + r[2]
        y1 = y0 + r[3]
        # Also account for connection pipes extending beyond rect
        for pipe in v.geometry.get("connection_pipes", []):
            ln = pipe["line"]
            x0 = min(x0, v.offset_x + ln[0], v.offset_x + ln[2])
            x1 = max(x1, v.offset_x + ln[0], v.offset_x + ln[2])
        min_x = min(min_x, x0)
        min_y = min(min_y, y0)
        max_x = max(max_x, x1)
        max_y = max(max_y, y1)

    # Notes and title block region
    nx, ny = layout.notes_offset
    tx, ty = layout.title_block_offset
    min_x = min(min_x, nx)
    min_y = min(min_y, ny)
    max_x = max(max_x, tx + 380)
    max_y = max(max_y, ty + 100)

    # Add margin
    margin = 60.0
    total_w = max_x - min_x + 2 * margin
    total_h = max_y - min_y + 2 * margin

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(filepath)

    page_size = QPageSize(QSizeF(total_w, total_h), QPageSize.Unit.Point)
    page_layout = QPageLayout(page_size, QPageLayout.Orientation.Landscape,
                              QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Point)
    printer.setPageLayout(page_layout)

    painter = QPainter()
    if not painter.begin(printer):
        raise RuntimeError("Cannot begin QPainter on QPrinter")

    # Scale so 1 mm in model = 1 point in PDF (approx 0.35mm actual)
    dpi = printer.resolution()
    scale = dpi / 72.0
    painter.scale(scale, scale)

    # Translate so bounding box starts at margin
    painter.translate(margin - min_x, margin - min_y)

    renderer = QtRenderer(painter)

    for v in layout.views:
        painter.save()
        painter.translate(v.offset_x, v.offset_y)
        renderer.render_geometry(v.geometry)
        renderer.render_dimensions(v.dimensions)
        painter.restore()

        # View label below the view rect
        r = v.geometry.get("outer_rect", (0, 0, 0, 0))
        renderer.render_view_label(
            v.label,
            v.offset_x + r[0],
            v.offset_y + r[1] + r[3],
            r[2],
        )

    renderer.render_notes(layout.notes, *layout.notes_offset)
    renderer.render_title_block(layout.title_block, *layout.title_block_offset)

    painter.end()
    return filepath

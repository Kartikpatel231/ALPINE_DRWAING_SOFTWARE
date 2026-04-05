from pathlib import Path

from PyQt6.QtCore import QMarginsF, QSizeF
from PyQt6.QtGui import QFont, QPageLayout, QPageSize, QPdfWriter, QTextDocument
from PyQt6.QtWidgets import QApplication


def generate_pdf() -> Path:
    project_root = Path(__file__).resolve().parents[1]
    source_md = project_root / "PROJECT_DOCUMENTATION.md"
    output_pdf = project_root / "PROJECT_DOCUMENTATION.pdf"

    text = source_md.read_text(encoding="utf-8")

    app = QApplication.instance()
    owns_app = app is None
    if app is None:
        app = QApplication([])

    writer = QPdfWriter(str(output_pdf))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageOrientation(QPageLayout.Orientation.Portrait)
    writer.setPageMargins(QMarginsF(18.0, 18.0, 18.0, 18.0), QPageLayout.Unit.Millimeter)

    document = QTextDocument()
    document.setDefaultFont(QFont("Arial", 10))
    document.setPlainText(text)
    document.setPageSize(QSizeF(writer.width(), writer.height()))
    document.print(writer)

    if owns_app:
        app.quit()

    return output_pdf


def main() -> None:
    output_pdf = generate_pdf()
    print(f"Documentation PDF generated: {output_pdf}")


if __name__ == "__main__":
    main()

"""Parameter input panel — left sidebar of the main window."""
from __future__ import annotations
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QGroupBox,
    QDoubleSpinBox, QSpinBox, QComboBox, QPushButton,
    QLabel, QScrollArea, QMessageBox,
)
from core.parameters import CoilParameters, validate_parameters

TUBE_OD_OPTIONS = {
    "1/4": 6.35, "5/16": 7.9375, "3/8": 9.525, "7/16": 11.1125,
    "1/2": 12.7, "5/8": 15.875, "3/4": 19.05, "7/8": 22.225,
    "1": 25.4,
}


class ParameterPanel(QWidget):
    """Sidebar widget that collects coil parameters and emits a signal."""

    generate_requested = Signal(object)   # CoilParameters
    export_dxf_requested = Signal()
    export_pdf_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(300)
        self._build_ui()

    # ── Build the widget tree ─────────────────────────────────────────────
    def _build_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        container = QWidget()
        root = QVBoxLayout(container)

        # ─ Primary dims ──────────────────────────────────────────────────
        grp1 = QGroupBox("Primary Dimensions")
        form1 = QFormLayout(grp1)

        self.sp_fl = self._dspin(100, 10000, 1330, " mm")
        form1.addRow("Fin Length (FL):", self.sp_fl)

        self.sp_fh = self._dspin(100, 10000, 1400, " mm")
        form1.addRow("Fin Height (FH):", self.sp_fh)

        self.cb_tube_od = QComboBox()
        for k in TUBE_OD_OPTIONS:
            self.cb_tube_od.addItem(f'{k}"', k)
        self.cb_tube_od.setCurrentText('5/8"')
        form1.addRow("Tube OD:", self.cb_tube_od)

        self.sp_nr = self._ispin(1, 20, 6)
        form1.addRow("No. of Rows (NR):", self.sp_nr)

        self.sp_tpr = self._ispin(1, 200, 35)
        form1.addRow("Tubes per Row (TPR):", self.sp_tpr)

        self.sp_fpi = self._ispin(1, 30, 13)
        form1.addRow("Fins per Inch (FPI):", self.sp_fpi)

        self.sp_nc = self._ispin(1, 200, 35)
        form1.addRow("No. of Circuits (NC):", self.sp_nc)

        root.addWidget(grp1)

        # ─ Plate offsets ─────────────────────────────────────────────────
        grp2 = QGroupBox("Plate Offsets")
        form2 = QFormLayout(grp2)

        self.sp_tp = self._dspin(0, 500, 65, " mm")
        form2.addRow("Top Plate:", self.sp_tp)

        self.sp_bp = self._dspin(0, 500, 35, " mm")
        form2.addRow("Bottom Plate:", self.sp_bp)

        root.addWidget(grp2)

        # ─ Casing extensions ─────────────────────────────────────────────
        grp3 = QGroupBox("Casing Extensions")
        form3 = QFormLayout(grp3)

        self.sp_cl = self._dspin(0, 500, 35, " mm")
        form3.addRow("Left (Header):", self.sp_cl)

        self.sp_cr = self._dspin(0, 500, 65, " mm")
        form3.addRow("Right (Return):", self.sp_cr)

        self.sp_ct = self._dspin(0, 500, 15, " mm")
        form3.addRow("Top:", self.sp_ct)

        self.sp_cb = self._dspin(0, 500, 15, " mm")
        form3.addRow("Bottom:", self.sp_cb)

        self.sp_cthk = self._dspin(0.1, 10, 1.5, " mm")
        form3.addRow("Thickness:", self.sp_cthk)

        root.addWidget(grp3)

        # ─ Depth & Connection ────────────────────────────────────────────
        grp4 = QGroupBox("Depth & Connection")
        form4 = QFormLayout(grp4)

        self.sp_cd = self._dspin(10, 2000, 207.6, " mm")
        form4.addRow("Coil Depth:", self.sp_cd)

        self.sp_hd = self._dspin(10, 2000, 320, " mm")
        form4.addRow("Header Depth:", self.sp_hd)

        self.sp_rd = self._dspin(10, 2000, 320, " mm")
        form4.addRow("Return Depth:", self.sp_rd)

        self.cb_conn = QComboBox()
        self.cb_conn.addItems(["LHS", "RHS"])
        form4.addRow("Connection Side:", self.cb_conn)

        self.sp_conn_ext = self._dspin(10, 2000, 170, " mm")
        form4.addRow("Conn. Extension:", self.sp_conn_ext)

        self.sp_conn_gap = self._dspin(10, 1000, 75, " mm")
        form4.addRow("Conn. Gap (IN-OUT):", self.sp_conn_gap)

        self.sp_hdr_block = self._dspin(10, 1000, 180, " mm")
        form4.addRow("Top Header Block:", self.sp_hdr_block)

        self.sp_ret_ext = self._dspin(10, 1000, 145, " mm")
        form4.addRow("Top Return Ext:", self.sp_ret_ext)

        self.sp_top_step = self._dspin(1, 200, 12, " mm")
        form4.addRow("Top Right Step:", self.sp_top_step)

        root.addWidget(grp4)

        # ─ Detail Offsets ───────────────────────────────────────────────
        grp5 = QGroupBox("Detail Offsets")
        form5 = QFormLayout(grp5)

        self.sp_pipe_fit_outer = self._dspin(1, 500, 50, " mm")
        form5.addRow("Pipe Fit Outer Off:", self.sp_pipe_fit_outer)

        self.sp_pipe_fit_inner = self._dspin(1, 500, 25, " mm")
        form5.addRow("Pipe Fit Inner Off:", self.sp_pipe_fit_inner)

        self.sp_pipe_stub_center = self._dspin(1, 500, 50, " mm")
        form5.addRow("Pipe Stub Ctr Off:", self.sp_pipe_stub_center)

        self.sp_pipe_stub_spacing = self._dspin(1, 200, 12, " mm")
        form5.addRow("Pipe Stub Spacing:", self.sp_pipe_stub_spacing)

        self.sp_front_ref_extra = self._dspin(1, 1000, 150, " mm")
        form5.addRow("Front Ref Extra:", self.sp_front_ref_extra)

        root.addWidget(grp5)

        # ─ Buttons ───────────────────────────────────────────────────────
        self.btn_gen = QPushButton("Generate Drawing")
        self.btn_gen.setStyleSheet(
            "QPushButton{background:#0078D4;color:white;padding:8px;"
            "font-weight:bold;border-radius:4px}"
            "QPushButton:hover{background:#005EA2}"
        )
        self.btn_gen.clicked.connect(self._on_generate)
        root.addWidget(self.btn_gen)

        self.btn_dxf = QPushButton("Export DXF")
        self.btn_dxf.clicked.connect(self.export_dxf_requested.emit)
        root.addWidget(self.btn_dxf)

        self.btn_pdf = QPushButton("Export PDF")
        self.btn_pdf.clicked.connect(self.export_pdf_requested.emit)
        root.addWidget(self.btn_pdf)

        root.addStretch()
        scroll.setWidget(container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ── Helpers ───────────────────────────────────────────────────────────
    def _dspin(self, lo, hi, val, suffix=""):
        sb = QDoubleSpinBox()
        sb.setRange(lo, hi)
        sb.setValue(val)
        sb.setDecimals(1)
        sb.setSuffix(suffix)
        return sb

    def _ispin(self, lo, hi, val):
        sb = QSpinBox()
        sb.setRange(lo, hi)
        sb.setValue(val)
        return sb

    # ── Collect values ────────────────────────────────────────────────────
    def _collect_params(self) -> CoilParameters:
        od_key = self.cb_tube_od.currentData()
        return CoilParameters(
            fin_length=self.sp_fl.value(),
            fin_height=self.sp_fh.value(),
            no_of_rows=self.sp_nr.value(),
            tubes_per_row=self.sp_tpr.value(),
            tube_od_inch=od_key,
            tube_diameter=TUBE_OD_OPTIONS[od_key],
            fpi=self.sp_fpi.value(),
            no_of_circuits=self.sp_nc.value(),
            top_plate=self.sp_tp.value(),
            bottom_plate=self.sp_bp.value(),
            casing_left=self.sp_cl.value(),
            casing_right=self.sp_cr.value(),
            casing_top=self.sp_ct.value(),
            casing_bottom=self.sp_cb.value(),
            casing_thickness=self.sp_cthk.value(),
            coil_depth=self.sp_cd.value(),
            header_depth=self.sp_hd.value(),
            return_depth=self.sp_rd.value(),
            connection_side=self.cb_conn.currentText(),
            connection_extension=self.sp_conn_ext.value(),
            connection_vertical_gap=self.sp_conn_gap.value(),
            top_header_block_length=self.sp_hdr_block.value(),
            top_return_extension=self.sp_ret_ext.value(),
            top_right_step=self.sp_top_step.value(),
            top_pipe_fitting_outer_offset=self.sp_pipe_fit_outer.value(),
            top_pipe_fitting_inner_offset=self.sp_pipe_fit_inner.value(),
            top_pipe_stub_center_offset=self.sp_pipe_stub_center.value(),
            top_pipe_stub_spacing=self.sp_pipe_stub_spacing.value(),
            front_left_reference_extra=self.sp_front_ref_extra.value(),
        )

    def _on_generate(self):
        params = self._collect_params()
        errors = validate_parameters(params)
        if errors:
            QMessageBox.warning(self, "Validation Error", "\n".join(errors))
            return
        self.generate_requested.emit(params)

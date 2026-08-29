"""
ui/dialogs/vessel_editor.py — Add / Edit vessel (platform) — 4-tab QDialog.

Tab 1 — Identity & Classification
Tab 2 — Dimensions & Tonnage
Tab 3 — Marine Systems (DP, motion factor, air gap)
Tab 4 — Verification
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QTabWidget, QWidget, QLabel, QLineEdit, QComboBox,
    QDoubleSpinBox, QSpinBox, QCheckBox, QTextEdit,
    QDialogButtonBox, QGroupBox, QDateEdit, QMessageBox, QFrame,
)
from PyQt6.QtCore import Qt, QDate

from core.database import get_connection
from core.utils import m_to_ft, ft_to_m

_M_TO_FT = 3.28084

_HULL_FACTORS = {
    "semisub": 0.78,
    "tlp":     0.82,
    "jackup":  0.92,
    "spar":    0.75,
    "fixed":   1.00,
}
_HULL_DISPLAY = {
    "semisub": "Semi-submersible (DP)",
    "tlp":     "Tension leg (TLP)",
    "jackup":  "Jack-up",
    "spar":    "Spar buoy",
    "fixed":   "Fixed structure",
}
_HULL_KEYS = list(_HULL_DISPLAY.keys())

_PAYLOAD_CLASSES = ["SLV", "SLV/light MLV", "MLV", "Heavy", "Universal"]
_DP_CLASSES = [
    "— (not classified)",
    "DP Class 1 — Single failure not critical to DP",
    "DP Class 2 — Single failure does not cause loss of position",
    "DP Class 3 — Fire or flood does not cause loss of position",
]


def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet("background: #374151;")
    return f


def _hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet("color: #64748b; font-size: 8pt;")
    return lbl


class VesselEditorDialog(QDialog):
    def __init__(self, parent=None, platform_data: dict | None = None,
                 main_window=None):
        super().__init__(parent)
        self._platform_data = platform_data or {}
        self._edit_mode     = bool(platform_data)
        self._main_window   = main_window
        self._syncing       = False   # prevent recursive spinbox sync

        self.setWindowTitle("Edit Vessel" if self._edit_mode else "Add Vessel")
        self.setMinimumWidth(580)
        self.setMinimumHeight(560)
        self.setModal(True)

        self._build()
        if self._edit_mode:
            self._populate(self._platform_data)
        else:
            self._on_hull_changed(self._hull_combo.currentText())

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_tab1(), "Identity & Classification")
        self._tabs.addTab(self._build_tab2(), "Dimensions & Tonnage")
        self._tabs.addTab(self._build_tab3(), "Marine Systems")
        self._tabs.addTab(self._build_tab4(), "Verification")
        root.addWidget(self._tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # TAB 1 — Identity & Classification ───────────────────────────────────────

    def _build_tab1(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(10)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Required")

        self._hull_combo = QComboBox()
        for key, label in _HULL_DISPLAY.items():
            self._hull_combo.addItem(label, key)
        self._hull_combo.currentIndexChanged.connect(
            lambda _: self._on_hull_changed(self._hull_combo.currentData())
        )

        self._payload_combo = QComboBox()
        self._payload_combo.addItems(_PAYLOAD_CLASSES)

        self._class_society_edit = QLineEdit()
        self._class_society_edit.setPlaceholderText("e.g. ABS, DNV GL, Lloyd's Register")

        self._class_notation_edit = QLineEdit()
        self._class_notation_edit.setPlaceholderText("e.g. A1 Offshore Support Vessel")

        self._flag_state_edit = QLineEdit()
        self._imo_edit = QLineEdit()

        self._deploy_yr_spin = QSpinBox()
        self._deploy_yr_spin.setRange(0, 2040)
        self._deploy_yr_spin.setSpecialValueText("Unknown")

        self._abs_edit = QLineEdit()
        self._abs_edit.setPlaceholderText("e.g. ABS Approval in Principle December 2025")

        self._notes1_edit = QTextEdit()
        self._notes1_edit.setFixedHeight(60)

        form.addRow("Vessel name *",         self._name_edit)
        form.addRow("Hull type",             self._hull_combo)
        form.addRow("Payload class",         self._payload_combo)
        form.addRow("Classification society", self._class_society_edit)
        form.addRow("Class notation",        self._class_notation_edit)
        form.addRow("Flag state",            self._flag_state_edit)
        form.addRow("IMO number",            self._imo_edit)
        form.addRow("First deployment yr",   self._deploy_yr_spin)
        form.addRow("ABS/Classification approval", self._abs_edit)
        form.addRow("Notes",                 self._notes1_edit)
        return w

    # TAB 2 — Dimensions & Tonnage ────────────────────────────────────────────

    def _build_tab2(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(12, 12, 12, 12)
        vbox.setSpacing(8)

        vbox.addWidget(_hint(
            "All dimensions stored in metres. Feet values shown for reference."
        ))

        # DIMENSIONS
        dim_group = QGroupBox("Principal Dimensions")
        dim_form  = QFormLayout(dim_group)
        dim_form.setSpacing(8)

        self._loa_m, self._loa_ft   = self._dual_spin(300, "LOA")
        self._beam_m, self._beam_ft = self._dual_spin(100, "Beam")

        dim_form.addRow("Length overall (LOA):", self._dual_row(self._loa_ft, self._loa_m, label_a="ft", label_b="m"))
        dim_form.addRow("Beam (maximum):",        self._dual_row(self._beam_ft, self._beam_m, label_a="ft", label_b="m"))
        vbox.addWidget(dim_group)

        # DRAFT
        draft_group = QGroupBox("Draft")
        draft_form  = QFormLayout(draft_group)
        draft_form.setSpacing(8)

        self._transit_draft_ft, self._transit_draft_m = self._dual_spin_ft_first(50, "TransitDraft")
        self._launch_draft_ft,  self._launch_draft_m  = self._dual_spin_ft_first(50, "LaunchDraft")

        self._draft_change_lbl = QLabel("—")
        self._draft_change_lbl.setStyleSheet("color: #94a3b8;")

        self._mindepth_m_spin = QDoubleSpinBox()
        self._mindepth_m_spin.setRange(0, 5000)
        self._mindepth_m_spin.setDecimals(1)
        self._mindepth_ft_spin = QDoubleSpinBox()
        self._mindepth_ft_spin.setRange(0, 16000)
        self._mindepth_ft_spin.setDecimals(1)
        self._mindepth_m_spin.valueChanged.connect(
            lambda v: self._sync_ft(v, self._mindepth_ft_spin)
        )
        self._mindepth_ft_spin.valueChanged.connect(
            lambda v: self._sync_m(v, self._mindepth_m_spin)
        )

        draft_form.addRow("Transit draft:",
                          self._dual_row(self._transit_draft_ft, self._transit_draft_m,
                                         label_a="ft", label_b="m"))
        draft_form.addRow("", _hint("Hull depth below waterline during tow"))
        draft_form.addRow("Launch (operating) draft:",
                          self._dual_row(self._launch_draft_ft, self._launch_draft_m,
                                         label_a="ft", label_b="m"))
        draft_form.addRow("", _hint("Hull depth at ballasted / operating position"))
        draft_form.addRow("Draft change at ballast:", self._draft_change_lbl)
        draft_form.addRow("Min operating water depth:",
                          self._dual_row(self._mindepth_ft_spin, self._mindepth_m_spin, label_a="ft", label_b="m"))
        draft_form.addRow("", _hint("Default = launch draft × 1.5, user-overridable"))
        vbox.addWidget(draft_group)

        # Wire draft-change label + min-depth auto-fill
        self._launch_draft_m.valueChanged.connect(self._update_draft_change)
        self._transit_draft_m.valueChanged.connect(self._update_draft_change)
        self._launch_draft_m.valueChanged.connect(self._autofill_min_depth)

        # TONNAGE
        ton_group = QGroupBox("Tonnage")
        ton_form  = QFormLayout(ton_group)
        ton_form.setSpacing(8)

        def _tonspin():
            s = QDoubleSpinBox()
            s.setRange(0, 999_999_999)
            s.setDecimals(0)
            s.setSpecialValueText("Unknown")
            s.setSingleStep(100)
            return s

        self._grt_spin   = _tonspin()
        self._nrt_spin   = _tonspin()
        self._pcnt_spin  = _tonspin()
        self._disp_spin  = _tonspin()

        ton_form.addRow("Gross register tonnage (GRT):", self._grt_spin)
        ton_form.addRow("Net register tonnage (NRT):",   self._nrt_spin)
        ton_form.addRow("Panama Canal Net Tonnage:",     self._pcnt_spin)
        ton_form.addRow("", _hint(
            "Used for Panama Canal transit fee calculation if routing through canal"
        ))
        ton_form.addRow("Full load displacement (tonnes):", self._disp_spin)
        vbox.addWidget(ton_group)

        vbox.addStretch()
        return w

    # TAB 3 — Marine Systems ──────────────────────────────────────────────────

    def _build_tab3(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(12, 12, 12, 12)
        vbox.setSpacing(10)

        # DP
        dp_group = QGroupBox("Dynamic Positioning")
        dp_form  = QFormLayout(dp_group)
        dp_form.setSpacing(8)

        self._dp_check = QCheckBox("DP capable")
        self._dp_check.setChecked(True)
        self._dp_check.toggled.connect(self._on_dp_toggled)

        self._dp_class_combo = QComboBox()
        self._dp_class_combo.addItems(_DP_CLASSES)

        self._dp_class_notes_edit = QLineEdit()
        self._dp_class_notes_edit.setPlaceholderText('e.g. "ABS DYNPOS-AUTRO notation"')

        dp_form.addRow("", self._dp_check)
        dp_form.addRow("DP Class:", self._dp_class_combo)
        dp_form.addRow("DP notes:", self._dp_class_notes_edit)
        vbox.addWidget(dp_group)

        # Hull motion factor
        hmf_group = QGroupBox("Hull Motion Factor")
        hmf_form  = QFormLayout(hmf_group)
        hmf_form.setSpacing(8)

        self._mf_spin = QDoubleSpinBox()
        self._mf_spin.setRange(0.50, 1.00)
        self._mf_spin.setDecimals(2)
        self._mf_spin.setSingleStep(0.01)

        hmf_form.addRow("Motion factor:", self._mf_spin)
        hmf_form.addRow("", _hint(
            "Auto-filled from hull type. Applies to Hs and swell only — not to wind."
        ))

        ref_lbl = QLabel(
            "semisub=0.78 · tlp=0.82 · jackup=0.92 · spar=0.75 · fixed=1.00"
        )
        ref_lbl.setStyleSheet("color: #64748b; font-size: 8pt;")
        hmf_form.addRow("Reference:", ref_lbl)

        self._maxhs_spin = QDoubleSpinBox()
        self._maxhs_spin.setRange(0, 20)
        self._maxhs_spin.setDecimals(2)
        hmf_form.addRow("Max operating Hs (m):", self._maxhs_spin)
        vbox.addWidget(hmf_group)

        # Air gap (semisub only)
        self._airgap_group = QGroupBox(
            "Air Gap Specifications — semi-submersible specific"
        )
        ag_form = QFormLayout(self._airgap_group)
        ag_form.setSpacing(8)

        self._airgap_m, self._airgap_ft = self._dual_spin(50, "AirGap")
        self._wavecrest_m, self._wavecrest_ft = self._dual_spin(30, "WaveCrest")
        self._deckelev_m, self._deckelev_ft = self._dual_spin(80, "DeckElev")

        self._clearance_lbl = QLabel("Available clearance: —")
        self._clearance_lbl.setWordWrap(True)

        self._airgap_m.valueChanged.connect(self._update_clearance)
        self._wavecrest_m.valueChanged.connect(self._update_clearance)
        self._deckelev_m.valueChanged.connect(self._update_clearance)

        ag_form.addRow("Minimum air gap:",
                       self._dual_row(self._airgap_ft, self._airgap_m, label_a="ft", label_b="m"))
        ag_form.addRow("", _hint(
            "Clearance between underside of main deck and still water "
            "surface at operating draft. Per DNV-ST-0119 and MODU Code."
        ))
        ag_form.addRow("Max wave crest height:",
                       self._dual_row(self._wavecrest_ft, self._wavecrest_m, label_a="ft", label_b="m"))
        ag_form.addRow("Deck elevation above waterline:",
                       self._dual_row(self._deckelev_ft, self._deckelev_m, label_a="ft", label_b="m"))
        ag_form.addRow("Computed clearance:", self._clearance_lbl)
        vbox.addWidget(self._airgap_group)

        # Also deck area
        misc_form = QFormLayout()
        self._deck_area_spin = QDoubleSpinBox()
        self._deck_area_spin.setRange(0, 100_000)
        self._deck_area_spin.setDecimals(1)
        self._deck_area_spin.setSpecialValueText("Unknown")
        misc_form.addRow("Deck area (m²):", self._deck_area_spin)
        vbox.addLayout(misc_form)

        vbox.addStretch()
        return w

    # TAB 4 — Verification ────────────────────────────────────────────────────

    def _build_tab4(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(12, 12, 12, 12)
        vbox.setSpacing(10)

        self._ver_status_lbl = QLabel()
        self._ver_status_lbl.setWordWrap(True)
        self._ver_status_lbl.setStyleSheet(
            "background: #1e3a5f; border-radius: 4px; padding: 8px; color: #93c5fd;"
        )
        vbox.addWidget(self._ver_status_lbl)

        form = QFormLayout()
        form.setSpacing(10)

        self._ver_check = QCheckBox("Specifications verified")
        self._ver_check.toggled.connect(self._update_ver_status)

        self._ver_source_edit = QLineEdit()
        self._ver_source_edit.setPlaceholderText(
            "e.g. Operator provided 2026-06-27 / ABS survey"
        )

        self._ver_notes_edit = QTextEdit()
        self._ver_notes_edit.setFixedHeight(80)

        form.addRow("", self._ver_check)
        form.addRow("Verified by / source:", self._ver_source_edit)
        form.addRow("Specification notes:",  self._ver_notes_edit)
        vbox.addLayout(form)
        vbox.addStretch()

        self._update_ver_status()
        return w

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _dual_spin(self, hi: float, tag: str) -> tuple[QDoubleSpinBox, QDoubleSpinBox]:
        """Return (metres_spin, feet_spin) pair that sync with each other."""
        m = QDoubleSpinBox(); m.setRange(0, hi); m.setDecimals(2)
        m.setSpecialValueText("Unknown")
        f = QDoubleSpinBox(); f.setRange(0, hi * _M_TO_FT); f.setDecimals(2)
        f.setSpecialValueText("Unknown")
        m.valueChanged.connect(lambda v: self._sync_ft(v, f))
        f.valueChanged.connect(lambda v: self._sync_m(v, m))
        return m, f

    def _dual_spin_ft_first(self, hi: float, tag: str) -> tuple[QDoubleSpinBox, QDoubleSpinBox]:
        """Return (feet_spin, metres_spin) pair."""
        f = QDoubleSpinBox(); f.setRange(0, hi); f.setDecimals(2)
        f.setSpecialValueText("Unknown")
        m = QDoubleSpinBox(); m.setRange(0, hi / _M_TO_FT + 1); m.setDecimals(3)
        m.setSpecialValueText("Unknown")
        f.valueChanged.connect(lambda v: self._sync_m(v, m))
        m.valueChanged.connect(lambda v: self._sync_ft(v, f))
        return f, m

    def _dual_row(self, a: QDoubleSpinBox, b: QDoubleSpinBox,
                  label_a: str = "m", label_b: str = "ft") -> QWidget:
        row = QWidget()
        hl  = QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)
        hl.addWidget(a, 1)
        hl.addWidget(QLabel(label_a))
        hl.addWidget(b, 1)
        hl.addWidget(QLabel(label_b))
        return row

    def _sync_ft(self, m_val: float, ft_spin: QDoubleSpinBox) -> None:
        if self._syncing or m_val == 0:
            return
        self._syncing = True
        ft_spin.setValue(m_to_ft(m_val))
        self._syncing = False

    def _sync_m(self, ft_val: float, m_spin: QDoubleSpinBox) -> None:
        if self._syncing or ft_val == 0:
            return
        self._syncing = True
        m_spin.setValue(ft_to_m(ft_val))
        self._syncing = False

    def _on_hull_changed(self, hull_key: str) -> None:
        factor = _HULL_FACTORS.get(hull_key, 1.00)
        self._mf_spin.setValue(factor)
        is_semi = hull_key == "semisub"
        self._airgap_group.setVisible(is_semi)

    def _on_dp_toggled(self, checked: bool) -> None:
        self._dp_class_combo.setEnabled(checked)
        self._dp_class_notes_edit.setEnabled(checked)

    def _update_draft_change(self) -> None:
        t = self._transit_draft_m.value()
        l = self._launch_draft_m.value()
        if t > 0 and l > 0:
            delta_m  = l - t
            delta_ft = m_to_ft(delta_m)
            self._draft_change_lbl.setText(
                f"{delta_m:.3f} m ({delta_ft:.2f} ft)  "
                f"({'ballast down' if delta_m > 0 else 'de-ballast'})"
            )
        else:
            self._draft_change_lbl.setText("—")

    def _autofill_min_depth(self, launch_m: float) -> None:
        if launch_m > 0 and self._mindepth_m_spin.value() == 0:
            self._mindepth_m_spin.setValue(launch_m * 1.5)

    def _update_clearance(self) -> None:
        de = self._deckelev_m.value()
        wc = self._wavecrest_m.value()
        if de > 0 and wc > 0:
            cl_m  = de - wc
            cl_ft = m_to_ft(cl_m)
            if cl_m >= 0:
                self._clearance_lbl.setText(
                    f"Available clearance = {cl_m:.2f} m ({cl_ft:.1f} ft)"
                )
                self._clearance_lbl.setStyleSheet("color: #86efac;")
            else:
                self._clearance_lbl.setText(
                    f"⚠  Wave crest exceeds deck elevation by {-cl_m:.2f} m "
                    f"({-cl_ft:.1f} ft) — review design basis"
                )
                self._clearance_lbl.setStyleSheet("color: #fca5a5; font-weight: bold;")
        else:
            self._clearance_lbl.setText("Available clearance: —")
            self._clearance_lbl.setStyleSheet("color: #94a3b8;")

    def _update_ver_status(self) -> None:
        if self._ver_check.isChecked():
            self._ver_status_lbl.setText(
                "✓  Specifications verified — source document recorded below."
            )
            self._ver_status_lbl.setStyleSheet(
                "background: #14532d; border-radius: 4px; padding: 8px; color: #86efac;"
            )
        else:
            self._ver_status_lbl.setText(
                "⚠  Specifications not verified — estimated values only. "
                "Check this box when confirmed by official documentation."
            )
            self._ver_status_lbl.setStyleSheet(
                "background: #1e3a5f; border-radius: 4px; padding: 8px; color: #93c5fd;"
            )

    # ── Populate ──────────────────────────────────────────────────────────────

    def _populate(self, d: dict) -> None:
        self._name_edit.setText(d.get("name", ""))
        hull_key = d.get("hull_type", "semisub")
        idx = self._hull_combo.findData(hull_key)
        if idx >= 0:
            self._hull_combo.setCurrentIndex(idx)

        pc = d.get("payload_class") or "MLV"
        pi = self._payload_combo.findText(pc, Qt.MatchFlag.MatchFixedString)
        if pi >= 0:
            self._payload_combo.setCurrentIndex(pi)

        self._class_society_edit.setText(d.get("class_society") or "")
        self._class_notation_edit.setText(d.get("class_notation") or "")
        self._flag_state_edit.setText(d.get("flag_state") or "")
        self._imo_edit.setText(d.get("imo_number") or "")
        self._deploy_yr_spin.setValue(d.get("first_deployment_yr") or 0)
        self._abs_edit.setText(d.get("abs_approval") or "")
        self._notes1_edit.setPlainText(d.get("notes") or "")

        # Tab 2
        self._loa_m.setValue(d.get("loa_m") or 0)
        self._beam_m.setValue(d.get("beam_m") or 0)
        self._transit_draft_ft.setValue(m_to_ft(d["transit_draft_m"]) if d.get("transit_draft_m") else 0)
        self._launch_draft_ft.setValue(m_to_ft(d["launch_draft_m"]) if d.get("launch_draft_m") else 0)
        self._mindepth_m_spin.setValue(d.get("min_depth_m") or 0)
        self._grt_spin.setValue(d.get("grt") or 0)
        self._nrt_spin.setValue(d.get("nrt") or 0)
        self._pcnt_spin.setValue(d.get("panama_canal_tons") or 0)
        self._disp_spin.setValue(d.get("displacement_t") or 0)

        # Tab 3
        self._dp_check.setChecked(bool(d.get("dp_capable", True)))
        dp_cls = d.get("dp_class") or 0
        if isinstance(dp_cls, int) and 1 <= dp_cls <= 3:
            self._dp_class_combo.setCurrentIndex(dp_cls)
        self._dp_class_notes_edit.setText(d.get("dp_class_notes") or "")
        self._mf_spin.setValue(d.get("hull_motion_factor") or 0.78)
        self._maxhs_spin.setValue(d.get("max_hs_operating_m") or 0)
        self._airgap_m.setValue(d.get("min_air_gap_m") or 0)
        self._wavecrest_m.setValue(d.get("max_wave_crest_m") or 0)
        self._deckelev_m.setValue(d.get("deck_elevation_m") or 0)
        self._deck_area_spin.setValue(d.get("deck_area_m2") or 0)

        # Tab 4
        self._ver_check.setChecked(bool(d.get("specs_verified")))
        self._ver_source_edit.setText(d.get("specs_verified_source") or "")
        self._ver_notes_edit.setPlainText(d.get("specs_notes") or "")

        self._on_hull_changed(hull_key)

    # ── Save ──────────────────────────────────────────────────────────────────

    def _on_save(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Vessel name is required.")
            self._tabs.setCurrentIndex(0)
            self._name_edit.setFocus()
            return

        hull_key = self._hull_combo.currentData() or "semisub"
        dp_cls_idx = self._dp_class_combo.currentIndex()   # 0=not classified, 1/2/3=class

        data = dict(
            name=name,
            hull_type=hull_key,
            hull_motion_factor=self._mf_spin.value(),
            dp_capable=int(self._dp_check.isChecked()),
            payload_class=self._payload_combo.currentText(),
            max_hs_operating_m=self._maxhs_spin.value() or None,
            typical_depth_m=None,           # legacy field, left None
            min_depth_m=self._mindepth_m_spin.value() or 50.0,
            abs_approval=self._abs_edit.text().strip() or None,
            first_deployment_yr=self._deploy_yr_spin.value() or None,
            notes=self._notes1_edit.toPlainText().strip() or None,
            # Tab 2
            loa_m=self._loa_m.value() or None,
            beam_m=self._beam_m.value() or None,
            transit_draft_m=self._transit_draft_m.value() or None,
            launch_draft_m=self._launch_draft_m.value() or None,
            grt=self._grt_spin.value() or None,
            nrt=self._nrt_spin.value() or None,
            panama_canal_tons=self._pcnt_spin.value() or None,
            displacement_t=self._disp_spin.value() or None,
            # Tab 3
            dp_class=dp_cls_idx if dp_cls_idx > 0 else None,
            dp_class_notes=self._dp_class_notes_edit.text().strip() or None,
            min_air_gap_m=self._airgap_m.value() or None,
            max_wave_crest_m=self._wavecrest_m.value() or None,
            deck_elevation_m=self._deckelev_m.value() or None,
            deck_area_m2=self._deck_area_spin.value() or None,
            # Tab 4
            specs_verified=int(self._ver_check.isChecked()),
            specs_verified_source=self._ver_source_edit.text().strip() or None,
            specs_notes=self._ver_notes_edit.toPlainText().strip() or None,
            # Classification
            class_society=self._class_society_edit.text().strip() or None,
            class_notation=self._class_notation_edit.text().strip() or None,
            flag_state=self._flag_state_edit.text().strip() or None,
            imo_number=self._imo_edit.text().strip() or None,
        )

        try:
            conn = get_connection()
            if self._edit_mode:
                sets = ", ".join(f"{k}=:{k}" for k in data)
                data["_id"] = self._platform_data["id"]
                conn.execute(f"UPDATE platforms SET {sets} WHERE id=:_id", data)
            else:
                cols = ", ".join(data.keys())
                vals = ", ".join(f":{k}" for k in data)
                conn.execute(f"INSERT INTO platforms ({cols}) VALUES ({vals})", data)
            conn.commit()
            conn.close()
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", str(exc))
            return

        if self._main_window and hasattr(self._main_window, "reload_platforms"):
            self._main_window.reload_platforms()

        self.accept()

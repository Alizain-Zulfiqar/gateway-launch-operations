"""
ui/dialogs/launcher_editor.py — Add / Edit launcher configuration — 2-tab QDialog.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QTabWidget, QWidget, QLabel, QLineEdit, QComboBox,
    QDoubleSpinBox, QSpinBox, QCheckBox, QTextEdit,
    QDialogButtonBox, QGroupBox, QMessageBox,
)
from PyQt6.QtCore import Qt

from core.database import get_connection
from core.utils import m_to_ft, ft_to_m

_M_TO_FT = 3.28084

_LAUNCHER_TYPES = [
    ("rail",            "Rail erector-launcher"),
    ("vertical_fixed",  "Vertical fixed (launch table)"),
    ("vertical_mobile", "Vertical mobile erector (MEL)"),
    ("air_carrier",     "Air carrier / mothership"),
]
_MOUNT_METHODS = [
    ("underslung",    "Underslung — vehicle hangs below erector arm"),
    ("top_mount",     "Top mount — vehicle sits on launch table"),
    ("side_clamp",    "Side clamp — clamped to rail-mounted clamp ring"),
    ("cradle",        "Cradle / trunnion — rocking cradle mount"),
    ("captive_bolt",  "Captive bolt — hold-down bolt pattern release"),
    ("other",         "Other (specify in notes)"),
]
_DATA_SOURCES = [
    "Estimated",
    "ICD",
    "Manufacturer spec",
    "Integration contractor",
    "Range safety doc",
]


def _hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet("color: #64748b; font-size: 8pt;")
    return lbl


class LauncherEditorDialog(QDialog):
    def __init__(self, parent=None, launcher_data: dict | None = None,
                 vehicle_id: int | None = None):
        super().__init__(parent)
        self._launcher_data = launcher_data or {}
        self._edit_mode     = bool(launcher_data)
        self._preset_vid    = vehicle_id

        self.setWindowTitle("Edit Launcher" if self._edit_mode else "Add Launcher")
        self.setMinimumWidth(560)
        self.setMinimumHeight(520)
        self.setModal(True)

        self._syncing:  bool = False
        self._vehicles: list[dict] = []
        self._load_vehicles()
        self._build()
        if self._edit_mode:
            self._populate(self._launcher_data)
        if vehicle_id and not self._edit_mode:
            self._pre_select_vehicle(vehicle_id)

    # ── DB ────────────────────────────────────────────────────────────────────

    def _load_vehicles(self) -> None:
        try:
            conn = get_connection()
            rows = conn.execute(
                "SELECT id, name FROM vehicles ORDER BY name"
            ).fetchall()
            conn.close()
            self._vehicles = [{"id": r["id"], "name": r["name"]} for r in rows]
        except Exception:
            self._vehicles = []

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_tab1(), "Configuration")
        self._tabs.addTab(self._build_tab2(), "Verification")
        root.addWidget(self._tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # TAB 1 ───────────────────────────────────────────────────────────────────

    def _build_tab1(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(12, 12, 12, 12)
        vbox.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText(
            'e.g. "Alpha Rail Erector Mk1", "Falcon 9 TEL"  — Required'
        )

        self._vehicle_combo = QComboBox()
        self._vehicle_combo.addItem("— Generic / multi-vehicle —", None)
        for v in self._vehicles:
            self._vehicle_combo.addItem(v["name"], v["id"])

        self._type_combo = QComboBox()
        for key, label in _LAUNCHER_TYPES:
            self._type_combo.addItem(label, key)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)

        self._mount_combo = QComboBox()
        for key, label in _MOUNT_METHODS:
            self._mount_combo.addItem(label, key)

        form.addRow("Launcher name *:", self._name_edit)
        form.addRow("Associated vehicle:", self._vehicle_combo)
        form.addRow("Launcher type:", self._type_combo)
        form.addRow("Mount method:", self._mount_combo)
        vbox.addLayout(form)

        # Physical specs group
        phys_group = QGroupBox("Physical Specifications")
        pf = QFormLayout(phys_group)
        pf.setSpacing(8)

        def _rspin(hi, dec=2):
            s = QDoubleSpinBox(); s.setRange(0, hi); s.setDecimals(dec)
            s.setSpecialValueText("Unknown")
            return s

        self._base_diam_spin,   self._base_diam_ft   = self._dual_m_ft(_rspin(50),  _rspin(50 * _M_TO_FT))
        self._base_len_spin,    self._base_len_ft     = self._dual_m_ft(_rspin(100), _rspin(100 * _M_TO_FT))
        self._height_spin,      self._height_ft       = self._dual_m_ft(_rspin(200), _rspin(200 * _M_TO_FT))
        self._weight_spin = _rspin(9_999_999, dec=0)

        pf.addRow("Base footprint diameter:", self._dual_row(self._base_diam_ft, self._base_diam_spin))
        pf.addRow("", _hint("Circular diameter or rectangular width"))
        pf.addRow("Base footprint length:", self._dual_row(self._base_len_ft, self._base_len_spin))
        pf.addRow("", _hint("Leave blank if circular footprint"))
        pf.addRow("Launcher height w/o vehicle:", self._dual_row(self._height_ft, self._height_spin))
        pf.addRow("Total weight w/o vehicle (kg):", self._weight_spin)
        vbox.addWidget(phys_group)

        # Vehicle interface
        iface_group = QGroupBox("Vehicle Interface")
        ifm = QFormLayout(iface_group)
        ifm.setSpacing(8)
        self._holddown_edit  = QLineEdit()
        self._holddown_edit.setPlaceholderText('e.g. "4-bolt 3.0 m diameter pattern"')
        self._umbilical_spin = QSpinBox()
        self._umbilical_spin.setRange(0, 20)
        ifm.addRow("Hold-down pattern:", self._holddown_edit)
        ifm.addRow("Umbilical connections:", self._umbilical_spin)
        vbox.addWidget(iface_group)

        # Marine platform requirements
        marine_group = QGroupBox("Marine Platform Requirements")
        mm = QFormLayout(marine_group)
        mm.setSpacing(8)

        self._deck_load_spin = _rspin(500)
        self._deck_load_spin.setToolTip(
            "Distributed load on deck surface from launcher structure (kPa). "
            "Verify against platform deck load capacity."
        )
        self._min_deck_spin  = _rspin(50_000, dec=1)

        # Rail-specific (hidden unless rail type)
        self._rail_widget = QWidget()
        rw = QFormLayout(self._rail_widget)
        rw.setContentsMargins(0, 0, 0, 0)
        self._rail_gauge_spin, self._rail_gauge_ft = self._dual_m_ft(_rspin(5),   _rspin(5 * _M_TO_FT))
        self._rail_run_spin,   self._rail_run_ft   = self._dual_m_ft(_rspin(300), _rspin(300 * _M_TO_FT))
        rw.addRow("Rail gauge:", self._dual_row(self._rail_gauge_ft, self._rail_gauge_spin))
        rw.addRow("Required rail run length:", self._dual_row(self._rail_run_ft, self._rail_run_spin))

        mm.addRow("Deck loading (kPa):", self._deck_load_spin)
        mm.addRow("",                    self._rail_widget)
        mm.addRow("Min clear deck area (m²):", self._min_deck_spin)
        vbox.addWidget(marine_group)

        # Launch envelope
        env_group = QGroupBox("Launch Envelope")
        ev = QFormLayout(env_group)
        ev.setSpacing(8)
        self._blast_spin, self._blast_ft = self._dual_m_ft(_rspin(1000, dec=0), _rspin(1000 * _M_TO_FT, dec=0))
        self._az_min_spin   = _rspin(360, dec=1)
        self._az_max_spin   = _rspin(360, dec=1)
        ev.addRow("Blast exclusion radius:", self._dual_row(self._blast_ft, self._blast_spin))
        ev.addRow("Min launch azimuth (°):", self._az_min_spin)
        ev.addRow("Max launch azimuth (°):", self._az_max_spin)
        ev.addRow("", _hint(
            "Azimuth range defines the arc of launch directions achievable "
            "from the platform deck layout. Used in orbit access analysis."
        ))
        vbox.addWidget(env_group)

        self._notes_edit = QTextEdit()
        self._notes_edit.setFixedHeight(60)
        vbox.addWidget(QLabel("Notes:"))
        vbox.addWidget(self._notes_edit)
        vbox.addStretch()

        self._on_type_changed(0)
        return w

    # TAB 2 ───────────────────────────────────────────────────────────────────

    def _build_tab2(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(10)

        self._ver_check = QCheckBox("Specifications verified")

        self._ver_source_edit = QLineEdit()
        self._ver_source_edit.setPlaceholderText(
            "e.g. Manufacturer ICD Rev B 2025-03"
        )

        self._datasource_combo = QComboBox()
        self._datasource_combo.addItems(_DATA_SOURCES)

        self._spec_notes_edit = QTextEdit()
        self._spec_notes_edit.setFixedHeight(80)

        form.addRow("", self._ver_check)
        form.addRow("Verified source:", self._ver_source_edit)
        form.addRow("Data source:", self._datasource_combo)
        form.addRow("Specification notes:", self._spec_notes_edit)
        return w

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _dual_m_ft(self, m_spin: QDoubleSpinBox, ft_spin: QDoubleSpinBox
                   ) -> tuple[QDoubleSpinBox, QDoubleSpinBox]:
        """Wire m↔ft sync and return (m_spin, ft_spin)."""
        m_spin.valueChanged.connect(lambda v: self._sync_ft(v, ft_spin))
        ft_spin.valueChanged.connect(lambda v: self._sync_m(v, m_spin))
        return m_spin, ft_spin

    def _dual_row(self, first: QDoubleSpinBox, second: QDoubleSpinBox,
                  label_a: str = "ft", label_b: str = "m") -> QWidget:
        row = QWidget()
        hl  = QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)
        hl.addWidget(first, 1)
        hl.addWidget(QLabel(label_a))
        hl.addWidget(second, 1)
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

    # ── Behaviour ─────────────────────────────────────────────────────────────

    def _on_type_changed(self, idx: int) -> None:
        is_rail = self._type_combo.currentData() == "rail"
        self._rail_widget.setVisible(is_rail)

    def _pre_select_vehicle(self, vehicle_id: int) -> None:
        for i in range(self._vehicle_combo.count()):
            if self._vehicle_combo.itemData(i) == vehicle_id:
                self._vehicle_combo.setCurrentIndex(i)
                return

    def _populate(self, d: dict) -> None:
        self._name_edit.setText(d.get("launcher_name", ""))
        # vehicle
        vid = d.get("vehicle_id")
        if vid:
            for i in range(self._vehicle_combo.count()):
                if self._vehicle_combo.itemData(i) == vid:
                    self._vehicle_combo.setCurrentIndex(i)
                    break
        # type
        lt = d.get("launcher_type", "vertical_fixed")
        for i in range(self._type_combo.count()):
            if self._type_combo.itemData(i) == lt:
                self._type_combo.setCurrentIndex(i)
                break
        # mount
        mm = d.get("mount_method", "other")
        for i in range(self._mount_combo.count()):
            if self._mount_combo.itemData(i) == mm:
                self._mount_combo.setCurrentIndex(i)
                break
        self._base_diam_spin.setValue(d.get("base_diameter_m") or 0)
        self._base_len_spin.setValue(d.get("base_length_m") or 0)
        self._height_spin.setValue(d.get("launcher_height_m") or 0)
        self._weight_spin.setValue(d.get("total_weight_kg") or 0)
        self._holddown_edit.setText(d.get("hold_down_pattern") or "")
        self._umbilical_spin.setValue(d.get("umbilical_count") or 0)
        self._deck_load_spin.setValue(d.get("deck_load_kpa") or 0)
        self._rail_gauge_spin.setValue(d.get("rail_gauge_m") or 0)
        self._rail_run_spin.setValue(d.get("rail_length_m") or 0)
        self._min_deck_spin.setValue(d.get("min_deck_area_m2") or 0)
        self._blast_spin.setValue(d.get("blast_radius_m") or 0)
        self._az_min_spin.setValue(d.get("launch_azimuth_min_deg") or 0)
        self._az_max_spin.setValue(d.get("launch_azimuth_max_deg") or 0)
        self._notes_edit.setPlainText(d.get("notes") or "")
        self._ver_check.setChecked(bool(d.get("specs_verified")))
        self._ver_source_edit.setText(d.get("specs_verified_source") or "")
        ds = d.get("data_source", "Estimated")
        idx = self._datasource_combo.findText(ds, Qt.MatchFlag.MatchFixedString)
        if idx >= 0:
            self._datasource_combo.setCurrentIndex(idx)
        self._spec_notes_edit.setPlainText(d.get("specs_notes") or "")

    # ── Save ──────────────────────────────────────────────────────────────────

    def _on_save(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Launcher name is required.")
            self._tabs.setCurrentIndex(0)
            self._name_edit.setFocus()
            return

        vid = self._vehicle_combo.currentData()
        data = dict(
            launcher_name=name,
            vehicle_id=vid,
            launcher_type=self._type_combo.currentData(),
            mount_method=self._mount_combo.currentData(),
            base_diameter_m=self._base_diam_spin.value() or None,
            base_length_m=self._base_len_spin.value() or None,
            launcher_height_m=self._height_spin.value() or None,
            total_weight_kg=self._weight_spin.value() or None,
            hold_down_pattern=self._holddown_edit.text().strip() or None,
            umbilical_count=self._umbilical_spin.value() or None,
            deck_load_kpa=self._deck_load_spin.value() or None,
            rail_gauge_m=self._rail_gauge_spin.value() or None,
            rail_length_m=self._rail_run_spin.value() or None,
            min_deck_area_m2=self._min_deck_spin.value() or None,
            blast_radius_m=self._blast_spin.value() or None,
            launch_azimuth_min_deg=self._az_min_spin.value() or None,
            launch_azimuth_max_deg=self._az_max_spin.value() or None,
            notes=self._notes_edit.toPlainText().strip() or None,
            specs_verified=int(self._ver_check.isChecked()),
            specs_verified_source=self._ver_source_edit.text().strip() or None,
            data_source=self._datasource_combo.currentText(),
            specs_notes=self._spec_notes_edit.toPlainText().strip() or None,
        )

        try:
            conn = get_connection()
            if self._edit_mode:
                sets = ", ".join(f"{k}=:{k}" for k in data)
                data["_id"] = self._launcher_data["id"]
                conn.execute(f"UPDATE launcher_configs SET {sets} WHERE id=:_id", data)
            else:
                cols = ", ".join(data.keys())
                vals = ", ".join(f":{k}" for k in data)
                conn.execute(
                    f"INSERT INTO launcher_configs ({cols}) VALUES ({vals})", data
                )
            conn.commit()
            conn.close()
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", str(exc))
            return

        self.accept()

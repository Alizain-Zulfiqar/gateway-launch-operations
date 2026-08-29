"""
ui/dialogs/vehicle_editor.py — Add / Edit vehicle dialog (5-tab QDialog).
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QTabWidget, QWidget, QLabel, QLineEdit, QComboBox,
    QDoubleSpinBox, QSpinBox, QCheckBox, QTextEdit,
    QDialogButtonBox, QPushButton, QFrame, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from core.database import get_connection

# ── Class defaults (from CLAUDE.md) ──────────────────────────────────────────

# Keyed by size bucket (see _cat_key), NOT by vehicle_class. Each entry now also
# carries direction-tolerance defaults (wdtol/sdtol/swtol, degrees) so
# "Reset to class defaults" restores all eight threshold spinboxes, not just five.
_CAT_DEFAULTS: dict[str, dict] = {
    "small":   dict(wind=18, gust=25, hs=1.5, swh=2.0, swp=12, wdtol=30.0, sdtol=60.0, swtol=60.0),
    "medium":  dict(wind=25, gust=35, hs=2.0, swh=2.5, swp=14, wdtol=45.0, sdtol=75.0, swtol=75.0),
    "heavy":   dict(wind=30, gust=42, hs=2.5, swh=3.0, swp=15, wdtol=45.0, sdtol=75.0, swtol=75.0),
    "super":   dict(wind=35, gust=50, hs=3.0, swh=3.5, swp=16, wdtol=45.0, sdtol=75.0, swtol=75.0),
    "suborbital": dict(wind=20, gust=28, hs=1.8, swh=2.3, swp=13, wdtol=30.0, sdtol=60.0, swtol=60.0),
    "air":     dict(wind=30, gust=45, hs=3.0, swh=4.0, swp=18, wdtol=60.0, sdtol=90.0, swtol=90.0),
}

def _cat_key(cat_name: str) -> str:
    n = cat_name.lower()
    if "small"     in n: return "small"
    if "medium"    in n: return "medium"
    if "heavy"     in n and "super" not in n: return "heavy"
    if "super"     in n: return "super"
    if "suborbital" in n or "hypersonic" in n: return "suborbital"
    if "air"       in n: return "air"
    return "small"

_PROPELLANTS = [
    "LOX/Kerosene", "LOX/LH2", "LOX/Methane",
    "Solid", "Hypergolic", "Solid/Nitrous",
    "Other", "None / N-A",
]
_RECOVERY_MODES = ["expendable", "rtls", "droneship", "parachute", "glide", "air catch"]
_VEHICLE_CLASSES = ["slv_orb", "slv_sub", "mlv_orb", "mlv_sub"]
_DATA_SOURCES    = ["estimated", "icd", "range_safety"]
_COUNTRIES = ["USA", "EU/France", "Italy/EU", "UK", "Japan", "India",
              "Russia", "China", "USA/NZ", "USA/International", "Other"]


def _label(text: str, hint: bool = False) -> QLabel:
    lbl = QLabel(text)
    if hint:
        lbl.setStyleSheet("color: #64748b; font-size: 8pt;")
    return lbl


class VehicleEditorDialog(QDialog):
    """
    Dialog for adding or editing a vehicle.
    Pass vehicle_data=None for Add mode; pass a dict from DB row for Edit.
    """

    def __init__(self, parent=None, vehicle_data: dict | None = None):
        super().__init__(parent)
        self._vehicle_data = vehicle_data or {}
        self._edit_mode    = bool(vehicle_data)
        self._category_names: list[str] = []
        self._hint_labels:    dict[str, QLabel] = {}

        self.setWindowTitle("Edit Vehicle" if self._edit_mode else "Add Vehicle")
        self.setMinimumWidth(560)
        self.setMinimumHeight(540)
        self.setModal(True)

        self._load_categories()
        self._build()
        if self._edit_mode:
            self._populate(self._vehicle_data)

    # ── DB helpers ────────────────────────────────────────────────────────────

    def _load_categories(self) -> None:
        try:
            conn = get_connection()
            rows = conn.execute(
                "SELECT name FROM vehicle_categories ORDER BY sort_order"
            ).fetchall()
            conn.close()
            self._category_names = [r["name"] for r in rows]
        except Exception:
            self._category_names = []

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_identity_tab(),    "Identity")
        self._tabs.addTab(self._build_physical_tab(),    "Physical")
        self._tabs.addTab(self._build_performance_tab(), "Performance")
        self._tabs.addTab(self._build_constraints_tab(), "Launch Constraints")
        self._tabs.addTab(self._build_launchers_tab(),   "Launchers")
        root.addWidget(self._tabs)

        # Validation warning
        self._warn_label = QLabel()
        self._warn_label.setWordWrap(True)
        self._warn_label.setStyleSheet(
            "background: #2a1d00; color: #f59e0b; border-radius: 4px; padding: 6px;"
        )
        self._warn_label.setVisible(False)
        root.addWidget(self._warn_label)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _build_identity_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(10)

        self._name_edit     = QLineEdit(); self._name_edit.setPlaceholderText("Required")
        self._provider_edit = QLineEdit()
        self._country_combo = QComboBox()
        self._country_combo.addItems(_COUNTRIES)
        self._country_combo.setEditable(True)

        self._category_combo = QComboBox()
        self._category_combo.addItems(self._category_names)
        self._category_combo.currentIndexChanged.connect(self._update_defaults_hints)

        self._status_combo = QComboBox()
        self._status_combo.addItems(["operational", "development", "retired", "proposed"])

        self._year_spin = QSpinBox()
        self._year_spin.setRange(0, 2040)
        self._year_spin.setSpecialValueText("Unknown")

        self._datasource_combo = QComboBox()
        self._datasource_combo.addItems(_DATA_SOURCES)
        self._datasource_combo.currentIndexChanged.connect(self._check_validation)

        self._notes_edit = QTextEdit()
        self._notes_edit.setFixedHeight(70)

        form.addRow("Name *",         self._name_edit)
        form.addRow("Provider",       self._provider_edit)
        form.addRow("Country",        self._country_combo)
        form.addRow("Category",       self._category_combo)
        form.addRow("Status",         self._status_combo)
        form.addRow("First flight",   self._year_spin)
        form.addRow("Data source",    self._datasource_combo)
        form.addRow("Notes",          self._notes_edit)
        return w

    def _build_physical_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(10)

        def _rspin(lo=0, hi=999_999, dec=1) -> QDoubleSpinBox:
            s = QDoubleSpinBox()
            s.setRange(lo, hi)
            s.setDecimals(dec)
            s.setSpecialValueText("Unknown")
            return s

        self._height_spin   = _rspin(0, 300)
        self._diameter_spin = _rspin(0, 30)
        self._mass_spin     = _rspin(0, 9_999_999)

        self._stages_spin   = QSpinBox()
        self._stages_spin.setRange(1, 5)

        self._prop1_combo   = QComboBox(); self._prop1_combo.addItems(_PROPELLANTS)
        self._prop2_combo   = QComboBox(); self._prop2_combo.addItems(_PROPELLANTS)
        self._propu_combo   = QComboBox(); self._propu_combo.addItems(["None / N-A"] + _PROPELLANTS)

        form.addRow("Height (m)",          self._height_spin)
        form.addRow("Max diameter (m)",    self._diameter_spin)
        form.addRow("Gross liftoff mass (kg)", self._mass_spin)
        form.addRow("Number of stages",    self._stages_spin)
        form.addRow("Stage 1 propellant",  self._prop1_combo)
        form.addRow("Stage 2 propellant",  self._prop2_combo)
        form.addRow("Upper stage prop.",   self._propu_combo)
        return w

    def _build_performance_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(10)

        def _rspin(hi=999_999) -> QDoubleSpinBox:
            s = QDoubleSpinBox()
            s.setRange(0, hi)
            s.setDecimals(0)
            s.setSpecialValueText("Unknown")
            return s

        self._leo_spin    = _rspin()
        self._sso_spin    = _rspin()
        self._gto_spin    = _rspin()
        self._recovery_combo = QComboBox()
        self._recovery_combo.addItems(_RECOVERY_MODES)
        self._class_combo = QComboBox()
        self._class_combo.addItems(_VEHICLE_CLASSES)

        form.addRow("LEO payload (kg)",  self._leo_spin)
        form.addRow("SSO payload (kg)",  self._sso_spin)
        form.addRow("GTO payload (kg)",  self._gto_spin)
        form.addRow("Recovery mode",     self._recovery_combo)
        form.addRow("Vehicle class",     self._class_combo)
        form.addRow("", _label(
            "Vehicle class drives probability engine modifiers. "
            "slv_orb = small-lift orbital, mlv_orb = medium/heavy-lift, "
            "slv_sub = suborbital.", hint=True
        ))
        return w

    def _build_constraints_tab(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(12, 12, 12, 12)
        vbox.setSpacing(6)

        note = QLabel(
            "These values are used directly in launch window probability "
            "calculations. Use ICD or range safety documentation values where "
            "available. Mark as Verified when sourced from official documentation."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #94a3b8; font-size: 8pt;")
        vbox.addWidget(note)

        form = QFormLayout()
        form.setSpacing(8)

        def _wspin(hi, dec=1) -> QDoubleSpinBox:
            s = QDoubleSpinBox()
            s.setRange(0, hi)
            s.setDecimals(dec)
            return s

        self._wind_spin  = _wspin(80)
        self._gust_spin  = _wspin(80)
        self._hs_spin    = _wspin(20, 2)
        self._swh_spin   = _wspin(20, 2)
        self._swp_spin   = _wspin(30, 1)
        self._wdtol_spin = _wspin(180)
        self._sdtol_spin = _wspin(180)
        self._swtol_spin = _wspin(180)

        def _add_with_hint(label, spin, key) -> None:
            hint = QLabel("Class default: —")
            hint.setStyleSheet("color: #64748b; font-size: 8pt;")
            self._hint_labels[key] = hint
            row = QHBoxLayout()
            row.addWidget(spin, 1)
            row.addWidget(hint)
            form.addRow(label, row)

        _add_with_hint("Max wind (kts)",         self._wind_spin,  "wind")
        _add_with_hint("Max gust (kts)",         self._gust_spin,  "gust")
        _add_with_hint("Max sig. wave Hs (m)",   self._hs_spin,    "hs")
        _add_with_hint("Max swell height (m)",   self._swh_spin,   "swh")
        _add_with_hint("Max swell period (s)",   self._swp_spin,   "swp")

        form.addRow("Wind dir tolerance (±°)",  self._wdtol_spin)
        form.addRow("Sea dir tolerance (±°)",   self._sdtol_spin)
        form.addRow("Swell dir tolerance (±°)", self._swtol_spin)

        vbox.addLayout(form)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #374151;")
        vbox.addWidget(sep)

        self._wind_verified = QCheckBox("Wind constraints verified (from official doc)")
        self._sea_verified  = QCheckBox("Sea state constraints verified (from official doc)")
        self._wind_verified.toggled.connect(self._check_validation)
        self._sea_verified.toggled.connect(self._check_validation)
        vbox.addWidget(self._wind_verified)
        vbox.addWidget(self._sea_verified)

        reset_btn = QPushButton("Reset to class defaults")
        reset_btn.clicked.connect(self._reset_to_defaults)
        vbox.addWidget(reset_btn)

        # Preferred launcher info box
        self._launcher_info_box = QFrame()
        self._launcher_info_box.setStyleSheet(
            "background: #1e3a5f; border-radius: 4px; padding: 2px;"
        )
        lib = QVBoxLayout(self._launcher_info_box)
        lib.setContentsMargins(10, 8, 10, 8)
        lib.setSpacing(4)
        lbl_title = QLabel("Preferred Launcher")
        lbl_title.setStyleSheet("color: #93c5fd; font-weight: bold; font-size: 9pt;")
        lib.addWidget(lbl_title)
        self._pref_launcher_name_lbl = QLabel("—")
        self._pref_launcher_name_lbl.setStyleSheet("color: #e2e8f0;")
        lib.addWidget(self._pref_launcher_name_lbl)
        self._pref_launcher_detail_lbl = QLabel("")
        self._pref_launcher_detail_lbl.setStyleSheet("color: #94a3b8; font-size: 8pt;")
        self._pref_launcher_detail_lbl.setWordWrap(True)
        lib.addWidget(self._pref_launcher_detail_lbl)
        self._launcher_info_box.setVisible(False)
        vbox.addWidget(self._launcher_info_box)

        vbox.addStretch()
        return w

    def _build_launchers_tab(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(12, 12, 12, 12)
        vbox.setSpacing(8)

        note = QLabel(
            "Launcher configurations for this vehicle are managed in the Launchers "
            "section.  This tab shows associated configurations and allows you to set "
            "a preferred launcher."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #94a3b8; font-size: 8pt;")
        vbox.addWidget(note)

        _LCOLS = ["Launcher Name", "Type", "Mount Method", "Base Ø (m)", "Weight (kg)", "Verified"]
        self._launcher_table = QTableWidget(0, len(_LCOLS))
        self._launcher_table.setHorizontalHeaderLabels(_LCOLS)
        self._launcher_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._launcher_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._launcher_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._launcher_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._launcher_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._launcher_table.setFixedHeight(160)
        vbox.addWidget(self._launcher_table)

        form2 = QFormLayout()
        form2.setSpacing(8)
        self._pref_launcher_combo = QComboBox()
        self._pref_launcher_combo.addItem("— None —", None)
        self._pref_launcher_combo.currentIndexChanged.connect(self._on_pref_launcher_changed)
        form2.addRow("Preferred launcher:", self._pref_launcher_combo)
        vbox.addLayout(form2)

        btn_row = QHBoxLayout()
        open_btn = QPushButton("Open Launcher in Editor")
        open_btn.clicked.connect(self._on_open_launcher)
        add_btn  = QPushButton("+ Add New Launcher for This Vehicle")
        add_btn.setStyleSheet(
            "background: #2563eb; color: white; border-radius: 4px; padding: 6px;"
        )
        add_btn.clicked.connect(self._on_add_launcher)
        btn_row.addWidget(open_btn)
        btn_row.addWidget(add_btn)
        vbox.addLayout(btn_row)

        vbox.addStretch()
        return w

    # ── Launcher tab helpers ──────────────────────────────────────────────────

    def _reload_launchers_tab(self) -> None:
        vid = self._vehicle_data.get("id") if self._edit_mode else None
        launchers: list[dict] = []
        if vid:
            try:
                conn = get_connection()
                rows = conn.execute(
                    """SELECT lc.* FROM launcher_configs lc
                       WHERE lc.vehicle_id=?
                       UNION
                       SELECT lc.* FROM launcher_configs lc
                       JOIN launcher_vehicle_compat lvc ON lvc.launcher_id=lc.id
                       WHERE lvc.vehicle_id=?
                       ORDER BY launcher_name""",
                    (vid, vid),
                ).fetchall()
                conn.close()
                launchers = [dict(r) for r in rows]
            except Exception:
                pass

        self._launcher_table.setRowCount(0)
        self._launcher_table.setRowCount(len(launchers))
        _type_disp = {
            "rail": "Rail", "vertical_fixed": "Vertical Fixed",
            "vertical_mobile": "Vertical Mobile", "air_carrier": "Air Carrier",
        }
        for ri, r in enumerate(launchers):
            verified = bool(r.get("specs_verified"))
            vals = [
                r.get("launcher_name", ""),
                _type_disp.get(r.get("launcher_type", ""), r.get("launcher_type", "")),
                (r.get("mount_method") or "").replace("_", " ").title(),
                f"{r['base_diameter_m']:.2f}" if r.get("base_diameter_m") else "—",
                f"{int(r['total_weight_kg'])}" if r.get("total_weight_kg") else "—",
                "✓" if verified else "✗",
            ]
            for ci, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                if ci == 5:
                    item.setForeground(QColor("#86efac") if verified else QColor("#fca5a5"))
                else:
                    item.setForeground(QColor("#f1f5f9"))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._launcher_table.setItem(ri, ci, item)

        # Rebuild preferred launcher combo
        self._pref_launcher_combo.blockSignals(True)
        self._pref_launcher_combo.clear()
        self._pref_launcher_combo.addItem("— None —", None)
        for r in launchers:
            self._pref_launcher_combo.addItem(r["launcher_name"], r["id"])
        pref_id = self._vehicle_data.get("preferred_launcher_id")
        if pref_id:
            for i in range(self._pref_launcher_combo.count()):
                if self._pref_launcher_combo.itemData(i) == pref_id:
                    self._pref_launcher_combo.setCurrentIndex(i)
                    break
        self._pref_launcher_combo.blockSignals(False)
        self._on_pref_launcher_changed()

    def _on_pref_launcher_changed(self) -> None:
        lid = self._pref_launcher_combo.currentData()
        if lid is None:
            self._launcher_info_box.setVisible(False)
            return
        try:
            conn = get_connection()
            row = conn.execute(
                "SELECT launcher_name, deck_load_kpa, blast_radius_m, min_deck_area_m2 "
                "FROM launcher_configs WHERE id=?", (lid,)
            ).fetchone()
            conn.close()
        except Exception:
            row = None
        if row:
            self._pref_launcher_name_lbl.setText(row["launcher_name"])
            parts = []
            if row["deck_load_kpa"]:
                parts.append(f"Deck load: {row['deck_load_kpa']:.1f} kPa")
            if row["blast_radius_m"]:
                parts.append(f"Blast radius: {int(row['blast_radius_m'])} m")
            if row["min_deck_area_m2"]:
                parts.append(f"Min deck area: {row['min_deck_area_m2']:.0f} m²")
            self._pref_launcher_detail_lbl.setText("  ·  ".join(parts) if parts else "No specs recorded")
            self._launcher_info_box.setVisible(True)

    def _on_open_launcher(self) -> None:
        row = self._launcher_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "No selection", "Select a launcher to open.")
            return
        name = self._launcher_table.item(row, 0).text()
        try:
            conn = get_connection()
            r = conn.execute(
                "SELECT * FROM launcher_configs WHERE launcher_name=?", (name,)
            ).fetchone()
            conn.close()
        except Exception:
            r = None
        if r:
            from ui.dialogs.launcher_editor import LauncherEditorDialog
            dlg = LauncherEditorDialog(self, launcher_data=dict(r))
            if dlg.exec():
                self._reload_launchers_tab()

    def _on_add_launcher(self) -> None:
        vid = self._vehicle_data.get("id") if self._edit_mode else None
        from ui.dialogs.launcher_editor import LauncherEditorDialog
        dlg = LauncherEditorDialog(self, vehicle_id=vid)
        if dlg.exec():
            self._reload_launchers_tab()

    # ── Behaviour ─────────────────────────────────────────────────────────────

    def _update_defaults_hints(self) -> None:
        """Update hint labels in tab 4 to reflect the selected category."""
        cat_name = self._category_combo.currentText()
        key      = _cat_key(cat_name)
        defs     = _CAT_DEFAULTS.get(key, {})
        mapping  = {
            "wind": f"{defs.get('wind', '—')} kts",
            "gust": f"{defs.get('gust', '—')} kts",
            "hs":   f"{defs.get('hs',   '—')} m",
            "swh":  f"{defs.get('swh',  '—')} m",
            "swp":  f"{defs.get('swp',  '—')} s",
        }
        for k, lbl in self._hint_labels.items():
            lbl.setText(f"Class default: {mapping.get(k, '—')}")

    def _reset_to_defaults(self) -> None:
        cat_name = self._category_combo.currentText()
        defs = _CAT_DEFAULTS.get(_cat_key(cat_name), {})
        if defs:
            self._wind_spin.setValue(defs["wind"])
            self._gust_spin.setValue(defs["gust"])
            self._hs_spin.setValue(defs["hs"])
            self._swh_spin.setValue(defs["swh"])
            self._swp_spin.setValue(defs["swp"])
            # Direction tolerances (previously not reset — Pre-28B-3 Part D)
            self._wdtol_spin.setValue(defs.get("wdtol", 45.0))
            self._sdtol_spin.setValue(defs.get("sdtol", 60.0))
            self._swtol_spin.setValue(defs.get("swtol", 60.0))

    def _check_validation(self) -> None:
        ds = self._datasource_combo.currentText()
        if ds in ("icd", "range_safety"):
            if not (self._wind_verified.isChecked() and self._sea_verified.isChecked()):
                self._warn_label.setText(
                    "⚠  Source set to official document but not marked as verified — "
                    "consider checking the Verified boxes in the Launch Constraints tab."
                )
                self._warn_label.setVisible(True)
                return
        self._warn_label.setVisible(False)

    # ── Populate / save ───────────────────────────────────────────────────────

    def _populate(self, d: dict) -> None:
        self._name_edit.setText(d.get("name", ""))
        self._provider_edit.setText(d.get("provider", "") or "")
        _set_combo(self._country_combo, d.get("country", ""))
        _set_combo(self._category_combo, d.get("category_name", ""))
        _set_combo(self._status_combo,   d.get("status", "operational"))
        yr = d.get("first_flight_year") or 0
        self._year_spin.setValue(int(yr))
        _set_combo(self._datasource_combo, d.get("data_source", "estimated"))
        self._notes_edit.setPlainText(d.get("notes", "") or "")

        self._height_spin.setValue(d.get("height_m") or 0)
        self._diameter_spin.setValue(d.get("diameter_m") or 0)
        self._mass_spin.setValue(d.get("gross_mass_kg") or 0)
        self._stages_spin.setValue(int(d.get("stages") or 1))
        _set_combo(self._prop1_combo, d.get("propellant_stage1", ""))
        _set_combo(self._prop2_combo, d.get("propellant_stage2", ""))
        _set_combo(self._propu_combo, d.get("propellant_upper", "None / N-A") or "None / N-A")

        self._leo_spin.setValue(d.get("leo_payload_kg") or 0)
        self._sso_spin.setValue(d.get("sso_payload_kg") or 0)
        self._gto_spin.setValue(d.get("gto_payload_kg") or 0)
        _set_combo(self._recovery_combo, d.get("recovery_mode", "expendable"))
        _set_combo(self._class_combo,    d.get("vehicle_class", "slv_orb"))

        # Explicit None checks (not `or`) so a legitimately stored 0.0 is
        # preserved on reopen rather than being replaced by the fallback
        # default. 0.0 is falsy in Python, which silently discarded saved
        # zero values under the previous `or` pattern (Pre-28B-3).
        _wind = d.get("max_wind_kts")
        self._wind_spin.setValue(_wind if _wind is not None else 0.0)
        _gust = d.get("max_gust_kts")
        self._gust_spin.setValue(_gust if _gust is not None else 0.0)
        _hs = d.get("max_hs_m")
        self._hs_spin.setValue(_hs if _hs is not None else 0.0)
        _swh = d.get("max_swell_ht_m")
        self._swh_spin.setValue(_swh if _swh is not None else 0.0)
        _swp = d.get("max_swell_period_s")
        self._swp_spin.setValue(_swp if _swp is not None else 0.0)
        _wdtol = d.get("max_wind_dir_tolerance_deg")
        self._wdtol_spin.setValue(_wdtol if _wdtol is not None else 45.0)
        _sdtol = d.get("max_sea_dir_tolerance_deg")
        self._sdtol_spin.setValue(_sdtol if _sdtol is not None else 60.0)
        _swtol = d.get("max_swell_dir_tolerance_deg")
        self._swtol_spin.setValue(_swtol if _swtol is not None else 60.0)
        self._wind_verified.setChecked(bool(d.get("wind_hold_verified")))
        self._sea_verified.setChecked(bool(d.get("sea_state_verified")))

        self._update_defaults_hints()
        self._reload_launchers_tab()

    def _on_save(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Name is required.")
            self._tabs.setCurrentIndex(0)
            self._name_edit.setFocus()
            return

        # Enforce unique vehicle name at the application layer. vehicles.name has
        # no DB-level UNIQUE constraint (see CLAUDE.md known limitation), and
        # _selected_row_data() matches rows by name, so a duplicate would make
        # edits/deletes act on the wrong vehicle. -1 is the Add-mode sentinel id
        # (never matches a real autoincrement id).
        conn_check = get_connection()
        try:
            existing = conn_check.execute(
                "SELECT id FROM vehicles WHERE name = ? AND id != ?",
                (name, self._vehicle_data.get("id", -1)),
            ).fetchone()
        finally:
            conn_check.close()
        if existing:
            QMessageBox.warning(
                self, "Duplicate name",
                f"A vehicle named '{name}' already exists. "
                f"Each vehicle must have a unique name.",
            )
            self._tabs.setCurrentIndex(0)
            self._name_edit.setFocus()
            return

        # Gather category_id
        cat_name = self._category_combo.currentText()
        cat_id: int | None = None
        try:
            conn = get_connection()
            row = conn.execute(
                "SELECT id FROM vehicle_categories WHERE name=?", (cat_name,)
            ).fetchone()
            conn.close()
            cat_id = row["id"] if row else None
        except Exception:
            pass

        yr = self._year_spin.value() or None
        data = dict(
            name=name,
            provider=self._provider_edit.text().strip() or None,
            country=self._country_combo.currentText() or None,
            vehicle_class=self._class_combo.currentText(),
            recovery_mode=self._recovery_combo.currentText(),
            leo_payload_kg=_spin_val(self._leo_spin),
            sso_payload_kg=_spin_val(self._sso_spin),
            gto_payload_kg=_spin_val(self._gto_spin),
            height_m=_spin_val(self._height_spin),
            diameter_m=_spin_val(self._diameter_spin),
            gross_mass_kg=_spin_val(self._mass_spin),
            stages=self._stages_spin.value(),
            propellant_stage1=self._prop1_combo.currentText() or None,
            propellant_stage2=self._prop2_combo.currentText() or None,
            propellant_upper=self._propu_combo.currentText() or None,
            status=self._status_combo.currentText(),
            first_flight_year=yr,
            max_wind_kts=self._wind_spin.value(),
            max_gust_kts=self._gust_spin.value(),
            max_hs_m=self._hs_spin.value(),
            max_swell_ht_m=self._swh_spin.value(),
            max_swell_period_s=self._swp_spin.value(),
            max_wind_dir_tolerance_deg=self._wdtol_spin.value(),
            max_sea_dir_tolerance_deg=self._sdtol_spin.value(),
            max_swell_dir_tolerance_deg=self._swtol_spin.value(),
            wind_hold_verified=int(self._wind_verified.isChecked()),
            sea_state_verified=int(self._sea_verified.isChecked()),
            data_source=self._datasource_combo.currentText(),
            notes=self._notes_edit.toPlainText().strip() or None,
            category_id=cat_id,
            preferred_launcher_id=self._pref_launcher_combo.currentData(),
        )

        conn = get_connection()
        try:
            if self._edit_mode:
                sets = ", ".join(f"{k}=:{k}" for k in data)
                data["_id"] = self._vehicle_data["id"]
                conn.execute(f"UPDATE vehicles SET {sets} WHERE id=:_id", data)
            else:
                cols = ", ".join(data.keys())
                vals = ", ".join(f":{k}" for k in data)
                conn.execute(f"INSERT INTO vehicles ({cols}) VALUES ({vals})", data)
            conn.commit()
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", str(exc))
            return
        finally:
            # Always close, even on exception — a leaked connection can hold a
            # SQLite file lock on Windows and block subsequent writes.
            conn.close()

        self.accept()   # only reached on success (exception path returns above)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _set_combo(combo: QComboBox, value: str | None) -> None:
    if not value:
        return
    idx = combo.findText(value, Qt.MatchFlag.MatchFixedString)
    if idx >= 0:
        combo.setCurrentIndex(idx)
    elif combo.isEditable():
        combo.setEditText(value)


def _spin_val(spin: QDoubleSpinBox) -> float | None:
    v = spin.value()
    return v if v > 0 else None

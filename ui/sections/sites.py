"""
ui/sections/sites.py — Multi-site table for launch site management.

Coordinate convention: +lat=N, -lat=S, +lon=E, -lon=W (WGS-84 decimal degrees).
Coordinates displayed in DDM format; any recognised format accepted on input.

Mode toggle at top:
  All Sites    — full editable table (default, unchanged behaviour). No
                 Activate control here — status column is read-only,
                 reflecting whatever is active via the By Project mechanism.
  By Project   — project-filtered view; site fields are read-only, but this
                 is the only place that can Activate/Deactivate a site+project
                 pairing.
"""
from __future__ import annotations

import json
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QComboBox, QMessageBox, QMenu, QApplication, QButtonGroup,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QAction

from core.models import Site, Platform
from ui.styles import apply_table_colors
from ui.widgets.coord_input import parse_coordinate


# ── Styles ─────────────────────────────────────────────────────────────────────

_BTN_PRIMARY = (
    "QPushButton { background: #2563eb; color: white; border-radius: 4px;"
    "padding: 6px 16px; font-weight: bold; border: none; }"
    "QPushButton:hover { background: #1d4ed8; }"
    "QPushButton:disabled { background: #1e3a5f; color: #64748b; }"
)
_BTN_SECONDARY = (
    "QPushButton { background: #1e2d3d; color: #e2e8f0; border: 1px solid #374151;"
    "border-radius: 4px; padding: 6px 14px; }"
    "QPushButton:hover { background: #2d3f55; }"
    "QPushButton:disabled { color: #4b5563; }"
)

# Mode toggle button styles (pill left / pill right)
_TOGGLE_L = (
    "QPushButton { background:#1a2233; color:#94a3b8; border:1px solid #374151;"
    "border-right:none; border-top-left-radius:4px; border-bottom-left-radius:4px;"
    "border-top-right-radius:0; border-bottom-right-radius:0;"
    "padding:5px 20px; font-weight:600; font-size:9pt; }"
    "QPushButton:hover:!checked { background:#1e2d3d; color:#e2e8f0; }"
    "QPushButton:checked { background:#2563eb; color:#ffffff; border-color:#2563eb; }"
)
_TOGGLE_R = (
    "QPushButton { background:#1a2233; color:#94a3b8; border:1px solid #374151;"
    "border-top-left-radius:0; border-bottom-left-radius:0;"
    "border-top-right-radius:4px; border-bottom-right-radius:4px;"
    "padding:5px 20px; font-weight:600; font-size:9pt; }"
    "QPushButton:hover:!checked { background:#1e2d3d; color:#e2e8f0; }"
    "QPushButton:checked { background:#2563eb; color:#ffffff; border-color:#2563eb; }"
)

_COMBO_STYLE = (
    "QComboBox { background: #1a2233; color: #e2e8f0; border: 1px solid #374151;"
    " border-radius: 3px; padding: 4px 8px; }"
    "QComboBox::drop-down { border: none; width: 18px; }"
    "QComboBox QAbstractItemView { background: #1a2233; color: #e2e8f0;"
    " selection-background-color: #2563eb; }"
)

# Status badge colour pairs (bg, fg) — All Sites mode
_STATUS_UNSAVED  = ("#374151", "#94a3b8")
_STATUS_SAVED    = ("#14532d", "#86efac")
_STATUS_ACTIVE   = ("#1e3a8a", "#93c5fd")

# Status badge colours for By Project mode
_PROJ_STATUS_COLORS = {
    "candidate":     ("#1e2d3d", "#93c5fd"),
    "down-selected": ("#422006", "#fde68a"),
    "approved":      ("#14532d", "#86efac"),
    "final":         ("#1e3a8a", "#bfdbfe"),
    "rejected":      ("#450a0a", "#fca5a5"),
}

_COLUMNS = ["#", "Name", "Latitude", "Longitude", "Bbox NM", "Vessel Platform",
            "Notes", "Status", "Vehicles Used"]

_COL_NUM      = 0
_COL_NAME     = 1
_COL_LAT      = 2
_COL_LON      = 3
_COL_BBOX     = 4
_COL_PLATFORM = 5
_COL_NOTES    = 6
_COL_STATUS   = 7
_COL_VEHICLES = 8   # read-only; populated from site_vehicles (Set 27B)

# By Project table columns
_PROJ_COLUMNS = [
    "Site Name", "Coord Code", "Latitude", "Longitude",
    "Bbox NM", "Vessel Platform", "Status", "Status Changed", "History",
    "Vehicles Used", "Activate",
]
_PCOL_HIST     = 8   # history column index in project table
_PCOL_VEH      = 9   # vehicles-used column index in project table (Set 27B)
_PCOL_ACTIVATE = 10  # per-row Activate button column (site+project pairing)

# Statuses a parent project must be in for its candidate sites to be
# activatable (site+project pairing).
_PROJECT_STATUSES_ALLOWING_ACTIVATION = ("planning", "pending")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _dd_to_ddm(dd: float, is_lat: bool) -> str:
    """Format decimal degrees as DDM string: e.g. '28 30.000 N'."""
    hemi = ("N" if dd >= 0 else "S") if is_lat else ("E" if dd >= 0 else "W")
    ad   = abs(dd)
    deg  = int(ad)
    mins = (ad - deg) * 60.0
    return f"{deg} {mins:.3f} {hemi}"


def _item(text: str, editable: bool = True) -> QTableWidgetItem:
    it = QTableWidgetItem(str(text))
    it.setForeground(QColor("#f1f5f9"))
    if not editable:
        it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return it


def _pitem(text: str, fg: str = "#e2e8f0") -> QTableWidgetItem:
    """Read-only table item for the By Project view."""
    it = QTableWidgetItem(str(text))
    it.setForeground(QColor(fg))
    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return it


def _fmt_last_used(raw) -> str:
    """Format a site_vehicles.last_used timestamp as 'Jun 28 2026'."""
    from datetime import datetime
    if not raw:
        return "—"
    s = str(raw).replace("T", " ")
    try:
        return datetime.fromisoformat(s).strftime("%b %d %Y")
    except ValueError:
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").strftime("%b %d %Y")
        except ValueError:
            return s[:10]


def _vehicles_used_display(site_id: Optional[int]) -> tuple[str, Optional[str]]:
    """
    Return (display_text, tooltip) summarising the vehicles analysed at a site,
    read from the site_vehicles table most-recent-first.

    0 vehicles → ("—", None) shown in gray by the caller
    1          → ("Name", None)
    2          → ("Name1, Name2", None)
    3+         → ("Name1 +N more", tooltip listing all with last-used dates)
    """
    if site_id is None:
        return "—", None
    from core.database import get_connection
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT v.name AS name, sv.run_count AS run_count, "
            "       sv.last_used AS last_used "
            "FROM site_vehicles sv "
            "JOIN vehicles v ON sv.vehicle_id = v.id "
            "WHERE sv.site_id = ? "
            "ORDER BY sv.last_used DESC",
            (site_id,),
        ).fetchall()
        conn.close()
    except Exception:
        return "—", None

    if not rows:
        return "—", None

    names = [r["name"] for r in rows]
    if len(rows) == 1:
        return names[0], None
    if len(rows) == 2:
        return f"{names[0]}, {names[1]}", None

    text = f"{names[0]} +{len(rows) - 1} more"
    tip_lines = []
    for r in rows:
        runs = r["run_count"]
        run_word = "run" if runs == 1 else "runs"
        tip_lines.append(
            f"{r['name']} (last: {_fmt_last_used(r['last_used'])}, {runs} {run_word})"
        )
    return text, "\n".join(tip_lines)


def _activation_guard_reasons(project_status: Optional[str],
                               candidate_status: Optional[str]) -> list[str]:
    """
    Return the list of reasons a site+project pairing may NOT be activated.
    Empty list = activation allowed. Pure function (no Qt/DB) so it can be
    unit-tested directly.

    Rules:
      - parent project.status must be in ('planning', 'pending')
      - this row's project_sites candidate status must not be 'rejected'
    """
    reasons: list[str] = []
    if project_status not in _PROJECT_STATUSES_ALLOWING_ACTIVATION:
        reasons.append(
            f"project status is '{project_status}' "
            f"(must be 'planning' or 'pending' to activate a site)"
        )
    if candidate_status == "rejected":
        reasons.append("this site's candidate status is 'rejected'")
    return reasons


# ── Section ────────────────────────────────────────────────────────────────────

class SitesSection(QWidget):
    """Multi-site table: add, edit, save, and set an active launch site."""

    site_saved = pyqtSignal(int)  # emits site_id after successful DB save

    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._row_ids: list[Optional[int]] = []   # DB id per row; None = unsaved
        self._active_id: Optional[int] = None
        self._platforms: list[Platform] = []
        self._build()

    # ── Layout ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        # Title + subtitle
        title = QLabel("Site & Vehicle Configuration")
        title.setObjectName("sectionTitle")
        root.addWidget(title)

        subtitle = QLabel(
            "Add launch site candidates to the table and save them to the "
            "database.  To activate a site for analysis, switch to By Project mode."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #94a3b8;")
        root.addWidget(subtitle)

        # ── Mode toggle ───────────────────────────────────────────────────────
        root.addLayout(self._build_mode_toggle())

        # ── All Sites widget (default mode) ───────────────────────────────────
        self._all_sites_widget = QWidget()
        self._all_sites_widget.setStyleSheet("background: transparent;")
        self._build_all_sites_content(self._all_sites_widget)
        root.addWidget(self._all_sites_widget, 1)

        # ── By Project widget (hidden by default) ─────────────────────────────
        self._project_view_widget = self._build_project_view()
        self._project_view_widget.hide()
        root.addWidget(self._project_view_widget, 1)

    def _build_mode_toggle(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(0)

        self._all_sites_btn = QPushButton("● All Sites")
        self._all_sites_btn.setCheckable(True)
        self._all_sites_btn.setStyleSheet(_TOGGLE_L)

        self._by_project_btn = QPushButton("  By Project")
        self._by_project_btn.setCheckable(True)
        self._by_project_btn.setChecked(True)
        self._by_project_btn.setStyleSheet(_TOGGLE_R)

        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._mode_group.addButton(self._all_sites_btn, 0)
        self._mode_group.addButton(self._by_project_btn, 1)
        self._mode_group.idToggled.connect(self._on_mode_toggled)

        row.addWidget(self._all_sites_btn)
        row.addWidget(self._by_project_btn)
        row.addStretch(1)
        return row

    def _build_all_sites_content(self, container: QWidget) -> None:
        """Build the All Sites (editable) content into the given container."""
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Vehicle selector
        v_row = QHBoxLayout()
        v_row.setSpacing(8)
        v_row.addWidget(QLabel("Launch vehicle:"))

        self.vehicle_combo = QComboBox()
        self.vehicle_combo.addItem("— select launch vehicle —", userData=None)
        for v in self.mw.vehicles:
            self.vehicle_combo.addItem(v.name, userData=v)
        if self.mw.vehicle:
            for i in range(1, self.vehicle_combo.count()):
                if self.vehicle_combo.itemData(i) and \
                        self.vehicle_combo.itemData(i).name == self.mw.vehicle.name:
                    self.vehicle_combo.setCurrentIndex(i)
                    break
        self.vehicle_combo.currentIndexChanged.connect(self._on_vehicle_changed)
        v_row.addWidget(self.vehicle_combo)
        v_row.addStretch()
        layout.addLayout(v_row)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self._add_btn = QPushButton("+ Add Row")
        self._add_btn.setStyleSheet(_BTN_SECONDARY)
        self._add_btn.clicked.connect(self._add_row)
        toolbar.addWidget(self._add_btn)

        self._del_btn = QPushButton("Delete Selected")
        self._del_btn.setStyleSheet(_BTN_SECONDARY)
        self._del_btn.clicked.connect(self._delete_selected)
        toolbar.addWidget(self._del_btn)

        self._clear_btn = QPushButton("Clear All")
        self._clear_btn.setStyleSheet(_BTN_SECONDARY)
        self._clear_btn.clicked.connect(self._clear_all)
        toolbar.addWidget(self._clear_btn)

        toolbar.addStretch()

        self._save_btn = QPushButton("Save All Sites")
        self._save_btn.setStyleSheet(_BTN_PRIMARY)
        self._save_btn.clicked.connect(self._save_all)
        toolbar.addWidget(self._save_btn)

        layout.addLayout(toolbar)

        # Table
        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_NAME,     QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(_COL_NOTES,    QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(_COL_PLATFORM, QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(_COL_PLATFORM, 170)
        self._table.setColumnWidth(_COL_STATUS,   90)
        self._table.setColumnWidth(_COL_NUM,      30)

        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.SelectedClicked
        )
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._context_menu)
        apply_table_colors(self._table)
        layout.addWidget(self._table, 1)

        # Status bar
        self._status_lbl = QLabel("No active site.")
        self._status_lbl.setStyleSheet("color: #64748b; font-style: italic; font-size: 8pt;")
        layout.addWidget(self._status_lbl)

        hint = QLabel(
            "Tip: right-click a row for more options.  "
            "Coordinates accept decimal degrees, DDM, or DMS."
        )
        hint.setStyleSheet("color: #475569; font-size: 7.5pt;")
        layout.addWidget(hint)

    def _build_project_view(self) -> QWidget:
        """Build the By Project read-only view widget."""
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(10)

        # Controls row
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)

        proj_lbl = QLabel("Project:")
        proj_lbl.setStyleSheet("color: #94a3b8;")
        ctrl.addWidget(proj_lbl)

        self._proj_combo = QComboBox()
        self._proj_combo.setStyleSheet(_COMBO_STYLE)
        self._proj_combo.setMinimumWidth(240)
        self._proj_combo.currentIndexChanged.connect(self._on_project_combo_changed)
        ctrl.addWidget(self._proj_combo)

        ctrl.addSpacing(12)

        status_lbl = QLabel("Status:")
        status_lbl.setStyleSheet("color: #94a3b8;")
        ctrl.addWidget(status_lbl)

        self._status_filter_combo = QComboBox()
        self._status_filter_combo.setStyleSheet(_COMBO_STYLE)
        for label, value in [
            ("All",           None),
            ("Candidate",     ["candidate"]),
            ("Down-Selected", ["down-selected"]),
            ("Final",         ["final"]),
            ("Rejected",      ["rejected"]),
        ]:
            self._status_filter_combo.addItem(label, userData=value)
        self._status_filter_combo.currentIndexChanged.connect(self._refresh_project_table)
        ctrl.addWidget(self._status_filter_combo)

        ctrl.addSpacing(8)
        self._refresh_proj_btn = QPushButton("Refresh")
        self._refresh_proj_btn.setStyleSheet(_BTN_SECONDARY)
        self._refresh_proj_btn.clicked.connect(self._on_refresh_project_view)
        ctrl.addWidget(self._refresh_proj_btn)

        # Deactivate is section-level, not row-scoped: visible whenever a
        # site+project pairing is currently active, regardless of table selection.
        self._deactivate_btn = QPushButton("Deactivate")
        self._deactivate_btn.setStyleSheet(_BTN_SECONDARY)
        self._deactivate_btn.clicked.connect(self._on_deactivate_site)
        self._deactivate_btn.setVisible(False)
        ctrl.addWidget(self._deactivate_btn)

        ctrl.addStretch(1)
        layout.addLayout(ctrl)

        self._active_status_lbl = QLabel("No active site.")
        self._active_status_lbl.setStyleSheet(
            "color: #64748b; font-style: italic; font-size: 8pt;"
        )
        layout.addWidget(self._active_status_lbl)

        # Empty state label
        self._proj_empty_lbl = QLabel(
            "Select a project above to view its candidate sites."
        )
        self._proj_empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._proj_empty_lbl.setStyleSheet("color: #475569; font-size: 10pt; padding: 40px;")
        layout.addWidget(self._proj_empty_lbl, 1)

        # Read-only results table
        self._proj_table = QTableWidget()
        self._proj_table.setColumnCount(len(_PROJ_COLUMNS))
        self._proj_table.setHorizontalHeaderLabels(_PROJ_COLUMNS)
        self._proj_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._proj_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._proj_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._proj_table.verticalHeader().setVisible(False)
        self._proj_table.setAlternatingRowColors(True)
        apply_table_colors(self._proj_table)
        self._proj_table.hide()
        self._proj_table.cellClicked.connect(self._on_proj_table_cell_clicked)
        self._proj_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._proj_table.customContextMenuRequested.connect(self._proj_context_menu)
        layout.addWidget(self._proj_table, 1)

        # Read-only note
        note = QLabel(
            "Site details are read-only here.  To edit coordinates or other site fields, "
            "switch to All Sites mode.  To change a site's project status, use the Projects tab."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #475569; font-size: 7.5pt; font-style: italic;")
        layout.addWidget(note)

        return w

    # ── Mode toggle slot ───────────────────────────────────────────────────────

    def _on_mode_toggled(self, button_id: int, checked: bool) -> None:
        if not checked:
            return
        if button_id == 0:  # All Sites
            self._project_view_widget.hide()
            self._all_sites_widget.show()
        else:               # By Project
            self._all_sites_widget.hide()
            self._project_view_widget.show()
            self._populate_project_combo()

    # ── Show event ─────────────────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._reload_platforms()
        self._load_from_db()
        if self._project_view_widget.isVisible():
            self._populate_project_combo()
        self._refresh_active_indicator()

    # ── Platform helpers ────────────────────────────────────────────────────────

    def _reload_platforms(self) -> None:
        try:
            from core.database import get_connection
            conn = get_connection()
            rows = conn.execute(
                "SELECT * FROM platforms ORDER BY is_reference DESC, name"
            ).fetchall()
            conn.close()
            self._platforms = [
                Platform(
                    id=r["id"], name=r["name"],
                    hull_type=r["hull_type"],
                    hull_motion_factor=r["hull_motion_factor"],
                    dp_capable=bool(r["dp_capable"]),
                    max_hs_operating_m=r["max_hs_operating_m"],
                    typical_depth_m=r["typical_depth_m"],
                    payload_class=r["payload_class"] or "",
                    notes=r["notes"] or "",
                )
                for r in rows
            ]
        except Exception:
            self._platforms = []

        for row in range(self._table.rowCount()):
            combo = self._table.cellWidget(row, _COL_PLATFORM)
            if isinstance(combo, QComboBox):
                prev = combo.currentText()
                self._fill_platform_combo(combo)
                idx = combo.findText(prev)
                if idx >= 0:
                    combo.setCurrentIndex(idx)

    def _fill_platform_combo(self, combo: QComboBox) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("— none —", userData=None)
        for p in self._platforms:
            combo.addItem(p.name, userData=p.id)
        combo.blockSignals(False)

    def _platform_combo(self, platform_id: Optional[int] = None) -> QComboBox:
        combo = QComboBox()
        combo.setStyleSheet(
            "QComboBox { background: #1a2233; color: #e2e8f0; border: 1px solid #374151;"
            " border-radius: 3px; padding: 2px 6px; }"
            "QComboBox::drop-down { border: none; }"
            "QComboBox QAbstractItemView { background: #1a2233; color: #e2e8f0; }"
        )
        self._fill_platform_combo(combo)
        if platform_id is not None:
            idx = combo.findData(platform_id)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        return combo

    # ── DB load / save ─────────────────────────────────────────────────────────

    def _load_from_db(self) -> None:
        from modules.m1_site.site_config import list_sites
        try:
            db_sites = list_sites()
        except Exception:
            db_sites = []

        self._table.setRowCount(0)
        self._row_ids = []

        active_id = getattr(self.mw.site, "id", None) if self.mw.site else None
        self._active_id = active_id

        for site in db_sites:
            self._append_site_row(site, active_id)

        for _ in range(3):
            self._add_row()

        self._refresh_row_numbers()

    def _append_site_row(self, site: Site, active_id: Optional[int] = None) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._row_ids.append(site.id)

        self._table.setItem(row, _COL_NUM,  _item(str(row + 1), editable=False))
        self._table.setItem(row, _COL_NAME, _item(site.name or ""))
        self._table.setItem(row, _COL_LAT,  _item(_dd_to_ddm(site.lat, is_lat=True)))
        self._table.setItem(row, _COL_LON,  _item(_dd_to_ddm(site.lon, is_lat=False)))
        self._table.setItem(row, _COL_BBOX, _item(f"{site.bbox_nm:.1f}"))
        self._table.setItem(row, _COL_NOTES, _item(site.notes or ""))

        combo = self._platform_combo(site.platform_id)
        self._table.setCellWidget(row, _COL_PLATFORM, combo)

        if site.id == active_id:
            status, bg, fg = "Active ★", _STATUS_ACTIVE[0], _STATUS_ACTIVE[1]
        elif site.id is not None:
            status, bg, fg = "Saved ✓", _STATUS_SAVED[0], _STATUS_SAVED[1]
        else:
            status, bg, fg = "Unsaved", _STATUS_UNSAVED[0], _STATUS_UNSAVED[1]

        s_item = _item(status, editable=False)
        s_item.setBackground(QColor(bg))
        s_item.setForeground(QColor(fg))
        self._table.setItem(row, _COL_STATUS, s_item)

        self._set_vehicles_cell(row, site.id)

    def _set_vehicles_cell(self, row: int, site_id: Optional[int]) -> None:
        """Populate the read-only Vehicles Used cell from site_vehicles."""
        text, tip = _vehicles_used_display(site_id)
        v_item = _item(text, editable=False)
        v_item.setForeground(QColor("#64748b" if text == "—" else "#f1f5f9"))
        if tip:
            v_item.setToolTip(tip)
        self._table.setItem(row, _COL_VEHICLES, v_item)

    # ── Row management ─────────────────────────────────────────────────────────

    def _add_row(self) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._row_ids.append(None)

        self._table.setItem(row, _COL_NUM,    _item(str(row + 1), editable=False))
        self._table.setItem(row, _COL_NAME,   _item(""))
        self._table.setItem(row, _COL_LAT,    _item(""))
        self._table.setItem(row, _COL_LON,    _item(""))
        self._table.setItem(row, _COL_BBOX,   _item("25.0"))
        self._table.setItem(row, _COL_NOTES,  _item(""))

        combo = self._platform_combo()
        self._table.setCellWidget(row, _COL_PLATFORM, combo)

        s_item = _item("Unsaved", editable=False)
        s_item.setBackground(QColor(_STATUS_UNSAVED[0]))
        s_item.setForeground(QColor(_STATUS_UNSAVED[1]))
        self._table.setItem(row, _COL_STATUS, s_item)

        self._set_vehicles_cell(row, None)

    def _delete_selected(self) -> None:
        rows = sorted(
            {idx.row() for idx in self._table.selectedIndexes()},
            reverse=True,
        )
        if not rows:
            return

        saved_rows = [r for r in rows if r < len(self._row_ids) and self._row_ids[r] is not None]
        if saved_rows:
            from modules.m1_site.site_config import get_site_associations
            any_linked = any(
                any(c > 0 for c in get_site_associations(self._row_ids[r]).values())
                for r in saved_rows
            )
            warning = (
                "\n\nOne or more of these sites are still linked to projects, "
                "reports, or analysis history — deleting will permanently "
                "remove those associations too (including status history). "
                "Report PDF files already on disk are not deleted."
                if any_linked else ""
            )
            reply = QMessageBox.question(
                self, "Delete Selected",
                f"Permanently delete {len(saved_rows)} saved site"
                f"{'s' if len(saved_rows) != 1 else ''} from the database? "
                "This cannot be undone." + warning,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        failures: list[str] = []
        # Process highest row index first so earlier removals don't shift
        # the indices of rows still pending deletion.
        for row in rows:
            site_id = self._row_ids[row] if row < len(self._row_ids) else None
            if site_id is None:
                self._table.removeRow(row)
                self._row_ids.pop(row)
                continue
            ok, error = self._delete_site_row(row, site_id)
            if not ok:
                name_item = self._table.item(row, _COL_NAME)
                name = name_item.text() if name_item else f"row {row + 1}"
                failures.append(f"{name}: {error}")

        self._refresh_row_numbers()

        if failures:
            QMessageBox.critical(
                self, "Some Sites Could Not Be Deleted",
                "The following sites could not be deleted:\n\n"
                + "\n".join(failures)
            )

    def _clear_all(self) -> None:
        if QMessageBox.question(
            self, "Clear All",
            "Remove all rows from the table? (Does not delete saved DB entries.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self._table.setRowCount(0)
        self._row_ids.clear()
        for _ in range(3):
            self._add_row()
        self._refresh_row_numbers()

    def _refresh_row_numbers(self) -> None:
        for row in range(self._table.rowCount()):
            item = self._table.item(row, _COL_NUM)
            if item:
                item.setText(str(row + 1))

    # ── Parsing ────────────────────────────────────────────────────────────────

    def _parse_row(self, row: int) -> Optional[dict]:
        """Parse one table row; returns None and shows an error if invalid."""
        def _cell(col: int) -> str:
            it = self._table.item(row, col)
            return it.text().strip() if it else ""

        name    = _cell(_COL_NAME)
        lat_txt = _cell(_COL_LAT)
        lon_txt = _cell(_COL_LON)
        bbox_t  = _cell(_COL_BBOX)
        notes   = _cell(_COL_NOTES)

        if not lat_txt and not lon_txt and not name:
            return None  # empty row — skip silently

        lat = parse_coordinate(lat_txt, "lat")
        if lat is None:
            QMessageBox.warning(
                self, "Invalid Latitude",
                f"Row {row+1}: cannot parse latitude '{lat_txt}'.\n"
                "Use decimal degrees or DDM (e.g. 28 30.000 N)."
            )
            return None

        lon = parse_coordinate(lon_txt, "lon")
        if lon is None:
            QMessageBox.warning(
                self, "Invalid Longitude",
                f"Row {row+1}: cannot parse longitude '{lon_txt}'.\n"
                "Use decimal degrees or DDM (e.g. 80 36.000 W)."
            )
            return None

        try:
            bbox = float(bbox_t) if bbox_t else 25.0
        except ValueError:
            bbox = 25.0

        combo = self._table.cellWidget(row, _COL_PLATFORM)
        platform_id = combo.currentData() if isinstance(combo, QComboBox) else None

        auto_name = (
            name if name else
            f"Site {abs(lat):.3f}{'N' if lat>=0 else 'S'} "
            f"{abs(lon):.3f}{'E' if lon>=0 else 'W'}"
        )

        return {
            "name": auto_name,
            "lat": lat, "lon": lon,
            "bbox_nm": bbox,
            "platform_id": platform_id,
            "notes": notes,
        }

    # ── Save ───────────────────────────────────────────────────────────────────

    def _save_all(self) -> None:
        from modules.m1_site.site_config import save_site
        from core.database import get_connection

        rows_to_save: list[tuple[int, dict]] = []
        for row in range(self._table.rowCount()):
            data = self._parse_row(row)
            if data is None:
                continue
            rows_to_save.append((row, data))

        if not rows_to_save:
            self._status_lbl.setText("No valid rows to save.")
            self._status_lbl.setStyleSheet("color: #f59e0b; font-style: italic;")
            return

        saved = 0
        newly_created_ids: list[int] = []
        for row, data in rows_to_save:
            existing_id = self._row_ids[row] if row < len(self._row_ids) else None
            try:
                if existing_id is not None:
                    conn = get_connection()
                    conn.execute(
                        "UPDATE sites SET name=?, lat=?, lon=?, bbox_nm=?, "
                        "platform_id=?, notes=? WHERE id=?",
                        (data["name"], data["lat"], data["lon"], data["bbox_nm"],
                         data["platform_id"], data["notes"], existing_id),
                    )
                    conn.commit()
                    conn.close()
                    site_id = existing_id
                else:
                    site = Site(
                        lat=data["lat"], lon=data["lon"],
                        name=data["name"],
                        bbox_nm=data["bbox_nm"],
                        platform_id=data["platform_id"],
                        notes=data["notes"],
                    )
                    site_id = save_site(site)
                    self._row_ids[row] = site_id
                    self.site_saved.emit(site_id)
                    newly_created_ids.append(site_id)

                self._set_row_status(row, "saved", site_id == self._active_id)
                saved += 1
            except Exception as exc:
                QMessageBox.critical(self, "Save Error",
                                     f"Row {row+1}: {exc}")

        self._status_lbl.setText(
            f"✓ {saved} site{'s' if saved!=1 else ''} saved to database."
        )
        self._status_lbl.setStyleSheet("color: #22c55e; font-weight: bold;")

        for site_id in newly_created_ids:
            self._prompt_first_vehicle(site_id)

    def _prompt_first_vehicle(self, site_id: int) -> None:
        """On first-time site creation, offer to associate a launch vehicle
        (pre-fill convenience only — writes to site_vehicles, same table the
        Analysis tab upserts into after a run). Skippable; never blocks save."""
        from core.database import get_connection

        try:
            conn = get_connection()
            vehicles = conn.execute(
                "SELECT id, name FROM vehicles ORDER BY name"
            ).fetchall()
            conn.close()
        except Exception:
            return

        if not vehicles:
            return

        combo = QComboBox()
        combo.setStyleSheet(_COMBO_STYLE)
        for v in vehicles:
            combo.addItem(v["name"], userData=v["id"])

        box = QMessageBox(self)
        box.setWindowTitle("Launch Vehicle")
        box.setText(
            "Which launch vehicle will be used at this site?\n"
            "(Optional — used to pre-fill the Analysis tab. You can skip this.)"
        )
        box.layout().addWidget(combo, 1, 1)
        skip_btn = box.addButton("Skip", QMessageBox.ButtonRole.RejectRole)
        ok_btn = box.addButton("Set Vehicle", QMessageBox.ButtonRole.AcceptRole)
        box.exec()

        if box.clickedButton() is not ok_btn:
            return

        vehicle_id = combo.currentData()
        if vehicle_id is None:
            return

        try:
            from datetime import datetime, timezone
            conn = get_connection()
            conn.execute(
                """
                INSERT INTO site_vehicles (site_id, vehicle_id, run_count, last_used)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(site_id, vehicle_id) DO UPDATE SET
                    last_used = excluded.last_used
                """,
                (site_id, vehicle_id, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass  # non-fatal — site is already saved regardless

    def _set_row_status(self, row: int, state: str, is_active: bool) -> None:
        if is_active:
            text, bg, fg = "Active ★", _STATUS_ACTIVE[0], _STATUS_ACTIVE[1]
        elif state == "saved":
            text, bg, fg = "Saved ✓", _STATUS_SAVED[0], _STATUS_SAVED[1]
        else:
            text, bg, fg = "Unsaved", _STATUS_UNSAVED[0], _STATUS_UNSAVED[1]

        item = self._table.item(row, _COL_STATUS)
        if item is None:
            item = _item(text, editable=False)
            self._table.setItem(row, _COL_STATUS, item)
        item.setText(text)
        item.setBackground(QColor(bg))
        item.setForeground(QColor(fg))

    # ── Context menu ──────────────────────────────────────────────────────────

    def _context_menu(self, pos) -> None:
        row = self._table.rowAt(pos.y())
        if row < 0:
            return

        menu = QMenu(self)

        act_dup = QAction("Duplicate Row", self)
        act_dup.triggered.connect(lambda: self._duplicate_row(row))
        menu.addAction(act_dup)

        is_saved = row < len(self._row_ids) and self._row_ids[row] is not None
        act_del = QAction("Delete Site (from database)" if is_saved else "Remove Row", self)
        act_del.triggered.connect(lambda: self._delete_row(row))
        menu.addAction(act_del)

        menu.addSeparator()

        act_copy = QAction("Copy Coordinates", self)
        act_copy.triggered.connect(lambda: self._copy_coords(row))
        menu.addAction(act_copy)

        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _duplicate_row(self, row: int) -> None:
        data = self._parse_row(row)
        if data is None:
            return
        new_row = self._table.rowCount()
        self._table.insertRow(new_row)
        self._row_ids.append(None)
        self._table.setItem(new_row, _COL_NUM,   _item(str(new_row + 1), editable=False))
        self._table.setItem(new_row, _COL_NAME,  _item(data["name"] + " (copy)"))
        self._table.setItem(new_row, _COL_LAT,   _item(_dd_to_ddm(data["lat"], True)))
        self._table.setItem(new_row, _COL_LON,   _item(_dd_to_ddm(data["lon"], False)))
        self._table.setItem(new_row, _COL_BBOX,  _item(f"{data['bbox_nm']:.1f}"))
        self._table.setItem(new_row, _COL_NOTES, _item(data["notes"]))
        combo = self._platform_combo(data["platform_id"])
        self._table.setCellWidget(new_row, _COL_PLATFORM, combo)
        self._set_row_status(new_row, "unsaved", False)
        self._set_vehicles_cell(new_row, None)

    _ASSOC_LABELS = {
        "project_sites": ("project link", "project links"),
        "project_site_status_history": ("status history entry", "status history entries"),
        "site_vehicles": ("vehicle usage record", "vehicle usage records"),
        "voyage_schedules": ("voyage schedule", "voyage schedules"),
        "analyses": ("saved analysis result", "saved analysis results"),
        "reports": ("saved report", "saved reports"),
    }

    @classmethod
    def _describe_associations(cls, counts: dict) -> str:
        parts = []
        for table, count in counts.items():
            if count > 0:
                singular, plural = cls._ASSOC_LABELS[table]
                parts.append(f"{count} {singular if count == 1 else plural}")
        return ", ".join(parts)

    def _delete_row(self, row: int) -> None:
        site_id = self._row_ids[row] if row < len(self._row_ids) else None

        if site_id is None:
            # Unsaved row — nothing in the database yet, just remove it locally.
            self._table.removeRow(row)
            if row < len(self._row_ids):
                self._row_ids.pop(row)
            self._refresh_row_numbers()
            return

        name_item = self._table.item(row, _COL_NAME)
        name = name_item.text() if name_item else ""

        from modules.m1_site.site_config import get_site_associations
        assoc = get_site_associations(site_id)
        assoc_text = self._describe_associations(assoc)

        if assoc_text:
            msg = (
                f"'{name or 'this site'}' is still linked to: {assoc_text}.\n\n"
                "Deleting it will permanently remove all of these along with "
                "the site — including status history. This cannot be undone. "
                "(Any previously generated report PDF files stay on disk, "
                "just no longer linked to this site.)\n\nDelete anyway?"
            )
        else:
            msg = (
                f"Permanently delete '{name or 'this site'}' from the database? "
                "This cannot be undone."
            )
        reply = QMessageBox.question(
            self, "Delete Site", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        ok, error = self._delete_site_row(row, site_id)
        if not ok:
            QMessageBox.critical(
                self, "Cannot Delete Site",
                f"This site could not be deleted — {error}."
            )
            return
        self._refresh_row_numbers()

    def _delete_site_row(self, row: int, site_id: int) -> tuple[bool, str]:
        """
        Delete a saved site's DB record (and any associations blocking it —
        project links, status history, vehicle usage, voyage schedules,
        analyses, reports) and remove its table row. Returns
        (success, error_message) — the error message is always plain
        language, never a raw exception string. Does NOT show any dialogs —
        callers own confirmation/error UI so single-row and batch deletes
        can each present one dialog instead of one per row.
        """
        from modules.m1_site.site_config import delete_site_cascade
        try:
            delete_site_cascade(site_id)
        except Exception:
            return False, "an unexpected database error occurred"

        if site_id == self._active_id:
            from core.settings import set_session
            set_session("active_site_id", "")
            set_session("active_project_id", "")
            self.mw.site = None
            self.mw.active_project_id = None
            self.mw.on_site_changed()

        self._table.removeRow(row)
        self._row_ids.pop(row)
        return True, ""

    def _copy_coords(self, row: int) -> None:
        data = self._parse_row(row)
        if data is None:
            return
        text = f"{_dd_to_ddm(data['lat'], True)},  {_dd_to_ddm(data['lon'], False)}"
        QApplication.clipboard().setText(text)
        self._status_lbl.setText(f"Copied: {text}")
        self._status_lbl.setStyleSheet("color: #94a3b8; font-style: italic;")

    # ── Vehicle slot ───────────────────────────────────────────────────────────

    def _on_vehicle_changed(self, idx: int) -> None:
        v = self.vehicle_combo.itemData(idx)
        if v is not None:
            self.mw.vehicle = v

    # ── By Project: project combo population ───────────────────────────────────

    def _populate_project_combo(self) -> None:
        try:
            from core.database import get_connection
            conn = get_connection()
            rows = conn.execute(
                "SELECT id, name, status FROM projects ORDER BY updated_at DESC, id DESC"
            ).fetchall()
            conn.close()
        except Exception:
            rows = []

        current_id = self._proj_combo.currentData()

        self._proj_combo.blockSignals(True)
        self._proj_combo.clear()
        self._proj_combo.addItem("— select project —", userData=None)
        for row in rows:
            label = f"{row['name']}  —  {row['status'].replace('_', ' ').title()}"
            self._proj_combo.addItem(label, userData=row["id"])
        self._proj_combo.blockSignals(False)

        # Restore previous selection if still present
        if current_id is not None:
            idx = self._proj_combo.findData(current_id)
            self._proj_combo.setCurrentIndex(idx if idx >= 0 else 0)
        else:
            self._proj_combo.setCurrentIndex(0)

        # Trigger display update
        self._on_project_combo_changed(self._proj_combo.currentIndex())

    def _on_project_combo_changed(self, index: int) -> None:
        project_id = self._proj_combo.currentData()
        if project_id is None:
            self._proj_empty_lbl.show()
            self._proj_table.hide()
        else:
            self._proj_empty_lbl.hide()
            self._proj_table.show()
            self._refresh_project_table()

    def _refresh_project_table(self) -> None:
        project_id = self._proj_combo.currentData()
        if project_id is None:
            return

        status_filter = self._status_filter_combo.currentData()

        from modules.m1_site.project_sites import list_project_sites
        try:
            sites = list_project_sites(project_id, status_filter=status_filter)
        except Exception:
            sites = []

        from core.database import get_connection
        conn = get_connection()
        try:
            prow = conn.execute(
                "SELECT status FROM projects WHERE id=?", (project_id,)
            ).fetchone()
        finally:
            conn.close()
        project_status = prow["status"] if prow else None

        self._proj_table.setRowCount(len(sites))
        for row_idx, site in enumerate(sites):
            # Site Name
            self._proj_table.setItem(row_idx, 0, _pitem(site.get("site_name", "")))
            # Coord Code
            self._proj_table.setItem(row_idx, 1, _pitem(site.get("coord_code") or "—"))
            # Latitude (DDM)
            lat = site.get("lat") or 0.0
            self._proj_table.setItem(row_idx, 2, _pitem(_dd_to_ddm(lat, True)))
            # Longitude (DDM)
            lon = site.get("lon") or 0.0
            self._proj_table.setItem(row_idx, 3, _pitem(_dd_to_ddm(lon, False)))
            # Bbox NM
            bbox = site.get("bbox_nm") or 25.0
            self._proj_table.setItem(row_idx, 4, _pitem(f"{bbox:.1f}"))
            # Vessel Platform
            self._proj_table.setItem(row_idx, 5, _pitem(site.get("platform_name") or "—"))
            # Status badge
            status = site.get("status", "candidate")
            st_item = _pitem(status.replace("_", " ").title())
            bg_hex, fg_hex = _PROJ_STATUS_COLORS.get(status, ("#374151", "#94a3b8"))
            st_item.setBackground(QColor(bg_hex))
            st_item.setForeground(QColor(fg_hex))
            self._proj_table.setItem(row_idx, 6, st_item)
            # Status Changed (date portion only)
            changed = str(site.get("updated_at", ""))[:10]
            self._proj_table.setItem(row_idx, 7, _pitem(changed))
            # History — "N entries", clickable
            count = site.get("history_count") or 0
            entry_word = "entry" if count == 1 else "entries"
            hist_item = _pitem(f"{count} {entry_word}", fg="#93c5fd")
            hist_item.setData(Qt.ItemDataRole.UserRole, site["site_id"])
            self._proj_table.setItem(row_idx, _PCOL_HIST, hist_item)
            # Vehicles Used — same site_vehicles lookup as All Sites mode
            veh_text, veh_tip = _vehicles_used_display(site.get("site_id"))
            v_item = _pitem(veh_text, fg="#64748b" if veh_text == "—" else "#e2e8f0")
            if veh_tip:
                v_item.setToolTip(veh_tip)
            self._proj_table.setItem(row_idx, _PCOL_VEH, v_item)
            # Activate — per-row, guarded by parent project status + candidate status
            site_id = site["site_id"]
            btn = QPushButton("Activate")
            btn.setStyleSheet(_BTN_SECONDARY)
            reasons = _activation_guard_reasons(project_status, status)
            if reasons:
                btn.setEnabled(False)
                btn.setToolTip("Cannot activate: " + "; ".join(reasons) + ".")
            else:
                btn.clicked.connect(
                    lambda _checked=False, pid=project_id, sid=site_id:
                        self._on_activate_site(pid, sid)
                )
            self._proj_table.setCellWidget(row_idx, _PCOL_ACTIVATE, btn)

        self._proj_table.resizeColumnsToContents()
        self._proj_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._refresh_active_indicator()

    # ── Candidate site removal (By Project view) ─────────────────────────────

    def _proj_context_menu(self, pos) -> None:
        row = self._proj_table.rowAt(pos.y())
        if row < 0:
            return
        hist_item = self._proj_table.item(row, _PCOL_HIST)
        site_id = hist_item.data(Qt.ItemDataRole.UserRole) if hist_item else None
        if site_id is None:
            return
        name_item = self._proj_table.item(row, 0)
        site_name = name_item.text() if name_item else ""

        menu = QMenu(self)
        act_remove = QAction("Remove from Project", self)
        act_remove.triggered.connect(
            lambda: self._on_remove_from_project(site_id, site_name)
        )
        menu.addAction(act_remove)
        menu.exec(self._proj_table.viewport().mapToGlobal(pos))

    def _on_remove_from_project(self, site_id: int, site_name: str) -> None:
        project_id = self._proj_combo.currentData()
        if project_id is None:
            return
        reply = QMessageBox.question(
            self, "Remove Site",
            f"Remove '{site_name or 'this site'}' from this project's "
            "candidate list? The site itself is not deleted — only its "
            "association with this project.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        from modules.m1_site.project_sites import remove_site_from_project
        try:
            remove_site_from_project(project_id, site_id)
        except Exception:
            QMessageBox.critical(
                self, "Error",
                "This site could not be removed from the project. Please try again."
            )
            return

        if site_id == self._active_id:
            from core.settings import set_session
            set_session("active_site_id", "")
            set_session("active_project_id", "")
            self.mw.site = None
            self.mw.active_project_id = None
            self.mw.on_site_changed()

        self._refresh_project_table()

    # ── Activate / Deactivate (site+project pairing) ─────────────────────────

    def _on_activate_site(self, project_id: int, site_id: int) -> None:
        from core.settings import set_session
        from modules.m1_site.site_config import get_site
        try:
            site = get_site(site_id)
        except Exception as exc:
            QMessageBox.critical(self, "Activate Error", str(exc))
            return

        set_session("active_site_id", str(site_id))
        set_session("active_project_id", str(project_id))
        self.mw.site = site
        self.mw.active_project_id = project_id
        self.mw.on_site_changed()
        self._refresh_active_indicator()

    def _on_deactivate_site(self) -> None:
        from core.settings import set_session
        set_session("active_site_id", "")
        set_session("active_project_id", "")
        self.mw.site = None
        self.mw.active_project_id = None
        self.mw.on_site_changed()
        self._refresh_active_indicator()

    def _refresh_active_indicator(self) -> None:
        """Sync the Deactivate button visibility and status label to the
        current site+project pairing (or lack thereof) in session_state."""
        from core.settings import get_session
        active = bool(get_session("active_site_id", ""))
        self._deactivate_btn.setVisible(active)
        if active and self.mw.site:
            self._active_status_lbl.setText(
                f"Active: {self.mw.site.name or self.mw.site.coord_str}"
            )
            self._active_status_lbl.setStyleSheet(
                "color: #93c5fd; font-weight: bold; font-size: 8pt;"
            )
        else:
            self._active_status_lbl.setText("No active site.")
            self._active_status_lbl.setStyleSheet(
                "color: #64748b; font-style: italic; font-size: 8pt;"
            )

    def _on_proj_table_cell_clicked(self, row: int, col: int) -> None:
        if col != _PCOL_HIST:
            return
        item = self._proj_table.item(row, col)
        if not item:
            return
        site_id = item.data(Qt.ItemDataRole.UserRole)
        if site_id is None:
            return
        project_id = self._proj_combo.currentData()
        if project_id is None:
            return
        from ui.dialogs.site_history_viewer import SiteHistoryViewer
        dlg = SiteHistoryViewer(project_id, site_id, parent=self)
        dlg.exec()

    def _on_refresh_project_view(self) -> None:
        self._populate_project_combo()

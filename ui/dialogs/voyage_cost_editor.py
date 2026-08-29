"""
ui/dialogs/voyage_cost_editor.py -- Voyage cost parameter editor (Ports page popup).

Four tabs cover every adjustable input of the voyage cost model:

    Route      -- port roles, speed, and the resulting leg table (on-site days)
    Vessels    -- charter rate / hire days / fuel rates per vessel
    Port Fees  -- six fee categories per port role
    Summary    -- live breakdown plus economy-of-scale per-launch pricing

Transit days (distance / speed / 24) and leg distances are computed, never
editable.  Everything else is user-driven.  Values persist to the settings
table as a single JSON blob via modules.m4_ports.voyage.save_params().
"""
from typing import Dict, List, Optional

from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout, QFormLayout,
    QWidget, QLabel, QTabWidget, QComboBox, QCompleter, QCheckBox,
    QDoubleSpinBox, QSpinBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QScrollArea, QFrame, QAbstractItemView, QLineEdit,
)
from PyQt6.QtCore import Qt

from core.models import (
    Site, Port, VoyageLeg,
    PORT_ROLE_LABELS, SELECTABLE_PORT_ROLES, PORT_ROLES,
    FEE_CATEGORIES, FEE_CATEGORY_LABELS,
)
from modules.m4_ports.voyage import (
    VoyageCostParams, load_params, save_params,
    build_voyage_legs, compute_voyage_cost,
)
from ui.styles import apply_table_colors


_BTN_PRIMARY = (
    "QPushButton { background:#2563eb; color:white; border-radius:4px;"
    "padding:6px 16px; font-weight:bold; border:none; }"
    "QPushButton:hover { background:#1d4ed8; }"
)
_COMBO_STYLE = (
    "QComboBox { background:#1a2233; color:#e2e8f0; border:1px solid #374151;"
    " border-radius:3px; padding:4px 8px; }"
    "QComboBox::drop-down { border:none; width:18px; }"
    "QComboBox QAbstractItemView { background:#1a2233; color:#e2e8f0;"
    " selection-background-color:#2563eb; }"
)
_SPIN_STYLE = (
    "QDoubleSpinBox, QSpinBox { background:#1a2233; color:#e2e8f0;"
    " border:1px solid #374151; border-radius:3px; padding:2px 4px; }"
)
_NOTES_STYLE = (
    "QLineEdit { background:#1a2233; color:#e2e8f0; border:1px solid #374151;"
    " border-radius:3px; padding:4px 6px; }"
    "QLineEdit:focus { border-color:#2563eb; }"
)
_HINT_STYLE = "color:#64748b; font-size:8pt; font-style:italic;"
_NONE_LABEL = "— none —"

# Roles the route always needs; the rest are optional and collapse out when unset.
_REQUIRED_HINT = {
    "mob":       "Optional. Voyage start; no on-site days are billed at the origin.",
    "load":      "Defaults to the port selected in the nearest-ports table.",
    "staging":   "Optional. Sits between the load port and the launch site.",
    "discharge": "Defaults to the port selected in the nearest-ports table.",
    "demob":     "Optional. Final arrival port.",
}


def _ro_item(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    item.setForeground(Qt.GlobalColor.white)
    return item


def _money_spin(hi: float = 10_000_000.0, decimals: int = 2) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(0.0, hi)
    s.setDecimals(decimals)
    s.setPrefix("$")
    s.setGroupSeparatorShown(True)
    s.setStyleSheet(_SPIN_STYLE)
    return s


def _days_spin(hi: float = 365.0) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(0.0, hi)
    s.setDecimals(2)
    s.setSuffix(" d")
    s.setStyleSheet(_SPIN_STYLE)
    return s


def _gal_spin() -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(0.0, 100_000.0)
    s.setDecimals(2)
    s.setSuffix(" gal/d")
    s.setStyleSheet(_SPIN_STYLE)
    return s


def _notes_edit() -> QLineEdit:
    edit = QLineEdit()
    edit.setPlaceholderText("Optional notes…")
    edit.setStyleSheet(_NOTES_STYLE)
    return edit


def breakdown_summary_html(b) -> str:
    """Render a VoyageCostBreakdown as the shared rich-text cost summary.

    Used by both this dialog's Summary tab and the Ports tab breakdown panel so
    the two can never drift apart.
    """
    if isinstance(b, dict):
        return breakdown_summary_html_from_dict(b)
    return breakdown_summary_html_from_dict(_breakdown_object_to_dict(b))


def _breakdown_object_to_dict(b) -> dict:
    from modules.m4_ports.voyage import serialize_breakdown
    return serialize_breakdown(b)


def breakdown_summary_html_from_dict(d: dict) -> str:
    """Render a serialised breakdown dict as rich-text HTML."""
    rows = []

    def row(label, value, indent=0, bold=False):
        pad = 18 * indent
        style = "font-weight:bold;" if bold else ""
        rows.append(
            f"<tr><td style='padding:2px 0 2px {pad}px;{style}'>{label}</td>"
            f"<td align='right' style='padding:2px 0 2px 24px;{style}'>{value}</td></tr>"
        )

    charter_total = float(d.get("charter_total_usd") or 0.0)
    port_fees_total = float(d.get("port_fees_total_usd") or 0.0)
    fuel_total = float(d.get("fuel_total_usd") or 0.0)
    total_usd = float(d.get("total_usd") or 0.0)
    launches = int(d.get("launches") or 1)
    cost_per_launch = float(d.get("cost_per_launch_usd") or 0.0)
    legs = d.get("legs") or []
    vessels = d.get("vessels") or []
    port_fees = d.get("port_fees") or []

    row("Charter Hire", f"${charter_total:,.2f}", bold=True)
    for line in vessels:
        if line.get("deployed"):
            row(
                f"{line.get('name', line.get('key', ''))} — "
                f"{float(line.get('charter_days') or 0.0):.2f} d x "
                f"${float(line.get('charter_rate_usd_day') or 0.0):,.0f}/d",
                f"${float(line.get('charter_usd') or 0.0):,.2f}",
                indent=1,
            )
        else:
            row(f"{line.get('name', line.get('key', ''))} — not deployed", "$0.00", indent=1)

    row("Port Fees", f"${port_fees_total:,.2f}", bold=True)
    if any(float(pf.get("total_usd") or 0.0) for pf in port_fees):
        for pf in port_fees:
            total = float(pf.get("total_usd") or 0.0)
            if total:
                row(
                    PORT_ROLE_LABELS.get(pf.get("role", ""), pf.get("role", "")),
                    f"${total:,.2f}",
                    indent=1,
                )
    else:
        row("No fees entered for the visited ports", "$0.00", indent=1)

    underway_gal = float(d.get("underway_gal") or 0.0)
    onsite_gal = float(d.get("onsite_gal") or 0.0)
    fuel_total_gal = float(d.get("fuel_total_gal") or 0.0)
    row("Fuel", f"${fuel_total:,.2f}", bold=True)
    row(
        f"Underway {underway_gal:,.2f} gal + on-site {onsite_gal:,.2f} gal "
        f"= {fuel_total_gal:,.2f} gal",
        "",
        indent=1,
    )
    for line in vessels:
        if line.get("deployed") and float(line.get("total_gal") or 0.0):
            row(
                f"{line.get('name', line.get('key', ''))} — "
                f"{float(line.get('total_gal') or 0.0):,.2f} gal x "
                f"${float(line.get('fuel_usd_gal') or 0.0):,.2f}/gal",
                f"${float(line.get('fuel_usd') or 0.0):,.2f}",
                indent=1,
            )

    rows.append("<tr><td colspan='2'><hr style='border:1px solid #374151;'></td></tr>")
    row("TOTAL VOYAGE COST", f"${total_usd:,.2f}", bold=True)
    row(
        f"Per launch ({launches} launch{'es' if launches != 1 else ''})",
        f"${cost_per_launch:,.2f}",
        indent=1,
    )

    total_distance = float(d.get("total_distance_nm") or 0.0)
    total_transit = float(d.get("total_transit_days") or 0.0)
    total_onsite = float(d.get("total_onsite_days") or 0.0)
    voyage_days = float(d.get("voyage_days") or 0.0)
    speed_kts = float(d.get("speed_kts") or 0.0)
    header = (
        f"<div style='color:#94a3b8;'>"
        f"{len(legs)} leg(s) &nbsp;|&nbsp; {total_distance:,.0f} NM "
        f"&nbsp;|&nbsp; {total_transit:.2f} transit + "
        f"{total_onsite:.2f} on-site = {voyage_days:.2f} voyage days "
        f"at {speed_kts:g} kts</div><br>"
    )
    return header + "<table width='100%'>" + "".join(rows) + "</table>"


def _section_sep(title: str) -> QWidget:
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 8, 0, 2)
    lay.setSpacing(2)
    lbl = QLabel(title)
    lbl.setStyleSheet(
        "color:#64748b; font-size:9px; font-weight:bold; letter-spacing:1px;"
    )
    lay.addWidget(lbl)
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("background:#374151; max-height:1px;")
    lay.addWidget(line)
    return box


class VoyageCostEditorDialog(QDialog):
    """Editor for the full VoyageCostParams set.

    Height is capped rather than sized to content so adding fields later cannot
    push the button bar off screen (same pattern as ContractEditorDialog).
    """

    def __init__(self, site: Optional[Site] = None,
                 candidate_port: Optional[Port] = None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Voyage Cost Parameters")
        self.setMinimumWidth(880)
        self.setMinimumHeight(700)
        self.setMaximumHeight(820)
        self.resize(940, 760)

        self._site = site
        self._candidate = candidate_port
        self.params = load_params()
        self._legs: List[VoyageLeg] = []
        self._loading = True

        # Cached WPI ports so live recalculation never touches the DB.
        self._ports_by_id: Dict[int, Port] = {}
        try:
            from modules.m4_ports.proximity import search_ports
            self._ports_by_id = {
                p.id: p for p in search_ports("", limit=10_000) if p.id is not None
            }
        except Exception:
            self._ports_by_id = {}

        self._role_combos: Dict[str, QComboBox] = {}
        self._onsite_spins: Dict[str, QDoubleSpinBox] = {}
        self._vessel_widgets: Dict[str, dict] = {}
        self._fee_spins: Dict[str, Dict[str, QDoubleSpinBox]] = {}
        self._fee_notes: Dict[str, QLineEdit] = {}

        self._build()
        self._load_from_params()
        self._loading = False
        self._rebuild_route()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setStyleSheet("background:#151c27; border-bottom:1px solid #374151;")
        hl = QVBoxLayout(header)
        hl.setContentsMargins(20, 14, 20, 12)
        title = QLabel("Voyage Cost Parameters")
        title.setStyleSheet("font-size:14px; font-weight:bold; color:#f1f5f9;")
        hl.addWidget(title)
        sub = QLabel(
            "Total = charter hire (per vessel) + port fees + fuel.  "
            "Leg distances and transit days are computed and cannot be edited."
        )
        sub.setStyleSheet("color:#94a3b8; font-size:9pt;")
        hl.addWidget(sub)
        root.addWidget(header)

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            "QTabWidget::pane { border:none; background:#0f1923; }"
            "QTabBar::tab { background:#1a2233; color:#94a3b8; padding:7px 18px;"
            " border:1px solid #374151; border-bottom:none; }"
            "QTabBar::tab:selected { background:#0f1923; color:#f1f5f9;"
            " font-weight:bold; }"
        )
        self._tabs.addTab(self._build_route_tab(), "Route")
        self._tabs.addTab(self._build_vessels_tab(), "Vessels")
        self._tabs.addTab(self._build_fees_tab(), "Port Fees")
        self._tabs.addTab(self._build_summary_tab(), "Summary")
        root.addWidget(self._tabs, 1)

        # Button bar lives outside every scroll area so it stays pinned.
        bar = QWidget()
        bar.setStyleSheet("background:#151c27; border-top:1px solid #374151;")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(20, 10, 20, 10)
        self._footer_lbl = QLabel("")
        self._footer_lbl.setStyleSheet("color:#93c5fd; font-size:9pt;")
        bl.addWidget(self._footer_lbl)
        bl.addStretch()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setStyleSheet(_BTN_PRIMARY)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        bl.addWidget(buttons)
        root.addWidget(bar)

    def _scrolled(self, content: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border:none; background:transparent; }")
        content.setStyleSheet("background:transparent;")
        scroll.setWidget(content)
        return scroll

    # ── Tab 1: Route ──────────────────────────────────────────────────────────

    def _build_route_tab(self) -> QWidget:
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(20, 14, 20, 14)
        lay.setSpacing(8)

        site_txt = (
            f"Launch site: {self._site.coord_str}" if self._site
            else "No launch site active — activate a site to see leg distances."
        )
        self._site_lbl = QLabel(site_txt)
        self._site_lbl.setStyleSheet("color:#94a3b8;")
        lay.addWidget(self._site_lbl)

        lay.addWidget(_section_sep("SPEED"))
        form = QFormLayout()
        form.setSpacing(8)
        self._speed_spin = QDoubleSpinBox()
        self._speed_spin.setRange(0.5, 40.0)
        self._speed_spin.setDecimals(2)
        self._speed_spin.setSuffix(" kts")
        self._speed_spin.setStyleSheet(_SPIN_STYLE)
        self._speed_spin.valueChanged.connect(self._refresh_computed)
        form.addRow("Transit speed:", self._speed_spin)
        lay.addLayout(form)
        speed_hint = QLabel(
            "Transit days per leg = distance (NM) / speed (kts) / 24.  "
            "This formula is fixed; speed is the only input to it."
        )
        speed_hint.setStyleSheet(_HINT_STYLE)
        speed_hint.setWordWrap(True)
        lay.addWidget(speed_hint)

        lay.addWidget(_section_sep("PORT ROLES"))
        roles_form = QFormLayout()
        roles_form.setSpacing(8)
        for role in SELECTABLE_PORT_ROLES:
            combo = self._make_port_combo()
            combo.currentIndexChanged.connect(self._on_route_changed)
            self._role_combos[role] = combo
            row = QWidget()
            rl = QVBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(1)
            rl.addWidget(combo)
            hint = QLabel(_REQUIRED_HINT[role])
            hint.setStyleSheet(_HINT_STYLE)
            rl.addWidget(hint)
            roles_form.addRow(f"{PORT_ROLE_LABELS[role]}:", row)
        lay.addLayout(roles_form)

        lay.addWidget(_section_sep("LEGS"))
        self._legs_table = QTableWidget(0, 5)
        self._legs_table.setHorizontalHeaderLabels(
            ["From", "To", "Distance (NM)", "Transit (days)", "On-Site Days"]
        )
        self._legs_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._legs_table.verticalHeader().setVisible(False)
        self._legs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._legs_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._legs_table.setMinimumHeight(200)
        apply_table_colors(self._legs_table)
        lay.addWidget(self._legs_table)

        self._legs_total_lbl = QLabel("")
        self._legs_total_lbl.setStyleSheet("color:#f1f5f9; font-weight:bold;")
        lay.addWidget(self._legs_total_lbl)

        legs_hint = QLabel(
            "On-site days belong to each leg's destination, so the first stop "
            "(the voyage origin) is never billed on-site time."
        )
        legs_hint.setStyleSheet(_HINT_STYLE)
        legs_hint.setWordWrap(True)
        lay.addWidget(legs_hint)

        lay.addStretch()
        return self._scrolled(content)

    def _make_port_combo(self) -> QComboBox:
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        combo.setStyleSheet(_COMBO_STYLE)
        combo.addItem(_NONE_LABEL, None)
        for port in sorted(self._ports_by_id.values(), key=lambda p: p.port_name):
            combo.addItem(f"{port.port_name} ({port.country})", port.id)
        completer = combo.completer()
        if completer is not None:
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        return combo

    # ── Tab 2: Vessels ────────────────────────────────────────────────────────

    def _build_vessels_tab(self) -> QWidget:
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(20, 14, 20, 14)
        lay.setSpacing(8)

        intro = QLabel(
            "The Gateway platform bills the full voyage (transit + on-site days). "
            "Support vessels have independent on-hire/off-hire windows, so they "
            "bill only their own hire days — but they still burn fuel across every "
            "leg while deployed."
        )
        intro.setStyleSheet("color:#94a3b8;")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        for v in self.params.vessels:
            lay.addWidget(_section_sep(v.name.upper()))
            grid = QFormLayout()
            grid.setSpacing(8)

            deployed = QCheckBox("Deployed on this voyage")
            deployed.setStyleSheet("color:#e2e8f0;")
            deployed.toggled.connect(
                lambda checked, key=v.key: self._on_deployed_toggled(key, checked)
            )
            grid.addRow("", deployed)

            rate = _money_spin(1_000_000.0, decimals=0)
            rate.setSuffix(" /day")
            rate.valueChanged.connect(self._refresh_computed)
            grid.addRow("Charter rate:", rate)

            days_row = QWidget()
            dr = QHBoxLayout(days_row)
            dr.setContentsMargins(0, 0, 0, 0)
            dr.setSpacing(8)
            days = _days_spin()
            days.valueChanged.connect(self._refresh_computed)
            dr.addWidget(days)
            days_note = QLabel("")
            days_note.setStyleSheet(_HINT_STYLE)
            dr.addWidget(days_note, 1)
            grid.addRow("Hire days:", days_row)

            at_sea = _gal_spin()
            at_sea.valueChanged.connect(self._refresh_computed)
            grid.addRow("At-sea consumption:", at_sea)

            in_port = _gal_spin()
            in_port.valueChanged.connect(self._refresh_computed)
            grid.addRow("In-port consumption:", in_port)

            price = _money_spin(1_000.0, decimals=2)
            price.setSuffix(" /gal")
            price.valueChanged.connect(self._refresh_computed)
            grid.addRow("Fuel price:", price)

            result = QLabel("")
            result.setStyleSheet("color:#93c5fd; font-size:9pt;")
            result.setWordWrap(True)
            grid.addRow("", result)

            lay.addLayout(grid)
            self._vessel_widgets[v.key] = {
                "deployed": deployed, "rate": rate, "days": days,
                "days_note": days_note, "at_sea": at_sea, "in_port": in_port,
                "price": price, "result": result,
                "full_voyage": v.charter_days is None,
            }

        lay.addStretch()
        return self._scrolled(content)

    def _on_deployed_toggled(self, key: str, checked: bool) -> None:
        w = self._vessel_widgets.get(key)
        if w:
            for name in ("rate", "days", "at_sea", "in_port", "price"):
                w[name].setEnabled(checked)
            if w["full_voyage"]:
                w["days"].setEnabled(False)
        self._refresh_computed()

    # ── Tab 3: Port Fees ──────────────────────────────────────────────────────

    def _build_fees_tab(self) -> QWidget:
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(20, 14, 20, 14)
        lay.setSpacing(8)

        intro = QLabel(
            "Six flat fee categories per port call.  Fees are only charged for "
            "roles the route actually visits, so values left on an unused role "
            "have no effect until that port is selected."
        )
        intro.setStyleSheet("color:#94a3b8;")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        headers = ["Port Role"] + [FEE_CATEGORY_LABELS[c] for c in FEE_CATEGORIES] \
            + ["Row Total", "Notes"]
        col_row_total = 1 + len(FEE_CATEGORIES)
        col_notes = col_row_total + 1
        self._fees_table = QTableWidget(len(PORT_ROLES), len(headers))
        self._fees_table.setHorizontalHeaderLabels(headers)
        self._fees_table.verticalHeader().setVisible(False)
        self._fees_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._fees_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        hdr = self._fees_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(col_row_total, QHeaderView.ResizeMode.ResizeToContents)
        apply_table_colors(self._fees_table)

        self._fee_total_items: Dict[str, QTableWidgetItem] = {}
        for row, role in enumerate(PORT_ROLES):
            self._fees_table.setRowHeight(row, 34)
            self._fees_table.setItem(row, 0, _ro_item(PORT_ROLE_LABELS[role]))
            self._fee_spins[role] = {}
            for col, cat in enumerate(FEE_CATEGORIES, start=1):
                spin = _money_spin(5_000_000.0, decimals=0)
                spin.valueChanged.connect(self._refresh_computed)
                self._fee_spins[role][cat] = spin
                self._fees_table.setCellWidget(row, col, spin)
            total_item = _ro_item("$0")
            self._fee_total_items[role] = total_item
            self._fees_table.setItem(row, col_row_total, total_item)
            notes_edit = _notes_edit()
            self._fee_notes[role] = notes_edit
            self._fees_table.setCellWidget(row, col_notes, notes_edit)

        self._fees_table.setMinimumHeight(260)
        lay.addWidget(self._fees_table)

        self._fees_total_lbl = QLabel("")
        self._fees_total_lbl.setStyleSheet("color:#f1f5f9; font-weight:bold;")
        lay.addWidget(self._fees_total_lbl)

        lay.addStretch()
        return self._scrolled(content)

    # ── Tab 4: Summary ────────────────────────────────────────────────────────

    def _build_summary_tab(self) -> QWidget:
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(20, 14, 20, 14)
        lay.setSpacing(10)

        self._summary_lbl = QLabel("")
        self._summary_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._summary_lbl.setWordWrap(True)
        self._summary_lbl.setStyleSheet(
            "color:#e2e8f0; background:#1a2233; border:1px solid #374151;"
            " border-radius:4px; padding:12px;"
        )
        self._summary_lbl.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        lay.addWidget(self._summary_lbl)

        lay.addWidget(_section_sep("ECONOMY OF SCALE"))
        launch_row = QHBoxLayout()
        launch_row.addWidget(QLabel("Launches per voyage:"))
        self._launches_spin = QSpinBox()
        self._launches_spin.setRange(1, 50)
        self._launches_spin.setStyleSheet(_SPIN_STYLE)
        self._launches_spin.valueChanged.connect(self._refresh_computed)
        launch_row.addWidget(self._launches_spin)
        launch_row.addStretch()
        lay.addLayout(launch_row)

        self._launch_table = QTableWidget(0, 2)
        self._launch_table.setHorizontalHeaderLabels(["Launches", "Cost Per Launch"])
        self._launch_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._launch_table.verticalHeader().setVisible(False)
        self._launch_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._launch_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._launch_table.setMinimumHeight(160)
        apply_table_colors(self._launch_table)
        lay.addWidget(self._launch_table)

        lay.addStretch()
        return self._scrolled(content)

    # ── Load / read widget state ──────────────────────────────────────────────

    def _load_from_params(self) -> None:
        p = self.params
        self._speed_spin.setValue(p.speed_kts)
        self._launches_spin.setValue(p.launches)

        for role, combo in self._role_combos.items():
            pid = p.role_port_ids.get(role)
            idx = combo.findData(pid) if pid is not None else 0
            combo.setCurrentIndex(idx if idx >= 0 else 0)

        for v in p.vessels:
            w = self._vessel_widgets.get(v.key)
            if not w:
                continue
            w["rate"].setValue(v.charter_rate_usd_day)
            w["at_sea"].setValue(v.at_sea_gal_day)
            w["in_port"].setValue(v.in_port_gal_day)
            w["price"].setValue(v.fuel_usd_gal)
            if v.charter_days is None:
                w["days"].setEnabled(False)
                w["days_note"].setText("Bills the full voyage (transit + on-site).")
            else:
                w["days"].setValue(float(v.charter_days))
                w["days_note"].setText("Independent on-hire / off-hire window.")
            w["deployed"].setChecked(v.deployed)
            self._on_deployed_toggled(v.key, v.deployed)

        for role, spins in self._fee_spins.items():
            fees = p.fees_for(role)
            if fees is None:
                continue
            for cat, spin in spins.items():
                spin.setValue(fees.amount(cat))
            notes_edit = self._fee_notes.get(role)
            if notes_edit is not None:
                notes_edit.setText(fees.notes or "")

    def _selected_port(self, role: str) -> Optional[Port]:
        combo = self._role_combos.get(role)
        if combo is None:
            return None
        pid = combo.currentData()
        if pid is None:
            # The user may have typed a name rather than picking from the list.
            idx = combo.findText(combo.currentText())
            pid = combo.itemData(idx) if idx >= 0 else None
        if pid is None:
            return None
        return self._ports_by_id.get(pid)

    def _read_into_params(self) -> VoyageCostParams:
        """Copy widget state back into self.params and return it."""
        p = self.params
        p.speed_kts = self._speed_spin.value()
        p.launches = self._launches_spin.value()

        for role in SELECTABLE_PORT_ROLES:
            port = self._selected_port(role)
            p.role_port_ids[role] = port.id if port is not None else None

        for role, spin in self._onsite_spins.items():
            p.onsite_days[role] = spin.value()

        for v in p.vessels:
            w = self._vessel_widgets.get(v.key)
            if not w:
                continue
            v.deployed = w["deployed"].isChecked()
            v.charter_rate_usd_day = w["rate"].value()
            v.at_sea_gal_day = w["at_sea"].value()
            v.in_port_gal_day = w["in_port"].value()
            v.fuel_usd_gal = w["price"].value()
            if not w["full_voyage"]:
                v.charter_days = w["days"].value()

        for role, spins in self._fee_spins.items():
            fees = p.fees_for(role)
            if fees is None:
                continue
            for cat, spin in spins.items():
                setattr(fees, f"{cat}_usd", spin.value())
            notes_edit = self._fee_notes.get(role)
            if notes_edit is not None:
                fees.notes = notes_edit.text().strip()
        return p

    # ── Recalculation ─────────────────────────────────────────────────────────

    def _role_ports(self) -> Dict[str, Optional[Port]]:
        resolved = {r: self._selected_port(r) for r in SELECTABLE_PORT_ROLES}
        # Mirror runtime behaviour: an unset Load/Discharge falls back to the
        # port currently selected in the nearest-ports table.
        for role in ("load", "discharge"):
            if resolved.get(role) is None:
                resolved[role] = self._candidate
        return resolved

    def _on_route_changed(self) -> None:
        if self._loading:
            return
        self._rebuild_route()

    def _rebuild_route(self) -> None:
        """Rebuild the leg table.  Only called when the route shape changes, so
        on-site spin boxes are not recreated (and never lose focus) while the
        user is typing into them."""
        if self._site is None:
            self._legs = []
            self._legs_table.setRowCount(0)
            self._onsite_spins.clear()
            self._legs_total_lbl.setText("No launch site active — no legs to cost.")
            self._refresh_computed()
            return

        role_ports = self._role_ports()
        legs = build_voyage_legs(
            self._site, role_ports, self.params.onsite_days, self._speed_spin.value()
        )
        self._legs = legs
        self._onsite_spins.clear()
        self._legs_table.setRowCount(len(legs))
        for row, leg in enumerate(legs):
            self._legs_table.setRowHeight(row, 32)
            self._legs_table.setItem(row, 0, _ro_item(leg.from_name))
            self._legs_table.setItem(row, 1, _ro_item(leg.to_name))
            self._legs_table.setItem(row, 2, _ro_item(f"{leg.distance_nm:,.1f}"))
            self._legs_table.setItem(row, 3, _ro_item(f"{leg.transit_days:.2f}"))
            spin = _days_spin()
            spin.setValue(self.params.onsite_days.get(leg.to_role, 0.0))
            spin.valueChanged.connect(self._refresh_computed)
            self._onsite_spins[leg.to_role] = spin
            self._legs_table.setCellWidget(row, 4, spin)
        self._refresh_computed()

    def _refresh_computed(self) -> None:
        """Recompute in place: distances/transit cells, vessel lines, summary."""
        if self._loading:
            return
        params = self._read_into_params()

        if self._site is not None:
            self._legs = build_voyage_legs(
                self._site, self._role_ports(), params.onsite_days, params.speed_kts
            )
            for row, leg in enumerate(self._legs):
                if row >= self._legs_table.rowCount():
                    break
                self._legs_table.setItem(row, 2, _ro_item(f"{leg.distance_nm:,.1f}"))
                self._legs_table.setItem(row, 3, _ro_item(f"{leg.transit_days:.2f}"))

        port = self._candidate or Port(port_name="(no port)", lat=0.0, lon=0.0)
        site = self._site or Site(lat=0.0, lon=0.0, name="(no site)")
        breakdown = compute_voyage_cost(
            site, port, self._legs,
            vessels=params.vessels, port_fees=params.port_fees,
            speed_kts=params.speed_kts, launches=params.launches,
        )

        self._legs_total_lbl.setText(
            f"Totals:  {breakdown.total_distance_nm:,.0f} NM   |   "
            f"{breakdown.total_transit_days:.2f} transit days   |   "
            f"{breakdown.total_onsite_days:.2f} on-site days   |   "
            f"{breakdown.voyage_days:.2f} voyage days"
        )

        for role, item in self._fee_total_items.items():
            fees = params.fees_for(role)
            item.setText(f"${fees.total_usd:,.0f}" if fees else "$0")
        self._fees_total_lbl.setText(
            f"Port fees charged on this route: ${breakdown.port_fees_total_usd:,.0f}"
        )

        for line in breakdown.vessels:
            w = self._vessel_widgets.get(line.key)
            if not w:
                continue
            if w["full_voyage"]:
                w["days"].blockSignals(True)
                w["days"].setValue(line.charter_days if line.deployed
                                   else breakdown.voyage_days)
                w["days"].blockSignals(False)
            if not line.deployed:
                w["result"].setText("Not deployed — contributes $0.")
            else:
                w["result"].setText(
                    f"Charter ${line.charter_usd:,.0f}  "
                    f"({line.charter_days:.2f} d x ${line.charter_rate_usd_day:,.0f})"
                    f"   |   Fuel {line.total_gal:,.1f} gal "
                    f"(underway {line.underway_gal:,.1f} + on-site "
                    f"{line.onsite_gal:,.1f}) = ${line.fuel_usd:,.0f}"
                )

        self._summary_lbl.setText(breakdown_summary_html(breakdown))
        self._populate_launch_table(breakdown)
        self._footer_lbl.setText(
            f"Total voyage cost: {breakdown.total_formatted}   |   "
            f"${breakdown.cost_per_launch():,.0f} per launch"
        )

    def _populate_launch_table(self, b) -> None:
        max_n = max(3, b.launches)
        self._launch_table.setRowCount(max_n)
        for row, n in enumerate(range(1, max_n + 1)):
            self._launch_table.setRowHeight(row, 26)
            self._launch_table.setItem(row, 0, _ro_item(str(n)))
            item = _ro_item(f"${b.cost_per_launch(n):,.2f}")
            if n == b.launches:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            self._launch_table.setItem(row, 1, item)

    # ── Save ──────────────────────────────────────────────────────────────────

    def _on_save(self) -> None:
        params = self._read_into_params()
        try:
            save_params(params)
        except Exception as exc:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "Could not save",
                f"Parameters could not be written to the settings table:\n{exc}\n\n"
                "They will still apply for this session."
            )
        self.params = params
        self.accept()

    def get_params(self) -> VoyageCostParams:
        return self.params

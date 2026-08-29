"""
ui/ports_tab.py -- Tab 3: Port proximity search and voyage economics.
"""
import csv
import io
from datetime import datetime, date, timezone
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QGroupBox, QFrame,
    QHeaderView, QFileDialog, QMessageBox, QDateEdit, QScrollArea,
)
from PyQt6.QtCore import Qt, QDate, QTimer
from PyQt6.QtGui import QColor

from core.models import Port, VoyageCostBreakdown
from ui.styles import apply_table_colors


_SELECTED_ROW_COLOR = QColor(210, 228, 250)   # light blue — matches voyage_pdf.py highlight

_COL_REMOVE = 6   # ports_table column holding the per-row ✕ Remove button (Set 28)

_BTN_PRIMARY = (
    "QPushButton {"
    "  background: #0F2850; color: white;"
    "  border-radius: 4px; padding: 6px 20px; font-weight: bold;"
    "}"
    "QPushButton:hover  { background: #1A4080; }"
    "QPushButton:disabled { background: #B0B8C8; }"
)
_BTN_GREEN = (
    "QPushButton {"
    "  background: #1A6030; color: white;"
    "  border-radius: 4px; padding: 6px 20px; font-weight: bold;"
    "}"
    "QPushButton:hover  { background: #2A8040; }"
    "QPushButton:disabled { background: #B0B8C8; }"
)


class PortsTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._ports: list[Port] = []   # full result set from the last search
        self._costs: list[VoyageCostBreakdown] = []
        self._selected_port: Port | None = None
        self._excluded_port_ids: set = set()   # session-only exclusions (no DB)
        self._visible: list[Port] = []         # ports currently shown (rebuild cache)
        self._snackbar: QFrame | None = None
        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        title = QLabel("Ports && Voyage Economics")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #f1f5f9;")
        root.addWidget(title)

        self.site_label = QLabel(
            "No site selected.  Set coordinates in the Site & Vehicle tab."
        )
        self.site_label.setStyleSheet("color: #94a3b8;")
        root.addWidget(self.site_label)

        # Controls row
        ctrl = QHBoxLayout()

        self.find_btn = QPushButton("Find Nearest Ports")
        self.find_btn.setMinimumHeight(34)
        self.find_btn.setEnabled(False)
        self.find_btn.setStyleSheet(_BTN_PRIMARY)
        self.find_btn.clicked.connect(self._find_ports)
        ctrl.addWidget(self.find_btn)

        self.params_btn = QPushButton("Voyage Cost Settings…")
        self.params_btn.setMinimumHeight(34)
        self.params_btn.setStyleSheet(_BTN_PRIMARY)
        self.params_btn.clicked.connect(self._edit_params)
        ctrl.addWidget(self.params_btn)

        self.csv_btn = QPushButton("Compare All 5 Ports — Export CSV")
        self.csv_btn.setMinimumHeight(34)
        self.csv_btn.setEnabled(False)
        self.csv_btn.setStyleSheet(_BTN_PRIMARY)
        self.csv_btn.clicked.connect(self._export_csv)
        ctrl.addWidget(self.csv_btn)

        self.voyage_pdf_btn = QPushButton("Generate Voyage PDF")
        self.voyage_pdf_btn.setMinimumHeight(34)
        self.voyage_pdf_btn.setEnabled(False)
        self.voyage_pdf_btn.setStyleSheet(_BTN_GREEN)
        self.voyage_pdf_btn.clicked.connect(self._generate_voyage_pdf)
        ctrl.addWidget(self.voyage_pdf_btn)

        self.finalize_btn = QPushButton("Finalize Port for Project")
        self.finalize_btn.setMinimumHeight(34)
        self.finalize_btn.setEnabled(False)
        self.finalize_btn.setStyleSheet(_BTN_GREEN)
        self.finalize_btn.setToolTip(
            "Snapshot this port's voyage estimate for the active project + site."
        )
        self.finalize_btn.clicked.connect(self._finalize_port)
        ctrl.addWidget(self.finalize_btn)

        self.reset_btn = QPushButton("Show All Ports")
        self.reset_btn.setMinimumHeight(34)
        self.reset_btn.setStyleSheet(
            "QPushButton { background: #1e2d3d; color: #e2e8f0; border: 1px solid #374151;"
            " border-radius: 4px; padding: 6px 14px; }"
            "QPushButton:hover { background: #2d3f55; }"
        )
        self.reset_btn.clicked.connect(self._reset_exclusions)
        self.reset_btn.setVisible(False)   # only shown once something is excluded
        ctrl.addWidget(self.reset_btn)

        ctrl.addSpacing(12)
        dep_lbl = QLabel("Departure:")
        dep_lbl.setStyleSheet("color: #94a3b8;")
        ctrl.addWidget(dep_lbl)
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setStyleSheet(
            "QDateEdit { background:#1a2233; color:#e2e8f0; border:1px solid #374151;"
            " border-radius:3px; padding:4px 8px; }"
        )
        ctrl.addWidget(self.date_edit)

        ctrl.addStretch()
        root.addLayout(ctrl)

        # Port count / exclusion status line
        self.count_label = QLabel("")
        self.count_label.setStyleSheet("color: #94a3b8; font-size: 8pt;")
        root.addWidget(self.count_label)

        # ── Ports table ───────────────────────────────────────────────────────
        ports_group  = QGroupBox(
            "Nearest Qualifying Ports  (anchorage depth >= 10 m, fuel oil available)"
        )
        ports_layout = QVBoxLayout(ports_group)
        ports_layout.setContentsMargins(10, 10, 10, 10)

        self.ports_table = QTableWidget(0, 7)
        self.ports_table.setHorizontalHeaderLabels(
            ["Port Name", "Country", "Distance (NM)", "Bearing", "Size",
             "Anch. Depth", ""]
        )
        _phdr = self.ports_table.horizontalHeader()
        _phdr.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        _phdr.setSectionResizeMode(_COL_REMOVE, QHeaderView.ResizeMode.ResizeToContents)
        self.ports_table.verticalHeader().setVisible(False)
        self.ports_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.ports_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.ports_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.ports_table.itemSelectionChanged.connect(self._on_port_row_selected)
        apply_table_colors(self.ports_table)
        ports_layout.addWidget(self.ports_table)
        root.addWidget(ports_group, 1)

        # ── Voyage cost table ─────────────────────────────────────────────────
        voyage_group  = QGroupBox(
            "Voyage Economics  —  full multi-leg route costed per candidate "
            "Load / Discharge port"
        )
        voyage_layout = QVBoxLayout(voyage_group)
        voyage_layout.setContentsMargins(10, 10, 10, 10)

        self.voyage_table = QTableWidget(0, 5)
        self.voyage_table.setHorizontalHeaderLabels(
            ["Port Name", "Distance (NM)", "Total Transit (days)",
             "Total Voyage Cost", "Cost / Launch"]
        )
        self.voyage_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.voyage_table.verticalHeader().setVisible(False)
        self.voyage_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.voyage_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.voyage_table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                alternate-background-color: #f0f4f8;
                gridline-color: #cbd5e1;
                border: 1px solid #cbd5e1;
                color: #0f172a;
            }
            QHeaderView::section {
                background-color: #1e3a5f;
                color: #f1f5f9;
                font-size: 11px;
                font-weight: 500;
                padding: 6px 8px;
                border-bottom: 1px solid #374151;
                border-right: 1px solid #374151;
            }
        """)
        self.voyage_table.setAlternatingRowColors(True)
        voyage_layout.addWidget(self.voyage_table)
        root.addWidget(voyage_group, 1)

        # ── Cost breakdown for the selected port ──────────────────────────────
        breakdown_group  = QGroupBox("Cost Breakdown — selected port")
        breakdown_layout = QVBoxLayout(breakdown_group)
        breakdown_layout.setContentsMargins(10, 10, 10, 10)

        self.breakdown_label = QLabel(
            "Click a port row above to see its charter, port-fee and fuel breakdown."
        )
        self.breakdown_label.setTextFormat(Qt.TextFormat.RichText)
        self.breakdown_label.setWordWrap(True)
        self.breakdown_label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self.breakdown_label.setStyleSheet("color: #e2e8f0; padding: 4px;")

        # Capped scroll area: this label's sizeHint grows with its content, and
        # an uncapped one starves the tables above of vertical space.
        breakdown_scroll = QScrollArea()
        breakdown_scroll.setWidgetResizable(True)
        breakdown_scroll.setMaximumHeight(200)
        breakdown_scroll.setWidget(self.breakdown_label)
        breakdown_scroll.setStyleSheet(
            "QScrollArea { background:#1a2233; border:1px solid #374151;"
            " border-radius:4px; }"
        )
        breakdown_layout.addWidget(breakdown_scroll)
        root.addWidget(breakdown_group)

        # Selection indicator
        self.selection_label = QLabel("")
        self.selection_label.setStyleSheet("color: #93c5fd; font-style: italic;")
        root.addWidget(self.selection_label)

    # ── Slot called by MainWindow ─────────────────────────────────────────────

    def on_site_changed(self) -> None:
        if self.mw.site:
            self.site_label.setText(f"Site: {self.mw.site.coord_str}")
            self.find_btn.setEnabled(True)
        self._ports = []
        self._costs = []
        self._selected_port = None
        self._excluded_port_ids.clear()
        self._visible = []
        self._dismiss_snackbar()
        self.reset_btn.setVisible(False)
        self.count_label.setText("")
        self._clear_tables()
        self.voyage_pdf_btn.setEnabled(False)
        self.csv_btn.setEnabled(False)
        self.finalize_btn.setEnabled(False)
        self.selection_label.setText("")

    def on_project_changed(self) -> None:
        self._update_finalize_btn()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _clear_tables(self) -> None:
        self.ports_table.setRowCount(0)
        self.voyage_table.setRowCount(0)
        self.breakdown_label.setText(
            "Click a port row above to see its charter, port-fee and fuel breakdown."
        )

    def _edit_params(self) -> None:
        """Open the voyage cost parameter popup and re-cost with the new values."""
        from ui.dialogs.voyage_cost_editor import VoyageCostEditorDialog

        dlg = VoyageCostEditorDialog(
            site=getattr(self.mw, "site", None),
            candidate_port=self._selected_port,
            parent=self,
        )
        if dlg.exec() != VoyageCostEditorDialog.DialogCode.Accepted:
            return
        self.mw.status("Voyage cost parameters saved.")
        self._recost()

    def _recost(self) -> None:
        """Recalculate every candidate port against the saved parameters."""
        if not self.mw.site or not self._ports:
            return
        from modules.m4_ports.voyage import compare_port_options
        self._costs = compare_port_options(self.mw.site, self._ports)
        self._rebuild_port_cards()
        self._highlight_voyage_row()
        self._show_breakdown()
        self._update_finalize_btn()

    def _find_ports(self) -> None:
        if not self.mw.site:
            return
        from modules.m4_ports.proximity import nearest_ports
        from modules.m4_ports.voyage    import compare_port_options

        self.mw.status("Searching for nearest qualifying ports...")
        self._ports = nearest_ports(self.mw.site, n=5, min_depth_m=10.0, require_fuel=True)
        self._excluded_port_ids.clear()   # fresh search clears prior exclusions
        self.csv_btn.setEnabled(bool(self._ports))

        if not self._ports:
            self._clear_tables()
            self.voyage_pdf_btn.setEnabled(False)
            self.mw.status(
                "No qualifying ports found.  "
                "Import the WPI first: python scripts/import_wpi.py"
            )
            QMessageBox.warning(
                self, "No Ports Found",
                "No qualifying ports were found in the database.\n\n"
                "Import the NGA World Port Index first:\n"
                "  python scripts/import_wpi.py\n\n"
                "Download wpi.csv from:  https://msi.nga.mil/Publications/WPI\n"
                "Save it to:  data/wpi.csv"
            )
            return

        self._costs = compare_port_options(self.mw.site, self._ports)
        self._rebuild_port_cards()

        # Auto-select the nearest port (cheapest is first in voyage table)
        self._selected_port = self._ports[0]
        self.ports_table.selectRow(0)
        self.voyage_pdf_btn.setEnabled(True)
        self._show_breakdown()
        self._update_finalize_btn()
        self.mw.status(f"Found {len(self._ports)} qualifying port(s).")

    # ── Session-only exclusion (remove / undo / reset) ────────────────────────

    def _port_key(self, p: Port):
        """Stable exclusion key — port id when present, else the port name."""
        return p.id if getattr(p, "id", None) is not None else p.port_name

    def _visible_ports(self) -> list:
        return [p for p in self._ports if self._port_key(p) not in self._excluded_port_ids]

    def _rebuild_port_cards(self) -> None:
        """Redraw both tables showing only non-excluded ports; update status."""
        self._visible = self._visible_ports()
        self._populate_ports_table()
        self._populate_voyage_table()

        total    = len(self._ports)
        shown    = len(self._visible)
        excluded = total - shown
        if excluded:
            self.count_label.setText(f"Showing {shown} of {total} ports "
                                     f"({excluded} removed).")
        elif total:
            self.count_label.setText(f"Showing {shown} port(s).")
        else:
            self.count_label.setText("")
        self.reset_btn.setVisible(excluded > 0)

        # Drop selection if the selected port is no longer visible
        if self._selected_port and self._selected_port not in self._visible:
            self._selected_port = None
            self.selection_label.setText("")
            self.voyage_pdf_btn.setEnabled(False)

    def _remove_port(self, port_key) -> None:
        self._excluded_port_ids.add(port_key)
        self._rebuild_port_cards()
        self._show_undo_snackbar(port_key)

    def _undo_remove(self, port_key) -> None:
        self._excluded_port_ids.discard(port_key)
        self._dismiss_snackbar()
        self._rebuild_port_cards()

    def _reset_exclusions(self) -> None:
        self._excluded_port_ids.clear()
        self._dismiss_snackbar()
        self._rebuild_port_cards()

    def _dismiss_snackbar(self) -> None:
        if self._snackbar is not None:
            self._snackbar.deleteLater()
            self._snackbar = None

    def _show_undo_snackbar(self, port_key) -> None:
        """Temporary bottom snackbar with an Undo button; auto-dismiss after 5s."""
        self._dismiss_snackbar()
        snackbar = QFrame(self)
        snackbar.setStyleSheet(
            "QFrame { background-color: #2d3748; border: 1px solid #374151;"
            " border-radius: 4px; padding: 6px 12px; }"
        )
        lay = QHBoxLayout(snackbar)
        lay.setContentsMargins(10, 4, 10, 4)
        label = QLabel("Port removed")
        label.setStyleSheet("color: #f1f5f9; font-size: 12px;")
        undo_btn = QPushButton("Undo")
        undo_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #93c5fd;"
            " font-size: 12px; }"
            "QPushButton:hover { color: #ffffff; }"
        )
        undo_btn.clicked.connect(lambda: self._undo_remove(port_key))
        lay.addWidget(label)
        lay.addStretch()
        lay.addWidget(undo_btn)

        self.layout().addWidget(snackbar)   # bottom of the ports panel
        self._snackbar = snackbar
        # Auto-dismiss after 5s — guard against the widget already being gone.
        QTimer.singleShot(5000, lambda sb=snackbar: sb.deleteLater())

    def _remove_button(self, port_key) -> QPushButton:
        btn = QPushButton("✕ Remove")
        btn.setStyleSheet(
            "QPushButton { background: transparent; border: 1px solid #dc2626;"
            " color: #fca5a5; font-size: 11px; padding: 3px 8px; border-radius: 3px; }"
            "QPushButton:hover { background-color: #450a0a; }"
        )
        btn.clicked.connect(lambda _checked=False, k=port_key: self._remove_port(k))
        return btn

    def _populate_ports_table(self) -> None:
        # FIX 4: explicit foreground colors for readability on dark background
        _PORT_NAME_COLOR  = QColor("#f1f5f9")
        _COUNTRY_COLOR    = QColor("#94a3b8")
        _DIST_COLOR       = QColor("#f1f5f9")
        _SIZE_COLOR       = QColor("#cbd5e1")

        self.ports_table.setRowCount(len(self._visible))
        for row, p in enumerate(self._visible):
            depth_str   = f"{p.depth_anch_m:.1f} m" if p.depth_anch_m else "--"
            bearing_str = f"{p.bearing_deg:.1f}°" if p.bearing_deg is not None else "--"
            dist_str    = f"{p.distance_nm:.1f}" if p.distance_nm is not None else "--"

            # Depth clearance color (vs platform launch draft)
            launch_draft = getattr(getattr(self.mw, "platform", None), "launch_draft_m", None)
            depth_color = _SIZE_COLOR
            if p.depth_anch_m is not None and launch_draft is not None:
                clearance_m = p.depth_anch_m - launch_draft
                clearance_ft = clearance_m * 3.28084
                if clearance_ft < 0:
                    depth_color = QColor("#fca5a5")
                elif clearance_ft < 5:
                    depth_color = QColor("#fde68a")
                else:
                    depth_color = QColor("#86efac")

            fuel_color = QColor("#86efac") if p.fuel_oil else QColor("#fca5a5")

            vals_colors = [
                (p.port_name, _PORT_NAME_COLOR),
                (p.country, _COUNTRY_COLOR),
                (dist_str, _DIST_COLOR),
                (bearing_str, _DIST_COLOR),
                (p.harbor_size or "--", _SIZE_COLOR),
                (depth_str, depth_color),
            ]
            self.ports_table.setRowHeight(row, 28)
            for col, (text, color) in enumerate(vals_colors):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setForeground(color)
                self.ports_table.setItem(row, col, item)
            # Per-row remove button (session-only exclusion)
            self.ports_table.setCellWidget(row, _COL_REMOVE, self._remove_button(self._port_key(p)))

    def _visible_costs(self) -> list[VoyageCostBreakdown]:
        visible_keys = {self._port_key(p) for p in self._visible}
        return [vc for vc in self._costs if self._port_key(vc.port) in visible_keys]

    def _cost_for(self, port: Port | None) -> VoyageCostBreakdown | None:
        if port is None:
            return None
        key = self._port_key(port)
        for vc in self._costs:
            if self._port_key(vc.port) == key:
                return vc
        return None

    def _populate_voyage_table(self) -> None:
        _TEXT = QColor("#0f172a")    # near-black on white rows
        _COST = QColor("#14532d")   # dark green for cost columns
        costs = self._visible_costs()
        self.voyage_table.setRowCount(len(costs))
        for row, vc in enumerate(costs):
            vals_colors = [
                (vc.port.port_name,                       _TEXT),
                (f"{vc.total_distance_nm:,.1f} NM",       _TEXT),
                (f"{vc.total_transit_days:.2f} days",     _TEXT),
                (f"${vc.total_usd:,.0f}",                 _COST),
                (f"${vc.cost_per_launch():,.0f}",         _COST),
            ]
            for col, (text, color) in enumerate(vals_colors):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setForeground(color)
                self.voyage_table.setItem(row, col, item)

    def _show_breakdown(self) -> None:
        """Render the selected port's full cost breakdown."""
        from ui.dialogs.voyage_cost_editor import breakdown_summary_html

        vc = self._cost_for(self._selected_port)
        if vc is None:
            self.breakdown_label.setText(
                "Click a port row above to see its charter, port-fee and fuel "
                "breakdown."
            )
            return
        route = " -> ".join(
            [vc.legs[0].from_name] + [leg.to_name for leg in vc.legs]
        ) if vc.legs else "(no route — no launch site)"
        header = (
            f"<div style='color:#f1f5f9; font-weight:bold;'>{vc.port.port_name}</div>"
            f"<div style='color:#94a3b8; font-size:9pt;'>{route}</div><br>"
        )
        self.breakdown_label.setText(header + breakdown_summary_html(vc))

    def _export_csv(self) -> None:
        if not self._costs:
            QMessageBox.information(self, "No data", "Run Find Nearest Ports first.")
            return

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        reports_dir = Path("reports")
        reports_dir.mkdir(parents=True, exist_ok=True)
        default = str(reports_dir / f"port_comparison_{ts}.csv")

        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Port Comparison CSV", default, "CSV files (*.csv)"
        )
        if not path:
            return

        headers = [
            "Rank", "Port Name", "Country", "Legs", "Total Distance NM",
            "Transit Days", "On-Site Days", "Voyage Days",
            "Charter USD", "Port Fees USD", "Fuel Gal", "Fuel USD",
            "Total USD", "Launches", "Cost Per Launch USD",
        ]
        ranked = sorted(self._costs, key=lambda vc: vc.total_usd)
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                for rank, vc in enumerate(ranked, 1):
                    writer.writerow([
                        rank,
                        vc.port.port_name,
                        vc.port.country,
                        len(vc.legs),
                        f"{vc.total_distance_nm:.1f}",
                        f"{vc.total_transit_days:.2f}",
                        f"{vc.total_onsite_days:.2f}",
                        f"{vc.voyage_days:.2f}",
                        f"{vc.charter_total_usd:.2f}",
                        f"{vc.port_fees_total_usd:.2f}",
                        f"{vc.fuel_total_gal:.2f}",
                        f"{vc.fuel_total_usd:.2f}",
                        f"{vc.total_usd:.2f}",
                        vc.launches,
                        f"{vc.cost_per_launch():.2f}",
                    ])
            self.mw.status(f"Port comparison CSV saved: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))
            return
        try:
            _open_file(path)
        except Exception as exc:
            QMessageBox.warning(
                self, "CSV Saved",
                f"CSV saved to:\n{path}\n\n"
                f"Could not open it automatically:\n{exc}"
            )

    def _on_port_row_selected(self) -> None:
        indexes = self.ports_table.selectedIndexes()
        if not indexes:
            return
        row_idx = indexes[0].row()
        if 0 <= row_idx < len(self._visible):
            self._selected_port = self._visible[row_idx]
            self.selection_label.setText(
                f"Selected for voyage PDF: {self._selected_port.port_name}"
            )
            if self._costs:
                self.voyage_pdf_btn.setEnabled(True)
            self._update_finalize_btn()
            self._highlight_voyage_row()
            self._show_breakdown()

    def _highlight_voyage_row(self) -> None:
        """Highlight the voyage-table row that matches the selected port."""
        if not self._selected_port:
            return
        _DARK = QColor("#0f172a")
        for row in range(self.voyage_table.rowCount()):
            is_match = False
            name_item = self.voyage_table.item(row, 0)
            if name_item and name_item.text() == self._selected_port.port_name:
                is_match = True
            for col in range(self.voyage_table.columnCount()):
                item = self.voyage_table.item(row, col)
                if item:
                    item.setBackground(
                        _SELECTED_ROW_COLOR if is_match else QColor(255, 255, 255)
                    )
                    item.setForeground(_DARK)

    def _generate_voyage_pdf(self) -> None:
        if not self.mw.site or not self._selected_port or not self._costs:
            return
        from core.models import VoyageSchedule
        from modules.m4_ports.voyage import (
            calculate_voyage_cost, generate_waypoints, load_params,
        )
        from modules.m5_reports.voyage_pdf import generate_voyage_report

        params = load_params()
        cost = self._cost_for(self._selected_port) or calculate_voyage_cost(
            self.mw.site, self._selected_port, params=params
        )
        waypoints = generate_waypoints(
            self.mw.site, self._selected_port, platform_speed_kts=params.speed_kts
        )
        qd = self.date_edit.date()
        schedule = VoyageSchedule(
            site=self.mw.site,
            port=self._selected_port,
            cost=cost,
            waypoints=waypoints,
            departure_date=date(qd.year(), qd.month(), qd.day()),
        )

        ts          = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        site        = self.mw.site
        site_slug   = (
            f"{abs(site.lat):.1f}{'N' if site.lat >= 0 else 'S'}_"
            f"{abs(site.lon):.1f}{'E' if site.lon >= 0 else 'W'}"
        )
        reports_dir  = Path("reports")
        reports_dir.mkdir(parents=True, exist_ok=True)
        default_name = f"voyage_{site_slug}_{ts}.pdf"

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Voyage Report", str(reports_dir / default_name),
            "PDF files (*.pdf)"
        )
        if not path:
            return
        try:
            saved = generate_voyage_report(
                schedule        = schedule,
                all_port_costs  = self._costs,
                analysis_result = None,
                output_path     = path,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))
            return
        self.mw.status(f"Voyage report saved: {saved}")
        try:
            _open_file(saved)
        except Exception as exc:
            QMessageBox.warning(
                self, "Report Saved",
                f"PDF saved to:\n{saved}\n\n"
                f"Could not open it automatically:\n{exc}"
            )

    def _can_finalize(self) -> bool:
        if not getattr(self.mw, "site", None) or self.mw.site.id is None:
            return False
        if not getattr(self.mw, "active_project_id", None):
            return False
        if not self._selected_port or not self._costs:
            return False
        if self._cost_for(self._selected_port) is None:
            return False
        if getattr(self._selected_port, "id", None) is None:
            return False
        return True

    def _update_finalize_btn(self) -> None:
        self.finalize_btn.setEnabled(self._can_finalize())

    def _finalize_port(self) -> None:
        if not self._can_finalize():
            QMessageBox.information(
                self,
                "Cannot Finalize",
                "Finalize requires an open project, an active saved site, and a "
                "selected port with voyage costs calculated.",
            )
            return

        from modules.m4_ports.finalization import (
            finalize_voyage, get_finalization, FinalizationError,
        )
        from modules.m4_ports.voyage import load_params

        project_id = self.mw.active_project_id
        site = self.mw.site
        port = self._selected_port
        breakdown = self._cost_for(port)
        params = load_params()

        existing = get_finalization(project_id, site.id)
        if existing and existing.actual_breakdown:
            ans = QMessageBox.warning(
                self,
                "Actuals Will Be Cleared",
                "This project + site already has saved actual costs.\n\n"
                "Re-finalizing will replace the estimate snapshot and clear "
                "the existing actuals.\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return

        route = " → ".join(
            [breakdown.legs[0].from_name] + [leg.to_name for leg in breakdown.legs]
        ) if breakdown.legs else port.port_name

        msg = (
            f"Finalize voyage estimate for:\n\n"
            f"  Project ID: {project_id}\n"
            f"  Site: {site.coord_str}\n"
            f"  Load port: {port.port_name}\n"
            f"  Route: {route}\n"
            f"  Total estimate: ${breakdown.total_usd:,.0f}\n\n"
            f"The current voyage cost settings and computed breakdown will be "
            f"frozen until you re-finalize."
        )
        if QMessageBox.question(
            self, "Finalize Port for Project", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        try:
            finalize_voyage(
                project_id=project_id,
                site=site,
                port_id=port.id,
                params=params,
                breakdown=breakdown,
            )
        except FinalizationError as exc:
            QMessageBox.warning(self, "Finalize Failed", str(exc))
            return

        self.mw.status(
            f"Port finalized: {port.port_name} — ${breakdown.total_usd:,.0f}"
        )
        ans = QMessageBox.question(
            self,
            "Port Finalized",
            f"Voyage estimate for {port.port_name} has been saved.\n\n"
            "Open Mission Economics to review or enter actual costs?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            self.mw.sidebar.select_section("mission_economics")
            from ui.main_window import _SECTION_INDEX
            self.mw.stack.setCurrentIndex(_SECTION_INDEX["mission_economics"])
            econ = getattr(self.mw, "mission_economics_section", None)
            if econ is not None:
                econ.reload()


# ── Utility ───────────────────────────────────────────────────────────────────

def _open_file(path: str) -> None:
    from core.utils import open_local_path
    open_local_path(path)

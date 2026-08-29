"""
ui/sections/mission_economics.py — Mission Economics: finalized estimate vs actuals.
"""
from __future__ import annotations

from copy import deepcopy

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QGroupBox, QScrollArea,
    QHeaderView, QMessageBox, QCheckBox, QSpinBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from core.models import FEE_CATEGORIES, FEE_CATEGORY_LABELS, PORT_ROLE_LABELS
from ui.styles import apply_table_colors
from ui.widgets.spinbox import StyledDoubleSpinBox
from modules.m4_ports.finalization import (
    VoyageFinalization,
    compare_estimate_actual,
    copy_estimate_for_actuals,
    get_finalization,
    recompute_breakdown_totals,
    save_actuals,
    clear_actuals,
    FinalizationError,
)


_BTN_PRIMARY = (
    "QPushButton { background:#2563eb; color:white; border-radius:4px;"
    "padding:6px 16px; font-weight:bold; border:none; }"
    "QPushButton:hover { background:#1d4ed8; }"
    "QPushButton:disabled { background:#1e3a5f; color:#64748b; }"
)
_BTN_SECONDARY = (
    "QPushButton { background:#1e2d3d; color:#e2e8f0; border:1px solid #374151;"
    "border-radius:4px; padding:5px 12px; }"
    "QPushButton:hover { background:#2d3f55; }"
)
_SPIN_STYLE = (
    "QSpinBox { background:#1a2233; color:#e2e8f0; border:1px solid #374151;"
    "border-radius:3px; padding:2px 4px; }"
)


class MissionEconomicsSection(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._fin: VoyageFinalization | None = None
        self._actual_data: dict | None = None
        self._vessel_spinboxes: list[dict] = []
        self._fee_spinboxes: list[dict] = []
        self._transit_spin: StyledDoubleSpinBox | None = None
        self._onsite_spin: StyledDoubleSpinBox | None = None
        self._launches_spin: QSpinBox | None = None
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        title = QLabel("Mission Economics")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #f1f5f9;")
        root.addWidget(title)

        self._header_lbl = QLabel("")
        self._header_lbl.setStyleSheet("color: #94a3b8;")
        self._header_lbl.setWordWrap(True)
        root.addWidget(self._header_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(14)

        self._empty_lbl = QLabel(
            "Finalize a port on the Ports tab first.\n\n"
            "Requires an open project and an active site with a saved voyage estimate."
        )
        self._empty_lbl.setStyleSheet("color: #94a3b8; font-size: 11pt; padding: 24px 0;")
        self._empty_lbl.setWordWrap(True)
        body_layout.addWidget(self._empty_lbl)

        self._content = QWidget()
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)

        summary_group = QGroupBox("Project / Location Summary")
        summary_layout = QVBoxLayout(summary_group)
        self._summary_lbl = QLabel("")
        self._summary_lbl.setWordWrap(True)
        self._summary_lbl.setStyleSheet("color: #e2e8f0;")
        summary_layout.addWidget(self._summary_lbl)
        content_layout.addWidget(summary_group)

        est_group = QGroupBox("Estimated Cost (Finalized Snapshot)")
        est_layout = QVBoxLayout(est_group)
        self._estimate_lbl = QLabel("")
        self._estimate_lbl.setWordWrap(True)
        self._estimate_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._estimate_lbl.setStyleSheet("color: #e2e8f0;")
        est_layout.addWidget(self._estimate_lbl)
        content_layout.addWidget(est_group)

        actual_group = QGroupBox("Actual Cost Entry")
        actual_layout = QVBoxLayout(actual_group)

        dur_row = QHBoxLayout()
        dur_row.addWidget(QLabel("Transit days:"))
        self._transit_spin = StyledDoubleSpinBox()
        self._transit_spin.setRange(0, 9999)
        self._transit_spin.setDecimals(2)
        self._transit_spin.valueChanged.connect(self._on_actual_edited)
        dur_row.addWidget(self._transit_spin)
        dur_row.addSpacing(16)
        dur_row.addWidget(QLabel("On-site days:"))
        self._onsite_spin = StyledDoubleSpinBox()
        self._onsite_spin.setRange(0, 9999)
        self._onsite_spin.setDecimals(2)
        self._onsite_spin.valueChanged.connect(self._on_actual_edited)
        dur_row.addWidget(self._onsite_spin)
        dur_row.addSpacing(16)
        dur_row.addWidget(QLabel("Launches:"))
        self._launches_spin = QSpinBox()
        self._launches_spin.setRange(1, 999)
        self._launches_spin.setStyleSheet(_SPIN_STYLE)
        self._launches_spin.valueChanged.connect(self._on_actual_edited)
        dur_row.addWidget(self._launches_spin)
        dur_row.addStretch()
        actual_layout.addLayout(dur_row)

        self._vessel_table = QTableWidget(0, 7)
        self._vessel_table.setHorizontalHeaderLabels([
            "Vessel", "Deployed", "Charter Days", "Charter $/day",
            "At-sea gal/day", "In-port gal/day", "Fuel $/gal",
        ])
        self._vessel_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._vessel_table.verticalHeader().setVisible(False)
        apply_table_colors(self._vessel_table)
        actual_layout.addWidget(self._vessel_table)

        self._fees_table = QTableWidget(0, 7)
        self._fees_table.setHorizontalHeaderLabels(
            ["Role"] + [FEE_CATEGORY_LABELS[c] for c in FEE_CATEGORIES]
        )
        self._fees_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._fees_table.verticalHeader().setVisible(False)
        apply_table_colors(self._fees_table)
        actual_layout.addWidget(self._fees_table)

        btn_row = QHBoxLayout()
        self._save_btn = QPushButton("Save Actuals")
        self._save_btn.setStyleSheet(_BTN_PRIMARY)
        self._save_btn.clicked.connect(self._save_actuals)
        btn_row.addWidget(self._save_btn)
        self._clear_btn = QPushButton("Clear Actuals")
        self._clear_btn.setStyleSheet(_BTN_SECONDARY)
        self._clear_btn.clicked.connect(self._clear_actuals)
        btn_row.addWidget(self._clear_btn)
        btn_row.addStretch()
        actual_layout.addLayout(btn_row)
        content_layout.addWidget(actual_group)

        cmp_group = QGroupBox("Estimate vs Actual")
        cmp_layout = QVBoxLayout(cmp_group)
        self._compare_table = QTableWidget(0, 5)
        self._compare_table.setHorizontalHeaderLabels(
            ["Line Item", "Estimate", "Actual", "Δ", "Δ%"]
        )
        self._compare_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._compare_table.verticalHeader().setVisible(False)
        apply_table_colors(self._compare_table)
        cmp_layout.addWidget(self._compare_table)
        content_layout.addWidget(cmp_group)

        self._content.hide()
        body_layout.addWidget(self._content)
        body_layout.addStretch()

        scroll.setWidget(body)
        root.addWidget(scroll, 1)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.reload()

    def on_project_changed(self) -> None:
        self.reload()

    def on_site_changed(self) -> None:
        self.reload()

    def reload(self) -> None:
        project_id = getattr(self.mw, "open_project_id", None)
        site = getattr(self.mw, "site", None)

        if not project_id:
            self._fin = None
            self._show_empty("Open a project to view mission economics.")
            return

        if not site or site.id is None:
            self._fin = None
            self._show_empty(
                "Activate a saved site (By Project view on Sites tab) to view "
                "mission economics for that location."
            )
            return

        self._fin = get_finalization(project_id, site.id)
        if self._fin is None:
            self._show_empty(
                "No finalized port estimate for this project + site.\n\n"
                "Go to the Ports tab, select a candidate port, and click "
                '"Finalize Port for Project".'
            )
            return

        self._empty_lbl.hide()
        self._content.show()
        self._populate()

    def _show_empty(self, message: str) -> None:
        self._empty_lbl.setText(message)
        self._empty_lbl.show()
        self._content.hide()
        proj_name = getattr(self.mw, "open_project_name", "") or "(no project)"
        self._header_lbl.setText(f"Project: {proj_name}")

    def _populate(self) -> None:
        from ui.dialogs.voyage_cost_editor import breakdown_summary_html_from_dict

        fin = self._fin
        if fin is None:
            return

        site = self.mw.site
        proj_name = getattr(self.mw, "open_project_name", "") or f"Project #{fin.project_id}"
        site_label = site.name if site and site.name else (site.coord_str if site else fin.site_name)
        finalized = fin.finalized_at.replace("T", " ") if fin.finalized_at else "—"
        actual_ts = (
            fin.actual_entered_at.replace("T", " ")
            if fin.actual_entered_at else "Not entered"
        )

        self._header_lbl.setText(
            f"Project: {proj_name}  |  Site: {site_label}  |  "
            f"Load port: {fin.load_port_name or '—'}  |  "
            f"Finalized: {finalized}  |  Actuals: {actual_ts}"
        )

        est = fin.estimate_breakdown
        legs = est.get("legs") or []
        route = " → ".join(
            [legs[0].get("from_name", "")] + [leg.get("to_name", "") for leg in legs]
        ) if legs else "(route unavailable)"

        self._summary_lbl.setText(
            f"Site coordinates: {site.coord_str if site else '—'}\n"
            f"Route: {route}\n"
            f"Speed: {float(est.get('speed_kts') or 0.0):g} kts  |  "
            f"Voyage days: {float(est.get('voyage_days') or 0.0):.2f}  |  "
            f"Launches: {int(est.get('launches') or 1)}"
        )
        self._estimate_lbl.setText(breakdown_summary_html_from_dict(est))

        if fin.actual_breakdown:
            self._actual_data = deepcopy(fin.actual_breakdown)
            # Ensure gal/day rates exist for recompute (may be absent in older rows).
            param_vessels = {
                v.get("key"): v for v in (fin.estimate_params.get("vessels") or [])
            }
            for v in self._actual_data.get("vessels") or []:
                pv = param_vessels.get(v.get("key"), {})
                v.setdefault("at_sea_gal_day", float(pv.get("at_sea_gal_day") or 0.0))
                v.setdefault("in_port_gal_day", float(pv.get("in_port_gal_day") or 0.0))
        else:
            self._actual_data = copy_estimate_for_actuals(est, fin.estimate_params)

        self._fill_actual_editor()
        self._refresh_comparison()

    def _fill_actual_editor(self) -> None:
        data = self._actual_data or {}
        self._vessel_spinboxes.clear()
        self._fee_spinboxes.clear()

        self._transit_spin.blockSignals(True)
        self._onsite_spin.blockSignals(True)
        self._launches_spin.blockSignals(True)
        self._transit_spin.setValue(float(data.get("total_transit_days") or 0.0))
        self._onsite_spin.setValue(float(data.get("total_onsite_days") or 0.0))
        self._launches_spin.setValue(int(data.get("launches") or 1))
        self._transit_spin.blockSignals(False)
        self._onsite_spin.blockSignals(False)
        self._launches_spin.blockSignals(False)

        vessels = data.get("vessels") or []
        self._vessel_table.setRowCount(len(vessels))
        for row, v in enumerate(vessels):
            name_item = QTableWidgetItem(v.get("name") or v.get("key") or "")
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._vessel_table.setItem(row, 0, name_item)

            deployed_cb = QCheckBox()
            deployed_cb.setChecked(bool(v.get("deployed")))
            deployed_cb.stateChanged.connect(self._on_actual_edited)
            self._vessel_table.setCellWidget(row, 1, deployed_cb)

            spins: dict = {"deployed_cb": deployed_cb}
            specs = [
                ("charter_days", float(v.get("charter_days") or 0.0), 2),
                ("charter_rate_usd_day", float(v.get("charter_rate_usd_day") or 0.0), 0),
                ("at_sea_gal_day", float(v.get("at_sea_gal_day") or 0.0), 1),
                ("in_port_gal_day", float(v.get("in_port_gal_day") or 0.0), 1),
                ("fuel_usd_gal", float(v.get("fuel_usd_gal") or 0.0), 2),
            ]
            for col_offset, (key, val, decimals) in enumerate(specs, start=2):
                spin = StyledDoubleSpinBox()
                spin.setRange(0, 99999999)
                spin.setDecimals(decimals)
                spin.setValue(val)
                spin.valueChanged.connect(self._on_actual_edited)
                self._vessel_table.setCellWidget(row, col_offset, spin)
                spins[key] = spin
            self._vessel_spinboxes.append(spins)

        port_fees = data.get("port_fees") or []
        self._fees_table.setRowCount(len(port_fees))
        for row, pf in enumerate(port_fees):
            role = pf.get("role") or ""
            role_item = QTableWidgetItem(PORT_ROLE_LABELS.get(role, role))
            role_item.setFlags(role_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._fees_table.setItem(row, 0, role_item)
            fee_spins: dict = {"role": role}
            for col, cat in enumerate(FEE_CATEGORIES, start=1):
                spin = StyledDoubleSpinBox()
                spin.setRange(0, 99999999)
                spin.setDecimals(0)
                spin.setValue(float(pf.get(f"{cat}_usd") or 0.0))
                spin.valueChanged.connect(self._on_actual_edited)
                self._fees_table.setCellWidget(row, col, spin)
                fee_spins[cat] = spin
            self._fee_spinboxes.append(fee_spins)

    def _collect_actual_dict(self) -> dict:
        base = deepcopy(self._actual_data or {})
        base["total_transit_days"] = self._transit_spin.value()
        base["total_onsite_days"] = self._onsite_spin.value()
        base["launches"] = self._launches_spin.value()

        vessels = base.get("vessels") or []
        for idx, spins in enumerate(self._vessel_spinboxes):
            if idx >= len(vessels):
                break
            v = vessels[idx]
            v["deployed"] = spins["deployed_cb"].isChecked()
            v["charter_days"] = spins["charter_days"].value()
            v["charter_rate_usd_day"] = spins["charter_rate_usd_day"].value()
            v["at_sea_gal_day"] = spins["at_sea_gal_day"].value()
            v["in_port_gal_day"] = spins["in_port_gal_day"].value()
            v["fuel_usd_gal"] = spins["fuel_usd_gal"].value()
        base["vessels"] = vessels

        port_fees = base.get("port_fees") or []
        for idx, fee_spins in enumerate(self._fee_spinboxes):
            if idx >= len(port_fees):
                break
            pf = port_fees[idx]
            for cat in FEE_CATEGORIES:
                pf[f"{cat}_usd"] = fee_spins[cat].value()
        base["port_fees"] = port_fees
        return recompute_breakdown_totals(base)

    def _on_actual_edited(self, *_args) -> None:
        self._actual_data = self._collect_actual_dict()
        self._refresh_comparison()

    def _refresh_comparison(self) -> None:
        if self._fin is None:
            return
        actual = self._actual_data or self._collect_actual_dict()
        rows = compare_estimate_actual(self._fin.estimate_breakdown, actual)
        self._compare_table.setRowCount(len(rows))

        for row_idx, row in enumerate(rows):
            is_currency = row.get("is_currency", True)
            est = row["estimate"]
            act = row["actual"]
            delta = row["delta"]
            delta_pct = row["delta_pct"]

            if is_currency:
                est_s = f"${est:,.2f}"
                act_s = f"${act:,.2f}"
                delta_s = f"${delta:+,.2f}"
            else:
                est_s = f"{est:,.2f}"
                act_s = f"{act:,.2f}"
                delta_s = f"{delta:+,.2f}"

            if delta_pct is None:
                pct_s = "—"
            else:
                pct_s = f"{delta_pct:+.1f}%"

            label_item = QTableWidgetItem(row["label"])
            label_item.setFlags(label_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._compare_table.setItem(row_idx, 0, label_item)

            for col, text in enumerate([est_s, act_s, delta_s, pct_s], start=1):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col in (3, 4) and delta != 0:
                    if delta > 0:
                        item.setForeground(QColor("#fca5a5"))
                    else:
                        item.setForeground(QColor("#86efac"))
                self._compare_table.setItem(row_idx, col, item)

    def _save_actuals(self) -> None:
        if self._fin is None:
            return
        actual = self._collect_actual_dict()
        try:
            self._fin = save_actuals(self._fin.id, actual)
            self._actual_data = deepcopy(self._fin.actual_breakdown or actual)
            self.mw.status("Actual voyage costs saved.")
            self._header_lbl.setText(self._header_lbl.text())  # trigger refresh below
            self.reload()
        except FinalizationError as exc:
            QMessageBox.warning(self, "Save Failed", str(exc))

    def _clear_actuals(self) -> None:
        if self._fin is None:
            return
        ans = QMessageBox.question(
            self,
            "Clear Actuals",
            "Remove saved actual costs for this site? The estimate snapshot is kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        try:
            self._fin = clear_actuals(self._fin.id)
            self.mw.status("Actual voyage costs cleared.")
            self.reload()
        except FinalizationError as exc:
            QMessageBox.warning(self, "Clear Failed", str(exc))

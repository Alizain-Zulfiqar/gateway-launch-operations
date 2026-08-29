"""
ui/sections/reports.py — Report generation, naming, and archive management.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QGroupBox, QProgressBar, QMessageBox, QRadioButton,
    QButtonGroup, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QMenu,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPoint
from PyQt6.QtGui import QAction

from config import BASE_DIR
from core.database import get_connection
from ui.styles import apply_table_colors

REPORTS_DIR = BASE_DIR / "reports"

_BTN_PRIMARY = (
    "QPushButton {"
    "  background: #2563eb; color: white;"
    "  border-radius: 4px; padding: 8px 20px; font-weight: bold; border: none;"
    "}"
    "QPushButton:hover { background: #1d4ed8; }"
    "QPushButton:disabled { background: #1e3a5f; color: #64748b; }"
)
_BTN_GREEN = (
    "QPushButton {"
    "  background: #166534; color: white;"
    "  border-radius: 4px; padding: 8px 20px; font-weight: bold; border: none;"
    "}"
    "QPushButton:hover { background: #15803d; }"
)
_BTN_SECONDARY = (
    "QPushButton {"
    "  background: #1e293b; color: #cbd5e1;"
    "  border: 1px solid #374151; border-radius: 4px; padding: 6px 16px;"
    "}"
    "QPushButton:hover { background: #334155; }"
)
_COMBO_STYLE = (
    "QComboBox { background: #1a2233; color: #e2e8f0; border: 1px solid #374151;"
    " border-radius: 3px; padding: 2px 8px; }"
    "QComboBox QAbstractItemView { background: #1a2233; color: #e2e8f0; }"
)


# ── Worker ────────────────────────────────────────────────────────────────────

class _ReportWorker(QThread):
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(
        self,
        analysis_row: dict,
        output_dir: str,
        project=None,                      # Optional[Project]
        include_buoy_forecast: bool = False,
        ndbc_station_ids: list | None = None,
        forecast_horizon_hours: int = 72,
    ):
        super().__init__()
        self._row            = analysis_row
        self._dir            = output_dir
        self._project        = project
        self._combined_mode  = include_buoy_forecast
        self._station_ids    = ndbc_station_ids or []
        self._horizon        = forecast_horizon_hours

    def run(self):
        try:
            from core.models import Site, Vehicle, Platform, AnalysisResult
            from modules.m5_reports.pdf_report import generate_analysis_report
            from config import DEFAULT_WEIGHTS

            row  = self._row
            conn = get_connection()

            s  = conn.execute("SELECT * FROM sites     WHERE id=?", (row["site_id"],)).fetchone()
            v  = conn.execute("SELECT * FROM vehicles  WHERE id=?", (row["vehicle_id"],)).fetchone()
            pl = conn.execute("SELECT * FROM platforms WHERE id=?", (row["platform_id"],)).fetchone()
            conn.close()

            site = Site(
                id=s["id"], name=s["name"], lat=s["lat"], lon=s["lon"],
                bbox_nm=s["bbox_nm"] or 25.0,
                coord_code=s["coord_code"],
            )
            vehicle = Vehicle(
                id=v["id"], name=v["name"],
                vehicle_class=v["vehicle_class"],
                recovery_mode=v["recovery_mode"] or "expendable",
                max_wind_kts=v["max_wind_kts"] or 25.0,
                max_gust_kts=v["max_gust_kts"] or 35.0,
                max_hs_m=v["max_hs_m"] or 2.0,
                max_swell_ht_m=v["max_swell_ht_m"] or 2.5,
                max_swell_period_s=v["max_swell_period_s"] or 14.0,
            )
            platform = Platform(
                id=pl["id"], name=pl["name"],
                hull_type=pl["hull_type"],
                hull_motion_factor=pl["hull_motion_factor"],
            )

            param_probs  = json.loads(row["param_probs_json"]  or "{}")
            data_sources = json.loads(row["data_sources_json"] or "{}")

            thresholds = vehicle.thresholds()
            eff_means  = {k: 0.0 for k in param_probs}
            weights    = DEFAULT_WEIGHTS.copy()
            total      = sum(weights.values())
            weights    = {k: w / total for k, w in weights.items()}

            result = AnalysisResult(
                site=site, vehicle=vehicle, platform=platform,
                mode=row["mode"] or "historical",
                overall_prob=row["overall_prob"] or 0.0,
                param_probs=param_probs,
                limiting_param=row["limiting_param"] or "",
                data_sources=data_sources,
                effective_means=eff_means,
                thresholds=thresholds,
                weights=weights,
                confidence_rating=row["confidence_rating"] or "model",
                year_start=row["year_start"],
                year_end=row["year_end"],
                month_filter=row["month_filter"],
            )

            blended_result  = None
            observed_result = None
            forecast_data   = None
            ndbc_combined   = None

            if self._combined_mode and self._station_ids:
                from modules.m2_weather.ndbc import fetch_multiple_station_dataframes
                from modules.m2_weather.ndbc_history import aggregate_station_statistics
                from modules.m2_weather.forecast import compute_forecast_analysis
                from modules.m3_probability.engine import (
                    compute_probability,
                    compute_probability_from_observed,
                )

                raw          = fetch_multiple_station_dataframes(self._station_ids)
                station_data = {
                    sid: d for sid, d in raw.items()
                    if not d.get("fetch_error")
                }
                ndbc_combined = aggregate_station_statistics(
                    station_data, forecast_hours=self._horizon
                )
                forecast_data = compute_forecast_analysis(
                    ndbc_combined, horizon_hours=self._horizon
                )

                obs_means = {
                    "ws":  ndbc_combined.get("wind_speed",   {}).get("weighted_mean_kts"),
                    "wg":  ndbc_combined.get("wind_gust",    {}).get("weighted_mean_kts"),
                    "sh":  ndbc_combined.get("wave_height",  {}).get("weighted_mean_m"),
                    "swh": ndbc_combined.get("swell_height", {}).get("weighted_mean_m"),
                    "swp": ndbc_combined.get("swell_period", {}).get("weighted_mean_s"),
                }

                obs_dict = {
                    param: {"mean": val, "source": "ndbc_realtime"}
                    for param, val in obs_means.items()
                    if val is not None
                }
                blended_result = compute_probability(
                    site=site, vehicle=vehicle, platform=platform,
                    month=row["month_filter"] or 1,
                    year_start=row["year_start"],
                    year_end=row["year_end"],
                    weights=weights,
                    mode="blended",
                    observed_means=obs_dict,
                )

                observed_result = compute_probability_from_observed(
                    vehicle, platform, obs_means, result
                )

            saved = generate_analysis_report(
                result,
                self._dir,
                include_buoy_forecast=self._combined_mode,
                blended_result=blended_result,
                observed_result=observed_result,
                forecast_data=forecast_data,
                ndbc_combined=ndbc_combined,
                forecast_horizon_hours=self._horizon,
                project=self._project,
            )
            self.finished.emit(saved)
        except Exception as exc:
            self.error.emit(str(exc))


# ── Reports Section ───────────────────────────────────────────────────────────

class ReportsSection(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._analyses: list[dict] = []
        self._projects: list[dict] = []
        self._report_rows: list[dict] = []
        self._worker: _ReportWorker | None = None
        self._last_path: str = ""
        self._build()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._reload_analyses()
        self._reload_projects()
        self.refresh_report_list()
        self._refresh_station_count()

    def on_project_changed(self) -> None:
        """Default the report association + saved-report filter to the open
        project. Called by GatewayMainWindow.open_project()/close_project()."""
        self._reload_projects()
        open_id = getattr(self.mw, "open_project_id", None)

        # Saved-report filter combo stores project ids.
        self._proj_filter_combo.blockSignals(True)
        target = 0
        if open_id is not None:
            for i in range(self._proj_filter_combo.count()):
                if self._proj_filter_combo.itemData(i) == open_id:
                    target = i
                    break
        self._proj_filter_combo.setCurrentIndex(target)
        self._proj_filter_combo.blockSignals(False)

        # Association combo stores Project objects (or None); match by id.
        if open_id is not None:
            self._proj_assoc_combo.blockSignals(True)
            for i in range(self._proj_assoc_combo.count()):
                d = self._proj_assoc_combo.itemData(i)
                if d is not None and getattr(d, "id", None) == open_id:
                    self._proj_assoc_combo.setCurrentIndex(i)
                    break
            self._proj_assoc_combo.blockSignals(False)

        self.refresh_report_list()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        title = QLabel("Reports")
        title.setObjectName("sectionTitle")
        root.addWidget(title)

        subtitle = QLabel(
            "Select a saved analysis and click Generate PDF Report to produce a "
            "launch window probability report. Optionally associate with a project "
            "for structured filename generation."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #94a3b8;")
        root.addWidget(subtitle)

        # ── Report type toggle ────────────────────────────────────────────────
        type_group = QGroupBox("Report Type")
        tg = QVBoxLayout(type_group)
        tg.setSpacing(8)

        self._type_btn_group = QButtonGroup(self)
        self._analysis_only_rb = QRadioButton(
            "Analysis Report Only  (3 pages: summary, parameter detail, data basis)"
        )
        self._combined_rb = QRadioButton(
            "Combined GO/NO-GO Report  (+ Near-term Outlook, Buoy Observations, Forecast Detail)"
        )
        self._analysis_only_rb.setChecked(True)
        self._type_btn_group.addButton(self._analysis_only_rb, 0)
        self._type_btn_group.addButton(self._combined_rb, 1)
        tg.addWidget(self._analysis_only_rb)
        tg.addWidget(self._combined_rb)

        self._forecast_opts = QWidget()
        fo = QHBoxLayout(self._forecast_opts)
        fo.setContentsMargins(20, 0, 0, 0)
        fo.setSpacing(12)

        self._station_lbl = QLabel("0 NDBC stations selected.")
        self._station_lbl.setStyleSheet("color: #94a3b8; font-size: 8pt;")
        fo.addWidget(self._station_lbl)

        fo.addWidget(QLabel("Horizon:"))
        self._horizon_combo = QComboBox()
        self._horizon_combo.addItems(["24 h", "48 h", "72 h", "5 day", "7 day"])
        self._horizon_combo.setCurrentIndex(2)
        self._horizon_combo.setStyleSheet(_COMBO_STYLE)
        fo.addWidget(self._horizon_combo)
        fo.addStretch()

        self._forecast_opts.setVisible(False)
        tg.addWidget(self._forecast_opts)
        root.addWidget(type_group)

        self._combined_rb.toggled.connect(self._on_type_toggled)

        # ── No-analysis banner ────────────────────────────────────────────────
        self._no_analysis_widget = QWidget()
        nav = QVBoxLayout(self._no_analysis_widget)
        nav.setSpacing(10)
        no_lbl = QLabel(
            "No saved analyses found.  Run an analysis in the Analysis section first, "
            "then return here to generate a report."
        )
        no_lbl.setWordWrap(True)
        no_lbl.setStyleSheet(
            "background: #1e3a5f; color: #93c5fd; border-radius: 6px; padding: 12px;"
        )
        nav.addWidget(no_lbl)
        go_btn = QPushButton("Go to Analysis")
        go_btn.setStyleSheet(_BTN_PRIMARY)
        go_btn.clicked.connect(self._go_to_analysis)
        nav.addWidget(go_btn)
        root.addWidget(self._no_analysis_widget)

        # ── Analysis selector group ───────────────────────────────────────────
        self._selector_group = QGroupBox("Saved Analyses")
        sg = QVBoxLayout(self._selector_group)
        sg.setSpacing(10)

        self._analysis_combo = QComboBox()
        self._analysis_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self._analysis_combo.setStyleSheet(_COMBO_STYLE)
        sg.addWidget(self._analysis_combo)

        self._detail_lbl = QLabel()
        self._detail_lbl.setWordWrap(True)
        self._detail_lbl.setStyleSheet(
            "background: #111827; border: 1px solid #374151; "
            "border-radius: 4px; padding: 8px; color: #e2e8f0;"
        )
        sg.addWidget(self._detail_lbl)

        proj_row = QHBoxLayout()
        proj_row.setSpacing(8)
        proj_lbl = QLabel("Associate with project (optional):")
        proj_lbl.setStyleSheet("color: #94a3b8;")
        proj_row.addWidget(proj_lbl)
        self._proj_assoc_combo = QComboBox()
        self._proj_assoc_combo.setMinimumWidth(260)
        self._proj_assoc_combo.setStyleSheet(_COMBO_STYLE)
        proj_row.addWidget(self._proj_assoc_combo, 1)
        sg.addLayout(proj_row)

        btn_row = QHBoxLayout()
        self._gen_btn = QPushButton("Generate PDF Report")
        self._gen_btn.setMinimumHeight(36)
        self._gen_btn.setStyleSheet(_BTN_PRIMARY)
        self._gen_btn.clicked.connect(self._on_generate)
        btn_row.addWidget(self._gen_btn)

        self._open_btn = QPushButton("Open Report")
        self._open_btn.setMinimumHeight(36)
        self._open_btn.setStyleSheet(_BTN_GREEN)
        self._open_btn.setVisible(False)
        self._open_btn.clicked.connect(self._on_open)
        btn_row.addWidget(self._open_btn)

        btn_row.addStretch()
        sg.addLayout(btn_row)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        sg.addWidget(self._progress)

        self._result_lbl = QLabel()
        self._result_lbl.setWordWrap(True)
        self._result_lbl.setVisible(False)
        sg.addWidget(self._result_lbl)

        root.addWidget(self._selector_group)

        # ── Saved Reports filter + table ──────────────────────────────────────
        self._files_group = QGroupBox("Saved Reports")
        fg = QVBoxLayout(self._files_group)
        fg.setSpacing(8)

        # Filter row
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)

        filter_row.addWidget(QLabel("Project:"))
        self._proj_filter_combo = QComboBox()
        self._proj_filter_combo.setMinimumWidth(160)
        self._proj_filter_combo.setStyleSheet(_COMBO_STYLE)
        filter_row.addWidget(self._proj_filter_combo)

        filter_row.addWidget(QLabel("Type:"))
        self._type_filter_combo = QComboBox()
        self._type_filter_combo.setStyleSheet(_COMBO_STYLE)
        self._type_filter_combo.addItem("All Types", userData=None)
        self._type_filter_combo.addItem("Analysis",  userData="analysis")
        self._type_filter_combo.addItem("Voyage",    userData="voyage")
        filter_row.addWidget(self._type_filter_combo)

        filter_row.addWidget(QLabel("Show:"))
        self._show_filter_combo = QComboBox()
        self._show_filter_combo.setStyleSheet(_COMBO_STYLE)
        self._show_filter_combo.addItem("Active",   userData="active")
        self._show_filter_combo.addItem("Archived", userData="archived")
        self._show_filter_combo.addItem("All",      userData=None)
        filter_row.addWidget(self._show_filter_combo)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setStyleSheet(_BTN_SECONDARY)
        refresh_btn.clicked.connect(self.refresh_report_list)
        filter_row.addWidget(refresh_btn)

        # Set 37, item 33: deletion already worked via right-click "Delete...",
        # but that's easy to miss — a visible button makes it discoverable,
        # matching the toolbar+context-menu pattern used elsewhere (e.g. the
        # Sites tab's "Delete Selected").
        delete_btn = QPushButton("Delete Selected")
        delete_btn.setStyleSheet(_BTN_SECONDARY)
        delete_btn.clicked.connect(self._delete_selected_reports)
        filter_row.addWidget(delete_btn)

        filter_row.addStretch()
        fg.addLayout(filter_row)

        # Report table
        self._report_table = QTableWidget(0, 6)
        self._report_table.setHorizontalHeaderLabels(
            ["Filename", "Project", "Site", "Type", "Generated", "Archived"]
        )
        self._report_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._report_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self._report_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self._report_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self._report_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents
        )
        self._report_table.horizontalHeader().setSectionResizeMode(
            5, QHeaderView.ResizeMode.ResizeToContents
        )
        self._report_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._report_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._report_table.verticalHeader().setVisible(False)
        self._report_table.setAlternatingRowColors(True)
        self._report_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._report_table.customContextMenuRequested.connect(
            self._on_table_context_menu
        )
        self._report_table.cellDoubleClicked.connect(self._on_table_double_click)
        apply_table_colors(self._report_table)
        fg.addWidget(self._report_table)

        # Bottom row: archive all filtered button
        bottom_row = QHBoxLayout()
        self._archive_all_btn = QPushButton("Archive All Filtered")
        self._archive_all_btn.setStyleSheet(_BTN_SECONDARY)
        self._archive_all_btn.clicked.connect(self._archive_all_filtered)
        bottom_row.addWidget(self._archive_all_btn)
        bottom_row.addStretch()
        fg.addLayout(bottom_row)

        root.addWidget(self._files_group)
        root.addStretch()

        self._analysis_combo.currentIndexChanged.connect(self._on_combo_changed)
        self._proj_filter_combo.currentIndexChanged.connect(
            lambda _: self.refresh_report_list()
        )
        self._type_filter_combo.currentIndexChanged.connect(
            lambda _: self.refresh_report_list()
        )
        self._show_filter_combo.currentIndexChanged.connect(
            lambda _: self.refresh_report_list()
        )

    # ── Data loading ──────────────────────────────────────────────────────────

    def _reload_analyses(self) -> None:
        try:
            conn = get_connection()
            rows = conn.execute("""
                SELECT a.id, a.overall_prob, a.limiting_param, a.mode,
                       a.year_start, a.year_end, a.month_filter,
                       a.param_probs_json, a.data_sources_json,
                       a.confidence_rating, a.created_at,
                       a.site_id, a.vehicle_id, a.platform_id,
                       s.name AS site_name,
                       v.name AS vehicle_name,
                       p.name AS platform_name
                  FROM analyses a
                  JOIN sites    s ON a.site_id     = s.id
                  JOIN vehicles v ON a.vehicle_id  = v.id
                  JOIN platforms p ON a.platform_id = p.id
                 ORDER BY a.created_at DESC
            """).fetchall()
            conn.close()
            self._analyses = [dict(r) for r in rows]
        except Exception:
            self._analyses = []

        has = bool(self._analyses)
        self._no_analysis_widget.setVisible(not has)
        self._selector_group.setVisible(has)

        self._analysis_combo.blockSignals(True)
        self._analysis_combo.clear()
        for row in self._analyses:
            mo = row.get("month_filter")
            mo_str = ["Jan","Feb","Mar","Apr","May","Jun",
                      "Jul","Aug","Sep","Oct","Nov","Dec"][mo-1] if mo else "All months"
            label = (
                f"{row['site_name']}  |  {row['vehicle_name']}  |  "
                f"{mo_str}  |  {round((row['overall_prob'] or 0)*100)}%  "
                f"({row['created_at'] or ''})"
            )
            self._analysis_combo.addItem(label)
        self._analysis_combo.blockSignals(False)
        if self._analyses:
            self._on_combo_changed(0)

    def _reload_projects(self) -> None:
        """Reload project list into both the association combo and filter combo."""
        try:
            conn = get_connection()
            rows = conn.execute(
                "SELECT id, name, code_name, launch_date_start, launch_date_end "
                "FROM projects WHERE status != 'cancelled' ORDER BY name"
            ).fetchall()
            conn.close()
            self._projects = [dict(r) for r in rows]
        except Exception:
            self._projects = []

        # Association combo (for generation)
        prev_assoc = self._proj_assoc_combo.currentData()
        self._proj_assoc_combo.blockSignals(True)
        self._proj_assoc_combo.clear()
        self._proj_assoc_combo.addItem("— none (unassigned) —", userData=None)
        for p in self._projects:
            label = p["name"]
            if p.get("code_name"):
                label += f"  ({p['code_name']})"
            # Set 37, item 34: report filenames require code_name + both
            # launch dates when a project is associated (naming.py's
            # {CODE}_{start}-{end}_... convention needs real values, not
            # None) — but "+ New Project" only ever sets name/status, so
            # nearly every project fails this validation by default,
            # making the association dropdown feel non-functional. Flag
            # incomplete projects right in the list instead of only
            # discovering it after clicking Generate.
            missing = []
            if not p.get("code_name"):
                missing.append("code name")
            if not p.get("launch_date_start"):
                missing.append("start date")
            if not p.get("launch_date_end"):
                missing.append("end date")
            if missing:
                label += f"  ⚠ missing {', '.join(missing)}"
            from core.models import Project
            proj_obj = Project(
                id=p["id"],
                name=p["name"],
                code_name=p.get("code_name") or "",
                launch_date_start=p.get("launch_date_start"),
                launch_date_end=p.get("launch_date_end"),
            )
            self._proj_assoc_combo.addItem(label, userData=proj_obj)
            if missing:
                idx = self._proj_assoc_combo.count() - 1
                self._proj_assoc_combo.setItemData(
                    idx,
                    "This project is missing fields required to build the "
                    "report filename: " + ", ".join(missing) + ". "
                    "Set them in the Projects section, or choose "
                    "— none — to generate an unassigned report.",
                    Qt.ItemDataRole.ToolTipRole,
                )
        # Restore selection
        if prev_assoc is not None:
            for i in range(self._proj_assoc_combo.count()):
                d = self._proj_assoc_combo.itemData(i)
                if d is not None and d.id == prev_assoc.id:
                    self._proj_assoc_combo.setCurrentIndex(i)
                    break
        self._proj_assoc_combo.blockSignals(False)

        # Filter combo (for table)
        prev_filter = self._proj_filter_combo.currentData()
        self._proj_filter_combo.blockSignals(True)
        self._proj_filter_combo.clear()
        self._proj_filter_combo.addItem("All Projects", userData=None)
        self._proj_filter_combo.addItem("Unassigned",   userData="UNASSIGNED")
        for p in self._projects:
            label = p["name"]
            if p.get("code_name"):
                label += f"  ({p['code_name']})"
            self._proj_filter_combo.addItem(label, userData=p["id"])
        # Restore selection
        if prev_filter is not None:
            for i in range(self._proj_filter_combo.count()):
                if self._proj_filter_combo.itemData(i) == prev_filter:
                    self._proj_filter_combo.setCurrentIndex(i)
                    break
        self._proj_filter_combo.blockSignals(False)

    def refresh_report_list(self) -> None:
        """Query reports from DB using current filter settings and repopulate table."""
        REPORTS_DIR.mkdir(exist_ok=True)

        conditions: list[str] = []
        params: list = []

        proj_data = self._proj_filter_combo.currentData()
        if proj_data == "UNASSIGNED":
            conditions.append("r.project_id IS NULL")
        elif proj_data is not None:
            conditions.append("r.project_id = ?")
            params.append(proj_data)

        type_data = self._type_filter_combo.currentData()
        if type_data:
            conditions.append("r.report_type = ?")
            params.append(type_data)

        show_data = self._show_filter_combo.currentData()
        if show_data == "active":
            conditions.append("r.is_archived = 0")
        elif show_data == "archived":
            conditions.append("r.is_archived = 1")

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        try:
            conn = get_connection()
            rows = conn.execute(
                f"""
                SELECT r.id, r.filename, r.file_path, r.report_type,
                       r.generated_at, r.is_archived, r.project_id,
                       p.name AS project_name, p.code_name,
                       s.name AS site_name
                  FROM reports r
                  LEFT JOIN projects p ON p.id = r.project_id
                  JOIN sites s ON s.id = r.site_id
                {where}
                 ORDER BY r.generated_at DESC
                """,
                params,
            ).fetchall()
            conn.close()
            self._report_rows = [dict(r) for r in rows]
        except Exception:
            self._report_rows = []

        self._report_table.setRowCount(0)
        for r in self._report_rows:
            row_idx = self._report_table.rowCount()
            self._report_table.insertRow(row_idx)

            proj_str = r.get("project_name") or "—"
            if r.get("code_name"):
                proj_str = f"{proj_str} ({r['code_name']})"

            cells = [
                r["filename"],
                proj_str,
                r.get("site_name") or "—",
                "Analysis" if r["report_type"] == "analysis" else "Voyage",
                r.get("generated_at") or "",
                "Yes" if r["is_archived"] else "No",
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(str(text))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, r)
                self._report_table.setItem(row_idx, col, item)

    def _refresh_station_count(self) -> None:
        try:
            from core.settings import get_session
            raw = get_session("selected_ndbc_stations")
            ids = json.loads(raw) if raw else []
        except Exception:
            ids = []
        n = len(ids)
        self._station_lbl.setText(
            f"{n} NDBC station{'s' if n != 1 else ''} selected "
            f"(configure in NDBC tab)."
        )

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_type_toggled(self, checked: bool) -> None:
        self._forecast_opts.setVisible(checked)
        if checked:
            self._refresh_station_count()

    def _horizon_hours(self) -> int:
        mapping = {0: 24, 1: 48, 2: 72, 3: 120, 4: 168}
        return mapping.get(self._horizon_combo.currentIndex(), 72)

    def _ndbc_station_ids(self) -> list[str]:
        try:
            from core.settings import get_session
            raw = get_session("selected_ndbc_stations")
            return json.loads(raw) if raw else []
        except Exception:
            return []

    def _on_combo_changed(self, idx: int) -> None:
        if not self._analyses or idx < 0 or idx >= len(self._analyses):
            return
        r = self._analyses[idx]
        mo = r.get("month_filter")
        mo_str = ["Jan","Feb","Mar","Apr","May","Jun",
                  "Jul","Aug","Sep","Oct","Nov","Dec"][mo-1] if mo else "All months"
        yr_s = r.get("year_start") or 1960
        yr_e = r.get("year_end")   or 2024
        self._detail_lbl.setText(
            f"<b>Site:</b> {r['site_name']}&nbsp;&nbsp;"
            f"<b>Vehicle:</b> {r['vehicle_name']}&nbsp;&nbsp;"
            f"<b>Platform:</b> {r['platform_name']}<br>"
            f"<b>Month:</b> {mo_str}&nbsp;&nbsp;"
            f"<b>Era:</b> {yr_s}-{yr_e}&nbsp;&nbsp;"
            f"<b>Probability:</b> {round((r['overall_prob'] or 0)*100)}%&nbsp;&nbsp;"
            f"<b>Limiting:</b> {r.get('limiting_param', '--')}"
        )
        self._open_btn.setVisible(False)
        self._result_lbl.setVisible(False)

    def _go_to_analysis(self) -> None:
        self._go_to_section("analysis")

    def _go_to_section(self, key: str) -> None:
        if hasattr(self.mw, "_on_section_changed"):
            self.mw._on_section_changed(key)
            if hasattr(self.mw, "sidebar"):
                self.mw.sidebar.select_section(key)

    def _on_generate(self) -> None:
        idx = self._analysis_combo.currentIndex()
        if idx < 0 or idx >= len(self._analyses):
            return
        row = self._analyses[idx]

        combined = self._combined_rb.isChecked()
        if combined and not self._ndbc_station_ids():
            QMessageBox.warning(
                self, "No NDBC Stations",
                "No NDBC stations are selected.\n\n"
                "Go to the NDBC Stations tab, fetch data, and select stations,\n"
                "then return here to generate the combined report.",
            )
            return

        project = self._proj_assoc_combo.currentData()  # Project or None

        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

        # Validate project has required naming fields if selected
        if project is not None:
            missing = []
            if not project.code_name:
                missing.append("project code name")
            if not project.launch_date_start:
                missing.append("launch date start")
            if not project.launch_date_end:
                missing.append("launch date end")
            if missing:
                box = QMessageBox(self)
                box.setIcon(QMessageBox.Icon.Warning)
                box.setWindowTitle("Incomplete Project")
                box.setText(
                    f"The selected project is missing: {', '.join(missing)}.\n\n"
                    "These are required to build the report filename. Set them "
                    "in the Projects section, or choose '— none —' here to "
                    "generate an unassigned report."
                )
                goto_btn = box.addButton("Go to Projects", QMessageBox.ButtonRole.ActionRole)
                box.addButton(QMessageBox.StandardButton.Ok)
                box.exec()
                if box.clickedButton() is goto_btn:
                    self._go_to_section("projects")
                return

        self._gen_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._result_lbl.setVisible(False)
        self._open_btn.setVisible(False)

        self._worker = _ReportWorker(
            analysis_row=row,
            output_dir=str(REPORTS_DIR),
            project=project,
            include_buoy_forecast=combined,
            ndbc_station_ids=self._ndbc_station_ids() if combined else [],
            forecast_horizon_hours=self._horizon_hours() if combined else 72,
        )
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_err)
        self._worker.start()

    def _on_done(self, path: str) -> None:
        self._last_path = path
        self._gen_btn.setEnabled(True)
        self._progress.setVisible(False)
        self._result_lbl.setText(f"Report saved:  {path}")
        self._result_lbl.setStyleSheet("color: #86efac;")
        self._result_lbl.setVisible(True)
        self._open_btn.setVisible(True)
        self.refresh_report_list()

    def _on_err(self, msg: str) -> None:
        self._gen_btn.setEnabled(True)
        self._progress.setVisible(False)
        self._result_lbl.setText(f"Error: {msg}")
        self._result_lbl.setStyleSheet("color: #fca5a5;")
        self._result_lbl.setVisible(True)
        QMessageBox.critical(self, "Report Error", msg)

    def _on_open(self) -> None:
        if self._last_path:
            self._open_file(self._last_path)

    def _on_table_double_click(self, row: int, col: int) -> None:
        if 0 <= row < len(self._report_rows):
            self._open_report(self._report_rows[row])

    def _on_table_context_menu(self, pos: QPoint) -> None:
        row = self._report_table.rowAt(pos.y())
        if row < 0 or row >= len(self._report_rows):
            return
        r = self._report_rows[row]

        menu = QMenu(self)

        open_act = QAction("Open", self)
        open_act.triggered.connect(lambda: self._open_report(r))
        menu.addAction(open_act)

        if r["is_archived"]:
            arch_act = QAction("Unarchive", self)
            arch_act.triggered.connect(lambda: self._set_archived(r["id"], False))
        else:
            arch_act = QAction("Archive", self)
            arch_act.triggered.connect(lambda: self._set_archived(r["id"], True))
        menu.addAction(arch_act)

        menu.addSeparator()

        del_act = QAction("Delete...", self)
        del_act.triggered.connect(lambda: self._delete_report(r))
        menu.addAction(del_act)

        menu.exec(self._report_table.viewport().mapToGlobal(pos))

    # ── Report actions ────────────────────────────────────────────────────────

    def _open_report(self, r: dict) -> None:
        self._open_file(r.get("file_path", ""))

    def _open_file(self, path: str) -> None:
        if not path:
            return
        try:
            from core.utils import open_local_path
            open_local_path(path)
        except Exception as exc:
            QMessageBox.warning(
                self, "Could Not Open File",
                f"Could not open:\n{path}\n\n{exc}"
            )

    def _set_archived(self, report_id: int, archived: bool) -> None:
        try:
            conn = get_connection()
            conn.execute(
                "UPDATE reports SET is_archived=? WHERE id=?",
                (1 if archived else 0, report_id),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            QMessageBox.warning(self, "Error", str(exc))
            return
        self.refresh_report_list()

    def _delete_report(self, r: dict) -> None:
        reply = QMessageBox.question(
            self, "Delete Report",
            f"Permanently delete '{r['filename']}'?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        ok, error = self._delete_report_row(r)
        if not ok:
            QMessageBox.warning(self, "Delete Error", error)
            return
        self.refresh_report_list()

    def _delete_report_row(self, r: dict) -> tuple[bool, str]:
        """Delete one report's file + DB row. No dialogs — callers own
        confirmation/error UI so single and batch delete each show one
        dialog instead of one per report."""
        try:
            fp = Path(r["file_path"])
            if fp.exists():
                fp.unlink()
        except Exception:
            pass  # file already gone / inaccessible — still remove the DB row
        try:
            conn = get_connection()
            conn.execute("DELETE FROM reports WHERE id=?", (r["id"],))
            conn.commit()
            conn.close()
        except Exception as exc:
            return False, str(exc)
        return True, ""

    def _delete_selected_reports(self) -> None:
        rows = sorted({idx.row() for idx in self._report_table.selectedIndexes()})
        targets = [self._report_rows[r] for r in rows if r < len(self._report_rows)]
        if not targets:
            QMessageBox.information(
                self, "No Selection", "Select one or more reports first."
            )
            return

        reply = QMessageBox.question(
            self, "Delete Selected",
            f"Permanently delete {len(targets)} report"
            f"{'s' if len(targets) != 1 else ''}?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        failures = []
        for r in targets:
            ok, error = self._delete_report_row(r)
            if not ok:
                failures.append(f"{r['filename']}: {error}")

        self.refresh_report_list()

        if failures:
            QMessageBox.warning(
                self, "Some Reports Could Not Be Deleted",
                "\n".join(failures)
            )

    def _archive_all_filtered(self) -> None:
        active_ids = [r["id"] for r in self._report_rows if not r["is_archived"]]
        if not active_ids:
            QMessageBox.information(self, "Nothing to Archive",
                                    "No active reports in the current filter.")
            return
        reply = QMessageBox.question(
            self, "Archive All Filtered",
            f"Archive {len(active_ids)} report(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            placeholders = ",".join("?" * len(active_ids))
            conn = get_connection()
            conn.execute(
                f"UPDATE reports SET is_archived=1 WHERE id IN ({placeholders})",
                active_ids,
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            QMessageBox.warning(self, "Archive Error", str(exc))
            return
        self.refresh_report_list()

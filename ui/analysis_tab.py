"""
ui/analysis_tab.py -- Tab 2: 12-month launch window probability analysis.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
    QApplication, QCheckBox, QFrame, QSpinBox, QRadioButton, QButtonGroup,
    QScrollArea, QProgressBar, QComboBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from config import BASE_DIR, DEFAULT_THRESHOLDS, refresh_analysis_year_spins
from ui import analysis_common as ac
from ui.widgets.analysis_charts import AnalysisChartsWidget
from ui.widgets.threshold_editor import ThresholdEditorWidget, threshold_editor_stylesheet

# Full-name labels for the eight engine parameters (used by the basis panel).
_PARAM_FULL = {
    "ws": "Wind speed", "wg": "Wind gust", "sh": "Sea wave height",
    "swh": "Swell height", "swp": "Swell period",
    "wdV": "Wind direction", "sdV": "Sea direction", "swdV": "Swell direction",
}
_MAGNITUDE_PARAMS = ["ws", "wg", "sh", "swh", "swp"]
_DIRECTION_PARAMS = ["wdV", "sdV", "swdV"]


def unit_for(param: str) -> str:
    units = {
        "ws":   "kts",
        "wg":   "kts",
        "sh":   "m",
        "swh":  "m",
        "swp":  "s",
        "wdV":  "°",
        "sdV":  "°",
        "swdV": "°",
    }
    return units.get(param, "")


_MO = ["Jan","Feb","Mar","Apr","May","Jun",
       "Jul","Aug","Sep","Oct","Nov","Dec"]

# Dark-theme verdict colors
_GO_BG       = QColor('#14532d')
_GO_FG       = QColor('#86efac')
_MARGINAL_BG = QColor('#422006')
_MARGINAL_FG = QColor('#fde68a')
_NOGO_BG     = QColor('#450a0a')
_NOGO_FG     = QColor('#fca5a5')
_DEFAULT_FG  = QColor('#f1f5f9')

_BTN_PRIMARY = (
    "QPushButton {"
    "  background: #2563eb; color: white;"
    "  border-radius: 4px; padding: 6px 20px; font-weight: bold; border: none;"
    "}"
    "QPushButton:hover  { background: #1d4ed8; }"
    "QPushButton:disabled { background: #1e3a5f; color: #64748b; }"
)
_BTN_GREEN = (
    "QPushButton {"
    "  background: #166534; color: white;"
    "  border-radius: 4px; padding: 6px 20px; font-weight: bold; border: none;"
    "}"
    "QPushButton:hover  { background: #15803d; }"
    "QPushButton:disabled { background: #14532d; color: #64748b; }"
)


class AnalysisTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._profile: dict = {}   # month (1-12) -> AnalysisResult
        self._ncei_worker = None
        self._era5_worker = None
        self._last_operability_limits: tuple[float, float] = (25.0, 1.8)
        self._build()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        refresh_analysis_year_spins(self.year_start_spin, self.year_end_spin)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Whole-tab scroll: the Calculation Basis panel and the charts below the
        # table can each be several hundred px tall, so instead of trapping the
        # basis panel in its own 180px inner scroll box (the old behaviour that
        # made it unreadable), the entire tab scrolls and every block grows to
        # its natural height.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { border:none; background:#0f1923; }"
            "QScrollBar:vertical { background:#0f1923; width:10px; }"
            "QScrollBar::handle:vertical { background:#374151; border-radius:5px; }"
        )
        content = QWidget()
        content.setStyleSheet("background:#0f1923;")
        outer.addWidget(scroll)

        root = QVBoxLayout(content)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        title = QLabel("Launch Window Analysis")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #f1f5f9;")
        root.addWidget(title)

        self.site_label = QLabel(
            "No site selected.  Open a project (Projects tab) to load its sites."
        )
        self.site_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
        root.addWidget(self.site_label)

        # Project site selector — shown when the open project has more than one
        # site, so the user can pick which one this analysis runs against.
        self.site_selector_row = QWidget()
        ssr = QHBoxLayout(self.site_selector_row)
        ssr.setContentsMargins(0, 0, 0, 0)
        ssr.setSpacing(8)
        sel_lbl = QLabel("Analyse site:")
        sel_lbl.setStyleSheet("color:#94a3b8; font-size:11px;")
        ssr.addWidget(sel_lbl)
        self.site_combo = QComboBox()
        self.site_combo.setMinimumWidth(320)
        self.site_combo.setStyleSheet(
            "QComboBox { background:#1a2233; color:#e2e8f0; border:1px solid #374151;"
            " border-radius:4px; padding:4px 8px; }"
            "QComboBox QAbstractItemView { background:#1a2233; color:#e2e8f0;"
            " selection-background-color:#2563eb; }"
        )
        self.site_combo.currentIndexChanged.connect(self._on_site_selected)
        ssr.addWidget(self.site_combo)
        ssr.addStretch()
        self.site_selector_row.setVisible(False)
        root.addWidget(self.site_selector_row)

        # Fetch-status banner — the live weather fetches this tab triggers
        # (NCEI, ERA5, WW3 ERDDAP) are synchronous and can take anywhere from
        # a couple seconds to several minutes (WW3 measured ~13min cold —
        # see CLAUDE.md), during which the app would otherwise look frozen.
        # Hidden by default; shown/hidden via _set_fetch_status().
        self.fetch_status_widget = QWidget()
        fetch_row = QHBoxLayout(self.fetch_status_widget)
        fetch_row.setContentsMargins(0, 0, 0, 0)
        fetch_row.setSpacing(8)
        self.fetch_progress = QProgressBar()
        self.fetch_progress.setRange(0, 0)   # indeterminate "busy" style
        self.fetch_progress.setFixedWidth(140)
        self.fetch_progress.setFixedHeight(12)
        self.fetch_progress.setTextVisible(False)
        self.fetch_progress.setStyleSheet(
            "QProgressBar { background: #1a2233; border: 1px solid #374151;"
            " border-radius: 4px; }"
            "QProgressBar::chunk { background: #2563eb; border-radius: 4px; }"
        )
        fetch_row.addWidget(self.fetch_progress)
        self.fetch_status_label = QLabel()
        self.fetch_status_label.setStyleSheet(
            "color: #fde68a; font-size: 10px; font-weight: 600;"
        )
        fetch_row.addWidget(self.fetch_status_label)
        fetch_row.addStretch()
        self.fetch_status_widget.setVisible(False)
        root.addWidget(self.fetch_status_widget)

        # Controls row
        ctrl = QHBoxLayout()

        self.run_btn = QPushButton("Run 12-Month Profile")
        self.run_btn.setMinimumHeight(34)
        self.run_btn.setEnabled(False)
        self.run_btn.setStyleSheet(_BTN_PRIMARY)
        self.run_btn.clicked.connect(self._run)
        ctrl.addWidget(self.run_btn)

        self.pdf_btn = QPushButton("Export Analysis PDF")
        self.pdf_btn.setMinimumHeight(34)
        self.pdf_btn.setEnabled(False)
        self.pdf_btn.setStyleSheet(_BTN_GREEN)
        self.pdf_btn.clicked.connect(self._export_pdf)
        ctrl.addWidget(self.pdf_btn)

        ctrl.addStretch()
        root.addLayout(ctrl)

        # Direction-parameter inclusion row (Set 27B).
        # Checkboxes default to their DB setting: excluded ('1') → unchecked.
        from core.settings import get_setting
        dir_ctrl = QHBoxLayout()
        dir_lbl = QLabel("Direction parameters:")
        dir_lbl.setStyleSheet("color: #94a3b8; font-size: 10px;")
        dir_ctrl.addWidget(dir_lbl)

        _CB_STYLE = "QCheckBox { color: #e2e8f0; font-size: 10px; }"
        self.cb_wind_dir  = QCheckBox("Wind direction")
        self.cb_sea_dir   = QCheckBox("Sea direction")
        self.cb_swell_dir = QCheckBox("Swell direction")
        for cb in (self.cb_wind_dir, self.cb_sea_dir, self.cb_swell_dir):
            cb.setStyleSheet(_CB_STYLE)
            dir_ctrl.addWidget(cb)

        # A checkbox is checked when the parameter is INCLUDED; the setting stores
        # '1' for excluded and '0' for included, so checked = (setting == '0').
        self.cb_wind_dir.setChecked(get_setting("exclude_wind_dir", "1") == "0")
        self.cb_sea_dir.setChecked(get_setting("exclude_sea_dir", "1") == "0")
        self.cb_swell_dir.setChecked(get_setting("exclude_swell_dir", "1") == "0")

        hint = QLabel("(excluded from the overall probability unless checked)")
        hint.setStyleSheet("color: #64748b; font-size: 8pt; font-style: italic;")
        dir_ctrl.addWidget(hint)
        dir_ctrl.addStretch()
        root.addLayout(dir_ctrl)

        # Mode + year range row (Set 34, items 14/15). '45day' uses a live
        # NDBC/near-term snapshot instead of ICOADS climatology, so the year
        # range only applies to Historical mode — disabled otherwise.
        mode_ctrl = QHBoxLayout()
        mode_lbl = QLabel("Mode:")
        mode_lbl.setStyleSheet("color: #94a3b8; font-size: 10px;")
        mode_ctrl.addWidget(mode_lbl)

        self._mode_group = QButtonGroup(self)
        self.rb_historical = QRadioButton("Historical")
        self.rb_45day = QRadioButton("45-Day (live)")
        self.rb_historical.setChecked(True)
        for rb in (self.rb_historical, self.rb_45day):
            rb.setStyleSheet(_CB_STYLE)
            self._mode_group.addButton(rb)
            mode_ctrl.addWidget(rb)
        self.rb_historical.toggled.connect(self._on_mode_toggled)

        mode_ctrl.addSpacing(16)
        year_lbl = QLabel("Year range:")
        year_lbl.setStyleSheet("color: #94a3b8; font-size: 10px;")
        mode_ctrl.addWidget(year_lbl)

        self.year_start_spin = QSpinBox()
        self.year_start_spin.setValue(1960)
        mode_ctrl.addWidget(self.year_start_spin)

        to_lbl = QLabel("–")
        to_lbl.setStyleSheet("color: #64748b; font-size: 10px;")
        mode_ctrl.addWidget(to_lbl)

        self.year_end_spin = QSpinBox()
        from datetime import date as _date
        self.year_end_spin.setValue(min(_date.today().year, 2024))
        mode_ctrl.addWidget(self.year_end_spin)
        refresh_analysis_year_spins(self.year_start_spin, self.year_end_spin)

        mode_ctrl.addStretch()
        root.addLayout(mode_ctrl)

        clim_hint = QLabel(
            "Historical mode fetches Copernicus ERA5 monthly data for the selected "
            "year range; calendar months are pooled across those years for "
            "charts 1–10 and 11–12. Recent years may require a new ERA5 download."
        )
        clim_hint.setWordWrap(True)
        clim_hint.setStyleSheet("color: #64748b; font-size: 10px;")
        root.addWidget(clim_hint)

        # Optimal-values (threshold) editor. Pre-filled from the active
        # vehicle's own limits in on_site_changed(); if the operator leaves
        # them untouched the run uses those system defaults, otherwise the
        # edited values override the engine thresholds for this run.
        self.threshold_editor = ThresholdEditorWidget()
        self.threshold_editor.setStyleSheet(threshold_editor_stylesheet())
        # System-default operating limits, independent of the selected vehicle
        # (vehicle no longer influences the analysis — see config).
        self.threshold_editor.set_defaults(DEFAULT_THRESHOLDS)
        root.addWidget(self.threshold_editor)

        # Results table
        self.table = QTableWidget(12, 4)
        self.table.setHorizontalHeaderLabels(
            ["Month", "Probability", "Verdict", "Limiting Parameter"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        # Apply dark theme explicitly — QSS inheritance is unreliable inside tab panels
        from ui.styles import apply_table_colors
        apply_table_colors(self.table)

        # The whole tab now scrolls (see _build's QScrollArea), so the table is
        # given a fixed sensible height that shows all 12 rows rather than
        # competing for leftover space with the basis panel below it.
        self.table.setMinimumHeight(360)
        root.addWidget(self.table)

        # Summary strip
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(
            "background: #1e3a5f; border: 1px solid #2563eb;"
            "border-radius: 4px; padding: 10px; color: #e2e8f0;"
        )
        self.summary_label.setVisible(False)
        root.addWidget(self.summary_label)

        # Vessel pre-check row (Pre-28B-1) — shows the platform-contract verdict
        # alongside the vehicle result, or a "no contract linked" indicator.
        self.vessel_label = QLabel()
        self.vessel_label.setWordWrap(True)
        self.vessel_label.setTextFormat(Qt.TextFormat.RichText)
        self.vessel_label.setVisible(False)
        root.addWidget(self.vessel_label)

        # Data source badges
        self.sources_label = QLabel()
        self.sources_label.setWordWrap(True)
        self.sources_label.setStyleSheet("color: #94a3b8; font-size: 8pt;")
        self.sources_label.setVisible(False)
        root.addWidget(self.sources_label)

        # Decision charts (matplotlib) — fed by self._profile after each run.
        charts_title = QLabel("Decision Charts")
        charts_title.setStyleSheet("color:#f1f5f9; font-size:11pt; font-weight:600;")
        root.addWidget(charts_title)
        self.charts = AnalysisChartsWidget()
        root.addWidget(self.charts)

        # Calculation basis panel (Set 27B) — persistent read-only summary of
        # the inputs behind the most recent run. Populated by update_basis_panel().
        #
        # No longer trapped in a 180px inner QScrollArea (the old fix that made
        # it unreadable): the whole tab scrolls now, so this panel simply grows
        # to fit its content like every other block.
        basis_title = QLabel("Calculation Basis")
        basis_title.setStyleSheet("color:#f1f5f9; font-size:11pt; font-weight:600;")
        root.addWidget(basis_title)
        self.basis_panel = QLabel(
            "No analysis run yet. Configure parameters above and click "
            "Run 12-Month Profile."
        )
        self.basis_panel.setWordWrap(True)
        self.basis_panel.setTextFormat(Qt.TextFormat.RichText)
        self.basis_panel.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.basis_panel.setStyleSheet(
            "QLabel { background: #2d3748; color: #64748b; font-size: 11px;"
            " border: 1px solid #374151; border-radius: 6px; padding: 12px 16px; }"
        )
        root.addWidget(self.basis_panel)

        scroll.setWidget(content)

    def _on_mode_toggled(self, checked: bool) -> None:
        """Year range only applies to Historical mode (ignored by the engine
        in 45day mode, per compute_probability()'s own docstring)."""
        self.year_start_spin.setEnabled(checked)
        self.year_end_spin.setEnabled(checked)

    def _set_fetch_status(
        self,
        msg: str | None,
        *,
        done: int | None = None,
        total: int | None = None,
        indeterminate: bool = False,
    ) -> None:
        """Show/hide the in-tab busy banner for a live data fetch or the run
        itself. msg=None hides the banner and restores the Run button.

        done/total drive a determinate progress bar; indeterminate=True or
        done=-1 uses the busy (marquee) style during CDS queue waits.
        """
        if msg is None:
            self.fetch_status_widget.setVisible(False)
            self.fetch_progress.setRange(0, 0)
            self.run_btn.setEnabled(self.mw.site is not None)
            return
        self.fetch_status_label.setText(msg)
        self.fetch_status_widget.setVisible(True)
        if indeterminate or done is not None and done < 0:
            self.fetch_progress.setRange(0, 0)
        elif done is not None and total is not None and total > 0:
            self.fetch_progress.setRange(0, total)
            self.fetch_progress.setValue(min(done, total))
        else:
            self.fetch_progress.setRange(0, 0)
        self.run_btn.setEnabled(False)
        self.mw.status(msg)
        QApplication.processEvents()

    # ── Slot called by MainWindow ─────────────────────────────────────────────

    def on_site_changed(self) -> None:
        if self.mw.site:
            self.site_label.setText(
                f"Site: {self.mw.site.coord_str}  |  "
                f"{self.mw.vehicle.name}  |  {self.mw.platform.name}"
            )
            self.site_label.setStyleSheet("color: #86efac; font-size: 11px;")
            self.run_btn.setEnabled(True)
        else:
            self.site_label.setText(
                "No site selected.  Open a project (Projects tab) to load its sites."
            )
            self.site_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
            self.run_btn.setEnabled(False)
        self._profile = {}
        self._clear_table()
        self.pdf_btn.setEnabled(False)
        self.summary_label.setVisible(False)
        self.sources_label.setVisible(False)
        self.vessel_label.setVisible(False)
        self.vessel_label.setVisible(False)
        self.charts.set_profile({})
        self._reset_basis_panel()
        self._cancel_background_workers()

    def _cancel_background_workers(self) -> None:
        for worker in (self._ncei_worker, self._era5_worker):
            if worker is not None and worker.isRunning():
                worker.cancel()
                worker.wait(3000)
        self._ncei_worker = None
        self._era5_worker = None

    def _vehicle_operability_limits(self) -> tuple[float, float]:
        """Wind / Hs limits from Optimal Values panel (falls back to defaults)."""
        vals = self.threshold_editor.values()
        return float(vals.get("ws", 20.0)), float(vals.get("sh", 1.83))

    def _active_criteria_params(self, weights: dict | None = None) -> list[str]:
        """All params with non-zero weight (magnitude + opted-in direction)."""
        from modules.m2_weather.operability import criteria_params_from_weights

        w = weights if weights is not None else self._active_weights()
        return criteria_params_from_weights(w)

    def _start_background_fetches(self, site, mode: str) -> None:
        """45-Day mode only: background NCEI fill for operability heatmaps."""
        if mode != "45day":
            return
        from core.utils import ncei_bbox_str
        from modules.m2_weather.climatology import climatology_year_range
        from modules.m2_weather.ncei_download import (
            NceiDownloadWorker,
            ncei_fetch_incomplete,
        )

        ys, ye = climatology_year_range()
        bbox = ncei_bbox_str(site.lat, site.lon, site.bbox_nm)
        wind_kts, hs_m = self._vehicle_operability_limits()
        self._last_operability_limits = (wind_kts, hs_m)

        if ncei_fetch_incomplete(bbox, ys, ye):
            self._ncei_worker = NceiDownloadWorker(
                site.lat, site.lon, site.bbox_nm, ys, ye,
            )
            self._ncei_worker.progress.connect(self._on_ncei_progress)
            self._ncei_worker.finished.connect(self._on_ncei_finished)
            self._ncei_worker.error.connect(self._on_ncei_error)
            self._ncei_worker.start()

    def _on_ncei_progress(self, done: int, total: int, _new: int) -> None:
        self.charts.update_operability_progress(done, total)
        self.mw.status(f"NCEI operability cache: month {done} of {total}…")

    def _on_ncei_finished(self, _new: int, _cached: int) -> None:
        if not self.mw.site or not self._profile:
            return
        if not self.rb_45day.isChecked():
            return
        from modules.m2_weather.operability import build_operability_heatmaps_for_site

        wind_kts, hs_m = self._last_operability_limits
        try:
            operability = build_operability_heatmaps_for_site(
                self.mw.site, wind_kts, hs_m,
            )
            self.charts.set_operability(operability)
        except Exception:
            pass
        self.mw.status("NCEI operability cache update complete.")

    def _on_ncei_error(self, msg: str) -> None:
        self.mw.status(f"NCEI fetch error: {msg}")

    def on_project_changed(self) -> None:
        """Rebuild the project-site selector from the main window's open-project
        state. Called by GatewayMainWindow.open_project()/close_project()."""
        sites = getattr(self.mw, "open_project_sites", []) or []
        self.site_combo.blockSignals(True)
        self.site_combo.clear()
        for s in sites:
            label = f"{s.name or 'Unnamed'}  ({s.coord_str})"
            self.site_combo.addItem(label, s.id)
        # Select the currently active site if it is among the project sites.
        target = 0
        active_id = getattr(self.mw.site, "id", None)
        if active_id is not None:
            for i, s in enumerate(sites):
                if s.id == active_id:
                    target = i
                    break
        if sites:
            self.site_combo.setCurrentIndex(target)
        self.site_combo.blockSignals(False)
        # Only offer the picker when there's a real choice to make.
        self.site_selector_row.setVisible(len(sites) > 1)
        self.on_site_changed()

    def _on_site_selected(self, idx: int) -> None:
        sites = getattr(self.mw, "open_project_sites", []) or []
        if idx < 0 or idx >= len(sites):
            return
        self.mw.site = sites[idx]
        # Resolve platform + refresh labels/table (also refreshes Ports tab).
        self.mw.on_site_changed()

    def _update_vessel_row(self, result) -> None:
        """Render the vessel pre-check verdict (Pre-28B-1). Shows a gray
        'no contract linked' indicator when no contract governs the run."""
        _BADGE = {
            "GO":       ("#14532d", "#86efac"),
            "MARGINAL": ("#422006", "#fde68a"),
            "NO-GO":    ("#450a0a", "#fca5a5"),
        }
        if getattr(result, "vessel_verdict", None) is None:
            self.vessel_label.setText(
                "<span style='background:#374151;color:#94a3b8;padding:2px 8px;"
                "border-radius:3px;font-size:11px;'>VESSEL: No contract linked</span>"
            )
            self.vessel_label.setStyleSheet("padding: 2px;")
            self.vessel_label.setVisible(True)
            return

        bg, fg = _BADGE.get(result.vessel_verdict, ("#374151", "#94a3b8"))
        parts = [
            f"<span style='background:{bg};color:{fg};padding:2px 8px;"
            f"border-radius:3px;font-size:12px;font-weight:bold;'>"
            f"VESSEL: {result.vessel_verdict}</span>"
        ]
        if result.vessel_contract_code:
            parts.append(
                f"<span style='color:#94a3b8;font-size:9pt;'>&nbsp; "
                f"Contract: {result.vessel_contract_code}</span>"
            )
        if not getattr(result, "warranted_verified", False):
            parts.append(
                "<br><span style='background:#422006;color:#fde68a;padding:2px 6px;"
                "border-radius:3px;font-size:9pt;'>⚠ Unverified envelope — verify "
                "against contract before operational use</span>"
            )
        if result.vessel_limiting_param:
            parts.append(
                f"<br><span style='color:#94a3b8;font-size:9pt;'>Limiting: "
                f"{result.vessel_limiting_param}</span>"
            )
        self.vessel_label.setText("".join(parts))
        self.vessel_label.setStyleSheet("padding: 2px;")
        self.vessel_label.setVisible(True)

    def _reset_basis_panel(self) -> None:
        self.basis_panel.setStyleSheet(
            "QLabel { background: #2d3748; padding: 12px 16px;"
            " color: #64748b; font-size: 11px;"
            " border: 1px solid #374151; border-radius: 6px; }"
        )
        self.basis_panel.setText(
            "No analysis run yet. Configure parameters above and click "
            "Run 12-Month Profile."
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _clear_table(self) -> None:
        ac.clear_profile_table(self.table)

    def _run(self) -> None:
        if not self.mw.site:
            return

        # Require site saved to DB so analyses can be linked
        if getattr(self.mw.site, 'id', None) is None:
            QMessageBox.warning(
                self, "Site Not Saved",
                "Please click 'Apply & Save Site' in the Sites section first.\n"
                "The site must be saved to the database before analysis can be stored."
            )
            return

        self._cancel_background_workers()

        from modules.m3_probability.engine import compute_annual_profile

        active_weights = self._active_weights()
        platform_contract = self._resolve_active_platform_contract()
        thresholds_override = self.threshold_editor.values()

        mode = "45day" if self.rb_45day.isChecked() else "historical"
        year_start = self.year_start_spin.value()
        year_end = self.year_end_spin.value()
        observed_means = None
        observed_means_by_month = None
        climatology = None
        operability = None
        operability_progress = None
        wind_kts, hs_m = self._vehicle_operability_limits()
        self._last_operability_limits = (wind_kts, hs_m)

        try:
            if mode == "45day":
                self._set_fetch_status("Fetching live 45-day weather data…", indeterminate=True)
                try:
                    from modules.m2_weather.data_manager import get_site_weather_summary
                    observed_means = get_site_weather_summary(self.mw.site, mode="45day")
                except Exception:
                    observed_means = None
            else:
                from modules.m2_weather.climatology import build_monthly_climatology
                from modules.m2_weather.era5_ensure import ensure_era5_cache_blocking
                from modules.m2_weather.operability import build_era5_operability_heatmaps

                span = year_end - year_start + 1
                if span > 20:
                    QMessageBox.information(
                        self,
                        "Large Year Range",
                        f"The selected range spans {span} years. The first Copernicus "
                        "ERA5 download may take 20–45+ minutes.",
                    )

                def _era5_progress(done: int, total: int, detail: str) -> None:
                    if done < 0:
                        self._set_fetch_status(
                            f"Fetching Copernicus ERA5 for charts 1–10… {detail}",
                            indeterminate=True,
                        )
                    else:
                        self._set_fetch_status(
                            f"Fetching Copernicus ERA5 for charts 1–10… {detail}",
                            done=done,
                            total=total if total > 0 else None,
                        )

                ok, err = ensure_era5_cache_blocking(
                    self.mw.site.lat,
                    self.mw.site.lon,
                    year_start,
                    year_end,
                    on_progress=_era5_progress,
                )
                if not ok:
                    QMessageBox.warning(
                        self,
                        "ERA5 Fetch Failed",
                        err or "Copernicus ERA5 data could not be retrieved.",
                    )
                    return

                self._set_fetch_status(
                    "Analyzing 12-month profile (charts 1–10)…",
                    indeterminate=True,
                )
                climatology = build_monthly_climatology(
                    self.mw.site, year_start, year_end, wind_kts, hs_m,
                )
                observed_means_by_month = climatology.by_month

            if mode == "45day":
                self._set_fetch_status(
                    "Running 12-month analysis…",
                    indeterminate=True,
                )

            self._profile = compute_annual_profile(
                self.mw.site, self.mw.vehicle, self.mw.platform,
                year_start=year_start,
                year_end=year_end,
                weights=active_weights,
                platform_contract=platform_contract,
                mode=mode,
                observed_means=observed_means,
                observed_means_by_month=observed_means_by_month,
                thresholds_override=thresholds_override,
            )

            criteria_params = self._active_criteria_params(active_weights)

            if mode == "historical":
                # Chart 1 / table verdict: avg % of days/month (full analysis
                # range) where every active optimal criterion is met.
                from modules.m2_weather.operability import (
                    apply_day_fraction_verdicts,
                    direction_supplemental_means,
                    monthly_all_criteria_day_fractions,
                    monthly_per_param_criterion_fractions,
                )
                supplemental = direction_supplemental_means(
                    self._profile, criteria_params,
                )
                day_frac = monthly_all_criteria_day_fractions(
                    self.mw.site,
                    year_start,
                    year_end,
                    thresholds=thresholds_override,
                    active_params=criteria_params,
                    supplemental_means_by_month=supplemental,
                )
                param_frac = monthly_per_param_criterion_fractions(
                    self.mw.site,
                    year_start,
                    year_end,
                    thresholds=thresholds_override,
                    active_params=criteria_params,
                    supplemental_means_by_month=supplemental,
                )
                apply_day_fraction_verdicts(
                    self._profile,
                    day_frac,
                    thresholds=thresholds_override,
                    active_params=criteria_params,
                )
            else:
                day_frac = None
                from modules.m2_weather.operability import (
                    per_param_criterion_fractions_from_profile,
                )
                param_frac = per_param_criterion_fractions_from_profile(
                    self._profile,
                    thresholds=thresholds_override,
                    active_params=criteria_params,
                )

            chart_kw = dict(
                thresholds=thresholds_override,
                active_criteria=criteria_params,
                day_fractions=day_frac,
                param_fractions=param_frac,
            )

            if mode == "45day":
                try:
                    from core.utils import ncei_bbox_str
                    from modules.m2_weather.ncei_download import (
                        initial_operability_progress,
                        operability_year_range,
                    )
                    from modules.m2_weather.operability import build_operability_heatmaps_for_site

                    ys, ye = operability_year_range()
                    operability = build_operability_heatmaps_for_site(
                        self.mw.site, wind_kts, hs_m,
                    )
                    bbox = ncei_bbox_str(
                        self.mw.site.lat, self.mw.site.lon, self.mw.site.bbox_nm,
                    )
                    operability_progress = initial_operability_progress(bbox, ys, ye)
                except Exception:
                    operability = None
                    operability_progress = None

                self._populate_table()
                self._populate_summary()
                self._populate_sources()
                self.charts.set_profile(
                    self._profile,
                    operability=operability,
                    operability_progress=operability_progress,
                    climatology=climatology,
                    **chart_kw,
                )
            else:
                self._populate_table()
                self._populate_summary()
                self._populate_sources()
                self.charts.set_profile_charts_1_10(
                    self._profile,
                    climatology=climatology,
                    **chart_kw,
                )
                QApplication.processEvents()

                from modules.m2_weather.operability import era5_operability_year_range

                # Charts 11–12: always last 10 calendar years, all criteria.
                op_ys, op_ye = era5_operability_year_range()

                def _op_fetch_progress(done: int, total: int, detail: str) -> None:
                    if done < 0:
                        self._set_fetch_status(
                            f"Fetching ERA5 for charts 11–12 ({op_ys}–{op_ye})… {detail}",
                            indeterminate=True,
                        )
                    else:
                        self._set_fetch_status(
                            f"Fetching ERA5 for charts 11–12 ({op_ys}–{op_ye})… {detail}",
                            done=done,
                            total=total if total > 0 else None,
                        )

                ok_op, err_op = ensure_era5_cache_blocking(
                    self.mw.site.lat,
                    self.mw.site.lon,
                    op_ys,
                    op_ye,
                    on_progress=_op_fetch_progress,
                )
                if not ok_op:
                    QMessageBox.warning(
                        self,
                        "ERA5 Operability Fetch",
                        err_op
                        or "Could not load the last-10-year ERA5 cache for charts 11–12.",
                    )

                def _op_progress(done: int, total: int, _detail: str) -> None:
                    self._set_fetch_status(
                        "Building operability heatmaps (charts 11–12)…",
                        done=done,
                        total=total,
                    )

                operability = build_era5_operability_heatmaps(
                    self.mw.site,
                    op_ys,
                    op_ye,
                    wind_kts,
                    hs_m,
                    thresholds=thresholds_override,
                    active_params=criteria_params,
                    on_progress=_op_progress,
                )
                self.charts.set_operability(operability, climatology=climatology)

            best_month = max(self._profile, key=lambda m: self._profile[m].overall_prob)
            self.update_basis_panel(self._profile[best_month])
            self._update_vessel_row(self._profile[best_month])
            self.pdf_btn.setEnabled(True)
        finally:
            self._set_fetch_status(None)

        self._start_background_fetches(self.mw.site, mode=mode)
        self.mw.status("Analysis complete.")
        self._save_to_db()
        self._record_site_vehicle()

    def _resolve_active_platform_contract(self):
        """
        Look up the platform_contracts row linked to the currently active
        project (self.mw.active_project_id, set by the By Project
        Activate/Deactivate pairing mechanism), if any.

        Returns None — and the vessel pre-check gate stays fully skipped,
        "No contract linked" behavior applies unchanged — when: there is no
        active project, the project has no linked contract
        (projects.platform_contract_id IS NULL), or the lookup fails for any
        reason. Never raises.
        """
        project_id = getattr(self.mw, "active_project_id", None)
        if project_id is None:
            return None
        try:
            from core.database import get_connection
            conn = get_connection()
            row = conn.execute(
                "SELECT platform_contract_id FROM projects WHERE id=?",
                (project_id,),
            ).fetchone()
            conn.close()
            if row is None or row["platform_contract_id"] is None:
                return None
            from modules.m1_site.contracts import get_contract
            return get_contract(row["platform_contract_id"])
        except Exception:
            return None

    def _active_weights(self) -> dict:
        """Build the active weight dict — magnitude weights plus opted-in
        direction params (shared with Quick Analysis via analysis_common)."""
        return ac.active_weights(
            self.cb_wind_dir.isChecked(),
            self.cb_sea_dir.isChecked(),
            self.cb_swell_dir.isChecked(),
        )

    def _record_site_vehicle(self) -> None:
        """Upsert the (site, vehicle) pair into site_vehicles after a run."""
        site = self.mw.site
        vehicle = self.mw.vehicle
        if getattr(site, "id", None) is not None and getattr(vehicle, "id", None) is not None:
            self._upsert_site_vehicle(site.id, vehicle.id)
        else:
            print(
                "WARNING: site_vehicles upsert skipped — "
                f"site.id={getattr(site, 'id', None)}, "
                f"vehicle.id={getattr(vehicle, 'id', None)}"
            )

    def _upsert_site_vehicle(self, site_id: int, vehicle_id: int) -> None:
        """
        Insert or increment the site_vehicles usage row for this pair.
        Non-fatal: the analysis result has already been saved, so any failure
        here is logged but never surfaced to the user.
        """
        from core.database import get_connection
        from datetime import datetime, timezone
        conn = get_connection()
        try:
            conn.execute(
                """
                INSERT INTO site_vehicles (site_id, vehicle_id, run_count, last_used)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(site_id, vehicle_id) DO UPDATE SET
                    run_count = run_count + 1,
                    last_used = excluded.last_used
                """,
                (site_id, vehicle_id, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        except Exception as e:
            print(f"site_vehicles upsert failed: {e}")
        finally:
            conn.close()

    def _save_to_db(self) -> None:
        """Save aggregate analysis result to analyses table."""
        if not self._profile:
            return
        site = self.mw.site
        vehicle = self.mw.vehicle
        platform = self.mw.platform
        if not (getattr(site, 'id', None) and getattr(vehicle, 'id', None)
                and getattr(platform, 'id', None)):
            return

        # Use the month with highest probability as the representative result
        best_month = max(self._profile.keys(), key=lambda m: self._profile[m].overall_prob)
        result = self._profile[best_month]

        try:
            from core.database import get_connection
            conn = get_connection()
            conn.execute("""
                INSERT INTO analyses (
                    site_id, vehicle_id, platform_id,
                    mode, year_start, year_end, month_filter,
                    param_probs_json, overall_prob,
                    limiting_param, data_sources_json,
                    confidence_rating
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                site.id,
                vehicle.id,
                platform.id,
                getattr(result, 'mode', 'historical'),
                getattr(result, 'year_start', 1960),
                getattr(result, 'year_end', 2024),
                None,  # NULL = all months (12-month profile)
                json.dumps(getattr(result, 'param_probs', {})),
                result.overall_prob,
                result.limiting_param,
                json.dumps(getattr(result, 'data_sources', {})),
                getattr(result, 'confidence_rating', 'model'),
            ))
            conn.commit()
            conn.close()
        except Exception:
            pass  # DB save failure must not block the UI result

    def _populate_table(self) -> None:
        ac.populate_profile_table(self.table, self._profile)

    def _populate_summary(self) -> None:
        self.summary_label.setText(ac.summary_html(self._profile))
        self.summary_label.setVisible(True)

    def _populate_sources(self) -> None:
        html = ac.sources_html(self._profile)
        if not html:
            return
        self.sources_label.setText(html)
        self.sources_label.setVisible(True)

    # ── Calculation basis panel (Set 27B) ────────────────────────────────────

    def update_basis_panel(self, result) -> None:
        """Populate the calculation basis panel from an AnalysisResult (shared
        renderer in analysis_common, also used by Quick Analysis)."""
        self.basis_panel.setStyleSheet(
            "QLabel { background: #2d3748; padding: 12px 16px;"
            " border: 1px solid #374151; border-radius: 6px; }"
        )
        self.basis_panel.setText(ac.basis_html(result))

    def _export_pdf(self) -> None:
        if not self._profile or not self.mw.site:
            return
        import shutil
        import tempfile

        from modules.m5_reports.pdf_report import generate_analysis_report

        # Use the already-computed profile (respects the run's actual mode/
        # year-range settings) instead of silently recomputing a fresh
        # single-month result — this also fixes the PDF only ever showing
        # the current calendar month regardless of what was analyzed
        # (Set 34, item 13). Cover page defaults to the current calendar
        # month's result when present, else the first computed month.
        month  = datetime.now(timezone.utc).month
        result = self._profile.get(month) or next(iter(self._profile.values()))

        reports_dir = BASE_DIR / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        ts           = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        default_name = f"gateway_report_{ts}.pdf"

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Analysis Report", str(reports_dir / default_name),
            "PDF files (*.pdf)"
        )
        if not path:
            return

        chart_tmpdir = tempfile.mkdtemp(prefix="gateway_charts_")
        try:
            from modules.m5_reports.analysis_chart_pages import (
                build_analysis_chart_pages,
            )
            chart_pages = build_analysis_chart_pages(
                chart_tmpdir,
                self._profile,
                climatology=getattr(self.charts, "_climatology", None),
                operability=getattr(self.charts, "_operability", None),
                thresholds=getattr(self.charts, "_thresholds", None),
                active_criteria=getattr(self.charts, "_active_criteria", None),
                day_fractions=getattr(self.charts, "_day_fractions", None),
                param_fractions=getattr(self.charts, "_param_fractions", None),
            )
            saved = generate_analysis_report(
                result,
                path,
                annual_profile=self._profile,
                chart_pages=chart_pages,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))
            return
        finally:
            shutil.rmtree(chart_tmpdir, ignore_errors=True)

        self.mw.status(f"Report saved: {saved}")
        try:
            from core.utils import open_local_path
            open_local_path(saved)
        except Exception as exc:
            # Save already succeeded — don't report this as an export failure.
            QMessageBox.warning(
                self, "Report Saved",
                f"PDF saved to:\n{saved}\n\n"
                f"Could not open it automatically:\n{exc}"
            )

"""
ui/sections/quick_analysis.py — Ephemeral ad-hoc launch-window analysis.

Same 12-month probability capability as the project Analysis tab, but for a
one-off site the user types in directly (lat/lon, bbox, vehicle, platform,
mode, year range, direction toggles). Nothing here is persisted: no sites
row, no analyses row, no site_vehicles upsert. Leaving the tab (hideEvent) or
clicking Clear wipes the form, table, charts, and basis panel — every run
starts from scratch.

Shares rendering with the project Analysis tab via ui/analysis_common.py and
ui/widgets/analysis_charts.py so results look identical to a saved run.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QDoubleSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QCheckBox, QRadioButton, QButtonGroup, QSpinBox, QScrollArea,
    QProgressBar, QFrame, QApplication, QMessageBox,
)
from PyQt6.QtCore import Qt

from ui.styles import apply_table_colors
from ui.widgets.coord_input import CoordInputWidget
from ui.widgets.analysis_charts import AnalysisChartsWidget
from ui.widgets.threshold_editor import ThresholdEditorWidget, threshold_editor_stylesheet
from ui import analysis_common as ac

_BTN_PRIMARY = (
    "QPushButton { background: #2563eb; color: white; border-radius: 4px;"
    " padding: 6px 20px; font-weight: bold; border: none; }"
    "QPushButton:hover { background: #1d4ed8; }"
    "QPushButton:disabled { background: #1e3a5f; color: #64748b; }"
)
_BTN_SECONDARY = (
    "QPushButton { background:#1e2d3d; color:#e2e8f0; border:1px solid #374151;"
    " border-radius:4px; padding:6px 16px; }"
    "QPushButton:hover { background:#2d3f55; }"
)
_INPUT_STYLE = (
    "QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox { background:#1a2233;"
    " color:#e2e8f0; border:1px solid #374151; border-radius:4px; padding:4px 8px; }"
    "QComboBox QAbstractItemView { background:#1a2233; color:#e2e8f0;"
    " selection-background-color:#2563eb; }"
)
_CB_STYLE = "QCheckBox, QRadioButton { color: #e2e8f0; font-size: 10px; }"
_LBL = "color:#94a3b8; font-size:10px;"


class QuickAnalysisSection(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._profile: dict = {}
        self._ncei_worker = None
        self._last_site = None
        self._last_operability_limits: tuple[float, float] = (25.0, 1.8)
        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
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
        root = QVBoxLayout(content)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        title = QLabel("Quick Analysis")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #f1f5f9;")
        root.addWidget(title)

        subtitle = QLabel(
            "Analyse an ad-hoc site without saving anything. Results and inputs "
            "are discarded when you leave this tab or restart the app."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#94a3b8; font-size:11px;")
        root.addWidget(subtitle)

        root.addWidget(self._build_site_form())

        # Direction + mode + year controls
        root.addLayout(self._build_option_rows())

        # Optimal-values (threshold) editor — pre-filled from the selected
        # vehicle; edits override the engine limits for this (unsaved) run.
        self.threshold_editor = ThresholdEditorWidget()
        self.threshold_editor.setStyleSheet(threshold_editor_stylesheet())
        self._refresh_threshold_defaults()
        root.addWidget(self.threshold_editor)

        # Fetch-status banner (live fetches are synchronous — see analysis_tab).
        self.fetch_status_widget = QWidget()
        fr = QHBoxLayout(self.fetch_status_widget)
        fr.setContentsMargins(0, 0, 0, 0)
        fr.setSpacing(8)
        self.fetch_progress = QProgressBar()
        self.fetch_progress.setRange(0, 0)
        self.fetch_progress.setFixedWidth(140)
        self.fetch_progress.setFixedHeight(12)
        self.fetch_progress.setTextVisible(False)
        self.fetch_progress.setStyleSheet(
            "QProgressBar { background:#1a2233; border:1px solid #374151;"
            " border-radius:4px; }"
            "QProgressBar::chunk { background:#2563eb; border-radius:4px; }"
        )
        fr.addWidget(self.fetch_progress)
        self.fetch_status_label = QLabel()
        self.fetch_status_label.setStyleSheet("color:#fde68a; font-size:10px; font-weight:600;")
        fr.addWidget(self.fetch_status_label)
        fr.addStretch()
        self.fetch_status_widget.setVisible(False)
        root.addWidget(self.fetch_status_widget)

        # Action buttons
        btn_row = QHBoxLayout()
        self.run_btn = QPushButton("Run 12-Month Profile")
        self.run_btn.setMinimumHeight(34)
        self.run_btn.setStyleSheet(_BTN_PRIMARY)
        self.run_btn.clicked.connect(self._run)
        btn_row.addWidget(self.run_btn)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setMinimumHeight(34)
        self.clear_btn.setStyleSheet(_BTN_SECONDARY)
        self.clear_btn.clicked.connect(self._clear_all)
        btn_row.addWidget(self.clear_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # Results table
        self.table = QTableWidget(12, 4)
        self.table.setHorizontalHeaderLabels(
            ["Month", "Probability", "Verdict", "Limiting Parameter"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setMinimumHeight(300)
        apply_table_colors(self.table)
        ac.clear_profile_table(self.table)
        root.addWidget(self.table)

        # Summary strip
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(
            "background:#1e3a5f; border:1px solid #2563eb; border-radius:4px;"
            " padding:10px; color:#e2e8f0;"
        )
        self.summary_label.setVisible(False)
        root.addWidget(self.summary_label)

        # Data source badges
        self.sources_label = QLabel()
        self.sources_label.setWordWrap(True)
        self.sources_label.setStyleSheet("color:#94a3b8; font-size:8pt;")
        self.sources_label.setVisible(False)
        root.addWidget(self.sources_label)

        # Charts
        charts_title = QLabel("Decision Charts")
        charts_title.setStyleSheet("color:#f1f5f9; font-size:11pt; font-weight:600;")
        root.addWidget(charts_title)
        self.charts = AnalysisChartsWidget()
        root.addWidget(self.charts)

        # Calculation basis panel — grows naturally (whole tab scrolls).
        basis_title = QLabel("Calculation Basis")
        basis_title.setStyleSheet("color:#f1f5f9; font-size:11pt; font-weight:600;")
        root.addWidget(basis_title)
        self.basis_panel = QLabel("No analysis run yet.")
        self.basis_panel.setWordWrap(True)
        self.basis_panel.setTextFormat(Qt.TextFormat.RichText)
        self.basis_panel.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.basis_panel.setStyleSheet(
            "QLabel { background:#2d3748; color:#64748b; font-size:11px;"
            " border:1px solid #374151; border-radius:6px; padding:12px 16px; }"
        )
        root.addWidget(self.basis_panel)

        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _build_site_form(self) -> QWidget:
        box = QFrame()
        box.setStyleSheet(
            "QFrame { background:#1a2233; border:1px solid #1e2d3d; border-radius:6px; }"
        )
        grid = QGridLayout(box)
        grid.setContentsMargins(16, 14, 16, 14)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)

        def lbl(t):
            l = QLabel(t)
            l.setStyleSheet(_LBL)
            return l

        grid.addWidget(lbl("Site name (optional)"), 0, 0)
        self.name_edit = QLineEdit()
        self.name_edit.setStyleSheet(_INPUT_STYLE)
        self.name_edit.setPlaceholderText("e.g. Ad-hoc point")
        grid.addWidget(self.name_edit, 1, 0)

        grid.addWidget(lbl("Bounding box radius"), 0, 1)
        self.bbox_spin = QDoubleSpinBox()
        self.bbox_spin.setRange(1.0, 500.0)
        self.bbox_spin.setDecimals(1)
        self.bbox_spin.setValue(25.0)
        self.bbox_spin.setSuffix(" NM")
        self.bbox_spin.setStyleSheet(_INPUT_STYLE)
        grid.addWidget(self.bbox_spin, 1, 1)

        grid.addWidget(lbl("Latitude  (+N / −S)"), 2, 0)
        self.lat_input = CoordInputWidget("lat")
        grid.addWidget(self.lat_input, 3, 0)

        grid.addWidget(lbl("Longitude  (+E / −W)"), 2, 1)
        self.lon_input = CoordInputWidget("lon")
        grid.addWidget(self.lon_input, 3, 1)

        grid.addWidget(lbl("Vehicle"), 4, 0)
        self.vehicle_combo = QComboBox()
        self.vehicle_combo.setStyleSheet(_INPUT_STYLE)
        for i, v in enumerate(self.mw.vehicles):
            self.vehicle_combo.addItem(v.name, i)
        grid.addWidget(self.vehicle_combo, 5, 0)

        grid.addWidget(lbl("Platform"), 4, 1)
        self.platform_combo = QComboBox()
        self.platform_combo.setStyleSheet(_INPUT_STYLE)
        for i, p in enumerate(self.mw.platforms):
            self.platform_combo.addItem(p.name, i)
        if len(self.mw.platforms) > 1:
            self.platform_combo.setCurrentIndex(1)  # Gateway X default
        grid.addWidget(self.platform_combo, 5, 1)

        return box

    def _build_option_rows(self) -> QVBoxLayout:
        wrap = QVBoxLayout()

        # Direction parameters
        dir_row = QHBoxLayout()
        dl = QLabel("Direction parameters:")
        dl.setStyleSheet(_LBL)
        dir_row.addWidget(dl)
        self.cb_wind_dir = QCheckBox("Wind direction")
        self.cb_sea_dir = QCheckBox("Sea direction")
        self.cb_swell_dir = QCheckBox("Swell direction")
        for cb in (self.cb_wind_dir, self.cb_sea_dir, self.cb_swell_dir):
            cb.setStyleSheet(_CB_STYLE)
            dir_row.addWidget(cb)
        dir_row.addStretch()
        wrap.addLayout(dir_row)

        # Mode + year range
        mode_row = QHBoxLayout()
        ml = QLabel("Mode:")
        ml.setStyleSheet(_LBL)
        mode_row.addWidget(ml)
        self._mode_group = QButtonGroup(self)
        self.rb_historical = QRadioButton("Historical")
        self.rb_45day = QRadioButton("45-Day (live)")
        self.rb_historical.setChecked(True)
        for rb in (self.rb_historical, self.rb_45day):
            rb.setStyleSheet(_CB_STYLE)
            self._mode_group.addButton(rb)
            mode_row.addWidget(rb)
        self.rb_historical.toggled.connect(self._on_mode_toggled)

        mode_row.addSpacing(16)
        yl = QLabel("Year range:")
        yl.setStyleSheet(_LBL)
        mode_row.addWidget(yl)
        self.year_start_spin = QSpinBox()
        self.year_start_spin.setValue(1960)
        self.year_start_spin.setStyleSheet(_INPUT_STYLE)
        mode_row.addWidget(self.year_start_spin)
        dash = QLabel("–")
        dash.setStyleSheet(_LBL)
        mode_row.addWidget(dash)
        self.year_end_spin = QSpinBox()
        from datetime import date as _date
        self.year_end_spin.setValue(min(_date.today().year, 2024))
        self.year_end_spin.setStyleSheet(_INPUT_STYLE)
        mode_row.addWidget(self.year_end_spin)
        from config import refresh_analysis_year_spins
        refresh_analysis_year_spins(self.year_start_spin, self.year_end_spin)
        mode_row.addStretch()
        wrap.addLayout(mode_row)

        return wrap

    def _on_mode_toggled(self, checked: bool) -> None:
        self.year_start_spin.setEnabled(checked)
        self.year_end_spin.setEnabled(checked)

    def _refresh_threshold_defaults(self) -> None:
        """Fill the optimal-values editor from the system defaults (independent
        of the selected vehicle — the vehicle no longer influences analysis)."""
        from config import DEFAULT_THRESHOLDS
        self.threshold_editor.set_defaults(DEFAULT_THRESHOLDS)

    # ── Fetch banner ──────────────────────────────────────────────────────────

    def _set_fetch_status(self, msg: str | None) -> None:
        if msg is None:
            self.fetch_status_widget.setVisible(False)
            self.run_btn.setEnabled(True)
            return
        self.fetch_status_label.setText(msg)
        self.fetch_status_widget.setVisible(True)
        self.run_btn.setEnabled(False)
        self.mw.status(msg)
        QApplication.processEvents()

    # ── Ephemeral behaviour ─────────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        from config import refresh_analysis_year_spins
        refresh_analysis_year_spins(self.year_start_spin, self.year_end_spin)

    def hideEvent(self, event) -> None:
        """Wipe everything when the user navigates away — nothing persists."""
        super().hideEvent(event)
        self._clear_all()

    def _clear_all(self) -> None:
        self._profile = {}
        self.name_edit.clear()
        self.bbox_spin.setValue(25.0)
        self.lat_input._input.clear()
        self.lon_input._input.clear()
        self.vehicle_combo.setCurrentIndex(0)
        if len(self.mw.platforms) > 1:
            self.platform_combo.setCurrentIndex(1)
        else:
            self.platform_combo.setCurrentIndex(0)
        self.cb_wind_dir.setChecked(False)
        self.cb_sea_dir.setChecked(False)
        self.cb_swell_dir.setChecked(False)
        self.rb_historical.setChecked(True)
        self.year_start_spin.setValue(1960)
        self.year_end_spin.setValue(2024)
        self._refresh_threshold_defaults()
        ac.clear_profile_table(self.table)
        self.summary_label.setVisible(False)
        self.sources_label.setVisible(False)
        self.basis_panel.setText("No analysis run yet.")
        self.charts.set_profile({})
        self._cancel_ncei_worker()

    def _cancel_ncei_worker(self) -> None:
        if self._ncei_worker is not None and self._ncei_worker.isRunning():
            self._ncei_worker.cancel()
            self._ncei_worker.wait(3000)
        self._ncei_worker = None

    def _start_ncei_fetch_if_needed(self, site) -> None:
        from core.utils import ncei_bbox_str
        from modules.m2_weather.ncei_download import (
            NceiDownloadWorker,
            ncei_fetch_incomplete,
            operability_year_range,
        )

        ys, ye = operability_year_range()
        bbox = ncei_bbox_str(site.lat, site.lon, site.bbox_nm)
        if not ncei_fetch_incomplete(bbox, ys, ye):
            return
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
        site = self._last_site
        if site is None or not self._profile:
            return
        from modules.m2_weather.operability import build_operability_heatmaps_for_site

        wind_kts, hs_m = self._last_operability_limits
        try:
            operability = build_operability_heatmaps_for_site(site, wind_kts, hs_m)
            self.charts.set_operability(operability)
        except Exception:
            pass
        self.mw.status("NCEI operability cache update complete.")

    def _on_ncei_error(self, msg: str) -> None:
        self.mw.status(f"NCEI fetch error: {msg}")

    # ── Run ─────────────────────────────────────────────────────────────────────

    def _build_site(self):
        from core.models import Site
        from core.utils import generate_coord_code
        if not self.lat_input.is_valid() or not self.lon_input.is_valid():
            QMessageBox.warning(
                self, "Invalid Coordinates",
                "Enter a valid latitude and longitude before running."
            )
            return None
        try:
            site = Site(
                lat=self.lat_input.value(),
                lon=self.lon_input.value(),
                name=self.name_edit.text().strip(),
                bbox_nm=self.bbox_spin.value(),
            )
        except Exception as exc:
            QMessageBox.warning(self, "Validation Error", str(exc))
            return None
        try:
            site.coord_code = generate_coord_code(site.lat, site.lon)
        except Exception:
            pass
        return site

    def _run(self) -> None:
        site = self._build_site()
        if site is None:
            return

        self._cancel_ncei_worker()
        self._last_site = site

        vehicle = self.mw.vehicles[self.vehicle_combo.currentData()]
        platform = self.mw.platforms[self.platform_combo.currentData()]
        wind_kts = float(vehicle.max_wind_kts)
        hs_m = float(vehicle.max_hs_m)
        self._last_operability_limits = (wind_kts, hs_m)

        from modules.m3_probability.engine import compute_annual_profile
        weights = ac.active_weights(
            self.cb_wind_dir.isChecked(),
            self.cb_sea_dir.isChecked(),
            self.cb_swell_dir.isChecked(),
        )
        mode = "45day" if self.rb_45day.isChecked() else "historical"
        year_start = self.year_start_spin.value()
        year_end = self.year_end_spin.value()
        thresholds_override = self.threshold_editor.values()
        from modules.m2_weather.operability import criteria_params_from_weights
        criteria_params = criteria_params_from_weights(weights)
        chart_kw = dict(
            thresholds=thresholds_override,
            active_criteria=criteria_params,
            day_fractions=None,
            param_fractions=None,
        )
        observed_means = None
        operability = None
        operability_progress = None
        try:
            try:
                from modules.m2_weather.data_manager import get_site_weather_summary
                if mode == "45day":
                    self._set_fetch_status("Fetching live 45-day weather data…")
                    observed_means = get_site_weather_summary(site, mode="45day")
                else:
                    self._set_fetch_status("Fetching live NCEI/ERA5 historical data…")
                    observed_means = get_site_weather_summary(
                        site, mode="historical",
                        year_start=year_start, year_end=year_end,
                    )
            except Exception:
                observed_means = None

            self._set_fetch_status("Running 12-month analysis…")
            self._profile = compute_annual_profile(
                site, vehicle, platform,
                year_start=year_start, year_end=year_end,
                weights=weights, mode=mode, observed_means=observed_means,
                thresholds_override=thresholds_override,
            )

            day_frac = None
            param_frac = None
            if mode == "historical":
                try:
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
                        site,
                        year_start,
                        year_end,
                        thresholds=thresholds_override,
                        active_params=criteria_params,
                        supplemental_means_by_month=supplemental,
                    )
                    param_frac = monthly_per_param_criterion_fractions(
                        site,
                        year_start,
                        year_end,
                        thresholds=thresholds_override,
                        active_params=criteria_params,
                        supplemental_means_by_month=supplemental,
                    )
                    if day_frac:
                        apply_day_fraction_verdicts(
                            self._profile,
                            day_frac,
                            thresholds=thresholds_override,
                            active_params=criteria_params,
                        )
                except Exception:
                    day_frac = None
                    param_frac = None
            else:
                try:
                    from modules.m2_weather.operability import (
                        per_param_criterion_fractions_from_profile,
                    )
                    param_frac = per_param_criterion_fractions_from_profile(
                        self._profile,
                        thresholds=thresholds_override,
                        active_params=criteria_params,
                    )
                except Exception:
                    param_frac = None

            chart_kw["day_fractions"] = day_frac
            chart_kw["param_fractions"] = param_frac
        finally:
            self._set_fetch_status(None)

        try:
            from core.utils import ncei_bbox_str
            from modules.m2_weather.ncei_download import (
                initial_operability_progress,
                operability_year_range,
            )
            from modules.m2_weather.operability import build_operability_heatmaps_for_site

            ys, ye = operability_year_range()
            operability = build_operability_heatmaps_for_site(site, wind_kts, hs_m)
            bbox = ncei_bbox_str(site.lat, site.lon, site.bbox_nm)
            operability_progress = initial_operability_progress(bbox, ys, ye)
        except Exception:
            operability = None
            operability_progress = None

        ac.populate_profile_table(self.table, self._profile)
        self.summary_label.setText(ac.summary_html(self._profile))
        self.summary_label.setVisible(True)
        src = ac.sources_html(self._profile)
        if src:
            self.sources_label.setText(src)
            self.sources_label.setVisible(True)
        best = max(self._profile, key=lambda m: self._profile[m].overall_prob)
        self.basis_panel.setStyleSheet(
            "QLabel { background:#2d3748; border:1px solid #374151;"
            " border-radius:6px; padding:12px 16px; }"
        )
        self.basis_panel.setText(ac.basis_html(self._profile[best]))
        self.charts.set_profile(
            self._profile,
            operability=operability,
            operability_progress=operability_progress,
            **chart_kw,
        )
        self._start_ncei_fetch_if_needed(site)
        self.mw.status("Quick analysis complete (not saved).")

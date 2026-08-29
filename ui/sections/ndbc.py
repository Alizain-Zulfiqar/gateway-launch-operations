"""
ui/sections/ndbc.py — NDBC station browser with per-parameter NaN tracking,
multi-select, checkbox-based inclusion control, and aggregated statistics.
"""
from __future__ import annotations

import json
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QGroupBox, QMessageBox, QFrame, QComboBox, QCheckBox, QScrollArea,
    QGridLayout, QSizePolicy, QDoubleSpinBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor

from ui.styles import apply_table_colors


_BTN_PRIMARY = (
    "QPushButton { background: #2563eb; color: white; border-radius: 4px;"
    "padding: 8px 16px; font-weight: bold; border: none; }"
    "QPushButton:hover { background: #1d4ed8; }"
    "QPushButton:disabled { background: #1e3a5f; color: #64748b; }"
)
_BTN_SECONDARY = (
    "QPushButton { background: #1e2d3d; color: #e2e8f0; border: 1px solid #374151;"
    "border-radius: 4px; padding: 6px 12px; }"
    "QPushButton:hover { background: #2d3f55; }"
    "QPushButton:disabled { color: #4b5563; }"
)

_STATION_COLS = ["Station ID", "Dist (NM)", "Bearing", "Lat", "Lon",
                 "Wind", "Wave", "Swell"]
_AGG_COLS     = ["Parameter", "Weighted Mean", "Network Max", "Stations Used"]
_OBS_WINDOWS  = ["24 h", "48 h", "72 h", "7 d", "14 d", "30 d", "45 d"]
_OBS_HOURS    = [24,     48,     72,     168,   336,    720,    1080]

# Coverage thresholds
_GOOD_PCT     = 90.0   # nan_pct < 10  → ✓ green
_PARTIAL_PCT  = 50.0   # nan_pct 10-50 → ~ amber
# nan_pct >= 50 or no data → ✗ red

_SYM_GOOD     = ("✓", "#86efac")
_SYM_PARTIAL  = ("~", "#fde68a")
_SYM_BAD      = ("✗", "#fca5a5")
_SYM_UNKNOWN  = ("?", "#64748b")

# Matplotlib colour palette for comparison chart bars
_BAR_COLORS   = ["#3b82f6", "#22c55e", "#f59e0b", "#a855f7", "#06b6d4", "#ef4444"]


# ── Workers ────────────────────────────────────────────────────────────────────

class _DiscoverWorker(QThread):
    finished = pyqtSignal(list)
    error    = pyqtSignal(str)

    def __init__(self, lat: float, lon: float, radius_nm: float = 200.0):
        super().__init__()
        self._lat = lat; self._lon = lon; self._radius = radius_nm

    def run(self) -> None:
        try:
            from modules.m2_weather.ndbc import nearest_stations
            self.finished.emit(nearest_stations(self._lat, self._lon, self._radius))
        except Exception as exc:
            self.error.emit(str(exc))


class _FetchWorker(QThread):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(dict)
    error    = pyqtSignal(str)

    def __init__(self, station_ids: list, stations: list):
        super().__init__()
        self._ids      = station_ids
        self._stations = stations

    def run(self) -> None:
        try:
            from modules.m2_weather.ndbc import fetch_multiple_station_dataframes
            raw = fetch_multiple_station_dataframes(
                self._ids, progress_callback=self.progress.emit
            )
            dist_map = {s.station_id: getattr(s, "distance_nm", None)
                        for s in self._stations}
            for sid, d in raw.items():
                d["distance_nm"] = dist_map.get(sid)
            self.finished.emit(raw)
        except Exception as exc:
            self.error.emit(str(exc))


# ── Section ────────────────────────────────────────────────────────────────────

class NDCBSection(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._stations: list = []
        self._disc_worker:  Optional[_DiscoverWorker] = None
        self._fetch_worker: Optional[_FetchWorker]    = None
        # {station_id: {met_df, spec_df, distance_nm, fetch_error}}
        self._fetch_cache: dict = {}
        # {(station_id, period_days): per_param_stats}
        self._stats_cache: dict = {}
        # IDs from the last fetch run
        self._last_fetched_ids: list[str] = []
        # {(station_id, param_key): QCheckBox}
        self._cb_map: dict = {}
        # matplotlib figure (created lazily)
        self._fig = None
        self._canvas = None
        self._build()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_site_selector()
        site = self._selected_site()
        if site:
            self._map.set_center(site.lat, site.lon)
        if self._table.rowCount() > 0:
            self._restore_table_selection()

    def on_project_changed(self) -> None:
        self._refresh_site_selector()

    def _refresh_site_selector(self) -> None:
        from ui.widgets.project_site_selector import refresh_project_site_selector
        site = refresh_project_site_selector(
            self.mw, self._site_combo, self._site_name_lbl,
        )
        if site:
            lat_d = "N" if site.lat >= 0 else "S"
            lon_d = "E" if site.lon >= 0 else "W"
            self._site_lbl.setText(
                f"{abs(site.lat):.3f}°{lat_d}, {abs(site.lon):.3f}°{lon_d}"
            )
            self._discover_btn.setEnabled(True)
        else:
            self._site_lbl.setText("")
            self._discover_btn.setEnabled(False)

    def _on_site_combo_changed(self) -> None:
        site = self._selected_site()
        if site:
            self._map.set_center(site.lat, site.lon)
            lat_d = "N" if site.lat >= 0 else "S"
            lon_d = "E" if site.lon >= 0 else "W"
            self._site_lbl.setText(
                f"{abs(site.lat):.3f}°{lat_d}, {abs(site.lon):.3f}°{lon_d}"
            )

    def _selected_site(self):
        from ui.widgets.project_site_selector import selected_project_site
        return selected_project_site(self.mw, self._site_combo)

    # ── Layout ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left panel ─────────────────────────────────────────────────────────
        left = QWidget()
        left.setFixedWidth(300)
        left.setStyleSheet("background: #151c27; border-right: 1px solid #374151;")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(12, 16, 12, 16)
        lv.setSpacing(10)

        title = QLabel("NDBC Stations")
        title.setObjectName("sectionTitle")
        lv.addWidget(title)

        hint = QLabel(
            "Discover NDBC buoy stations near the selected project site.\n"
            "Select multiple stations (Ctrl/Shift) for aggregated statistics.\n"
            "Wind/Wave/Swell symbols show data availability for the chosen window."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #94a3b8; font-size: 8pt;")
        lv.addWidget(hint)

        site_row = QHBoxLayout()
        site_row.addWidget(QLabel("Site:"))
        self._site_name_lbl = QLabel("No project site")
        self._site_name_lbl.setStyleSheet("color: #64748b; font-size: 8pt;")
        self._site_combo = QComboBox()
        self._site_combo.setStyleSheet(
            "QComboBox { background: #1a2233; color: #e2e8f0; border: 1px solid #374151;"
            " border-radius: 3px; padding: 2px 6px; }"
            "QComboBox QAbstractItemView { background: #1a2233; color: #e2e8f0; }"
        )
        self._site_combo.setVisible(False)
        site_row.addWidget(self._site_name_lbl, 1)
        site_row.addWidget(self._site_combo, 1)
        lv.addLayout(site_row)

        from ui.widgets.project_site_selector import (
            wire_project_site_combo, refresh_project_site_selector,
        )
        wire_project_site_combo(self.mw, self._site_combo, self._on_site_combo_changed)

        self._site_lbl = QLabel("")
        self._site_lbl.setStyleSheet("color: #64748b; font-size: 8pt;")
        lv.addWidget(self._site_lbl)

        # Search radius (Set 36, item 24) — moved here from Settings > Data
        # Sources so it lives where it's actually used. Persists to the same
        # ndbc_radius_nm setting; station discovery now reads this live
        # value instead of always using the 200.0 NM class default
        # (item 23's real root cause — the setting was never read at all).
        radius_row = QHBoxLayout()
        radius_row.addWidget(QLabel("Search radius:"))
        from core.settings import get_float
        try:
            _radius = get_float("ndbc_radius_nm", 200.0)
        except Exception:
            _radius = 200.0
        self._radius_spin = QDoubleSpinBox()
        self._radius_spin.setRange(10.0, 1000.0)
        self._radius_spin.setDecimals(0)
        self._radius_spin.setSuffix(" NM")
        self._radius_spin.setValue(_radius)
        self._radius_spin.valueChanged.connect(self._on_radius_changed)
        radius_row.addWidget(self._radius_spin)
        radius_row.addStretch()
        lv.addLayout(radius_row)

        self._discover_btn = QPushButton("Discover Stations")
        self._discover_btn.setStyleSheet(_BTN_PRIMARY)
        self._discover_btn.clicked.connect(self._on_discover)
        lv.addWidget(self._discover_btn)

        self._disc_status = QLabel("")
        self._disc_status.setWordWrap(True)
        self._disc_status.setStyleSheet("color: #94a3b8; font-size: 8pt;")
        lv.addWidget(self._disc_status)

        # Observation window
        ow_row = QHBoxLayout()
        ow_row.addWidget(QLabel("Window:"))
        self._obs_combo = QComboBox()
        for lbl in _OBS_WINDOWS:
            self._obs_combo.addItem(lbl)
        self._obs_combo.setCurrentIndex(2)  # 72h default
        self._obs_combo.setStyleSheet(
            "QComboBox { background: #1a2233; color: #e2e8f0; border: 1px solid #374151;"
            " border-radius: 3px; padding: 2px 6px; }"
            "QComboBox QAbstractItemView { background: #1a2233; color: #e2e8f0; }"
        )
        self._obs_combo.currentIndexChanged.connect(self._on_obs_changed)
        ow_row.addWidget(self._obs_combo)
        lv.addLayout(ow_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #374151;")
        lv.addWidget(sep)

        # Selection summary
        sel_row = QHBoxLayout()
        self._sel_lbl = QLabel("No stations selected")
        self._sel_lbl.setStyleSheet(
            "color: #94a3b8; font-size: 8pt; font-weight: bold;"
        )
        sel_row.addWidget(self._sel_lbl, 1)
        self._clear_sel_btn = QPushButton("Clear Selection")
        self._clear_sel_btn.setStyleSheet(_BTN_SECONDARY)
        self._clear_sel_btn.setEnabled(False)
        self._clear_sel_btn.clicked.connect(self._clear_station_selection)
        sel_row.addWidget(self._clear_sel_btn)
        lv.addLayout(sel_row)

        sel_hint = QLabel(
            "No selection → Forecast uses the nearest buoy automatically."
        )
        sel_hint.setWordWrap(True)
        sel_hint.setStyleSheet("color: #64748b; font-size: 7.5pt;")
        lv.addWidget(sel_hint)

        self._fetch_btn = QPushButton("Fetch Data for Selected")
        self._fetch_btn.setStyleSheet(_BTN_SECONDARY)
        self._fetch_btn.setEnabled(False)
        self._fetch_btn.clicked.connect(self._on_fetch)
        lv.addWidget(self._fetch_btn)

        self._fetch_status = QLabel("")
        self._fetch_status.setStyleSheet("color: #64748b; font-size: 7.5pt;")
        lv.addWidget(self._fetch_status)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("background: #374151;")
        lv.addWidget(sep2)

        # Single-station detail
        self._detail_group = QGroupBox("Selected Station")
        dv = QVBoxLayout(self._detail_group)
        self._detail_lbl = QLabel("Click a station or select from the table.")
        self._detail_lbl.setWordWrap(True)
        self._detail_lbl.setStyleSheet("color: #94a3b8; font-size: 8pt;")
        dv.addWidget(self._detail_lbl)
        lv.addWidget(self._detail_group)

        lv.addStretch()
        root.addWidget(left)

        # ── Right panel (scrollable) ────────────────────────────────────────────
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setStyleSheet(
            "QScrollArea { border: none; background: #0f1923; }"
        )

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)

        from ui.widgets.station_map import StationMapWidget
        self._map = StationMapWidget()
        self._map.setFixedHeight(280)
        self._map.station_selected.connect(self._on_station_selected)
        rv.addWidget(self._map)

        # Station discovery table
        self._table = QTableWidget(0, len(_STATION_COLS))
        self._table.setHorizontalHeaderLabels(_STATION_COLS)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setMaximumHeight(180)
        self._table.itemSelectionChanged.connect(self._on_table_selection)
        apply_table_colors(self._table)
        rv.addWidget(self._table)

        # Coverage & inclusion panel (hidden until data fetched)
        self._coverage_group = QGroupBox("Data Coverage & Inclusion Control")
        cg_lay = QVBoxLayout(self._coverage_group)
        cg_lay.setSpacing(8)

        self._cb_table = QTableWidget(0, 4)
        self._cb_table.setHorizontalHeaderLabels(
            ["Station", "Dist NM", "Wind  incl", "Wave  incl", "Swell  incl"]
        )
        self._cb_table.setHorizontalHeaderLabels(
            ["Station", "Dist", "Wind", "Wave", "Swell"]
        )
        self._cb_table.setColumnCount(5)
        self._cb_table.setHorizontalHeaderLabels(
            ["Station", "Dist NM", "Wind", "Wave", "Swell"]
        )
        self._cb_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._cb_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._cb_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._cb_table.setMaximumHeight(160)
        apply_table_colors(self._cb_table)
        cg_lay.addWidget(self._cb_table)

        self._contrib_lbl = QLabel("")
        self._contrib_lbl.setWordWrap(True)
        self._contrib_lbl.setStyleSheet("color: #94a3b8; font-size: 8pt;")
        cg_lay.addWidget(self._contrib_lbl)

        self._recalc_btn = QPushButton("Recalculate Average")
        self._recalc_btn.setStyleSheet(_BTN_PRIMARY)
        self._recalc_btn.setFixedWidth(180)
        self._recalc_btn.clicked.connect(self._on_recalculate)
        cg_lay.addWidget(self._recalc_btn)

        self._coverage_group.setVisible(False)
        rv.addWidget(self._coverage_group)

        # Aggregated statistics table
        agg_lbl = QLabel("Aggregated Statistics (inverse-distance weighted)")
        agg_lbl.setStyleSheet(
            "color: #94a3b8; font-size: 8pt; padding: 6px 8px 2px 8px;"
            " background: #0f1923;"
        )
        rv.addWidget(agg_lbl)

        self._agg_table = QTableWidget(0, len(_AGG_COLS))
        self._agg_table.setHorizontalHeaderLabels(_AGG_COLS)
        self._agg_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._agg_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._agg_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._agg_table.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        self._agg_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._agg_table.setMaximumHeight(180)
        apply_table_colors(self._agg_table)
        rv.addWidget(self._agg_table)

        # Comparison chart placeholder (built lazily)
        self._chart_container = QWidget()
        self._chart_container.setFixedHeight(260)
        self._chart_container.setStyleSheet("background: #0f1923;")
        self._chart_layout = QVBoxLayout(self._chart_container)
        self._chart_layout.setContentsMargins(0, 0, 0, 0)
        self._chart_container.setVisible(False)
        rv.addWidget(self._chart_container)

        rv.addStretch()
        right_scroll.setWidget(right)
        root.addWidget(right_scroll, 1)

    # ── Observation window ─────────────────────────────────────────────────────

    def _obs_period_days(self) -> int:
        idx = self._obs_combo.currentIndex()
        h = _OBS_HOURS[idx] if 0 <= idx < len(_OBS_HOURS) else 72
        return max(1, h // 24)

    def _on_obs_changed(self, _idx: int) -> None:
        """Recompute status symbols from cached data — no network request."""
        if not self._fetch_cache:
            return
        period_days = self._obs_period_days()
        self._update_station_symbols(period_days)
        if self._last_fetched_ids:
            self._rebuild_coverage_grid(period_days)
            self._update_contrib_summary()

    # ── Discovery ──────────────────────────────────────────────────────────────

    def _on_radius_changed(self, value: float) -> None:
        try:
            from core.settings import set_setting
            set_setting("ndbc_radius_nm", str(int(value)))
        except Exception:
            pass

    def _on_discover(self) -> None:
        site = self._selected_site()
        if not site:
            QMessageBox.warning(
                self, "No Site",
                "Open a project with at least one site, or select a site from the list.",
            )
            return
        radius = self._radius_spin.value()
        lat_d  = "N" if site.lat >= 0 else "S"
        lon_d  = "E" if site.lon >= 0 else "W"
        self._site_lbl.setText(
            f"{abs(site.lat):.3f}°{lat_d}, {abs(site.lon):.3f}°{lon_d}"
        )
        self._map.set_center(site.lat, site.lon)
        self._discover_btn.setEnabled(False)
        self._disc_status.setText(
            f"Fetching stations within {radius:.0f} NM from NDBC…"
        )

        self._disc_worker = _DiscoverWorker(site.lat, site.lon, radius)
        self._disc_worker.finished.connect(self._on_discovered)
        self._disc_worker.error.connect(self._on_error)
        self._disc_worker.start()

    def _on_discovered(self, stations: list) -> None:
        self._stations = stations
        self._discover_btn.setEnabled(True)
        self._disc_status.setText(
            f"{len(stations)} station{'s' if len(stations)!=1 else ''} found "
            f"within {self._radius_spin.value():.0f} NM."
        )
        self._map.set_stations(stations)
        self._populate_table(stations)
        self._restore_table_selection()

    def _restore_table_selection(self) -> None:
        """Re-highlight rows saved in session (empty list = no selection)."""
        try:
            from core.settings import get_session
            raw = get_session("selected_ndbc_stations")
            ids = json.loads(raw) if raw else []
        except Exception:
            ids = []

        if not ids:
            self._clear_station_selection()
            return

        id_set = set(ids)
        self._table.blockSignals(True)
        self._table.clearSelection()
        for ri in range(self._table.rowCount()):
            it = self._table.item(ri, 0)
            if it and it.text() in id_set:
                self._table.selectRow(ri)
        self._table.blockSignals(False)

        rows = {idx.row() for idx in self._table.selectedIndexes()}
        restored = [
            self._table.item(r, 0).text()
            for r in sorted(rows)
            if self._table.item(r, 0)
        ]
        self._apply_selection_state(restored)

    def _on_error(self, msg: str) -> None:
        self._discover_btn.setEnabled(True)
        self._fetch_btn.setEnabled(False)
        self._disc_status.setText(f"Error: {msg[:80]}")
        QMessageBox.critical(self, "NDBC Error", msg)

    # ── Station table ──────────────────────────────────────────────────────────

    def _populate_table(self, stations: list) -> None:
        self._table.setRowCount(0)
        self._table.setRowCount(len(stations))
        period_days = self._obs_period_days()

        for ri, stn in enumerate(stations):
            values = [
                stn.station_id,
                f"{getattr(stn,'distance_nm',0):.1f}",
                f"{getattr(stn,'bearing_deg',0):.0f}°",
                f"{stn.lat:.3f}",
                f"{stn.lon:.3f}",
            ]
            for ci, val in enumerate(values):
                item = QTableWidgetItem(str(val))
                item.setForeground(QColor("#f1f5f9"))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(ri, ci, item)

            # Wind/Wave/Swell status columns (5,6,7)
            for pi, param in enumerate(("wind", "wave", "swell")):
                sym, col, tip = self._symbol_for(
                    stn.station_id, param, period_days
                )
                it = QTableWidgetItem(sym)
                it.setForeground(QColor(col))
                it.setToolTip(tip)
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(ri, 5 + pi, it)

    def _update_station_symbols(self, period_days: int) -> None:
        """Refresh the Wind/Wave/Swell cells for all rows using cached data."""
        for row in range(self._table.rowCount()):
            sid_item = self._table.item(row, 0)
            if sid_item is None:
                continue
            sid = sid_item.text()
            for pi, param in enumerate(("wind", "wave", "swell")):
                sym, col, tip = self._symbol_for(sid, param, period_days)
                it = self._table.item(row, 5 + pi)
                if it is None:
                    it = QTableWidgetItem()
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self._table.setItem(row, 5 + pi, it)
                it.setText(sym)
                it.setForeground(QColor(col))
                it.setToolTip(tip)

    def _symbol_for(
        self, sid: str, param: str, period_days: int
    ) -> tuple[str, str, str]:
        """Return (symbol, color, tooltip) for a station+parameter combination."""
        cache = self._fetch_cache.get(sid)
        if cache is None:
            return _SYM_UNKNOWN[0], _SYM_UNKNOWN[1], "Click Fetch to check"

        if cache.get("fetch_error"):
            return _SYM_BAD[0], _SYM_BAD[1], f"Fetch error: {cache['fetch_error'][:60]}"

        stats = self._get_stats(sid, period_days, cache)
        param_key = {"wind": "wind_speed", "wave": "wave_height", "swell": "swell_height"}[param]
        ps = stats.get(param_key, {})

        has_data    = ps.get("has_data", False)
        nan_pct     = ps.get("nan_pct", 100.0)
        record_cnt  = ps.get("record_count", 0)
        expected    = ps.get("expected_count", period_days * 24)
        pname       = param.title()

        if not has_data:
            return (
                _SYM_BAD[0], _SYM_BAD[1],
                f"{pname}: No data available for last {period_days} day(s)",
            )
        if nan_pct >= 50.0:
            return (
                _SYM_BAD[0], _SYM_BAD[1],
                f"{pname}: {record_cnt}/{expected} records ({100-nan_pct:.1f}% coverage)",
            )
        if nan_pct >= 10.0:
            return (
                _SYM_PARTIAL[0], _SYM_PARTIAL[1],
                f"{pname}: {record_cnt}/{expected} records ({100-nan_pct:.1f}% coverage)",
            )
        return (
            _SYM_GOOD[0], _SYM_GOOD[1],
            f"{pname}: {record_cnt}/{expected} records ({100-nan_pct:.1f}% coverage)",
        )

    def _get_stats(self, sid: str, period_days: int, cache: dict) -> dict:
        """Return per-parameter stats for sid/period, computing and caching if needed."""
        key = (sid, period_days)
        if key not in self._stats_cache:
            from modules.m2_weather.ndbc_history import (
                compute_period_statistics, _merge_met_spec
            )
            merged = _merge_met_spec(cache.get("met_df"), cache.get("spec_df"))
            self._stats_cache[key] = (
                compute_period_statistics(merged, period_days)
                if not merged.empty else {}
            )
        return self._stats_cache[key]

    # ── Table selection ────────────────────────────────────────────────────────

    def _on_station_selected(self, station_id: str) -> None:
        for ri in range(self._table.rowCount()):
            it = self._table.item(ri, 0)
            if it and it.text() == station_id:
                self._table.selectRow(ri)
                self._table.scrollToItem(it)
                break
        self._update_detail(station_id)

    def _clear_station_selection(self) -> None:
        """Deselect all table rows and clear the session NDBC station list."""
        self._table.blockSignals(True)
        self._table.clearSelection()
        self._table.blockSignals(False)
        self._apply_selection_state([])

    def _apply_selection_state(self, ids: list[str]) -> None:
        """Update UI + session for the current station ID list (may be empty)."""
        n = len(ids)
        if n == 0:
            self._sel_lbl.setText("No stations selected")
            self._sel_lbl.setStyleSheet(
                "color: #94a3b8; font-size: 8pt; font-weight: bold;"
            )
        else:
            self._sel_lbl.setText(f"{n} station{'s' if n != 1 else ''} selected")
            self._sel_lbl.setStyleSheet(
                "color: #f59e0b; font-size: 8pt; font-weight: bold;"
            )

        self._fetch_btn.setEnabled(n > 0)
        self._clear_sel_btn.setEnabled(n > 0)

        try:
            from core.settings import set_session
            set_session("selected_ndbc_stations", json.dumps(ids))
        except Exception:
            pass

        if n == 1:
            self._map.selected_station_id = ids[0]
            if hasattr(self._map, "_redraw"):
                self._map._redraw()
            self._update_detail(ids[0])
        elif n > 1:
            self._map.selected_station_id = ids[0]
            if hasattr(self._map, "_redraw"):
                self._map._redraw()
            self._detail_lbl.setText(
                f"<span style='color:#f1f5f9;'>{n} stations selected.</span><br>"
                "<span style='color:#94a3b8;'>Click 'Fetch Data' to load observations.</span>"
            )
        else:
            self._map.selected_station_id = None
            if hasattr(self._map, "_redraw"):
                self._map._redraw()
            self._detail_lbl.setText(
                "<span style='color:#94a3b8;'>No stations selected.</span><br>"
                "Forecast will auto-select the nearest buoy, or pick rows here "
                "and click Fetch."
            )

    def _on_table_selection(self) -> None:
        rows = {idx.row() for idx in self._table.selectedIndexes()}
        ids = [
            self._table.item(r, 0).text()
            for r in sorted(rows)
            if self._table.item(r, 0)
        ]
        self._apply_selection_state(ids)

    def _update_detail(self, station_id: str) -> None:
        stn = next((s for s in self._stations if s.station_id == station_id), None)
        if stn is None:
            return
        lat_d = "N" if stn.lat >= 0 else "S"
        lon_d = "E" if stn.lon >= 0 else "W"

        period_days = self._obs_period_days()
        lines = [
            f"<b style='color:#f1f5f9;'>{station_id}</b>",
            f"<span style='color:#94a3b8;'>"
            f"{abs(stn.lat):.3f}°{lat_d}, {abs(stn.lon):.3f}°{lon_d}<br>"
            f"Distance: {getattr(stn,'distance_nm',0):.1f} NM</span>",
        ]
        cache = self._fetch_cache.get(station_id)
        if cache and not cache.get("fetch_error"):
            stats = self._get_stats(station_id, period_days, cache)
            for param, pk, unit in [
                ("Wind",  "wind_speed",   "kts"),
                ("Wave",  "wave_height",  "m"),
                ("Swell", "swell_height", "m"),
            ]:
                ps   = stats.get(pk, {})
                sym, col, _ = self._symbol_for(station_id, param.lower(), period_days)
                mean = ps.get(f"mean_{unit}")
                val  = f"{mean:.2f} {unit}" if mean is not None else "—"
                lines.append(
                    f"<span style='color:{col};'>{sym}</span>"
                    f"<span style='color:#94a3b8;'> {param}: {val}</span>"
                )
        self._detail_lbl.setText("<br>".join(lines))

    # ── Fetch ──────────────────────────────────────────────────────────────────

    def _on_fetch(self) -> None:
        rows = {idx.row() for idx in self._table.selectedIndexes()}
        ids  = [
            self._table.item(r, 0).text()
            for r in rows
            if self._table.item(r, 0)
        ]
        if not ids:
            return
        self._fetch_btn.setEnabled(False)
        self._fetch_status.setText(f"Fetching 0/{len(ids)}…")
        self._fetch_worker = _FetchWorker(ids, self._stations)
        self._fetch_worker.progress.connect(self._on_fetch_progress)
        self._fetch_worker.finished.connect(self._on_fetch_done)
        self._fetch_worker.error.connect(self._on_error)
        self._fetch_worker.start()

    def _on_fetch_progress(self, done: int, total: int) -> None:
        self._fetch_status.setText(f"Fetching {done}/{total}…")

    def _on_fetch_done(self, raw: dict) -> None:
        self._fetch_cache.update(raw)
        self._stats_cache.clear()  # invalidate computed stats
        self._last_fetched_ids = list(raw.keys())

        self._fetch_btn.setEnabled(True)
        ok  = sum(1 for d in raw.values() if not d.get("fetch_error"))
        err = len(raw) - ok
        msg = f"Fetched {ok} station{'s' if ok!=1 else ''}"
        if err:
            msg += f", {err} error{'s' if err!=1 else ''}"
        self._fetch_status.setText(msg + ".")

        period_days = self._obs_period_days()
        self._update_station_symbols(period_days)

        self._rebuild_coverage_grid(period_days)
        self._coverage_group.setVisible(True)
        self._update_contrib_summary()

        # Initial aggregation with all stations
        self._run_aggregation()

    # ── Coverage / checkbox grid ───────────────────────────────────────────────

    def _rebuild_coverage_grid(self, period_days: int) -> None:
        self._cb_map.clear()
        self._cb_table.clearContents()
        ids = self._last_fetched_ids
        self._cb_table.setRowCount(len(ids))

        for ri, sid in enumerate(ids):
            cache = self._fetch_cache.get(sid, {})
            dist  = cache.get("distance_nm") or 0.0

            # Station ID cell
            sid_item = QTableWidgetItem(sid)
            sid_item.setForeground(QColor("#f1f5f9"))
            sid_item.setFlags(sid_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._cb_table.setItem(ri, 0, sid_item)

            # Distance cell
            d_item = QTableWidgetItem(f"{dist:.0f}")
            d_item.setForeground(QColor("#94a3b8"))
            d_item.setFlags(d_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._cb_table.setItem(ri, 1, d_item)

            # Wind / Wave / Swell checkbox cells (columns 2, 3, 4)
            for ci, (param, pk) in enumerate([
                ("wind",  "wind_speed"),
                ("wave",  "wave_height"),
                ("swell", "swell_height"),
            ]):
                sym, col, tip = self._symbol_for(sid, param, period_days)
                stats = self._get_stats(sid, period_days, cache)
                has_data = stats.get(pk, {}).get("has_data", False)
                nan_pct  = stats.get(pk, {}).get("nan_pct", 100.0)

                cell = QWidget()
                cell_lay = QHBoxLayout(cell)
                cell_lay.setContentsMargins(4, 0, 4, 0)
                cell_lay.setSpacing(6)

                sym_lbl = QLabel(sym)
                sym_lbl.setStyleSheet(f"color: {col}; font-size: 11pt;")
                sym_lbl.setToolTip(tip)
                cell_lay.addWidget(sym_lbl)

                cb = QCheckBox()
                cb.setToolTip(tip)
                if not has_data or nan_pct >= 50.0:
                    cb.setChecked(False)
                    cb.setEnabled(False)
                    cb.setToolTip(
                        f"Disabled — no usable {param} data for this station."
                    )
                else:
                    cb.setChecked(True)  # good or partial data → default included

                cb.stateChanged.connect(self._update_contrib_summary)
                self._cb_map[(sid, pk)] = cb
                cell_lay.addWidget(cb)
                cell_lay.addStretch()

                self._cb_table.setCellWidget(ri, 2 + ci, cell)

    def _update_contrib_summary(self) -> None:
        ids = self._last_fetched_ids
        total = len(ids)
        if total == 0:
            self._contrib_lbl.setText("")
            return

        parts = []
        for label, pk in [("wind", "wind_speed"), ("wave", "wave_height"),
                           ("swell", "swell_height")]:
            n = sum(
                1 for sid in ids
                if self._cb_map.get((sid, pk), _FalseCB()).isChecked()
            )
            parts.append(f"<b>{n}/{total}</b> stations → {label}")
        self._contrib_lbl.setText(
            "Contributing to average:  " + ",  ".join(parts)
        )

    def _on_recalculate(self) -> None:
        self._run_aggregation()

    def _run_aggregation(
        self,
        include_wind:  Optional[set] = None,
        include_wave:  Optional[set] = None,
        include_swell: Optional[set] = None,
    ) -> None:
        """Compute aggregation using checked stations and update the UI."""
        ids = self._last_fetched_ids
        if not ids:
            return

        # Collect inclusion sets from checkboxes
        def _incl(pk: str) -> Optional[set]:
            checked = {
                sid for sid in ids
                if self._cb_map.get((sid, pk), _FalseCB()).isChecked()
            }
            return checked if checked else None

        inc_wind  = _incl("wind_speed")
        inc_wave  = _incl("wave_height")
        inc_swell = _incl("swell_height")

        # Build station_data for aggregation
        station_data = {}
        for sid in ids:
            cache = self._fetch_cache.get(sid, {})
            if not cache.get("fetch_error"):
                station_data[sid] = {
                    "distance_nm": cache.get("distance_nm"),
                    "met_df":      cache.get("met_df"),
                    "spec_df":     cache.get("spec_df"),
                    "fetch_error": None,
                }

        if not station_data:
            return

        try:
            from modules.m2_weather.ndbc_history import aggregate_station_statistics
            period_days = self._obs_period_days()
            agg = aggregate_station_statistics(
                station_data,
                forecast_hours=period_days * 24,
                include_for_wind=inc_wind,
                include_for_wave=inc_wave,
                include_for_swell=inc_swell,
            )
            self._populate_agg_table(agg, len(ids))
            self._update_chart(agg, station_data, period_days)
        except Exception as exc:
            self._fetch_status.setText(f"Aggregation error: {str(exc)[:80]}")

    # ── Aggregated stats table ─────────────────────────────────────────────────

    def _populate_agg_table(self, agg: dict, total_stations: int) -> None:
        rows_data = [
            ("Wind speed",        "wind_speed",   "weighted_mean_kts", "kts"),
            ("Wind gust",         "wind_gust",    "weighted_mean_kts", "kts"),
            ("Wave height (Hs)",  "wave_height",  "weighted_mean_m",   "m"),
            ("Swell height",      "swell_height", "weighted_mean_m",   "m"),
            ("Swell period",      "swell_period", "weighted_mean_s",   "s"),
        ]

        self._agg_table.setRowCount(len(rows_data))
        for ri, (label, pk, mean_key, unit) in enumerate(rows_data):
            group = agg.get(pk, {})
            mean  = group.get(mean_key)
            nmax  = group.get(f"network_max_{unit}")
            n_con = len(group.get("contributing_stations", []))
            n_tot = total_stations
            msg   = group.get("message", "")

            # Parameter name
            name_it = QTableWidgetItem(label)
            name_it.setForeground(QColor("#f1f5f9"))
            name_it.setFlags(name_it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._agg_table.setItem(ri, 0, name_it)

            # Weighted mean
            if mean is not None:
                mean_txt = f"{mean:.2f} {unit}"
                mean_col = "#f1f5f9"
                self._agg_table.setItem(ri, 1, _agg_item(mean_txt, mean_col))
            else:
                mean_it = QTableWidgetItem("N/A ⚠")
                mean_it.setForeground(QColor("#fca5a5"))
                mean_it.setBackground(QColor("#450a0a"))
                mean_it.setFlags(mean_it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if msg:
                    mean_it.setToolTip(msg)
                self._agg_table.setItem(ri, 1, mean_it)

            # Network max
            max_txt = f"{nmax:.2f} {unit}" if nmax is not None else "—"
            self._agg_table.setItem(ri, 2, _agg_item(max_txt, "#94a3b8"))

            # Stations used
            if n_con == 0:
                used_it = QTableWidgetItem(f"0 of {n_tot} ⚠")
                used_it.setForeground(QColor("#fca5a5"))
                used_it.setBackground(QColor("#450a0a"))
            else:
                used_it = QTableWidgetItem(f"{n_con} of {n_tot}")
                used_it.setForeground(
                    QColor("#86efac") if n_con == n_tot else QColor("#fde68a")
                )
            used_it.setFlags(used_it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._agg_table.setItem(ri, 3, used_it)

    # ── Comparison chart ───────────────────────────────────────────────────────

    def _update_chart(
        self, agg: dict, station_data: dict, period_days: int
    ) -> None:
        """Build or refresh the per-station comparison bar chart."""
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
            import numpy as np
        except ImportError:
            return

        ids = list(station_data.keys())
        if not ids:
            return

        params = [
            ("wind_speed",   "wind_speed",   "mean_kts", "Wind Speed (kts)"),
            ("wave_height",  "wave_height",  "mean_m",   "Wave Ht (m)"),
            ("swell_height", "swell_height", "mean_m",   "Swell Ht (m)"),
        ]

        BG   = "#0f1923"
        GRID = "#1e2d3d"
        TEXT = "#94a3b8"

        if self._fig is not None:
            plt.close(self._fig)

        fig, axes = plt.subplots(1, 3, figsize=(9, 3))
        fig.patch.set_facecolor(BG)
        fig.subplots_adjust(left=0.06, right=0.98, top=0.85, bottom=0.18, wspace=0.35)

        n    = len(ids)
        bw   = 0.7 / max(n, 1)
        xpos = np.arange(1)

        for ax, (stat_pk, param_pk, mean_fld, ylabel) in zip(axes, params):
            ax.set_facecolor(BG)
            ax.tick_params(colors=TEXT)
            ax.xaxis.label.set_color(TEXT)
            ax.yaxis.label.set_color(TEXT)
            ax.set_ylabel(ylabel, fontsize=7, color=TEXT)
            ax.set_xticks([])
            for spine in ax.spines.values():
                spine.set_edgecolor(GRID)
            ax.yaxis.grid(True, color=GRID, linewidth=0.5)
            ax.set_axisbelow(True)

            for i, sid in enumerate(ids):
                color = _BAR_COLORS[i % len(_BAR_COLORS)]
                offset = (i - n / 2 + 0.5) * bw
                x = xpos + offset

                # Get per-station stat from cached stats
                cache = station_data.get(sid, {})
                s = self._get_stats(sid, period_days, cache)
                ps = s.get(stat_pk, {})
                has_data = ps.get("has_data", False)
                val      = ps.get(mean_fld)

                if has_data and val is not None:
                    ax.bar(
                        x, val, bw * 0.9,
                        color=color,
                        label=sid,
                        zorder=2,
                    )
                else:
                    # Hatched gray — no data
                    ax.bar(
                        x, 0.3, bw * 0.9,
                        color="#374151",
                        hatch="///",
                        edgecolor="#64748b",
                        linewidth=0.5,
                        label="_nolegend_",
                        zorder=2,
                    )
                    ax.annotate(
                        "✗", (float(x), 0.35),
                        ha="center", va="bottom",
                        color="#fca5a5", fontsize=9,
                    )
                    ax.text(
                        float(x), -0.05,
                        f"{sid[:6]}\nno data",
                        ha="center", va="top",
                        fontsize=5, color="#64748b",
                        transform=ax.get_xaxis_transform(),
                    )

        # Shared legend on the figure (top right)
        legend_handles = [
            matplotlib.patches.Patch(facecolor=_BAR_COLORS[i % len(_BAR_COLORS)],
                                      label=sid)
            for i, sid in enumerate(ids)
        ]
        legend_handles.append(
            matplotlib.patches.Patch(
                facecolor="#374151", hatch="///", edgecolor="#64748b",
                label="No data"
            )
        )
        fig.legend(
            handles=legend_handles,
            loc="upper right",
            fontsize=6,
            facecolor="#1a2233",
            edgecolor="#374151",
            labelcolor=TEXT,
            ncol=min(n + 1, 4),
        )

        # Embed canvas
        while self._chart_layout.count():
            item = self._chart_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._fig    = fig
        self._canvas = FigureCanvasQTAgg(fig)
        self._chart_layout.addWidget(self._canvas)
        self._chart_container.setVisible(True)
        self._canvas.draw()


# ── Utilities ──────────────────────────────────────────────────────────────────

def _agg_item(text: str, color: str) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setForeground(QColor(color))
    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return it


class _FalseCB:
    """Sentinel checkbox that is always unchecked — used when key absent from _cb_map."""
    def isChecked(self) -> bool:
        return False

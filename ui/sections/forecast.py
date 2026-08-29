"""
ui/sections/forecast.py — Hybrid forecast: NDBC past observations + site model forecast.
"""
from __future__ import annotations

import json

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QGroupBox, QFrame, QButtonGroup, QRadioButton,
    QGridLayout, QMessageBox, QScrollArea,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor


_BTN_PRIMARY = (
    "QPushButton { background: #2563eb; color: white; border-radius: 4px;"
    "padding: 8px 20px; font-weight: bold; border: none; }"
    "QPushButton:hover { background: #1d4ed8; }"
    "QPushButton:disabled { background: #1e3a5f; color: #64748b; }"
)
_BTN_SECONDARY = (
    "QPushButton { background: #1e2d3d; color: #e2e8f0; border: 1px solid #374151;"
    "border-radius: 4px; padding: 6px 14px; }"
    "QPushButton:hover { background: #2d3f55; }"
)

_HORIZONS     = [24, 48, 72, 120, 168]
_HOR_LABELS   = ["24 h", "48 h", "72 h", "5 day", "7 day"]
_CONFIDENCE   = {24: 5, 48: 4, 72: 4, 120: 3, 168: 2}

# GO / MARGINAL / NO-GO badge colours (bg, fg)
_BADGE = {
    "GO":       ("#14532d", "#86efac"),
    "MARGINAL": ("#422006", "#fde68a"),
    "NO-GO":    ("#450a0a", "#fca5a5"),
    "—":        ("#1a2233", "#64748b"),
}

_DOT_ACTIVE   = "#2563eb"
_DOT_INACTIVE = "#374151"


# ── Worker ─────────────────────────────────────────────────────────────────────

class _ForecastWorker(QThread):
    finished = pyqtSignal(dict)
    error    = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(
        self,
        station_ids: list,
        stations: list,
        horizon: int,
        site_lat: float = None,
        site_lon: float = None,
        vehicle=None,
        use_single: bool = False,
    ):
        super().__init__()
        self._ids = station_ids
        self._stations = stations
        self._horizon = horizon
        self._lat = site_lat
        self._lon = site_lon
        self._vehicle = vehicle
        self._use_single = use_single

    def run(self) -> None:
        try:
            from core.settings import get_float
            from modules.m2_weather.ndbc import (
                nearest_stations, fetch_multiple_station_dataframes,
            )
            from modules.m2_weather.ndbc_history import analyze_hourly_go_window
            from modules.m2_weather.forecast import (
                fetch_combined_forecast, compute_forecast_analysis,
            )

            result: dict = {
                "observed": {},
                "forecast_24h": {},
                "_station_data": None,
                "_model_combined": None,
                "_ndbc_station_count": 0,
                "_nws_available": False,
                "_openmeteo_available": False,
                "_openmeteo_weather_available": False,
                "_wind_source": None,
                "_obs_source_label": "",
                "_auto_buoy": False,
            }

            ids = list(self._ids)
            stations = list(self._stations)
            include_ids = None

            if not ids and self._lat is not None and self._lon is not None:
                try:
                    radius = float(get_float("ndbc_radius_nm", 200.0))
                except Exception:
                    radius = 200.0
                nearest = nearest_stations(self._lat, self._lon, radius, met_only=True)
                if nearest:
                    pick = nearest[0]
                    ids = [pick.station_id]
                    stations = [pick]
                    result["_auto_buoy"] = True
                    result["_obs_source_label"] = (
                        f"Nearest buoy {pick.station_id} "
                        f"({getattr(pick, 'distance_nm', 0):.0f} NM from site)"
                    )

            if self._use_single and ids:
                include_ids = {ids[0]}
                ids = [ids[0]]
                stations = [s for s in stations if s.station_id == ids[0]] or stations[:1]
                if stations:
                    st = stations[0]
                    result["_obs_source_label"] = (
                        f"Buoy {st.station_id} "
                        f"({getattr(st, 'distance_nm', 0):.0f} NM from site)"
                    )
            elif ids and not result["_obs_source_label"]:
                result["_obs_source_label"] = (
                    f"{len(ids)} buoy{'s' if len(ids) != 1 else ''} (distance-weighted blend)"
                )

            station_data: dict = {}
            if ids:
                self.progress.emit("Fetching NDBC hourly observations…")
                raw = fetch_multiple_station_dataframes(ids)
                dist_map = {
                    s.station_id: (getattr(s, "distance_nm", 1.0) or 1.0)
                    for s in stations
                }
                for sid, d in raw.items():
                    if not d.get("fetch_error"):
                        d["distance_nm"] = dist_map.get(sid, 1.0)
                        station_data[sid] = d

                if station_data:
                    self.progress.emit("Analysing observed GO windows…")
                    result["observed"] = analyze_hourly_go_window(
                        station_data,
                        horizon_hours=self._horizon,
                        vehicle=self._vehicle,
                        include_ids=include_ids,
                    )
                    result["observed"]["source_label"] = result["_obs_source_label"]
                    result["_station_data"] = station_data
                    result["_ndbc_station_count"] = len(station_data)

            if self._lat is not None and self._lon is not None:
                self.progress.emit("Fetching 24 h site forecast (NWS + Open-Meteo)…")
                try:
                    model_combined = fetch_combined_forecast(
                        self._lat, self._lon, forecast_days=2,
                    )
                    result["_model_combined"] = model_combined
                    result["_nws_available"] = model_combined.get("nws_available", False)
                    result["_openmeteo_available"] = model_combined.get(
                        "openmeteo_available", False
                    )
                    result["_openmeteo_weather_available"] = model_combined.get(
                        "openmeteo_weather_available", False
                    )
                    result["_wind_source"] = model_combined.get("wind_source")
                    merged = model_combined.get("merged")
                    if merged is not None and len(merged):
                        result["forecast_24h"] = compute_forecast_analysis(
                            model_combined,
                            vehicle=self._vehicle,
                            horizon_hours=24,
                        )
                        lat_d = "N" if self._lat >= 0 else "S"
                        lon_d = "E" if self._lon >= 0 else "W"
                        ws = result["_wind_source"] or "none"
                        result["forecast_24h"]["source_label"] = (
                            f"Site {abs(self._lat):.3f}°{lat_d}, "
                            f"{abs(self._lon):.3f}°{lon_d} · wind: {ws}"
                        )
                except Exception as exc:
                    self.progress.emit(f"Site forecast unavailable: {exc}")

            if not result["observed"] and not result["forecast_24h"]:
                self.error.emit(
                    "No data available. Ensure the site is valid and a nearby NDBC "
                    "buoy exists, or check network access for Open-Meteo/NWS."
                )
                return

            self.finished.emit(result)
        except Exception as exc:
            import traceback
            self.error.emit(f"{exc}\n{traceback.format_exc()}")


# ── Dot confidence indicator ────────────────────────────────────────────────────

class _ConfidenceDots(QWidget):
    def __init__(self, total: int = 5, active: int = 0, parent=None):
        super().__init__(parent)
        self._total  = total
        self._active = active
        self._build()

    def _build(self) -> None:
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self._dots: list[QLabel] = []
        for _ in range(self._total):
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {_DOT_INACTIVE}; font-size: 10pt;")
            lay.addWidget(dot)
            self._dots.append(dot)
        self._refresh()

    def set_active(self, active: int) -> None:
        self._active = active
        self._refresh()

    def _refresh(self) -> None:
        for i, dot in enumerate(self._dots):
            colour = _DOT_ACTIVE if i < self._active else _DOT_INACTIVE
            dot.setStyleSheet(f"color: {colour}; font-size: 10pt;")


# ── Status card ────────────────────────────────────────────────────────────────

def _status_card(param: str, value: str, status: str, threshold: str = "") -> QGroupBox:
    bg, fg = _BADGE.get(status, _BADGE["—"])
    box = QGroupBox(param)
    box.setStyleSheet(
        f"QGroupBox {{ background: {bg}; border: 1px solid #374151; border-radius: 6px;"
        f" padding: 8px; }}"
        f"QGroupBox::title {{ color: #94a3b8; font-size: 8pt; }}"
    )
    lay = QVBoxLayout(box)
    lay.setSpacing(4)
    val_lbl = QLabel(value)
    val_lbl.setStyleSheet(f"color: {fg}; font-size: 16pt; font-weight: bold;")
    val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(val_lbl)
    st_lbl = QLabel(status)
    st_lbl.setStyleSheet(f"color: {fg}; font-size: 9pt; font-weight: bold;")
    st_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(st_lbl)
    if threshold:
        # Set 36, item 25: show the threshold the value was compared against
        # — previously only the raw model value + status were shown, with no
        # indication of what limit produced that GO/MARGINAL/NO-GO call.
        thr_lbl = QLabel(threshold)
        thr_lbl.setStyleSheet(f"color: {fg}; font-size: 7.5pt; font-style: italic;")
        thr_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(thr_lbl)
    return box


# ── Section ────────────────────────────────────────────────────────────────────

class ForecastSection(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._stations: list = []
        self._worker: _ForecastWorker | None = None
        # Cached data for horizon re-analysis without refetch.
        self._last_station_data = None
        self._last_model_combined = None
        self._last_horizon = 72
        self._last_observed: dict = {}
        self._last_forecast_24h: dict = {}
        self._last_use_single = False
        self._active_vehicle = None
        self._build()

    # ── Layout ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #0f1923; }")

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # Title
        title = QLabel("Forecast Analysis")
        title.setObjectName("sectionTitle")
        root.addWidget(title)

        subtitle = QLabel(
            "Past: NDBC buoy observations over the selected look-back window. "
            "Forward: next 24 hours at the site from NWS (wind) + Open-Meteo Marine "
            "(wave/swell), checked against your vehicle limits."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #94a3b8;")
        root.addWidget(subtitle)

        site_row = QHBoxLayout()
        site_row.addWidget(QLabel("Site:"))
        self._site_name_lbl = QLabel("No project site")
        self._site_name_lbl.setStyleSheet("color: #64748b;")
        self._site_combo = QComboBox()
        self._site_combo.setMinimumWidth(280)
        self._site_combo.setStyleSheet(
            "QComboBox { background: #1a2233; color: #e2e8f0; border: 1px solid #374151;"
            " border-radius: 3px; padding: 2px 8px; }"
            "QComboBox QAbstractItemView { background: #1a2233; color: #e2e8f0; }"
        )
        self._site_combo.setVisible(False)
        site_row.addWidget(self._site_name_lbl, 1)
        site_row.addWidget(self._site_combo, 1)
        site_row.addStretch()
        root.addLayout(site_row)

        from ui.widgets.project_site_selector import wire_project_site_combo
        wire_project_site_combo(self.mw, self._site_combo, self._on_site_combo_changed)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #374151; max-height: 1px;")
        root.addWidget(sep)

        # ── Controls row ──────────────────────────────────────────────────────
        ctrl = QGroupBox("Past observations (NDBC buoys)")
        cv   = QVBoxLayout(ctrl)
        cv.setSpacing(10)

        # NDBC blend selection
        blend_row = QHBoxLayout()
        self._blend_all_rb  = QRadioButton("All selected NDBC stations (blend)")
        self._blend_one_rb  = QRadioButton("Single station:")
        self._blend_all_rb.setChecked(True)
        blend_row.addWidget(self._blend_all_rb)
        blend_row.addWidget(self._blend_one_rb)
        self._station_combo = QComboBox()
        self._station_combo.setEnabled(False)
        self._station_combo.setStyleSheet(
            "QComboBox { background: #1a2233; color: #e2e8f0; border: 1px solid #374151;"
            " border-radius: 3px; padding: 2px 8px; }"
            "QComboBox QAbstractItemView { background: #1a2233; color: #e2e8f0; }"
        )
        blend_row.addWidget(self._station_combo)
        blend_row.addStretch()
        cv.addLayout(blend_row)

        self._blend_group = QButtonGroup(self)
        self._blend_group.addButton(self._blend_all_rb, 0)
        self._blend_group.addButton(self._blend_one_rb, 1)
        self._blend_one_rb.toggled.connect(
            lambda checked: self._station_combo.setEnabled(checked)
        )

        # Horizon selector row
        hor_row = QHBoxLayout()
        hor_row.addWidget(QLabel("Look-back window:"))
        hor_row.setSpacing(6)

        self._hor_btns: list[QPushButton] = []
        self._hor_group = QButtonGroup(self)
        for i, (h, lbl) in enumerate(zip(_HORIZONS, _HOR_LABELS)):
            btn = QPushButton(lbl)
            btn.setCheckable(True)
            btn.setFixedWidth(68)
            btn.setStyleSheet(
                "QPushButton { background: #1a2233; color: #94a3b8; border: 1px solid #374151;"
                " border-radius: 4px; padding: 4px 6px; }"
                "QPushButton:checked { background: #1e3a8a; color: #93c5fd;"
                " border-color: #2563eb; font-weight: bold; }"
                "QPushButton:hover:!checked { background: #1e2d3d; }"
            )
            self._hor_group.addButton(btn, i)
            hor_row.addWidget(btn)
            self._hor_btns.append(btn)
        self._hor_btns[2].setChecked(True)  # 72h default

        hor_row.addStretch()
        cv.addLayout(hor_row)

        # Data availability indicator
        conf_row = QHBoxLayout()
        conf_row.addWidget(QLabel("Data quality:"))
        self._conf_dots = _ConfidenceDots(total=5, active=_CONFIDENCE[72])
        conf_row.addWidget(self._conf_dots)
        conf_row.addStretch()
        cv.addLayout(conf_row)
        self._hor_group.idToggled.connect(self._on_horizon_changed)

        run_row = QHBoxLayout()
        self._run_btn = QPushButton("Run Forecast Analysis")
        self._run_btn.setStyleSheet(_BTN_PRIMARY)
        self._run_btn.clicked.connect(self._on_run)
        run_row.addWidget(self._run_btn)

        self._clear_overlay_btn = QPushButton("Clear Buoy Overlay")
        self._clear_overlay_btn.setStyleSheet(_BTN_SECONDARY)
        self._clear_overlay_btn.clicked.connect(self._on_clear_overlay)
        run_row.addWidget(self._clear_overlay_btn)

        self._run_status = QLabel("")
        self._run_status.setStyleSheet("color: #94a3b8; font-size: 8pt;")
        run_row.addWidget(self._run_status)
        run_row.addStretch()
        cv.addLayout(run_row)

        root.addWidget(ctrl)

        # Station-selection transparency label (Step 11 Fix B).
        self._station_status_label = QLabel("")
        self._station_status_label.setWordWrap(True)
        self._station_status_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
        root.addWidget(self._station_status_label)

        # ── Past observations (NDBC) ───────────────────────────────────────────
        self._obs_box = QGroupBox("Recent Observations — NDBC Buoys")
        ov = QVBoxLayout(self._obs_box)
        self._obs_go_lbl = QLabel("—")
        self._obs_go_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._obs_go_lbl.setStyleSheet(
            "color: #86efac; font-size: 20pt; font-weight: bold; padding: 6px;"
        )
        ov.addWidget(self._obs_go_lbl)
        self._obs_go_sub = QLabel(
            "Select NDBC stations and run analysis to see past GO hours."
        )
        self._obs_go_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._obs_go_sub.setWordWrap(True)
        self._obs_go_sub.setStyleSheet("color: #64748b; font-size: 9pt;")
        self._obs_source_lbl = QLabel("")
        self._obs_source_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._obs_source_lbl.setWordWrap(True)
        self._obs_source_lbl.setStyleSheet("color: #94a3b8; font-size: 8pt;")
        ov.addWidget(self._obs_source_lbl)
        self._obs_cards_lay = QHBoxLayout()
        self._obs_cards_lay.setSpacing(8)
        ov.addLayout(self._obs_cards_lay)
        root.addWidget(self._obs_box)

        # ── Forward 24 h forecast (site) ───────────────────────────────────────
        self._fwd_box = QGroupBox("Next 24 Hours — Site Forecast (NWS + Open-Meteo)")
        fv = QVBoxLayout(self._fwd_box)
        self._fwd_go_lbl = QLabel("—")
        self._fwd_go_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fwd_go_lbl.setStyleSheet(
            "color: #93c5fd; font-size: 20pt; font-weight: bold; padding: 6px;"
        )
        fv.addWidget(self._fwd_go_lbl)
        self._fwd_go_sub = QLabel(
            "Hourly model forecast at the selected site coordinates."
        )
        self._fwd_go_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fwd_go_sub.setWordWrap(True)
        self._fwd_go_sub.setStyleSheet("color: #64748b; font-size: 9pt;")
        fv.addWidget(self._fwd_go_sub)
        self._fwd_window_lbl = QLabel("")
        self._fwd_window_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fwd_window_lbl.setWordWrap(True)
        self._fwd_window_lbl.setStyleSheet("color: #94a3b8; font-size: 9pt;")
        self._fwd_source_lbl = QLabel("")
        self._fwd_source_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fwd_source_lbl.setWordWrap(True)
        self._fwd_source_lbl.setStyleSheet("color: #94a3b8; font-size: 8pt;")
        fv.addWidget(self._fwd_source_lbl)
        self._fwd_cards_lay = QHBoxLayout()
        self._fwd_cards_lay.setSpacing(8)
        fv.addLayout(self._fwd_cards_lay)
        root.addWidget(self._fwd_box)

        # ── Data source badge ──────────────────────────────────────────────────
        src_frame = QFrame()
        src_row = QHBoxLayout(src_frame)
        src_row.setContentsMargins(0, 0, 0, 0)
        src_row.setSpacing(8)
        self._ndbc_badge = QLabel("NDBC: —")
        self._wind_badge = QLabel("NWS wind: —")
        self._wave_badge = QLabel("Open-Meteo: —")
        for b in (self._ndbc_badge, self._wind_badge, self._wave_badge):
            b.setStyleSheet(
                "background:#374151;color:#64748b;padding:3px 8px;"
                "border-radius:3px;font-size:11px;"
            )
            src_row.addWidget(b)
        src_row.addStretch()
        root.addWidget(src_frame)

        self._no_data_label = QLabel("")
        self._no_data_label.setWordWrap(True)
        self._no_data_label.setStyleSheet(
            "background:#450a0a;color:#fca5a5;padding:8px;border-radius:4px;font-size:10px;"
        )
        self._no_data_label.hide()
        root.addWidget(self._no_data_label)

        # ── Station blend weights (past only) ─────────────────────────────────
        self._weights_box = QGroupBox("Past — Buoy Blend Weights")
        wv = QVBoxLayout(self._weights_box)
        self._weights_lbl = QLabel("—")
        self._weights_lbl.setStyleSheet("color: #94a3b8; font-size: 8pt;")
        wv.addWidget(self._weights_lbl)
        root.addWidget(self._weights_box)

        root.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

    # ── Show event ─────────────────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_site_selector()
        self._refresh_station_list()

    def on_project_changed(self) -> None:
        self._refresh_site_selector()
        self._refresh_station_list()

    def _refresh_site_selector(self) -> None:
        from ui.widgets.project_site_selector import refresh_project_site_selector
        refresh_project_site_selector(self.mw, self._site_combo, self._site_name_lbl)

    def _on_site_combo_changed(self) -> None:
        self._refresh_station_list()

    def _selected_site(self):
        from ui.widgets.project_site_selector import selected_project_site
        return selected_project_site(self.mw, self._site_combo)

    def _go_banner_color(self, go_pct: float) -> str:
        from core.verdict_thresholds import go_pct_threshold, marginal_pct_threshold
        if go_pct >= go_pct_threshold():
            return "#86efac"
        if go_pct >= marginal_pct_threshold():
            return "#fde68a"
        return "#fca5a5"

    def _refresh_station_list(self) -> None:
        """Load selected station IDs from session state, populate the combo, and
        build station objects with real great-circle distances from the active
        site so the blend weighting reflects actual proximity (Step 11 Fix B)."""
        from core.settings import get_session
        from core.database import get_connection
        from core.utils import haversine_nm
        import json

        raw = get_session("selected_ndbc_stations")
        ids = json.loads(raw) if raw else []

        # Keep the single-station dropdown in sync with the selection.
        self._station_combo.blockSignals(True)
        self._station_combo.clear()
        for sid in ids:
            self._station_combo.addItem(sid)
        self._station_combo.blockSignals(False)

        if not ids:
            self._station_status_label.setText(
                "No NDBC stations selected. Select stations on the NDBC tab first."
            )
            self._station_status_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
            self._stations = []
            return

        active_site = self._selected_site()

        conn = get_connection()
        try:
            station_rows = {}
            for sid in ids:
                row = conn.execute(
                    "SELECT station_id, name, lat, lon, has_spec "
                    "FROM ndbc_stations WHERE station_id = ?",
                    (sid,),
                ).fetchone()
                if row:
                    station_rows[sid] = row
        finally:
            conn.close()

        from core.models import NDBCStation
        self._stations = []
        equal_weight_warning = False

        for sid in ids:
            row = station_rows.get(sid)
            if row is None:
                # Discovered but not cached in ndbc_stations → default distance.
                equal_weight_warning = True
                stn = NDBCStation(station_id=sid, name=sid, lat=0.0, lon=0.0,
                                  distance_nm=1.0)
            elif active_site is None:
                # No active site → cannot compute real distance.
                equal_weight_warning = True
                stn = NDBCStation(station_id=row["station_id"],
                                  name=row["name"] or sid,
                                  lat=row["lat"], lon=row["lon"],
                                  distance_nm=1.0)
            else:
                dist_nm = haversine_nm(active_site.lat, active_site.lon,
                                       row["lat"], row["lon"])
                dist_nm = max(1.0, dist_nm)   # clamp to avoid divide-by-zero weight
                stn = NDBCStation(station_id=row["station_id"],
                                  name=row["name"] or sid,
                                  lat=row["lat"], lon=row["lon"],
                                  distance_nm=dist_nm)
            self._stations.append(stn)

        if equal_weight_warning:
            self._station_status_label.setText(
                "⚠ No project site selected. Station blend weights default to equal "
                "(1.0 NM). Select a site above for distance-weighted averaging."
            )
            self._station_status_label.setStyleSheet(
                "color: #fde68a; background: #422006; padding: 6px 10px; "
                "border-radius: 4px; font-size: 11px;"
            )
        else:
            n = len(self._stations)
            self._station_status_label.setText(
                f"Using {n} NDBC station{'s' if n != 1 else ''} from last NDBC "
                f"session: {', '.join(ids[:5])}{'...' if n > 5 else ''}"
            )
            self._station_status_label.setStyleSheet("color: #94a3b8; font-size: 11px;")

    # ── Horizon toggle ─────────────────────────────────────────────────────────

    def _on_horizon_changed(self, btn_id: int, checked: bool) -> None:
        if not checked:
            return
        h = _HORIZONS[btn_id]
        self._conf_dots.set_active(_CONFIDENCE.get(h, 2))
        self._last_horizon = h

        # Re-analyze past window from cached NDBC data only.
        if self._last_station_data is None:
            return
        from modules.m2_weather.ndbc_history import analyze_hourly_go_window
        try:
            include = None
            if self._last_use_single and self._last_station_data:
                include = {next(iter(self._last_station_data))}
            self._last_observed = analyze_hourly_go_window(
                self._last_station_data,
                horizon_hours=h,
                vehicle=self._active_vehicle,
                include_ids=include,
            )
            if self._last_observed:
                self._last_observed["source_label"] = self._obs_source_lbl.text()
            self._render_observed(self._last_observed)
        except Exception as e:
            print(f"Horizon re-analysis failed: {e}")

    def _current_horizon(self) -> int:
        idx = self._hor_group.checkedId()
        return _HORIZONS[idx] if 0 <= idx < len(_HORIZONS) else 72

    # ── Run ────────────────────────────────────────────────────────────────────

    def _on_run(self) -> None:
        try:
            from core.settings import get_session
            raw = get_session("selected_ndbc_stations")
            ids = json.loads(raw) if raw else []
        except Exception:
            ids = []

        if self._blend_one_rb.isChecked():
            single = self._station_combo.currentText()
            if not single:
                QMessageBox.warning(self, "No Station",
                                    "Select a station from the dropdown.")
                return
            ids = [single]

        use_single = self._blend_one_rb.isChecked()
        if use_single:
            single = self._station_combo.currentText()
            if single:
                ids = [single]

        site = self._selected_site()
        if not site:
            QMessageBox.warning(
                self, "No Site",
                "Open a project with at least one site, or select a site from the list.",
            )
            return

        self._active_vehicle = getattr(self.mw, "vehicle", None)
        self._last_use_single = use_single
        horizon = self._current_horizon()
        self._run_btn.setEnabled(False)
        self._run_status.setText("Fetching buoy observations and 24 h site forecast…")

        self._worker = _ForecastWorker(
            ids, self._stations, horizon,
            site_lat=site.lat, site_lon=site.lon, vehicle=self._active_vehicle,
            use_single=use_single,
        )
        self._worker.finished.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.progress.connect(self._on_progress)
        self._worker.start()

    def _on_clear_overlay(self) -> None:
        """Clear the persisted NDBC station selection."""
        from core.settings import set_session
        set_session("selected_ndbc_stations", "[]")
        self._stations = []
        self._last_station_data = None
        self._last_observed = {}
        self._station_status_label.setText(
            "NDBC station selection cleared. Select stations on the NDBC tab."
        )
        self._station_status_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
        self._station_combo.blockSignals(True)
        self._station_combo.clear()
        self._station_combo.blockSignals(False)
        self._update_source_badges(0, False, False, False, None)
        self._render_observed({})
        self._render_forecast_24h({})
        self._no_data_label.hide()

    def _on_error(self, msg: str) -> None:
        self._run_btn.setEnabled(True)
        self._run_status.setText(f"Error: {msg[:80]}")
        QMessageBox.critical(self, "Forecast Error", msg)

    def _on_progress(self, msg: str) -> None:
        self._run_status.setText(msg)

    def _on_result(self, result: dict) -> None:
        self._run_btn.setEnabled(True)
        self._last_station_data = result.pop("_station_data", None)
        self._last_model_combined = result.pop("_model_combined", None)
        ndbc_count = result.pop("_ndbc_station_count", 0)
        nws_ok = result.pop("_nws_available", False)
        om_ok = result.pop("_openmeteo_available", False)
        om_wx_ok = result.pop("_openmeteo_weather_available", False)
        wind_src = result.pop("_wind_source", None)
        auto_buoy = result.pop("_auto_buoy", False)
        obs_label = result.pop("_obs_source_label", "")
        self._last_observed = result.get("observed") or {}
        self._last_forecast_24h = result.get("forecast_24h") or {}
        if auto_buoy and obs_label:
            self._station_status_label.setText(
                f"Auto-selected {obs_label} (no NDBC tab selection)."
            )
            self._station_status_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
        self._update_source_badges(ndbc_count, nws_ok, om_ok, om_wx_ok, wind_src)
        self._run_status.setText("Analysis complete.")
        self._update_display()

    def _populate_cards(self, layout, cards: list) -> None:
        _clear_layout(layout)
        if not cards:
            layout.addWidget(QLabel("No parameter data in this window."))
        else:
            for card_data in cards:
                layout.addWidget(
                    _status_card(
                        card_data["param"], card_data["value"], card_data["status"],
                        card_data.get("threshold", ""),
                    )
                )
        layout.addStretch()

    def _format_go_line(self, total_go, period, go_pct) -> str:
        if go_pct is not None and period > 0:
            return f"{total_go:.0f} of {period} h ({go_pct:.0f}%)"
        if period > 0:
            return f"{total_go:.0f} of {period} h"
        return "—"

    def _render_observed(self, analysis: dict) -> None:
        horizon_lbl = analysis.get("horizon_label", "—")
        period = analysis.get("period_hours", self._last_horizon)
        total_go = analysis.get("go_hours")
        go_pct = analysis.get("go_pct")
        data_hours = analysis.get("data_hours")
        coverage = analysis.get("coverage_pct")
        source = analysis.get("source_label", "")

        self._obs_source_lbl.setText(source or "NDBC buoy observations")

        if total_go is not None and period > 0 and self._active_vehicle is not None:
            self._obs_go_lbl.setText(self._format_go_line(total_go, period, go_pct))
            cov_txt = ""
            if data_hours is not None and coverage is not None:
                cov_txt = f" · data in {data_hours:.0f} of {period:.0f} h ({coverage:.0f}% coverage)"
            self._obs_go_sub.setText(
                f"Past observed hours meeting all {self._active_vehicle.name} thresholds "
                f"· look-back {horizon_lbl}{cov_txt}"
            )
            if go_pct is not None:
                color = self._go_banner_color(go_pct)
                self._obs_go_lbl.setStyleSheet(
                    f"color: {color}; font-size: 20pt; font-weight: bold; padding: 6px;"
                )
        elif not analysis:
            self._obs_go_lbl.setText("—")
            self._obs_go_sub.setText(
                "No buoy data — select stations on NDBC tab or use nearest auto-selected buoy."
            )
            self._obs_go_lbl.setStyleSheet(
                "color: #64748b; font-size: 20pt; font-weight: bold; padding: 6px;"
            )
        elif self._active_vehicle is None:
            self._obs_go_lbl.setText("—")
            self._obs_go_sub.setText(
                "Select a vehicle in Analysis to evaluate observed GO hours."
            )
        else:
            self._obs_go_lbl.setText("Insufficient data")
            self._obs_go_sub.setText("No valid hourly observations in the selected window.")

        self._populate_cards(self._obs_cards_lay, analysis.get("cards") or [])

        weights = analysis.get("weights", {})
        if weights:
            lines = [
                f"<b style='color:#f1f5f9;'>{sid}</b>:"
                f" <span style='color:#93c5fd;'>{w*100:.1f}%</span>"
                for sid, w in sorted(weights.items(), key=lambda kv: -kv[1])
            ]
            self._weights_lbl.setText("  ·  ".join(lines))
            self._weights_box.setVisible(True)
        else:
            self._weights_lbl.setText("—")
            self._weights_box.setVisible(bool(analysis))

    def _render_forecast_24h(self, analysis: dict) -> None:
        period = analysis.get("period_hours", 24)
        total_go = analysis.get("go_hours")
        go_pct = analysis.get("go_pct")
        go_windows = analysis.get("go_windows") or []
        data_hours = analysis.get("data_hours")
        coverage = analysis.get("coverage_pct")
        source = analysis.get("source_label", "")

        self._fwd_source_lbl.setText(source or "Site coordinates · NWS + Open-Meteo")

        if total_go is not None and self._active_vehicle is not None:
            self._fwd_go_lbl.setText(self._format_go_line(total_go, period, go_pct))
            cov_txt = ""
            if data_hours is not None and coverage is not None:
                cov_txt = f" · {data_hours:.0f} of {period:.0f} h had forecast data"
            self._fwd_go_sub.setText(
                f"Next 24 h at site meeting all {self._active_vehicle.name} "
                f"thresholds{cov_txt}"
            )
            if go_pct is not None:
                color = self._go_banner_color(go_pct)
                self._fwd_go_lbl.setStyleSheet(
                    f"color: {color}; font-size: 20pt; font-weight: bold; padding: 6px;"
                )
            if go_windows:
                longest = max(go_windows, key=lambda w: w.get("duration_hours", 0))
                dur = longest.get("duration_hours", 0)
                start = longest.get("start_hour", 0)
                self._fwd_window_lbl.setText(
                    f"Longest contiguous GO window: {dur:.0f} h "
                    f"(starts at hour +{start:.0f} from now)"
                )
            else:
                self._fwd_window_lbl.setText("No contiguous GO window in the next 24 h.")
        elif not analysis:
            self._fwd_go_lbl.setText("—")
            self._fwd_go_sub.setText(
                "Site forecast unavailable — check network; NWS is US-only "
                "(Open-Meteo wind/wave used elsewhere)."
            )
            self._fwd_window_lbl.setText("")
            self._fwd_go_lbl.setStyleSheet(
                "color: #64748b; font-size: 20pt; font-weight: bold; padding: 6px;"
            )
        elif self._active_vehicle is None:
            self._fwd_go_lbl.setText("—")
            self._fwd_go_sub.setText("Select a vehicle in Analysis to evaluate forecast GO hours.")
            self._fwd_window_lbl.setText("")
        else:
            self._fwd_go_lbl.setText("Insufficient data")
            self._fwd_go_sub.setText("No valid forecast hours for this site.")
            self._fwd_window_lbl.setText("")

        self._populate_cards(self._fwd_cards_lay, analysis.get("cards") or [])

    def _update_display(self) -> None:
        self._render_observed(self._last_observed)
        self._render_forecast_24h(self._last_forecast_24h)

    def _update_source_badges(
        self,
        ndbc_count: int,
        nws_available: bool,
        openmeteo_available: bool,
        openmeteo_weather_available: bool = False,
        wind_source: str | None = None,
    ) -> None:
        if ndbc_count > 0:
            self._ndbc_badge.setText(f"Past (NDBC): {ndbc_count} buoy(s) ✓")
            self._ndbc_badge.setStyleSheet(
                "background:#14532d;color:#86efac;"
                "padding:3px 8px;border-radius:3px;font-size:11px;"
            )
        else:
            self._ndbc_badge.setText("Past (NDBC): no data ✗")
            self._ndbc_badge.setStyleSheet(
                "background:#450a0a;color:#fca5a5;"
                "padding:3px 8px;border-radius:3px;font-size:11px;"
            )

        if nws_available:
            self._wind_badge.setText("Next 24 h wind: NWS ✓")
            self._wind_badge.setStyleSheet(
                "background:#14532d;color:#86efac;"
                "padding:3px 8px;border-radius:3px;font-size:11px;"
            )
        elif openmeteo_weather_available or wind_source == "openmeteo_weather":
            self._wind_badge.setText("Next 24 h wind: Open-Meteo ✓")
            self._wind_badge.setStyleSheet(
                "background:#14532d;color:#86efac;"
                "padding:3px 8px;border-radius:3px;font-size:11px;"
            )
        else:
            self._wind_badge.setText("Next 24 h wind: unavailable ✗")
            self._wind_badge.setStyleSheet(
                "background:#450a0a;color:#fca5a5;"
                "padding:3px 8px;border-radius:3px;font-size:11px;"
            )

        if openmeteo_available:
            self._wave_badge.setText("Next 24 h waves: Open-Meteo ✓")
            self._wave_badge.setStyleSheet(
                "background:#14532d;color:#86efac;"
                "padding:3px 8px;border-radius:3px;font-size:11px;"
            )
        else:
            self._wave_badge.setText("Next 24 h waves: unavailable ✗")
            self._wave_badge.setStyleSheet(
                "background:#450a0a;color:#fca5a5;"
                "padding:3px 8px;border-radius:3px;font-size:11px;"
            )

        if ndbc_count == 0 and not nws_available and not openmeteo_available:
            self._no_data_label.setText(
                "Limited data: pick NDBC buoys for past analysis; site forecast needs "
                "Open-Meteo (global) or NWS (US) network access."
            )
            self._no_data_label.show()
        else:
            self._no_data_label.hide()


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()

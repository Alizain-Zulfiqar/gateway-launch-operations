"""
ui/sections/comparison.py — Multi-site launch window probability comparison.

Uses the same Copernicus ERA5 Historical path as Main Analysis (cache ensure →
month-pooled climatology → day-fraction GO verdicts). Decision Charts overlay
all sites; Per-Site Charts render the Main Analysis chart stack for each site
separately (main.html-style).
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QGroupBox, QSpinBox,
    QFormLayout, QScrollArea, QSizePolicy, QMessageBox, QFileDialog,
    QProgressBar, QCheckBox, QFrame, QGridLayout,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRectF
from PyQt6.QtGui import QColor, QPainter, QPen, QFont

from core.database import get_connection
from core.models import Site, AnalysisResult
from ui.styles import apply_table_colors
from ui.widgets.analysis_charts import (
    AnalysisChartsWidget,
    ComparisonChartsWidget,
    SITE_COLORS,
)
from ui.widgets.threshold_editor import ThresholdEditorWidget, threshold_editor_stylesheet
from ui import analysis_common as ac
from config import DEFAULT_THRESHOLDS

_MO = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

_COLUMNS_RANK = [
    "Rank", "Site", "Lat", "Lon", "Annual GO%",
    "Mean Prob%", "Best Month", "Worst Month",
]


# ── Worker thread ─────────────────────────────────────────────────────────────

class _ComparisonWorker(QThread):
    """ERA5-backed comparison — one site at a time with progress updates."""

    finished = pyqtSignal(list)  # (Site, profile, clim, operability, day_frac, param_frac)
    error = pyqtSignal(str)
    # msg, done, total — done < 0 ⇒ indeterminate busy bar
    progress = pyqtSignal(str, int, int)

    def __init__(
        self,
        sites,
        vehicle,
        platform,
        year_start,
        year_end,
        thresholds=None,
        weights=None,
    ):
        super().__init__()
        self._sites = sites
        self._vehicle = vehicle
        self._platform = platform
        self._year_start = year_start
        self._year_end = year_end
        self._thresholds = thresholds
        self._weights = weights

    def run(self):
        try:
            from modules.m3_probability.compare_sites import compare_site_era5

            results = []
            n = len(self._sites)
            for i, site in enumerate(self._sites):
                label = site.name or site.coord_str

                def _on_progress(
                    done: int, total: int, detail: str, *, _i=i, _n=n
                ) -> None:
                    self.progress.emit(f"Site {_i + 1}/{_n}: {detail}", done, total)

                self.progress.emit(
                    f"Site {i + 1}/{n}: {label} — starting ERA5 comparison…",
                    -1, 0,
                )
                profile, climatology, operability, day_frac, param_frac = compare_site_era5(
                    site,
                    self._vehicle,
                    self._platform,
                    self._year_start,
                    self._year_end,
                    thresholds=self._thresholds,
                    weights=self._weights,
                    on_progress=_on_progress,
                )
                results.append(
                    (site, profile, climatology, operability, day_frac, param_frac),
                )
            self.finished.emit(results)
        except Exception as exc:
            self.error.emit(str(exc))


# ── Simple line-chart widget ──────────────────────────────────────────────────

class _LineChart(QWidget):
    """12-month probability line chart drawn with QPainter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._series: list[tuple[str, str, list[float]]] = []
        # (site_name, hex_color, [12 floats 0-1])
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, series: list[tuple[str, str, list[float]]]) -> None:
        self._series = series
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        ml, mr, mt, mb = 50, 20, 20, 40   # margins

        chart_w = w - ml - mr
        chart_h = h - mt - mb

        # Background
        p.fillRect(0, 0, w, h, QColor("#1a2233"))

        # Grid lines + Y labels
        p.setPen(QPen(QColor("#374151"), 1, Qt.PenStyle.DotLine))
        p.setFont(QFont("Segoe UI", 7))
        for pct in [0, 25, 50, 70, 100]:
            y = mt + chart_h - int(pct / 100 * chart_h)
            p.drawLine(ml, y, ml + chart_w, y)
            p.setPen(QColor("#94a3b8"))
            p.drawText(0, y - 6, ml - 4, 14, Qt.AlignmentFlag.AlignRight, f"{pct}%")
            p.setPen(QPen(QColor("#374151"), 1, Qt.PenStyle.DotLine))

        # GO threshold from Settings
        from core.verdict_thresholds import go_pct_threshold
        go_pct = go_pct_threshold()
        y_go = mt + chart_h - int(go_pct / 100 * chart_h)
        p.setPen(QPen(QColor("#d97706"), 1, Qt.PenStyle.DashLine))
        p.drawLine(ml, y_go, ml + chart_w, y_go)

        # X labels
        p.setPen(QColor("#94a3b8"))
        p.setFont(QFont("Segoe UI", 7))
        for i, mo in enumerate(_MO):
            x = ml + int((i + 0.5) * chart_w / 12)
            p.drawText(x - 12, h - mb + 4, 24, 14,
                       Qt.AlignmentFlag.AlignCenter, mo)

        # Lines
        if not self._series:
            p.setPen(QColor("#64748b"))
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(ml, mt, chart_w, chart_h,
                       Qt.AlignmentFlag.AlignCenter,
                       "Select sites and run comparison")
            return

        for label, color, values in self._series:
            pen = QPen(QColor(color), 2)
            p.setPen(pen)
            pts = []
            for i, v in enumerate(values):
                x = ml + int((i + 0.5) * chart_w / 12)
                y = mt + chart_h - int(v * chart_h)
                pts.append((x, y))
            for i in range(len(pts) - 1):
                p.drawLine(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])
            # Dot at each month
            for x, y in pts:
                p.setBrush(QColor(color))
                p.drawEllipse(x - 3, y - 3, 6, 6)

        # Legend
        lx = ml + 4
        ly = mt + 6
        p.setFont(QFont("Segoe UI", 7))
        for label, color, _ in self._series:
            p.setPen(QPen(QColor(color), 2))
            p.drawLine(lx, ly + 5, lx + 18, ly + 5)
            p.setPen(QColor("#e2e8f0"))
            p.drawText(lx + 22, ly, 160, 14, Qt.AlignmentFlag.AlignLeft, label[:30])
            ly += 16


# ── Comparison section ────────────────────────────────────────────────────────

class ComparisonSection(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        # (Site, profile) for rankings; full quads kept for charts/PDF.
        self._results: list[tuple[Site, dict]] = []
        self._full_results: list = []
        self._climatologies: list = []
        self._worker: _ComparisonWorker | None = None
        self._per_site_charts: list[AnalysisChartsWidget] = []
        # Session cache: same sites/years/thresholds → instant re-display
        # (ERA5 months already live in era5_monthly_cache like Main Analysis).
        self._result_cache: dict = {}
        self._last_cache_key: tuple | None = None
        self._last_chart_ctx: dict = {}
        self._build()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._reload_sites()
        from config import refresh_analysis_year_spins
        refresh_analysis_year_spins(self._year_start, self._year_end)
        from core.verdict_thresholds import go_pct_threshold
        self._chart_group.setTitle(
            f"Decision Charts  (ERA5 day-fraction GO% · {go_pct_threshold():.0f}% "
            f"GO threshold shown)"
        )

    def refresh_site_list(self, *_) -> None:
        """Public slot — called when a new site is saved."""
        self._reload_sites()

    def on_project_changed(self) -> None:
        """Called by GatewayMainWindow.open_project()/close_project() — reloads
        the site checklist scoped to the open project (all pre-checked)."""
        self._reload_sites()

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left panel ────────────────────────────────────────────────────────
        left = QWidget()
        left.setFixedWidth(320)
        left.setStyleSheet("background: #151c27; border-right: 1px solid #374151;")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(12, 16, 12, 16)
        lv.setSpacing(10)

        lv.addWidget(QLabel("Multi-Site Comparison"))

        self._hint = QLabel("Check 2–7 saved sites:")
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet("color: #94a3b8; font-size: 8pt;")
        lv.addWidget(self._hint)

        self._site_list = QListWidget()
        self._site_list.setMinimumHeight(140)
        self._site_list.setStyleSheet("background: #1a2233; border: 1px solid #374151;")
        lv.addWidget(self._site_list, 1)

        # Run settings — scroll when the window is short (optimal values + years + buttons).
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        settings_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        settings_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        settings_inner = QWidget()
        settings_inner.setStyleSheet("background: transparent;")
        settings_layout = QVBoxLayout(settings_inner)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(10)

        opt_group = QGroupBox("Optimal Values")
        opt_group.setStyleSheet(
            "QGroupBox { color: #e2e8f0; font-size: 9pt; font-weight: bold;"
            " border: 1px solid #374151; border-radius: 6px; margin-top: 10px;"
            " padding-top: 14px; background: #1a2233; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }"
        )
        opt_layout = QVBoxLayout(opt_group)
        opt_layout.setContentsMargins(10, 8, 10, 10)
        opt_layout.setSpacing(8)
        self._threshold_editor = ThresholdEditorWidget(
            compact=True,
            show_header=False,
            show_hint=True,
        )
        self._threshold_editor.setFrameShape(QFrame.Shape.NoFrame)
        self._threshold_editor.setStyleSheet(threshold_editor_stylesheet(flat=True))
        self._threshold_editor.set_defaults(DEFAULT_THRESHOLDS)
        opt_layout.addWidget(self._threshold_editor)

        dir_lbl = QLabel("Include in operability:")
        dir_lbl.setStyleSheet("color: #94a3b8; font-size: 8pt; font-weight: 600;")
        opt_layout.addWidget(dir_lbl)
        dir_grid = QGridLayout()
        dir_grid.setHorizontalSpacing(4)
        dir_grid.setVerticalSpacing(4)
        _CB_STYLE = "QCheckBox { color: #e2e8f0; font-size: 8pt; spacing: 4px; }"
        from core.settings import get_setting
        self._cb_wind_dir = QCheckBox("Wind dir")
        self._cb_sea_dir = QCheckBox("Sea dir")
        self._cb_swell_dir = QCheckBox("Swell dir")
        for i, cb in enumerate((self._cb_wind_dir, self._cb_sea_dir, self._cb_swell_dir)):
            cb.setStyleSheet(_CB_STYLE)
            dir_grid.addWidget(cb, i // 2, i % 2)
        self._cb_wind_dir.setChecked(get_setting("exclude_wind_dir", "1") == "0")
        self._cb_sea_dir.setChecked(get_setting("exclude_sea_dir", "1") == "0")
        self._cb_swell_dir.setChecked(get_setting("exclude_swell_dir", "1") == "0")
        opt_layout.addLayout(dir_grid)
        dir_hint = QLabel("Unchecked = excluded from charts and ranking.")
        dir_hint.setWordWrap(True)
        dir_hint.setStyleSheet("color: #64748b; font-size: 7pt; font-style: italic;")
        opt_layout.addWidget(dir_hint)
        settings_layout.addWidget(opt_group)

        # Year range
        year_group = QGroupBox("Year Range")
        year_group.setStyleSheet(opt_group.styleSheet())
        form = QFormLayout(year_group)
        form.setContentsMargins(10, 8, 10, 10)
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self._year_start = QSpinBox()
        self._year_start.setValue(2020)
        self._year_end = QSpinBox()
        from datetime import date as _date
        from config import analysis_year_max
        self._year_end.setValue(min(_date.today().year, analysis_year_max()))
        from config import refresh_analysis_year_spins
        refresh_analysis_year_spins(self._year_start, self._year_end)
        form.addRow("Start:", self._year_start)
        form.addRow("End:", self._year_end)
        settings_layout.addWidget(year_group)

        era5_note = QLabel(
            "Copernicus ERA5 Historical (same as Main Analysis). "
            "First run may take several minutes per site; cache reuse afterward."
        )
        era5_note.setWordWrap(True)
        era5_note.setStyleSheet("color: #64748b; font-size: 7.5pt;")
        settings_layout.addWidget(era5_note)

        self._run_btn = QPushButton("Run Comparison")
        self._run_btn.setStyleSheet(
            "background: #2563eb; color: white; border-radius: 4px;"
            "padding: 8px; font-weight: bold;"
        )
        self._run_btn.clicked.connect(self._on_run)
        settings_layout.addWidget(self._run_btn)

        self._report_btn = QPushButton("Export Detailed Report (PDF)")
        self._report_btn.setEnabled(False)
        self._report_btn.setStyleSheet(
            "background: #166534; color: white; border-radius: 4px;"
            "padding: 8px; font-weight: bold;"
        )
        self._report_btn.clicked.connect(self._on_export_report)
        settings_layout.addWidget(self._report_btn)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedHeight(12)
        self._progress.setTextVisible(False)
        self._progress.setVisible(False)
        self._progress.setStyleSheet(
            "QProgressBar { background: #1a2233; border: 1px solid #374151;"
            " border-radius: 4px; }"
            "QProgressBar::chunk { background: #2563eb; border-radius: 4px; }"
        )
        settings_layout.addWidget(self._progress)

        self._status_lbl = QLabel("")
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setStyleSheet("color: #94a3b8; font-size: 8pt;")
        settings_layout.addWidget(self._status_lbl)

        settings_scroll.setWidget(settings_inner)
        lv.addWidget(settings_scroll, 0)

        root.addWidget(left)

        # ── Right panel (scrollable — charts + rankings can be tall) ───────────
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setStyleSheet(
            "QScrollArea { border:none; background:#0f1923; }"
            "QScrollBar:vertical { background:#0f1923; width:10px; }"
            "QScrollBar::handle:vertical { background:#374151; border-radius:5px; }"
        )
        right = QWidget()
        right.setStyleSheet("background:#0f1923;")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(16, 16, 16, 16)
        rv.setSpacing(12)

        title = QLabel("Comparison")
        title.setObjectName("sectionTitle")
        rv.addWidget(title)

        # Decision charts (matplotlib): overlaid GO lines, site×month heatmap,
        # and annual-mean ranking bar — fed by ERA5 day-fraction GO%.
        chart_group = QGroupBox()
        self._chart_group = chart_group
        cg_layout = QVBoxLayout(chart_group)
        self._charts = ComparisonChartsWidget()
        cg_layout.addWidget(self._charts)
        rv.addWidget(chart_group)

        # Rankings table
        rank_group = QGroupBox("Site Rankings")
        rg_layout = QVBoxLayout(rank_group)
        self._rank_table = QTableWidget(0, len(_COLUMNS_RANK))
        self._rank_table.setHorizontalHeaderLabels(_COLUMNS_RANK)
        self._rank_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self._rank_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._rank_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self._rank_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._rank_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        apply_table_colors(self._rank_table)
        self._rank_table.setMinimumHeight(240)
        rg_layout.addWidget(self._rank_table)
        rv.addWidget(rank_group)

        # Per-site Main Analysis charts (separate panel per site, main.html style)
        self._per_site_group = QGroupBox(
            "Per-Site Charts  (ERA5 — same stack as Main Analysis)"
        )
        self._per_site_layout = QVBoxLayout(self._per_site_group)
        self._per_site_layout.setContentsMargins(8, 16, 8, 16)
        self._per_site_layout.setSpacing(36)
        empty = QLabel("Run a comparison to see per-site charts.")
        empty.setStyleSheet("color: #64748b; font-size: 9pt;")
        empty.setObjectName("perSiteEmpty")
        self._per_site_layout.addWidget(empty)
        rv.addWidget(self._per_site_group)

        right_scroll.setWidget(right)
        root.addWidget(right_scroll, 1)

    # ── Data loading ──────────────────────────────────────────────────────────

    def _reload_sites(self) -> None:
        # When a project is open, scope the checklist to its sites and pre-check
        # them all (comparison is a project-level decision). Otherwise fall back
        # to the full saved-sites list (unchecked by default).
        open_id = getattr(self.mw, "open_project_id", None)
        project_mode = open_id is not None

        if project_mode:
            sites = getattr(self.mw, "open_project_sites", []) or []
            rows = [
                {"id": s.id, "name": s.name or "Unnamed",
                 "lat": s.lat, "lon": s.lon}
                for s in sites if s.id is not None
            ]
            self._hint.setText(
                f"Project sites (2–7 for comparison) — {len(rows)} available:"
            )
        else:
            try:
                conn = get_connection()
                db_rows = conn.execute(
                    "SELECT id, name, lat, lon FROM sites ORDER BY name"
                ).fetchall()
                conn.close()
            except Exception:
                return
            rows = [dict(r) for r in db_rows]
            self._hint.setText("Check 2–7 saved sites:")

        # Preserve prior checked states by id (used in the non-project path).
        checked_ids = set()
        for i in range(self._site_list.count()):
            item = self._site_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                checked_ids.add(item.data(Qt.ItemDataRole.UserRole))

        self._site_list.clear()
        for r in rows:
            lat_d = "N" if r["lat"] >= 0 else "S"
            lon_d = "E" if r["lon"] >= 0 else "W"
            label = f"{r['name']}  ({abs(r['lat']):.2f}°{lat_d}, {abs(r['lon']):.2f}°{lon_d})"
            item = QListWidgetItem(label)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if project_mode:
                checked = True  # pre-check all project sites
            else:
                checked = r["id"] in checked_ids
            item.setCheckState(
                Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            )
            item.setData(Qt.ItemDataRole.UserRole, r["id"])
            self._site_list.addItem(item)

    def _collect_checked_sites(self) -> list[Site]:
        sites = []
        for i in range(self._site_list.count()):
            item = self._site_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                site_id = item.data(Qt.ItemDataRole.UserRole)
                try:
                    conn = get_connection()
                    r = conn.execute(
                        "SELECT id, name, lat, lon, bbox_nm FROM sites WHERE id=?",
                        (site_id,)
                    ).fetchone()
                    conn.close()
                    if r:
                        sites.append(Site(
                            id=r["id"], name=r["name"],
                            lat=r["lat"], lon=r["lon"],
                            bbox_nm=r["bbox_nm"] or 25.0,
                        ))
                except Exception:
                    pass
        return sites

    # ── Actions ───────────────────────────────────────────────────────────────

    def _comparison_thresholds(self) -> dict:
        return dict(self._threshold_editor.values())

    def _comparison_weights(self) -> dict:
        return ac.active_weights(
            self._cb_wind_dir.isChecked(),
            self._cb_sea_dir.isChecked(),
            self._cb_swell_dir.isChecked(),
        )

    def _make_cache_key(
        self,
        sites: list[Site],
        year_start: int,
        year_end: int,
        thresholds: dict,
        weights: dict,
    ) -> tuple:
        site_ids = tuple(sorted(s.id for s in sites if s.id is not None))
        thr = tuple(sorted(
            (k, round(float(v), 4)) for k, v in (thresholds or {}).items()
            if v is not None
        ))
        wts = tuple(sorted(
            (k, round(float(v), 6)) for k, v in (weights or {}).items()
            if float(v or 0) > 0
        ))
        vid = getattr(self.mw.vehicle, "id", None) or getattr(
            self.mw.vehicle, "name", ""
        )
        pid = getattr(self.mw.platform, "id", None) or getattr(
            self.mw.platform, "name", ""
        )
        return (site_ids, year_start, year_end, thr, wts, vid, pid)

    def _on_run(self) -> None:
        selected_sites = self._collect_checked_sites()

        if len(selected_sites) < 2:
            QMessageBox.warning(self, "Selection",
                                "Select at least 2 sites to compare.")
            return

        if len(selected_sites) > 7:
            QMessageBox.warning(self, "Selection",
                                "Select at most 7 sites (chart colour limit).")
            return

        ys = self._year_start.value()
        ye = self._year_end.value()
        if ye < ys:
            QMessageBox.warning(self, "Year Range",
                                "Year end must be ≥ year start.")
            return

        thresholds = self._comparison_thresholds()
        weights = self._comparison_weights()
        from modules.m2_weather.operability import criteria_params_from_weights
        self._last_chart_ctx = {
            "thresholds": thresholds,
            "active_criteria": criteria_params_from_weights(weights),
        }
        cache_key = self._make_cache_key(
            selected_sites, ys, ye, thresholds, weights,
        )
        cached = self._result_cache.get(cache_key)
        if cached is not None:
            self._last_cache_key = cache_key
            self._on_results(cached, from_cache=True)
            return

        span = ye - ys + 1
        if span > 20:
            QMessageBox.information(
                self,
                "Large Year Range",
                f"The selected range spans {span} years across "
                f"{len(selected_sites)} sites. The first Copernicus ERA5 "
                "download may take a long time (cache is reused afterward).",
            )

        self._run_btn.setEnabled(False)
        self._report_btn.setEnabled(False)
        self._last_cache_key = cache_key
        self._set_busy(
            "Running ERA5 comparison… (first download may take several minutes; "
            "re-runs with the same settings are instant)",
            -1, 0,
        )

        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(
                self, "Comparison Running",
                "A comparison is already in progress. Please wait for it to finish.",
            )
            return

        self._worker = _ComparisonWorker(
            sites=selected_sites,
            vehicle=self.mw.vehicle,
            platform=self.mw.platform,
            year_start=ys,
            year_end=ye,
            thresholds=thresholds,
            weights=weights,
        )
        self._worker.finished.connect(self._on_results)
        self._worker.error.connect(self._on_error)
        self._worker.progress.connect(self._on_progress)
        self._worker.start()

    def _set_busy(self, msg: str, done: int = -1, total: int = 0) -> None:
        self._status_lbl.setText(msg)
        self._progress.setVisible(True)
        if done < 0 or total <= 0:
            self._progress.setRange(0, 0)  # indeterminate
        else:
            self._progress.setRange(0, total)
            self._progress.setValue(min(done, total))
        if hasattr(self.mw, "status"):
            self.mw.status(msg)

    def _clear_busy(self) -> None:
        self._progress.setVisible(False)
        self._progress.setRange(0, 0)

    def _on_progress(self, msg: str, done: int, total: int) -> None:
        self._set_busy(msg, done, total)

    def _on_results(self, results: list, from_cache: bool = False) -> None:
        # Worker: (Site, profile, clim, operability, day_frac, param_frac); PDF uses full rows.
        if self._last_cache_key is not None and not from_cache:
            self._result_cache[self._last_cache_key] = results

        self._full_results = results
        self._results = [(site, profile) for site, profile, *_rest in results]
        self._climatologies = [clim for _s, _p, clim, *_rest in results]
        self._run_btn.setEnabled(True)
        self._report_btn.setEnabled(bool(self._results))
        self._clear_busy()
        if from_cache:
            self._status_lbl.setText(
                f"Loaded from cache — {len(self._results)} site"
                f"{'s' if len(self._results) != 1 else ''} "
                "(same settings; ERA5 months already on disk)."
            )
        else:
            self._status_lbl.setText(
                f"Complete — {len(self._results)} site"
                f"{'s' if len(self._results) != 1 else ''} compared "
                "(ERA5, charts 1–12). Re-run with same settings is instant."
            )
        self._update_chart(self._results)
        self._update_rankings(self._results)
        self._update_per_site_charts(results)

    def _on_error(self, msg: str) -> None:
        self._run_btn.setEnabled(True)
        self._clear_busy()
        self._status_lbl.setText(f"Error: {msg}")
        QMessageBox.critical(self, "Comparison Error", msg)

    def _clear_per_site_charts(self) -> None:
        while self._per_site_layout.count():
            item = self._per_site_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._per_site_charts.clear()

    def _update_per_site_charts(self, full_results: list) -> None:
        """One Main Analysis chart stack per site (main.html separate panels)."""
        self._clear_per_site_charts()
        if not full_results:
            empty = QLabel("Run a comparison to see per-site charts.")
            empty.setStyleSheet("color: #64748b; font-size: 9pt;")
            self._per_site_layout.addWidget(empty)
            return

        ctx = self._last_chart_ctx or {}
        for idx, row in enumerate(full_results):
            site, profile, climatology, operability, day_frac, param_frac = row
            color = SITE_COLORS[idx % len(SITE_COLORS)]

            site_box = QGroupBox(site.name or site.coord_str)
            site_box.setStyleSheet(
                f"QGroupBox {{ "
                f"color: {color}; font-size: 11pt; font-weight: bold; "
                f"border: 1px solid #374151; border-radius: 6px; "
                f"margin-top: 14px; padding-top: 18px; "
                f"background: #151c27; }}"
                f"QGroupBox::title {{ subcontrol-origin: margin; left: 12px; "
                f"padding: 0 6px; }}"
            )
            box_layout = QVBoxLayout(site_box)
            box_layout.setContentsMargins(14, 22, 14, 18)
            box_layout.setSpacing(12)

            charts = AnalysisChartsWidget(spacious=True)
            charts.set_profile(
                profile,
                operability=operability,
                climatology=climatology,
                thresholds=ctx.get("thresholds"),
                active_criteria=ctx.get("active_criteria"),
                day_fractions=day_frac,
                param_fractions=param_frac,
            )
            self._per_site_charts.append(charts)
            box_layout.addWidget(charts)
            self._per_site_layout.addWidget(site_box)

    def _on_export_report(self) -> None:
        if not self._results:
            return
        import shutil
        import tempfile
        from datetime import datetime, timezone
        from config import BASE_DIR
        from modules.m5_reports.comparison_pdf import generate_comparison_report

        reports_dir = BASE_DIR / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        default_name = f"comparison_report_{ts}.pdf"

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Comparison Report", str(reports_dir / default_name),
            "PDF files (*.pdf)"
        )
        if not path:
            return

        chart_tmpdir = tempfile.mkdtemp(prefix="gateway_cmp_charts_")
        try:
            saved = generate_comparison_report(
                self._results,
                self.mw.vehicle,
                self.mw.platform,
                path,
                full_results=self._full_results or None,
                chart_tmpdir=chart_tmpdir,
                chart_context=self._last_chart_ctx or None,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))
            return
        finally:
            shutil.rmtree(chart_tmpdir, ignore_errors=True)
        self.mw.status(f"Comparison report saved: {saved}")
        try:
            from core.utils import open_local_path
            open_local_path(saved)
        except Exception as exc:
            QMessageBox.warning(
                self, "Report Saved",
                f"PDF saved to:\n{saved}\n\n"
                f"Could not open it automatically:\n{exc}"
            )

    def _update_chart(self, results: list) -> None:
        self._charts.set_results(results)

    def _update_rankings(self, results: list) -> None:
        # Sort by annual GO fraction descending
        def _annual_go(profile: dict) -> float:
            return sum(1 for r in profile.values() if r.verdict == "GO") / 12.0

        def _annual_mean(profile: dict) -> float:
            return sum(r.overall_prob for r in profile.values()) / 12.0

        ranked = sorted(results, key=lambda sr: _annual_go(sr[1]), reverse=True)

        self._rank_table.setSortingEnabled(False)
        self._rank_table.setRowCount(0)
        self._rank_table.setRowCount(len(ranked))

        for rank_idx, (site, profile) in enumerate(ranked):
            go_frac  = _annual_go(profile)
            mean_p   = _annual_mean(profile)
            best_m   = max(range(1, 13), key=lambda m: profile[m].overall_prob)
            worst_m  = min(range(1, 13), key=lambda m: profile[m].overall_prob)
            color    = SITE_COLORS[results.index((site, profile)) % len(SITE_COLORS)]

            values = [
                str(rank_idx + 1),
                site.name or site.coord_str,
                f"{abs(site.lat):.4f}°{'N' if site.lat>=0 else 'S'}",
                f"{abs(site.lon):.4f}°{'E' if site.lon>=0 else 'W'}",
                f"{go_frac*100:.0f}%",
                f"{mean_p*100:.0f}%",
                _MO[best_m - 1],
                _MO[worst_m - 1],
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setForeground(QColor("#f1f5f9"))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 1:
                    item.setForeground(QColor(color))
                self._rank_table.setItem(rank_idx, col, item)

        self._rank_table.setSortingEnabled(True)

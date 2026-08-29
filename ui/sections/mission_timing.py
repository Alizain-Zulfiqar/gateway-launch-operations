"""
ui/sections/mission_timing.py — Mission Timing: consecutive GO-day windows.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QFormLayout, QGroupBox, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QProgressBar, QSizePolicy,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor

from core.models import Site
from ui.styles import apply_table_colors

_MO = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

_BTN_PRIMARY = (
    "QPushButton { background:#2563eb; color:white; border-radius:4px;"
    "padding:8px 16px; font-weight:bold; border:none; }"
    "QPushButton:hover { background:#1d4ed8; }"
    "QPushButton:disabled { background:#1e3a5f; color:#64748b; }"
)


class _MissionTimingWorker(QThread):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(str, int, int)

    def __init__(self, site, calendar_month, duration_years, thresholds, weights):
        super().__init__()
        self._site = site
        self._month = calendar_month
        self._duration = duration_years
        self._thresholds = thresholds
        self._weights = weights

    def run(self):
        try:
            from modules.m3_probability.mission_windows import analyze_mission_windows

            def _cb(done: int, total: int, detail: str) -> None:
                self.progress.emit(detail, done, total)

            result = analyze_mission_windows(
                self._site,
                self._month,
                self._duration,
                thresholds=self._thresholds,
                weights=self._weights,
                on_progress=_cb,
            )
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class _StreakChart(QWidget):
    """Simple bar chart: max GO streak by year."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._years: list[int] = []
        self._values: list[int] = []
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_data(self, years: list[int], max_streaks: list[int]) -> None:
        self._years = years
        self._values = max_streaks
        self.update()

    def paintEvent(self, event):
        from PyQt6.QtGui import QPainter, QPen, QFont, QColor as QC

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        ml, mr, mt, mb = 44, 16, 28, 36
        cw, ch = w - ml - mr, h - mt - mb
        p.fillRect(0, 0, w, h, QC("#1a2233"))

        p.setPen(QC("#e2e8f0"))
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        p.drawText(ml, 8, cw, 18, Qt.AlignmentFlag.AlignLeft, "Max consecutive GO days by year")

        if not self._years:
            p.setPen(QC("#64748b"))
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(ml, mt, cw, ch, Qt.AlignmentFlag.AlignCenter, "Run analysis to see chart")
            return

        ymax = max(max(self._values, default=1), 1)
        n = len(self._years)
        bar_w = max(8, int(cw / max(n, 1) * 0.55))
        gap = cw / max(n, 1)

        p.setPen(QPen(QC("#374151"), 1, Qt.PenStyle.DotLine))
        for tick in range(0, ymax + 1, max(1, ymax // 5)):
            y = mt + ch - int(tick / ymax * ch)
            p.drawLine(ml, y, ml + cw, y)
            p.setPen(QC("#94a3b8"))
            p.setFont(QFont("Segoe UI", 7))
            p.drawText(0, y - 6, ml - 4, 14, Qt.AlignmentFlag.AlignRight, str(tick))
            p.setPen(QPen(QC("#374151"), 1, Qt.PenStyle.DotLine))

        for i, (yr, val) in enumerate(zip(self._years, self._values)):
            x = ml + int((i + 0.5) * gap - bar_w / 2)
            bh = int(val / ymax * ch) if ymax else 0
            y = mt + ch - bh
            p.fillRect(x, y, bar_w, bh, QC("#2563eb"))
            p.setPen(QC("#94a3b8"))
            p.setFont(QFont("Segoe UI", 7))
            p.drawText(x - 4, h - mb + 4, bar_w + 8, 14, Qt.AlignmentFlag.AlignCenter, str(yr))
            p.setPen(QC("#e2e8f0"))
            p.drawText(x - 4, y - 14, bar_w + 8, 12, Qt.AlignmentFlag.AlignCenter, str(val))


class MissionTimingSection(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._result = None
        self._worker: _MissionTimingWorker | None = None
        self._cache: dict = {}
        self._build()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_site_selector()
        self._prefill_month_from_analysis()

    def on_project_changed(self) -> None:
        self._refresh_site_selector()

    def _refresh_site_selector(self) -> None:
        from ui.widgets.project_site_selector import refresh_project_site_selector
        refresh_project_site_selector(self.mw, self._site_combo, self._site_name_lbl)

    def _selected_site(self):
        from ui.widgets.project_site_selector import selected_project_site
        return selected_project_site(self.mw, self._site_combo)

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        title = QLabel("Mission Timing")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #f1f5f9;")
        root.addWidget(title)

        subtitle = QLabel(
            "For a launch month, analyse ERA5 daily history over N years to find "
            "consecutive all-criteria GO windows and typical start periods."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #94a3b8; font-size: 9pt;")
        root.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setSpacing(14)

        ctrl = QGroupBox("Analysis Settings")
        form = QFormLayout(ctrl)
        form.setSpacing(8)

        self._site_name_lbl = QLabel("No project site")
        self._site_name_lbl.setStyleSheet("color: #fde68a; font-weight: 600;")
        self._site_combo = QComboBox()
        self._site_combo.setMinimumWidth(280)
        self._site_combo.setStyleSheet(
            "QComboBox { background: #1a2233; color: #e2e8f0; border: 1px solid #374151;"
            " border-radius: 3px; padding: 2px 8px; }"
            "QComboBox QAbstractItemView { background: #1a2233; color: #e2e8f0; }"
        )
        self._site_combo.setVisible(False)
        site_row = QHBoxLayout()
        site_row.addWidget(self._site_name_lbl, 1)
        site_row.addWidget(self._site_combo, 1)
        form.addRow("Site:", site_row)

        from ui.widgets.project_site_selector import wire_project_site_combo
        wire_project_site_combo(self.mw, self._site_combo, lambda: None)

        self._month_combo = QComboBox()
        for i, mo in enumerate(_MO, 1):
            self._month_combo.addItem(mo, i)
        self._month_combo.setCurrentIndex(5)
        form.addRow("Launch month:", self._month_combo)

        self._duration_spin = QSpinBox()
        self._duration_spin.setRange(1, 15)
        self._duration_spin.setValue(5)
        self._duration_spin.setSuffix(" years")
        form.addRow("Duration:", self._duration_spin)

        note = QLabel(
            "Duration = number of past calendar years of that month to analyse "
            "(ends at last complete year). First run downloads ERA5 hourly data."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #64748b; font-size: 8pt;")
        form.addRow("", note)

        layout.addWidget(ctrl)

        run_row = QHBoxLayout()
        self._run_btn = QPushButton("Run Mission Timing Analysis")
        self._run_btn.setStyleSheet(_BTN_PRIMARY)
        self._run_btn.clicked.connect(self._on_run)
        run_row.addWidget(self._run_btn)
        run_row.addStretch()
        layout.addLayout(run_row)

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
        layout.addWidget(self._progress)

        self._status_lbl = QLabel("")
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setStyleSheet("color: #94a3b8; font-size: 8pt;")
        layout.addWidget(self._status_lbl)

        self._summary_group = QGroupBox("Planning Summary")
        sg = QVBoxLayout(self._summary_group)
        self._summary_lbl = QLabel("Run an analysis to see mission window statistics.")
        self._summary_lbl.setWordWrap(True)
        self._summary_lbl.setStyleSheet("color: #e2e8f0; font-size: 9pt; line-height: 140%;")
        sg.addWidget(self._summary_lbl)
        layout.addWidget(self._summary_group)

        chart_group = QGroupBox("Max Streak by Year")
        cg = QVBoxLayout(chart_group)
        self._chart = _StreakChart()
        cg.addWidget(self._chart)
        layout.addWidget(chart_group)

        table_group = QGroupBox("Year-by-Year Detail")
        tg = QVBoxLayout(table_group)
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels([
            "Year", "Max streak (days)", "Longest window", "GO days", "# streaks",
        ])
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch,
        )
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        apply_table_colors(self._table)
        self._table.setMinimumHeight(200)
        tg.addWidget(self._table)
        layout.addWidget(table_group)

        layout.addStretch()
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

    def _prefill_month_from_analysis(self) -> None:
        try:
            tab = self.mw.analysis_tab
            profile = getattr(tab, "_profile", None)
            if not profile:
                return
            from modules.m3_probability.engine import best_launch_months
            best = best_launch_months(profile)
            if best:
                month = best[0][0]
                idx = self._month_combo.findData(month)
                if idx >= 0:
                    self._month_combo.setCurrentIndex(idx)
        except Exception:
            pass

    def _thresholds(self) -> dict:
        from config import DEFAULT_THRESHOLDS
        try:
            editor = getattr(self.mw.analysis_tab, "threshold_editor", None)
            if editor is not None:
                return editor.values()
        except Exception:
            pass
        return dict(DEFAULT_THRESHOLDS)

    def _weights(self) -> dict:
        from config import DEFAULT_WEIGHTS
        try:
            tab = self.mw.analysis_tab
            if hasattr(tab, "_active_weights"):
                return tab._active_weights()
        except Exception:
            pass
        return dict(DEFAULT_WEIGHTS)

    def _cache_key(self, site: Site, month: int, duration: int) -> tuple:
        sid = getattr(site, "id", None)
        thr = tuple(sorted(
            (k, round(float(v), 4)) for k, v in self._thresholds().items() if v is not None
        ))
        wts = tuple(sorted(
            (k, round(float(v), 6)) for k, v in self._weights().items() if float(v or 0) > 0
        ))
        return (sid, month, duration, thr, wts)

    def _set_busy(self, msg: str, done: int = -1, total: int = 0) -> None:
        self._status_lbl.setText(msg)
        self._progress.setVisible(True)
        if done < 0 or total <= 0:
            self._progress.setRange(0, 0)
        else:
            self._progress.setRange(0, total)
            self._progress.setValue(min(done, total))
        if hasattr(self.mw, "status"):
            self.mw.status(msg)

    def _clear_busy(self) -> None:
        self._progress.setVisible(False)
        self._progress.setRange(0, 0)

    def _on_run(self) -> None:
        site = self._selected_site()
        if not site or getattr(site, "id", None) is None:
            QMessageBox.warning(
                self, "Site Required",
                "Open a project with at least one saved site, or select a site from the list.",
            )
            return

        month = int(self._month_combo.currentData())
        duration = self._duration_spin.value()
        cache_key = self._cache_key(site, month, duration)
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._apply_result(cached, from_cache=True)
            return

        if self._worker is not None and self._worker.isRunning():
            return

        if duration > 10:
            QMessageBox.information(
                self, "Long Duration",
                f"Analysing {duration} years requires many ERA5 hourly downloads. "
                "First run may take a long time; re-runs use cache.",
            )

        self._run_btn.setEnabled(False)
        self._set_busy(
            "Fetching ERA5 daily data… (first run may take several minutes per year)",
            -1, 0,
        )

        self._worker = _MissionTimingWorker(
            site, month, duration, self._thresholds(), self._weights(),
        )
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.progress.connect(self._on_progress)
        self._worker.start()

    def _on_progress(self, msg: str, done: int, total: int) -> None:
        self._set_busy(msg, done, total)

    def _on_finished(self, result) -> None:
        site = self._selected_site()
        if site:
            key = self._cache_key(
                site,
                int(self._month_combo.currentData()),
                self._duration_spin.value(),
            )
            self._cache[key] = result
        self._apply_result(result, from_cache=False)

    def _on_error(self, msg: str) -> None:
        self._run_btn.setEnabled(True)
        self._clear_busy()
        self._status_lbl.setText(f"Error: {msg}")
        QMessageBox.critical(self, "Mission Timing Error", msg)

    def _apply_result(self, result, from_cache: bool = False) -> None:
        self._result = result
        self._run_btn.setEnabled(True)
        self._clear_busy()

        if from_cache:
            self._status_lbl.setText(
                f"Loaded from cache — {result.month_label} "
                f"({result.year_start}–{result.year_end})."
            )
        else:
            self._status_lbl.setText(
                f"Complete — {result.month_label} analysed over "
                f"{result.duration_years} years ({result.year_start}–{result.year_end})."
            )

        self._summary_lbl.setText(
            f"<b>{result.month_label}</b> · {result.year_start}–{result.year_end} "
            f"({result.duration_years} years)<br><br>"
            f"<b>Avg max consecutive GO streak:</b> {result.avg_max_streak} days<br>"
            f"<b>Overall max streak:</b> {result.max_streak_ever} days<br>"
            f"<b>Avg streak length (all runs):</b> {result.avg_streak_length} days<br>"
            f"<b>Avg GO days/month:</b> {result.avg_go_days} ({result.avg_go_pct}%)<br>"
            f"<b>Avg # streaks/year:</b> {result.avg_streaks_per_year}<br>"
            f"<b>Typical start:</b> {result.typical_start_label}<br><br>"
            f"<span style='color:#94a3b8;'>{result.planning_hint}</span>"
        )

        years = [y.year for y in result.years]
        maxs = [y.max_streak for y in result.years]
        self._chart.set_data(years, maxs)

        self._table.setRowCount(0)
        self._table.setRowCount(len(result.years))
        for row, ys in enumerate(result.years):
            vals = [
                str(ys.year),
                str(ys.max_streak),
                ys.longest_window,
                f"{ys.go_days}/{ys.total_days}",
                str(ys.num_streaks),
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setForeground(QColor("#f1f5f9"))
                self._table.setItem(row, col, item)

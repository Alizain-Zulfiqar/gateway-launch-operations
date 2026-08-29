"""
ui/sections/settings.py -- Settings tab: 4-tab interface for application configuration.

Tab 1 -- Data Sources  : ERA5 .cdsapirc status, NCEI timeout, NDBC radius
Tab 2 -- Voyage Defaults: editable voyage economics + [Save as defaults]
Tab 3 -- Display       : GO threshold slider, colour scheme note
Tab 4 -- About         : app info and DB path
"""
import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFormLayout, QFrame, QTabWidget, QDoubleSpinBox,
    QSpinBox, QSlider, QComboBox, QMessageBox, QScrollArea, QProgressBar,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap


_BTN_PRIMARY = (
    "QPushButton {"
    "  background: #0F2850; color: white;"
    "  border-radius: 4px; padding: 6px 20px; font-weight: bold;"
    "}"
    "QPushButton:hover    { background: #1A4080; }"
    "QPushButton:disabled { background: #B0B8C8; }"
)
_BTN_GREEN = (
    "QPushButton {"
    "  background: #1A6030; color: white;"
    "  border-radius: 4px; padding: 6px 16px; font-weight: bold;"
    "}"
    "QPushButton:hover { background: #2A8040; }"
)

_STATUS_BASE = "border-radius: 4px; padding: 10px 14px; font-size: 13px;"


# ── Background worker for ERA5 auth check ────────────────────────────────────

class _AuthWorker(QThread):
    finished = pyqtSignal(bool, str)

    def run(self):
        from modules.m2_weather.era5 import check_era5_auth
        ok, msg = check_era5_auth()
        self.finished.emit(ok, msg)


# ── Background worker for NCEI history download (Set 41) ────────────────────

from modules.m2_weather.ncei_download import NceiDownloadWorker as _NceiDownloadWorker


# ── Tab 1: Data Sources ───────────────────────────────────────────────────────

class _DataSourcesTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw      = main_window
        self._worker = None
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(14)

        # ERA5 group
        era5_group  = QGroupBox("ERA5 / Copernicus CDS Authentication")
        era5_layout = QVBoxLayout(era5_group)
        era5_layout.setSpacing(10)
        era5_layout.setContentsMargins(14, 14, 14, 14)

        info = QLabel(
            "ERA5 swell data is fetched using credentials stored in "
            "<b>~\\.cdsapirc</b>. No API key is stored in this application.<br>"
            "Register and download <b>.cdsapirc</b> from "
            "<a href='https://cds.climate.copernicus.eu'>cds.climate.copernicus.eu</a>, "
            "then place it in your home directory."
        )
        info.setWordWrap(True)
        info.setOpenExternalLinks(True)
        info.setStyleSheet("color: #404040;")
        era5_layout.addWidget(info)

        form = QFormLayout()
        form.setSpacing(8)
        rc_path     = Path.home() / ".cdsapirc"
        file_exists = rc_path.exists()

        self.rc_path_label = QLabel(str(rc_path))
        self.rc_path_label.setStyleSheet(
            "font-family: Consolas, monospace; color: #303050;"
        )
        form.addRow("Expected path:", self.rc_path_label)

        self.rc_exists_label = QLabel("File found" if file_exists else "File not found")
        self.rc_exists_label.setStyleSheet(
            f"color: {'#1A6030' if file_exists else '#A03030'}; font-weight: bold;"
        )
        form.addRow("File status:", self.rc_exists_label)
        era5_layout.addLayout(form)

        self.status_banner = QLabel("")
        self.status_banner.setWordWrap(True)
        self.status_banner.setVisible(False)
        era5_layout.addWidget(self.status_banner)

        btn_row = QHBoxLayout()
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.setMinimumHeight(34)
        self.test_btn.setStyleSheet(_BTN_PRIMARY)
        self.test_btn.clicked.connect(self._test_connection)
        btn_row.addWidget(self.test_btn)
        btn_row.addStretch()
        era5_layout.addLayout(btn_row)
        root.addWidget(era5_group)

        # NCEI group. NDBC search radius moved to the NDBC tab itself (Set 36,
        # item 24) — it was previously only settable here, disconnected from
        # where it's actually used, and the NDBC tab's station search never
        # even read this setting (always used the 200.0 NM class default
        # regardless of what was saved here — item 23's real root cause).
        net_group  = QGroupBox("Network & Search Settings")
        net_layout = QFormLayout(net_group)
        net_layout.setSpacing(10)
        net_layout.setContentsMargins(14, 14, 14, 14)

        try:
            from core.settings import get_int
            _timeout = get_int("ncei_timeout_s", 30)
        except Exception:
            _timeout = 30

        self.ncei_timeout_spin = QSpinBox()
        self.ncei_timeout_spin.setRange(5, 120)
        self.ncei_timeout_spin.setValue(_timeout)
        self.ncei_timeout_spin.setSuffix(" s")
        net_layout.addRow("NCEI request timeout:", self.ncei_timeout_spin)

        save_row = QHBoxLayout()
        save_btn = QPushButton("Save Network Settings")
        save_btn.setStyleSheet(_BTN_PRIMARY)
        save_btn.clicked.connect(self._save_network)
        save_row.addWidget(save_btn)
        save_row.addStretch()
        net_layout.addRow("", save_row)
        root.addWidget(net_group)

        # NCEI historical data cache (Set 41) — downloads once, stores
        # locally in ncei_monthly_cache, so Historical-mode analysis runs
        # never pay the ~130s/month live NCEI query cost after this.
        cache_group  = QGroupBox("NCEI Historical Data Cache")
        cache_layout = QVBoxLayout(cache_group)
        cache_layout.setSpacing(10)
        cache_layout.setContentsMargins(14, 14, 14, 14)

        cache_info = QLabel(
            "Pre-downloads NCEI wind/wave/swell data for a site so Analysis "
            "runs use the cache instead of a live NCEI query (~130 seconds "
            "<i>per month</i> — this is NCEI's own query cost, not "
            "something this app controls). A 5-year download takes roughly "
            "2 hours; it can be cancelled and resumed later (already-cached "
            "months are skipped automatically)."
        )
        cache_info.setWordWrap(True)
        cache_info.setStyleSheet("color: #404040;")
        cache_layout.addWidget(cache_info)

        cache_form = QFormLayout()
        cache_form.setSpacing(8)

        self.ncei_site_combo = QComboBox()
        self._reload_ncei_sites()
        cache_form.addRow("Site:", self.ncei_site_combo)

        import datetime
        this_year = datetime.datetime.now().year
        self.ncei_dl_year_start = QSpinBox()
        self.ncei_dl_year_start.setRange(1960, this_year)
        self.ncei_dl_year_start.setValue(max(1960, this_year - 5))
        cache_form.addRow("From year:", self.ncei_dl_year_start)

        self.ncei_dl_year_end = QSpinBox()
        self.ncei_dl_year_end.setRange(1960, this_year)
        self.ncei_dl_year_end.setValue(this_year)
        cache_form.addRow("To year:", self.ncei_dl_year_end)

        cache_layout.addLayout(cache_form)

        dl_btn_row = QHBoxLayout()
        self.ncei_download_btn = QPushButton("Download NCEI History")
        self.ncei_download_btn.setStyleSheet(_BTN_PRIMARY)
        self.ncei_download_btn.clicked.connect(self._start_ncei_download)
        dl_btn_row.addWidget(self.ncei_download_btn)

        self.ncei_cancel_btn = QPushButton("Cancel")
        self.ncei_cancel_btn.setVisible(False)
        self.ncei_cancel_btn.clicked.connect(self._cancel_ncei_download)
        dl_btn_row.addWidget(self.ncei_cancel_btn)
        dl_btn_row.addStretch()
        cache_layout.addLayout(dl_btn_row)

        self.ncei_progress = QProgressBar()
        self.ncei_progress.setVisible(False)
        cache_layout.addWidget(self.ncei_progress)

        self.ncei_dl_status = QLabel("")
        self.ncei_dl_status.setWordWrap(True)
        self.ncei_dl_status.setStyleSheet("color: #404040; font-size: 11px;")
        cache_layout.addWidget(self.ncei_dl_status)

        root.addWidget(cache_group)
        root.addStretch()

        self._ncei_worker: "_NceiDownloadWorker | None" = None

    def _reload_ncei_sites(self) -> None:
        self.ncei_site_combo.clear()
        try:
            from core.database import get_connection
            conn = get_connection()
            rows = conn.execute(
                "SELECT id, name, lat, lon, bbox_nm FROM sites ORDER BY name"
            ).fetchall()
            conn.close()
        except Exception:
            rows = []
        for r in rows:
            self.ncei_site_combo.addItem(
                r["name"] or f"Site {r['id']}",
                userData=(r["lat"], r["lon"], r["bbox_nm"] or 25.0),
            )
        active_site = getattr(self.mw, "site", None)
        if active_site is not None:
            idx = self.ncei_site_combo.findText(active_site.name or "")
            if idx >= 0:
                self.ncei_site_combo.setCurrentIndex(idx)

    def _start_ncei_download(self) -> None:
        if self.ncei_site_combo.count() == 0:
            QMessageBox.warning(
                self, "No Sites",
                "No saved sites found. Save a site in the Sites section first."
            )
            return
        lat, lon, bbox_nm = self.ncei_site_combo.currentData()
        year_start = self.ncei_dl_year_start.value()
        year_end = self.ncei_dl_year_end.value()
        if year_start > year_end:
            QMessageBox.warning(self, "Invalid Range", "From year must be ≤ To year.")
            return

        self.ncei_download_btn.setEnabled(False)
        self.ncei_cancel_btn.setVisible(True)
        self.ncei_progress.setVisible(True)
        self.ncei_progress.setValue(0)
        self.ncei_dl_status.setText("Starting…")

        self._ncei_worker = _NceiDownloadWorker(lat, lon, bbox_nm, year_start, year_end)
        self._ncei_worker.progress.connect(self._on_ncei_progress)
        self._ncei_worker.finished.connect(self._on_ncei_finished)
        self._ncei_worker.error.connect(self._on_ncei_error)
        self._ncei_worker.start()

    def _cancel_ncei_download(self) -> None:
        if self._ncei_worker is not None:
            self._ncei_worker.cancel()
            self.ncei_dl_status.setText("Cancelling…")

    def _on_ncei_progress(self, done: int, total: int, newly_fetched: int) -> None:
        self.ncei_progress.setMaximum(total)
        self.ncei_progress.setValue(done)
        self.ncei_dl_status.setText(
            f"Month {done} of {total} — {newly_fetched} newly fetched this run"
        )

    def _on_ncei_finished(self, newly_fetched: int, already_cached: int) -> None:
        self.ncei_download_btn.setEnabled(True)
        self.ncei_cancel_btn.setVisible(False)
        self.ncei_dl_status.setText(
            f"Done — {newly_fetched} month(s) newly cached, "
            f"{already_cached} already cached (skipped)."
        )
        self.mw.status("NCEI history download complete.")

    def _on_ncei_error(self, message: str) -> None:
        self.ncei_download_btn.setEnabled(True)
        self.ncei_cancel_btn.setVisible(False)
        self.ncei_progress.setVisible(False)
        QMessageBox.critical(self, "Download Error", message)

    def _test_connection(self) -> None:
        self.test_btn.setEnabled(False)
        self.test_btn.setText("Testing...")
        self.status_banner.setVisible(False)
        self._worker = _AuthWorker()
        self._worker.finished.connect(self._on_auth_result)
        self._worker.start()

    def _on_auth_result(self, ok: bool, message: str) -> None:
        self.test_btn.setEnabled(True)
        self.test_btn.setText("Test Connection")
        style = (
            _STATUS_BASE
            + ("background: #D8F0D8; border: 1px solid #5AAA5A; color: #1A5020;"
               if ok else
               "background: #F8D8D8; border: 1px solid #C05050; color: #801010;")
        )
        self.status_banner.setStyleSheet(style)
        self.status_banner.setText(message)
        self.status_banner.setVisible(True)

        rc_path     = Path.home() / ".cdsapirc"
        file_exists = rc_path.exists()
        self.rc_exists_label.setText("File found" if file_exists else "File not found")
        self.rc_exists_label.setStyleSheet(
            f"color: {'#1A6030' if file_exists else '#A03030'}; font-weight: bold;"
        )
        self.mw.status("ERA5: Connected" if ok else
                       "ERA5: Authentication failed -- see Settings > Data Sources")

    def _save_network(self) -> None:
        try:
            from core.settings import set_setting
            set_setting("ncei_timeout_s",  str(self.ncei_timeout_spin.value()))
            self.mw.status("Network settings saved.")
        except Exception as exc:
            QMessageBox.warning(self, "Save Failed", str(exc))


# ── Tab 2: Voyage Defaults ────────────────────────────────────────────────────

class _VoyageDefaultsTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(14)

        info = QLabel(
            "Voyage cost parameters now live on the <b>Ports</b> page, because "
            "the route itself (which ports, how many days at each) is part of "
            "the same parameter set and only makes sense alongside the port "
            "search."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #404040;")
        root.addWidget(info)

        group = QGroupBox("Voyage Economics")
        gl = QVBoxLayout(group)
        gl.setSpacing(10)
        gl.setContentsMargins(14, 14, 14, 14)

        summary = QLabel("")
        summary.setWordWrap(True)
        summary.setTextFormat(Qt.TextFormat.RichText)
        summary.setStyleSheet("color: #404040;")
        self._summary = summary
        gl.addWidget(summary)

        open_btn = QPushButton("Open Voyage Cost Settings…")
        open_btn.setStyleSheet(_BTN_GREEN)
        open_btn.setMinimumHeight(34)
        open_btn.clicked.connect(self._open_editor)
        row = QHBoxLayout()
        row.addWidget(open_btn)
        row.addStretch()
        gl.addLayout(row)

        root.addWidget(group)
        root.addStretch()
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        try:
            from modules.m4_ports.voyage import load_params
            p = load_params()
        except Exception:
            self._summary.setText("Current parameters could not be read.")
            return

        deployed = [v.name for v in p.vessels if v.deployed]
        fees_total = sum(pf.total_usd for pf in p.port_fees)
        self._summary.setText(
            f"Current settings — transit speed <b>{p.speed_kts:g} kts</b>, "
            f"<b>{p.launches}</b> launch(es) per voyage, "
            f"vessels deployed: <b>{', '.join(deployed) or 'none'}</b>, "
            f"port fees entered: <b>${fees_total:,.0f}</b>.<br>"
            f"Total voyage cost = charter hire (per vessel) + port fees + fuel."
        )

    def _open_editor(self) -> None:
        from ui.dialogs.voyage_cost_editor import VoyageCostEditorDialog

        dlg = VoyageCostEditorDialog(
            site=getattr(self.mw, "site", None), parent=self
        )
        if dlg.exec() == VoyageCostEditorDialog.DialogCode.Accepted:
            self.mw.status("Voyage cost parameters saved.")
            self._refresh_summary()


# ── Tab 3: Display ────────────────────────────────────────────────────────────

class _DisplayTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(14)

        group  = QGroupBox("Display Options")
        form   = QFormLayout(group)
        form.setSpacing(12)
        form.setContentsMargins(14, 14, 14, 14)

        try:
            from core.settings import get_float
            _go = int(get_float("go_threshold", 0.70) * 100)
            _marg = int(get_float("marginal_threshold", 0.50) * 100)
        except Exception:
            _go, _marg = 70, 50

        self._go_label = QLabel(f"{_go}%")
        self._go_label.setStyleSheet("font-weight: bold; color: #86efac; min-width: 36px;")

        self.go_slider = QSlider(Qt.Orientation.Horizontal)
        self.go_slider.setRange(5, 95)
        self.go_slider.setValue(_go)
        self.go_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.go_slider.setTickInterval(5)
        self.go_slider.valueChanged.connect(
            lambda v: self._on_go_changed(v)
        )

        go_row = QHBoxLayout()
        go_row.addWidget(self.go_slider)
        go_row.addWidget(self._go_label)
        form.addRow("GO (minimum %):", go_row)

        self._marg_label = QLabel(f"{_marg}%")
        self._marg_label.setStyleSheet("font-weight: bold; color: #fde68a; min-width: 36px;")

        self.marg_slider = QSlider(Qt.Orientation.Horizontal)
        self.marg_slider.setRange(5, 90)
        self.marg_slider.setValue(min(_marg, max(5, _go - 1)))
        self.marg_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.marg_slider.setTickInterval(5)
        self.marg_slider.valueChanged.connect(
            lambda v: self._on_marg_changed(v)
        )

        marg_row = QHBoxLayout()
        marg_row.addWidget(self.marg_slider)
        marg_row.addWidget(self._marg_label)
        form.addRow("MARGINAL (minimum %):", marg_row)

        self._nogo_label = QLabel(f"< {_marg}%")
        self._nogo_label.setStyleSheet("font-weight: bold; color: #fca5a5;")
        form.addRow("NO-GO (below %):", self._nogo_label)

        self.scheme_combo = QComboBox()
        self.scheme_combo.addItems(["Default (Navy / Green / Amber / Red)", "High-contrast"])
        form.addRow("Colour scheme:", self.scheme_combo)

        root.addWidget(group)

        save_row = QHBoxLayout()
        save_btn = QPushButton("Save Display Settings")
        save_btn.setStyleSheet(_BTN_PRIMARY)
        save_btn.clicked.connect(self._save)
        save_row.addWidget(save_btn)
        save_row.addStretch()
        root.addLayout(save_row)

        root.addWidget(QLabel(
            "<i>Colour scheme changes take effect after restarting the application.</i>"
        ))
        root.addStretch()

    def _on_go_changed(self, v: int) -> None:
        self._go_label.setText(f"{v}%")
        if self.marg_slider.value() >= v:
            self.marg_slider.blockSignals(True)
            self.marg_slider.setValue(max(5, v - 1))
            self.marg_slider.blockSignals(False)
            self._marg_label.setText(f"{self.marg_slider.value()}%")
        self._nogo_label.setText(f"< {self.marg_slider.value()}%")

    def _on_marg_changed(self, v: int) -> None:
        cap = self.go_slider.value() - 1
        if v >= self.go_slider.value():
            v = max(5, cap)
            self.marg_slider.blockSignals(True)
            self.marg_slider.setValue(v)
            self.marg_slider.blockSignals(False)
        self._marg_label.setText(f"{v}%")
        self._nogo_label.setText(f"< {v}%")

    def _save(self) -> None:
        try:
            from core.settings import set_setting
            go = self.go_slider.value() / 100.0
            marg = min(self.marg_slider.value() / 100.0, go - 0.01)
            set_setting("go_threshold", str(go))
            set_setting("marginal_threshold", str(marg))
            self.mw.status(
                f"Display settings saved  (GO ≥{self.go_slider.value()}%, "
                f"MARGINAL ≥{int(marg * 100)}%, NO-GO <{int(marg * 100)}%)."
            )
        except Exception as exc:
            QMessageBox.warning(self, "Save Failed", str(exc))


# ── Tab 4: About ──────────────────────────────────────────────────────────────

def _lbl(text: str, color: str = "#94a3b8", size: int = 10,
         bold: bool = False, align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft) -> QLabel:
    lbl = QLabel(text)
    weight = "font-weight: 600;" if bold else ""
    lbl.setStyleSheet(f"color: {color}; font-size: {size}px; {weight} background: transparent;")
    lbl.setAlignment(align)
    lbl.setWordWrap(True)
    return lbl


class _AboutTab(QWidget):
    def __init__(self):
        super().__init__()
        self._build()

    def _build(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        root = QVBoxLayout(content)
        root.setContentsMargins(24, 20, 24, 24)
        root.setSpacing(10)

        # ── Logo ─────────────────────────────────────────────────────────────
        from config import LOGO_PATH
        logo_lbl = QLabel()
        logo_lbl.setStyleSheet("background: transparent;")
        pixmap = QPixmap(str(LOGO_PATH))
        if not pixmap.isNull():
            scaled = pixmap.scaledToWidth(280, Qt.TransformationMode.SmoothTransformation)
            logo_lbl.setPixmap(scaled)
        else:
            logo_lbl.setText("SeagateSpace")
            logo_lbl.setStyleSheet(
                "color: #f1f5f9; font-size: 22px; font-weight: 700; background: transparent;"
            )
        logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(logo_lbl)
        root.addSpacing(6)

        root.addWidget(_lbl("Gateway Launch Operations", color="#f1f5f9", size=16,
                            bold=True, align=Qt.AlignmentFlag.AlignCenter))
        root.addWidget(_lbl("Site Analysis & Mission Planning", color="#94a3b8", size=12,
                            align=Qt.AlignmentFlag.AlignCenter))
        root.addWidget(_lbl("v0.1.0", color="#64748b", size=11,
                            align=Qt.AlignmentFlag.AlignCenter))
        root.addSpacing(8)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #2d3748; border: none;")
        root.addWidget(sep)
        root.addSpacing(8)

        # ── Details ───────────────────────────────────────────────────────────
        def _row(label: str, value: str):
            row_w = QWidget()
            row_w.setStyleSheet("background: transparent;")
            hl = QHBoxLayout(row_w)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(8)
            key_lbl = QLabel(label)
            key_lbl.setFixedWidth(130)
            key_lbl.setStyleSheet(
                "color: #f1f5f9; font-size: 10px; font-weight: 600; background: transparent;"
            )
            val_lbl = QLabel(value)
            val_lbl.setStyleSheet("color: #94a3b8; font-size: 10px; background: transparent;")
            val_lbl.setWordWrap(True)
            hl.addWidget(key_lbl)
            hl.addWidget(val_lbl, 1)
            root.addWidget(row_w)

        _row("Developed for:", "Seagate Space Corporation")
        _row("Purpose:", "Offshore launch site analysis and maritime mission planning")
        _row("Platform:", "Gateway Series (S, X, XL) — Semi-submersible DP hull class")
        _row("ABS AIP:", "December 2025")
        _row("DB path:", _db_path())
        root.addSpacing(10)

        root.addWidget(_lbl("Data sources:", color="#f1f5f9", size=10, bold=True))
        for src in [
            "NOAA ICOADS C00606 — marine climatology",
            "NOAA NDBC — real-time buoy observations",
            "NOAA NCEI — historical marine data API",
            "ERA5 (ECMWF) — wave reanalysis",
            "WaveWatch III (NOAA NCEP) — wave hindcast",
            "NGA World Port Index — port database",
        ]:
            root.addWidget(_lbl(f"  •  {src}", color="#94a3b8", size=10))
        root.addSpacing(10)

        root.addWidget(_lbl("Coordinate convention:", color="#f1f5f9", size=10, bold=True))
        root.addWidget(_lbl("  •  +Latitude = North   −Latitude = South", color="#94a3b8", size=10))
        root.addWidget(_lbl("  •  +Longitude = East   −Longitude = West", color="#94a3b8", size=10))
        root.addWidget(_lbl("  •  WGS-84 decimal degrees throughout", color="#94a3b8", size=10))
        root.addStretch()

        scroll.setWidget(content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)


# ── Settings tab (outer shell, 4 inner tabs) ──────────────────────────────────

class SettingsTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        title = QLabel("Settings")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #0F2850;")
        root.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(_DataSourcesTab(self.mw),    "  Data Sources  ")
        tabs.addTab(_VoyageDefaultsTab(self.mw), "  Voyage Costs  ")
        tabs.addTab(_DisplayTab(self.mw),        "  Display  ")
        tabs.addTab(_AboutTab(),                 "  About  ")
        root.addWidget(tabs)


# ── Utility ───────────────────────────────────────────────────────────────────

def _db_path() -> str:
    try:
        from config import DB_PATH
        return str(DB_PATH)
    except Exception:
        return "--"

"""
ui/site_tab.py -- Tab 1: Site coordinates, vehicle, and platform selection.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QDoubleSpinBox, QComboBox, QPushButton, QGroupBox,
)
from PyQt6.QtCore import Qt

from core.models import Site


_BTN_PRIMARY = (
    "QPushButton {"
    "  background: #0F2850; color: white;"
    "  border-radius: 4px; padding: 6px 20px; font-weight: bold;"
    "}"
    "QPushButton:hover { background: #1A4080; }"
    "QPushButton:disabled { background: #B0B8C8; }"
)

_INFO_BOX = (
    "background: #F0F4FF; border: 1px solid #BCC8E0;"
    "border-radius: 4px; padding: 8px; color: #303050;"
)


class SiteTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # Title
        title = QLabel("Site & Vehicle Configuration")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #0F2850;")
        root.addWidget(title)

        subtitle = QLabel(
            "Enter the proposed launch site coordinates, then select the vehicle "
            "and Gateway platform variant.  Click Apply to update all tabs."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #505050;")
        root.addWidget(subtitle)

        # ── Coordinates ───────────────────────────────────────────────────────
        coord_group = QGroupBox("Launch Site Coordinates  (WGS-84 decimal degrees)")
        coord_form  = QFormLayout(coord_group)
        coord_form.setSpacing(10)
        coord_form.setContentsMargins(14, 14, 14, 14)

        self.lat_spin = QDoubleSpinBox()
        self.lat_spin.setRange(-90.0, 90.0)
        self.lat_spin.setDecimals(4)
        self.lat_spin.setValue(28.5)
        self.lat_spin.setSuffix("   (+N / -S)")
        self.lat_spin.setMinimumWidth(240)
        coord_form.addRow("Latitude:", self.lat_spin)

        self.lon_spin = QDoubleSpinBox()
        self.lon_spin.setRange(-180.0, 180.0)
        self.lon_spin.setDecimals(4)
        self.lon_spin.setValue(-80.6)
        self.lon_spin.setSuffix("   (+E / -W)")
        self.lon_spin.setMinimumWidth(240)
        coord_form.addRow("Longitude:", self.lon_spin)

        root.addWidget(coord_group)

        # ── Vehicle & Platform ────────────────────────────────────────────────
        vp_group = QGroupBox("Vehicle && Platform")
        vp_form  = QFormLayout(vp_group)
        vp_form.setSpacing(10)
        vp_form.setContentsMargins(14, 14, 14, 14)

        self.vehicle_combo = QComboBox()
        for v in self.mw.vehicles:
            self.vehicle_combo.addItem(v.name)
        self.vehicle_combo.setCurrentIndex(0)
        self.vehicle_combo.currentIndexChanged.connect(self._on_vehicle_changed)
        vp_form.addRow("Launch vehicle:", self.vehicle_combo)

        self.platform_combo = QComboBox()
        for p in self.mw.platforms:
            self.platform_combo.addItem(p.name)
        self.platform_combo.setCurrentIndex(1)   # Gateway X default
        self.platform_combo.currentIndexChanged.connect(self._on_platform_changed)
        vp_form.addRow("Gateway platform:", self.platform_combo)

        root.addWidget(vp_group)

        # ── Vehicle info card ─────────────────────────────────────────────────
        self.vehicle_info = QLabel()
        self.vehicle_info.setWordWrap(True)
        self.vehicle_info.setStyleSheet(_INFO_BOX)
        root.addWidget(self.vehicle_info)

        # ── Apply button ──────────────────────────────────────────────────────
        apply_row = QHBoxLayout()
        self.apply_btn = QPushButton("Apply Site && Vehicle")
        self.apply_btn.setMinimumHeight(36)
        self.apply_btn.setStyleSheet(_BTN_PRIMARY)
        self.apply_btn.clicked.connect(self._apply)
        apply_row.addWidget(self.apply_btn)
        apply_row.addStretch()
        root.addLayout(apply_row)

        # ── Status label ──────────────────────────────────────────────────────
        self.status_label = QLabel("No site set.")
        self.status_label.setStyleSheet("color: #707070; font-style: italic;")
        root.addWidget(self.status_label)

        root.addStretch()

        # Populate info card for the default vehicle selection
        self._update_vehicle_info()

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_vehicle_changed(self, idx: int) -> None:
        self.mw.vehicle = self.mw.vehicles[idx]
        self._update_vehicle_info()

    def _on_platform_changed(self, idx: int) -> None:
        self.mw.platform = self.mw.platforms[idx]

    def _update_vehicle_info(self) -> None:
        v = self.mw.vehicle
        self.vehicle_info.setText(
            f"<b>{v.name}</b> &nbsp; ({v.vehicle_class} / {v.recovery_mode})<br>"
            f"Max wind: <b>{v.max_wind_kts} kts</b> &nbsp;|&nbsp; "
            f"Max gust: <b>{v.max_gust_kts} kts</b> &nbsp;|&nbsp; "
            f"Max Hs: <b>{v.max_hs_m} m</b> &nbsp;|&nbsp; "
            f"Max swell height: <b>{v.max_swell_ht_m} m</b> &nbsp;|&nbsp; "
            f"Max swell period: <b>{v.max_swell_period_s} s</b>"
        )

    def _apply(self) -> None:
        lat = self.lat_spin.value()
        lon = self.lon_spin.value()
        try:
            self.mw.site = Site(
                lat=lat, lon=lon,
                name=f"Site {abs(lat):.4f}{'N' if lat >= 0 else 'S'} "
                     f"{abs(lon):.4f}{'E' if lon >= 0 else 'W'}"
            )
        except ValueError as exc:
            self.status_label.setText(f"Coordinate error: {exc}")
            self.status_label.setStyleSheet("color: #C00000;")
            return

        self.status_label.setText(f"Active site: {self.mw.site.coord_str}")
        self.status_label.setStyleSheet("color: #1A6030; font-weight: bold;")
        self.mw.on_site_changed()

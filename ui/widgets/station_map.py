"""
ui/widgets/station_map.py — Matplotlib-based NDBC station map widget.
No basemap tiles required — draws a lat/lon grid with colored station markers.
"""
from __future__ import annotations

import matplotlib
matplotlib.use("QtAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.lines import Line2D

from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import pyqtSignal


class StationMapWidget(QWidget):
    """Interactive matplotlib canvas showing NDBC stations around a launch site."""

    station_selected = pyqtSignal(str)  # emits station_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.stations: list = []
        self.center_lat = 28.5
        self.center_lon = -80.6
        self.radius_nm  = 200.0
        self.selected_station_id: str | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.fig, self.ax = plt.subplots(figsize=(6, 5), facecolor='#1e2530')
        self.canvas = FigureCanvasQTAgg(self.fig)
        layout.addWidget(self.canvas)

        self.canvas.mpl_connect('button_press_event', self._on_click)
        self._redraw()

    def set_center(self, lat: float, lon: float, radius_nm: float = 200.0) -> None:
        self.center_lat = lat
        self.center_lon = lon
        self.radius_nm  = radius_nm
        self._redraw()

    def set_stations(self, stations: list) -> None:
        self.stations = stations
        self._redraw()

    def _redraw(self) -> None:
        ax = self.ax
        ax.clear()
        ax.set_facecolor('#1e2530')

        deg = self.radius_nm / 60.0 * 1.2
        lat_min = self.center_lat - deg
        lat_max = self.center_lat + deg
        lon_min = self.center_lon - deg
        lon_max = self.center_lon + deg

        ax.set_xlim(lon_min, lon_max)
        ax.set_ylim(lat_min, lat_max)
        ax.set_xlabel('Longitude (°E/W)', color='#94a3b8', fontsize=9)
        ax.set_ylabel('Latitude (°N/S)',  color='#94a3b8', fontsize=9)
        ax.tick_params(colors='#94a3b8', labelsize=8)
        for spine in ax.spines.values():
            spine.set_color('#374151')
        ax.grid(True, color='#374151', linewidth=0.5, alpha=0.5)

        # Radius circle (approximate — degrees are not uniform but close enough)
        circle = plt.Circle(
            (self.center_lon, self.center_lat),
            self.radius_nm / 60.0,
            fill=False, color='#2563eb', linewidth=1.5, linestyle='--',
        )
        ax.add_patch(circle)

        # Center (launch site)
        ax.plot(self.center_lon, self.center_lat,
                marker='*', color='#2563eb', markersize=14, zorder=5)
        lat_d = 'N' if self.center_lat >= 0 else 'S'
        ax.annotate(
            f'  Site\n  {abs(self.center_lat):.2f}°{lat_d}',
            (self.center_lon, self.center_lat),
            color='#93c5fd', fontsize=8,
        )

        # Station markers
        for stn in self.stations:
            if stn.station_id == self.selected_station_id:
                color, marker, size, zorder = '#fde68a', 'D', 10, 6
            elif getattr(stn, 'has_spec', False):
                color, marker, size, zorder = '#86efac', 'o', 8, 4
            else:
                color, marker, size, zorder = '#93c5fd', 'o', 7, 4

            ax.plot(stn.lon, stn.lat,
                    marker=marker, color=color, markersize=size,
                    zorder=zorder, picker=True, pickradius=8)
            ax.annotate(
                f'  {stn.station_id}',
                (stn.lon, stn.lat),
                color='#94a3b8', fontsize=7,
            )

        # Legend
        legend_elements = [
            Line2D([0],[0], marker='*', color='w', markerfacecolor='#2563eb',
                   markersize=10, label='Launch site', linestyle='None'),
            Line2D([0],[0], marker='o', color='w', markerfacecolor='#86efac',
                   markersize=8, label='Station (with .spec)', linestyle='None'),
            Line2D([0],[0], marker='o', color='w', markerfacecolor='#93c5fd',
                   markersize=8, label='Station (met only)', linestyle='None'),
            Line2D([0],[0], marker='D', color='w', markerfacecolor='#fde68a',
                   markersize=8, label='Selected', linestyle='None'),
        ]
        ax.legend(
            handles=legend_elements, loc='lower right',
            facecolor='#2d3748', edgecolor='#374151',
            labelcolor='#94a3b8', fontsize=8,
        )

        count = len(self.stations)
        ax.set_title(
            f'NDBC Stations within {self.radius_nm:.0f} NM'
            + (f'  ({count} found)' if count else '  (no stations loaded)'),
            color='#f1f5f9', fontsize=10, pad=8,
        )

        self.fig.tight_layout()
        self.canvas.draw()

    def _on_click(self, event) -> None:
        if event.inaxes != self.ax or not self.stations:
            return
        click_lon = event.xdata
        click_lat = event.ydata
        if click_lon is None or click_lat is None:
            return

        min_dist = float('inf')
        nearest = None
        for stn in self.stations:
            dist = ((stn.lat - click_lat) ** 2 + (stn.lon - click_lon) ** 2) ** 0.5
            if dist < min_dist:
                min_dist = dist
                nearest = stn

        if nearest and min_dist < 0.5:
            self.selected_station_id = nearest.station_id
            self._redraw()
            self.station_selected.emit(nearest.station_id)

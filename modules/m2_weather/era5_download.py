"""
modules/m2_weather/era5_download.py — Background ERA5 marine cache population.
"""
from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from modules.m2_weather.climatology import climatology_year_range
from modules.m2_weather.era5 import fetch_marine_climatology
from modules.m2_weather.era5_cache import (
    era5_cache_progress,
    era5_fetch_incomplete,
    save_cached_era5_month,
)


class Era5DownloadWorker(QThread):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, lat: float, lon: float, year_start: int, year_end: int):
        super().__init__()
        self._lat = lat
        self._lon = lon
        self._year_start = year_start
        self._year_end = year_end
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            if self._cancelled:
                return
            if not era5_fetch_incomplete(
                self._lat, self._lon, self._year_start, self._year_end,
            ):
                cached, total = era5_cache_progress(
                    self._lat, self._lon, self._year_start, self._year_end,
                )
                self.progress.emit(cached, total)
                self.finished.emit()
                return

            rows = fetch_marine_climatology(
                self._lat, self._lon, self._year_start, self._year_end,
            )
            if self._cancelled:
                return
            if rows:
                for month_start, summary in rows.items():
                    save_cached_era5_month(self._lat, self._lon, month_start, summary)

            cached, total = era5_cache_progress(
                self._lat, self._lon, self._year_start, self._year_end,
            )
            self.progress.emit(cached, total)
            self.finished.emit()
        except Exception as exc:
            self.error.emit(str(exc))


def default_era5_year_range() -> tuple[int, int]:
    return climatology_year_range()

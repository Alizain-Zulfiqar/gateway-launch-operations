"""
modules/m2_weather/ncei_download.py — Background NCEI cache population for operability.

Shared by Settings, Analysis tab, and Quick Analysis tab.
"""
from __future__ import annotations

import calendar
import time
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from core.utils import ncei_bbox_str
from modules.m2_weather.ncei import fetch_wind_history, get_cached_month, save_cached_month


def operability_year_range() -> tuple[int, int]:
    """Rolling last 10 calendar years (charts 11–12), independent of analysis range."""
    from modules.m2_weather.operability import era5_operability_year_range
    return era5_operability_year_range()


def month_has_operability_cache(row: Optional[dict]) -> bool:
    """True when a cache row has operability fields usable for heatmaps."""
    if row is None:
        return False
    return row.get("pct_both_criteria") is not None or row.get("n_fully_operable_days") is not None


def month_needs_fetch(bbox: str, month_start: str) -> bool:
    """True when this bbox+month is missing or lacks operability fields."""
    row = get_cached_month(bbox, month_start)
    if row is None:
        return True
    return not month_has_operability_cache(row)


def operability_cache_progress(bbox: str, year_start: int, year_end: int) -> tuple[int, int]:
    """
    Return (months_complete, months_total) for the operability window.
    Complete = row exists and has operability fields (no live fetch needed).
    """
    total = 0
    complete = 0
    for yr in range(year_start, year_end + 1):
        for mo in range(1, 13):
            total += 1
            month_start = f"{yr}-{mo:02d}-01"
            if not month_needs_fetch(bbox, month_start):
                complete += 1
    return complete, total


def ncei_fetch_incomplete(bbox: str, year_start: int, year_end: int) -> bool:
    complete, total = operability_cache_progress(bbox, year_start, year_end)
    return complete < total


def initial_operability_progress(bbox: str, year_start: int, year_end: int) -> tuple[int, int] | None:
    """Return (done, total) while fetch incomplete, else None."""
    complete, total = operability_cache_progress(bbox, year_start, year_end)
    if complete >= total:
        return None
    return complete, total


class NceiDownloadWorker(QThread):
    """
    Populates ncei_monthly_cache for one site's bbox across a year range.
    Re-fetches months whose row exists but operability fields are NULL.
    """

    progress = pyqtSignal(int, int, int)   # (done, total, newly_fetched)
    finished = pyqtSignal(int, int)        # (newly_fetched, already_cached)
    error = pyqtSignal(str)

    def __init__(
        self,
        lat: float,
        lon: float,
        bbox_nm: float,
        year_start: int,
        year_end: int,
    ):
        super().__init__()
        self._lat = lat
        self._lon = lon
        self._bbox_nm = bbox_nm
        self._year_start = year_start
        self._year_end = year_end
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            bbox = ncei_bbox_str(self._lat, self._lon, self._bbox_nm)
            windows: list[tuple[str, str]] = []
            for yr in range(self._year_start, self._year_end + 1):
                for mo in range(1, 13):
                    last_day = calendar.monthrange(yr, mo)[1]
                    windows.append(
                        (f"{yr}-{mo:02d}-01", f"{yr}-{mo:02d}-{last_day:02d}")
                    )

            total = len(windows)
            newly_fetched = 0
            already_cached = 0

            for i, (start_date, end_date) in enumerate(windows):
                if self._cancelled:
                    break
                if not month_needs_fetch(bbox, start_date):
                    already_cached += 1
                    self.progress.emit(i + 1, total, newly_fetched)
                    continue
                if newly_fetched > 0:
                    time.sleep(1)
                result = fetch_wind_history(
                    lat=self._lat,
                    lon=self._lon,
                    bbox_nm=self._bbox_nm,
                    start_date=start_date,
                    end_date=end_date,
                )
                if result is not None:
                    save_cached_month(bbox, start_date, result)
                    newly_fetched += 1
                self.progress.emit(i + 1, total, newly_fetched)

            self.finished.emit(newly_fetched, already_cached)
        except Exception as exc:
            self.error.emit(str(exc))

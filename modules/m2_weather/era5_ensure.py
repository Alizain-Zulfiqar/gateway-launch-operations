"""
modules/m2_weather/era5_ensure.py — Blocking ERA5 monthly cache ensure for Main Analysis.
"""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import QEventLoop, QThread, pyqtSignal

from modules.m2_weather.era5 import fetch_marine_climatology
from modules.m2_weather.era5_cache import (
    era5_cache_progress,
    era5_month_complete,
    get_cached_era5_month,
    save_cached_era5_month,
)

ProgressCallback = Callable[[int, int, str], None]

_ERA5_AUTH_HINT = (
    "Verify Copernicus CDS credentials (~/.cdsapirc) and use "
    "Settings → Data Sources → Test Connection."
)
_ERA5_FETCH_FAILED = f"ERA5 fetch failed. {_ERA5_AUTH_HINT}"
_ERA5_PARSE_FAILED = (
    "ERA5 data downloaded from Copernicus but could not be parsed into monthly "
    f"wind/wave fields. {_ERA5_AUTH_HINT}"
)


def _years_needing_fetch(lat: float, lon: float, year_start: int, year_end: int) -> list[int]:
    """Return calendar years that still have incomplete cache months."""
    needed = []
    for yr in range(year_start, year_end + 1):
        incomplete = False
        for mo in range(1, 13):
            row = get_cached_era5_month(lat, lon, f"{yr}-{mo:02d}-01")
            if not era5_month_complete(row):
                incomplete = True
                break
        if incomplete:
            needed.append(yr)
    return needed


def ensure_era5_cache(
    lat: float,
    lon: float,
    year_start: int,
    year_end: int,
    *,
    on_progress: ProgressCallback | None = None,
) -> tuple[bool, str | None]:
    """
    Ensure era5_monthly_cache is complete for lat/lon and year range.

    Fetches one Copernicus job per incomplete calendar year (avoids huge
    multi-decade requests that blow up NetCDF merge and CDS queues).

    Returns (ok, error_message).  on_progress(done, total, msg): done=-1 means
    indeterminate (CDS queue wait).
    """
    cached, total = era5_cache_progress(lat, lon, year_start, year_end)
    if on_progress:
        on_progress(cached, total, f"{cached}/{total} months cached")

    if cached >= total and total > 0:
        return True, None

    years = _years_needing_fetch(lat, lon, year_start, year_end)
    last_error: str | None = None

    for i, yr in enumerate(years):
        if on_progress:
            on_progress(
                -1,
                0,
                f"Waiting on Copernicus CDS for {yr} "
                f"(year {i + 1}/{len(years)}; may take several minutes)…",
            )
        try:
            rows = fetch_marine_climatology(lat, lon, yr, yr)
        except Exception as exc:
            last_error = f"{_ERA5_FETCH_FAILED}\n\n{exc}"
            continue

        if not rows:
            last_error = (
                f"ERA5 fetch returned no data for {yr}. {_ERA5_AUTH_HINT}"
            )
            continue

        usable = {k: v for k, v in rows.items() if era5_month_complete(v)}
        if not usable:
            last_error = f"{_ERA5_PARSE_FAILED}\n\nYear {yr} had no complete months."
            continue

        for month_start, summary in usable.items():
            save_cached_era5_month(lat, lon, month_start, summary)

        cached, total = era5_cache_progress(lat, lon, year_start, year_end)
        if on_progress:
            on_progress(cached, total, f"{cached}/{total} months cached (through {yr})")

    cached, total = era5_cache_progress(lat, lon, year_start, year_end)
    if on_progress:
        on_progress(cached, total, "ERA5 cache complete" if cached >= total else
                    f"ERA5 cache incomplete ({cached}/{total})")

    if cached < total:
        return False, last_error or (
            f"ERA5 cache incomplete after fetch ({cached}/{total} months). "
            f"{_ERA5_PARSE_FAILED}"
        )
    return True, None


class _EnsureEra5Worker(QThread):
    progress = pyqtSignal(int, int, str)
    finished_ok = pyqtSignal(bool, str)

    def __init__(self, lat: float, lon: float, year_start: int, year_end: int):
        super().__init__()
        self._lat = lat
        self._lon = lon
        self._year_start = year_start
        self._year_end = year_end

    def run(self) -> None:
        def _cb(done: int, total: int, msg: str) -> None:
            self.progress.emit(done, total, msg)

        ok, err = ensure_era5_cache(
            self._lat,
            self._lon,
            self._year_start,
            self._year_end,
            on_progress=_cb,
        )
        self.finished_ok.emit(ok, err or "")


def ensure_era5_cache_blocking(
    lat: float,
    lon: float,
    year_start: int,
    year_end: int,
    *,
    on_progress: ProgressCallback | None = None,
) -> tuple[bool, str | None]:
    """Run ensure_era5_cache on a worker thread; block until complete."""
    cached, total = era5_cache_progress(lat, lon, year_start, year_end)
    if cached >= total and total > 0:
        if on_progress:
            on_progress(cached, total, f"{cached}/{total} months cached")
        return True, None

    loop = QEventLoop()
    result: list[bool | str] = [False, ""]

    worker = _EnsureEra5Worker(lat, lon, year_start, year_end)

    def _on_progress(done: int, total: int, msg: str) -> None:
        if on_progress:
            on_progress(done, total, msg)

    def _on_finished(ok: bool, err: str) -> None:
        result[0] = ok
        result[1] = err
        loop.quit()

    worker.progress.connect(_on_progress)
    worker.finished_ok.connect(_on_finished)
    worker.start()
    loop.exec()
    worker.wait(5000)

    if result[0]:
        return True, None
    return False, str(result[1]) or _ERA5_FETCH_FAILED

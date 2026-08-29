"""
modules/m2_weather/era5_daily.py — Ensure ERA5 daily cache for Mission Timing.
"""
from __future__ import annotations

import calendar
from datetime import date
from typing import Callable, Optional

from modules.m2_weather.era5 import fetch_marine_hourly_month
from modules.m2_weather.era5_daily_cache import (
    era5_daily_complete,
    era5_daily_duration_progress,
    era5_daily_month_progress,
    get_cached_era5_day,
    save_cached_era5_day,
)

ProgressCallback = Callable[[int, int, str], None]

_ERA5_AUTH_HINT = (
    "Verify Copernicus CDS credentials (~/.cdsapirc) and use "
    "Settings → Data Sources → Test Connection."
)


def mission_timing_year_range(duration_years: int, as_of: date | None = None) -> tuple[int, int]:
    """Last `duration_years` complete calendar years ending at as_of.year - 1."""
    ye = (as_of or date.today()).year - 1
    ys = ye - int(duration_years) + 1
    return ys, ye


def _month_needs_fetch(lat: float, lon: float, year: int, month: int) -> bool:
    cached, total = era5_daily_month_progress(lat, lon, year, month)
    return cached < total


def ensure_era5_daily_month(
    lat: float,
    lon: float,
    year: int,
    month: int,
    *,
    on_progress: ProgressCallback | None = None,
) -> tuple[bool, str | None]:
    """Ensure all days in one calendar month are cached. Returns (ok, error)."""
    cached, total = era5_daily_month_progress(lat, lon, year, month)
    if on_progress:
        on_progress(cached, total, f"{cached}/{total} days cached for {year}-{month:02d}")

    if cached >= total and total > 0:
        return True, None

    if not _month_needs_fetch(lat, lon, year, month):
        return True, None

    if on_progress:
        on_progress(-1, 0, f"Waiting on Copernicus CDS for {year}-{month:02d}…")

    try:
        rows = fetch_marine_hourly_month(lat, lon, year, month)
    except Exception as exc:
        return False, f"ERA5 hourly fetch failed for {year}-{month:02d}. {_ERA5_AUTH_HINT}\n\n{exc}"

    if not rows:
        return False, f"ERA5 hourly returned no data for {year}-{month:02d}. {_ERA5_AUTH_HINT}"

    ndays = calendar.monthrange(year, month)[1]
    saved = 0
    for day in range(1, ndays + 1):
        date_str = f"{year}-{month:02d}-{day:02d}"
        summary = rows.get(date_str)
        if summary and era5_daily_complete(summary):
            save_cached_era5_day(lat, lon, date_str, summary)
            saved += 1
        elif summary:
            save_cached_era5_day(lat, lon, date_str, summary)

    cached, total = era5_daily_month_progress(lat, lon, year, month)
    if on_progress:
        on_progress(cached, total, f"{cached}/{total} days cached for {year}-{month:02d}")

    if cached < total:
        return False, (
            f"ERA5 daily cache incomplete for {year}-{month:02d} "
            f"({cached}/{total} days). {_ERA5_AUTH_HINT}"
        )
    return True, None


def ensure_era5_daily_duration(
    lat: float,
    lon: float,
    calendar_month: int,
    duration_years: int,
    *,
    on_progress: ProgressCallback | None = None,
) -> tuple[bool, str | None]:
    """Ensure daily cache for one calendar month across `duration_years`."""
    ys, ye = mission_timing_year_range(duration_years)
    cached, total = era5_daily_duration_progress(lat, lon, calendar_month, ys, ye)
    if on_progress:
        on_progress(cached, total, f"{cached}/{total} days cached ({ys}–{ye})")

    if cached >= total and total > 0:
        return True, None

    last_error: str | None = None
    years = list(range(ys, ye + 1))
    for i, yr in enumerate(years):
        if not _month_needs_fetch(lat, lon, yr, calendar_month):
            continue

        def _cb(done: int, total: int, msg: str, *, _yr=yr, _i=i) -> None:
            if on_progress:
                on_progress(
                    done, total,
                    f"Year {_yr} ({_i + 1}/{len(years)}): {msg}",
                )

        ok, err = ensure_era5_daily_month(
            lat, lon, yr, calendar_month, on_progress=_cb,
        )
        if not ok:
            last_error = err

    cached, total = era5_daily_duration_progress(lat, lon, calendar_month, ys, ye)
    if on_progress:
        on_progress(
            cached, total,
            "ERA5 daily cache complete" if cached >= total
            else f"ERA5 daily cache incomplete ({cached}/{total})",
        )

    if cached < total:
        return False, last_error or (
            f"ERA5 daily cache incomplete ({cached}/{total} days). {_ERA5_AUTH_HINT}"
        )
    return True, None


def load_daily_month_series(
    lat: float,
    lon: float,
    year: int,
    month: int,
) -> list[dict]:
    """Load cached daily rows for one month (may be partial)."""
    ndays = calendar.monthrange(year, month)[1]
    out = []
    for day in range(1, ndays + 1):
        date_str = f"{year}-{month:02d}-{day:02d}"
        row = get_cached_era5_day(lat, lon, date_str)
        if row is not None:
            out.append({"date": date_str, "day": day, **row})
    return out

"""
modules/m2_weather/era5_daily_cache.py — Local cache for ERA5 daily marine fields.
"""
from __future__ import annotations

import calendar
from typing import Optional

from modules.m2_weather.era5_cache import era5_lat_bucket, era5_lon_bucket

_DAILY_COLUMNS = [
    "ws_mean_kts",
    "wg_max_kts",
    "sh_mean_m",
    "swh_mean_m",
    "swp_mean_s",
    "n_hours",
]

_REQUIRED_FIELDS = ("ws_mean_kts", "wg_max_kts", "sh_mean_m", "swh_mean_m", "swp_mean_s")
_MIN_HOURS = 18


def era5_daily_complete(summary: dict | None) -> bool:
    """True when a cache row has core marine fields and enough hourly samples."""
    if not summary:
        return False
    if int(summary.get("n_hours") or 0) < _MIN_HOURS:
        return False
    return all(summary.get(field) is not None for field in _REQUIRED_FIELDS)


def get_cached_era5_day(lat: float, lon: float, date_str: str) -> Optional[dict]:
    from core.database import get_connection

    lat_b = era5_lat_bucket(lat)
    lon_b = era5_lon_bucket(lon)
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT * FROM era5_daily_cache
            WHERE lat_bucket=? AND lon_bucket=? AND date=?
            """,
            (lat_b, lon_b, date_str),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {col: row[col] for col in _DAILY_COLUMNS}


def save_cached_era5_day(lat: float, lon: float, date_str: str, summary: dict) -> None:
    from core.database import get_connection

    lat_b = era5_lat_bucket(lat)
    lon_b = era5_lon_bucket(lon)
    conn = get_connection()
    try:
        conn.execute(
            f"""
            INSERT INTO era5_daily_cache
                (lat_bucket, lon_bucket, date, {", ".join(_DAILY_COLUMNS)}, fetched_at)
            VALUES (?, ?, ?, {", ".join("?" for _ in _DAILY_COLUMNS)}, CURRENT_TIMESTAMP)
            ON CONFLICT(lat_bucket, lon_bucket, date) DO UPDATE SET
                {", ".join(f"{c}=excluded.{c}" for c in _DAILY_COLUMNS)},
                fetched_at = excluded.fetched_at
            """,
            (
                lat_b,
                lon_b,
                date_str,
                *(summary.get(c) for c in _DAILY_COLUMNS),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def era5_daily_month_progress(
    lat: float,
    lon: float,
    year: int,
    month: int,
) -> tuple[int, int]:
    """Return (cached_days, total_days) for one calendar month."""
    total = calendar.monthrange(year, month)[1]
    cached = 0
    for day in range(1, total + 1):
        date_str = f"{year}-{month:02d}-{day:02d}"
        row = get_cached_era5_day(lat, lon, date_str)
        if era5_daily_complete(row):
            cached += 1
    return cached, total


def era5_daily_duration_progress(
    lat: float,
    lon: float,
    calendar_month: int,
    year_start: int,
    year_end: int,
) -> tuple[int, int]:
    """Return (cached_days, total_days) across all years for one calendar month."""
    cached = 0
    total = 0
    for yr in range(year_start, year_end + 1):
        c, t = era5_daily_month_progress(lat, lon, yr, calendar_month)
        cached += c
        total += t
    return cached, total

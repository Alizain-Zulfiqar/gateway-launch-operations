"""
modules/m2_weather/era5_cache.py — Local cache for ERA5 monthly marine climatology.
"""
from __future__ import annotations

from datetime import date
from typing import Iterator, Optional, Tuple

_CACHE_COLUMNS = [
    "ws_mean_kts",
    "sh_mean_m",
    "swh_mean_m",
    "swp_mean_s",
    "wg_mean_kts",
    "record_count",
]

_REQUIRED_FIELDS = ("ws_mean_kts", "sh_mean_m", "swh_mean_m", "wg_mean_kts")

# Copernicus ERA5 monthly-means products typically lag the calendar by a few
# months. Requiring Dec of the current planning year (year_max = today+1)
# makes ensure_era5_cache report incomplete (e.g. 18/24) and abort analysis.
_ERA5_AVAILABILITY_LAG_MONTHS = 2


def era5_last_available_month(as_of: date | None = None) -> Tuple[int, int]:
    """Latest (year, month) we expect ERA5 monthly-means to cover."""
    d = as_of or date.today()
    y, m = d.year, d.month - _ERA5_AVAILABILITY_LAG_MONTHS
    while m <= 0:
        m += 12
        y -= 1
    return y, m


def iter_era5_expected_months(
    year_start: int,
    year_end: int,
    *,
    as_of: date | None = None,
) -> Iterator[Tuple[int, int]]:
    """Yield (year, month) pairs in range that ERA5 is expected to provide."""
    last_y, last_m = era5_last_available_month(as_of)
    for yr in range(year_start, year_end + 1):
        for mo in range(1, 13):
            if (yr, mo) > (last_y, last_m):
                return
            yield yr, mo


def era5_month_complete(summary: dict | None) -> bool:
    """True when a cache row has the core marine fields Main Analysis needs."""
    if not summary:
        return False
    return all(summary.get(field) is not None for field in _REQUIRED_FIELDS)


def era5_lat_bucket(lat: float) -> float:
    return round(lat * 4) / 4.0


def era5_lon_bucket(lon: float) -> float:
    return round(lon * 4) / 4.0


def get_cached_era5_month(lat: float, lon: float, month_start: str) -> Optional[dict]:
    from core.database import get_connection

    lat_b = era5_lat_bucket(lat)
    lon_b = era5_lon_bucket(lon)
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT * FROM era5_monthly_cache
            WHERE lat_bucket=? AND lon_bucket=? AND month_start=?
            """,
            (lat_b, lon_b, month_start),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {col: row[col] for col in _CACHE_COLUMNS}


def save_cached_era5_month(lat: float, lon: float, month_start: str, summary: dict) -> None:
    from core.database import get_connection

    lat_b = era5_lat_bucket(lat)
    lon_b = era5_lon_bucket(lon)
    conn = get_connection()
    try:
        conn.execute(
            f"""
            INSERT INTO era5_monthly_cache
                (lat_bucket, lon_bucket, month_start, {", ".join(_CACHE_COLUMNS)}, fetched_at)
            VALUES (?, ?, ?, {", ".join("?" for _ in _CACHE_COLUMNS)}, CURRENT_TIMESTAMP)
            ON CONFLICT(lat_bucket, lon_bucket, month_start) DO UPDATE SET
                {", ".join(f"{c}=excluded.{c}" for c in _CACHE_COLUMNS)},
                fetched_at = excluded.fetched_at
            """,
            (
                lat_b,
                lon_b,
                month_start,
                *(summary.get(c) for c in _CACHE_COLUMNS),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def era5_cache_progress(
    lat: float,
    lon: float,
    year_start: int,
    year_end: int,
    *,
    as_of: date | None = None,
) -> tuple[int, int]:
    """Return (cached_complete, expected_total) for months ERA5 should have.

    Future / not-yet-published months (beyond the ERA5 availability lag) are
    excluded from *total* so a 2025–2026 planning range does not demand
    months Copernicus has not released yet.
    """
    expected = list(iter_era5_expected_months(year_start, year_end, as_of=as_of))
    total = len(expected)
    cached = 0
    for yr, mo in expected:
        row = get_cached_era5_month(lat, lon, f"{yr}-{mo:02d}-01")
        if era5_month_complete(row):
            cached += 1
    return cached, total


def era5_fetch_incomplete(lat: float, lon: float, year_start: int, year_end: int) -> bool:
    cached, total = era5_cache_progress(lat, lon, year_start, year_end)
    return total > 0 and cached < total

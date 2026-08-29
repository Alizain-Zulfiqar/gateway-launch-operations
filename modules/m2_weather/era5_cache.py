"""
modules/m2_weather/era5_cache.py — Local cache for ERA5 monthly marine climatology.
"""
from __future__ import annotations

from typing import Optional

_CACHE_COLUMNS = [
    "ws_mean_kts",
    "sh_mean_m",
    "swh_mean_m",
    "swp_mean_s",
    "wg_mean_kts",
    "record_count",
]

_REQUIRED_FIELDS = ("ws_mean_kts", "sh_mean_m", "swh_mean_m", "wg_mean_kts")


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


def era5_cache_progress(lat: float, lon: float, year_start: int, year_end: int) -> tuple[int, int]:
    total = (year_end - year_start + 1) * 12
    cached = 0
    for yr in range(year_start, year_end + 1):
        for mo in range(1, 13):
            row = get_cached_era5_month(lat, lon, f"{yr}-{mo:02d}-01")
            if era5_month_complete(row):
                cached += 1
    return cached, total


def era5_fetch_incomplete(lat: float, lon: float, year_start: int, year_end: int) -> bool:
    cached, total = era5_cache_progress(lat, lon, year_start, year_end)
    return cached < total

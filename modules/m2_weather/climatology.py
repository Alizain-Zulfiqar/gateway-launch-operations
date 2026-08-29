"""
modules/m2_weather/climatology.py — Month-pooled ERA5 climatology.

ERA5 reanalysis monthly means are pooled by calendar month across a selected
year range for Main Analysis charts 1–10 and the probability engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

import numpy as np

from core.models import Site
from modules.m2_weather.era5_cache import era5_cache_progress, get_cached_era5_month
from modules.m2_weather.operability import REF_HS_M, REF_WIND_KTS

CLIMATOLOGY_YEARS = 5
_MONTHS = list(range(1, 13))


def climatology_year_range() -> tuple[int, int]:
    ye = date.today().year
    return ye - (CLIMATOLOGY_YEARS - 1), ye


@dataclass
class MonthlyClimatology:
    years: tuple[int, int] = (0, 0)
    by_month: Dict[int, Dict[str, dict]] = field(default_factory=dict)
    pct_both_by_month: Dict[int, Optional[float]] = field(default_factory=dict)
    era5_coverage: tuple[int, int] = (0, 0)
    ncei_operability_coverage: tuple[int, int] = (0, 0)

    @property
    def window_label(self) -> str:
        ys, ye = self.years
        return f"{ys}–{ye}" if ys and ye else ""


def _pool_era5_month(
    lat: float,
    lon: float,
    calendar_month: int,
    year_start: int,
    year_end: int,
) -> Dict[str, dict]:
    """Mean ERA5 cache values for one calendar month across all years in range."""
    ws_vals: List[float] = []
    sh_vals: List[float] = []
    swh_vals: List[float] = []
    swp_vals: List[float] = []
    wg_vals: List[float] = []

    for yr in range(year_start, year_end + 1):
        month_start = f"{yr}-{calendar_month:02d}-01"
        row = get_cached_era5_month(lat, lon, month_start)
        if row is None:
            continue
        if row.get("ws_mean_kts") is not None:
            ws_vals.append(float(row["ws_mean_kts"]))
        if row.get("sh_mean_m") is not None:
            sh_vals.append(float(row["sh_mean_m"]))
        if row.get("swh_mean_m") is not None:
            swh_vals.append(float(row["swh_mean_m"]))
        if row.get("swp_mean_s") is not None:
            swp_vals.append(float(row["swp_mean_s"]))
        if row.get("wg_mean_kts") is not None:
            wg_vals.append(float(row["wg_mean_kts"]))

    out: Dict[str, dict] = {}
    if ws_vals:
        out["ws"] = {
            "mean": round(float(np.mean(ws_vals)), 2),
            "source": "era5_reanalysis",
            "station_id": None,
        }
    if sh_vals:
        out["sh"] = {
            "mean": round(float(np.mean(sh_vals)), 3),
            "source": "era5_reanalysis",
            "station_id": None,
        }
    if swh_vals:
        out["swh"] = {
            "mean": round(float(np.mean(swh_vals)), 3),
            "source": "era5_reanalysis",
            "station_id": None,
        }
    if swp_vals:
        out["swp"] = {
            "mean": round(float(np.mean(swp_vals)), 3),
            "source": "era5_reanalysis",
            "station_id": None,
        }
    if wg_vals:
        out["wg"] = {
            "mean": round(float(np.mean(wg_vals)), 2),
            "source": "era5_reanalysis",
            "station_id": None,
        }
    return out


def build_monthly_climatology(
    site: Site,
    year_start: int | None = None,
    year_end: int | None = None,
    wind_limit_kts: float = REF_WIND_KTS,
    hs_limit_m: float = REF_HS_M,
) -> MonthlyClimatology:
    """Cache-only month-pooled ERA5 climatology for the given year range."""
    if year_start is None or year_end is None:
        year_start, year_end = climatology_year_range()
    by_month: Dict[int, Dict[str, dict]] = {}

    for mo in _MONTHS:
        by_month[mo] = _pool_era5_month(
            site.lat, site.lon, mo, year_start, year_end,
        )

    return MonthlyClimatology(
        years=(year_start, year_end),
        by_month=by_month,
        pct_both_by_month={},
        era5_coverage=era5_cache_progress(
            site.lat, site.lon, year_start, year_end,
        ),
        ncei_operability_coverage=(0, 0),
    )

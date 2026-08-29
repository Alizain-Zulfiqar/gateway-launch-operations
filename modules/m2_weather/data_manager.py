"""
modules/m2_weather/data_manager.py — Weather data source selection and site summary.

Source hierarchy
----------------
45-day mode:
  Wind (ws, wg, wdV) + Sea state (sh, sdV): nearest NDBC met station (.txt)
  Swell (swh, swp, swdV):                   nearest NDBC station with .spec file
                                             fallback → WW3 ERDDAP (Phase 2)

Historical mode:
  ws, wdV : NCEI Global Marine (ship/buoy observations, 1662–present)
  wg      : icoads_model  (NCEI does not carry gust directly)
  sh, sdV : icoads_model
  swh, swp : ERA5 reanalysis climatology (Phase 2); fallback → icoads_model
  swdV     : icoads_model (ERA5/WW3 provide mean direction, not variance)

Units returned:
  ws, wg  → knots
  sh, swh → metres
  swp     → seconds
  wdV, sdV, swdV → degrees (directional variance — circular std)
"""

import sys
from pathlib import Path
from typing import Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import NDBC_STATION_SEARCH_RADIUS_NM
from core.models import Site
from modules.m2_weather.ndbc import (
    nearest_stations,
    fetch_met_data,
    fetch_spec_data,
    spec_available,
)
from modules.m2_weather.ncei import fetch_wind_history

# ── Parameter → None-valued template ────────────────────────────────────────

_PARAM_NAMES = ["ws", "wg", "sh", "swh", "swp", "wdV", "sdV", "swdV"]


def _model_entry() -> dict:
    return {"mean": None, "p90": None, "source": "icoads_model", "station_id": None}


def _empty_summary() -> dict:
    return {p: _model_entry() for p in _PARAM_NAMES}


# ── Circular directional statistics ─────────────────────────────────────────

def _circular_std_deg(angles_deg) -> Optional[float]:
    """
    Circular standard deviation of a series of bearings (degrees).
    Returns None if the series is empty or contains fewer than 2 valid values.
    """
    arr = np.asarray(angles_deg, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 2:
        return None
    rad = np.deg2rad(arr)
    r = np.sqrt(np.mean(np.sin(rad)) ** 2 + np.mean(np.cos(rad)) ** 2)
    r = min(r, 1.0)
    return float(np.rad2deg(np.sqrt(-2 * np.log(r))))


def _p90(series) -> Optional[float]:
    arr = np.asarray(series, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return None
    return float(np.percentile(arr, 90))


# ── Public API ───────────────────────────────────────────────────────────────

def get_site_weather_summary(
    site: Site,
    mode: str,
    year_start: int = 1960,
    year_end:   int = 2024,
) -> dict:
    """
    Return observed weather statistics for a site keyed by the 8 parameter
    shortnames (ws, wg, sh, swh, swp, wdV, sdV, swdV).

    Each value is a dict:
        mean       : float or None
        p90        : float or None
        source     : 'ndbc_realtime' | 'ncei_global_marine' | 'icoads_model'
        station_id : str or None

    Parameters
    ----------
    site       : Site  — lat/lon and bbox_nm used for station and bbox queries
    mode       : '45day' | 'historical'
    year_start : first year of historical range (historical mode only)
    year_end   : last  year of historical range (historical mode only)

    45-day mode  : Fetches live NDBC data. Parameters without NDBC coverage
                   fall back to source='icoads_model'.
    Historical mode : Populates ws from NCEI Global Marine; wg and all sea/swell
                      parameters remain 'icoads_model' until ERA5 is integrated.
    """
    if mode not in ("45day", "historical"):
        raise ValueError(f"mode must be '45day' or 'historical', got {repr(mode)}")

    if mode == "historical":
        return _fetch_historical(site, year_start, year_end)

    return _fetch_45day(site)


# ── Historical implementation (NCEI) ─────────────────────────────────────────

def _fetch_historical(site: Site, year_start: int, year_end: int) -> dict:
    """
    Populate ws/wdV/sh/sdV from NCEI Global Marine (cache-first, Set 41),
    swh/swp from ERA5/Copernicus, for the given year range (Set 39 —
    sh/sdV/swdV added; see ncei.py's module docstring for the empirical
    field-availability check behind this).

    NCEI enforces a per-request record limit (~10 k rows). A 25 NM bbox
    around a well-observed coastal location can return ~7 k rows per month,
    so even a single calendar-year request exceeds the limit. We batch by
    calendar MONTH and sleep 1 second between LIVE requests only — cached
    months (ncei_monthly_cache, keyed by exact bbox string + month) cost no
    network round-trip at all.

    Live-fetch gate (Set 39, revised after live measurement; Set 41 fixed a
    regression this caused — see below): a live NCEI request measured ~130s
    regardless of which/how many dataTypes were requested (confirmed via a
    direct A/B test — NCEI's query cost scales with date-range/station-day
    count, not field count or bbox size in the ranges tested). This function
    is ALWAYS called from the interactive Analysis flow, so it must never
    silently take minutes: live fetching only happens when the ENTIRE
    requested range is already small (≤ NCEI_MAX_LIVE_MONTHS) — for any
    larger range (e.g. the default 1960-2024), it is cache-only and NEVER
    calls fetch_wind_history() itself, regardless of how many months are
    cached vs. not. (Set 41's first version made the cap apply per-month
    instead of per-range, so even a 65-year request attempted a few live
    fetches before giving up — silently adding minutes to every Historical
    run and to any test exercising it; this cache-existence check is always
    a fast local DB read regardless of range size, so checking the cache for
    every month in a huge range is fine — only the LIVE fetch is gated.)
    The only way to populate the cache for large ranges is the explicit
    "Download NCEI History" action in Settings, which has no such range cap.

    wg (wind gust) is confirmed empirically absent from NCEI Global Marine
    (no gust field exists in this dataset at all, tried both
    WIND_GUST_SPEED and GUST_SPEED against live data). ERA5 is now the
    live historical source for it instead — see _apply_era5_gust() below,
    wired in once Set 42's CDS auth fix made this testable (confirmed live
    2026-07-13 that ERA5's monthly-means product does carry gust, despite
    ECMWF's docs marking gust fields "forecast only").
    """
    import time
    import calendar
    from core.utils import ncei_bbox_str
    from modules.m2_weather.ncei import get_cached_month, save_cached_month

    summary = _empty_summary()
    bbox = ncei_bbox_str(site.lat, site.lon, site.bbox_nm)

    NCEI_MAX_LIVE_MONTHS = 3

    # Build list of (start, end) monthly windows
    windows: list[tuple[str, str]] = []
    for yr in range(year_start, year_end + 1):
        for mo in range(1, 13):
            last_day = calendar.monthrange(yr, mo)[1]
            windows.append((f"{yr}-{mo:02d}-01", f"{yr}-{mo:02d}-{last_day:02d}"))

    allow_live_fetch = len(windows) <= NCEI_MAX_LIVE_MONTHS

    ws_means, ws_p90s, wdir_means, ws_record_counts = [], [], [], []
    wave_hgt_means, wave_hgt_p90s, wave_hgt_record_counts = [], [], []
    wave_dir_means, swell_dir_means = [], []

    live_fetches_used = 0
    for start_date, end_date in windows:
        month_start = start_date
        result = get_cached_month(bbox, month_start)   # always a fast local read
        if result is None:
            if not allow_live_fetch:
                continue   # range too large to risk live NCEI calls — cache-only
            if live_fetches_used > 0:
                time.sleep(1)   # NCEI rate-limit courtesy pause between LIVE requests
            live_fetches_used += 1
            result = fetch_wind_history(
                lat        = site.lat,
                lon        = site.lon,
                bbox_nm    = site.bbox_nm,
                start_date = start_date,
                end_date   = end_date,
            )
            if result is None:
                continue
            save_cached_month(bbox, month_start, result)
        if result.get("ws_mean_kts") is not None:
            ws_means.append(result["ws_mean_kts"])
            ws_p90s.append(result["ws_p90_kts"])
            ws_record_counts.append(result["record_count"])
        if result.get("wdir_mean_deg") is not None:
            wdir_means.append(result["wdir_mean_deg"])
        if result.get("wave_hgt_mean_m") is not None:
            wave_hgt_means.append(result["wave_hgt_mean_m"])
            wave_hgt_p90s.append(result.get("wave_hgt_p90_m") or result["wave_hgt_mean_m"])
            wave_hgt_record_counts.append(result["record_count"])
        if result.get("wave_dir_mean_deg") is not None:
            wave_dir_means.append(result["wave_dir_mean_deg"])
        if result.get("swell_dir_mean_deg") is not None:
            swell_dir_means.append(result["swell_dir_mean_deg"])

    def _circular_mean(angles_deg: list[float]) -> float:
        rad = np.deg2rad(angles_deg)
        return float(
            np.degrees(np.arctan2(np.mean(np.sin(rad)), np.mean(np.cos(rad)))) % 360
        )

    if ws_means:
        total_records = sum(ws_record_counts)
        weights       = [rc / total_records for rc in ws_record_counts]
        ws_mean_agg   = round(sum(m * w for m, w in zip(ws_means, weights)), 2)
        ws_p90_agg    = round(float(np.mean(ws_p90s)), 2)
        summary["ws"] = {
            "mean":       ws_mean_agg,
            "p90":        ws_p90_agg,
            "source":     "ncei_global_marine",
            "station_id": None,   # area-aggregate, not a single station
        }
        if wdir_means:
            summary["wdV"] = {
                "mean":       round(_circular_mean(wdir_means), 1),
                "p90":        None,
                "source":     "ncei_global_marine",
                "station_id": None,
            }

    if wave_hgt_means:
        total_wave_records = sum(wave_hgt_record_counts)
        wave_weights = [rc / total_wave_records for rc in wave_hgt_record_counts]
        summary["sh"] = {
            "mean":       round(sum(m * w for m, w in zip(wave_hgt_means, wave_weights)), 2),
            "p90":        round(float(np.mean(wave_hgt_p90s)), 2),
            "source":     "ncei_global_marine",
            "station_id": None,
        }
        if wave_dir_means:
            summary["sdV"] = {
                "mean":       round(_circular_mean(wave_dir_means), 1),
                "p90":        None,
                "source":     "ncei_global_marine",
                "station_id": None,
            }

    if swell_dir_means:
        summary["swdV"] = {
            "mean":       round(_circular_mean(swell_dir_means), 1),
            "p90":        None,
            "source":     "ncei_global_marine",
            "station_id": None,
        }

    # ── ERA5: swell climatology for swh and swp ──────────────────────────────
    _apply_era5_swell(summary, site.lat, site.lon, year_start, year_end)

    # ── ERA5: wind gust climatology for wg (Set 42 follow-up) ────────────────
    _apply_era5_gust(summary, site.lat, site.lon, year_start, year_end)

    return summary


# ── 45-day implementation ────────────────────────────────────────────────────

def _fetch_45day(site: Site) -> dict:
    summary = _empty_summary()

    # ── Discover nearby stations ──────────────────────────────────────────────
    try:
        stations = nearest_stations(
            site.lat, site.lon,
            radius_nm=NDBC_STATION_SEARCH_RADIUS_NM,
        )
    except Exception:
        return summary   # network failure → full model fallback

    if not stations:
        return summary

    # ── Met data: walk met stations (nearest first) until one returns data ────
    # Some stations in the active XML are tide gauges whose .txt files do not
    # exist or contain no wind/wave observations. Try up to 10 candidates.
    for candidate in (s for s in stations if s.met_data):
        populated = _populate_from_met(summary, candidate.station_id)
        # Accept this station if at least one parameter was filled
        if any(populated[p]["mean"] is not None for p in ("ws", "sh")):
            summary = populated
            break

    # ── Spec data: nearest station with a .spec file — then WW3 fallback ─────
    # First check stations that are already flagged has_spec=True.
    # If none flagged (has_spec is lazily populated), walk stations checking HEAD.
    spec_station_id = _find_spec_station(stations)
    if spec_station_id is not None:
        summary = _populate_from_spec(summary, spec_station_id)

    # ── WW3 fallback: if no .spec data was found, try ERDDAP ─────────────────
    if summary["swh"]["mean"] is None:
        _apply_ww3_swell(summary, site.lat, site.lon)

    return summary


def _populate_from_met(summary: dict, station_id: str) -> dict:
    """Fetch met DataFrame and populate ws, wg, sh, wdV, sdV entries."""
    try:
        df = fetch_met_data(station_id)
    except Exception:
        return summary

    if df is None or len(df) == 0:
        return summary

    sid = station_id.upper()

    # Wind speed (kts)
    if "wspd_kts" in df.columns and df["wspd_kts"].notna().any():
        vals = df["wspd_kts"].dropna()
        summary["ws"] = {
            "mean":       round(float(vals.mean()), 2),
            "p90":        round(float(np.percentile(vals, 90)), 2),
            "source":     "ndbc_realtime",
            "station_id": sid,
        }

    # Wind gust (kts)
    if "gst_kts" in df.columns and df["gst_kts"].notna().any():
        vals = df["gst_kts"].dropna()
        summary["wg"] = {
            "mean":       round(float(vals.mean()), 2),
            "p90":        round(float(np.percentile(vals, 90)), 2),
            "source":     "ndbc_realtime",
            "station_id": sid,
        }

    # Significant wave height / sea Hs (m)
    if "wvht_m" in df.columns and df["wvht_m"].notna().any():
        vals = df["wvht_m"].dropna()
        summary["sh"] = {
            "mean":       round(float(vals.mean()), 2),
            "p90":        round(float(np.percentile(vals, 90)), 2),
            "source":     "ndbc_realtime",
            "station_id": sid,
        }

    # Wind direction variance (circular std, degrees)
    if "wdir_deg" in df.columns and df["wdir_deg"].notna().sum() >= 2:
        cstd = _circular_std_deg(df["wdir_deg"].dropna())
        if cstd is not None:
            summary["wdV"] = {
                "mean":       round(cstd, 2),
                "p90":        round(cstd * 1.3, 2),   # approx upper tail
                "source":     "ndbc_realtime",
                "station_id": sid,
            }

    # Sea direction variance (MWD circular std, degrees)
    if "mwd_deg" in df.columns and df["mwd_deg"].notna().sum() >= 2:
        cstd = _circular_std_deg(df["mwd_deg"].dropna())
        if cstd is not None:
            summary["sdV"] = {
                "mean":       round(cstd, 2),
                "p90":        round(cstd * 1.3, 2),
                "source":     "ndbc_realtime",
                "station_id": sid,
            }

    return summary


def _populate_from_spec(summary: dict, station_id: str) -> dict:
    """Fetch spec DataFrame and populate swh, swp, swdV entries."""
    try:
        df = fetch_spec_data(station_id)
    except Exception:
        return summary

    if df is None or len(df) == 0:
        return summary

    sid = station_id.upper()

    # Swell height (m)
    if "swh_m" in df.columns and df["swh_m"].notna().any():
        vals = df["swh_m"].dropna()
        summary["swh"] = {
            "mean":       round(float(vals.mean()), 2),
            "p90":        round(float(np.percentile(vals, 90)), 2),
            "source":     "ndbc_realtime",
            "station_id": sid,
        }

    # Swell period (s)
    if "swp_s" in df.columns and df["swp_s"].notna().any():
        vals = df["swp_s"].dropna()
        summary["swp"] = {
            "mean":       round(float(vals.mean()), 2),
            "p90":        round(float(np.percentile(vals, 90)), 2),
            "source":     "ndbc_realtime",
            "station_id": sid,
        }

    # Swell direction variance (circular std)
    if "swd_deg" in df.columns and df["swd_deg"].notna().sum() >= 2:
        cstd = _circular_std_deg(df["swd_deg"].dropna())
        if cstd is not None:
            summary["swdV"] = {
                "mean":       round(cstd, 2),
                "p90":        round(cstd * 1.3, 2),
                "source":     "ndbc_realtime",
                "station_id": sid,
            }

    return summary


def _apply_era5_swell(
    summary: dict,
    lat: float,
    lon: float,
    year_start: int,
    year_end: int,
) -> None:
    """
    Call fetch_swell_climatology and, if successful, populate swh and swp in
    summary with ERA5 annual-aggregate stats.  Mutates summary in place.

    swdV is intentionally left as icoads_model: ERA5 provides the mean wave
    direction, not the directional variance that the engine expects.
    """
    from modules.m2_weather.era5 import fetch_swell_climatology

    era5 = fetch_swell_climatology(lat, lon, year_start, year_end, months=None)
    if era5 is None:
        return   # fall back to icoads_model — already set

    # Aggregate across all available months using simple mean
    swh_means = [v["swh_mean_m"] for v in era5.values() if v.get("swh_mean_m") is not None]
    swh_p90s  = [v["swh_p90_m"]  for v in era5.values() if v.get("swh_p90_m")  is not None]
    swp_means = [v["swp_mean_s"] for v in era5.values() if v.get("swp_mean_s") is not None]

    if swh_means:
        summary["swh"] = {
            "mean":       round(float(np.mean(swh_means)), 3),
            "p90":        round(float(np.mean(swh_p90s)), 3) if swh_p90s else None,
            "source":     "era5_reanalysis",
            "station_id": None,
        }

    if swp_means:
        summary["swp"] = {
            "mean":       round(float(np.mean(swp_means)), 3),
            "p90":        round(float(np.mean(swp_means)) * 1.2, 3),
            "source":     "era5_reanalysis",
            "station_id": None,
        }


def _apply_era5_gust(
    summary: dict,
    lat: float,
    lon: float,
    year_start: int,
    year_end: int,
) -> None:
    """
    Call fetch_gust_climatology and, if successful, populate wg in summary
    with ERA5 annual-aggregate stats. Mutates summary in place.

    wg has no other live historical source — NCEI Global Marine does not
    carry gust at all (see _fetch_historical()'s docstring) — so this is
    the difference between wg staying icoads_model and getting a real
    observed-climatology figure in Historical mode.
    """
    from modules.m2_weather.era5 import fetch_gust_climatology

    era5 = fetch_gust_climatology(lat, lon, year_start, year_end, months=None)
    if era5 is None:
        return   # fall back to icoads_model — already set

    wg_means = [v["wg_mean_kts"] for v in era5.values() if v.get("wg_mean_kts") is not None]
    wg_p90s  = [v["wg_p90_kts"]  for v in era5.values() if v.get("wg_p90_kts")  is not None]

    if wg_means:
        summary["wg"] = {
            "mean":       round(float(np.mean(wg_means)), 2),
            "p90":        round(float(np.mean(wg_p90s)), 2) if wg_p90s else None,
            "source":     "era5_reanalysis",
            "station_id": None,
        }


def _apply_ww3_swell(summary: dict, lat: float, lon: float) -> None:
    """
    Call fetch_swell_realtime_ww3 and, if successful, populate swh and swp.
    Mutates summary in place.

    swdV is left as icoads_model for the same reason as ERA5: WW3 ERDDAP
    returns mean direction, not the circular std the engine uses for swdV.
    """
    from modules.m2_weather.era5 import fetch_swell_realtime_ww3

    ww3 = fetch_swell_realtime_ww3(lat, lon)
    if ww3 is None:
        return

    if ww3.get("swh_mean_m") is not None:
        summary["swh"] = {
            "mean":       ww3["swh_mean_m"],
            "p90":        ww3.get("swh_p90_m"),
            "source":     "ww3_erddap",
            "station_id": None,
        }

    if ww3.get("swp_mean_s") is not None:
        summary["swp"] = {
            "mean":       ww3["swp_mean_s"],
            "p90":        round(ww3["swp_mean_s"] * 1.2, 3),
            "source":     "ww3_erddap",
            "station_id": None,
        }


def _find_spec_station(stations) -> Optional[str]:
    """
    Return the nearest station_id that has a .spec file, or None.
    Checks has_spec flag first (fast path); falls back to HEAD requests
    for the 5 closest stations if none are pre-flagged.
    """
    # Fast path: has_spec already known
    for s in stations:
        if s.has_spec:
            return s.station_id

    # Slow path: walk the closest stations and probe with HEAD
    for s in stations[:5]:
        try:
            if spec_available(s.station_id):
                s.has_spec = True
                return s.station_id
        except Exception:
            continue

    return None

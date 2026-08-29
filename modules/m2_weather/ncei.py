"""
modules/m2_weather/ncei.py — NCEI Data Service API integration.

Fetches historical marine observations from the NCEI Global Marine dataset
(ICOADS-based ship and buoy reports, 1662–present).

No API key required. Rate limit is generous for individual queries.
Sleep 1 second between calls when making multiple requests in a loop.

Endpoint: https://www.ncei.noaa.gov/access/services/data/v1
Dataset:  global-marine
Types:    WIND_SPEED (m/s), WIND_DIR (deg), WAVE_HGT (m), WAVE_DIR (deg),
          SWELL_HGT (m), SWELL_DIR (deg)
BBox:     N,W,S,E  (NCEI convention — note W is negative lon)

Units:
  WIND_SPEED arrives in m/s → converted to knots before returning.
  WIND_DIR/WAVE_DIR/SWELL_DIR in degrees true (0–360).
  WAVE_HGT/SWELL_HGT arrive in metres already (units=metric) — no conversion.

Set 39 field-availability note (empirically confirmed against the live API,
not assumed from docs — NCEI's field catalogue isn't fully documented):
  - WIND_GUST_SPEED / GUST_SPEED: tried both, neither ever appears in a
    response (tested 36k+ records across a wide bbox/date range). This
    dataset genuinely does not carry gust — ship/buoy reports here only
    include sustained wind. `wg` has no live historical source in this app.
  - SWELL_PRD: also tried, never appears. Swell period has no NCEI source;
    stays on ERA5 (era5.py) as before.
  - WAVE_HGT, WAVE_DIR, SWELL_HGT, SWELL_DIR: all confirmed present and are
    now fetched — see fetch_wind_history()'s return dict.
"""

import logging
import sys
import time
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import NCEI_DATA_API, NCEI_DATASET, MS_TO_KTS
from core.utils import ncei_bbox_str

log = logging.getLogger(__name__)

_TIMEOUT = 30   # seconds — NCEI can be slow on large date ranges


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_wind_history(
    lat: float,
    lon: float,
    bbox_nm: float,
    start_date: str,
    end_date: str,
) -> Optional[dict]:
    """
    Fetch historical wind, wave, and swell observations from NCEI Global
    Marine dataset (Set 39 — previously wind-only; wave/swell fields added
    once confirmed present via a direct live-API query, see module docstring).

    Parameters
    ----------
    lat, lon    : Site center in decimal degrees (+N/-S, +E/-W).
    bbox_nm     : Bounding box radius in nautical miles (e.g. 25.0).
    start_date  : ISO date string 'YYYY-MM-DD'.
    end_date    : ISO date string 'YYYY-MM-DD'.

    Returns
    -------
    dict with keys:
        ws_mean_kts       : float — mean wind speed (knots)
        ws_p90_kts        : float — 90th-percentile wind speed (knots)
        ws_max_kts        : float — maximum wind speed (knots)
        wdir_mean_deg     : float — circular mean wind direction (degrees)
        wave_hgt_mean_m   : float or None — mean wave height (metres)
        wave_hgt_p90_m    : float or None — 90th-percentile wave height
        wave_dir_mean_deg : float or None — circular mean wave direction
        swell_hgt_mean_m  : float or None — mean swell height (metres)
        swell_dir_mean_deg: float or None — circular mean swell direction
        record_count      : int
        date_range_start  : str (ISO 8601)
        date_range_end    : str (ISO 8601)
        source            : 'ncei_global_marine'

    Any field is None if that dataType had no observations in range — a
    station reporting wind but not waves is common and not an error.
    Returns None only on total HTTP/parsing failure (warning is logged).
    """
    bbox = ncei_bbox_str(lat, lon, bbox_nm)
    params = {
        "dataset":      NCEI_DATASET,
        "dataTypes":    "WIND_SPEED,WIND_DIR,WAVE_HGT,WAVE_DIR,SWELL_HGT,SWELL_DIR",
        "boundingBox":  bbox,          # NCEI API param name (not 'bbox')
        "startDate":    start_date,
        "endDate":      end_date,
        "format":       "json",
        "units":        "metric",
    }

    try:
        resp = requests.get(NCEI_DATA_API, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("NCEI fetch failed for bbox=%s %s–%s: %s", bbox, start_date, end_date, exc)
        return None

    try:
        data = resp.json()
    except ValueError as exc:
        log.warning("NCEI response is not valid JSON: %s", exc)
        return None

    df = _parse_ncei_json(data)
    if df is None or len(df) == 0:
        log.warning("NCEI returned no usable records for bbox=%s %s–%s", bbox, start_date, end_date)
        return None

    from modules.m2_weather.operability import compute_operability_from_df, REF_WIND_KTS, REF_HS_M
    pct_both, n_operable = compute_operability_from_df(df, REF_WIND_KTS, REF_HS_M)
    summary = _summarise(df)
    summary["pct_both_criteria"] = pct_both
    summary["n_fully_operable_days"] = n_operable
    return summary


# ── Monthly cache (Set 41) ─────────────────────────────────────────────────────
# Avoids the ~130s-per-month live NCEI query on repeat use — see module
# docstring. Cached rows are ncei.py::_summarise()'s exact output shape,
# keyed by the exact NCEI boundingBox string queried (not site id) + the
# calendar month's start date. Climatological data, not live conditions —
# no automatic expiry; a caller-driven "Refresh" can just re-fetch and
# overwrite via save_cached_month().

_CACHE_COLUMNS = [
    "ws_mean_kts", "ws_p90_kts", "ws_max_kts", "wdir_mean_deg",
    "wave_hgt_mean_m", "wave_hgt_p90_m", "wave_dir_mean_deg",
    "swell_hgt_mean_m", "swell_dir_mean_deg", "record_count",
    "pct_both_criteria", "n_fully_operable_days",
]


def get_cached_month(bbox: str, month_start: str) -> Optional[dict]:
    """
    Return the cached summary for this bbox+month, or None if not cached.
    Shape matches fetch_wind_history()'s return dict (minus date_range_*,
    which the caller already knows from month_start).
    """
    from core.database import get_connection
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM ncei_monthly_cache WHERE bbox=? AND month_start=?",
            (bbox, month_start),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    result = {col: row[col] for col in _CACHE_COLUMNS}
    result["source"] = "ncei_global_marine"
    return result


def save_cached_month(bbox: str, month_start: str, summary: dict) -> None:
    """Insert or overwrite the cached summary for this bbox+month."""
    from core.database import get_connection
    conn = get_connection()
    try:
        conn.execute(
            f"""
            INSERT INTO ncei_monthly_cache
                (bbox, month_start, {", ".join(_CACHE_COLUMNS)}, fetched_at)
            VALUES (?, ?, {", ".join("?" for _ in _CACHE_COLUMNS)}, CURRENT_TIMESTAMP)
            ON CONFLICT(bbox, month_start) DO UPDATE SET
                {", ".join(f"{c}=excluded.{c}" for c in _CACHE_COLUMNS)},
                fetched_at = excluded.fetched_at
            """,
            (bbox, month_start, *(summary.get(c) for c in _CACHE_COLUMNS)),
        )
        conn.commit()
    finally:
        conn.close()


# ── Parsing ───────────────────────────────────────────────────────────────────

_NUMERIC_FIELDS = {
    "WIND_SPEED": "wind_speed_ms",
    "WIND_DIR":   "wind_dir_deg",
    "WAVE_HGT":   "wave_hgt_m",
    "WAVE_DIR":   "wave_dir_deg",
    "SWELL_HGT":  "swell_hgt_m",
    "SWELL_DIR":  "swell_dir_deg",
}


def _parse_ncei_json(data) -> Optional[pd.DataFrame]:
    """
    Parse the NCEI Data Service JSON response into a DataFrame.

    The response is a list of observation dicts. Each dict has at minimum
    'DATE' and whichever requested dataType fields that particular
    station/report actually provided — a report with only WAVE_HGT (no
    wind) is common (different sensor/observer per field) and must be kept,
    not dropped, so wave/swell-only rows aren't silently lost.

    Returns DataFrame with columns: timestamp, wind_speed_ms, wind_dir_deg,
    wind_speed_kts, wave_hgt_m, wave_dir_deg, swell_hgt_m, swell_dir_deg.
    Returns None if the response format is unexpected or no row has any
    of these six fields.
    """
    if not isinstance(data, list) or len(data) == 0:
        return None

    rows = []
    for obs in data:
        if not isinstance(obs, dict):
            continue

        date_str = obs.get("DATE") or obs.get("date")
        if not date_str:
            continue

        row = {"timestamp": date_str}
        any_value = False
        for src_key, col in _NUMERIC_FIELDS.items():
            raw = obs.get(src_key)
            try:
                val = float(raw) if raw is not None else None
            except (TypeError, ValueError):
                val = None
            row[col] = val
            if val is not None:
                any_value = True

        if not any_value:
            continue

        rows.append(row)

    if not rows:
        return None

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"])

    numeric_cols = list(_NUMERIC_FIELDS.values())
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Convert m/s → knots
    df["wind_speed_kts"] = df["wind_speed_ms"] * MS_TO_KTS

    return df.reset_index(drop=True)


# ── Summary statistics ────────────────────────────────────────────────────────

def _summarise(df: pd.DataFrame) -> dict:
    """Compute summary statistics from a parsed NCEI DataFrame."""
    ws        = df["wind_speed_kts"].dropna()
    wd        = df["wind_dir_deg"].dropna()
    wave_hgt  = df["wave_hgt_m"].dropna()
    wave_dir  = df["wave_dir_deg"].dropna()
    swell_hgt = df["swell_hgt_m"].dropna()
    swell_dir = df["swell_dir_deg"].dropna()

    wdir_mean  = _circular_mean_deg(wd)        if len(wd)        >= 2 else None
    wavedir_mean  = _circular_mean_deg(wave_dir)  if len(wave_dir)  >= 2 else None
    swelldir_mean = _circular_mean_deg(swell_dir) if len(swell_dir) >= 2 else None

    ts = df["timestamp"]
    return {
        "ws_mean_kts":        round(float(ws.mean()), 2)              if len(ws)        else None,
        "ws_p90_kts":         round(float(np.percentile(ws, 90)), 2)  if len(ws)        else None,
        "ws_max_kts":         round(float(ws.max()), 2)               if len(ws)        else None,
        "wdir_mean_deg":      round(wdir_mean, 1)                     if wdir_mean is not None else None,
        "wave_hgt_mean_m":    round(float(wave_hgt.mean()), 2)        if len(wave_hgt)  else None,
        "wave_hgt_p90_m":     round(float(np.percentile(wave_hgt, 90)), 2) if len(wave_hgt) else None,
        "wave_dir_mean_deg":  round(wavedir_mean, 1)                  if wavedir_mean is not None else None,
        "swell_hgt_mean_m":   round(float(swell_hgt.mean()), 2)       if len(swell_hgt) else None,
        "swell_dir_mean_deg": round(swelldir_mean, 1)                 if swelldir_mean is not None else None,
        "record_count":       len(df),
        "date_range_start":   ts.min().isoformat()                    if len(ts)        else "",
        "date_range_end":     ts.max().isoformat()                    if len(ts)        else "",
        "source":             "ncei_global_marine",
    }


def _circular_mean_deg(angles_deg) -> Optional[float]:
    """Circular mean of a series of bearings (degrees)."""
    arr = np.asarray(angles_deg, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return None
    rad = np.deg2rad(arr)
    mean_sin = np.mean(np.sin(rad))
    mean_cos = np.mean(np.cos(rad))
    return float(np.degrees(np.arctan2(mean_sin, mean_cos)) % 360)

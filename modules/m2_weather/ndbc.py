"""
modules/m2_weather/ndbc.py — NDBC station discovery and data fetch.

Station discovery:
  - Fetches the NDBC active stations XML feed
  - Filters to stations within a given radius (default 200 NM)
  - Returns NDBCStation objects sorted by distance

Data fetch:
  - fetch_met(station_id)  → parsed rows from the .txt realtime met file
  - fetch_spec(station_id) → parsed rows from the .spec spectral file
  - spec_available(station_id) → True if .spec file exists for this station

Units out of NDBC:
  - WSPD / GST in m/s → converted to knots here
  - WVHT, SwH in metres (returned as-is)
  - WDIR, MWD, SwD in degrees (returned as-is)
  - SwP in seconds (returned as-is)
"""

import io
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional
import xml.etree.ElementTree as ET

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import (
    NDBC_ACTIVE_STATIONS_URL,
    NDBC_REALTIME_BASE,
    NDBC_STATION_SEARCH_RADIUS_NM,
    MS_TO_KTS,
)
from core.models import NDBCStation
from core.utils import haversine_nm, bearing_deg

# HTTP timeout for all NDBC requests (seconds)
_TIMEOUT = 20


# ── Station discovery ────────────────────────────────────────────────────────

def fetch_active_stations() -> List[NDBCStation]:
    """
    Download the NDBC active stations XML and return all stations as
    NDBCStation objects (no distance filtering).
    """
    resp = requests.get(NDBC_ACTIVE_STATIONS_URL, timeout=_TIMEOUT)
    resp.raise_for_status()
    return _parse_stations_xml(resp.text)


def nearest_stations(
    lat: float,
    lon: float,
    radius_nm: float = NDBC_STATION_SEARCH_RADIUS_NM,
    met_only: bool = False,
) -> List[NDBCStation]:
    """
    Return NDBC stations within `radius_nm` nautical miles of (lat, lon),
    sorted by distance ascending.

    Args:
        lat: Site latitude (+N/-S).
        lon: Site longitude (+E/-W).
        radius_nm: Search radius in nautical miles (default 200 NM from config).
        met_only: If True, only return stations that report meteorological data.

    Returns:
        List of NDBCStation with distance_nm and bearing_deg populated.
    """
    stations = fetch_active_stations()
    nearby: List[NDBCStation] = []

    for st in stations:
        if met_only and not st.met_data:
            continue
        dist = haversine_nm(lat, lon, st.lat, st.lon)
        if dist <= radius_nm:
            st.distance_nm = round(dist, 1)
            st.bearing_deg = round(bearing_deg(lat, lon, st.lat, st.lon), 1)
            nearby.append(st)

    nearby.sort(key=lambda s: s.distance_nm)
    return nearby


def _parse_stations_xml(xml_text: str) -> List[NDBCStation]:
    """Parse NDBC activestations.xml into NDBCStation objects."""
    root = ET.fromstring(xml_text)
    stations: List[NDBCStation] = []

    for elem in root.iter("station"):
        sid = elem.get("id", "").strip()
        if not sid:
            continue
        try:
            lat = float(elem.get("lat", 0))
            lon = float(elem.get("lon", 0))
        except (TypeError, ValueError):
            continue

        # met_data: NDBC marks stations that have met obs with met="y"
        met = elem.get("met", "n").lower() == "y"

        stations.append(NDBCStation(
            station_id=sid,
            name=elem.get("name", sid),
            lat=lat,
            lon=lon,
            has_spec=False,   # determined lazily via spec_available()
            met_data=met,
        ))

    return stations


# ── .spec availability check ─────────────────────────────────────────────────

def spec_available(station_id: str) -> bool:
    """
    Return True if a realtime .spec spectral file exists for this station.
    Uses an HTTP HEAD request — cheap, no body downloaded.
    """
    url = f"{NDBC_REALTIME_BASE}/{station_id.upper()}.spec"
    try:
        resp = requests.head(url, timeout=_TIMEOUT, allow_redirects=True)
        return resp.status_code == 200
    except requests.RequestException:
        return False


# ── Met (.txt) data fetch ────────────────────────────────────────────────────

def fetch_met(station_id: str) -> List[dict]:
    """
    Fetch and parse the NDBC realtime met (.txt) file for a station.

    Returns a list of dicts (most-recent observation first) with keys:
      timestamp (str, ISO 8601), wind_spd_kts, gust_kts, wind_dir_deg,
      wave_ht_m, wave_dir_deg, water_temp_c, pressure_hpa, air_temp_c

    Missing values (MM in source) are returned as None.
    Wind speed and gust are converted from m/s to knots.
    """
    url = f"{NDBC_REALTIME_BASE}/{station_id.upper()}.txt"
    resp = requests.get(url, timeout=_TIMEOUT)
    resp.raise_for_status()
    return _parse_met(resp.text)


def _parse_met(text: str) -> List[dict]:
    """Parse NDBC .txt met file content into a list of observation dicts."""
    lines = text.splitlines()
    # First line is header; second line is units — skip both.
    if len(lines) < 3:
        return []

    header = lines[0].lstrip("#").split()
    # NDBC deliberately uses mixed case: MM=month, mm=minute, hh=hour.
    # Preserve original case so these do not collide.
    col = {h: i for i, h in enumerate(header)}
    # Also build an uppercase map for data columns (WSPD, GST, WVHT, etc.)
    col_up = {h.upper(): i for i, h in enumerate(header)}

    rows: List[dict] = []
    for line in lines[2:]:
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 5:
            continue

        def _get_cs(key: str) -> Optional[str]:
            """Case-sensitive lookup — for timestamp fields."""
            i = col.get(key)
            if i is None or i >= len(parts):
                return None
            v = parts[i]
            return None if v == "MM" else v

        def _get(key: str) -> Optional[str]:
            """Uppercase lookup — for data fields (WSPD, WVHT, etc.)."""
            i = col_up.get(key)
            if i is None or i >= len(parts):
                return None
            v = parts[i]
            return None if v == "MM" else v

        def fget(key: str) -> Optional[float]:
            v = _get(key)
            return float(v) if v is not None else None

        # Timestamp: NDBC column names are YY (or #YY), MM, DD, hh, mm
        yr = _get_cs("YY") or _get_cs("#YY")
        mo = _get_cs("MM")   # capital MM = calendar month
        dd = _get_cs("DD")
        hh = _get_cs("hh")   # lowercase hh = hour
        mn = _get_cs("mm") or "00"   # lowercase mm = minute
        if not all([yr, mo, dd, hh]):
            continue
        if len(yr) == 2:
            yr = "20" + yr
        ts = f"{yr}-{mo.zfill(2)}-{dd.zfill(2)}T{hh.zfill(2)}:{mn.zfill(2)}Z"

        wspd = fget("WSPD")
        gst  = fget("GST")
        rows.append({
            "timestamp":     ts,
            "wind_spd_kts":  round(wspd * MS_TO_KTS, 1) if wspd is not None else None,
            "gust_kts":      round(gst  * MS_TO_KTS, 1) if gst  is not None else None,
            "wind_dir_deg":  fget("WDIR"),
            "wave_ht_m":     fget("WVHT"),
            "wave_dir_deg":  fget("MWD"),
            "water_temp_c":  fget("WTMP"),
            "pressure_hpa":  fget("PRES"),
            "air_temp_c":    fget("ATMP"),
        })

    return rows


# ── Spectral (.spec) data fetch ───────────────────────────────────────────────

def fetch_spec(station_id: str) -> List[dict]:
    """
    Fetch and parse the NDBC realtime spectral (.spec) file for a station.

    Returns a list of dicts (most-recent observation first) with keys:
      timestamp (str, ISO 8601), swell_ht_m, swell_period_s, swell_dir_deg,
      wind_wave_ht_m, wind_wave_period_s, wind_wave_dir_deg

    Missing values are returned as None.
    """
    url = f"{NDBC_REALTIME_BASE}/{station_id.upper()}.spec"
    resp = requests.get(url, timeout=_TIMEOUT)
    resp.raise_for_status()
    return _parse_spec(resp.text)


def _parse_spec(text: str) -> List[dict]:
    """Parse NDBC .spec file content into a list of observation dicts."""
    lines = text.splitlines()
    if len(lines) < 3:
        return []

    header = lines[0].lstrip("#").split()
    col    = {h: i for i, h in enumerate(header)}        # case-sensitive (timestamps)
    col_up = {h.upper(): i for i, h in enumerate(header)}  # uppercase (data fields)

    rows: List[dict] = []
    for line in lines[2:]:
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 5:
            continue

        def _get_cs(key: str) -> Optional[str]:
            i = col.get(key)
            if i is None or i >= len(parts):
                return None
            v = parts[i]
            return None if v == "MM" else v

        def fget(key: str) -> Optional[float]:
            i = col_up.get(key)
            if i is None or i >= len(parts):
                return None
            v = parts[i]
            if v == "MM":
                return None
            try:
                return float(v)
            except ValueError:
                return None

        yr = _get_cs("YY") or _get_cs("#YY")
        mo = _get_cs("MM")
        dd = _get_cs("DD")
        hh = _get_cs("hh")
        mn = _get_cs("mm") or "00"
        if not all([yr, mo, dd, hh]):
            continue
        if len(yr) == 2:
            yr = "20" + yr
        ts = f"{yr}-{mo.zfill(2)}-{dd.zfill(2)}T{hh.zfill(2)}:{mn.zfill(2)}Z"

        rows.append({
            "timestamp":         ts,
            "swell_ht_m":        fget("SWH"),
            "swell_period_s":    fget("SWP"),
            "swell_dir_deg":     fget("SWD"),
            "wind_wave_ht_m":    fget("WWH"),
            "wind_wave_period_s":fget("WWP"),
            "wind_wave_dir_deg": fget("WWD"),
        })

    return rows


# ── DataFrame fetch functions ────────────────────────────────────────────────

# NDBC uses these sentinel values for missing data in numeric columns
_MISSING = {99.0, 999.0}
_CUTOFF_DAYS = 45


def fetch_met_data(station_id: str) -> pd.DataFrame:
    """
    Fetch the NDBC realtime met (.txt) file and return a cleaned DataFrame.

    Columns returned:
        timestamp  — UTC datetime (timezone-aware)
        wspd_ms    — wind speed (m/s, raw from NDBC); NOTE: also exposed as kts below
        wspd_kts   — wind speed converted to knots
        wdir_deg   — wind direction (degrees true)
        gst_ms     — gust speed (m/s, raw)
        gst_kts    — gust speed converted to knots
        wvht_m     — significant wave height (m)
        mwd_deg    — mean wave direction (degrees true)

    Processing:
        - Rows where any numeric value equals 99.0 or 999.0 are dropped.
        - Only records within the last 45 days are returned.
        - Rows with a missing timestamp are silently dropped.

    Raises:
        requests.HTTPError if the station file cannot be fetched.
    """
    url = f"{NDBC_REALTIME_BASE}/{station_id.upper()}.txt"
    resp = requests.get(url, timeout=_TIMEOUT)
    resp.raise_for_status()

    rows = _parse_met(resp.text)
    if not rows:
        return _empty_met_df()

    df = pd.DataFrame(rows)

    # Rename to match the specified column contract
    df = df.rename(columns={
        "wind_spd_kts": "wspd_kts",
        "gust_kts":     "gst_kts",
        "wind_dir_deg": "wdir_deg",
        "wave_ht_m":    "wvht_m",
        "wave_dir_deg": "mwd_deg",
    })

    # Parse timestamps
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"])

    # Derive raw m/s columns from kts (parser already converted; back-calculate)
    df["wspd_ms"] = df["wspd_kts"] / MS_TO_KTS
    df["gst_ms"]  = df["gst_kts"]  / MS_TO_KTS

    # Keep only the declared output columns (others like water_temp_c are dropped)
    df = df[["timestamp", "wspd_ms", "wspd_kts", "wdir_deg", "gst_ms", "gst_kts",
             "wvht_m", "mwd_deg"]]

    # Replace NDBC sentinel values (99.0, 999.0) with NaN — but keep rows that
    # have at least one valid measurement. Individual per-column NaN is fine;
    # callers handle missing columns via .notna() checks.
    num_cols = ["wspd_ms", "wspd_kts", "wdir_deg", "gst_ms", "gst_kts", "wvht_m", "mwd_deg"]
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df[num_cols] = df[num_cols].where(~df[num_cols].isin(_MISSING))
    # Drop rows where every numeric column is NaN (completely empty observations)
    df = df.dropna(subset=num_cols, how="all")

    # Limit to last 45 days
    cutoff = datetime.now(timezone.utc) - timedelta(days=_CUTOFF_DAYS)
    df = df[df["timestamp"] >= cutoff]

    return df.reset_index(drop=True)


def fetch_spec_data(station_id: str) -> Optional[pd.DataFrame]:
    """
    Fetch the NDBC realtime spectral (.spec) file and return a cleaned DataFrame.

    Returns None if the station has no spectral sensor (HTTP 404 is expected
    and not treated as an error).

    Columns returned:
        timestamp  — UTC datetime (timezone-aware)
        swh_m      — swell height (m)
        swp_s      — swell period (s)
        swd_deg    — swell direction (degrees true)

    Processing:
        - Rows where any value equals 99.0 or 999.0 are dropped.
        - Rows with a missing timestamp are silently dropped.

    Raises:
        requests.HTTPError for non-404 HTTP errors.
    """
    url = f"{NDBC_REALTIME_BASE}/{station_id.upper()}.spec"
    resp = requests.get(url, timeout=_TIMEOUT)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()

    rows = _parse_spec(resp.text)
    if not rows:
        return _empty_spec_df()

    df = pd.DataFrame(rows)

    df = df.rename(columns={
        "swell_ht_m":     "swh_m",
        "swell_period_s": "swp_s",
        "swell_dir_deg":  "swd_deg",
    })

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"])

    df = df[["timestamp", "swh_m", "swp_s", "swd_deg"]]

    num_cols = ["swh_m", "swp_s", "swd_deg"]
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    sentinel_mask = df[num_cols].isin(_MISSING).any(axis=1)
    df = df[~sentinel_mask].dropna(subset=num_cols)

    cutoff = datetime.now(timezone.utc) - timedelta(days=_CUTOFF_DAYS)
    df = df[df["timestamp"] >= cutoff]

    return df.reset_index(drop=True)


def get_station_summary(station_id: str) -> dict:
    """
    Fetch met and (optionally) spec data for a station and return a summary dict.

    Keys:
        station_id          (str)
        has_spec            (bool)
        record_count_met    (int)
        record_count_spec   (int or None)
        wind_speed_mean_kts (float)
        wind_speed_max_kts  (float)
        hs_mean_m           (float)
        hs_max_m            (float)
        date_range_start    (str, ISO 8601 UTC)
        date_range_end      (str, ISO 8601 UTC)
    """
    met_df  = fetch_met_data(station_id)
    spec_df = fetch_spec_data(station_id)

    def _iso(ts: pd.Timestamp) -> str:
        return ts.isoformat() if not pd.isna(ts) else ""

    return {
        "station_id":           station_id.upper(),
        "has_spec":             spec_df is not None,
        "record_count_met":     len(met_df),
        "record_count_spec":    len(spec_df) if spec_df is not None else None,
        "wind_speed_mean_kts":  round(met_df["wspd_kts"].mean(), 2) if len(met_df) else None,
        "wind_speed_max_kts":   round(met_df["wspd_kts"].max(),  2) if len(met_df) else None,
        "hs_mean_m":            round(met_df["wvht_m"].mean(),   2) if len(met_df) else None,
        "hs_max_m":             round(met_df["wvht_m"].max(),    2) if len(met_df) else None,
        "date_range_start":     _iso(met_df["timestamp"].min())     if len(met_df) else "",
        "date_range_end":       _iso(met_df["timestamp"].max())     if len(met_df) else "",
    }


def fetch_station_dataframes(station_id: str) -> dict:
    """
    Fetch raw met and spec DataFrames for a single station.

    Returns dict with keys: station_id, met_df, spec_df, fetch_error.
    On network error, met_df and spec_df are None and fetch_error is set.
    """
    try:
        met_df  = fetch_met_data(station_id)
        spec_df = fetch_spec_data(station_id)
        return {
            "station_id":  station_id,
            "met_df":      met_df,
            "spec_df":     spec_df,
            "fetch_error": None,
        }
    except Exception as exc:
        return {
            "station_id":  station_id,
            "met_df":      None,
            "spec_df":     None,
            "fetch_error": str(exc),
        }


def fetch_multiple_station_dataframes(
    station_ids: list,
    progress_callback=None,
) -> dict:
    """
    Parallel fetch of raw DataFrames for multiple station IDs (max 4 threads).

    Returns {station_id: fetch_station_dataframes(...)} dict.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results: dict = {}
    total = len(station_ids)
    if total == 0:
        return results

    with ThreadPoolExecutor(max_workers=4) as exe:
        futures = {exe.submit(fetch_station_dataframes, sid): sid
                   for sid in station_ids}
        done = 0
        for fut in as_completed(futures):
            sid = futures[fut]
            done += 1
            try:
                results[sid] = fut.result()
            except Exception as exc:
                results[sid] = {
                    "station_id":  sid,
                    "met_df":      None,
                    "spec_df":     None,
                    "fetch_error": str(exc),
                }
            if progress_callback:
                progress_callback(done, total)

    return results


def fetch_multiple_stations(
    station_ids: list,
    progress_callback=None,
) -> dict:
    """
    Fetch station summaries for multiple station IDs in parallel (max 4 threads).

    Returns {station_id: summary_dict} where summary_dict may contain
    {"error": str} if the fetch failed.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results: dict = {}
    total = len(station_ids)
    if total == 0:
        return results

    with ThreadPoolExecutor(max_workers=4) as exe:
        futures = {exe.submit(get_station_summary, sid): sid for sid in station_ids}
        done = 0
        for fut in as_completed(futures):
            sid = futures[fut]
            done += 1
            try:
                results[sid] = fut.result()
            except Exception as exc:
                results[sid] = {"error": str(exc), "station_id": sid}
            if progress_callback:
                progress_callback(done, total)

    return results


def _empty_met_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "timestamp", "wspd_ms", "wspd_kts", "wdir_deg",
        "gst_ms", "gst_kts", "wvht_m", "mwd_deg",
    ])


def _empty_spec_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["timestamp", "swh_m", "swp_s", "swd_deg"])


# ── DB cache helpers ──────────────────────────────────────────────────────────

def cache_stations(stations: List[NDBCStation]) -> None:
    """
    Upsert a list of NDBCStation objects into the ndbc_stations cache table.
    Only call after spec_available() has been checked if you want has_spec accurate.
    """
    from core.database import get_connection
    from datetime import datetime, timezone

    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        """
        INSERT INTO ndbc_stations (station_id, name, lat, lon, has_spec, met_data, last_checked)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(station_id) DO UPDATE SET
            name=excluded.name, lat=excluded.lat, lon=excluded.lon,
            has_spec=excluded.has_spec, met_data=excluded.met_data,
            last_checked=excluded.last_checked
        """,
        [
            (s.station_id, s.name, s.lat, s.lon,
             int(s.has_spec), int(s.met_data), now)
            for s in stations
        ],
    )
    conn.commit()
    conn.close()


# ── CLI quick-test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Usage: python -m modules.m2_weather.ndbc <lat> <lon> [radius_nm]
    import sys as _sys

    lat  = float(_sys.argv[1]) if len(_sys.argv) > 1 else 28.5
    lon  = float(_sys.argv[2]) if len(_sys.argv) > 2 else -80.6
    rad  = float(_sys.argv[3]) if len(_sys.argv) > 3 else 200.0

    print(f"Fetching active NDBC stations within {rad} NM of {lat:.4f}, {lon:.4f} …")
    stations = nearest_stations(lat, lon, radius_nm=rad)
    print(f"Found {len(stations)} station(s):\n")
    fmt = "{:<8}  {:>8.3f}°  {:>9.3f}°  {:>7.1f} NM  {:>6.1f}°  spec={!s:<5}  {}"
    print(f"{'ID':<8}  {'Lat':>9}  {'Lon':>10}  {'Dist':>8}  {'Brng':>7}  {'spec':<7}  Name")
    print("-" * 80)
    for s in stations:
        print(fmt.format(
            s.station_id, s.lat, s.lon,
            s.distance_nm, s.bearing_deg,
            s.has_spec, s.name,
        ))

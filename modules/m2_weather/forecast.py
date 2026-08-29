"""
modules/m2_weather/forecast.py — Forecast analysis from aggregated NDBC data,
plus live marine forecast fetch from NWS NDFD and the Open-Meteo Marine API.

`pandas` and `requests` are imported lazily inside the fetch functions so this
module stays importable in environments that lack them (the NDBC-aggregation
path — compute_forecast_analysis — has no such dependency).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Cardinal compass point → degrees (16-point), for parsing NWS windDirection.
CARDINAL_TO_DEG = {
    'N': 0, 'NNE': 22, 'NE': 45, 'ENE': 67,
    'E': 90, 'ESE': 112, 'SE': 135, 'SSE': 157,
    'S': 180, 'SSW': 202, 'SW': 225, 'WSW': 247,
    'W': 270, 'WNW': 292, 'NW': 315, 'NNW': 337,
}

# NWS API requires a descriptive User-Agent on every request.
_NWS_HEADERS = {"User-Agent": "GatewayLaunchOps/1.0 (offshore launch planning)"}
_OPENMETEO_MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
_OPENMETEO_WEATHER_URL = "https://api.open-meteo.com/v1/forecast"


def _speed_to_kts(text: Any) -> float:
    """
    Parse an NWS speed string ('15 mph', '15 kt', '10 to 15 mph') to knots.
    Ranges take the upper bound. Returns NaN when unparseable/empty.
    """
    if text is None:
        return float("nan")
    s = str(text).lower().strip()
    nums = re.findall(r"\d+\.?\d*", s)
    if not nums:
        return float("nan")
    val = float(nums[-1])   # upper bound of any range
    if "mph" in s:
        return val * 0.868976
    if "km/h" in s or "kph" in s:
        return val * 0.539957
    return val   # already knots (kt / kn / knot)


def fetch_nws_marine_forecast(
    lat: float,
    lon: float,
    timeout: int = 30,
):
    """
    Fetch the NWS NDFD hourly point forecast for lat/lon.

    Returns a DataFrame indexed by UTC timestamp with columns:
        wind_speed_kts, wind_gust_kts, wind_dir_deg, wave_height_m,
        forecast_source ('nws_ndfd')
    Returns None on any failure. NWS only covers U.S. waters — a 404 (or any
    HTTP error) is logged as a warning and yields None without raising.
    """
    try:
        import requests
        import pandas as pd
    except Exception as exc:                       # pragma: no cover
        logger.warning("fetch_nws_marine_forecast: missing dependency (%s)", exc)
        return None

    try:
        pts = requests.get(
            f"https://api.weather.gov/points/{lat},{lon}",
            headers=_NWS_HEADERS, timeout=timeout,
        )
        if pts.status_code != 200:
            logger.warning("NWS points %s,%s returned HTTP %s (likely outside "
                           "U.S. coverage)", lat, lon, pts.status_code)
            return None
        hourly_url = pts.json().get("properties", {}).get("forecastHourly")
        if not hourly_url:
            logger.warning("NWS points response had no forecastHourly URL")
            return None

        fc = requests.get(hourly_url, headers=_NWS_HEADERS, timeout=timeout)
        if fc.status_code != 200:
            logger.warning("NWS forecastHourly returned HTTP %s", fc.status_code)
            return None
        periods = fc.json().get("properties", {}).get("periods", [])
    except Exception as exc:
        logger.warning("fetch_nws_marine_forecast failed: %s", exc)
        return None

    rows = []
    for p in periods:
        ts = pd.to_datetime(p.get("startTime"), utc=True, errors="coerce")
        if ts is None or pd.isna(ts):
            continue
        gust = p.get("windGust")
        cardinal = (p.get("windDirection") or "").upper()
        wave = p.get("waveHeight")   # rarely present in NWS point forecasts
        rows.append({
            "timestamp":      ts,
            "wind_speed_kts": _speed_to_kts(p.get("windSpeed")),
            "wind_gust_kts":  _speed_to_kts(gust) if gust else float("nan"),
            "wind_dir_deg":   float(CARDINAL_TO_DEG[cardinal])
                              if cardinal in CARDINAL_TO_DEG else float("nan"),
            "wave_height_m":  float(wave) if isinstance(wave, (int, float)) else float("nan"),
            "forecast_source": "nws_ndfd",
        })

    if not rows:
        logger.warning("NWS forecast contained no usable periods")
        return None
    df = pd.DataFrame(rows).set_index("timestamp").sort_index()
    return df


def fetch_openmeteo_marine_forecast(
    lat: float,
    lon: float,
    forecast_days: int = 7,
    timeout: int = 30,
):
    """
    Fetch Open-Meteo Marine API hourly wave/swell forecast.

    Returns a DataFrame indexed by UTC timestamp with columns:
        wave_ht_m, wave_dir_deg, wave_period_s, swell_ht_m, swell_dir_deg,
        swell_period_s, wind_wave_ht_m, forecast_source ('openmeteo')
    Returns None on any failure (logged, never raised).
    """
    try:
        import requests
        import pandas as pd
    except Exception as exc:                       # pragma: no cover
        logger.warning("fetch_openmeteo_marine_forecast: missing dependency (%s)", exc)
        return None

    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join([
            "wave_height", "wave_direction", "wave_period",
            "swell_wave_height", "swell_wave_direction", "swell_wave_period",
            "wind_wave_height",
        ]),
        "forecast_days": forecast_days,
        "timezone": "UTC",
    }
    try:
        resp = requests.get(_OPENMETEO_MARINE_URL, params=params, timeout=timeout)
        if resp.status_code != 200:
            logger.warning("Open-Meteo Marine returned HTTP %s", resp.status_code)
            return None
        hourly = resp.json().get("hourly", {})
    except Exception as exc:
        logger.warning("fetch_openmeteo_marine_forecast failed: %s", exc)
        return None

    times = hourly.get("time")
    if not times:
        logger.warning("Open-Meteo response had no hourly time array")
        return None

    df = pd.DataFrame({
        "timestamp":      pd.to_datetime(times, utc=True, errors="coerce"),
        "wave_ht_m":      hourly.get("wave_height"),
        "wave_dir_deg":   hourly.get("wave_direction"),
        "wave_period_s":  hourly.get("wave_period"),
        "swell_ht_m":     hourly.get("swell_wave_height"),
        "swell_dir_deg":  hourly.get("swell_wave_direction"),
        "swell_period_s": hourly.get("swell_wave_period"),
        "wind_wave_ht_m": hourly.get("wind_wave_height"),
    })
    df["forecast_source"] = "openmeteo"
    df = df.set_index("timestamp").sort_index()
    return df


def fetch_openmeteo_weather_forecast(
    lat: float,
    lon: float,
    forecast_days: int = 2,
    timeout: int = 30,
):
    """
    Open-Meteo weather API — global hourly wind at lat/lon (fallback when NWS
    is unavailable outside U.S. waters).

    Returns DataFrame indexed by UTC with wind_speed_kts, wind_gust_kts,
    wind_dir_deg, forecast_source ('openmeteo_weather').
    """
    try:
        import requests
        import pandas as pd
    except Exception as exc:                       # pragma: no cover
        logger.warning("fetch_openmeteo_weather_forecast: missing dependency (%s)", exc)
        return None

    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "wind_speed_10m,wind_gusts_10m,wind_direction_10m",
        "wind_speed_unit": "kn",
        "forecast_days": max(1, forecast_days),
        "timezone": "UTC",
    }
    try:
        resp = requests.get(_OPENMETEO_WEATHER_URL, params=params, timeout=timeout)
        if resp.status_code != 200:
            logger.warning("Open-Meteo weather returned HTTP %s", resp.status_code)
            return None
        hourly = resp.json().get("hourly", {})
    except Exception as exc:
        logger.warning("fetch_openmeteo_weather_forecast failed: %s", exc)
        return None

    times = hourly.get("time")
    if not times:
        return None

    gust_raw = hourly.get("wind_gusts_10m") or [None] * len(times)

    df = pd.DataFrame({
        "timestamp": pd.to_datetime(times, utc=True, errors="coerce"),
        "wind_speed_kts": hourly.get("wind_speed_10m"),
        "wind_gust_kts": gust_raw,
        "wind_dir_deg": hourly.get("wind_direction_10m"),
    })
    df = df.set_index("timestamp").sort_index()
    df["forecast_source"] = "openmeteo_weather"
    return df


def fetch_combined_forecast(
    lat: float,
    lon: float,
    forecast_days: int = 7,
) -> dict:
    """
    Fetch site forecast and merge on UTC timestamps:
      • NWS NDFD wind (U.S. waters) OR Open-Meteo weather wind (global fallback)
      • Open-Meteo Marine wave/swell (global)

    Returns a dict: nws, openmeteo, openmeteo_weather, merged, forecast_start,
    forecast_end, lat, lon, nws_available, openmeteo_available,
    openmeteo_weather_available, wind_source.
    """
    nws = fetch_nws_marine_forecast(lat, lon)
    om  = fetch_openmeteo_marine_forecast(lat, lon, forecast_days=forecast_days)
    om_wx = None if nws is not None else fetch_openmeteo_weather_forecast(
        lat, lon, forecast_days=max(1, forecast_days),
    )

    merged = None
    wind_source = None
    _MERGED_COLS = [
        "wind_speed_kts", "wind_gust_kts", "wind_dir_deg",
        "wave_ht_m", "swell_ht_m", "swell_period_s", "swell_dir_deg",
    ]
    try:
        import pandas as pd
        frames = []
        if nws is not None:
            frames.append(nws[["wind_speed_kts", "wind_gust_kts", "wind_dir_deg"]])
            wind_source = "nws"
        elif om_wx is not None:
            frames.append(om_wx[["wind_speed_kts", "wind_gust_kts", "wind_dir_deg"]])
            wind_source = "openmeteo_weather"
        if om is not None:
            frames.append(om[["wave_ht_m", "swell_ht_m", "swell_period_s", "swell_dir_deg"]])
        if frames:
            merged = pd.concat(frames, axis=1, join="outer").sort_index()
            merged = merged.reindex(columns=_MERGED_COLS)
    except Exception as exc:                       # pragma: no cover
        logger.warning("fetch_combined_forecast merge failed: %s", exc)
        merged = None

    if merged is not None and len(merged):
        forecast_start = merged.index.min().to_pydatetime()
        forecast_end   = merged.index.max().to_pydatetime()
    else:
        forecast_start = forecast_end = datetime.now(timezone.utc)

    return {
        "nws":                 nws,
        "openmeteo":           om,
        "openmeteo_weather":   om_wx,
        "merged":              merged,
        "forecast_start":      forecast_start,
        "forecast_end":        forecast_end,
        "lat":                 lat,
        "lon":                 lon,
        "nws_available":       nws is not None,
        "openmeteo_available": om is not None,
        "openmeteo_weather_available": om_wx is not None,
        "wind_source":         wind_source,
    }


_CONFIDENCE = {24: 5, 48: 4, 72: 4, 120: 3, 168: 2}

_HORIZON_LABEL = {
    24:  "24-hour",
    48:  "48-hour",
    72:  "72-hour",
    120: "5-day",
    168: "7-day",
}

# GO/MARGINAL/NO-GO card thresholds (conservative defaults for the summary cards).
_WIND_GO       = 20.0   # kts
_WIND_MARGINAL = 25.0
_HS_GO         = 2.5    # m
_HS_MARGINAL   = 3.5


def _status_wind(v: float) -> str:
    if v < _WIND_GO:       return "GO"
    if v < _WIND_MARGINAL: return "MARGINAL"
    return "NO-GO"


def _status_hs(v: float) -> str:
    if v < _HS_GO:       return "GO"
    if v < _HS_MARGINAL: return "MARGINAL"
    return "NO-GO"


def _is_nan(x) -> bool:
    """True for None or a NaN float (avoids importing pandas/numpy)."""
    return x is None or (isinstance(x, float) and x != x)


def _slice_future_hours(merged, horizon_hours: int):
    """Return the next *horizon_hours* UTC hourly rows from *now*."""
    import pandas as pd

    work = merged.copy()
    if not isinstance(work.index, pd.DatetimeIndex):
        return work.head(horizon_hours)
    if work.index.tz is None:
        work.index = work.index.tz_localize("UTC")
    else:
        work.index = work.index.tz_convert("UTC")
    work = work.sort_index()
    now = pd.Timestamp.now(tz="UTC").floor("h")
    future = work[work.index >= now]
    if future.empty:
        future = work
    return future.iloc[:horizon_hours]


def _analyze_merged(combined: dict, merged, vehicle, horizon_hours: int) -> dict:
    """
    Per-hour forecast analysis from a merged model DataFrame (NWS or Open-Meteo
    wind + Open-Meteo wave/swell). Uses the next *horizon_hours* from now.
    """
    filtered = _slice_future_hours(merged, horizon_hours)
    period_hours = int(len(filtered))
    cols = set(filtered.columns)

    def _col(name):
        return filtered[name].tolist() if name in cols else [None] * period_hours

    ws = _col("wind_speed_kts")
    wg = _col("wind_gust_kts")
    wv = _col("wave_ht_m")
    sh = _col("swell_ht_m")
    sp = _col("swell_period_s")

    if vehicle is not None:
        limits = [
            (ws, getattr(vehicle, "max_wind_kts", None)),
            (wg, getattr(vehicle, "max_gust_kts", None)),
            (wv, getattr(vehicle, "max_hs_m", None)),
            (sh, getattr(vehicle, "max_swell_ht_m", None)),
            (sp, getattr(vehicle, "max_swell_period_s", None)),
        ]
    else:
        # No vehicle → conservative marginal thresholds for wind and Hs only.
        limits = [(ws, _WIND_MARGINAL), (wv, _HS_MARGINAL)]

    go_flags = []
    data_hours = 0
    for i in range(period_hours):
        ok = True
        checked = False
        for series, thr in limits:
            if thr is None:
                continue
            v = series[i]
            if _is_nan(v):
                continue
            checked = True
            if v > thr:
                ok = False
                break
        if checked:
            data_hours += 1
        go_flags.append(ok if checked else False)

    # Group contiguous GO hours into windows.
    go_windows: list[dict] = []
    start = None
    for i, flag in enumerate(go_flags):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            go_windows.append({"start_hour": start, "end_hour": i,
                               "duration_hours": i - start})
            start = None
    if start is not None:
        go_windows.append({"start_hour": start, "end_hour": period_hours,
                           "duration_hours": period_hours - start})

    total_go = sum(w["duration_hours"] for w in go_windows)
    target_hours = horizon_hours if horizon_hours > 0 else period_hours
    go_pct = round(total_go / target_hours * 100, 1) if target_hours > 0 else 0.0
    coverage_pct = round(data_hours / target_hours * 100, 1) if target_hours > 0 else 0.0

    def _mean(series):
        vals = [v for v in series if not _is_nan(v)]
        return sum(vals) / len(vals) if vals else None

    wind_mean = _mean(ws)
    wg_mean = _mean(wg)
    hs_mean = _mean(wv)
    swell_mean = _mean(sh)
    swell_p_mean = _mean(sp)
    confidence = _CONFIDENCE.get(horizon_hours, 2)
    horizon_label = _HORIZON_LABEL.get(horizon_hours, f"{horizon_hours}h")

    # Threshold shown alongside each card's value (Set 36, item 25) — matches
    # the same per-parameter limit used for the go_windows calculation above:
    # the vehicle's own threshold when given, else the conservative generic
    # default the status functions use internally.
    wind_limit = getattr(vehicle, "max_wind_kts", None) if vehicle is not None else None
    if wind_limit is None:
        wind_limit = _WIND_MARGINAL
    hs_limit = getattr(vehicle, "max_hs_m", None) if vehicle is not None else None
    if hs_limit is None:
        hs_limit = _HS_MARGINAL

    cards: list[dict] = []
    if wind_mean is not None:
        cards.append({"param": "Wind Speed", "value": f"{wind_mean:.1f} kts",
                      "status": _status_wind(wind_mean),
                      "threshold": f"limit {wind_limit:.1f} kts"})
    if wg_mean is not None and vehicle is not None:
        gl = getattr(vehicle, "max_gust_kts", None)
        if gl:
            cards.append({"param": "Wind Gust", "value": f"{wg_mean:.1f} kts",
                          "status": _status_wind(wg_mean),
                          "threshold": f"limit {gl:.1f} kts"})
    if hs_mean is not None:
        cards.append({"param": "Wave Height (Hs)", "value": f"{hs_mean:.2f} m",
                      "status": _status_hs(hs_mean),
                      "threshold": f"limit {hs_limit:.1f} m"})
    if swell_mean is not None and vehicle is not None:
        sl = getattr(vehicle, "max_swell_ht_m", None)
        if sl:
            cards.append({"param": "Swell Height", "value": f"{swell_mean:.2f} m",
                          "status": _status_hs(swell_mean),
                          "threshold": f"limit {sl:.1f} m"})

    return {
        "horizon_hours":  horizon_hours,
        "horizon_label":  horizon_label,
        "confidence":     confidence,
        "confidence_max": 5,
        "period_hours":   target_hours,
        "data_hours":     data_hours,
        "coverage_pct":   coverage_pct,
        "go_windows":     go_windows,
        "go_hours":       total_go,
        "total_hours":    target_hours,
        "go_pct":         go_pct,
        "wind_mean_kts":  wind_mean,
        "hs_mean_m":      hs_mean,
        "station_count":  combined.get("station_count", 0),
        "cards":          cards,
        "nws_available":       combined.get("nws_available", False),
        "openmeteo_available": combined.get("openmeteo_available", False),
        "wind_source":         combined.get("wind_source"),
        "data_source":         "site_forecast",
    }


def compute_forecast_analysis(
    combined: dict[str, Any],
    vehicle=None,
    horizon_hours: int = 72,
) -> dict:
    """
    Compute a forecast analysis. Two input shapes are supported:

      • Model forecast — *combined* has a non-empty 'merged' DataFrame (from
        fetch_combined_forecast). Produces per-hour GO windows and period_hours.
      • NDBC aggregation — *combined* is the aggregate_station_statistics() dict
        (no 'merged' key). Legacy behaviour, unchanged.

    horizon_hours: one of 24, 48, 72, 120, 168.
    vehicle:       optional Vehicle; when given, GO windows use its thresholds.
    """
    if not combined:
        return {}

    merged = combined.get("merged")
    if merged is not None:
        try:
            has_rows = len(merged) > 0
        except TypeError:
            has_rows = False
        if has_rows:
            return _analyze_merged(combined, merged, vehicle, horizon_hours)

    # ── Legacy NDBC aggregation-stats path ────────────────────────────────────
    confidence    = _CONFIDENCE.get(horizon_hours, 2)
    horizon_label = _HORIZON_LABEL.get(horizon_hours, f"{horizon_hours}h")

    wind_mean = combined.get("wind_speed_mean_kts")
    hs_mean   = combined.get("hs_mean_m")

    wind_limit = getattr(vehicle, "max_wind_kts", None) if vehicle is not None else None
    if wind_limit is None:
        wind_limit = _WIND_MARGINAL
    hs_limit = getattr(vehicle, "max_hs_m", None) if vehicle is not None else None
    if hs_limit is None:
        hs_limit = _HS_MARGINAL

    cards: list[dict] = []
    if wind_mean is not None:
        cards.append({"param": "Wind Speed",       "value": f"{wind_mean:.1f} kts", "status": _status_wind(wind_mean),
                      "threshold": f"limit {wind_limit:.1f} kts"})
    if hs_mean is not None:
        cards.append({"param": "Wave Height (Hs)", "value": f"{hs_mean:.2f} m",     "status": _status_hs(hs_mean),
                      "threshold": f"limit {hs_limit:.1f} m"})

    # Simple probability estimate from current observed means
    if wind_mean is None and hs_mean is None:
        go_pct   = None
        go_hours = None
    else:
        base = 1.0
        if wind_mean is not None:
            base *= max(0.0, min(1.0, 1.0 - wind_mean / _WIND_MARGINAL))
        if hs_mean is not None:
            base *= max(0.0, min(1.0, 1.0 - hs_mean / _HS_MARGINAL))
        conf_factor = confidence / 5.0
        go_pct   = round(base * 100 * (0.7 + 0.3 * conf_factor), 1)
        go_hours = round(go_pct / 100.0 * horizon_hours)

    return {
        "horizon_hours":  horizon_hours,
        "horizon_label":  horizon_label,
        "confidence":     confidence,
        "confidence_max": 5,
        "period_hours":   horizon_hours,
        "go_hours":       go_hours,
        "total_hours":    horizon_hours,
        "go_pct":         go_pct,
        "wind_mean_kts":  wind_mean,
        "hs_mean_m":      hs_mean,
        "station_count":  combined.get("station_count", 0),
        "cards":          cards,
    }

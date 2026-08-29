"""
modules/m2_weather/ndbc_history.py — Per-parameter NaN tracking and
multi-buoy aggregation via inverse-distance weighting.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import pandas as pd


# ── Per-parameter statistics ───────────────────────────────────────────────────

def compute_period_statistics(
    df: pd.DataFrame,
    period_days: int,
) -> dict:
    """
    Compute per-parameter statistics for the last *period_days* of data.

    *df* may have a DatetimeIndex or a 'timestamp' column.  Both timezone-aware
    and naive datetimes are handled (naive assumed UTC).

    Returns a dict keyed by parameter group.  Each group contains:
        has_data       — True if at least one non-NaN observation exists
        record_count   — count of valid (non-NaN) observations in window
        expected_count — period_days * 24  (one per hour)
        nan_pct        — (expected - actual) / expected * 100  (0–100)
        mean_{unit}    — float mean or None when has_data=False
        max_{unit}     — float max or None
        p90_{unit}     — float 90th-percentile or None
    """
    expected_count = period_days * 24

    # ── Normalise to DatetimeIndex ────────────────────────────────────────────
    work = df.copy()
    if "timestamp" in work.columns and not isinstance(work.index, pd.DatetimeIndex):
        work = work.set_index("timestamp")

    if isinstance(work.index, pd.DatetimeIndex) and len(work):
        cutoff_aware  = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=period_days)
        cutoff_naive  = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=period_days)
        if work.index.tz is not None:
            period_df = work[work.index >= cutoff_aware]
        else:
            period_df = work[work.index >= pd.Timestamp(cutoff_naive)]
    else:
        period_df = work

    # ── Helper ────────────────────────────────────────────────────────────────

    def _stats(col: str, unit: str) -> dict:
        """Build a parameter stats dict for one column."""
        base: dict = {
            "has_data":      False,
            "record_count":  0,
            "expected_count": expected_count,
            "nan_pct":       100.0,
            f"mean_{unit}":  None,
            f"max_{unit}":   None,
            f"p90_{unit}":   None,
        }

        if col not in period_df.columns:
            return base

        series = pd.to_numeric(period_df[col], errors="coerce").dropna()
        count  = len(series)

        if count == 0:
            return base

        nan_pct = max(0.0, (expected_count - count) / expected_count * 100) \
                  if expected_count > 0 else 0.0

        return {
            "has_data":      True,
            "record_count":  count,
            "expected_count": expected_count,
            "nan_pct":       nan_pct,
            f"mean_{unit}":  float(series.mean()),
            f"max_{unit}":   float(series.max()),
            f"p90_{unit}":   float(series.quantile(0.9)),
        }

    return {
        "wind_speed":   _stats("wspd_kts", "kts"),
        "wind_gust":    _stats("gst_kts",  "kts"),
        "wind_dir":     _stats("wdir_deg", "deg"),
        "wave_height":  _stats("wvht_m",   "m"),
        "swell_height": _stats("swh_m",    "m"),
        "swell_period": _stats("swp_s",    "s"),
    }


# ── Multi-window comparison ────────────────────────────────────────────────────

def _window_record_count(df: pd.DataFrame, period_days: int) -> int:
    """Count rows falling within the last *period_days* of the DataFrame."""
    work = df.copy()
    if "timestamp" in work.columns and not isinstance(work.index, pd.DatetimeIndex):
        work = work.set_index("timestamp")
    if isinstance(work.index, pd.DatetimeIndex) and len(work):
        if work.index.tz is not None:
            cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=period_days)
        else:
            cutoff = pd.Timestamp(datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=period_days))
        return int(len(work[work.index >= cutoff]))
    return int(len(work))


def compare_periods(
    df: pd.DataFrame,
    station_id: str,
    station_name: str = "",
) -> dict:
    """
    Return statistics for three overlapping trailing windows (15 / 30 / 45 days)
    from the same DataFrame.

    Each key '15', '30', '45' maps to the output of compute_period_statistics()
    for that window, OR None when the DataFrame holds fewer than 10% of the
    expected records for that window (expected = days * 24, e.g. a 15-day window
    needs >= 36 of 360). None (rather than a partial stats dict) lets callers
    do `if result['15'] is not None: …`.

    Returns:
        {'15': dict|None, '30': dict|None, '45': dict|None,
         'station_id': str, 'station_name': str}
    """
    result: dict = {"station_id": station_id, "station_name": station_name}
    for days in (15, 30, 45):
        expected = days * 24
        if _window_record_count(df, days) >= 0.10 * expected:
            result[str(days)] = compute_period_statistics(df, days)
        else:
            result[str(days)] = None
    return result


# ── Merge helper ──────────────────────────────────────────────────────────────

def _merge_met_spec(
    met_df: Optional[pd.DataFrame],
    spec_df: Optional[pd.DataFrame],
) -> pd.DataFrame:
    """
    Merge spectral columns (swh_m, swp_s, swd_deg) from spec_df into met_df.
    Uses nearest-match (≤1 h tolerance) on the timestamp index/column.
    Returns a copy of met_df (with or without added swell columns).
    """
    if met_df is None or met_df.empty:
        return pd.DataFrame()

    # Work with DatetimeIndex
    merged = met_df.copy()
    if "timestamp" in merged.columns and not isinstance(merged.index, pd.DatetimeIndex):
        merged = merged.set_index("timestamp")

    if spec_df is None or spec_df.empty:
        return merged

    spec = spec_df.copy()
    if "timestamp" in spec.columns and not isinstance(spec.index, pd.DatetimeIndex):
        spec = spec.set_index("timestamp")

    for col in ("swh_m", "swp_s", "swd_deg"):
        if col not in spec.columns:
            continue
        try:
            merged[col] = spec[col].reindex(
                merged.index, method="nearest",
                tolerance=pd.Timedelta("1h"),
            )
        except Exception:
            # Fall back to simple reindex without tolerance
            merged[col] = spec[col].reindex(merged.index)

    return merged


# ── Multi-station aggregation ─────────────────────────────────────────────────

def aggregate_station_statistics(
    station_data: dict[str, dict[str, Any]],
    forecast_hours: int = 168,
    include_for_wind:  Optional[set] = None,
    include_for_wave:  Optional[set] = None,
    include_for_swell: Optional[set] = None,
) -> dict:
    """
    Aggregate statistics from multiple NDBC stations using inverse-distance weighting.

    *station_data* format::

        {
          station_id: {
            "distance_nm": float,
            "met_df":      pd.DataFrame | None,
            "spec_df":     pd.DataFrame | None,
            "fetch_error": str | None,
          }
        }

    include_for_wind / include_for_wave / include_for_swell
        If provided, only station IDs in the set are considered for that
        parameter group (in addition to the normal has_data filter).
        Pass None to include all stations that have valid data.

    Returns a dict with per-parameter groups and backward-compat flat keys.
    """
    if not station_data:
        return {}

    period_days = max(1, forecast_hours // 24)
    all_ids     = list(station_data.keys())

    # ── Per-station statistics ────────────────────────────────────────────────
    station_stats: dict[str, dict] = {}
    for sid, data in station_data.items():
        if data.get("fetch_error"):
            station_stats[sid] = {}
            continue
        merged = _merge_met_spec(data.get("met_df"), data.get("spec_df"))
        station_stats[sid] = (
            compute_period_statistics(merged, period_days)
            if not merged.empty else {}
        )

    # ── Inverse-distance weight ───────────────────────────────────────────────
    def _w(sid: str) -> float:
        d = station_data[sid].get("distance_nm")
        return 1.0 / max(float(d), 0.001) if d else 1.0

    # ── Per-parameter aggregation ─────────────────────────────────────────────
    def _agg(
        param_key: str,
        mean_field: str,
        max_field:  str,
        p90_field:  str,
        include_set: Optional[set],
    ) -> dict:
        contributing: list[str] = []
        for sid in all_ids:
            ps = station_stats.get(sid, {}).get(param_key, {})
            if include_set is not None and sid not in include_set:
                continue
            if ps.get("has_data", False):
                contributing.append(sid)

        excluded = [s for s in all_ids if s not in contributing]

        if not contributing:
            return {
                "weighted_mean":       None,
                "network_max":         None,
                "network_p90":         None,
                "contributing_stations": [],
                "excluded_stations":   excluded,
                "message": "No stations have usable data for this period.",
            }

        weights = [_w(sid) for sid in contributing]
        w_total = sum(weights)

        means = [station_stats[sid][param_key][mean_field] for sid in contributing]
        maxes = [station_stats[sid][param_key][max_field]  for sid in contributing]
        p90s  = [
            station_stats[sid][param_key][p90_field]
            for sid in contributing
            if station_stats[sid][param_key].get(p90_field) is not None
        ]

        w_mean = sum(v * w for v, w in zip(means, weights) if v is not None) / w_total
        n_max  = max((v for v in maxes if v is not None), default=None)
        n_p90  = max(p90s) if p90s else None

        return {
            "weighted_mean":         w_mean,
            "network_max":           n_max,
            "network_p90":           n_p90,
            "contributing_stations": contributing,
            "excluded_stations":     excluded,
        }

    ws = _agg("wind_speed",   "mean_kts", "max_kts", "p90_kts", include_for_wind)
    wg = _agg("wind_gust",    "mean_kts", "max_kts", "p90_kts", include_for_wind)
    wh = _agg("wave_height",  "mean_m",   "max_m",   "p90_m",   include_for_wave)
    sh = _agg("swell_height", "mean_m",   "max_m",   "p90_m",   include_for_swell)
    sp = _agg("swell_period", "mean_s",   "max_s",   "p90_s",   include_for_swell)

    # Typed convenience aliases used by the aggregation result
    def _typed(base: dict, unit: str) -> dict:
        out = dict(base)
        out[f"weighted_mean_{unit}"] = base["weighted_mean"]
        out[f"network_max_{unit}"]   = base["network_max"]
        out[f"network_p90_{unit}"]   = base.get("network_p90")
        return out

    total_w = sum(_w(sid) for sid in all_ids)

    return {
        # Structured per-parameter blocks
        "wind_speed":   _typed(ws, "kts"),
        "wind_gust":    _typed(wg, "kts"),
        "wave_height":  _typed(wh, "m"),
        "swell_height": _typed(sh, "m"),
        "swell_period": _typed(sp, "s"),
        # Per-station raw stats (for symbol computation in the UI)
        "station_stats": station_stats,
        # Metadata
        "station_count": len(all_ids),
        "station_ids":   all_ids,
        "forecast_hours": forecast_hours,
        # Backward-compat flat keys (used by forecast.py)
        "wind_speed_mean_kts": ws["weighted_mean"],
        "wind_speed_max_kts":  ws["network_max"],
        "hs_mean_m":           wh["weighted_mean"],
        "hs_max_m":            wh["network_max"],
        "weights": {
            sid: _w(sid) / total_w for sid in all_ids
        },
    }


# ── Hourly GO-window analysis (observed NDBC data) ────────────────────────────

_HOURLY_PARAM_MAP = (
    ("wspd_kts", "max_wind_kts"),
    ("gst_kts",  "max_gust_kts"),
    ("wvht_m",   "max_hs_m"),
    ("swh_m",    "max_swell_ht_m"),
    ("swp_s",    "max_swell_period_s"),
)

_HORIZON_LABEL = {
    24:  "24-hour",
    48:  "48-hour",
    72:  "72-hour",
    120: "5-day",
    168: "7-day",
}


def _hourly_grid(horizon_hours: int) -> "pd.DatetimeIndex":
    """UTC hourly index covering the last *horizon_hours* (inclusive)."""
    end = pd.Timestamp.now(tz="UTC").floor("h")
    start = end - pd.Timedelta(hours=horizon_hours - 1)
    return pd.date_range(start, end, freq="h")


def _align_to_hourly_grid(frame: pd.DataFrame, horizon_hours: int) -> pd.DataFrame:
    """Resample buoy observations to UTC hourly means on a fixed look-back grid."""
    if frame.empty:
        return pd.DataFrame(index=_hourly_grid(horizon_hours), columns=frame.columns)

    work = frame.copy()
    if not isinstance(work.index, pd.DatetimeIndex):
        if "timestamp" in work.columns:
            work = work.set_index("timestamp")
        else:
            return pd.DataFrame(index=_hourly_grid(horizon_hours), columns=work.columns)

    if work.index.tz is None:
        work.index = pd.to_datetime(work.index).tz_localize("UTC")
    else:
        work.index = work.index.tz_convert("UTC")

    work = work.sort_index()
    hourly = work.resample("h").mean(numeric_only=True)
    grid = _hourly_grid(horizon_hours)
    return hourly.reindex(grid)


def _station_hourly_frame(
    data: dict,
    horizon_hours: int,
) -> pd.DataFrame:
    """Merge met+spec and align to an hourly UTC grid for the look-back window."""
    merged = _merge_met_spec(data.get("met_df"), data.get("spec_df"))
    if merged.empty:
        return merged
    return _align_to_hourly_grid(merged, horizon_hours)


def _blend_hourly_frames(
    station_data: dict[str, dict],
    horizon_hours: int,
    include_ids: Optional[set] = None,
) -> pd.DataFrame:
    """Inverse-distance weighted hourly blend across stations."""
    frames: list[tuple[pd.DataFrame, float]] = []
    for sid, data in station_data.items():
        if data.get("fetch_error"):
            continue
        if include_ids is not None and sid not in include_ids:
            continue
        frame = _station_hourly_frame(data, horizon_hours)
        if frame.empty:
            continue
        dist = data.get("distance_nm")
        weight = 1.0 / max(float(dist), 0.001) if dist else 1.0
        frames.append((frame, weight))

    if not frames:
        return pd.DataFrame()

    grid = _hourly_grid(horizon_hours)
    cols = [c for c, _ in _HOURLY_PARAM_MAP]
    out = pd.DataFrame(index=grid, columns=cols, dtype=float)
    for ts in grid:
        for col, _ in _HOURLY_PARAM_MAP:
            vals, weights = [], []
            for frame, w in frames:
                if ts not in frame.index or col not in frame.columns:
                    continue
                v = pd.to_numeric(frame.at[ts, col], errors="coerce")
                if pd.notna(v):
                    vals.append(float(v))
                    weights.append(w)
            if vals:
                out.at[ts, col] = sum(v * wt for v, wt in zip(vals, weights)) / sum(weights)
    return out


def analyze_hourly_go_window(
    station_data: dict[str, dict[str, Any]],
    horizon_hours: int = 72,
    vehicle=None,
    include_ids: Optional[set] = None,
) -> dict:
    """
    Count hours in the last *horizon_hours* where all available parameters
    meet the active vehicle's limits (inverse-distance blend when multiple
    stations are supplied).

    Returns the same keys used by the Forecast tab display
    (go_windows, period_hours, go_pct, cards, weights, …).
    """
    if not station_data:
        return {}

    blended = _blend_hourly_frames(station_data, horizon_hours, include_ids)
    if blended.empty:
        return {
            "horizon_hours": horizon_hours,
            "horizon_label": _HORIZON_LABEL.get(horizon_hours, f"{horizon_hours}h"),
            "period_hours": 0,
            "go_windows": [],
            "go_hours": 0,
            "go_pct": 0.0,
            "cards": [],
            "station_count": len(station_data),
            "weights": {},
        }

    period_hours = horizon_hours
    limits = []
    for col, attr in _HOURLY_PARAM_MAP:
        thr = getattr(vehicle, attr, None) if vehicle is not None else None
        limits.append((col, thr))

    go_flags: list[bool] = []
    data_hours = 0
    for i in range(period_hours):
        ok = True
        checked = False
        for col, thr in limits:
            if thr is None:
                continue
            v = blended.iloc[i][col] if col in blended.columns else float("nan")
            if pd.isna(v):
                continue
            checked = True
            if float(v) > float(thr):
                ok = False
                break
        if checked:
            data_hours += 1
        go_flags.append(ok if checked else False)

    go_windows: list[dict] = []
    start = None
    for i, flag in enumerate(go_flags):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            go_windows.append({
                "start_hour": start,
                "end_hour": i,
                "duration_hours": i - start,
            })
            start = None
    if start is not None:
        go_windows.append({
            "start_hour": start,
            "end_hour": period_hours,
            "duration_hours": period_hours - start,
        })

    total_go = sum(w["duration_hours"] for w in go_windows)
    coverage_pct = round(data_hours / period_hours * 100, 1) if period_hours > 0 else 0.0
    go_pct = round(total_go / period_hours * 100, 1) if period_hours > 0 else 0.0

    def _mean_col(col: str):
        s = pd.to_numeric(blended[col], errors="coerce").dropna()
        return float(s.mean()) if len(s) else None

    wind_mean = _mean_col("wspd_kts")
    hs_mean = _mean_col("wvht_m")

    from modules.m2_weather.forecast import _status_wind, _status_hs, _WIND_MARGINAL, _HS_MARGINAL

    wind_limit = getattr(vehicle, "max_wind_kts", None) if vehicle is not None else _WIND_MARGINAL
    hs_limit = getattr(vehicle, "max_hs_m", None) if vehicle is not None else _HS_MARGINAL

    cards: list[dict] = []
    if wind_mean is not None:
        cards.append({
            "param": "Wind Speed",
            "value": f"{wind_mean:.1f} kts",
            "status": _status_wind(wind_mean),
            "threshold": f"limit {wind_limit:.1f} kts",
        })
    if hs_mean is not None:
        cards.append({
            "param": "Wave Height (Hs)",
            "value": f"{hs_mean:.2f} m",
            "status": _status_hs(hs_mean),
            "threshold": f"limit {hs_limit:.1f} m",
        })

    total_w = sum(
        1.0 / max(float(d.get("distance_nm") or 1.0), 0.001)
        for d in station_data.values()
        if not d.get("fetch_error")
    )
    weights = {}
    for sid, d in station_data.items():
        if d.get("fetch_error"):
            continue
        w = 1.0 / max(float(d.get("distance_nm") or 1.0), 0.001)
        weights[sid] = w / total_w if total_w else 0.0

    return {
        "horizon_hours": horizon_hours,
        "horizon_label": _HORIZON_LABEL.get(horizon_hours, f"{horizon_hours}h"),
        "period_hours": period_hours,
        "data_hours": data_hours,
        "coverage_pct": coverage_pct,
        "go_windows": go_windows,
        "go_hours": total_go,
        "total_hours": period_hours,
        "go_pct": go_pct,
        "wind_mean_kts": wind_mean,
        "hs_mean_m": hs_mean,
        "station_count": len(station_data),
        "cards": cards,
        "weights": weights,
        "data_source": "ndbc_hourly",
    }

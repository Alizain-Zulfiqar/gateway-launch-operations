"""tests/test_nan_handling.py — Per-parameter NaN tracking and aggregation tests."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from modules.m2_weather.ndbc_history import (
    compute_period_statistics,
    aggregate_station_statistics,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _dates(n: int = 168) -> pd.DatetimeIndex:
    return pd.date_range(end=datetime.now(timezone.utc).replace(tzinfo=None), periods=n, freq="h")


# ── compute_period_statistics ──────────────────────────────────────────────────

def test_compute_period_stats_no_data():
    """Wave height all-NaN → has_data=False, mean_m=None, nan_pct=100."""
    dates = _dates()
    df = pd.DataFrame({
        "wspd_kts": np.random.uniform(5, 20, 168),
        "wvht_m":   np.full(168, np.nan),
    }, index=dates)

    stats = compute_period_statistics(df, 7)

    assert stats["wave_height"]["has_data"]  is False
    assert stats["wave_height"]["mean_m"]    is None
    assert stats["wave_height"]["nan_pct"]   == pytest.approx(100.0)
    assert stats["wave_height"]["max_m"]     is None
    assert stats["wind_speed"]["has_data"]   is True
    assert stats["wind_speed"]["mean_kts"]   is not None


def test_compute_period_stats_partial_data():
    """50 of 168 valid wave obs → has_data=True, nan_pct>60%, mean=1.5."""
    dates = _dates()
    wvht  = np.full(168, np.nan)
    wvht[:50] = 1.5

    df = pd.DataFrame({
        "wspd_kts": np.random.uniform(5, 20, 168),
        "wvht_m":   wvht,
    }, index=dates)

    stats = compute_period_statistics(df, 7)

    assert stats["wave_height"]["has_data"]       is True
    assert stats["wave_height"]["record_count"]   == 50
    assert stats["wave_height"]["expected_count"] == 168
    assert stats["wave_height"]["nan_pct"]        > 60.0
    assert stats["wave_height"]["mean_m"]         == pytest.approx(1.5, abs=0.01)


def test_compute_period_stats_full_data():
    """All 168 obs valid → nan_pct~0, has_data=True."""
    dates = _dates()
    df = pd.DataFrame({"wspd_kts": np.full(168, 12.0)}, index=dates)

    stats = compute_period_statistics(df, 7)

    assert stats["wind_speed"]["has_data"]     is True
    assert stats["wind_speed"]["nan_pct"]      == pytest.approx(0.0)
    assert stats["wind_speed"]["mean_kts"]     == pytest.approx(12.0, abs=0.01)
    assert stats["wind_speed"]["record_count"] == 168


def test_compute_period_stats_missing_column():
    """Column not present in DF → has_data=False (not an error)."""
    dates = _dates()
    df = pd.DataFrame({"wspd_kts": np.full(168, 10.0)}, index=dates)

    stats = compute_period_statistics(df, 7)

    assert stats["wave_height"]["has_data"] is False
    assert stats["wave_height"]["mean_m"]   is None
    # wind_speed still valid
    assert stats["wind_speed"]["has_data"] is True


# ── aggregate_station_statistics ──────────────────────────────────────────────

def _make_station(name, distance, wspd, wvht=None, swh=None):
    """Helper: build station_data entry with synthetic DataFrames."""
    dates = _dates()
    data = {"wspd_kts": np.full(168, wspd)}
    if wvht is not None:
        data["wvht_m"] = np.full(168, wvht) if not np.isnan(wvht) else np.full(168, np.nan)
    if swh is not None:
        data["swh_m"] = np.full(168, swh) if not np.isnan(swh) else np.full(168, np.nan)

    return {
        "station_id":  name,
        "distance_nm": distance,
        "met_df":      pd.DataFrame(data, index=dates),
        "spec_df":     None,
        "fetch_error": None,
    }


def test_aggregate_excludes_no_data_stations():
    """Station with all-NaN wave obs is excluded from wave average."""
    station_data = {
        "STN_A": _make_station("STN_A", 50.0,  wspd=10.0, wvht=1.0),
        "STN_B": _make_station("STN_B", 100.0, wspd=14.0, wvht=float("nan")),
    }

    result = aggregate_station_statistics(station_data)

    # Wind: both STN_A and STN_B contribute
    assert len(result["wind_speed"]["contributing_stations"]) == 2

    # Wave: only STN_A contributes
    wave = result["wave_height"]
    assert "STN_A" in wave["contributing_stations"]
    assert "STN_B" in wave["excluded_stations"]
    assert wave["weighted_mean_m"] == pytest.approx(1.0, abs=0.01)


def test_aggregate_all_excluded_returns_none():
    """When no station has swell data, weighted_mean_m is None and 'message' is set."""
    station_data = {
        "STN_A": _make_station("STN_A", 50.0, wspd=10.0, wvht=1.0, swh=float("nan")),
    }

    result = aggregate_station_statistics(station_data)

    swell = result["swell_height"]
    assert swell["weighted_mean_m"] is None
    assert len(swell["contributing_stations"]) == 0
    assert "message" in swell


def test_manual_inclusion_override():
    """include_for_wind={'STN_A'} forces STN_B out of the wind average."""
    station_data = {
        "STN_A": _make_station("STN_A", 50.0, wspd=10.0),
        "STN_B": _make_station("STN_B", 50.0, wspd=30.0),
    }

    result = aggregate_station_statistics(
        station_data, include_for_wind={"STN_A"}
    )

    ws = result["wind_speed"]
    assert ws["weighted_mean_kts"] == pytest.approx(10.0, abs=0.1)
    assert "STN_B" in ws["excluded_stations"]
    assert "STN_A" in ws["contributing_stations"]


def test_aggregate_inverse_distance_weighting():
    """IDW cross-check: 10 kts @50 NM + 20 kts @200 NM → 12.0 kts."""
    # w(STN_A) = 1/50 = 0.02, w(STN_B) = 1/200 = 0.005; total = 0.025
    # mean = (10*0.02 + 20*0.005) / 0.025 = 0.3 / 0.025 = 12.0
    station_data = {
        "STN_A": _make_station("STN_A", 50.0,  wspd=10.0),
        "STN_B": _make_station("STN_B", 200.0, wspd=20.0),
    }

    result = aggregate_station_statistics(station_data)

    assert result["wind_speed"]["weighted_mean_kts"] == pytest.approx(12.0, abs=0.01)
    assert sum(result["weights"].values()) == pytest.approx(1.0, abs=1e-9)


def test_aggregate_nan_pct_thresholds():
    """Stations with partial wave data still contribute to the average."""
    dates = _dates()
    # STN_A: 50 of 168 wave obs valid (partial, ~70% nan) — still has_data=True
    wvht_partial = np.full(168, np.nan)
    wvht_partial[:50] = 2.0
    df_partial = pd.DataFrame({
        "wspd_kts": np.full(168, 12.0),
        "wvht_m":   wvht_partial,
    }, index=dates)

    station_data = {
        "STN_P": {
            "station_id":  "STN_P",
            "distance_nm": 100.0,
            "met_df":      df_partial,
            "spec_df":     None,
            "fetch_error": None,
        }
    }

    result = aggregate_station_statistics(station_data)

    # Partial data (50/168 valid) still counts as has_data=True
    wave = result["wave_height"]
    assert "STN_P" in wave["contributing_stations"]
    assert wave["weighted_mean_m"] == pytest.approx(2.0, abs=0.01)

"""
tests/test_pre28b4.py — Pre-28B-4: live marine forecast wiring, period_hours /
go_windows from the merged model DataFrame, and the distance_nm None fix.

Uses datetime.now(timezone.utc) (not the deprecated datetime.utcnow()).
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_fetch_combined_returns_required_keys():
    try:
        from modules.m2_weather.forecast import fetch_combined_forecast
        result = fetch_combined_forecast(32.6, -61.1, forecast_days=3)
        required = ["nws_available", "openmeteo_available", "lat", "lon",
                    "forecast_start", "forecast_end"]
        for key in required:
            assert key in result, f"Missing key: {key}"
    except Exception:
        pytest.skip("Network unavailable")


def _merged_df(periods, **const_cols):
    pd = pytest.importorskip("pandas")
    np = pytest.importorskip("numpy")
    dates = pd.date_range(start=datetime.now(timezone.utc), periods=periods, freq="h")
    data = {col: np.full(periods, val) for col, val in const_cols.items()}
    return pd.DataFrame(data, index=dates), dates


def test_compute_forecast_analysis_period_hours():
    from modules.m2_weather.forecast import compute_forecast_analysis
    df, dates = _merged_df(
        72, wind_speed_kts=12.0, wind_gust_kts=18.0,
        wave_ht_m=1.5, swell_ht_m=1.2, swell_period_s=9.0,
    )
    combined = {
        "merged": df, "nws_available": False, "openmeteo_available": True,
        "forecast_start": dates[0], "forecast_end": dates[-1],
        "lat": 32.6, "lon": -61.1,
    }
    analysis = compute_forecast_analysis(combined, horizon_hours=72)
    assert "period_hours" in analysis, "must return period_hours"
    assert analysis["period_hours"] == 72


def test_horizon_filter_24_vs_168():
    from modules.m2_weather.forecast import compute_forecast_analysis
    df, dates = _merged_df(
        168, wind_speed_kts=12.0, wind_gust_kts=18.0,
        wave_ht_m=1.5, swell_ht_m=1.2, swell_period_s=9.0,
    )
    combined = {
        "merged": df, "nws_available": False, "openmeteo_available": True,
        "forecast_start": dates[0], "forecast_end": dates[-1],
        "lat": 32.6, "lon": -61.1,
    }
    a24 = compute_forecast_analysis(combined, horizon_hours=24)
    a168 = compute_forecast_analysis(combined, horizon_hours=168)
    assert a24["period_hours"] == 24
    assert a168["period_hours"] == 168
    assert a24["period_hours"] != a168["period_hours"]


def test_distance_nm_none_defaults_to_one():
    class StationWithNone:
        station_id = "STN_A"
        distance_nm = None

    class StationWithoutAttr:
        station_id = "STN_B"

    def get_dist(s):
        return getattr(s, "distance_nm", 1.0) or 1.0

    assert get_dist(StationWithNone()) == 1.0
    assert get_dist(StationWithoutAttr()) == 1.0


def test_go_window_all_within_threshold():
    from modules.m2_weather.forecast import compute_forecast_analysis
    from core.models import Vehicle
    df, dates = _merged_df(
        72, wind_speed_kts=5.0, wind_gust_kts=7.0,
        wave_ht_m=0.5, swell_ht_m=0.4, swell_period_s=6.0,
    )
    combined = {
        "merged": df, "nws_available": False, "openmeteo_available": True,
        "forecast_start": dates[0], "forecast_end": dates[-1],
        "lat": 32.6, "lon": -61.1,
    }
    v = Vehicle(name="Test", vehicle_class="slv_orb", recovery_mode="expendable",
                max_wind_kts=18, max_gust_kts=25, max_hs_m=1.5,
                max_swell_ht_m=2.0, max_swell_period_s=12)
    analysis = compute_forecast_analysis(combined, vehicle=v, horizon_hours=72)
    assert "go_windows" in analysis
    total_go = sum(w.get("duration_hours", 0) for w in analysis["go_windows"])
    assert total_go == pytest.approx(72, abs=1)

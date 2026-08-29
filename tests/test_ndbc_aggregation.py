"""tests/test_ndbc_aggregation.py — Aggregation and session-state tests."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

import core.database as db_mod


@pytest.fixture()
def db_file(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture(autouse=True)
def _patch_db(db_file, monkeypatch):
    monkeypatch.setattr(db_mod, "DB_PATH", str(db_file))
    db_mod.init_db()


def _station_df(wspd: float, wvht: float | None = None) -> pd.DataFrame:
    """Build a 168-row hourly DataFrame for use in station_data."""
    dates = pd.date_range(end=datetime.now(timezone.utc).replace(tzinfo=None), periods=168, freq="h")
    data: dict = {"wspd_kts": np.full(168, wspd)}
    if wvht is not None:
        data["wvht_m"] = np.full(168, wvht)
    return pd.DataFrame(data, index=dates)


def test_aggregate_weights_inverse_distance():
    """Inverse-distance weighted mean: 10 kts @50 NM + 20 kts @200 NM → 12.0 kts."""
    from modules.m2_weather.ndbc_history import aggregate_station_statistics

    # w(41009) = 1/50 = 0.02, w(41047) = 1/200 = 0.005, total = 0.025
    # weighted mean = (10*0.02 + 20*0.005) / 0.025 = (0.2 + 0.1) / 0.025 = 12.0
    station_data = {
        "41009": {
            "distance_nm":  50.0,
            "met_df":       _station_df(10.0, wvht=0.8),
            "spec_df":      None,
            "fetch_error":  None,
        },
        "41047": {
            "distance_nm":  200.0,
            "met_df":       _station_df(20.0, wvht=2.0),
            "spec_df":      None,
            "fetch_error":  None,
        },
    }

    agg = aggregate_station_statistics(station_data)

    # Backward-compat flat key
    assert agg["wind_speed_mean_kts"] == pytest.approx(12.0, abs=0.01)
    # Network max = max of both station maxes (both constant so max = their value)
    assert agg["wind_speed_max_kts"]  == pytest.approx(20.0, abs=0.01)
    assert agg["station_count"] == 2
    assert set(agg["station_ids"]) == {"41009", "41047"}

    # Weights should sum to 1.0
    assert sum(agg["weights"].values()) == pytest.approx(1.0, abs=1e-9)


def test_session_state_round_trip():
    """get_session / set_session round-trip through session_state table."""
    import json
    from core.settings import get_session, set_session

    ids = ["41009", "41047", "41060"]
    set_session("selected_ndbc_stations", json.dumps(ids))

    raw = get_session("selected_ndbc_stations")
    assert raw is not None
    assert json.loads(raw) == ids

    # Overwrite and verify update
    set_session("selected_ndbc_stations", json.dumps(["41009"]))
    assert json.loads(get_session("selected_ndbc_stations")) == ["41009"]

    # Missing key returns default
    assert get_session("nonexistent_key", "default") == "default"


def test_forecast_horizon_filtering():
    """compute_forecast_analysis returns correct horizon metadata."""
    from modules.m2_weather.ndbc_history import aggregate_station_statistics
    from modules.m2_weather.forecast import compute_forecast_analysis

    station_data = {
        "41009": {
            "distance_nm": 50.0,
            "met_df":      _station_df(10.0, wvht=1.2),
            "spec_df":     None,
            "fetch_error": None,
        },
    }

    for horizon in [24, 48, 72, 120, 168]:
        agg    = aggregate_station_statistics(station_data, forecast_hours=horizon)
        result = compute_forecast_analysis(agg, horizon_hours=horizon)

        assert result["horizon_hours"]  == horizon
        assert result["total_hours"]    == horizon
        assert result["confidence_max"] == 5
        assert 1 <= result["confidence"] <= 5

    # 72h should have confidence 4
    agg72  = aggregate_station_statistics(station_data, forecast_hours=72)
    res72  = compute_forecast_analysis(agg72, horizon_hours=72)
    assert res72["confidence"] == 4

    # 168h should have confidence 2
    agg168 = aggregate_station_statistics(station_data, forecast_hours=168)
    res168 = compute_forecast_analysis(agg168, horizon_hours=168)
    assert res168["confidence"] == 2

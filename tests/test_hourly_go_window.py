"""Tests for hourly NDBC GO-window analysis and verdict threshold settings."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from core import database as db_mod
from core.verdict_thresholds import classify_verdict, get_go_threshold, get_marginal_threshold
from modules.m2_weather.ndbc_history import analyze_hourly_go_window


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(db_mod, "DB_PATH", str(db_file))
    db_mod.init_db()


def _make_met(hours: int, wspd: float) -> pd.DataFrame:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    idx = [now - timedelta(hours=h) for h in range(hours - 1, -1, -1)]
    return pd.DataFrame({"wspd_kts": [wspd] * hours, "gst_kts": [wspd + 2] * hours,
                         "wvht_m": [1.0] * hours}, index=idx)


class _Vehicle:
    max_wind_kts = 20.0
    max_gust_kts = 25.0
    max_hs_m = 3.0
    max_swell_ht_m = 2.0
    max_swell_period_s = 20.0


def test_analyze_hourly_go_window_counts_go_hours():
    station_data = {
        "41009": {
            "distance_nm": 10.0,
            "met_df": _make_met(24, 15.0),
            "spec_df": None,
            "fetch_error": None,
        }
    }
    result = analyze_hourly_go_window(station_data, horizon_hours=24, vehicle=_Vehicle())
    assert result["period_hours"] == 24
    assert result["go_hours"] == 24
    assert result["go_pct"] == 100.0


def test_analyze_hourly_go_window_exceeding_wind_not_go():
    station_data = {
        "41009": {
            "distance_nm": 10.0,
            "met_df": _make_met(24, 30.0),
            "spec_df": None,
            "fetch_error": None,
        }
    }
    result = analyze_hourly_go_window(station_data, horizon_hours=24, vehicle=_Vehicle())
    assert result["go_hours"] == 0
    assert result["go_pct"] == 0.0


def test_classify_verdict_uses_settings(monkeypatch):
    from core.settings import set_setting
    set_setting("go_threshold", "0.80")
    set_setting("marginal_threshold", "0.60")
    assert get_go_threshold() == 0.80
    assert get_marginal_threshold() == 0.60
    assert classify_verdict(0.85) == "GO"
    assert classify_verdict(0.65) == "MARGINAL"
    assert classify_verdict(0.55) == "NO-GO"

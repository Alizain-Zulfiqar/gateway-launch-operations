"""Tests for modules/m2_weather/operability.py"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.m2_weather.operability import (
    compute_operability_from_df,
    classify_pct,
    classify_days,
    build_operability_heatmaps,
    build_operability_heatmaps_for_site,
    REF_WIND_KTS,
    REF_HS_M,
)
from core.models import Site


def _sample_df():
    ts = pd.date_range("2024-06-01", periods=48, freq="h", tz="UTC")
    return pd.DataFrame({
        "timestamp": ts,
        "wind_speed_kts": [10.0] * 40 + [30.0] * 8,
        "wave_hgt_m": [1.0] * 48,
        "swell_hgt_m": [0.5] * 48,
    })


class TestComputeOperability:
    def test_pct_and_days(self):
        pct, days = compute_operability_from_df(_sample_df(), REF_WIND_KTS, REF_HS_M)
        assert pct is not None
        assert 0 <= pct <= 100
        assert days is not None
        assert days >= 0

    def test_all_favorable(self):
        ts = pd.date_range("2024-07-01", periods=24, freq="h", tz="UTC")
        df = pd.DataFrame({
            "timestamp": ts,
            "wind_speed_kts": [15.0] * 24,
            "wave_hgt_m": [1.0] * 24,
            "swell_hgt_m": [0.3] * 24,
        })
        pct, days = compute_operability_from_df(df, REF_WIND_KTS, REF_HS_M)
        assert pct == 100.0
        assert days >= 1


class TestClassification:
    def test_pct_tiers(self, monkeypatch):
        monkeypatch.setattr(
            "core.verdict_thresholds.get_go_threshold", lambda: 0.70,
        )
        monkeypatch.setattr(
            "core.verdict_thresholds.get_marginal_threshold", lambda: 0.50,
        )
        assert classify_pct(85) == "optimal"
        assert classify_pct(55) == "marginal"
        assert classify_pct(30) == "suboptimal"

    def test_days_tiers(self):
        assert classify_days(28) == "optimal"
        assert classify_days(18) == "marginal"
        assert classify_days(5) == "suboptimal"


class TestBuildHeatmaps:
    def test_empty_when_no_cache(self, tmp_path, monkeypatch):
        import core.database as db_mod
        db = tmp_path / "oper.db"
        monkeypatch.setattr("config.DB_PATH", str(db))
        monkeypatch.setattr(db_mod, "DB_PATH", str(db))
        db_mod.init_db()
        site = Site(lat=28.5, lon=-80.5, bbox_nm=25.0)
        hm = build_operability_heatmaps(site, 2021, 2022)
        assert hm.months_cached == 0
        assert len(hm.years) == 2

    def test_build_for_site_uses_ten_years(self, tmp_path, monkeypatch):
        import core.database as db_mod
        from modules.m2_weather.operability import (
            OPERABILITY_YEARS,
            build_operability_heatmaps_for_site,
            era5_operability_year_range,
        )

        db = tmp_path / "oper2.db"
        monkeypatch.setattr("config.DB_PATH", str(db))
        monkeypatch.setattr(db_mod, "DB_PATH", str(db))
        db_mod.init_db()
        site = Site(lat=28.5, lon=-80.5, bbox_nm=25.0)
        hm = build_operability_heatmaps_for_site(site)
        ys, ye = era5_operability_year_range()
        assert ye - ys + 1 == OPERABILITY_YEARS
        assert hm.years == list(range(ys, ye + 1))

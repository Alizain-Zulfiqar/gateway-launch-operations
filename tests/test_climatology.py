"""Tests for modules/m2_weather/climatology.py and era5_cache.py"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import Site
from modules.m2_weather.climatology import (
    CLIMATOLOGY_YEARS,
    build_monthly_climatology,
    climatology_year_range,
)
from modules.m2_weather.era5_cache import (
    era5_cache_progress,
    save_cached_era5_month,
)


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    import core.database as db_mod

    db = tmp_path / "clim.db"
    monkeypatch.setattr("config.DB_PATH", str(db))
    monkeypatch.setattr(db_mod, "DB_PATH", str(db))
    db_mod.init_db()
    return db


class TestClimatologyYearRange:
    def test_five_years(self):
        ys, ye = climatology_year_range()
        assert ye - ys + 1 == CLIMATOLOGY_YEARS


class TestEra5Cache:
    def test_save_and_progress(self, isolated_db):
        save_cached_era5_month(28.5, -80.5, "2024-06-01", {
            "ws_mean_kts": 12.0,
            "sh_mean_m": 1.2,
            "swh_mean_m": 0.8,
            "swp_mean_s": 9.0,
            "wg_mean_kts": 18.0,
            "record_count": 1,
        })
        cached, total = era5_cache_progress(28.5, -80.5, 2024, 2024)
        assert cached == 1
        assert total == 12


class TestBuildMonthlyClimatology:
    def test_pools_era5_by_calendar_month(self, isolated_db):
        for yr in (2023, 2024):
            save_cached_era5_month(28.5, -80.5, f"{yr}-06-01", {
                "ws_mean_kts": 10.0 + yr - 2023,
                "sh_mean_m": 1.0,
                "swh_mean_m": 0.5,
                "swp_mean_s": 8.0,
                "wg_mean_kts": 15.0,
                "record_count": 1,
            })
        site = Site(lat=28.5, lon=-80.5, bbox_nm=25.0)
        clim = build_monthly_climatology(site, 2023, 2024)
        june_ws = clim.by_month[6].get("ws", {}).get("mean")
        assert june_ws == pytest.approx(10.5, abs=0.01)
        assert clim.years == (2023, 2024)

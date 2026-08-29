"""Tests for modules/m2_weather/ncei_download.py"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.m2_weather.ncei_download import (
    month_has_operability_cache,
    month_needs_fetch,
    operability_cache_progress,
)


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    import core.database as db_mod

    db = tmp_path / "ncei_dl.db"
    monkeypatch.setattr("config.DB_PATH", str(db))
    monkeypatch.setattr(db_mod, "DB_PATH", str(db))
    db_mod.init_db()
    return db


class TestMonthNeedsFetch:
    def test_missing_row(self, isolated_db):
        assert month_needs_fetch("40,39,41,42", "2024-01-01") is True

    def test_row_without_operability(self, isolated_db, monkeypatch):
        from modules.m2_weather.ncei import save_cached_month

        bbox = "40,39,41,42"
        save_cached_month(bbox, "2024-01-01", {
            "ws_mean_kts": 10.0,
            "ws_p90_kts": 15.0,
            "ws_max_kts": 20.0,
            "wdir_mean_deg": 180.0,
            "wave_hgt_mean_m": 1.0,
            "wave_hgt_p90_m": 1.5,
            "wave_dir_mean_deg": 90.0,
            "swell_hgt_mean_m": 0.5,
            "swell_dir_mean_deg": 100.0,
            "record_count": 100,
            "pct_both_criteria": None,
            "n_fully_operable_days": None,
        })
        assert month_needs_fetch(bbox, "2024-01-01") is True

    def test_row_with_operability(self, isolated_db):
        from modules.m2_weather.ncei import save_cached_month

        bbox = "40,39,41,42"
        save_cached_month(bbox, "2024-01-01", {
            "ws_mean_kts": 10.0,
            "ws_p90_kts": 15.0,
            "ws_max_kts": 20.0,
            "wdir_mean_deg": 180.0,
            "wave_hgt_mean_m": 1.0,
            "wave_hgt_p90_m": 1.5,
            "wave_dir_mean_deg": 90.0,
            "swell_hgt_mean_m": 0.5,
            "swell_dir_mean_deg": 100.0,
            "record_count": 100,
            "pct_both_criteria": 55.0,
            "n_fully_operable_days": 12,
        })
        assert month_needs_fetch(bbox, "2024-01-01") is False


class TestMonthHasOperabilityCache:
    def test_tiers(self):
        assert month_has_operability_cache(None) is False
        assert month_has_operability_cache({"pct_both_criteria": 50.0}) is True
        assert month_has_operability_cache({"n_fully_operable_days": 5}) is True
        assert month_has_operability_cache({"ws_mean_kts": 10.0}) is False


class TestOperabilityCacheProgress:
    def test_counts(self, isolated_db):
        from modules.m2_weather.ncei import save_cached_month

        bbox = "28,-81,29,-80"
        save_cached_month(bbox, "2024-01-01", {
            "ws_mean_kts": 10.0,
            "ws_p90_kts": 15.0,
            "ws_max_kts": 20.0,
            "wdir_mean_deg": 180.0,
            "wave_hgt_mean_m": 1.0,
            "wave_hgt_p90_m": 1.5,
            "wave_dir_mean_deg": 90.0,
            "swell_hgt_mean_m": 0.5,
            "swell_dir_mean_deg": 100.0,
            "record_count": 100,
            "pct_both_criteria": 60.0,
            "n_fully_operable_days": 10,
        })
        done, total = operability_cache_progress(bbox, 2024, 2024)
        assert total == 12
        assert done == 1

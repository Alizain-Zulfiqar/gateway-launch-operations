"""Tests for era5_daily_cache helpers."""
from __future__ import annotations

import pytest

from modules.m2_weather.era5_daily_cache import (
    era5_daily_complete,
    era5_daily_month_progress,
    get_cached_era5_day,
    save_cached_era5_day,
)


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    import core.database as db_mod

    db_file = tmp_path / "daily_cache.db"
    monkeypatch.setattr(db_mod, "DB_PATH", str(db_file))
    db_mod.init_db()


def _sample_day(**overrides):
    base = {
        "ws_mean_kts": 12.0,
        "wg_max_kts": 18.0,
        "sh_mean_m": 1.2,
        "swh_mean_m": 1.0,
        "swp_mean_s": 10.0,
        "n_hours": 24,
    }
    base.update(overrides)
    return base


def test_era5_daily_complete_requires_fields_and_hours():
    assert era5_daily_complete(_sample_day()) is True
    assert era5_daily_complete(_sample_day(n_hours=10)) is False
    assert era5_daily_complete(_sample_day(ws_mean_kts=None)) is False


def test_save_and_load_daily_row():
    save_cached_era5_day(28.5, -80.5, "2023-06-15", _sample_day())
    row = get_cached_era5_day(28.5, -80.5, "2023-06-15")
    assert row is not None
    assert row["ws_mean_kts"] == 12.0
    assert row["n_hours"] == 24


def test_month_progress_counts_complete_days():
    for day in range(1, 31):
        save_cached_era5_day(28.5, -80.5, f"2023-06-{day:02d}", _sample_day())
    cached, total = era5_daily_month_progress(28.5, -80.5, 2023, 6)
    assert total == 30
    assert cached == 30

"""Tests for mission_windows streak logic."""
from __future__ import annotations

import pytest

from modules.m3_probability.mission_windows import (
    day_meets_criteria,
    find_go_streaks,
    GoStreak,
)
from config import DEFAULT_THRESHOLDS


def test_find_go_streaks_single_run():
    mask = [False, True, True, True, False, True, False]
    streaks = find_go_streaks(mask)
    assert streaks == [
        GoStreak(2, 4, 3),
        GoStreak(6, 6, 1),
    ]


def test_find_go_streaks_ends_on_go():
    mask = [True, True, False]
    streaks = find_go_streaks(mask)
    assert streaks == [GoStreak(1, 2, 2)]


def test_find_go_streaks_none():
    assert find_go_streaks([False, False]) == []


def test_day_meets_criteria_all_pass():
    row = {
        "ws_mean_kts": 15.0,
        "wg_max_kts": 20.0,
        "sh_mean_m": 1.5,
        "swh_mean_m": 2.0,
        "swp_mean_s": 12.0,
    }
    params = ["ws", "wg", "sh", "swh", "swp"]
    assert day_meets_criteria(row, DEFAULT_THRESHOLDS, params) is True


def test_day_meets_criteria_wind_fail():
    row = {
        "ws_mean_kts": 25.0,
        "wg_max_kts": 20.0,
        "sh_mean_m": 1.5,
        "swh_mean_m": 2.0,
        "swp_mean_s": 12.0,
    }
    assert day_meets_criteria(row, DEFAULT_THRESHOLDS, ["ws"]) is False


def test_analyze_mission_windows_with_cached_daily(monkeypatch, tmp_path):
    """End-to-end streak stats using mocked daily cache (no CDS)."""
    import core.database as db_mod
    from core.models import Site
    from modules.m2_weather.era5_daily_cache import save_cached_era5_day

    db_file = tmp_path / "mission.db"
    monkeypatch.setattr(db_mod, "DB_PATH", str(db_file))
    db_mod.init_db()

    site = Site(name="Test", lat=28.5, lon=-80.5, bbox_nm=25.0)

    # June 2023: days 1-5 GO, day 6 NO-GO, days 7-9 GO
    for day in range(1, 10):
        ws = 12.0 if day != 6 else 30.0
        save_cached_era5_day(
            site.lat, site.lon, f"2023-06-{day:02d}",
            {
                "ws_mean_kts": ws,
                "wg_max_kts": 18.0,
                "sh_mean_m": 1.2,
                "swh_mean_m": 1.0,
                "swp_mean_s": 10.0,
                "n_hours": 24,
            },
        )

    def _fake_range(duration, as_of=None):
        return 2023, 2023

    def _fake_ensure(lat, lon, month, duration, *, on_progress=None):
        if on_progress:
            on_progress(9, 9, "done")
        return True, None

    monkeypatch.setattr(
        "modules.m3_probability.mission_windows.ensure_era5_daily_duration",
        _fake_ensure,
    )
    monkeypatch.setattr(
        "modules.m3_probability.mission_windows.mission_timing_year_range",
        _fake_range,
    )

    from modules.m3_probability.mission_windows import analyze_mission_windows

    result = analyze_mission_windows(site, 6, 1)
    assert result.max_streak_ever == 5
    assert len(result.years) == 1
    assert result.years[0].max_streak == 5
    assert result.years[0].num_streaks == 2

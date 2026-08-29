"""Tests for modules/m2_weather/era5_ensure.py"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.m2_weather.era5_cache import era5_cache_progress, save_cached_era5_month


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    import core.database as db_mod

    db = tmp_path / "era5_ensure.db"
    monkeypatch.setattr("config.DB_PATH", str(db))
    monkeypatch.setattr(db_mod, "DB_PATH", str(db))
    db_mod.init_db()
    return db


def _full_month(ws=12.0):
    return {
        "ws_mean_kts": ws,
        "sh_mean_m": 1.0,
        "swh_mean_m": 0.5,
        "swp_mean_s": 8.0,
        "wg_mean_kts": 15.0,
        "record_count": 1,
    }


class TestEnsureEra5Cache:
    def test_skips_fetch_when_cache_complete(self, isolated_db, monkeypatch):
        from modules.m2_weather import era5_ensure as mod

        for mo in range(1, 13):
            save_cached_era5_month(28.5, -80.5, f"2024-{mo:02d}-01", _full_month())

        calls = []

        def _fake_fetch(*_a, **_k):
            calls.append(1)
            return {}

        monkeypatch.setattr(mod, "fetch_marine_climatology", _fake_fetch)
        progress = []

        ok, err = mod.ensure_era5_cache(
            28.5, -80.5, 2024, 2024,
            on_progress=lambda d, t, m: progress.append((d, t, m)),
        )
        assert ok is True
        assert err is None
        assert calls == []
        assert progress[0][0] == 12

    def test_fetches_year_by_year_when_incomplete(self, isolated_db, monkeypatch):
        from modules.m2_weather import era5_ensure as mod

        years_called = []

        def _fake_fetch(lat, lon, ys, ye):
            years_called.append((ys, ye))
            return {
                f"{ys}-{mo:02d}-01": _full_month()
                for mo in range(1, 13)
            }

        monkeypatch.setattr(mod, "fetch_marine_climatology", _fake_fetch)
        ok, err = mod.ensure_era5_cache(28.5, -80.5, 2023, 2024)
        assert ok is True
        assert err is None
        assert years_called == [(2023, 2023), (2024, 2024)]
        cached, total = era5_cache_progress(28.5, -80.5, 2023, 2024)
        assert cached == 24
        assert total == 24

    def test_returns_error_when_fetch_raises(self, isolated_db, monkeypatch):
        from modules.m2_weather import era5_ensure as mod

        def _boom(*_a, **_k):
            raise RuntimeError("conflicting sizes for dimension 'valid_time'")

        monkeypatch.setattr(mod, "fetch_marine_climatology", _boom)
        ok, err = mod.ensure_era5_cache(28.5, -80.5, 2024, 2024)
        assert ok is False
        assert err is not None
        assert "valid_time" in err

    def test_returns_error_when_fetch_returns_none(self, isolated_db, monkeypatch):
        from modules.m2_weather import era5_ensure as mod

        monkeypatch.setattr(mod, "fetch_marine_climatology", lambda *_a, **_k: None)
        ok, err = mod.ensure_era5_cache(28.5, -80.5, 2024, 2024)
        assert ok is False
        assert err is not None

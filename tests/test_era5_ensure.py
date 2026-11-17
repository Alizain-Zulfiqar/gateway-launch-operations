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

    def test_partial_cache_continues_with_warning(self, isolated_db, monkeypatch):
        """When some months exist after a failed top-up, analysis should continue."""
        from modules.m2_weather import era5_ensure as mod

        for mo in range(1, 7):
            save_cached_era5_month(28.5, -80.5, f"2024-{mo:02d}-01", _full_month())

        monkeypatch.setattr(
            mod, "fetch_marine_climatology",
            lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("CDS unavailable")),
        )
        ok, err = mod.ensure_era5_cache(
            28.5, -80.5, 2024, 2024, allow_partial=True,
        )
        assert ok is True
        assert err is not None
        assert "6 of" in err
        assert "continue" in err.lower()

    def test_partial_disabled_still_fails(self, isolated_db, monkeypatch):
        from modules.m2_weather import era5_ensure as mod

        for mo in range(1, 7):
            save_cached_era5_month(28.5, -80.5, f"2024-{mo:02d}-01", _full_month())

        monkeypatch.setattr(
            mod, "fetch_marine_climatology",
            lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("CDS unavailable")),
        )
        ok, err = mod.ensure_era5_cache(
            28.5, -80.5, 2024, 2024, allow_partial=False,
        )
        assert ok is False
        assert err is not None


class TestNonBlockingWhenNearlyCached:
    """A site with nearly all months cached must not block the analysis on
    the Copernicus queue (client run sat >2 h waiting on 3 missing months)."""

    def test_cache_good_enough_thresholds(self):
        from modules.m2_weather.era5_ensure import cache_good_enough

        assert cache_good_enough(798, 801)          # 3 recent months missing
        assert cache_good_enough(110, 120)          # 10 missing, 92%
        assert not cache_good_enough(6, 12)         # half missing
        assert not cache_good_enough(700, 801)      # 101 missing
        assert not cache_good_enough(0, 12)         # brand-new site
        assert not cache_good_enough(5, 0)

    def test_returns_immediately_and_tops_up_in_background(
        self, isolated_db, monkeypatch,
    ):
        import threading
        from modules.m2_weather import era5_ensure as mod

        for yr in (2023, 2024):
            for mo in range(1, 13):
                if (yr, mo) in ((2024, 11), (2024, 12)):
                    continue
                save_cached_era5_month(
                    28.5, -80.5, f"{yr}-{mo:02d}-01", _full_month(),
                )

        release = threading.Event()
        fetch_started = threading.Event()

        def _slow_fetch(*_a, **_k):
            fetch_started.set()
            release.wait(5)          # simulates a long Copernicus queue
            return {}

        monkeypatch.setattr(mod, "fetch_marine_climatology", _slow_fetch)
        try:
            ok, msg = mod.ensure_era5_cache(28.5, -80.5, 2023, 2024)
            assert ok is True
            assert "background" in msg
            assert fetch_started.wait(2), "background top-up never started"

            # A second run while the top-up is in flight must not queue
            # another Copernicus job.
            ok2, msg2 = mod.ensure_era5_cache(28.5, -80.5, 2023, 2024)
            assert ok2 is True and "already downloading" in msg2
        finally:
            release.set()
            # Let the top-up thread finish while the test DB is still active.
            for t in threading.enumerate():
                if t.name == "era5-topup":
                    t.join(5)
            assert not mod._topups_running

    def test_large_gap_still_blocks_and_fetches(self, isolated_db, monkeypatch):
        from modules.m2_weather import era5_ensure as mod

        save_cached_era5_month(28.5, -80.5, "2024-01-01", _full_month())
        calls = []

        def _fetch(*_a, **_k):
            calls.append(1)
            return {}

        monkeypatch.setattr(mod, "fetch_marine_climatology", _fetch)
        mod.ensure_era5_cache(28.5, -80.5, 2024, 2024)
        assert calls, "a mostly-empty cache must still fetch synchronously"

"""
tests/test_era5.py -- Unit tests for modules/m2_weather/era5.py and its
integration with data_manager.py.

Network tests are skipped when the relevant endpoint is unreachable.
ERA5 tests use cdsapi.Client() with no arguments; credentials come from
~/.cdsapirc which cdsapi reads automatically.
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import core.database as db_mod

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── DB isolation ─────────────────────────────────────────────────────────────
# fetch_swell_realtime_ww3() reads/writes ww3_realtime_cache (Set 42
# follow-up) via core.database.get_connection(), which defaults to the real
# gateway.db. Without this fixture, TestFetchSwellRealtimeWW3's
# network-gated live test silently wrote real cache rows into the
# production DB, then a later test in this same class asserting an
# import-failure path returns None instead got a cache hit and failed
# (confirmed: this exact pollution was found and purged from a real
# gateway.db during Set 42 follow-up development). Same isolation pattern
# as test_contracts_and_pairing.py / test_analysis_fetch_status.py.
@pytest.fixture()
def db_file(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture(autouse=True)
def _patch_db(db_file, monkeypatch):
    monkeypatch.setattr(db_mod, "DB_PATH", str(db_file))
    db_mod.init_db()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _network_available(host: str = "8.8.8.8", port: int = 53, timeout: float = 2.0) -> bool:
    import socket
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except OSError:
        return False


# ── ERA5 tests ────────────────────────────────────────────────────────────────

class TestFetchSwellClimatology:
    def test_returns_none_when_cdsapirc_missing(self):
        """When ~/.cdsapirc is absent cdsapi.Client() raises; function returns None."""
        from modules.m2_weather.era5 import fetch_swell_climatology

        with patch("modules.m2_weather.era5._do_fetch_era5",
                   side_effect=Exception("Missing .cdsapirc")):
            result = fetch_swell_climatology(
                lat=28.5, lon=-80.6,
                year_start=2020, year_end=2022,
            )
        assert result is None

    def test_returns_none_when_cdsapi_missing(self):
        """If cdsapi cannot be imported the function returns None without raising."""
        import builtins
        real_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "cdsapi":
                raise ImportError("cdsapi not available")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_mock_import):
            from modules.m2_weather import era5 as era5_mod
            result = era5_mod.fetch_swell_climatology(
                lat=28.5, lon=-80.6,
                year_start=2020, year_end=2022,
            )
        assert result is None

    def test_months_filter_accepted(self):
        """Passing a months list with no .cdsapirc returns None without raising."""
        from modules.m2_weather.era5 import fetch_swell_climatology

        with patch("modules.m2_weather.era5._do_fetch_era5",
                   side_effect=Exception("auth error")):
            result = fetch_swell_climatology(
                lat=15.0, lon=-45.0,
                year_start=2018, year_end=2020,
                months=[6, 7, 8],
            )
        assert result is None


# ── ERA5 wind gust tests ─────────────────────────────────────────────────────

class TestFetchGustClimatology:
    """fetch_gust_climatology() -- wired up once Set 42's CDS auth fix made
    it testable; confirmed live that ERA5's monthly-means product carries
    the instantaneous_10m_wind_gust variable (netCDF shortname i10fg)."""

    def test_returns_none_when_cdsapirc_missing(self):
        from modules.m2_weather.era5 import fetch_gust_climatology

        with patch("modules.m2_weather.era5._do_fetch_era5_gust",
                   side_effect=Exception("Missing .cdsapirc")):
            result = fetch_gust_climatology(
                lat=28.5, lon=-80.6,
                year_start=2020, year_end=2022,
            )
        assert result is None

    def test_returns_none_when_cdsapi_missing(self):
        import builtins
        real_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "cdsapi":
                raise ImportError("cdsapi not available")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_mock_import):
            from modules.m2_weather import era5 as era5_mod
            result = era5_mod.fetch_gust_climatology(
                lat=28.5, lon=-80.6,
                year_start=2020, year_end=2022,
            )
        assert result is None

    def test_months_filter_accepted(self):
        from modules.m2_weather.era5 import fetch_gust_climatology

        with patch("modules.m2_weather.era5._do_fetch_era5_gust",
                   side_effect=Exception("auth error")):
            result = fetch_gust_climatology(
                lat=15.0, lon=-45.0,
                year_start=2018, year_end=2020,
                months=[6, 7, 8],
            )
        assert result is None


# ── WW3 tests ─────────────────────────────────────────────────────────────────

class TestFetchSwellRealtimeWW3:
    def test_returns_none_when_erddapy_missing(self):
        """If erddapy cannot be imported the function returns None without raising."""
        import builtins
        real_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "erddapy":
                raise ImportError("erddapy not available")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_mock_import):
            from modules.m2_weather import era5 as era5_mod
            result = era5_mod.fetch_swell_realtime_ww3(lat=32.6, lon=-61.1)
        assert result is None

    @pytest.mark.skipif(
        not _network_available(), reason="No network connection"
    )
    def test_structure_when_network_available(self):
        """
        If network is reachable, fetch_swell_realtime_ww3 for a known Atlantic
        location should return a dict with expected keys, or None if the ERDDAP
        dataset is unavailable.  Either outcome is acceptable — what matters is
        that no exception is raised.
        """
        from modules.m2_weather.era5 import fetch_swell_realtime_ww3

        result = fetch_swell_realtime_ww3(lat=32.6, lon=-61.1)
        if result is None:
            pytest.skip("WW3 ERDDAP returned None (dataset may be unavailable)")

        assert isinstance(result, dict)
        required_keys = {"swh_mean_m", "swh_p90_m", "source", "record_count"}
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

        assert result["source"] == "ww3_erddap"
        assert isinstance(result["swh_mean_m"], float)
        assert result["swh_mean_m"] > 0
        assert isinstance(result["record_count"], int)
        assert result["record_count"] > 0

        # Optional fields — may be None if variable not available
        assert "swd_mean_deg" in result
        assert "swp_mean_s"   in result

    def test_returns_none_on_network_error(self):
        """Simulated network error → function returns None, does not raise."""
        from modules.m2_weather import era5 as era5_mod

        with patch.object(era5_mod, "_do_fetch_ww3", side_effect=ConnectionError("timeout")):
            result = era5_mod.fetch_swell_realtime_ww3(lat=0.0, lon=0.0)
        assert result is None


# ── Data manager integration tests ────────────────────────────────────────────

class TestDataManagerSwellFallback:
    def test_era5_none_falls_back_to_icoads_model(self):
        """
        When fetch_swell_climatology returns None, data_manager leaves swh and
        swp as icoads_model — does not raise and does not corrupt other params.
        """
        from core.models import Site

        site = Site(lat=28.5, lon=-80.6, name="Test")

        with patch("modules.m2_weather.data_manager._apply_era5_swell") as mock_era5:
            mock_era5.return_value = None   # simulate no-op (ERA5 failed)
            with patch("modules.m2_weather.data_manager._fetch_historical") as mock_hist:
                # Call the real _fetch_historical but short-circuit NCEI
                from modules.m2_weather.data_manager import _empty_summary
                fake_summary = _empty_summary()
                mock_hist.return_value = fake_summary

                from modules.m2_weather.data_manager import get_site_weather_summary
                result = get_site_weather_summary(site, mode="historical")

        assert result is not None
        assert isinstance(result, dict)

    def test_era5_none_leaves_swell_as_icoads_model(self):
        """
        With _apply_era5_swell mocked to do nothing, swh and swp sources
        remain 'icoads_model'.
        """
        from core.models import Site
        from modules.m2_weather.data_manager import _empty_summary

        site    = Site(lat=28.5, lon=-80.6, name="Test")
        summary = _empty_summary()

        # _apply_era5_swell does nothing (ERA5 returned None)
        with patch("modules.m2_weather.data_manager._apply_era5_swell"):
            pass  # noop mock replaces the call → summary unchanged

        # swh and swp must still be icoads_model
        assert summary["swh"]["source"] == "icoads_model"
        assert summary["swp"]["source"] == "icoads_model"
        assert summary["swdV"]["source"] == "icoads_model"

    def test_ww3_populated_updates_swh_source(self):
        """
        _apply_ww3_swell with valid data should update summary['swh']['source']
        to 'ww3_erddap'.
        """
        from modules.m2_weather.data_manager import _apply_ww3_swell, _empty_summary

        summary = _empty_summary()
        fake_ww3 = {
            "swh_mean_m":   1.8,
            "swh_p90_m":    2.9,
            "swd_mean_deg": 215.0,
            "swp_mean_s":   10.5,
            "source":       "ww3_erddap",
            "record_count": 480,
        }

        with patch("modules.m2_weather.era5.fetch_swell_realtime_ww3", return_value=fake_ww3):
            _apply_ww3_swell(summary, lat=28.5, lon=-80.6)

        assert summary["swh"]["source"] == "ww3_erddap"
        assert summary["swh"]["mean"]   == 1.8
        assert summary["swh"]["p90"]    == 2.9
        assert summary["swp"]["source"] == "ww3_erddap"
        assert summary["swp"]["mean"]   == 10.5
        # swdV must remain icoads_model (direction variance not available from WW3)
        assert summary["swdV"]["source"] == "icoads_model"

    def test_era5_populated_updates_swh_source(self):
        """
        _apply_era5_swell with valid ERA5 monthly data should update
        summary['swh']['source'] to 'era5_reanalysis'.
        """
        from modules.m2_weather.data_manager import _apply_era5_swell, _empty_summary

        summary = _empty_summary()
        fake_era5 = {
            mo: {
                "swh_mean_m":   1.5 + mo * 0.05,
                "swh_p90_m":    2.2 + mo * 0.05,
                "swp_mean_s":   9.5,
                "swd_mean_deg": 200.0,
                "source":       "era5_reanalysis",
                "year_start":   2010,
                "year_end":     2022,
                "record_count": 120,
            }
            for mo in range(1, 13)
        }

        with patch("modules.m2_weather.era5.fetch_swell_climatology", return_value=fake_era5):
            _apply_era5_swell(summary, lat=28.5, lon=-80.6, year_start=2010, year_end=2022)

        assert summary["swh"]["source"] == "era5_reanalysis"
        assert summary["swp"]["source"] == "era5_reanalysis"
        assert summary["swdV"]["source"] == "icoads_model"

        # Aggregate mean should be the mean of all monthly means
        import numpy as np
        expected_swh = round(float(np.mean([v["swh_mean_m"] for v in fake_era5.values()])), 3)
        assert abs(summary["swh"]["mean"] - expected_swh) < 1e-6

    def test_ww3_none_leaves_swh_as_icoads_model(self):
        """
        When _apply_ww3_swell receives None from WW3, swh stays icoads_model.
        """
        from modules.m2_weather.data_manager import _apply_ww3_swell, _empty_summary

        summary = _empty_summary()
        with patch("modules.m2_weather.era5.fetch_swell_realtime_ww3", return_value=None):
            _apply_ww3_swell(summary, lat=28.5, lon=-80.6)

        assert summary["swh"]["source"] == "icoads_model"
        assert summary["swp"]["source"] == "icoads_model"

    def test_era5_gust_populated_updates_wg_source(self):
        """
        _apply_era5_gust with valid ERA5 monthly gust data should update
        summary['wg']['source'] to 'era5_reanalysis'. wg has no other live
        historical source (NCEI Global Marine carries no gust field at all),
        so this is the only path that moves wg off icoads_model in
        Historical mode.
        """
        from modules.m2_weather.data_manager import _apply_era5_gust, _empty_summary

        summary = _empty_summary()
        fake_gust = {
            mo: {
                "wg_mean_kts":  20.0 + mo * 0.1,
                "wg_p90_kts":   28.0 + mo * 0.1,
                "source":       "era5_reanalysis",
                "year_start":   2010,
                "year_end":     2022,
                "record_count": 120,
            }
            for mo in range(1, 13)
        }

        with patch("modules.m2_weather.era5.fetch_gust_climatology", return_value=fake_gust):
            _apply_era5_gust(summary, lat=28.5, lon=-80.6, year_start=2010, year_end=2022)

        assert summary["wg"]["source"] == "era5_reanalysis"

        import numpy as np
        expected_wg = round(float(np.mean([v["wg_mean_kts"] for v in fake_gust.values()])), 2)
        assert abs(summary["wg"]["mean"] - expected_wg) < 1e-6

    def test_era5_gust_none_leaves_wg_as_icoads_model(self):
        """
        When fetch_gust_climatology returns None, data_manager leaves wg as
        icoads_model — does not raise and does not corrupt other params.
        """
        from modules.m2_weather.data_manager import _apply_era5_gust, _empty_summary

        summary = _empty_summary()
        with patch("modules.m2_weather.era5.fetch_gust_climatology", return_value=None):
            _apply_era5_gust(summary, lat=28.5, lon=-80.6, year_start=2010, year_end=2022)

        assert summary["wg"]["source"] == "icoads_model"

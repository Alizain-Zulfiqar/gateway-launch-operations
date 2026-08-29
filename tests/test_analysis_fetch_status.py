"""
tests/test_analysis_fetch_status.py -- AnalysisTab's in-tab fetch-status
banner (fetch_status_widget / _set_fetch_status()), added so the tab shows a
visible busy indicator during the synchronous live NCEI/ERA5/WW3 fetches
_run() triggers (some of which take minutes -- see CLAUDE.md).

Requires PyQt6; runs under the venv interpreter (offscreen platform). Skips
cleanly under the system interpreter, matching every other PyQt-dependent
test in this suite.
"""
from __future__ import annotations

import os

import pytest
import core.database as db_mod

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

_app = QApplication.instance() or QApplication([])


@pytest.fixture()
def db_file(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture(autouse=True)
def _patch_db(db_file, monkeypatch):
    monkeypatch.setattr(db_mod, "DB_PATH", str(db_file))
    db_mod.init_db()


def _mw(site_present=True):
    from core.models import Site

    class MW:
        site = Site(lat=28.5, lon=-80.6, name="CC") if site_present else None
        active_project_id = None

        def status(self, msg):
            pass

    return MW()


def test_banner_hidden_by_default():
    from ui.analysis_tab import AnalysisTab

    tab = AnalysisTab(_mw())
    assert tab.fetch_status_widget.isVisible() is False


def test_set_fetch_status_shows_banner_and_disables_run_button():
    from ui.analysis_tab import AnalysisTab

    tab = AnalysisTab(_mw())
    tab.run_btn.setEnabled(True)

    tab._set_fetch_status("Fetching live 45-day weather data…")

    # isVisible() requires a shown top-level ancestor, which these offscreen
    # widgets don't have; isHidden() reflects the explicit setVisible() flag
    # this method actually toggles, independent of the parent chain.
    assert tab.fetch_status_widget.isHidden() is False
    assert tab.fetch_status_label.text() == "Fetching live 45-day weather data…"
    assert tab.run_btn.isEnabled() is False


def test_set_fetch_status_none_hides_banner_and_restores_run_button():
    from ui.analysis_tab import AnalysisTab

    tab = AnalysisTab(_mw(site_present=True))
    tab._set_fetch_status("Running 12-month analysis…")
    assert tab.fetch_status_widget.isHidden() is False

    tab._set_fetch_status(None)

    assert tab.fetch_status_widget.isHidden() is True
    # Run button re-enabled because mw.site is set.
    assert tab.run_btn.isEnabled() is True


def test_set_fetch_status_none_leaves_run_button_disabled_when_no_site():
    from ui.analysis_tab import AnalysisTab

    tab = AnalysisTab(_mw(site_present=False))
    tab._set_fetch_status("Fetching…")
    tab._set_fetch_status(None)

    assert tab.fetch_status_widget.isVisible() is False
    assert tab.run_btn.isEnabled() is False


def test_run_clears_banner_even_when_engine_raises():
    """_run()'s try/finally must hide the banner and re-enable the Run
    button even if compute_annual_profile() raises mid-run."""
    from unittest.mock import patch
    from ui.analysis_tab import AnalysisTab

    mw = _mw(site_present=True)
    mw.site.id = 1
    mw.site.bbox_nm = 25.0
    from core.models import Vehicle, Platform
    mw.vehicle = Vehicle(
        name="V", vehicle_class="slv_orb", recovery_mode="expendable",
        max_wind_kts=18, max_gust_kts=25, max_hs_m=1.5,
        max_swell_ht_m=2.0, max_swell_period_s=12,
    )
    mw.platform = Platform("Gateway X", "semisub", 0.78)

    tab = AnalysisTab(mw)
    tab.rb_45day.setChecked(True)

    with patch(
        "modules.m2_weather.data_manager.get_site_weather_summary",
        side_effect=Exception("network exploded"),
    ), patch(
        "modules.m3_probability.engine.compute_annual_profile",
        side_effect=RuntimeError("engine exploded"),
    ):
        with pytest.raises(RuntimeError):
            tab._run()

    assert tab.fetch_status_widget.isVisible() is False
    assert tab.run_btn.isEnabled() is True

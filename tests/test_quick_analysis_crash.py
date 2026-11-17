"""
Regression tests for the client-reported Quick Analysis "crash" (2026-11).

Root cause: Quick Analysis called the live NCEI/ERA5 fetch on the GUI thread,
and the Copernicus client's default retry policy (retry_max=500,
sleep_max=120s) kept retrying an unreachable server for hours — the window
froze ("Not Responding") and was killed. Fixes covered here:

* run_off_ui_thread() keeps the event loop alive during slow calls and
  propagates results / exceptions.
* _get_cds_client() fails fast when CDS is unreachable and uses bounded
  retries otherwise.
"""
from __future__ import annotations

import os
import time

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

_app = QApplication.instance() or QApplication([])


class TestRunOffUiThread:
    def test_returns_result(self):
        from ui.analysis_common import run_off_ui_thread

        assert run_off_ui_thread(lambda a, b=0: a + b, 2, b=3) == 5

    def test_reraises_worker_exception(self):
        from ui.analysis_common import run_off_ui_thread

        def boom():
            raise ValueError("fetch failed")

        with pytest.raises(ValueError, match="fetch failed"):
            run_off_ui_thread(boom)

    def test_event_loop_keeps_running_during_slow_call(self):
        from ui.analysis_common import run_off_ui_thread

        ticks = []
        timer = QTimer()
        timer.setInterval(20)
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start()
        try:
            run_off_ui_thread(time.sleep, 0.4)
        finally:
            timer.stop()
        # If the call had blocked the GUI thread, no timer ticks would fire.
        assert len(ticks) >= 5


class TestCdsClientLimits:
    def test_unreachable_fails_fast(self, monkeypatch):
        from modules.m2_weather import era5

        monkeypatch.setattr(era5, "cds_reachable", lambda: False)
        t0 = time.monotonic()
        with pytest.raises(era5.CdsUnreachableError):
            era5._get_cds_client()
        assert time.monotonic() - t0 < 1.0

    def test_swell_fetch_returns_none_when_unreachable(self, monkeypatch):
        from modules.m2_weather import era5

        monkeypatch.setattr(era5, "cds_reachable", lambda: False)
        assert era5.fetch_swell_climatology(40.0, -70.0, 2025, 2026) is None
        assert era5.fetch_gust_climatology(40.0, -70.0, 2025, 2026) is None

    def test_bounded_retries_passed_to_client(self, monkeypatch):
        pytest.importorskip("ecmwf.datastores.legacy_client")
        import ecmwf.datastores.legacy_client as lc
        from modules.m2_weather import era5

        captured = {}

        class FakeClient:
            def __init__(self, **kw):
                captured.update(kw)

        monkeypatch.setattr(era5, "cds_reachable", lambda: True)
        monkeypatch.setattr(lc, "LegacyClient", FakeClient)
        era5._get_cds_client()
        assert captured["retry_max"] <= 10
        assert captured["sleep_max"] <= 30


def test_operability_progress_update_does_not_crash():
    """A broken duplicate _draw_fetch_progress (referencing `self` inside a
    @staticmethod) crashed the app on the first background NCEI progress
    update after an analysis completed."""
    from modules.m3_probability.engine import compute_annual_profile
    from core.models import Platform, Site, Vehicle
    from ui.widgets.analysis_charts import AnalysisChartsWidget

    site = Site(lat=40.0, lon=-70.0, name="T")
    veh = Vehicle(
        name="V", vehicle_class="slv_orb", recovery_mode="expendable",
        max_wind_kts=25, max_gust_kts=30, max_hs_m=1.93,
        max_swell_ht_m=2.44, max_swell_period_s=12,
    )
    profile = compute_annual_profile(site, veh, Platform("Gateway X", "semisub", 0.78))
    w = AnalysisChartsWidget()
    w.set_profile(profile, operability=None, operability_progress=(0, 120))
    w.update_operability_progress(1, 120)
    w.update_operability_progress(120, 120)

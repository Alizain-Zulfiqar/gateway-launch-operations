"""Tests for Analysis & Comparison UX consistency (year range, thresholds, direction)."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestAnalysisYearMax:
    def test_analysis_year_max_is_at_least_current_year(self):
        from config import analysis_year_max

        assert analysis_year_max() >= date.today().year


class TestGoThresholdSettings:
    def test_sub_fifty_go_threshold_persists(self, tmp_path, monkeypatch):
        import core.database as db_mod

        db_file = tmp_path / "go_thr.db"
        monkeypatch.setattr(db_mod, "DB_PATH", str(db_file))
        db_mod.init_db()

        from core.settings import set_setting
        from core.verdict_thresholds import get_go_threshold, go_pct_threshold

        set_setting("go_threshold", "0.30")
        set_setting("marginal_threshold", "0.15")
        assert get_go_threshold() == pytest.approx(0.30)
        assert go_pct_threshold() == pytest.approx(30.0)


class TestDirectionDayFraction:
    def test_direction_param_lowers_joint_pct_when_included(self):
        from modules.m2_weather.operability import joint_pct_all_criteria

        means = {"ws": 10.0, "wg": 12.0, "sh": 0.8, "swh": 0.5, "swp": 8.0, "wdV": 8.0}
        thr = {
            "ws": 20.0, "wg": 25.0, "sh": 1.83, "swh": 2.44, "swp": 18.0, "wdV": 45.0,
        }
        mag_only = joint_pct_all_criteria(
            means, thr, ["ws", "wg", "sh", "swh", "swp"],
        )
        with_wind_dir = joint_pct_all_criteria(
            means, thr, ["ws", "wg", "sh", "swh", "swp", "wdV"],
        )
        assert mag_only is not None and with_wind_dir is not None
        assert with_wind_dir < mag_only


class TestChartThresholdHelpers:
    def test_go_pct_reflects_settings_not_hardcoded_seventy(self, tmp_path, monkeypatch):
        import core.database as db_mod

        db_file = tmp_path / "chart_thr.db"
        monkeypatch.setattr(db_mod, "DB_PATH", str(db_file))
        db_mod.init_db()

        from core.settings import set_setting

        set_setting("go_threshold", "0.50")
        set_setting("marginal_threshold", "0.35")

        from modules.m5_reports.analysis_chart_pages import _go_pct, _marg_pct

        assert _go_pct() == pytest.approx(50.0)
        assert _marg_pct() == pytest.approx(35.0)

        from ui.widgets.analysis_charts import _go_pct as ui_go

        assert ui_go() == pytest.approx(50.0)

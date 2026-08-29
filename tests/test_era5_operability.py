"""Tests for ERA5 monthly operability heatmaps and day-fraction verdicts."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import Site
from modules.m2_weather.era5_cache import save_cached_era5_month
from modules.m2_weather.operability import (
    OPERABILITY_YEARS,
    apply_day_fraction_verdicts,
    build_era5_operability_heatmaps,
    era5_operability_year_range,
    joint_pct_all_criteria,
    monthly_all_criteria_day_fractions,
    monthly_per_param_criterion_fractions,
    param_criterion_pct,
)


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    import core.database as db_mod

    db = tmp_path / "era5_oper.db"
    monkeypatch.setattr("config.DB_PATH", str(db))
    monkeypatch.setattr(db_mod, "DB_PATH", str(db))
    db_mod.init_db()
    return db


def _row(ws=10.0, sh=0.8, swh=0.4, swp=8.0, wg=14.0):
    return {
        "ws_mean_kts": ws,
        "sh_mean_m": sh,
        "swh_mean_m": swh,
        "swp_mean_s": swp,
        "wg_mean_kts": wg,
        "record_count": 1,
    }


class TestBuildEra5OperabilityHeatmaps:
    def test_builds_grids_from_cache(self, isolated_db):
        save_cached_era5_month(28.5, -80.5, "2024-07-01", _row())
        site = Site(lat=28.5, lon=-80.5, bbox_nm=25.0)
        progress = []
        op = build_era5_operability_heatmaps(
            site, 2024, 2024,
            on_progress=lambda d, t, m: progress.append((d, t)),
        )
        assert op.source == "era5_reanalysis"
        assert op.months_cached == 1
        assert op.months_total == 12
        assert op.pct_both[6][0] is not None
        assert op.operable_days[6][0] is not None
        assert set(op.active_params) >= {"ws", "wg", "sh", "swh", "swp"}
        assert len(progress) == 12

    def test_calm_month_high_operability(self, isolated_db):
        save_cached_era5_month(28.5, -80.5, "2024-01-01", _row(
            ws=5.0, sh=0.3, swh=0.2, swp=7.0, wg=8.0,
        ))
        site = Site(lat=28.5, lon=-80.5, bbox_nm=25.0)
        op = build_era5_operability_heatmaps(site, 2024, 2024)
        assert op.pct_both[0][0] is not None
        assert op.pct_both[0][0] >= 70.0

    def test_uses_all_params_not_just_wind_wave(self):
        # Calm wind/wave but swell period far over limit → joint drops.
        high_period = joint_pct_all_criteria(
            {"ws": 8.0, "wg": 10.0, "sh": 0.5, "swh": 0.4, "swp": 30.0},
            {"ws": 20.0, "wg": 25.0, "sh": 1.83, "swh": 2.44, "swp": 18.0},
            ["ws", "wg", "sh", "swh", "swp"],
        )
        calm_all = joint_pct_all_criteria(
            {"ws": 8.0, "wg": 10.0, "sh": 0.5, "swh": 0.4, "swp": 8.0},
            {"ws": 20.0, "wg": 25.0, "sh": 1.83, "swh": 2.44, "swp": 18.0},
            ["ws", "wg", "sh", "swh", "swp"],
        )
        assert high_period is not None and calm_all is not None
        assert high_period < calm_all

    def test_direction_included_lowers_joint(self):
        means = {"ws": 10.0, "wdV": 6.0}
        thr = {"ws": 20.0, "wdV": 45.0}
        base = joint_pct_all_criteria(means, thr, ["ws"])
        with_dir = joint_pct_all_criteria(means, thr, ["ws", "wdV"])
        assert base is not None and with_dir is not None
        assert with_dir < base


class TestDayFractionsAndYearRange:
    def test_operability_year_range_is_10_years(self):
        ys, ye = era5_operability_year_range()
        assert ye - ys + 1 == OPERABILITY_YEARS

    def test_monthly_day_fractions_and_verdict_bands(self, isolated_db):
        # Two Januaries: one calm, one rough → average fraction used for Chart 1.
        save_cached_era5_month(28.5, -80.5, "2023-01-01", _row(
            ws=5.0, sh=0.3, swh=0.2, swp=7.0, wg=8.0,
        ))
        save_cached_era5_month(28.5, -80.5, "2024-01-01", _row(
            ws=5.0, sh=0.3, swh=0.2, swp=7.0, wg=8.0,
        ))
        site = Site(lat=28.5, lon=-80.5, bbox_nm=25.0)
        fracs = monthly_all_criteria_day_fractions(
            site, 2023, 2024,
            thresholds={
                "ws": 20.0, "wg": 25.0, "sh": 1.83, "swh": 2.44, "swp": 18.0,
            },
        )
        assert 1 in fracs
        assert fracs[1]["pct"] >= 70.0

        class _R:
            def __init__(self):
                self.overall_prob = 0.0

            @property
            def verdict(self):
                if self.overall_prob >= 0.70:
                    return "GO"
                if self.overall_prob >= 0.50:
                    return "MARGINAL"
                return "NO-GO"

        profile = {1: _R()}
        apply_day_fraction_verdicts(profile, fracs)
        assert profile[1].verdict == "GO"

    def test_monthly_per_param_fractions_calm_january(self, isolated_db):
        save_cached_era5_month(28.5, -80.5, "2023-01-01", _row(
            ws=5.0, sh=0.3, swh=0.2, swp=7.0, wg=8.0,
        ))
        save_cached_era5_month(28.5, -80.5, "2024-01-01", _row(
            ws=5.0, sh=0.3, swh=0.2, swp=7.0, wg=8.0,
        ))
        site = Site(lat=28.5, lon=-80.5, bbox_nm=25.0)
        thr = {
            "ws": 20.0, "wg": 25.0, "sh": 1.83, "swh": 2.44, "swp": 18.0,
        }
        per_param = monthly_per_param_criterion_fractions(
            site, 2023, 2024, thresholds=thr,
        )
        assert 1 in per_param
        assert per_param[1]["wg"] >= 70.0
        assert per_param[1]["ws"] >= 70.0
        assert "wdV" not in per_param[1]

    def test_joint_matches_product_of_marginals(self, isolated_db):
        save_cached_era5_month(28.5, -80.5, "2024-06-01", _row(
            ws=10.0, wg=14.0, sh=0.8, swh=0.4, swp=8.0,
        ))
        site = Site(lat=28.5, lon=-80.5, bbox_nm=25.0)
        thr = {
            "ws": 20.0, "wg": 25.0, "sh": 1.83, "swh": 2.44, "swp": 18.0,
        }
        params = ["ws", "wg", "sh", "swh", "swp"]
        per_param = monthly_per_param_criterion_fractions(
            site, 2024, 2024, thresholds=thr, active_params=params,
        )
        joint_frac = monthly_all_criteria_day_fractions(
            site, 2024, 2024, thresholds=thr, active_params=params,
        )
        assert 6 in per_param and 6 in joint_frac
        product = 1.0
        for p in params:
            product *= per_param[6][p] / 100.0
        assert joint_frac[6]["pct"] == pytest.approx(product * 100.0, abs=0.2)

    def test_param_criterion_pct_single_param(self):
        thr = {"wg": 25.0}
        pct = param_criterion_pct({"wg": 8.0}, thr, "wg")
        assert pct is not None
        assert pct >= 70.0

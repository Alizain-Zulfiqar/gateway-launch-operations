"""tests/test_combined_report.py — compute_probability_from_observed + combined PDF."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

import core.database as db_mod


@pytest.fixture()
def db_file(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture(autouse=True)
def _patch_db(db_file, monkeypatch):
    monkeypatch.setattr(db_mod, "DB_PATH", str(db_file))
    db_mod.init_db()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_site_vehicle_platform():
    from core.models import Site, Vehicle, Platform
    site = Site(lat=28.5, lon=-80.6, name="Test Site")
    vehicle = Vehicle(
        name="Test Rocket",
        vehicle_class="slv_orb",
        recovery_mode="expendable",
        max_wind_kts=18.0,
        max_gust_kts=25.0,
        max_hs_m=1.5,
        max_swell_ht_m=2.0,
        max_swell_period_s=12.0,
    )
    platform = Platform(
        name="Gateway S",
        hull_type="semi_sub",
        hull_motion_factor=1.0,
    )
    return site, vehicle, platform


# ── compute_probability_from_observed ─────────────────────────────────────────

def test_compute_probability_from_observed_structure():
    """Function returns AnalysisResult; observed params tagged ndbc_realtime."""
    from modules.m3_probability.engine import (
        compute_probability,
        compute_probability_from_observed,
    )
    site, vehicle, platform = _make_site_vehicle_platform()

    fallback = compute_probability(site, vehicle, platform, month=6)
    result   = compute_probability_from_observed(
        vehicle, platform,
        {"ws": 10.0, "sh": 1.0},
        fallback,
    )

    assert hasattr(result, "overall_prob")
    assert 0.0 <= result.overall_prob <= 1.0
    assert result.mode == "observed"
    assert result.data_sources.get("ws") == "ndbc_realtime"
    assert result.data_sources.get("sh") == "ndbc_realtime"
    # overall_prob must differ from fallback if observed means differ from climate
    # (just check it's a valid float, not that it equals anything specific)
    assert isinstance(result.overall_prob, float)


def test_compute_probability_from_observed_missing_param():
    """Params absent from observed_means fall back to icoads_model."""
    from modules.m3_probability.engine import (
        compute_probability,
        compute_probability_from_observed,
    )
    site, vehicle, platform = _make_site_vehicle_platform()

    fallback = compute_probability(site, vehicle, platform, month=6)
    result   = compute_probability_from_observed(
        vehicle, platform,
        {"ws": 10.0},   # only wind speed observed, wave falls back to climate
        fallback,
    )

    assert result.data_sources.get("ws")  == "ndbc_realtime"
    assert result.data_sources.get("sh")  == "icoads_model"
    assert result.data_sources.get("swh") == "icoads_model"


def test_compute_probability_from_observed_none_values():
    """None values in observed_means are silently ignored (no crash)."""
    from modules.m3_probability.engine import (
        compute_probability,
        compute_probability_from_observed,
    )
    site, vehicle, platform = _make_site_vehicle_platform()

    fallback = compute_probability(site, vehicle, platform, month=6)
    result   = compute_probability_from_observed(
        vehicle, platform,
        {"ws": None, "sh": None},
        fallback,
    )

    # All None → no observed data → all params fall back to climate
    assert result.data_sources.get("ws") == "icoads_model"
    assert 0.0 <= result.overall_prob <= 1.0


# ── Combined PDF ──────────────────────────────────────────────────────────────

def test_combined_report_generates_extra_pages(tmp_path):
    """Combined report (include_buoy_forecast=True) produces a larger PDF."""
    from modules.m3_probability.engine import compute_probability
    from modules.m5_reports.pdf_report import generate_analysis_report

    site, vehicle, platform = _make_site_vehicle_platform()
    result = compute_probability(site, vehicle, platform, month=6)

    base_path = str(tmp_path / "base.pdf")
    comb_path = str(tmp_path / "combined.pdf")

    # 3-page baseline
    generate_analysis_report(result, base_path)
    size_base = os.path.getsize(base_path)

    # 6-page combined (pages 4-6 added)
    forecast_data = {
        "horizon_hours":  72,
        "horizon_label":  "72-hour",
        "confidence":     4,
        "confidence_max": 5,
        "go_hours":       50,
        "total_hours":    72,
        "go_pct":         69.4,
        "wind_mean_kts":  12.0,
        "hs_mean_m":      1.5,
        "station_count":  2,
        "cards": [
            {"param": "Wind Speed",       "value": "12.0 kts", "status": "GO"},
            {"param": "Wave Height (Hs)", "value": "1.50 m",   "status": "GO"},
        ],
    }
    ndbc_combined = {
        "wind_speed":   {"weighted_mean_kts": 12.0, "network_max_kts": 18.0, "network_p90_kts": 15.0},
        "wind_gust":    {"weighted_mean_kts": None, "network_max_kts": None, "network_p90_kts": None},
        "wave_height":  {"weighted_mean_m":   1.5,  "network_max_m":   2.0,  "network_p90_m":   1.8},
        "swell_height": {"weighted_mean_m":   None, "network_max_m":   None, "network_p90_m":   None},
        "swell_period": {"weighted_mean_s":   None, "network_max_s":   None, "network_p90_s":   None},
        "station_count": 2,
        "station_ids":   ["41009", "41047"],
        "weights":       {"41009": 0.8, "41047": 0.2},
    }

    from modules.m3_probability.engine import compute_probability_from_observed
    blended  = compute_probability(
        site, vehicle, platform, month=6,
        observed_means={"ws": {"mean": 12.0, "source": "ndbc_realtime"}},
    )
    observed = compute_probability_from_observed(
        vehicle, platform, {"ws": 12.0, "sh": 1.5}, result
    )

    generate_analysis_report(
        result,
        comb_path,
        include_buoy_forecast=True,
        blended_result=blended,
        observed_result=observed,
        forecast_data=forecast_data,
        ndbc_combined=ndbc_combined,
        forecast_horizon_hours=72,
    )
    size_comb = os.path.getsize(comb_path)

    assert size_comb > size_base, (
        f"Combined PDF ({size_comb} bytes) should be larger than base ({size_base} bytes)"
    )

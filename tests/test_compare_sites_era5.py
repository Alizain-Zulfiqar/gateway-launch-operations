"""
tests/test_compare_sites_era5.py — ERA5-backed multi-site comparison path.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.models import AnalysisResult, Platform, Site, Vehicle


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    import core.database as db_mod

    db_file = tmp_path / "compare_sites.db"
    monkeypatch.setattr(db_mod, "DB_PATH", str(db_file))
    db_mod.init_db()


def _site(name="A", lat=28.5, lon=-80.5):
    return Site(name=name, lat=lat, lon=lon, bbox_nm=25.0)


def _profile(prob: float = 0.75) -> dict:
    out = {}
    for m in range(1, 13):
        ar = MagicMock(spec=AnalysisResult)
        ar.overall_prob = prob
        ar.verdict = "GO" if prob >= 0.70 else ("MARGINAL" if prob >= 0.50 else "NO-GO")
        ar.effective_means = {"ws": 12.0, "sh": 1.2, "wg": 15.0, "swh": 0.8, "swp": 8.0}
        ar.thresholds = {"ws": 20.0, "sh": 1.83, "wg": 25.0, "swh": 2.44, "swp": 18.0}
        ar.param_probs = {p: prob for p in ("ws", "wg", "sh", "swh", "swp")}
        ar.active_params = ["ws", "wg", "sh", "swh", "swp"]
        out[m] = ar
    return out


def test_compare_site_era5_wires_climatology_day_fractions_and_operability():
    from modules.m2_weather.climatology import MonthlyClimatology

    site = _site()
    vehicle = MagicMock(spec=Vehicle)
    platform = MagicMock(spec=Platform)
    profile = _profile(0.80)
    clim = MonthlyClimatology(
        years=(2020, 2024),
        by_month={m: {"ws": {"mean": 10.0, "source": "era5_reanalysis"}}
                  for m in range(1, 13)},
    )
    day_frac = {m: {"pct": 72.0, "avg_days": 22.0} for m in range(1, 13)}
    param_frac = {m: {"ws": 80.0, "wg": 75.0} for m in range(1, 13)}
    operability = MagicMock()

    with (
        patch(
            "modules.m3_probability.compare_sites.ensure_era5_cache",
            return_value=(True, None),
        ) as mock_ensure,
        patch(
            "modules.m3_probability.compare_sites.build_monthly_climatology",
            return_value=clim,
        ) as mock_clim,
        patch(
            "modules.m3_probability.compare_sites.compute_annual_profile",
            return_value=profile,
        ) as mock_cap,
        patch(
            "modules.m3_probability.compare_sites.monthly_all_criteria_day_fractions",
            return_value=day_frac,
        ) as mock_df,
        patch(
            "modules.m3_probability.compare_sites.monthly_per_param_criterion_fractions",
            return_value=param_frac,
        ) as mock_pf,
        patch(
            "modules.m3_probability.compare_sites.apply_day_fraction_verdicts",
        ) as mock_apply,
        patch(
            "modules.m3_probability.compare_sites.era5_operability_year_range",
            return_value=(2017, 2026),
        ),
        patch(
            "modules.m3_probability.compare_sites.build_era5_operability_heatmaps",
            return_value=operability,
        ) as mock_op,
    ):
        from modules.m3_probability.compare_sites import compare_site_era5

        out_profile, out_clim, out_op, out_df, out_pf = compare_site_era5(
            site, vehicle, platform, 2020, 2024,
        )

    assert out_profile is profile
    assert out_clim is clim
    assert out_op is operability
    assert out_df is day_frac
    assert out_pf is param_frac
    # Phase A + Phase B each call ensure_era5_cache once
    assert mock_ensure.call_count == 2
    mock_clim.assert_called_once()
    assert mock_cap.call_args.kwargs["mode"] == "historical"
    assert mock_cap.call_args.kwargs["observed_means_by_month"] is clim.by_month
    mock_df.assert_called_once()
    mock_pf.assert_called_once()
    mock_apply.assert_called_once()
    assert mock_apply.call_args.args[0] is profile
    assert mock_apply.call_args.args[1] is day_frac
    assert "thresholds" in mock_apply.call_args.kwargs
    assert "active_params" in mock_apply.call_args.kwargs
    mock_op.assert_called_once()
    assert mock_op.call_args.args[1:3] == (2017, 2026)


def test_compare_site_era5_raises_on_cache_failure():
    site = _site()
    with patch(
        "modules.m3_probability.compare_sites.ensure_era5_cache",
        return_value=(False, "ERA5 fetch failed"),
    ):
        from modules.m3_probability.compare_sites import compare_site_era5

        with pytest.raises(RuntimeError, match="ERA5"):
            compare_site_era5(
                site, MagicMock(spec=Vehicle), MagicMock(spec=Platform),
                2020, 2024,
            )


def test_comparison_worker_emits_site_rows():
    """Worker returns (site, profile, clim, operability, day_frac, param_frac) per site."""
    from modules.m2_weather.climatology import MonthlyClimatology
    from ui.sections.comparison import _ComparisonWorker

    sites = [_site("A"), _site("B", lat=30.0, lon=-90.0)]
    clim = MonthlyClimatology(years=(2020, 2024), by_month={})
    profile = _profile(0.7)
    operability = MagicMock()

    day_frac = {m: {"pct": 70.0, "avg_days": 20.0} for m in range(1, 13)}
    param_frac = {m: {"ws": 72.0} for m in range(1, 13)}

    with patch(
        "modules.m3_probability.compare_sites.compare_site_era5",
        side_effect=lambda *a, **k: (profile, clim, operability, day_frac, param_frac),
    ):
        worker = _ComparisonWorker(
            sites=sites,
            vehicle=MagicMock(spec=Vehicle),
            platform=MagicMock(spec=Platform),
            year_start=2020,
            year_end=2024,
        )
        collected = []
        worker.finished.connect(collected.append)
        worker.run()  # synchronous for test

    assert len(collected) == 1
    results = collected[0]
    assert len(results) == 2
    assert results[0][0].name == "A"
    assert results[0][1] is profile
    assert results[0][2] is clim
    assert results[0][3] is operability
    assert results[0][4] is day_frac
    assert results[0][5] is param_frac

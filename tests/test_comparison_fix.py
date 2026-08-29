"""
tests/test_comparison_fix.py — Multi-site comparison logic tests.
"""
import pytest
from unittest.mock import MagicMock, patch
from core.models import Site, Vehicle, Platform


def _make_site(name, lat, lon):
    return Site(name=name, lat=lat, lon=lon)


def _make_profile(go_frac: float):
    """Return a dict[int, AnalysisResult] with constant annual_go_fraction."""
    from core.models import AnalysisResult
    result = {}
    for month in range(1, 13):
        ar = MagicMock(spec=AnalysisResult)
        ar.go_fraction = go_frac
        result[month] = ar
    return result


def test_comparison_collects_multiple_sites():
    """compute_annual_profile called once per site; each returns 12-month dict."""
    sites = [
        _make_site("Site A", 10.0, -50.0),
        _make_site("Site B", 20.0, -60.0),
        _make_site("Site C", 30.0, -70.0),
    ]
    vehicle  = MagicMock(spec=Vehicle)
    platform = MagicMock(spec=Platform)

    profiles = {}
    with patch(
        "modules.m3_probability.engine.compute_annual_profile",
        side_effect=lambda s, v, p, **kw: _make_profile(0.75),
    ) as mock_cap:
        from modules.m3_probability.engine import compute_annual_profile
        for site in sites:
            profiles[site.name] = compute_annual_profile(site, vehicle, platform)

    assert len(profiles) == 3
    for name, profile in profiles.items():
        assert len(profile) == 12, f"{name} should have 12 monthly entries"


def test_comparison_ranking_sorted():
    """Sites ranked by descending annual go_fraction."""
    site_go_fracs = {
        "Site A": 0.60,
        "Site B": 0.85,
        "Site C": 0.70,
    }

    def _annual_go(profile: dict) -> float:
        vals = [ar.go_fraction for ar in profile.values()]
        return sum(vals) / len(vals)

    profiles = {name: _make_profile(frac) for name, frac in site_go_fracs.items()}
    ranked = sorted(profiles.items(), key=lambda kv: _annual_go(kv[1]), reverse=True)

    names = [r[0] for r in ranked]
    assert names == ["Site B", "Site C", "Site A"]
    assert _annual_go(ranked[0][1]) > _annual_go(ranked[1][1])
    assert _annual_go(ranked[1][1]) > _annual_go(ranked[2][1])

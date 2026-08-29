"""tests/test_branding.py -- Branding and logo asset tests."""
import os
import tempfile

import pytest


def test_logo_path_defined():
    from config import LOGO_PATH
    assert LOGO_PATH is not None
    assert str(LOGO_PATH).endswith(".png")


def test_logo_available_returns_bool():
    from config import logo_available
    result = logo_available()
    assert isinstance(result, bool)


def test_assets_dir_exists_after_init(tmp_path, monkeypatch):
    import config
    import core.database as db_mod

    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    monkeypatch.setattr(db_mod, "DB_PATH", str(tmp_path / "test.db"))

    from core.database import init_db
    init_db()

    assets_dir = tmp_path / "assets"
    assert assets_dir.exists()


def test_report_header_does_not_crash_without_logo(monkeypatch):
    import config
    from config import BASE_DIR

    original = config.LOGO_PATH
    config.LOGO_PATH = BASE_DIR / "assets" / "nonexistent_logo_for_test.png"

    try:
        from core.models import Site, Vehicle, Platform
        from modules.m3_probability.engine import compute_probability
        from modules.m5_reports.pdf_report import generate_analysis_report

        site = Site(lat=32.6, lon=-61.1, name="Test")
        v = Vehicle(
            name="Test",
            vehicle_class="slv_orb",
            recovery_mode="expendable",
            max_wind_kts=18,
            max_gust_kts=25,
            max_hs_m=1.5,
            max_swell_ht_m=2.0,
            max_swell_period_s=12,
        )
        p = Platform("Gateway X", "semisub", 0.78)

        result = compute_probability(site, v, p, month=6)

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            outpath = f.name

        generate_analysis_report(result, outpath)
        assert os.path.exists(outpath)
        assert os.path.getsize(outpath) > 0
        os.unlink(outpath)
    finally:
        config.LOGO_PATH = original

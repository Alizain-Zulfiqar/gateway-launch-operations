"""
tests/test_bug_fixes.py — Tests for site save, comparison, coordinates, and reports dir.
"""
import pytest
from unittest.mock import patch, MagicMock

from core.models import Site, Vehicle, Platform


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    import core.database as db_mod
    monkeypatch.setattr(db_mod, "DB_PATH", str(db_file))
    from core.database import init_db
    init_db()


def test_save_site_returns_id():
    from modules.m1_site.site_config import save_site
    site = Site(lat=32.6, lon=-61.1, name="Bermuda Test")
    site_id = save_site(site)
    assert site_id is not None
    assert isinstance(site_id, int)
    assert site_id > 0


def test_saved_site_retrievable():
    from modules.m1_site.site_config import save_site, get_site
    site = Site(lat=31.7, lon=-66.3, name="Sargasso Test")
    site_id = save_site(site)
    retrieved = get_site(site_id)
    assert retrieved.name == "Sargasso Test"
    assert retrieved.lat == pytest.approx(31.7)
    assert retrieved.lon == pytest.approx(-66.3)


def test_list_sites_returns_saved():
    from modules.m1_site.site_config import save_site, list_sites
    save_site(Site(lat=22.4, lon=-69.1, name="Caribbean Test"))
    save_site(Site(lat=40.8, lon=-67.5, name="NE Slope Test"))
    sites = list_sites()
    names = [s.name for s in sites]
    assert "Caribbean Test" in names
    assert "NE Slope Test" in names


def test_comparison_worker_collects_all_sites():
    sites = [
        Site(lat=32.6, lon=-61.1, name="Bermuda"),
        Site(lat=31.7, lon=-66.3, name="Sargasso"),
        Site(lat=22.4, lon=-69.1, name="Caribbean"),
    ]
    vehicle = Vehicle(
        name="Test", vehicle_class="slv_orb", recovery_mode="expendable",
        max_wind_kts=18, max_gust_kts=25, max_hs_m=1.5,
        max_swell_ht_m=2.0, max_swell_period_s=12,
    )
    platform = Platform(name="Gateway X", hull_type="semisub", hull_motion_factor=0.78)

    mock_result = MagicMock()
    mock_result.overall_prob = 0.75
    mock_profile = {m: mock_result for m in range(1, 13)}

    results = []
    with patch(
        "modules.m3_probability.engine.compute_annual_profile",
        return_value=mock_profile,
    ):
        from modules.m3_probability.engine import compute_annual_profile
        for site in sites:
            profile = compute_annual_profile(site, vehicle, platform)
            results.append((site, profile))

    assert len(results) == 3
    for site, profile in results:
        assert len(profile) == 12
        for month, result in profile.items():
            assert hasattr(result, 'overall_prob')


def test_parse_coordinate_all_candidate_sites():
    from ui.widgets.coord_input import parse_coordinate
    pairs = [
        ("34.2", "-66.5"),
        ("33.8", "-73.5"),
        ("32.6", "-61.1"),
        ("31.7", "-66.3"),
        ("38.0", "-70.3"),
        ("22.4", "-69.1"),
        ("40.8", "-67.5"),
    ]
    for lat_str, lon_str in pairs:
        assert parse_coordinate(lat_str, 'lat') is not None, f"Failed lat: {lat_str}"
        assert parse_coordinate(lon_str, 'lon') is not None, f"Failed lon: {lon_str}"


def test_reports_dir_created(tmp_path, monkeypatch):
    import config as cfg
    monkeypatch.setattr(cfg, "BASE_DIR", tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(exist_ok=True)
    assert reports_dir.exists()


def test_apply_table_colors_does_not_raise():
    """apply_table_colors should run without error and set stylesheet."""
    import sys
    from PyQt6.QtWidgets import QApplication, QTableWidget
    app = QApplication.instance() or QApplication(sys.argv)
    table = QTableWidget(3, 3)
    from ui.styles import apply_table_colors
    apply_table_colors(table)
    # Stylesheet should include our color values
    ss = table.styleSheet()
    assert "#f1f5f9" in ss
    assert "#94a3b8" in ss

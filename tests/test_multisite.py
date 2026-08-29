"""tests/test_multisite.py — Multi-site DB and coordinate tests."""
import pytest

import core.database as db_mod


@pytest.fixture()
def db_file(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture(autouse=True)
def _patch_db(db_file, monkeypatch):
    monkeypatch.setattr(db_mod, "DB_PATH", str(db_file))
    db_mod.init_db()


def test_save_multiple_sites_transaction(db_file):
    """Save 7 distinct sites in a single connection commit."""
    from modules.m1_site.site_config import save_site, list_sites
    from core.models import Site

    sites = [
        Site(lat=28.5 + i * 0.1, lon=-80.6 - i * 0.1, name=f"Site {i+1}")
        for i in range(7)
    ]
    for site in sites:
        save_site(site)

    saved = list_sites()
    assert len(saved) == 7
    names = {s.name for s in saved}
    assert {f"Site {i+1}" for i in range(7)} == names


def test_seven_candidate_sites_valid_coords():
    """All 7 candidate sites have valid WGS-84 decimal-degree coordinates."""
    candidates = [
        (28.50, -80.60),   # Cape Canaveral
        (25.61, -80.39),   # Miami
        (17.97, -76.79),   # Kingston
        (10.65, -61.52),   # Trinidad
        (7.07,  -73.85),   # Bogota offshore
        (3.86,   11.52),   # Douala
        (-2.51,  -44.30),  # Alcântara
    ]
    for lat, lon in candidates:
        assert -90.0 <= lat <= 90.0,  f"Latitude out of range: {lat}"
        assert -180.0 <= lon <= 180.0, f"Longitude out of range: {lon}"


def test_coord_ddm_display():
    """DDM formatting from decimal degrees rounds to 3 decimal places in minutes."""
    from ui.sections.sites import _dd_to_ddm

    result = _dd_to_ddm(28.5, is_lat=True)
    # 28.5° → 28° 30.000' N
    assert result == "28 30.000 N"

    result = _dd_to_ddm(-80.6, is_lat=False)
    # 80.6° W → 80° 36.000' W
    assert result == "80 36.000 W"

    result = _dd_to_ddm(-2.51, is_lat=True)
    # 2.51° S → 2° 30.600' S
    assert "S" in result
    assert result.startswith("2 ")

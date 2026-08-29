"""
tests/test_site_config.py — Tests for modules/m1_site/site_config.py

Uses an isolated in-memory SQLite database for every test so no
gateway.db state bleeds between runs.

Run: pytest tests/test_site_config.py -v
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import pytest
from unittest.mock import patch

from core.models import Site
from core.database import init_db
import modules.m1_site.site_config as sc


# ── In-memory DB fixture ──────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """
    Redirect DB_PATH to a temp file and initialise a fresh schema for
    every test. Monkeypatching config.DB_PATH is enough because
    core/database.get_connection() reads the module-level DB_PATH.
    """
    db_file = tmp_path / "test_gateway.db"
    monkeypatch.setattr("config.DB_PATH", db_file)
    # Re-import database so it picks up the patched path
    import core.database as db_mod
    monkeypatch.setattr(db_mod, "DB_PATH", db_file)
    init_db()
    yield


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def cape_canaveral():
    return Site(lat=28.5, lon=-80.6, name="Cape Canaveral Area", bbox_nm=25.0)

@pytest.fixture
def pacific_site():
    return Site(lat=-22.3, lon=170.4, name="South Pacific Launch Zone", bbox_nm=50.0)

@pytest.fixture
def north_atlantic():
    return Site(lat=40.0, lon=-30.0, name="North Atlantic S1")


# ── save_site ─────────────────────────────────────────────────────────────────

def test_save_site_returns_int(cape_canaveral):
    row_id = sc.save_site(cape_canaveral)
    assert isinstance(row_id, int)
    assert row_id > 0

def test_save_site_sets_id_on_model(cape_canaveral):
    sc.save_site(cape_canaveral)
    assert cape_canaveral.id is not None
    assert cape_canaveral.id > 0

def test_save_site_sequential_ids(cape_canaveral, pacific_site):
    id1 = sc.save_site(cape_canaveral)
    id2 = sc.save_site(pacific_site)
    assert id2 == id1 + 1

def test_save_site_stores_coords(cape_canaveral):
    sc.save_site(cape_canaveral)
    retrieved = sc.get_site(cape_canaveral.id)
    assert retrieved.lat == pytest.approx(28.5)
    assert retrieved.lon == pytest.approx(-80.6)

def test_save_site_stores_name(cape_canaveral):
    sc.save_site(cape_canaveral)
    retrieved = sc.get_site(cape_canaveral.id)
    assert retrieved.name == "Cape Canaveral Area"

def test_save_site_stores_bbox_nm(pacific_site):
    sc.save_site(pacific_site)
    retrieved = sc.get_site(pacific_site.id)
    assert retrieved.bbox_nm == pytest.approx(50.0)

def test_save_site_default_bbox(north_atlantic):
    sc.save_site(north_atlantic)
    retrieved = sc.get_site(north_atlantic.id)
    assert retrieved.bbox_nm == pytest.approx(25.0)

def test_save_site_southern_hemisphere(pacific_site):
    sc.save_site(pacific_site)
    retrieved = sc.get_site(pacific_site.id)
    assert retrieved.lat == pytest.approx(-22.3)   # South
    assert retrieved.lon == pytest.approx(170.4)    # East

def test_save_site_with_notes():
    site = Site(lat=28.5, lon=-80.6, name="Noted", notes="Prototype test site")
    sc.save_site(site)
    retrieved = sc.get_site(site.id)
    assert retrieved.notes == "Prototype test site"

def test_save_site_with_platform_id(isolated_db):
    # Seed a platform row so the FK constraint is satisfied
    from core.database import get_connection as _gc
    conn = _gc()
    conn.execute(
        "INSERT INTO platforms (id, name, hull_type, hull_motion_factor) VALUES (2,'Gateway X','semisub',0.78)"
    )
    conn.commit()
    conn.close()

    site = Site(lat=28.5, lon=-80.6, name="Linked", platform_id=2)
    sc.save_site(site)
    retrieved = sc.get_site(site.id)
    assert retrieved.platform_id == 2


# ── get_site ──────────────────────────────────────────────────────────────────

def test_get_site_returns_site_type(cape_canaveral):
    sc.save_site(cape_canaveral)
    result = sc.get_site(cape_canaveral.id)
    assert isinstance(result, Site)

def test_get_site_not_found_raises():
    with pytest.raises(ValueError, match="No site with id=999"):
        sc.get_site(999)

def test_get_site_created_at_populated(cape_canaveral):
    sc.save_site(cape_canaveral)
    result = sc.get_site(cape_canaveral.id)
    assert result.created_at is not None

def test_get_site_coord_convention():
    # Negative lon = West; positive lat = North
    site = Site(lat=51.5, lon=-0.1, name="London Offshore")
    sc.save_site(site)
    result = sc.get_site(site.id)
    assert result.lat_dir == "N"
    assert result.lon_dir == "W"


# ── list_sites ────────────────────────────────────────────────────────────────

def test_list_sites_empty():
    assert sc.list_sites() == []

def test_list_sites_returns_all(cape_canaveral, pacific_site, north_atlantic):
    sc.save_site(cape_canaveral)
    sc.save_site(pacific_site)
    sc.save_site(north_atlantic)
    sites = sc.list_sites()
    assert len(sites) == 3

def test_list_sites_ordered_newest_first(cape_canaveral, pacific_site):
    sc.save_site(cape_canaveral)
    sc.save_site(pacific_site)
    sites = sc.list_sites()
    # pacific_site inserted second → should appear first
    assert sites[0].name == pacific_site.name

def test_list_sites_all_are_site_type(cape_canaveral, pacific_site):
    sc.save_site(cape_canaveral)
    sc.save_site(pacific_site)
    for s in sc.list_sites():
        assert isinstance(s, Site)


# ── delete_site ───────────────────────────────────────────────────────────────

def test_delete_site_removes_record(cape_canaveral):
    sc.save_site(cape_canaveral)
    sc.delete_site(cape_canaveral.id)
    with pytest.raises(ValueError):
        sc.get_site(cape_canaveral.id)

def test_delete_site_not_found_raises():
    with pytest.raises(ValueError, match="No site with id=42"):
        sc.delete_site(42)

def test_delete_site_only_removes_target(cape_canaveral, pacific_site):
    sc.save_site(cape_canaveral)
    sc.save_site(pacific_site)
    sc.delete_site(cape_canaveral.id)
    remaining = sc.list_sites()
    assert len(remaining) == 1
    assert remaining[0].name == pacific_site.name

def test_delete_then_list_empty(cape_canaveral):
    sc.save_site(cape_canaveral)
    sc.delete_site(cape_canaveral.id)
    assert sc.list_sites() == []


# ── bbox_corners ──────────────────────────────────────────────────────────────

def test_bbox_corners_keys(cape_canaveral):
    bb = sc.bbox_corners(cape_canaveral)
    assert set(bb.keys()) == {"north", "south", "east", "west"}

def test_bbox_corners_north_gt_south(cape_canaveral):
    bb = sc.bbox_corners(cape_canaveral)
    assert bb["north"] > bb["south"]

def test_bbox_corners_east_gt_west(cape_canaveral):
    bb = sc.bbox_corners(cape_canaveral)
    assert bb["east"] > bb["west"]

def test_bbox_corners_center_enclosed(cape_canaveral):
    bb = sc.bbox_corners(cape_canaveral)
    assert bb["south"] < cape_canaveral.lat < bb["north"]
    assert bb["west"]  < cape_canaveral.lon < bb["east"]

def test_bbox_corners_25nm_spread():
    # 25 NM ≈ 0.4167°, so total spread ~0.833°
    site = Site(lat=28.5, lon=-80.6, bbox_nm=25.0)
    bb = sc.bbox_corners(site)
    lat_spread = bb["north"] - bb["south"]
    assert 0.80 < lat_spread < 0.90

def test_bbox_corners_50nm_larger_than_25nm():
    s25 = Site(lat=28.5, lon=-80.6, bbox_nm=25.0)
    s50 = Site(lat=28.5, lon=-80.6, bbox_nm=50.0)
    bb25 = sc.bbox_corners(s25)
    bb50 = sc.bbox_corners(s50)
    assert (bb50["north"] - bb50["south"]) > (bb25["north"] - bb25["south"])

def test_bbox_corners_southern_hemisphere(pacific_site):
    bb = sc.bbox_corners(pacific_site)
    # Latitude -22.3 → north boundary should be less negative than south
    assert bb["north"] > bb["south"]
    assert bb["south"] < pacific_site.lat < bb["north"]

def test_bbox_corners_not_exceeding_poles():
    polar_site = Site(lat=89.9, lon=0.0, bbox_nm=200.0)
    bb = sc.bbox_corners(polar_site)
    assert bb["north"] <= 90.0

def test_bbox_corners_not_exceeding_antimeridian():
    west_site = Site(lat=0.0, lon=-179.5, bbox_nm=200.0)
    bb = sc.bbox_corners(west_site)
    assert bb["west"] >= -180.0


# ── Coordinate validation (guard against bad inputs reaching DB) ──────────────

def test_site_rejects_invalid_lat():
    with pytest.raises(ValueError):
        Site(lat=91.0, lon=0.0)

def test_site_rejects_invalid_lon():
    with pytest.raises(ValueError):
        Site(lat=0.0, lon=181.0)

def test_site_accepts_negative_lat_south():
    s = Site(lat=-33.9, lon=18.4, name="Cape Town Offshore")
    assert s.lat_dir == "S"

def test_site_accepts_positive_lon_east():
    s = Site(lat=35.0, lon=139.5, name="Pacific Launch Zone")
    assert s.lon_dir == "E"


if __name__ == "__main__":
    import pytest as _pt
    _pt.main([__file__, "-v"])

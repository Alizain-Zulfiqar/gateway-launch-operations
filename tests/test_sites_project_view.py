"""tests/test_sites_project_view.py — By Project mode filtering via list_project_sites."""
from __future__ import annotations

import pytest
import core.database as db_mod


@pytest.fixture()
def db_file(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture(autouse=True)
def _patch_db(db_file, monkeypatch):
    monkeypatch.setattr(db_mod, "DB_PATH", str(db_file))
    db_mod.init_db()


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _create_project(name: str = "Test Project") -> int:
    from core.database import get_connection
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO projects (name, status) VALUES (?, 'active')", (name,))
    conn.commit()
    pid = c.lastrowid
    conn.close()
    return pid


def _create_site(name: str = "Test Site", lat: float = 28.5, lon: float = -80.6) -> int:
    from modules.m1_site.site_config import save_site
    from core.models import Site
    site = Site(lat=lat, lon=lon, name=name)
    return save_site(site)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_by_project_mode_filters_correctly():
    from modules.m1_site.project_sites import (
        add_site_to_project, change_site_status, list_project_sites,
    )

    project_id = _create_project()
    site_a = _create_site(name="A", lat=20.0, lon=-75.0)
    site_b = _create_site(name="B", lat=21.0, lon=-74.0)

    add_site_to_project(project_id, site_a)
    change_site_status(project_id, site_a, "final")
    add_site_to_project(project_id, site_b)
    # site_b stays 'candidate'

    final_results = list_project_sites(project_id, status_filter=["final"])
    assert len(final_results) == 1
    assert final_results[0]["site_id"] == site_a

    all_results = list_project_sites(project_id)
    assert len(all_results) == 2


def test_empty_project_shows_no_sites():
    from modules.m1_site.project_sites import list_project_sites

    project_id = _create_project()
    results = list_project_sites(project_id)
    assert len(results) == 0


def test_filter_accepts_list_of_statuses():
    """Filter can accept multiple statuses at once."""
    from modules.m1_site.project_sites import (
        add_site_to_project, change_site_status, list_project_sites,
    )

    project_id = _create_project()
    site_a = _create_site(name="A", lat=20.0, lon=-75.0)
    site_b = _create_site(name="B", lat=21.0, lon=-74.0)
    site_c = _create_site(name="C", lat=22.0, lon=-73.0)

    add_site_to_project(project_id, site_a)
    add_site_to_project(project_id, site_b)
    add_site_to_project(project_id, site_c)

    change_site_status(project_id, site_a, "final")
    change_site_status(project_id, site_b, "rejected")
    # site_c stays candidate

    terminal_results = list_project_sites(
        project_id, status_filter=["final", "rejected"]
    )
    assert len(terminal_results) == 2
    site_ids = {r["site_id"] for r in terminal_results}
    assert site_ids == {site_a, site_b}


def test_filter_accepts_string_backwards_compat():
    """Passing a plain string (not a list) still works."""
    from modules.m1_site.project_sites import (
        add_site_to_project, change_site_status, list_project_sites,
    )

    project_id = _create_project()
    site_a = _create_site(name="A", lat=20.0, lon=-75.0)
    add_site_to_project(project_id, site_a)
    change_site_status(project_id, site_a, "approved")

    results = list_project_sites(project_id, status_filter="approved")
    assert len(results) == 1
    assert results[0]["site_id"] == site_a


def test_result_includes_history_count():
    """Each result row includes history_count showing all appended rows."""
    from modules.m1_site.project_sites import (
        add_site_to_project, change_site_status, list_project_sites,
    )

    project_id = _create_project()
    site_a = _create_site(name="A", lat=20.0, lon=-75.0)
    add_site_to_project(project_id, site_a)         # history row 1
    change_site_status(project_id, site_a, "approved")  # history row 2
    change_site_status(project_id, site_a, "final")     # history row 3

    results = list_project_sites(project_id)
    assert len(results) == 1
    assert results[0]["history_count"] == 3


def test_unknown_status_filter_returns_empty():
    """Filtering by a status that no site has returns empty list."""
    from modules.m1_site.project_sites import add_site_to_project, list_project_sites

    project_id = _create_project()
    site_a = _create_site(name="A", lat=20.0, lon=-75.0)
    add_site_to_project(project_id, site_a)

    results = list_project_sites(project_id, status_filter=["down-selected"])
    assert len(results) == 0


def test_result_includes_platform_name_when_set():
    """platform_name is included when site has a platform_id set."""
    from modules.m1_site.project_sites import add_site_to_project, list_project_sites
    from core.database import get_connection

    # Create a platform
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO platforms (name, hull_type, hull_motion_factor) "
        "VALUES ('TestPlatform', 'semisub', 0.78)"
    )
    conn.commit()
    platform_id = c.lastrowid
    conn.close()

    # Create site with that platform
    from modules.m1_site.site_config import save_site
    from core.models import Site
    site = Site(lat=20.0, lon=-75.0, name="PlatformSite", platform_id=platform_id)
    site_id = save_site(site)

    project_id = _create_project()
    add_site_to_project(project_id, site_id)

    results = list_project_sites(project_id)
    assert len(results) == 1
    assert results[0]["platform_name"] == "TestPlatform"

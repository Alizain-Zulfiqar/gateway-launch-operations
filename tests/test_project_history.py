"""tests/test_project_history.py — project site history write/read/archive tests."""
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

def test_add_site_to_project_creates_history_row():
    from modules.m1_site.project_sites import add_site_to_project, get_site_history
    pid = _create_project()
    sid = _create_site()

    history_id = add_site_to_project(pid, sid, changed_by="tester")

    assert isinstance(history_id, int)
    history = get_site_history(pid, sid)
    assert len(history) == 1
    assert history[0]["status"] == "candidate"
    assert history[0]["changed_by"] == "tester"


def test_add_site_to_project_raises_if_already_added():
    from modules.m1_site.project_sites import add_site_to_project
    pid = _create_project()
    sid = _create_site()

    add_site_to_project(pid, sid)
    with pytest.raises(ValueError, match="already in project"):
        add_site_to_project(pid, sid)


def test_change_site_status_appends_row():
    from modules.m1_site.project_sites import add_site_to_project, change_site_status, get_site_history
    pid = _create_project()
    sid = _create_site()

    add_site_to_project(pid, sid)
    change_site_status(pid, sid, "approved", changed_by="reviewer", approval_note="Looks good")

    history = get_site_history(pid, sid)
    assert len(history) == 2
    assert history[0]["status"] == "approved"
    assert history[0]["approval_note"] == "Looks good"
    assert history[1]["status"] == "candidate"


def test_get_current_status_reflects_latest():
    from modules.m1_site.project_sites import add_site_to_project, change_site_status, get_current_status
    pid = _create_project()
    sid = _create_site()

    add_site_to_project(pid, sid)
    change_site_status(pid, sid, "approved")
    change_site_status(pid, sid, "final")

    current = get_current_status(pid, sid)
    assert current is not None
    assert current["status"] == "final"


def test_get_current_status_returns_none_for_unknown_pair():
    from modules.m1_site.project_sites import get_current_status
    assert get_current_status(999, 999) is None


def test_list_project_sites_returns_all():
    from modules.m1_site.project_sites import add_site_to_project, list_project_sites
    pid = _create_project()
    sid1 = _create_site("Alpha", 20.0, -80.0)
    sid2 = _create_site("Beta",  21.0, -79.0)

    add_site_to_project(pid, sid1)
    add_site_to_project(pid, sid2)

    sites = list_project_sites(pid)
    assert len(sites) == 2
    names = {s["site_name"] for s in sites}
    assert names == {"Alpha", "Beta"}


def test_list_project_sites_status_filter():
    from modules.m1_site.project_sites import add_site_to_project, change_site_status, list_project_sites
    pid = _create_project()
    sid1 = _create_site("Alpha", 20.0, -80.0)
    sid2 = _create_site("Beta",  21.0, -79.0)

    add_site_to_project(pid, sid1)
    add_site_to_project(pid, sid2)
    change_site_status(pid, sid1, "approved")

    approved = list_project_sites(pid, status_filter="approved")
    assert len(approved) == 1
    assert approved[0]["site_name"] == "Alpha"

    candidates = list_project_sites(pid, status_filter="candidate")
    assert len(candidates) == 1
    assert candidates[0]["site_name"] == "Beta"


def test_get_site_history_excludes_archived_by_default():
    from modules.m1_site.project_sites import (
        add_site_to_project, change_site_status,
        archive_site_history, get_site_history,
    )
    pid = _create_project()
    sid = _create_site()

    add_site_to_project(pid, sid)
    change_site_status(pid, sid, "approved")
    change_site_status(pid, sid, "final")
    archive_site_history(pid, sid)

    # Without include_archived: only most recent returned
    history = get_site_history(pid, sid)
    assert len(history) == 1
    assert history[0]["status"] == "final"


def test_get_site_history_includes_archived_when_requested():
    from modules.m1_site.project_sites import (
        add_site_to_project, change_site_status,
        archive_site_history, get_site_history,
    )
    pid = _create_project()
    sid = _create_site()

    add_site_to_project(pid, sid)
    change_site_status(pid, sid, "approved")
    change_site_status(pid, sid, "final")
    archive_site_history(pid, sid)

    history = get_site_history(pid, sid, include_archived=True)
    assert len(history) == 3


def test_archive_site_history_guard_non_terminal():
    from modules.m1_site.project_sites import add_site_to_project, archive_site_history
    pid = _create_project()
    sid = _create_site()

    add_site_to_project(pid, sid)  # status = candidate

    with pytest.raises(ValueError, match="Cannot archive"):
        archive_site_history(pid, sid)


def test_unarchive_restores_rows():
    from modules.m1_site.project_sites import (
        add_site_to_project, change_site_status,
        archive_site_history, unarchive_site_history, get_site_history,
    )
    pid = _create_project()
    sid = _create_site()

    add_site_to_project(pid, sid)
    change_site_status(pid, sid, "approved")
    change_site_status(pid, sid, "final")
    archive_site_history(pid, sid)

    count = unarchive_site_history(pid, sid)
    assert count == 2  # the two non-final rows are unarchived

    history = get_site_history(pid, sid)
    assert len(history) == 3


def test_archive_project_history_skips_non_terminal():
    from modules.m1_site.project_sites import (
        add_site_to_project, change_site_status, archive_project_history,
    )
    pid = _create_project()
    sid1 = _create_site("Alpha", 20.0, -80.0)
    sid2 = _create_site("Beta",  21.0, -79.0)
    sid3 = _create_site("Gamma", 22.0, -78.0)

    add_site_to_project(pid, sid1)
    add_site_to_project(pid, sid2)
    add_site_to_project(pid, sid3)

    # sid1 → final (archivable), sid2 → rejected (archivable), sid3 stays candidate
    change_site_status(pid, sid1, "approved")
    change_site_status(pid, sid1, "final")
    change_site_status(pid, sid2, "rejected")

    result = archive_project_history(pid)

    assert result["archived_sites"] == 2
    assert result["skipped_sites"] == 1
    assert result["total_rows_archived"] >= 2

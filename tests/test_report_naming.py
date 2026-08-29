"""tests/test_report_naming.py — Report filename generation and sequence numbers."""
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


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_project(
    code_name: str,
    launch_date_start: str = "2026-08-15",
    launch_date_end: str = "2026-08-18",
):
    from core.database import get_connection
    from core.models import Project
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO projects (name, code_name, launch_date_start, launch_date_end, status)"
        " VALUES (?, ?, ?, ?, 'active')",
        (code_name, code_name, launch_date_start, launch_date_end),
    )
    conn.commit()
    pid = c.lastrowid
    conn.close()
    return Project(
        id=pid,
        name=code_name,
        code_name=code_name,
        launch_date_start=launch_date_start,
        launch_date_end=launch_date_end,
    )


def _make_site(name: str, lat: float = 28.5, lon: float = -80.6):
    from modules.m1_site.site_config import save_site
    from core.models import Site
    site = Site(lat=lat, lon=lon, name=name)
    sid = save_site(site)
    site.id = sid
    return site


def _insert_report(project_id, site_id: int, report_type: str, seq: int) -> None:
    from core.database import get_connection
    conn = get_connection()
    conn.execute(
        "INSERT INTO reports "
        "(project_id, site_id, report_type, filename, sequence_number, file_path)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (project_id, site_id, report_type, f"dummy_{seq}.pdf", seq, f"/dummy/{seq}.pdf"),
    )
    conn.commit()
    conn.close()


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_sequence_number_per_project_type():
    """Sequence numbers are scoped per (project_id, report_type)."""
    from modules.m5_reports.naming import next_sequence_number

    project = _make_project("ALPHA")
    site = _make_site("Site A")

    assert next_sequence_number("analysis", project.id, site.id) == 1

    _insert_report(project.id, site.id, "analysis", 1)
    assert next_sequence_number("analysis", project.id, site.id) == 2

    # Voyage type is independent of analysis count
    assert next_sequence_number("voyage", project.id, site.id) == 1


def test_unassigned_sequence_per_site():
    """Unassigned reports scope to (site_id, report_type) where project_id IS NULL."""
    from modules.m5_reports.naming import next_sequence_number

    site = _make_site("Site B")

    assert next_sequence_number("voyage", None, site.id) == 1

    _insert_report(None, site.id, "voyage", 1)
    assert next_sequence_number("voyage", None, site.id) == 2


def test_filename_with_project():
    """Filename for a project-assigned analysis report matches the expected pattern."""
    from modules.m5_reports.naming import build_report_filename

    project = _make_project(
        code_name="MARLIN",
        launch_date_start="2026-08-15",
        launch_date_end="2026-08-18",
    )
    site = _make_site("Bermuda East", lat=32.5, lon=-61.2)
    site.coord_code = "N32W061"

    result = build_report_filename("analysis", site, project)

    assert result["filename"] == "MARLIN_BermudaEast-N32W061_20260815-20260818_A001.pdf"
    assert result["sequence_number"] == 1
    assert result["type_prefix"] == "A"


def test_filename_unassigned():
    """Unassigned voyage filename starts and ends with expected patterns."""
    from modules.m5_reports.naming import build_report_filename

    site = _make_site("Sargasso SW", lat=31.5, lon=-66.2)
    site.coord_code = "N31W066"

    result = build_report_filename("voyage", site, project=None)

    assert result["filename"].startswith("UNASSIGNED_SargassoSW-N31W066_")
    assert result["filename"].endswith("_V001.pdf")
    assert result["sequence_number"] == 1
    assert result["type_prefix"] == "V"


def test_sanitize_removes_unsafe_chars():
    """sanitize() strips <>\"/\\|?* and joins remaining words CamelCase."""
    from modules.m5_reports.naming import sanitize

    assert sanitize("Bermuda East") == "BermudaEast"
    assert sanitize("Site: Test/2") == "SiteTest2"
    assert sanitize("ABC") == "ABC"
    assert sanitize("multi space") == "MultiSpace"
    assert sanitize('has"quotes') == "Hasquotes"  # no space → single word after removal

"""
tests/test_vessel_dimensions.py — Vessel dimension columns and utility functions.
"""
import pytest
from core.database import get_connection, init_db
from core.utils import fmt_length, m_to_ft


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    import core.database as db_mod
    monkeypatch.setattr(db_mod, "DB_PATH", str(db_file))
    init_db()


def _insert_platform(conn, name, **kwargs):
    kwargs.setdefault("hull_type", "semisub")
    kwargs.setdefault("hull_motion_factor", 1.0)
    cols = ["name"] + list(kwargs.keys())
    vals = [name] + list(kwargs.values())
    placeholders = ", ".join("?" for _ in vals)
    conn.execute(
        f"INSERT INTO platforms ({', '.join(cols)}) VALUES ({placeholders})", vals
    )
    conn.commit()
    return conn.execute("SELECT * FROM platforms WHERE name=?", (name,)).fetchone()


def test_loa_stored_in_meters():
    conn = get_connection()
    row = _insert_platform(conn, "LOA Test", loa_m=120.0)
    conn.close()
    assert row["loa_m"] == pytest.approx(120.0)


def test_fmt_length_format():
    result = fmt_length(120.0)
    assert "120.0 m" in result
    assert "393.7 ft" in result


def test_dp_class_values():
    conn = get_connection()
    for dp in (1, 2, 3):
        _insert_platform(conn, f"DP{dp} Platform", dp_class=dp)
    rows = conn.execute(
        "SELECT dp_class FROM platforms WHERE name LIKE 'DP% Platform'"
    ).fetchall()
    conn.close()
    stored = {r["dp_class"] for r in rows}
    assert stored == {1, 2, 3}


def test_air_gap_fields():
    conn = get_connection()
    row = _insert_platform(
        conn, "Air Gap Test",
        min_air_gap_m=5.0, max_wave_crest_m=3.5, deck_elevation_m=8.0
    )
    conn.close()
    clearance = row["deck_elevation_m"] - row["max_wave_crest_m"]
    assert row["min_air_gap_m"] == pytest.approx(5.0)
    assert row["max_wave_crest_m"] == pytest.approx(3.5)
    assert row["deck_elevation_m"] == pytest.approx(8.0)
    assert clearance == pytest.approx(4.5)


def test_gateway_s_confirmed_drafts():
    conn = get_connection()
    row = _insert_platform(
        conn, "Gateway S",
        transit_draft_m=2.591, launch_draft_m=4.267,
        min_depth_m=6.401, dp_class=2,
        specs_verified=1,
        specs_verified_source="Operator provided 2026-06-27",
    )
    conn.close()
    assert row["transit_draft_m"] == pytest.approx(2.591)
    assert row["launch_draft_m"] == pytest.approx(4.267)
    assert row["specs_verified"] == 1


def test_gateway_x_unverified_drafts():
    conn = get_connection()
    row = _insert_platform(conn, "Gateway X", specs_verified=0)
    conn.close()
    assert row["transit_draft_m"] is None
    assert row["launch_draft_m"] is None
    assert row["specs_verified"] == 0

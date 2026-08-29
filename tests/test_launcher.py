"""
tests/test_launcher.py — Launcher DB schema tests.
"""
import pytest
from core.database import get_connection, init_db


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    import core.database as db_mod
    monkeypatch.setattr(db_mod, "DB_PATH", str(db_file))
    init_db()


def test_launcher_config_table_exists():
    conn = get_connection()
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='launcher_configs'"
    ).fetchone()
    conn.close()
    assert row is not None


def test_launcher_vehicle_compat_table_exists():
    conn = get_connection()
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='launcher_vehicle_compat'"
    ).fetchone()
    conn.close()
    assert row is not None


def test_launcher_types_valid():
    conn = get_connection()
    for lt in ("rail", "vertical_fixed", "vertical_mobile", "air_carrier"):
        conn.execute(
            "INSERT INTO launcher_configs (launcher_name, launcher_type, mount_method) VALUES (?,?,?)",
            (f"Test {lt}", lt, "other"),
        )
    conn.commit()
    rows = conn.execute("SELECT launcher_type FROM launcher_configs").fetchall()
    conn.close()
    types_stored = {r["launcher_type"] for r in rows}
    assert types_stored == {"rail", "vertical_fixed", "vertical_mobile", "air_carrier"}


def test_launcher_mount_methods():
    conn = get_connection()
    for mm in ("underslung", "top_mount", "side_clamp", "cradle", "captive_bolt"):
        conn.execute(
            "INSERT INTO launcher_configs (launcher_name, launcher_type, mount_method) VALUES (?,?,?)",
            (f"Test {mm}", "vertical_fixed", mm),
        )
    conn.commit()
    rows = conn.execute("SELECT mount_method FROM launcher_configs").fetchall()
    conn.close()
    methods = {r["mount_method"] for r in rows}
    assert methods == {"underslung", "top_mount", "side_clamp", "cradle", "captive_bolt"}


def test_deck_load_positive():
    conn = get_connection()
    conn.execute(
        "INSERT INTO launcher_configs (launcher_name, launcher_type, mount_method, deck_load_kpa) VALUES (?,?,?,?)",
        ("LoadTest", "vertical_fixed", "top_mount", 25.0),
    )
    conn.commit()
    row = conn.execute(
        "SELECT deck_load_kpa FROM launcher_configs WHERE launcher_name='LoadTest'"
    ).fetchone()
    conn.close()
    assert row["deck_load_kpa"] == pytest.approx(25.0)


def test_blast_radius_stored():
    conn = get_connection()
    conn.execute(
        "INSERT INTO launcher_configs (launcher_name, launcher_type, mount_method, blast_radius_m) VALUES (?,?,?,?)",
        ("BlastTest", "rail", "cradle", 150.0),
    )
    conn.commit()
    row = conn.execute(
        "SELECT blast_radius_m FROM launcher_configs WHERE launcher_name='BlastTest'"
    ).fetchone()
    conn.close()
    assert row["blast_radius_m"] == pytest.approx(150.0)

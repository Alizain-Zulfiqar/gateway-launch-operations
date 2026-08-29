"""
tests/test_pre28b1.py — Pre-28B-1: vessel codes, platform contracts, hierarchy
traversal, and the Option 2 vessel pre-check gate.

Uses the real DB (via get_connection), inserting and cleaning up test rows, and
ensures the schema/vessel-code assignment has run via init_db() at import.
"""
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import get_connection, init_db

# Ensure the vessel_code column, platform_contracts table, and pinned codes exist.
init_db()


# ── Vessel codes (Part A) ─────────────────────────────────────────────────────

@pytest.mark.parametrize("name,code", [
    ("Gateway S", "0100"),
    ("Gateway X", "0101"),
    ("Gateway XL", "0102"),
])
def test_vessel_code_pinned(name, code):
    conn = get_connection()
    row = conn.execute(
        "SELECT vessel_code FROM platforms WHERE name=?", (name,)
    ).fetchone()
    conn.close()
    assert row is not None, f"{name} not seeded"
    assert row[0] == code


def test_vessel_code_unique():
    conn = get_connection()
    rows = conn.execute("""
        SELECT vessel_code, COUNT(*) AS n FROM platforms
        WHERE vessel_code IS NOT NULL
        GROUP BY vessel_code HAVING n > 1
    """).fetchall()
    conn.close()
    assert len(rows) == 0, f"Duplicate vessel codes: {[r[0] for r in rows]}"


# ── Contract code validation (Part B) ─────────────────────────────────────────

def test_validate_contract_code_valid():
    from config import validate_contract_code
    assert validate_contract_code("LM1_0100_10012026_09302027")
    assert validate_contract_code("FF1_0101_01152027_01142028")


def test_validate_contract_code_invalid():
    from config import validate_contract_code
    assert not validate_contract_code("LM1_10012026_09302027")     # missing vessel seg
    assert not validate_contract_code("lm1_0100_10012026_09302027")  # lowercase
    assert not validate_contract_code("LM1_0100_1012026_09302027")   # short date


# ── Hierarchy helpers ─────────────────────────────────────────────────────────

def _mk_platform(conn, vessel_code):
    conn.execute(
        "INSERT OR IGNORE INTO platforms (name, hull_type, hull_motion_factor, vessel_code) "
        "VALUES (?, 'semisub', 0.78, ?)",
        (f"P_{vessel_code}", vessel_code),
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM platforms WHERE vessel_code=?", (vessel_code,)
    ).fetchone()[0]


def _mk_contract(conn, pid, vessel_code, code, tier="master", parent=None, **warranted):
    cols = ["platform_id", "vessel_code", "contract_code", "customer_name",
            "contract_tier", "parent_contract_id", "contract_start", "contract_end"]
    vals = [pid, vessel_code, code, "Test", tier, parent, "2026-01-01", "2026-12-31"]
    for k, v in warranted.items():
        cols.append(k)
        vals.append(v)
    placeholders = ",".join("?" for _ in cols)
    conn.execute(
        f"INSERT INTO platform_contracts ({','.join(cols)}) VALUES ({placeholders})",
        vals,
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM platform_contracts WHERE contract_code=?", (code,)
    ).fetchone()[0]


def test_hierarchy_subcontract_overrides():
    from modules.m1_site.contracts import resolve_warranted_envelope
    conn = get_connection()
    try:
        pid = _mk_platform(conn, "9990")
        mid = _mk_contract(conn, pid, "9990", "OVR_MASTER", "master",
                           warranted_max_hs_m=2.5)
        sid = _mk_contract(conn, pid, "9990", "OVR_SUB", "subcontract", parent=mid,
                           warranted_max_hs_m=3.0)
        envelope, code = resolve_warranted_envelope(sid)
        assert envelope.get("sh") == 3.0
        assert code == "OVR_SUB"
    finally:
        conn.execute("DELETE FROM platform_contracts WHERE contract_code IN ('OVR_MASTER','OVR_SUB')")
        conn.execute("DELETE FROM platforms WHERE vessel_code='9990'")
        conn.commit()
        conn.close()


def test_hierarchy_null_falls_back_to_master():
    from modules.m1_site.contracts import resolve_warranted_envelope
    conn = get_connection()
    try:
        pid = _mk_platform(conn, "9991")
        mid = _mk_contract(conn, pid, "9991", "NULL_MASTER", "master",
                           warranted_max_wind_kts=25.0)
        sid = _mk_contract(conn, pid, "9991", "NULL_SUB", "subcontract", parent=mid,
                           warranted_max_hs_m=3.0)  # sub does NOT set wind
        envelope, _ = resolve_warranted_envelope(sid)
        assert envelope.get("ws") == 25.0   # inherited from master
        assert envelope.get("sh") == 3.0    # from sub
    finally:
        conn.execute("DELETE FROM platform_contracts WHERE contract_code IN ('NULL_MASTER','NULL_SUB')")
        conn.execute("DELETE FROM platforms WHERE vessel_code='9991'")
        conn.commit()
        conn.close()


def test_cycle_detection(caplog):
    from modules.m1_site.contracts import resolve_warranted_envelope
    conn = get_connection()
    try:
        pid = _mk_platform(conn, "9999")
        id_a = _mk_contract(conn, pid, "9999", "CYCLE_A", "master")
        id_b = _mk_contract(conn, pid, "9999", "CYCLE_B", "subcontract", parent=id_a)
        # Create the cycle: A now points to B.
        conn.execute("UPDATE platform_contracts SET parent_contract_id=? WHERE id=?",
                     (id_b, id_a))
        conn.commit()

        with caplog.at_level(logging.WARNING):
            envelope, code = resolve_warranted_envelope(id_a)
        assert any("Cycle" in m for m in caplog.messages)
    finally:
        conn.execute("DELETE FROM platform_contracts WHERE contract_code IN ('CYCLE_A','CYCLE_B')")
        conn.execute("DELETE FROM platforms WHERE vessel_code='9999'")
        conn.commit()
        conn.close()


# ── Vessel gate (Part D) ──────────────────────────────────────────────────────

def test_vessel_gate_more_conservative_wins():
    from core.models import Site, Vehicle, Platform
    from modules.m3_probability.engine import compute_probability
    from modules.m1_site.contracts import apply_vessel_gate

    site = Site(lat=32.6, lon=-61.1, name="Test")
    v = Vehicle(name="T", vehicle_class="slv_orb", recovery_mode="expendable",
                max_wind_kts=18, max_gust_kts=25, max_hs_m=1.5,
                max_swell_ht_m=2.0, max_swell_period_s=12)
    p = Platform("Gateway X", "semisub", 0.78)
    res = compute_probability(site, v, p, month=6)

    warranted = {"sh": 2.5}   # vessel looser than vehicle 1.5 → vehicle governs
    thresholds = {"ws": 18, "wg": 25, "sh": 1.5, "swh": 2.0, "swp": 12}
    vpp, verdict, limiting = apply_vessel_gate(
        warranted, thresholds, res.param_probs, res.active_params
    )
    assert limiting in {"ws", "wg", "sh", "swh", "swp"}
    # sh governed by the tighter vehicle limit → unchanged from vehicle prob
    assert vpp["sh"] == pytest.approx(res.param_probs["sh"])


def test_compute_probability_no_contract():
    from core.models import Site, Vehicle, Platform
    from modules.m3_probability.engine import compute_probability

    site = Site(lat=32.6, lon=-61.1, name="Test")
    v = Vehicle(name="T", vehicle_class="slv_orb", recovery_mode="expendable",
                max_wind_kts=18, max_gust_kts=25, max_hs_m=1.5,
                max_swell_ht_m=2.0, max_swell_period_s=12)
    p = Platform("Gateway X", "semisub", 0.78)
    result = compute_probability(site, v, p, month=6)

    assert result.vessel_verdict is None
    assert result.vessel_limiting_param is None
    assert result.vessel_contract_code is None

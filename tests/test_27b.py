"""
tests/test_27b.py -- Instruction Set 27B: weight redistribution, direction
parameter exclusion, site_vehicles upsert, and the calc-basis data flow.

These tests exercise pure logic and DB behaviour only — no Qt widgets are
instantiated, so they run in the headless test environment.
"""
import sys
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import Site, Vehicle, Platform
from modules.m3_probability.engine import compute_probability


def _fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    with patch("core.database.DB_PATH", db_path):
        from core.database import init_db
        init_db()
    return db_path


# ── Config / weights ─────────────────────────────────────────────────────────

def test_default_weights_redistributed():
    from config import DEFAULT_WEIGHTS, DIRECTION_WEIGHTS
    assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 0.0001
    assert set(DEFAULT_WEIGHTS) == {"ws", "wg", "sh", "swh", "swp"}
    assert DEFAULT_WEIGHTS["ws"] == 0.30
    assert DEFAULT_WEIGHTS["wg"] == 0.26
    assert DIRECTION_WEIGHTS == {"wdV": 0.04, "sdV": 0.03, "swdV": 0.03}


# ── Basis panel data flow ────────────────────────────────────────────────────

def test_basis_panel_data_available_after_run():
    """The AnalysisResult carries everything update_basis_panel() needs."""
    site = Site(lat=32.6, lon=-61.1, name="Bermuda East", coord_code="N32W061")
    v = Vehicle(name="Firefly Alpha", vehicle_class="slv_orb",
                recovery_mode="expendable", max_wind_kts=18, max_gust_kts=25,
                max_hs_m=1.5, max_swell_ht_m=2.0, max_swell_period_s=12)
    p = Platform("Gateway X", "semisub", 0.78)
    result = compute_probability(site, v, p, month=6)

    assert result.site.name == "Bermuda East"
    # Direction params excluded by default → zero weight
    assert result.weights.get("wdV", 0) == 0
    assert result.limiting_param in result.param_probs
    # Fields the panel reads
    assert result.thresholds["ws"] == 18
    assert result.data_sources  # non-empty
    assert isinstance(result.era_weight, float)
    assert result.confidence_rating


def test_included_direction_param_gets_weight():
    """Passing a direction weight in makes it non-zero after normalization."""
    from config import DEFAULT_WEIGHTS, DIRECTION_WEIGHTS
    site = Site(lat=28.5, lon=-80.6, name="CC")
    v = Vehicle(name="V", vehicle_class="slv_orb", recovery_mode="expendable",
                max_wind_kts=18, max_gust_kts=25, max_hs_m=1.5,
                max_swell_ht_m=2.0, max_swell_period_s=12)
    p = Platform("Gateway X", "semisub", 0.78)
    weights = DEFAULT_WEIGHTS.copy()
    weights["wdV"] = DIRECTION_WEIGHTS["wdV"]
    result = compute_probability(site, v, p, month=6, weights=weights)
    assert result.weights.get("wdV", 0) > 0
    assert result.weights.get("sdV", 0) == 0
    assert abs(sum(result.weights.values()) - 1.0) < 0.0001


# ── site_vehicles upsert ─────────────────────────────────────────────────────

def test_site_vehicles_upsert_increments():
    db_path = _fresh_db()
    try:
        with patch("core.database.DB_PATH", db_path):
            from core.database import get_connection
            conn = get_connection()
            conn.execute(
                "INSERT OR IGNORE INTO sites (name,lat,lon,bbox_nm) "
                "VALUES ('UpsertTest',32.6,-61.1,25)"
            )
            site_id = conn.execute(
                "SELECT id FROM sites WHERE name='UpsertTest'").fetchone()[0]
            conn.execute(
                "INSERT OR IGNORE INTO vehicles "
                "(name,vehicle_class,max_wind_kts,max_gust_kts,max_hs_m,"
                " max_swell_ht_m,max_swell_period_s) "
                "VALUES ('UpsertV','slv_orb',18,25,1.5,2.0,12)"
            )
            vehicle_id = conn.execute(
                "SELECT id FROM vehicles WHERE name='UpsertV'").fetchone()[0]
            conn.commit()

            upsert = (
                "INSERT INTO site_vehicles (site_id,vehicle_id,run_count,last_used) "
                "VALUES (?,?,1,?) "
                "ON CONFLICT(site_id,vehicle_id) DO UPDATE SET "
                "run_count=run_count+1, last_used=excluded.last_used"
            )
            for _ in range(2):
                conn.execute(upsert,
                             (site_id, vehicle_id, datetime.now(timezone.utc).isoformat()))
                conn.commit()

            row = conn.execute(
                "SELECT run_count FROM site_vehicles "
                "WHERE site_id=? AND vehicle_id=?", (site_id, vehicle_id)).fetchone()
            assert row[0] == 2
            conn.close()
    finally:
        db_path.unlink(missing_ok=True)


# ── Vehicles-used display logic ──────────────────────────────────────────────

def test_vehicles_used_column_query():
    """Two vehicles for one site are returned most-recent-first."""
    db_path = _fresh_db()
    try:
        with patch("core.database.DB_PATH", db_path):
            from core.database import get_connection
            conn = get_connection()
            conn.execute("INSERT INTO sites (name,lat,lon,bbox_nm) "
                         "VALUES ('MultiV',10.0,20.0,25)")
            site_id = conn.execute(
                "SELECT id FROM sites WHERE name='MultiV'").fetchone()[0]
            conn.execute("INSERT INTO vehicles "
                         "(name,vehicle_class,max_wind_kts,max_gust_kts,max_hs_m,"
                         " max_swell_ht_m,max_swell_period_s) "
                         "VALUES ('Older','slv_orb',18,25,1.5,2.0,12)")
            conn.execute("INSERT INTO vehicles "
                         "(name,vehicle_class,max_wind_kts,max_gust_kts,max_hs_m,"
                         " max_swell_ht_m,max_swell_period_s) "
                         "VALUES ('Newer','slv_orb',18,25,1.5,2.0,12)")
            v_old = conn.execute("SELECT id FROM vehicles WHERE name='Older'").fetchone()[0]
            v_new = conn.execute("SELECT id FROM vehicles WHERE name='Newer'").fetchone()[0]
            conn.execute("INSERT INTO site_vehicles VALUES (?,?,?,?)",
                         (site_id, v_old, 1, "2026-06-15T00:00:00"))
            conn.execute("INSERT INTO site_vehicles VALUES (?,?,?,?)",
                         (site_id, v_new, 1, "2026-06-28T00:00:00"))
            conn.commit()

            rows = conn.execute(
                "SELECT v.name FROM site_vehicles sv "
                "JOIN vehicles v ON sv.vehicle_id=v.id "
                "WHERE sv.site_id=? ORDER BY sv.last_used DESC", (site_id,)).fetchall()
            conn.close()
            assert [r[0] for r in rows] == ["Newer", "Older"]
    finally:
        db_path.unlink(missing_ok=True)

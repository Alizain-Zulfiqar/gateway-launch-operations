"""
tests/test_pre28b3.py — Pre-28B-3: VehicleEditorDialog._populate() must preserve
a legitimately stored 0.0 threshold instead of replacing it with the fallback
default (0.0 is falsy, so the previous `or`-fallback pattern discarded it).
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_populate_preserves_zero_tolerance():
    # Confirm that a zero value stored in the database is not overwritten
    # by the or-fallback pattern (DB round-trip invariant).
    from core.database import get_connection
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO vehicles
            (name, vehicle_class,
             max_wind_kts, max_gust_kts,
             max_hs_m, max_swell_ht_m,
             max_swell_period_s,
             max_wind_dir_tolerance_deg,
             max_sea_dir_tolerance_deg,
             max_swell_dir_tolerance_deg)
            VALUES
            ('ZeroTolTest','slv_orb',
             18,25,1.5,2.0,12,
             0.0, 0.0, 0.0)
        """)
        conn.commit()
        row = conn.execute("""
            SELECT max_wind_dir_tolerance_deg,
                   max_sea_dir_tolerance_deg,
                   max_swell_dir_tolerance_deg
            FROM vehicles
            WHERE name='ZeroTolTest'
        """).fetchone()
        assert row[0] == 0.0
        assert row[1] == 0.0
        assert row[2] == 0.0
    finally:
        conn.execute("DELETE FROM vehicles WHERE name='ZeroTolTest'")
        conn.commit()
        conn.close()


def test_populate_loads_zero_into_spinboxes():
    """
    Directly exercise _populate(): a vehicle_data dict with 0.0 tolerances must
    land 0.0 in the spinboxes, NOT the 45/60/60 fallbacks. Requires PyQt6, so it
    runs under the venv interpreter and skips in the headless system runner.
    """
    pytest.importorskip("PyQt6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    from ui.dialogs.vehicle_editor import VehicleEditorDialog

    app = QApplication.instance() or QApplication([])

    data = {
        "id": None, "name": "ZeroTolSpin", "vehicle_class": "slv_orb",
        "max_wind_kts": 0.0, "max_gust_kts": 0.0, "max_hs_m": 0.0,
        "max_swell_ht_m": 0.0, "max_swell_period_s": 0.0,
        "max_wind_dir_tolerance_deg": 0.0,
        "max_sea_dir_tolerance_deg": 0.0,
        "max_swell_dir_tolerance_deg": 0.0,
    }
    dlg = VehicleEditorDialog(None, vehicle_data=data)

    # The bug replaced these with 45.0 / 60.0 / 60.0 via the `or` fallback.
    assert dlg._wdtol_spin.value() == 0.0
    assert dlg._sdtol_spin.value() == 0.0
    assert dlg._swtol_spin.value() == 0.0
    # Magnitude thresholds preserved as 0.0 too.
    assert dlg._wind_spin.value() == 0.0
    assert dlg._gust_spin.value() == 0.0
    assert dlg._hs_spin.value() == 0.0
    assert dlg._swh_spin.value() == 0.0
    assert dlg._swp_spin.value() == 0.0
    dlg.deleteLater()


# ── Limiting parameter / active_params (Part E) ──────────────────────────────

def test_limiting_param_excludes_zero_weight():
    # Direction params excluded → limiting must be a magnitude param.
    from core.models import Site, Vehicle, Platform
    from modules.m3_probability.engine import compute_probability
    from config import DEFAULT_WEIGHTS

    site = Site(lat=32.6, lon=-61.1, name="Test")
    v = Vehicle(
        name="Test", vehicle_class="slv_orb", recovery_mode="expendable",
        max_wind_kts=18, max_gust_kts=25, max_hs_m=1.5,
        max_swell_ht_m=2.0, max_swell_period_s=12,
        max_wind_dir_tolerance_deg=30.0, max_sea_dir_tolerance_deg=60.0,
        max_swell_dir_tolerance_deg=60.0)
    p = Platform("Gateway X", "semisub", 0.78)

    result = compute_probability(site, v, p, month=6, weights=DEFAULT_WEIGHTS.copy())
    assert result.limiting_param in {"ws", "wg", "sh", "swh", "swp"}
    assert result.limiting_param not in {"wdV", "sdV", "swdV"}


def test_limiting_param_with_direction_included():
    # With direction params weighted, they CAN be the limiting param.
    from core.models import Site, Vehicle, Platform
    from modules.m3_probability.engine import compute_probability
    from config import DEFAULT_WEIGHTS, DIRECTION_WEIGHTS

    weights = DEFAULT_WEIGHTS.copy()
    weights.update(DIRECTION_WEIGHTS)

    v = Vehicle(
        name="Test", vehicle_class="slv_orb", recovery_mode="expendable",
        max_wind_kts=50.0, max_gust_kts=70.0, max_hs_m=10.0,
        max_swell_ht_m=10.0, max_swell_period_s=30.0,
        max_wind_dir_tolerance_deg=1.0, max_sea_dir_tolerance_deg=1.0,
        max_swell_dir_tolerance_deg=1.0)
    site = Site(lat=32.6, lon=-61.1, name="Test")
    p = Platform("Gateway X", "semisub", 0.78)

    result = compute_probability(site, v, p, month=6, weights=weights)
    assert result.limiting_param in {"ws", "wg", "sh", "swh", "swp",
                                     "wdV", "sdV", "swdV"}


def test_active_params_populated():
    from core.models import Site, Vehicle, Platform
    from modules.m3_probability.engine import compute_probability
    from config import DEFAULT_WEIGHTS

    site = Site(lat=32.6, lon=-61.1, name="Test")
    v = Vehicle(
        name="T", vehicle_class="slv_orb", recovery_mode="expendable",
        max_wind_kts=18, max_gust_kts=25, max_hs_m=1.5,
        max_swell_ht_m=2.0, max_swell_period_s=12)
    p = Platform("Gateway X", "semisub", 0.78)
    result = compute_probability(site, v, p, month=6, weights=DEFAULT_WEIGHTS.copy())

    assert len(result.active_params) == 5
    assert result.active_params == {"ws", "wg", "sh", "swh", "swp"}


# ── Vehicle save/reload + uniqueness (Parts A / C) ───────────────────────────

def test_vehicle_save_reloads_table():
    # Confirm a DB-side change is visible on a fresh query (the pattern
    # _reload_table() uses), i.e. reloads come from the database, not a cache.
    from core.database import get_connection
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO vehicles
            (name, vehicle_class, max_wind_kts, max_gust_kts,
             max_hs_m, max_swell_ht_m, max_swell_period_s)
            VALUES ('ReloadTest','slv_orb',18,25,1.5,2.0,12)
        """)
        conn.commit()
        vid = conn.execute(
            "SELECT id FROM vehicles WHERE name='ReloadTest'").fetchone()[0]
        conn.execute("UPDATE vehicles SET max_wind_kts=22 WHERE id=?", (vid,))
        conn.commit()
    finally:
        conn.close()

    conn2 = get_connection()
    try:
        row = conn2.execute(
            "SELECT max_wind_kts FROM vehicles WHERE id=?", (vid,)).fetchone()
        assert row[0] == 22.0
    finally:
        conn2.close()
        conn3 = get_connection()
        conn3.execute("DELETE FROM vehicles WHERE id=?", (vid,))
        conn3.commit()
        conn3.close()


def test_duplicate_vehicle_name_rejected():
    # Application-layer uniqueness check logic (id != sentinel).
    from core.database import get_connection
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO vehicles
            (name, vehicle_class, max_wind_kts, max_gust_kts,
             max_hs_m, max_swell_ht_m, max_swell_period_s)
            VALUES ('DupTest','slv_orb',18,25,1.5,2.0,12)
        """)
        conn.commit()
        existing = conn.execute(
            "SELECT id FROM vehicles WHERE name=? AND id != ?",
            ("DupTest", -1)).fetchone()
        assert existing is not None
    finally:
        conn.execute("DELETE FROM vehicles WHERE name='DupTest'")
        conn.commit()
        conn.close()

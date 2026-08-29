"""
tests/test_vehicles_db.py — Tests for vehicle DB schema and seed data.
"""
import sys
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def _seeded_db(tmp_path):
    """Return a path to a freshly initialised and seeded test DB."""
    db = str(tmp_path / "test.db")
    with patch("core.database.DB_PATH", db):
        from core.database import init_db
        init_db()
        from scripts.seed_vehicles import seed as sv
        sv()
        from scripts.seed_platforms import seed as sp
        sp()
    return db


class TestVehiclesDB:

    def test_vehicle_categories_seeded(self, tmp_path):
        db = _seeded_db(tmp_path)
        with patch("core.database.DB_PATH", db):
            from core.database import get_connection
            conn = get_connection()
            n = conn.execute("SELECT COUNT(*) FROM vehicle_categories").fetchone()[0]
            conn.close()
        assert n == 6, f"Expected 6 categories, got {n}"

    def test_all_vehicles_have_required_fields(self, tmp_path):
        db = _seeded_db(tmp_path)
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM vehicles").fetchall()
        conn.close()
        required = [
            "name", "vehicle_class",
            "max_wind_kts", "max_gust_kts", "max_hs_m",
            "max_swell_ht_m", "max_swell_period_s",
        ]
        for row in rows:
            for col in required:
                assert row[col] is not None, \
                    f"Vehicle '{row['name']}' has NULL {col}"

    def test_operational_vehicles_count(self, tmp_path):
        db = _seeded_db(tmp_path)
        conn = sqlite3.connect(db)
        n = conn.execute(
            "SELECT COUNT(*) FROM vehicles WHERE status='operational'"
        ).fetchone()[0]
        conn.close()
        assert n >= 20, f"Expected ≥20 operational vehicles, got {n}"

    def test_class_defaults_applied_slv(self, tmp_path):
        """SLV vehicles with data_source='estimated' should have wind in [15, 22] kts."""
        db = _seeded_db(tmp_path)
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT v.name, v.max_wind_kts
              FROM vehicles v
              JOIN vehicle_categories c ON v.category_id = c.id
             WHERE c.name LIKE '%Small-lift%'
               AND v.data_source = 'estimated'
        """).fetchall()
        conn.close()
        assert len(rows) > 0, "No SLV estimated vehicles found"
        for row in rows:
            assert 15 <= row["max_wind_kts"] <= 22, \
                f"{row['name']} wind={row['max_wind_kts']} outside [15,22]"

    def test_firefly_alpha_present(self, tmp_path):
        db = _seeded_db(tmp_path)
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM vehicles WHERE name LIKE '%Firefly Alpha%' LIMIT 1"
        ).fetchone()
        conn.close()
        assert row is not None, "Firefly Alpha not found in vehicles table"
        assert row["leo_payload_kg"] == pytest.approx(1000.0), \
            f"Expected leo=1000, got {row['leo_payload_kg']}"

    def test_vessel_motion_factor_range(self, tmp_path):
        db = _seeded_db(tmp_path)
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT name, hull_motion_factor FROM platforms").fetchall()
        conn.close()
        assert len(rows) > 0, "No platforms found"
        for row in rows:
            hmf = row["hull_motion_factor"]
            assert 0.50 <= hmf <= 1.00, \
                f"{row['name']} hmf={hmf} outside [0.50, 1.00]"

    def test_gateway_variants_is_reference(self, tmp_path):
        db = _seeded_db(tmp_path)
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT name, is_reference FROM platforms WHERE name LIKE 'Gateway%'"
        ).fetchall()
        conn.close()
        assert len(rows) == 3, f"Expected 3 Gateway platforms, got {len(rows)}"
        for row in rows:
            assert row["is_reference"] == 1, \
                f"{row['name']} has is_reference={row['is_reference']}, expected 1"

"""
tests/test_migration_27a.py -- Tests for the Instruction Set 27A schema
additions: site_vehicles table, project_sites.preferred_vehicle_id, and
direction-parameter exclusion setting defaults.
"""
import sys
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def _fresh_db():
    """Return a temp DB path with init_db() already called."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)

    with patch("core.database.DB_PATH", db_path):
        from core.database import init_db
        init_db()

    return db_path


def test_site_vehicles_table_exists():
    db_path = _fresh_db()
    try:
        with patch("core.database.DB_PATH", db_path):
            from core.database import get_connection
            conn = get_connection()
            result = conn.execute("""
                SELECT COUNT(*) FROM sqlite_master
                WHERE type='table' AND name='site_vehicles'
            """).fetchone()[0]
            conn.close()
        assert result == 1
    finally:
        db_path.unlink(missing_ok=True)


def test_site_vehicles_composite_key():
    db_path = _fresh_db()
    try:
        with patch("core.database.DB_PATH", db_path):
            from core.database import get_connection
            conn = get_connection()
            conn.execute("""
                INSERT OR IGNORE INTO sites (name, lat, lon, bbox_nm)
                VALUES ('KeyTest', 32.6, -61.1, 25)
            """)
            site_id = conn.execute(
                "SELECT id FROM sites WHERE name='KeyTest'"
            ).fetchone()[0]
            conn.execute("""
                INSERT OR IGNORE INTO vehicles
                (name, vehicle_class, max_wind_kts, max_gust_kts, max_hs_m,
                 max_swell_ht_m, max_swell_period_s)
                VALUES ('TestV','slv_orb',18,25,1.5,2.0,12)
            """)
            vehicle_id = conn.execute(
                "SELECT id FROM vehicles WHERE name='TestV'"
            ).fetchone()[0]
            now = datetime.now(timezone.utc).isoformat()
            conn.execute("""
                INSERT INTO site_vehicles
                (site_id, vehicle_id, run_count, last_used)
                VALUES (?, ?, 1, ?)
            """, (site_id, vehicle_id, now))
            conn.commit()

            # Duplicate insert must fail on the composite primary key
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute("""
                    INSERT INTO site_vehicles
                    (site_id, vehicle_id, run_count, last_used)
                    VALUES (?, ?, 1, ?)
                """, (site_id, vehicle_id, now))
                conn.commit()

            conn.execute(
                "DELETE FROM site_vehicles WHERE site_id=?", (site_id,))
            conn.execute("DELETE FROM sites WHERE id=?", (site_id,))
            conn.execute("DELETE FROM vehicles WHERE id=?", (vehicle_id,))
            conn.commit()
            conn.close()
    finally:
        db_path.unlink(missing_ok=True)


def test_direction_settings_excluded():
    db_path = _fresh_db()
    try:
        with patch("core.database.DB_PATH", db_path):
            from core.settings import get_setting
            assert get_setting('exclude_wind_dir') == '1'
            assert get_setting('exclude_sea_dir') == '1'
            assert get_setting('exclude_swell_dir') == '1'
    finally:
        db_path.unlink(missing_ok=True)


def test_preferred_vehicle_id_column_exists():
    db_path = _fresh_db()
    try:
        with patch("core.database.DB_PATH", db_path):
            from core.database import get_connection
            conn = get_connection()
            cols = [row[1] for row in conn.execute(
                "PRAGMA table_info(project_sites)"
            ).fetchall()]
            conn.close()
        assert 'preferred_vehicle_id' in cols
    finally:
        db_path.unlink(missing_ok=True)

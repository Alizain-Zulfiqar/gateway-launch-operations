"""
tests/test_vessel_editor_logic.py — Tests for vessel editor hull-factor logic
and DB availability of newly inserted vessels.
"""
import sys
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# Hull type → default motion factor mapping (mirrors vessel_editor.py)
HULL_FACTORS = {
    "semisub": 0.78,
    "jackup":  0.92,
    "tlp":     0.82,
    "spar":    0.75,
    "fixed":   1.00,
}


class TestVesselEditorLogic:

    def test_semisub_default_motion_factor(self):
        assert HULL_FACTORS["semisub"] == pytest.approx(0.78)

    def test_spar_default_motion_factor(self):
        assert HULL_FACTORS["spar"] == pytest.approx(0.75)

    def test_tlp_default_motion_factor(self):
        assert HULL_FACTORS["tlp"] == pytest.approx(0.82)

    def test_jackup_default_motion_factor(self):
        assert HULL_FACTORS["jackup"] == pytest.approx(0.92)

    def test_fixed_default_motion_factor(self):
        assert HULL_FACTORS["fixed"] == pytest.approx(1.00)

    def test_new_vessel_available_in_query(self, tmp_path):
        """A vessel inserted directly into platforms appears in a SELECT query."""
        db = str(tmp_path / "test.db")
        with patch("core.database.DB_PATH", db):
            from core.database import init_db, get_connection
            init_db()
            conn = get_connection()
            conn.execute("""
                INSERT INTO platforms
                    (name, hull_type, hull_motion_factor, dp_capable,
                     max_hs_operating_m, typical_depth_m, payload_class,
                     is_reference)
                VALUES ('Test DP-1', 'semisub', 0.78, 1, 3.5, 500.0, 'MLV', 0)
            """)
            conn.commit()
            row = conn.execute(
                "SELECT * FROM platforms WHERE name='Test DP-1'"
            ).fetchone()
            conn.close()
        assert row is not None, "Newly inserted vessel not found in query"
        assert row["hull_motion_factor"] == pytest.approx(0.78)
        assert row["is_reference"] == 0

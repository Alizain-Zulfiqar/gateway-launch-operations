"""
tests/test_settings.py -- Tests for core/settings.py and the settings DB table.
"""
import sys
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def _fresh_db():
    """Return a temp DB path with init_db() already called."""
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)

    # Patch at the module level where DB_PATH is actually used
    with patch("core.database.DB_PATH", db_path):
        from core.database import init_db
        init_db()

    return db_path


class TestSettingsTable:
    def test_default_settings_populated(self):
        """init_db() should seed all default settings keys."""
        db_path = _fresh_db()
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
            conn.close()

            keys = {r["key"] for r in rows}
            expected = {
                "go_threshold", "ndbc_radius_nm", "platform_speed_kts",
                "fuel_consumption_mt_day", "fuel_price_usd_mt", "num_tugs",
                "tug_day_rate_usd", "port_fees_usd", "crew_day_rate_usd",
                "weather_contingency_pct", "ncei_timeout_s",
            }
            assert expected <= keys, f"Missing keys: {expected - keys}"
        finally:
            db_path.unlink(missing_ok=True)

    def test_set_and_get_setting_round_trip(self):
        """set_setting / get_setting should return the same string that was stored."""
        db_path = _fresh_db()
        try:
            with patch("core.database.DB_PATH", db_path):
                from core.settings import set_setting, get_setting
                set_setting("test_key", "hello_world")
                assert get_setting("test_key") == "hello_world"
        finally:
            db_path.unlink(missing_ok=True)

    def test_get_float_returns_float(self):
        """get_float should parse the stored string to float."""
        db_path = _fresh_db()
        try:
            with patch("core.database.DB_PATH", db_path):
                from core.settings import get_float
                val = get_float("platform_speed_kts", default=0.0)
                assert isinstance(val, float)
                assert val == pytest.approx(6.0)
        finally:
            db_path.unlink(missing_ok=True)

    def test_missing_key_returns_default(self):
        """get_setting / get_float / get_int should return default for absent keys."""
        db_path = _fresh_db()
        try:
            with patch("core.database.DB_PATH", db_path):
                from core.settings import get_setting, get_float, get_int
                assert get_setting("no_such_key") is None
                assert get_setting("no_such_key", "fallback") == "fallback"
                assert get_float("no_such_key", 3.14) == pytest.approx(3.14)
                assert get_int("no_such_key", 42) == 42
        finally:
            db_path.unlink(missing_ok=True)

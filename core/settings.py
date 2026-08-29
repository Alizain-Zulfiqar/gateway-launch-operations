"""
core/settings.py — Persistent application settings backed by the settings table.
"""
from __future__ import annotations

from core.database import get_connection


def get_setting(key: str, default: str | None = None) -> str | None:
    """Return a setting value as a string, or default if the key is absent."""
    conn = get_connection()
    row  = conn.execute(
        "SELECT value FROM settings WHERE key = ?", (key,)
    ).fetchone()
    conn.close()
    if row is None:
        return default
    return row["value"]


def set_setting(key: str, value: str) -> None:
    """Insert or replace a setting value."""
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, str(value)),
    )
    conn.commit()
    conn.close()


def get_float(key: str, default: float) -> float:
    """Return a setting as float, falling back to default on missing or bad value."""
    raw = get_setting(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except (ValueError, TypeError):
        return default


def get_int(key: str, default: int) -> int:
    """Return a setting as int, falling back to default on missing or bad value."""
    raw = get_setting(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


def get_session(key: str, default=None):
    """Return a session-state value as a string, or default if absent."""
    conn = get_connection()
    row  = conn.execute(
        "SELECT value FROM session_state WHERE key = ?", (key,)
    ).fetchone()
    conn.close()
    if row is None:
        return default
    return row["value"]


def set_session(key: str, value: str) -> None:
    """Insert or replace a session-state value."""
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO session_state (key, value) VALUES (?, ?)",
        (key, str(value)),
    )
    conn.commit()
    conn.close()

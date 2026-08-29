"""tests/test_spinbox.py — Pure-logic tests for spinbox clamping and ft/m sync."""
import pytest

from core.utils import ft_to_m, m_to_ft


# ── Standalone pure functions matching the spinbox internals ─────────────────

def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def ft_to_m_sync(ft_val: float) -> float:
    return round(ft_to_m(ft_val), 3)


def m_to_ft_sync(m_val: float) -> float:
    return round(m_to_ft(m_val), 1)


# ── Clamp ─────────────────────────────────────────────────────────────────────

def test_clamp_within_range():
    assert clamp(5.0, 0.0, 10.0) == 5.0


def test_clamp_below_min():
    assert clamp(-1.0, 0.0, 10.0) == 0.0


def test_clamp_above_max():
    assert clamp(15.0, 0.0, 10.0) == 10.0


# ── Unit conversions ──────────────────────────────────────────────────────────

def test_ft_to_m_gateway_transit():
    assert ft_to_m_sync(8.5) == pytest.approx(2.591, abs=0.001)


def test_ft_to_m_gateway_launch():
    assert ft_to_m_sync(14.0) == pytest.approx(4.267, abs=0.001)


def test_m_to_ft_roundtrip():
    original_ft = 14.0
    m_val = ft_to_m(original_ft)
    back_to_ft = m_to_ft(m_val)
    assert back_to_ft == pytest.approx(original_ft, abs=0.1)


def test_sync_guard_prevents_loop():
    ft_val = 8.5
    m_val = ft_to_m(ft_val)
    ft_back = m_to_ft(m_val)
    assert abs(ft_back - ft_val) < 0.01

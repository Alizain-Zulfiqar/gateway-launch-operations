"""tests/test_generate_coord_code.py — generate_coord_code() unit tests."""
from __future__ import annotations

import pytest

from core.utils import generate_coord_code


def test_north_west():
    assert generate_coord_code(32.5, -61.3) == "N32W061"


def test_south_east():
    assert generate_coord_code(-15.9, 40.7) == "S15E040"


def test_equator_prime_meridian():
    assert generate_coord_code(0.0, 0.0) == "N00E000"


def test_north_east():
    assert generate_coord_code(51.5, 0.1) == "N51E000"


def test_south_west():
    assert generate_coord_code(-33.87, -70.65) == "S33W070"


def test_lat_padding():
    assert generate_coord_code(5.0, -10.0) == "N05W010"


def test_lon_padding():
    assert generate_coord_code(28.5, -80.6) == "N28W080"


def test_high_lat():
    assert generate_coord_code(89.9, -179.9) == "N89W179"


def test_negative_lat_integer_truncation():
    """Truncation (not rounding): -15.99 → S15, not S16."""
    assert generate_coord_code(-15.99, 40.0) == "S15E040"


def test_invalid_lat_raises():
    with pytest.raises(ValueError):
        generate_coord_code(91.0, 0.0)


def test_invalid_lon_raises():
    with pytest.raises(ValueError):
        generate_coord_code(0.0, 181.0)

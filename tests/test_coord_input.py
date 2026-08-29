"""
tests/test_coord_input.py -- Tests for parse_coordinate() in ui/widgets/coord_input.py.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from ui.widgets.coord_input import parse_coordinate


class TestParseCoordinate:

    def test_decimal_degrees_positive(self):
        """Plain positive decimal degrees."""
        assert parse_coordinate("28.5", "lat") == pytest.approx(28.5)

    def test_decimal_degrees_negative(self):
        """Leading minus sign for west / south."""
        assert parse_coordinate("-80.6", "lon") == pytest.approx(-80.6)

    def test_ddm_north(self):
        """DDM with space separator and trailing hemisphere."""
        assert parse_coordinate("28 30.00 N", "lat") == pytest.approx(28.5)

    def test_ddm_south(self):
        """DDM south hemisphere produces negative value."""
        assert parse_coordinate("15 30.00 S", "lat") == pytest.approx(-15.5)

    def test_ddm_west(self):
        """DDM west hemisphere produces negative longitude."""
        assert parse_coordinate("80 36.00 W", "lon") == pytest.approx(-80.6)

    def test_ddm_east(self):
        """DDM east hemisphere produces positive longitude."""
        assert parse_coordinate("139 45.00 E", "lon") == pytest.approx(139.75)

    def test_ddm_degree_symbol(self):
        """DDM with unicode degree (°) and prime (′) symbols."""
        assert parse_coordinate("28°30.00′N", "lat") == pytest.approx(28.5)

    def test_dms_format(self):
        """DMS with three integer parts and trailing hemisphere."""
        assert parse_coordinate("28 30 00 N", "lat") == pytest.approx(28.5)

    def test_compact_nautical(self):
        """Compact nautical notation: first 2 digits are degrees, rest are minutes."""
        assert parse_coordinate("2830.00N", "lat") == pytest.approx(28.5)

    def test_invalid_returns_none(self):
        """Unrecognisable text returns None."""
        assert parse_coordinate("not a coordinate", "lat") is None

    def test_out_of_range_lat(self):
        """Latitude outside ±90 returns None."""
        assert parse_coordinate("95.0", "lat") is None

    def test_out_of_range_lon(self):
        """Longitude outside ±180 returns None."""
        assert parse_coordinate("185.0", "lon") is None

    def test_empty_string_returns_none(self):
        """Empty / whitespace-only input returns None."""
        assert parse_coordinate("", "lat") is None
        assert parse_coordinate("   ", "lon") is None

    def test_seven_candidate_sites(self):
        """Round-trip seven lat/lon pairs representative of real launch sites."""
        pairs = [
            (28.5,    -80.6,   "lat", "lon"),   # KSC
            (34.442,  -120.56, "lat", "lon"),   # Vandenberg
            (5.239,   -52.769, "lat", "lon"),   # Kourou
            (-22.9,   -43.2,   "lat", "lon"),   # Alcântara-like
            (63.964,  12.504,  "lat", "lon"),   # Andøya
            (45.918,  63.342,  "lat", "lon"),   # Baikonur
            (-7.987,  -14.332, "lat", "lon"),   # Ascension
        ]
        for lat, lon, lt, ln in pairs:
            lat_str = f"{lat}"
            lon_str = f"{lon}"
            got_lat = parse_coordinate(lat_str, lt)
            got_lon = parse_coordinate(lon_str, ln)
            assert got_lat == pytest.approx(lat, abs=1e-4), \
                f"lat parse failed for {lat_str}"
            assert got_lon == pytest.approx(lon, abs=1e-4), \
                f"lon parse failed for {lon_str}"

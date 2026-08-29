"""
tests/test_voyage_pdf.py -- Tests for modules/m5_reports/voyage_pdf.py.
"""
import sys
import tempfile
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_site():
    from core.models import Site
    return Site(lat=28.5, lon=-80.6, name="Cape Canaveral Test Site")


def _make_port():
    from core.models import Port
    return Port(
        port_name="Port Canaveral",
        lat=28.4,
        lon=-80.6,
        country="United States",
        wpi_number="56370",
        harbor_size="L",
        depth_anch_m=12.0,
        fuel_oil=True,
        diesel=True,
        id=1,
        distance_nm=6.5,
        bearing_deg=180.0,
    )


def _make_cost(site, port):
    """A three-leg Mob -> Load -> Site -> Discharge route with fees on the mob port."""
    from core.models import VoyageLeg, PortFees
    from modules.m4_ports.voyage import (
        compute_voyage_cost, default_vessels, default_port_fees,
    )

    speed = 9.0
    spec = [
        ("mob", "Pensacola", "load", "Port Canaveral", 420.0, 2.0),
        ("load", "Port Canaveral", "launch_site", site.name, 6.5, 2.0),
        ("launch_site", site.name, "discharge", "Port Canaveral", 6.5, 4.0),
    ]
    legs = [
        VoyageLeg(index=i, from_role=fr, from_name=fn, from_lat=0.0, from_lon=0.0,
                  to_role=tr, to_name=tn, to_lat=0.0, to_lon=0.0,
                  distance_nm=dist, transit_days=round(dist / (speed * 24.0), 6),
                  onsite_days=onsite)
        for i, (fr, fn, tr, tn, dist, onsite) in enumerate(spec, 1)
    ]
    vessels = default_vessels()
    for v in vessels:
        if v.key == "sv1":
            v.deployed = True
    return compute_voyage_cost(
        site, port, legs, vessels=vessels, port_fees=default_port_fees(),
        speed_kts=speed, launches=2,
    )


def _make_waypoints(site, port):
    from core.models import Waypoint
    return [
        Waypoint(
            leg=1,
            description="Departure",
            lat=site.lat, lon=site.lon,
            elapsed_hours=0.0, elapsed_days=0.0, cumulative_nm=0.0,
        ),
        Waypoint(
            leg=2,
            description="Arrival — Port Canaveral",
            lat=port.lat, lon=port.lon,
            elapsed_hours=1.1, elapsed_days=0.05, cumulative_nm=6.5,
        ),
    ]


class TestGenerateVoyageReport:
    def test_generate_voyage_report_creates_file(self, tmp_path):
        """generate_voyage_report should create a non-empty PDF at the given path."""
        from core.models import VoyageSchedule
        from modules.m5_reports.voyage_pdf import generate_voyage_report

        site      = _make_site()
        port      = _make_port()
        cost      = _make_cost(site, port)
        waypoints = _make_waypoints(site, port)

        schedule = VoyageSchedule(
            site=site,
            port=port,
            cost=cost,
            waypoints=waypoints,
            departure_date=date(2026, 7, 1),
            notes="Test schedule",
        )

        out_path = str(tmp_path / "voyage_test.pdf")
        result   = generate_voyage_report(
            schedule        = schedule,
            all_port_costs  = [cost],
            analysis_result = None,
            output_path     = out_path,
        )

        assert Path(result).exists(), "PDF file was not created"
        assert Path(result).stat().st_size > 1_000, "PDF file is suspiciously small"

    def test_generate_voyage_report_returns_abs_path(self, tmp_path):
        """Return value should be an absolute path string."""
        from core.models import VoyageSchedule
        from modules.m5_reports.voyage_pdf import generate_voyage_report

        site      = _make_site()
        port      = _make_port()
        cost      = _make_cost(site, port)
        waypoints = _make_waypoints(site, port)

        schedule = VoyageSchedule(
            site=site, port=port, cost=cost, waypoints=waypoints,
        )
        out_path = str(tmp_path / "subdir" / "voyage.pdf")
        result   = generate_voyage_report(
            schedule=schedule,
            all_port_costs=[cost],
            analysis_result=None,
            output_path=out_path,
        )
        assert Path(result).is_absolute()

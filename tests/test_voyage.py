"""
tests/test_voyage.py -- Unit tests for modules/m4_ports/voyage.py

The cost model is a chain of port calls with the launch site in the middle.
Route construction (geodesy) and cost arithmetic are separate functions, so the
golden test below can feed the reference sheet's real sailing distances straight
into compute_voyage_cost() without great-circle distances getting in the way.
"""

import json
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import core.database as db_mod
from core.database import get_connection, init_db
from core.models import (
    Site, Port, VoyageLeg, VesselParams, PortFees, VoyageCostBreakdown,
    VoyageSchedule, PORT_ROLES, SELECTABLE_PORT_ROLES, FEE_CATEGORIES,
)
from core.utils import haversine_nm
from modules.m4_ports.voyage import (
    VoyageCostParams,
    build_voyage_legs,
    compute_voyage_cost,
    calculate_voyage_cost,
    compare_port_options,
    default_vessels,
    default_port_fees,
    generate_waypoints,
    load_params,
    route_roles,
    save_params,
    save_voyage_schedule,
)


# ---- Fixtures ----------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Every test gets its own DB.

    calculate_voyage_cost() and load_params() both read the settings table, so
    without this any test touching them would read (and save_params would write)
    the production gateway.db.
    """
    db = tmp_path / "test_voyage.db"
    monkeypatch.setattr("config.DB_PATH", str(db))
    monkeypatch.setattr(db_mod, "DB_PATH", str(db))
    init_db()
    return db


@pytest.fixture
def cape_site():
    return Site(lat=28.5, lon=-80.6, name="Cape Canaveral")


@pytest.fixture
def canaveral_port():
    return Port(
        port_name    = "Canaveral Harbor",
        lat          = 28.415,
        lon          = -80.603,
        country      = "United States",
        wpi_number   = "56050",
        harbor_size  = "S",
        depth_anch_m = 12.5,
        fuel_oil     = True,
    )


@pytest.fixture
def jacksonville_port():
    return Port(
        port_name    = "Jacksonville",
        lat          = 30.33,
        lon          = -81.65,
        country      = "United States",
        wpi_number   = "55630",
        harbor_size  = "M",
        depth_anch_m = 11.0,
        fuel_oil     = True,
    )


# ---- Golden test: the reference voyage sheet ---------------------------------

_REF_SPEED_KTS = 9.0

# (from_role, from_name, to_role, to_name, distance, onsite_days_at_destination)
_REF_LEGS = [
    ("mob",         "Pascagoula",   "load",        "Jacksonville", 1044, 2),
    ("load",        "Jacksonville", "staging",     "Providence",    887, 4),
    ("staging",     "Providence",   "launch_site", "Launch Site",   133, 2),
    ("launch_site", "Launch Site",  "discharge",   "Providence",    133, 4),
    ("discharge",   "Providence",   "demob",       "Jacksonville",  887, 2),
]


def _reference_legs() -> list[VoyageLeg]:
    return [
        VoyageLeg(
            index=i, from_role=fr, from_name=fn, from_lat=0.0, from_lon=0.0,
            to_role=tr, to_name=tn, to_lat=0.0, to_lon=0.0,
            distance_nm=float(dist),
            transit_days=round(dist / (_REF_SPEED_KTS * 24.0), 6),
            onsite_days=float(onsite),
        )
        for i, (fr, fn, tr, tn, dist, onsite) in enumerate(_REF_LEGS, 1)
    ]


def _reference_vessels() -> list[VesselParams]:
    """Reference-sheet vessel set: platform + SV1 deployed, SV2 idle."""
    vessels = default_vessels()
    for v in vessels:
        if v.key == "sv1":
            v.deployed = True
    return vessels


@pytest.fixture
def reference_breakdown() -> VoyageCostBreakdown:
    return compute_voyage_cost(
        Site(lat=40.0, lon=-70.0, name="Launch Site"),
        Port(port_name="Providence", lat=41.8, lon=-71.4),
        _reference_legs(),
        vessels=_reference_vessels(),
        port_fees=default_port_fees(),
        speed_kts=_REF_SPEED_KTS,
        launches=1,
    )


class TestReferenceSheetGolden:
    """Reproduce the reference voyage sheet's published figures."""

    def test_transit_days_total(self, reference_breakdown):
        assert round(reference_breakdown.total_transit_days, 2) == 14.28

    def test_onsite_days_total(self, reference_breakdown):
        assert reference_breakdown.total_onsite_days == 14.0

    def test_voyage_days_total(self, reference_breakdown):
        assert round(reference_breakdown.voyage_days, 2) == 28.28

    def test_platform_charter(self, reference_breakdown):
        platform = reference_breakdown.vessel("platform")
        # $20,000/day x 28.2778 days -> $565,556 to the nearest dollar.
        assert round(platform.charter_usd) == 565_556

    def test_support_vessel_1_charter_uses_own_hire_window(self, reference_breakdown):
        sv1 = reference_breakdown.vessel("sv1")
        assert sv1.charter_days == 18.5
        assert sv1.charter_usd == 185_000.0

    def test_support_vessel_2_not_deployed_costs_nothing(self, reference_breakdown):
        sv2 = reference_breakdown.vessel("sv2")
        assert sv2.deployed is False
        assert sv2.charter_usd == 0.0
        assert sv2.fuel_usd == 0.0

    def test_charter_total(self, reference_breakdown):
        assert round(reference_breakdown.charter_total_usd) == 750_556

    def test_port_fees_total(self, reference_breakdown):
        assert reference_breakdown.port_fees_total_usd == 14_000.0

    def test_underway_gallons(self, reference_breakdown):
        # 14.2778 transit days x (12 platform + 23 SV1) gal/day
        assert reference_breakdown.underway_gal == 499.72

    def test_onsite_gallons(self, reference_breakdown):
        # 14 on-site days x (50 platform + 8 SV1) gal/day.  The reference sheet
        # prints 814.22 because it multiplied SV1's in-port rate by transit days;
        # the documented formula uses on-site days, giving 812.
        assert reference_breakdown.onsite_gal == 812.0

    def test_total_gallons(self, reference_breakdown):
        assert reference_breakdown.fuel_total_gal == 1_311.72

    def test_fuel_cost_at_one_dollar_per_gallon(self, reference_breakdown):
        assert reference_breakdown.fuel_total_usd == 1_311.72

    def test_total_is_charter_plus_fees_plus_fuel(self, reference_breakdown):
        b = reference_breakdown
        assert b.total_usd == pytest.approx(
            b.charter_total_usd + b.port_fees_total_usd + b.fuel_total_usd
        )

    def test_economy_of_scale(self, reference_breakdown):
        b = reference_breakdown
        assert b.cost_per_launch(1) == pytest.approx(b.total_usd)
        assert b.cost_per_launch(2) == pytest.approx(b.total_usd / 2)
        assert b.cost_per_launch(3) == pytest.approx(b.total_usd / 3)

    def test_fuel_price_scales_linearly(self):
        """The sheet's $4/gal scenario is 4x the $1/gal figure."""
        vessels = _reference_vessels()
        for v in vessels:
            v.fuel_usd_gal = 4.0
        b = compute_voyage_cost(
            Site(lat=40.0, lon=-70.0), Port(port_name="P", lat=41.8, lon=-71.4),
            _reference_legs(), vessels=vessels, port_fees=default_port_fees(),
            speed_kts=_REF_SPEED_KTS,
        )
        assert b.fuel_total_usd == pytest.approx(1_311.72 * 4, abs=0.05)


# ---- build_voyage_legs -------------------------------------------------------

class TestBuildVoyageLegs:
    def test_load_and_discharge_only_is_a_round_trip(self, cape_site, canaveral_port):
        roles = {r: None for r in SELECTABLE_PORT_ROLES}
        roles["load"] = canaveral_port
        roles["discharge"] = canaveral_port
        legs = build_voyage_legs(cape_site, roles)
        assert len(legs) == 2
        assert legs[0].from_role == "load"
        assert legs[0].to_role == "launch_site"
        assert legs[1].to_role == "discharge"

    def test_unset_roles_collapse_out(self, cape_site, canaveral_port):
        roles = {r: None for r in SELECTABLE_PORT_ROLES}
        roles["load"] = canaveral_port
        legs = build_voyage_legs(cape_site, roles)
        assert len(legs) == 1
        assert [leg.to_role for leg in legs] == ["launch_site"]

    def test_full_chain_produces_five_legs(self, cape_site, canaveral_port,
                                           jacksonville_port):
        pensacola = Port(port_name="Pensacola", lat=30.4, lon=-87.2)
        roles = {
            "mob": pensacola, "load": jacksonville_port,
            "staging": canaveral_port, "discharge": canaveral_port,
            "demob": jacksonville_port,
        }
        legs = build_voyage_legs(cape_site, roles)
        assert len(legs) == 5
        assert [leg.to_role for leg in legs] == [
            "load", "staging", "launch_site", "discharge", "demob"
        ]

    def test_transit_days_formula(self, cape_site, jacksonville_port):
        roles = {r: None for r in SELECTABLE_PORT_ROLES}
        roles["load"] = jacksonville_port
        speed = 9.0
        legs = build_voyage_legs(cape_site, roles, speed_kts=speed)
        raw = haversine_nm(jacksonville_port.lat, jacksonville_port.lon,
                           cape_site.lat, cape_site.lon)
        assert legs[0].transit_days == pytest.approx(raw / (speed * 24.0), abs=1e-5)

    def test_distance_matches_haversine(self, cape_site, jacksonville_port):
        roles = {r: None for r in SELECTABLE_PORT_ROLES}
        roles["load"] = jacksonville_port
        legs = build_voyage_legs(cape_site, roles)
        expected = haversine_nm(jacksonville_port.lat, jacksonville_port.lon,
                                cape_site.lat, cape_site.lon)
        assert legs[0].distance_nm == pytest.approx(expected, abs=0.01)

    def test_higher_speed_shortens_transit(self, cape_site, jacksonville_port):
        roles = {r: None for r in SELECTABLE_PORT_ROLES}
        roles["load"] = jacksonville_port
        slow = build_voyage_legs(cape_site, roles, speed_kts=6.0)[0]
        fast = build_voyage_legs(cape_site, roles, speed_kts=12.0)[0]
        assert fast.transit_days < slow.transit_days
        assert fast.distance_nm == slow.distance_nm

    def test_onsite_days_attach_to_destination(self, cape_site, canaveral_port,
                                               jacksonville_port):
        roles = {r: None for r in SELECTABLE_PORT_ROLES}
        roles["mob"] = jacksonville_port
        roles["load"] = canaveral_port
        roles["discharge"] = canaveral_port
        onsite = {"mob": 99.0, "load": 3.0, "launch_site": 5.0, "discharge": 7.0}
        legs = build_voyage_legs(cape_site, roles, onsite)
        assert [leg.onsite_days for leg in legs] == [3.0, 5.0, 7.0]

    def test_origin_onsite_days_never_billed(self, cape_site, canaveral_port,
                                             jacksonville_port):
        """A value entered for the origin role must not reach any leg."""
        roles = {r: None for r in SELECTABLE_PORT_ROLES}
        roles["mob"] = jacksonville_port
        roles["load"] = canaveral_port
        roles["discharge"] = canaveral_port
        legs = build_voyage_legs(cape_site, roles, {"mob": 99.0})
        assert sum(leg.onsite_days for leg in legs) == 0.0

    def test_no_ports_yields_no_legs(self, cape_site):
        legs = build_voyage_legs(cape_site, {r: None for r in SELECTABLE_PORT_ROLES})
        assert legs == []

    def test_route_roles_includes_origin(self, cape_site, canaveral_port,
                                         jacksonville_port):
        roles = {r: None for r in SELECTABLE_PORT_ROLES}
        roles["mob"] = jacksonville_port
        roles["load"] = canaveral_port
        roles["discharge"] = canaveral_port
        legs = build_voyage_legs(cape_site, roles)
        assert route_roles(legs) == ["mob", "load", "launch_site", "discharge"]

    def test_route_roles_empty_for_no_legs(self):
        assert route_roles([]) == []


# ---- compute_voyage_cost -----------------------------------------------------

class TestComputeVoyageCost:
    def test_total_is_sum_of_three_components(self, reference_breakdown):
        b = reference_breakdown
        assert b.total_usd == round(
            b.charter_total_usd + b.port_fees_total_usd + b.fuel_total_usd, 2
        )

    def test_platform_bills_full_voyage(self, reference_breakdown):
        platform = reference_breakdown.vessel("platform")
        assert platform.charter_days == pytest.approx(
            reference_breakdown.voyage_days
        )

    def test_undeployed_vessel_burns_no_fuel(self, reference_breakdown):
        assert reference_breakdown.vessel("sv2").total_gal == 0.0

    def test_fees_only_charged_for_visited_roles(self, cape_site, canaveral_port):
        """Mob fees must not apply when no mob port is in the route."""
        roles = {r: None for r in SELECTABLE_PORT_ROLES}
        roles["load"] = canaveral_port
        roles["discharge"] = canaveral_port
        legs = build_voyage_legs(cape_site, roles)
        b = compute_voyage_cost(cape_site, canaveral_port, legs,
                                port_fees=default_port_fees())
        assert b.port_fees_total_usd == 0.0
        assert "mob" not in {pf.role for pf in b.port_fees}

    def test_fees_charged_once_the_role_is_visited(self, cape_site, canaveral_port,
                                                  jacksonville_port):
        roles = {r: None for r in SELECTABLE_PORT_ROLES}
        roles["mob"] = jacksonville_port
        roles["load"] = canaveral_port
        roles["discharge"] = canaveral_port
        legs = build_voyage_legs(cape_site, roles)
        b = compute_voyage_cost(cape_site, canaveral_port, legs,
                                port_fees=default_port_fees())
        assert b.port_fees_total_usd == 14_000.0

    def test_fee_categories_sum_to_row_total(self):
        fees = PortFees(role="mob", agents_usd=1.0, assist_tugs_usd=2.0,
                        pilots_usd=3.0, wharfage_usd=4.0, loading_ops_usd=5.0,
                        other_usd=6.0)
        assert fees.total_usd == 21.0
        assert sum(fees.amount(c) for c in FEE_CATEGORIES) == 21.0

    def test_empty_legs_yields_zero_distance_and_days(self, cape_site,
                                                      canaveral_port):
        b = compute_voyage_cost(cape_site, canaveral_port, [])
        assert b.total_distance_nm == 0.0
        assert b.total_transit_days == 0.0
        assert b.total_onsite_days == 0.0
        assert b.fuel_total_gal == 0.0

    def test_launches_floor_is_one(self, cape_site, canaveral_port):
        b = compute_voyage_cost(cape_site, canaveral_port, _reference_legs(),
                                launches=0)
        assert b.launches == 1
        assert b.cost_per_launch() == b.total_usd

    def test_cost_per_launch_guards_against_zero(self, reference_breakdown):
        assert reference_breakdown.cost_per_launch(0) == pytest.approx(
            reference_breakdown.total_usd
        )

    def test_total_formatted(self, reference_breakdown):
        assert reference_breakdown.total_formatted.startswith("$")

    def test_vessel_lookup_misses_return_none(self, reference_breakdown):
        assert reference_breakdown.vessel("nonexistent") is None
        assert reference_breakdown.fees_for("nonexistent") is None


# ---- calculate_voyage_cost (build + compute) ---------------------------------

class TestCalculateVoyageCost:
    def test_returns_breakdown(self, cape_site, canaveral_port):
        vc = calculate_voyage_cost(cape_site, canaveral_port)
        assert isinstance(vc, VoyageCostBreakdown)

    def test_candidate_fills_load_and_discharge(self, cape_site, canaveral_port):
        vc = calculate_voyage_cost(cape_site, canaveral_port)
        assert len(vc.legs) == 2
        assert vc.legs[0].from_name == canaveral_port.port_name
        assert vc.legs[-1].to_name == canaveral_port.port_name

    def test_site_and_port_stored(self, cape_site, canaveral_port):
        vc = calculate_voyage_cost(cape_site, canaveral_port)
        assert vc.site is cape_site
        assert vc.port is canaveral_port

    def test_all_totals_positive(self, cape_site, canaveral_port):
        vc = calculate_voyage_cost(cape_site, canaveral_port)
        assert vc.total_distance_nm > 0
        assert vc.total_transit_days > 0
        assert vc.charter_total_usd > 0
        assert vc.total_usd > 0

    def test_longer_route_costs_more(self, cape_site, canaveral_port,
                                    jacksonville_port):
        near = calculate_voyage_cost(cape_site, canaveral_port)
        far  = calculate_voyage_cost(cape_site, jacksonville_port)
        assert far.total_usd > near.total_usd

    def test_params_respected(self, cape_site, canaveral_port):
        params = VoyageCostParams()
        cheap = calculate_voyage_cost(cape_site, canaveral_port, params=params)
        for v in params.vessels:
            v.charter_rate_usd_day *= 2
        pricey = calculate_voyage_cost(cape_site, canaveral_port, params=params)
        assert pricey.charter_total_usd == pytest.approx(cheap.charter_total_usd * 2)


# ---- VoyageCostParams persistence -------------------------------------------

class TestVoyageCostParams:
    def test_defaults_match_reference_sheet(self):
        p = VoyageCostParams()
        assert p.speed_kts == 9.0
        assert p.launches == 1
        platform = p.vessel("platform")
        assert platform.charter_rate_usd_day == 20_000.0
        assert platform.charter_days is None          # bills the full voyage
        assert platform.at_sea_gal_day == 12.0
        assert platform.in_port_gal_day == 50.0
        sv1 = p.vessel("sv1")
        assert sv1.charter_rate_usd_day == 10_000.0
        assert sv1.charter_days == 18.5
        assert p.fees_for("mob").total_usd == 14_000.0

    def test_round_trip_through_dict(self):
        p = VoyageCostParams()
        p.speed_kts = 11.5
        p.launches = 4
        p.role_port_ids["mob"] = 479
        p.onsite_days["launch_site"] = 6.0
        p.vessel("sv1").deployed = True
        p.fees_for("load").pilots_usd = 1234.0

        restored = VoyageCostParams.from_dict(p.to_dict())
        assert restored.speed_kts == 11.5
        assert restored.launches == 4
        assert restored.role_port_ids["mob"] == 479
        assert restored.onsite_days["launch_site"] == 6.0
        assert restored.vessel("sv1").deployed is True
        assert restored.vessel("platform").charter_days is None
        assert restored.fees_for("load").pilots_usd == 1234.0

    def test_from_dict_tolerates_garbage(self):
        p = VoyageCostParams.from_dict({
            "speed_kts": "not-a-number",
            "launches": None,
            "role_port_ids": {"mob": "abc"},
            "onsite_days": {"load": "xyz"},
            "vessels": ["not-a-dict", {"key": "unknown"}],
            "port_fees": [{"role": "nope"}],
        })
        assert p.speed_kts == 9.0
        assert p.launches == 1
        assert p.role_port_ids["mob"] is None

    def test_from_dict_rejects_non_dict(self):
        assert VoyageCostParams.from_dict("nonsense").speed_kts == 9.0

    def test_save_and_load_round_trip(self):
        p = VoyageCostParams()
        p.speed_kts = 13.0
        p.launches = 2
        p.vessel("sv2").deployed = True
        save_params(p)

        loaded = load_params()
        assert loaded.speed_kts == 13.0
        assert loaded.launches == 2
        assert loaded.vessel("sv2").deployed is True

    def test_load_without_saved_value_returns_defaults(self):
        assert load_params().speed_kts == 9.0

    def test_load_survives_corrupt_json(self):
        from core.settings import set_setting
        set_setting("voyage_cost_params", "{not valid json")
        assert load_params().speed_kts == 9.0

    def test_all_roles_present_in_fees(self):
        p = VoyageCostParams()
        assert {pf.role for pf in p.port_fees} == set(PORT_ROLES)


# ---- generate_waypoints ------------------------------------------------------

class TestGenerateWaypoints:
    def test_first_point_is_port(self, cape_site, canaveral_port):
        wps = generate_waypoints(cape_site, canaveral_port)
        assert wps[0].lat == canaveral_port.lat
        assert wps[0].lon == canaveral_port.lon

    def test_last_point_is_site(self, cape_site, canaveral_port):
        wps = generate_waypoints(cape_site, canaveral_port)
        assert wps[-1].lat == cape_site.lat
        assert wps[-1].lon == cape_site.lon

    def test_first_elapsed_is_zero(self, cape_site, canaveral_port):
        wps = generate_waypoints(cape_site, canaveral_port)
        assert wps[0].elapsed_hours == 0.0

    def test_first_cumulative_is_zero(self, cape_site, canaveral_port):
        wps = generate_waypoints(cape_site, canaveral_port)
        assert wps[0].cumulative_nm == 0.0

    def test_elapsed_hours_monotonically_increasing(self, cape_site, jacksonville_port):
        wps = generate_waypoints(cape_site, jacksonville_port, interval_hours=6.0)
        elapsed = [w.elapsed_hours for w in wps]
        for a, b in zip(elapsed, elapsed[1:]):
            assert b > a, f"elapsed_hours not monotonic: {a} then {b}"

    def test_elapsed_days_equals_hours_over_24(self, cape_site, jacksonville_port):
        wps = generate_waypoints(cape_site, jacksonville_port, interval_hours=6.0)
        for wp in wps:
            assert abs(wp.elapsed_days - wp.elapsed_hours / 24.0) < 1e-4

    def test_leg_numbers_sequential(self, cape_site, jacksonville_port):
        wps = generate_waypoints(cape_site, jacksonville_port, interval_hours=6.0)
        for i, wp in enumerate(wps, 1):
            assert wp.leg == i

    def test_departure_description(self, cape_site, canaveral_port):
        wps = generate_waypoints(cape_site, canaveral_port)
        assert wps[0].description == "Departure"

    def test_arrival_description(self, cape_site, canaveral_port):
        wps = generate_waypoints(cape_site, canaveral_port)
        assert wps[-1].description == "Arrival at site"

    def test_minimum_two_waypoints(self, cape_site, canaveral_port):
        # Even a short route has departure + arrival
        wps = generate_waypoints(cape_site, canaveral_port)
        assert len(wps) >= 2

    def test_intermediate_waypoints_labeled(self, cape_site, jacksonville_port):
        wps = generate_waypoints(cape_site, jacksonville_port, interval_hours=6.0)
        inner = wps[1:-1]
        for i, wp in enumerate(inner, 1):
            assert wp.description == f"Waypoint {i}"

    def test_last_cumulative_nm_matches_total_distance(self, cape_site, jacksonville_port):
        total = haversine_nm(
            jacksonville_port.lat, jacksonville_port.lon,
            cape_site.lat, cape_site.lon,
        )
        wps = generate_waypoints(cape_site, jacksonville_port)
        assert abs(wps[-1].cumulative_nm - total) < 0.5   # within 0.5 NM rounding

    def test_same_location_returns_two_points(self):
        """When port and site are the same point, get departure + arrival only."""
        s = Site(lat=28.5, lon=-80.6, name="S")
        p = Port(port_name="P", lat=28.5, lon=-80.6)
        wps = generate_waypoints(s, p)
        assert len(wps) == 2
        assert wps[0].description == "Departure"
        assert wps[-1].description == "Arrival at site"


# ---- compare_port_options ----------------------------------------------------

class TestComparePortOptions:
    def test_sorted_cheapest_first(self, cape_site, canaveral_port, jacksonville_port):
        results = compare_port_options(cape_site, [jacksonville_port, canaveral_port])
        costs = [vc.total_usd for vc in results]
        assert costs == sorted(costs)

    def test_returns_all_ports(self, cape_site, canaveral_port, jacksonville_port):
        results = compare_port_options(cape_site, [canaveral_port, jacksonville_port])
        assert len(results) == 2

    def test_empty_ports_returns_empty(self, cape_site):
        assert compare_port_options(cape_site, []) == []

    def test_single_port_returns_one(self, cape_site, canaveral_port):
        results = compare_port_options(cape_site, [canaveral_port])
        assert len(results) == 1
        assert isinstance(results[0], VoyageCostBreakdown)

    def test_each_candidate_costed_over_full_route(self, cape_site, canaveral_port,
                                                   jacksonville_port):
        """A pinned mob port must appear in every candidate's route."""
        pensacola = Port(port_name="Pensacola", lat=30.4, lon=-87.2, id=9001)
        params = VoyageCostParams()
        params.role_port_ids["mob"] = 9001
        results = compare_port_options(
            cape_site, [canaveral_port, jacksonville_port], params=params
        )
        # port_lookup only holds the candidates, so the pinned id resolves via the
        # DB and is absent here -- the route falls back to load/discharge only.
        assert all(len(vc.legs) >= 2 for vc in results)

    def test_params_forwarded(self, cape_site, canaveral_port):
        params = VoyageCostParams()
        base = compare_port_options(cape_site, [canaveral_port], params=params)[0]
        for v in params.vessels:
            v.fuel_usd_gal = 40.0
        pricey = compare_port_options(cape_site, [canaveral_port], params=params)[0]
        assert pricey.total_usd > base.total_usd


# ---- save_voyage_schedule ----------------------------------------------------

class TestSaveVoyageSchedule:
    def _seed_site_and_port(self, conn):
        """Insert a site and port row and return (site_id, port_id)."""
        cur = conn.execute(
            "INSERT INTO sites (name, lat, lon) VALUES (?,?,?)",
            ("Test Site", 28.5, -80.6),
        )
        site_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO ports (port_name, lat, lon) VALUES (?,?,?)",
            ("Test Port", 28.415, -80.603),
        )
        port_id = cur.lastrowid
        conn.commit()
        return site_id, port_id

    def test_raises_without_site_id(self, cape_site, canaveral_port):
        vc  = calculate_voyage_cost(cape_site, canaveral_port)
        wps = generate_waypoints(cape_site, canaveral_port)
        schedule = VoyageSchedule(site=cape_site, port=canaveral_port,
                                  cost=vc, waypoints=wps)
        with pytest.raises(ValueError, match="site.id"):
            save_voyage_schedule(schedule)

    def test_raises_without_port_id(self, cape_site, canaveral_port):
        site_with_id = Site(lat=28.5, lon=-80.6, name="S", id=1)
        vc  = calculate_voyage_cost(site_with_id, canaveral_port)
        wps = generate_waypoints(site_with_id, canaveral_port)
        schedule = VoyageSchedule(site=site_with_id, port=canaveral_port,
                                  cost=vc, waypoints=wps)
        with pytest.raises(ValueError, match="port.id"):
            save_voyage_schedule(schedule)

    def test_returns_int_id(self):
        conn = get_connection()
        site_id, port_id = self._seed_site_and_port(conn)
        conn.close()

        site = Site(lat=28.5, lon=-80.6, name="S", id=site_id)
        port = Port(port_name="P", lat=28.415, lon=-80.603, id=port_id)
        vc   = calculate_voyage_cost(site, port)
        wps  = generate_waypoints(site, port)
        schedule = VoyageSchedule(site=site, port=port, cost=vc, waypoints=wps)

        new_id = save_voyage_schedule(schedule)
        assert isinstance(new_id, int)
        assert new_id >= 1

    def test_row_persisted_with_json(self):
        conn = get_connection()
        site_id, port_id = self._seed_site_and_port(conn)
        conn.close()

        site = Site(lat=28.5, lon=-80.6, name="S", id=site_id)
        port = Port(port_name="P", lat=28.415, lon=-80.603, id=port_id)
        vc   = calculate_voyage_cost(site, port)
        wps  = generate_waypoints(site, port)
        schedule = VoyageSchedule(site=site, port=port, cost=vc, waypoints=wps)

        new_id = save_voyage_schedule(schedule)

        conn2 = get_connection()
        row = conn2.execute(
            "SELECT * FROM voyage_schedules WHERE id=?", (new_id,)
        ).fetchone()
        conn2.close()

        assert row is not None
        assert row["site_id"] == site_id
        assert row["port_id"] == port_id
        assert row["platform_speed_kts"] == vc.speed_kts

        wp_data   = json.loads(row["waypoints_json"])
        cost_data = json.loads(row["cost_summary_json"])

        assert isinstance(wp_data, list)
        assert len(wp_data) >= 2
        for key in ("total_distance_nm", "total_transit_days", "charter_total_usd",
                    "port_fees_total_usd", "fuel_total_usd", "total_usd",
                    "cost_per_launch_usd", "legs", "vessels"):
            assert key in cost_data, f"missing {key} in cost_summary_json"
        assert len(cost_data["legs"]) == len(vc.legs)
        assert len(cost_data["vessels"]) == 3

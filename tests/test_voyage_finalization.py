"""
tests/test_voyage_finalization.py — voyage finalization + actuals persistence.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import core.database as db_mod
from core.database import get_connection, init_db
from core.models import Site, Port, VoyageLeg
from modules.m4_ports.voyage import (
    load_params,
    compute_voyage_cost,
    default_port_fees,
    default_vessels,
)
from modules.m4_ports.finalization import (
    FinalizationError,
    finalize_voyage,
    list_finalizations,
    save_actuals,
    clear_actuals,
    compare_estimate_actual,
    copy_estimate_for_actuals,
    recompute_breakdown_totals,
)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db = tmp_path / "test_voyage_finalization.db"
    monkeypatch.setattr("config.DB_PATH", str(db))
    monkeypatch.setattr(db_mod, "DB_PATH", str(db))
    init_db()
    return db


def _insert_project(name: str = "Test Project") -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO projects (name, status) VALUES (?, 'planning')",
        (name,),
    )
    conn.commit()
    pid = cur.lastrowid
    conn.close()
    return pid


def _insert_site(name: str = "Launch Site", lat: float = 40.0, lon: float = -70.0) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO sites (name, lat, lon) VALUES (?, ?, ?)",
        (name, lat, lon),
    )
    conn.commit()
    sid = cur.lastrowid
    conn.close()
    return sid


def _insert_port(name: str = "Providence", lat: float = 41.8, lon: float = -71.4) -> int:
    conn = get_connection()
    cur = conn.execute(
        """
        INSERT INTO ports (port_name, lat, lon, country, fuel_oil, depth_anch_m)
        VALUES (?, ?, ?, 'United States', 1, 12.0)
        """,
        (name, lat, lon),
    )
    conn.commit()
    pid = cur.lastrowid
    conn.close()
    return pid


def _sample_breakdown(site: Site, port: Port):
    leg = VoyageLeg(
        index=1, from_role="load", from_name=port.port_name,
        from_lat=port.lat, from_lon=port.lon,
        to_role="launch_site", to_name=site.name or "Launch Site",
        to_lat=site.lat, to_lon=site.lon,
        distance_nm=100.0, transit_days=0.5, onsite_days=2.0,
    )
    return compute_voyage_cost(
        site, port, [leg],
        vessels=default_vessels(),
        port_fees=default_port_fees(),
        speed_kts=9.0,
        launches=1,
    )


class TestFinalizeVoyage:
    def test_finalize_writes_params_and_breakdown(self):
        project_id = _insert_project()
        site_id = _insert_site()
        port_id = _insert_port()
        site = Site(id=site_id, lat=40.0, lon=-70.0, name="Launch Site")
        port = Port(id=port_id, port_name="Providence", lat=41.8, lon=-71.4)
        breakdown = _sample_breakdown(site, port)
        params = load_params()

        fin = finalize_voyage(project_id, site, port_id, params, breakdown)
        assert fin.project_id == project_id
        assert fin.site_id == site_id
        assert fin.load_port_id == port_id
        assert fin.estimate_params["speed_kts"] == params.speed_kts
        assert fin.estimate_breakdown["total_usd"] == breakdown.total_usd
        assert fin.actual_breakdown is None

    def test_unique_per_project_site_overwrites_estimate(self):
        project_id = _insert_project()
        site_id = _insert_site()
        port_a = _insert_port("Port A")
        port_b = _insert_port("Port B", 42.0, -72.0)
        site = Site(id=site_id, lat=40.0, lon=-70.0, name="Launch Site")
        port1 = Port(id=port_a, port_name="Port A", lat=41.8, lon=-71.4)
        port2 = Port(id=port_b, port_name="Port B", lat=42.0, lon=-72.0)
        params = load_params()

        b1 = _sample_breakdown(site, port1)
        b2 = _sample_breakdown(site, port2)
        b2.launches = 2
        b2 = compute_voyage_cost(
            site, port2, b2.legs,
            vessels=default_vessels(),
            port_fees=default_port_fees(),
            speed_kts=9.0,
            launches=2,
        )

        finalize_voyage(project_id, site, port_a, params, b1)
        fin2 = finalize_voyage(project_id, site, port_b, params, b2, notes="second")

        assert fin2.load_port_id == port_b
        assert fin2.notes == "second"
        assert fin2.estimate_breakdown["launches"] == 2
        assert len(list_finalizations(project_id)) == 1

    def test_finalize_without_project_raises(self):
        site = Site(id=1, lat=40.0, lon=-70.0)
        port = Port(id=1, port_name="P", lat=41.0, lon=-71.0)
        breakdown = _sample_breakdown(site, port)
        with pytest.raises(FinalizationError):
            finalize_voyage(0, site, 1, load_params(), breakdown)

    def test_finalize_without_saved_site_raises(self):
        site = Site(lat=40.0, lon=-70.0)  # no id
        with pytest.raises(FinalizationError):
            finalize_voyage(1, site, 1, load_params(), _sample_breakdown(
                Site(lat=40.0, lon=-70.0), Port(port_name="P", lat=41.0, lon=-71.0)
            ))


class TestActuals:
    def _finalize(self):
        project_id = _insert_project()
        site_id = _insert_site()
        port_id = _insert_port()
        site = Site(id=site_id, lat=40.0, lon=-70.0, name="Launch Site")
        port = Port(id=port_id, port_name="Providence", lat=41.8, lon=-71.4)
        breakdown = _sample_breakdown(site, port)
        params = load_params()
        fin = finalize_voyage(project_id, site, port_id, params, breakdown)
        return fin

    def test_save_and_compare_actuals(self):
        fin = self._finalize()
        actual = copy_estimate_for_actuals(fin.estimate_breakdown, fin.estimate_params)
        # Simulate overrun: add $10k to platform charter
        for v in actual["vessels"]:
            if v.get("key") == "platform":
                v["charter_days"] = float(v.get("charter_days") or 0.0) + 0.5
        actual = recompute_breakdown_totals(actual)

        updated = save_actuals(fin.id, actual)
        assert updated.actual_breakdown is not None
        assert updated.actual_entered_at

        rows = compare_estimate_actual(
            fin.estimate_breakdown, updated.actual_breakdown
        )
        total_row = next(r for r in rows if r["label"] == "Total USD")
        assert total_row["delta"] > 0

    def test_clear_actuals(self):
        fin = self._finalize()
        actual = copy_estimate_for_actuals(fin.estimate_breakdown, fin.estimate_params)
        save_actuals(fin.id, actual)
        cleared = clear_actuals(fin.id)
        assert cleared.actual_breakdown is None
        assert cleared.actual_entered_at is None

    def test_re_finalize_clears_actuals(self):
        fin = self._finalize()
        actual = copy_estimate_for_actuals(fin.estimate_breakdown, fin.estimate_params)
        save_actuals(fin.id, actual)

        site = Site(id=fin.site_id, lat=40.0, lon=-70.0, name="Launch Site")
        port = Port(id=fin.load_port_id, port_name="Providence", lat=41.8, lon=-71.4)
        refinal = finalize_voyage(
            fin.project_id, site, fin.load_port_id,
            load_params(), _sample_breakdown(site, port),
        )
        assert refinal.actual_breakdown is None


class TestRecomputeBreakdownTotals:
    def test_fuel_recomputed_from_gal_day_rates(self):
        data = {
            "total_transit_days": 10.0,
            "total_onsite_days": 5.0,
            "launches": 1,
            "vessels": [{
                "key": "platform", "name": "Platform", "deployed": True,
                "charter_days": 10.0, "charter_rate_usd_day": 1000.0,
                "at_sea_gal_day": 10.0, "in_port_gal_day": 5.0, "fuel_usd_gal": 2.0,
            }],
            "port_fees": [{"role": "load", "agents_usd": 100.0}],
        }
        out = recompute_breakdown_totals(data)
        assert out["charter_total_usd"] == 10_000.0
        assert out["underway_gal"] == 100.0
        assert out["onsite_gal"] == 25.0
        assert out["fuel_total_usd"] == 250.0
        assert out["port_fees_total_usd"] == 100.0
        assert out["total_usd"] == 10_350.0

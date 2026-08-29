"""
modules/m4_ports/voyage.py -- Voyage economics and waypoint generation.

The cost model is a chain of port calls with the launch site in the middle:

    [Mob] -> [Load] -> [Staging] -> Launch Site -> [Discharge] -> [Demob]

Each leg carries a distance, a transit time (distance / speed / 24 -- the one
formula the user cannot change) and the on-site days spent at its destination.
The first stop is the origin and has no on-site days.

Total cost = every vessel's charter hire + port fees + fuel.

Functions
---------
VoyageCostParams        -- the full editable parameter set (JSON-persistable)
load_params/save_params -- read/write VoyageCostParams from the settings table
build_voyage_legs       -- port-role chain -> list[VoyageLeg]  (geodesy)
compute_voyage_cost     -- legs + params -> VoyageCostBreakdown  (pure arithmetic)
calculate_voyage_cost   -- convenience: build legs then compute, for one candidate
compare_port_options    -- rerun the whole route for each candidate port
generate_waypoints      -- great-circle route points at fixed intervals
save_voyage_schedule    -- persist VoyageSchedule to voyage_schedules table
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.database import get_connection
from core.models import (
    Site, Port, VoyageSchedule, Waypoint,
    VoyageLeg, VesselParams, PortFees, VesselCostLine, VoyageCostBreakdown,
    PORT_ROLES, SELECTABLE_PORT_ROLES, FEE_CATEGORIES,
    VESSEL_KEYS, VESSEL_LABELS,
)
from core.utils import haversine_nm, bearing_deg, intermediate_point


_SETTINGS_KEY = "voyage_cost_params"

# Defaults seeded from the reference voyage sheet (Pascagoula -> ... -> 40N 70W).
_DEFAULT_SPEED_KTS = 9.0

_DEFAULT_ONSITE_DAYS: Dict[str, float] = {
    "mob":         0.0,   # origin -- nothing arrives here, so never billed
    "load":        2.0,
    "staging":     4.0,
    "launch_site": 2.0,
    "discharge":   4.0,
    "demob":       2.0,
}

_DEFAULT_VESSELS: Dict[str, dict] = {
    # charter_days=None -> bills the full voyage (transit + on-site)
    "platform": dict(deployed=True,  charter_rate_usd_day=20_000.0, charter_days=None,
                     at_sea_gal_day=12.0, in_port_gal_day=50.0, fuel_usd_gal=1.0),
    "sv1":      dict(deployed=False, charter_rate_usd_day=10_000.0, charter_days=18.5,
                     at_sea_gal_day=23.0, in_port_gal_day=8.0,  fuel_usd_gal=1.0),
    "sv2":      dict(deployed=False, charter_rate_usd_day=10_000.0, charter_days=0.0,
                     at_sea_gal_day=0.0,  in_port_gal_day=0.0,  fuel_usd_gal=1.0),
}

_DEFAULT_FEES: Dict[str, dict] = {
    "mob": dict(agents_usd=2_500.0, assist_tugs_usd=4_000.0, pilots_usd=3_500.0,
                wharfage_usd=1_000.0, loading_ops_usd=2_000.0, other_usd=1_000.0),
}


# ---- 0. Editable parameter set -----------------------------------------------

def default_vessels() -> List[VesselParams]:
    return [
        VesselParams(key=k, name=VESSEL_LABELS[k], **_DEFAULT_VESSELS[k])
        for k in VESSEL_KEYS
    ]


def default_port_fees() -> List[PortFees]:
    return [PortFees(role=r, **_DEFAULT_FEES.get(r, {})) for r in PORT_ROLES]


@dataclass
class VoyageCostParams:
    """Everything the user can adjust.  Serialisable to a single JSON blob."""
    speed_kts: float = _DEFAULT_SPEED_KTS
    launches: int = 1
    role_port_ids: Dict[str, Optional[int]] = field(
        default_factory=lambda: {r: None for r in SELECTABLE_PORT_ROLES}
    )
    onsite_days: Dict[str, float] = field(
        default_factory=lambda: dict(_DEFAULT_ONSITE_DAYS)
    )
    vessels: List[VesselParams] = field(default_factory=default_vessels)
    port_fees: List[PortFees] = field(default_factory=default_port_fees)

    def vessel(self, key: str) -> Optional[VesselParams]:
        for v in self.vessels:
            if v.key == key:
                return v
        return None

    def fees_for(self, role: str) -> Optional[PortFees]:
        for pf in self.port_fees:
            if pf.role == role:
                return pf
        return None

    def to_dict(self) -> dict:
        return {
            "speed_kts":     self.speed_kts,
            "launches":      self.launches,
            "role_port_ids": {r: self.role_port_ids.get(r) for r in SELECTABLE_PORT_ROLES},
            "onsite_days":   {r: float(self.onsite_days.get(r, 0.0)) for r in PORT_ROLES},
            "vessels": [
                {
                    "key":                  v.key,
                    "name":                 v.name,
                    "deployed":             bool(v.deployed),
                    "charter_rate_usd_day": v.charter_rate_usd_day,
                    "charter_days":         v.charter_days,
                    "at_sea_gal_day":       v.at_sea_gal_day,
                    "in_port_gal_day":      v.in_port_gal_day,
                    "fuel_usd_gal":         v.fuel_usd_gal,
                }
                for v in self.vessels
            ],
            "port_fees": [
                {"role": pf.role, "notes": pf.notes or "",
                 **{f"{c}_usd": pf.amount(c) for c in FEE_CATEGORIES}}
                for pf in self.port_fees
            ],
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "VoyageCostParams":
        """Rebuild from JSON, tolerating missing/extra keys and bad types."""
        p = cls()
        if not isinstance(raw, dict):
            return p

        try:
            p.speed_kts = float(raw.get("speed_kts", p.speed_kts))
        except (TypeError, ValueError):
            pass
        try:
            p.launches = max(1, int(raw.get("launches", p.launches)))
        except (TypeError, ValueError):
            pass

        ids = raw.get("role_port_ids") or {}
        if isinstance(ids, dict):
            for role in SELECTABLE_PORT_ROLES:
                val = ids.get(role)
                try:
                    p.role_port_ids[role] = int(val) if val is not None else None
                except (TypeError, ValueError):
                    p.role_port_ids[role] = None

        days = raw.get("onsite_days") or {}
        if isinstance(days, dict):
            for role in PORT_ROLES:
                if role in days:
                    try:
                        p.onsite_days[role] = float(days[role])
                    except (TypeError, ValueError):
                        pass

        by_key = {v.key: v for v in p.vessels}
        for entry in raw.get("vessels") or []:
            if not isinstance(entry, dict):
                continue
            v = by_key.get(entry.get("key"))
            if v is None:
                continue
            v.deployed = bool(entry.get("deployed", v.deployed))
            for attr in ("charter_rate_usd_day", "at_sea_gal_day",
                         "in_port_gal_day", "fuel_usd_gal"):
                if attr in entry:
                    try:
                        setattr(v, attr, float(entry[attr]))
                    except (TypeError, ValueError):
                        pass
            if "charter_days" in entry:
                cd = entry["charter_days"]
                try:
                    v.charter_days = None if cd is None else float(cd)
                except (TypeError, ValueError):
                    pass

        fees_by_role = {pf.role: pf for pf in p.port_fees}
        for entry in raw.get("port_fees") or []:
            if not isinstance(entry, dict):
                continue
            pf = fees_by_role.get(entry.get("role"))
            if pf is None:
                continue
            for cat in FEE_CATEGORIES:
                attr = f"{cat}_usd"
                if attr in entry:
                    try:
                        setattr(pf, attr, float(entry[attr]))
                    except (TypeError, ValueError):
                        pass
            if "notes" in entry:
                pf.notes = str(entry.get("notes") or "")
        return p


def load_params() -> VoyageCostParams:
    """Read the saved parameter set, falling back to reference-sheet defaults."""
    try:
        from core.settings import get_setting
        raw = get_setting(_SETTINGS_KEY)
    except Exception:
        return VoyageCostParams()
    if not raw:
        return VoyageCostParams()
    try:
        return VoyageCostParams.from_dict(json.loads(raw))
    except (ValueError, TypeError):
        return VoyageCostParams()


def save_params(params: VoyageCostParams) -> None:
    from core.settings import set_setting
    set_setting(_SETTINGS_KEY, json.dumps(params.to_dict()))


# ---- 1. Route construction ---------------------------------------------------

def resolve_role_ports(
    params: VoyageCostParams,
    candidate: Optional[Port] = None,
    port_lookup: Optional[Dict[int, Port]] = None,
) -> Dict[str, Optional[Port]]:
    """Map each selectable role to a Port.

    Roles the user pinned resolve through port_lookup (or the DB).  Load and
    Discharge fall back to the candidate port from the nearest-ports search, so
    the default route is candidate -> site -> candidate: a simple round trip.
    """
    from modules.m4_ports.proximity import get_port

    resolved: Dict[str, Optional[Port]] = {}
    for role in SELECTABLE_PORT_ROLES:
        pid = params.role_port_ids.get(role)
        port: Optional[Port] = None
        if pid is not None:
            if port_lookup and pid in port_lookup:
                port = port_lookup[pid]
            else:
                try:
                    port = get_port(pid)
                except Exception:
                    port = None
        if port is None and role in ("load", "discharge"):
            port = candidate
        resolved[role] = port
    return resolved


def build_voyage_legs(
    site: Site,
    role_ports: Dict[str, Optional[Port]],
    onsite_days: Optional[Dict[str, float]] = None,
    speed_kts: float = _DEFAULT_SPEED_KTS,
) -> List[VoyageLeg]:
    """Build the leg list for the port chain, skipping unset roles.

    Distances are great-circle (haversine); transit days are
    distance_nm / speed_kts / 24.  On-site days attach to each leg's
    destination, so the first stop (the origin) is never charged on-site time.
    """
    onsite_days = onsite_days or {}

    stops: List[tuple] = []
    for role in PORT_ROLES:
        if role == "launch_site":
            stops.append((role, site.name or "Launch Site", site.lat, site.lon))
            continue
        port = role_ports.get(role)
        if port is not None:
            stops.append((role, port.port_name, port.lat, port.lon))

    legs: List[VoyageLeg] = []
    for i in range(len(stops) - 1):
        f_role, f_name, f_lat, f_lon = stops[i]
        t_role, t_name, t_lat, t_lon = stops[i + 1]
        dist = haversine_nm(f_lat, f_lon, t_lat, t_lon)
        transit = dist / (speed_kts * 24.0) if speed_kts > 0 else 0.0
        legs.append(VoyageLeg(
            index        = i + 1,
            from_role    = f_role,
            from_name    = f_name,
            from_lat     = f_lat,
            from_lon     = f_lon,
            to_role      = t_role,
            to_name      = t_name,
            to_lat       = t_lat,
            to_lon       = t_lon,
            distance_nm  = round(dist, 2),
            # 6dp: rounding transit days more coarsely visibly shifts the
            # platform charter, which multiplies them by a ~$20k/day rate.
            transit_days = round(transit, 6),
            onsite_days  = float(onsite_days.get(t_role, 0.0)),
        ))
    return legs


def route_roles(legs: List[VoyageLeg]) -> List[str]:
    """Roles actually visited by this route, in order (origin included)."""
    if not legs:
        return []
    roles = [legs[0].from_role]
    for leg in legs:
        if leg.to_role not in roles:
            roles.append(leg.to_role)
    return roles


# ---- 2. Cost arithmetic ------------------------------------------------------

def compute_voyage_cost(
    site: Site,
    port: Port,
    legs: List[VoyageLeg],
    vessels: Optional[List[VesselParams]] = None,
    port_fees: Optional[List[PortFees]] = None,
    speed_kts: float = _DEFAULT_SPEED_KTS,
    launches: int = 1,
) -> VoyageCostBreakdown:
    """Pure arithmetic over a prepared leg list -- no geodesy, no DB.

    Charter: the platform bills the whole voyage (transit + on-site); a vessel
    with an explicit charter_days bills only that window.
    Fuel: every deployed vessel burns across the full leg list, at-sea rate on
    transit days and in-port rate on on-site days.
    Port fees: charged once per role actually visited.
    """
    vessels   = vessels if vessels is not None else default_vessels()
    port_fees = port_fees if port_fees is not None else default_port_fees()

    total_transit  = round(sum(leg.transit_days for leg in legs), 6)
    total_onsite   = round(sum(leg.onsite_days for leg in legs), 4)
    total_distance = round(sum(leg.distance_nm for leg in legs), 2)
    voyage_days    = total_transit + total_onsite

    lines: List[VesselCostLine] = []
    charter_total = 0.0
    fuel_total    = 0.0
    underway_gal  = 0.0
    onsite_gal    = 0.0

    for v in vessels:
        if not v.deployed:
            lines.append(VesselCostLine(
                key=v.key, name=v.name, deployed=False,
                charter_days=0.0, charter_rate_usd_day=v.charter_rate_usd_day,
                charter_usd=0.0, underway_gal=0.0, onsite_gal=0.0, total_gal=0.0,
                fuel_usd_gal=v.fuel_usd_gal, fuel_usd=0.0,
            ))
            continue

        days    = voyage_days if v.charter_days is None else float(v.charter_days)
        charter = round(v.charter_rate_usd_day * days, 2)
        v_under = round(total_transit * v.at_sea_gal_day, 2)
        v_onsit = round(total_onsite * v.in_port_gal_day, 2)
        v_gal   = round(v_under + v_onsit, 2)
        fuel    = round(v_gal * v.fuel_usd_gal, 2)

        charter_total += charter
        fuel_total    += fuel
        underway_gal  += v_under
        onsite_gal    += v_onsit

        lines.append(VesselCostLine(
            key=v.key, name=v.name, deployed=True,
            charter_days=round(days, 4), charter_rate_usd_day=v.charter_rate_usd_day,
            charter_usd=charter, underway_gal=v_under, onsite_gal=v_onsit,
            total_gal=v_gal, fuel_usd_gal=v.fuel_usd_gal, fuel_usd=fuel,
        ))

    visited   = set(route_roles(legs))
    fee_lines = [pf for pf in port_fees if pf.role in visited]
    fees_total = round(sum(pf.total_usd for pf in fee_lines), 2)

    charter_total = round(charter_total, 2)
    fuel_total    = round(fuel_total, 2)

    return VoyageCostBreakdown(
        site                = site,
        port                = port,
        legs                = legs,
        vessels             = lines,
        port_fees           = fee_lines,
        speed_kts           = speed_kts,
        total_distance_nm   = total_distance,
        total_transit_days  = total_transit,
        total_onsite_days   = total_onsite,
        charter_total_usd   = charter_total,
        port_fees_total_usd = fees_total,
        fuel_total_usd      = fuel_total,
        underway_gal        = round(underway_gal, 2),
        onsite_gal          = round(onsite_gal, 2),
        fuel_total_gal      = round(underway_gal + onsite_gal, 2),
        total_usd           = round(charter_total + fees_total + fuel_total, 2),
        launches            = max(1, int(launches or 1)),
    )


def calculate_voyage_cost(
    site: Site,
    port: Port,
    params: Optional[VoyageCostParams] = None,
    port_lookup: Optional[Dict[int, Port]] = None,
) -> VoyageCostBreakdown:
    """Build the route for one candidate Load/Discharge port and cost it."""
    params = params or load_params()
    role_ports = resolve_role_ports(params, candidate=port, port_lookup=port_lookup)
    legs = build_voyage_legs(site, role_ports, params.onsite_days, params.speed_kts)
    return compute_voyage_cost(
        site, port, legs,
        vessels   = params.vessels,
        port_fees = params.port_fees,
        speed_kts = params.speed_kts,
        launches  = params.launches,
    )


# ---- 2. generate_waypoints ---------------------------------------------------

def generate_waypoints(
    site: Site,
    port: Port,
    platform_speed_kts: float = 6.0,
    interval_hours: float = 12.0,
) -> list[Waypoint]:
    """
    Generate great-circle waypoints from port to site at interval_hours spacing.

    Returns a list whose first element is the departure point (port) and last
    element is the arrival point (site).  Intermediate points are spaced by
    interval_hours of travel at platform_speed_kts.
    """
    total_nm    = haversine_nm(port.lat, port.lon, site.lat, site.lon)
    total_hours = (total_nm / platform_speed_kts) if platform_speed_kts > 0 else 0.0

    waypoints: list[Waypoint] = []
    leg = 1

    # Departure
    waypoints.append(Waypoint(
        leg           = leg,
        description   = "Departure",
        lat           = port.lat,
        lon           = port.lon,
        elapsed_hours = 0.0,
        elapsed_days  = 0.0,
        cumulative_nm = 0.0,
    ))
    leg += 1

    # Intermediate waypoints (only if route is longer than one interval)
    if total_hours > 0 and interval_hours > 0:
        elapsed  = interval_hours
        wp_index = 1
        while elapsed < total_hours - 1e-9:   # avoid floating-point dup of final point
            frac    = elapsed / total_hours
            lat_wp, lon_wp = intermediate_point(
                port.lat, port.lon, site.lat, site.lon, frac
            )
            cum_nm = frac * total_nm
            waypoints.append(Waypoint(
                leg           = leg,
                description   = f"Waypoint {wp_index}",
                lat           = round(lat_wp, 5),
                lon           = round(lon_wp, 5),
                elapsed_hours = round(elapsed, 2),
                elapsed_days  = round(elapsed / 24.0, 4),
                cumulative_nm = round(cum_nm, 1),
            ))
            leg       += 1
            wp_index  += 1
            elapsed   += interval_hours

    # Arrival
    waypoints.append(Waypoint(
        leg           = leg,
        description   = "Arrival at site",
        lat           = site.lat,
        lon           = site.lon,
        elapsed_hours = round(total_hours, 2),
        elapsed_days  = round(total_hours / 24.0, 4),
        cumulative_nm = round(total_nm, 1),
    ))

    return waypoints


# ---- 3. compare_port_options -------------------------------------------------

def compare_port_options(
    site: Site,
    ports: list[Port],
    params: Optional[VoyageCostParams] = None,
) -> list[VoyageCostBreakdown]:
    """
    Rerun the whole voyage for each candidate port and return cheapest-first.

    Each candidate is swapped into the Load and Discharge roles (unless the user
    pinned those explicitly), so the ranking reflects the full multi-leg route
    rather than a single hop.
    """
    params = params or load_params()
    # Resolve pinned role ports once -- they are identical across candidates.
    lookup = {p.id: p for p in ports if p.id is not None}
    costs = [
        calculate_voyage_cost(site, port, params=params, port_lookup=lookup)
        for port in ports
    ]
    costs.sort(key=lambda vc: vc.total_usd)
    return costs


# ---- 4. save_voyage_schedule -------------------------------------------------

def save_voyage_schedule(schedule: VoyageSchedule) -> int:
    """
    Insert a VoyageSchedule into the voyage_schedules table.

    site.id and port.id must be set (i.e. both must have been saved to the DB
    before calling this function).  Raises ValueError if either is None.

    Returns the new row id.
    """
    if schedule.site.id is None:
        raise ValueError("schedule.site.id must be set before saving a voyage schedule")
    if schedule.port.id is None:
        raise ValueError("schedule.port.id must be set before saving a voyage schedule")

    cost = schedule.cost

    waypoints_json = json.dumps([
        {
            "leg":           wp.leg,
            "description":   wp.description,
            "lat":           wp.lat,
            "lon":           wp.lon,
            "elapsed_hours": wp.elapsed_hours,
            "elapsed_days":  wp.elapsed_days,
            "cumulative_nm": wp.cumulative_nm,
        }
        for wp in schedule.waypoints
    ])

    # The full breakdown lives in cost_summary_json; the legacy per-column fields
    # (tugs, crew, MT-based fuel, weather contingency) are not part of this model.
    cost_summary_json = json.dumps(serialize_breakdown(cost))

    conn = get_connection()
    with conn:
        cur = conn.execute(
            """
            INSERT INTO voyage_schedules (
                site_id, port_id,
                departure_date,
                platform_speed_kts, port_fees_usd,
                waypoints_json, cost_summary_json
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                schedule.site.id,
                schedule.port.id,
                schedule.departure_date.isoformat() if schedule.departure_date else None,
                cost.speed_kts,
                cost.port_fees_total_usd,
                waypoints_json,
                cost_summary_json,
            ),
        )
        new_id = cur.lastrowid
    conn.close()
    return new_id


def serialize_breakdown(breakdown: VoyageCostBreakdown) -> dict:
    """JSON-serialisable cost breakdown (shared by schedules and finalizations)."""
    return {
        "total_distance_nm":   breakdown.total_distance_nm,
        "total_transit_days":  breakdown.total_transit_days,
        "total_onsite_days":   breakdown.total_onsite_days,
        "voyage_days":         breakdown.voyage_days,
        "speed_kts":           breakdown.speed_kts,
        "charter_total_usd":   breakdown.charter_total_usd,
        "port_fees_total_usd": breakdown.port_fees_total_usd,
        "fuel_total_usd":      breakdown.fuel_total_usd,
        "underway_gal":        breakdown.underway_gal,
        "onsite_gal":          breakdown.onsite_gal,
        "fuel_total_gal":      breakdown.fuel_total_gal,
        "total_usd":           breakdown.total_usd,
        "launches":            breakdown.launches,
        "cost_per_launch_usd": breakdown.cost_per_launch(),
        "legs": [
            {
                "index":        leg.index,
                "from_role":    leg.from_role,
                "from_name":    leg.from_name,
                "to_role":      leg.to_role,
                "to_name":      leg.to_name,
                "distance_nm":  leg.distance_nm,
                "transit_days": leg.transit_days,
                "onsite_days":  leg.onsite_days,
            }
            for leg in breakdown.legs
        ],
        "vessels": [
            {
                "key":                  v.key,
                "name":                 v.name,
                "deployed":             v.deployed,
                "charter_days":         v.charter_days,
                "charter_rate_usd_day": v.charter_rate_usd_day,
                "charter_usd":          v.charter_usd,
                "underway_gal":         v.underway_gal,
                "onsite_gal":           v.onsite_gal,
                "total_gal":            v.total_gal,
                "fuel_usd_gal":         v.fuel_usd_gal,
                "fuel_usd":             v.fuel_usd,
            }
            for v in breakdown.vessels
        ],
        "port_fees": [
            {"role": pf.role, "total_usd": pf.total_usd, "notes": pf.notes or "",
             **{f"{c}_usd": pf.amount(c) for c in FEE_CATEGORIES}}
            for pf in breakdown.port_fees
        ],
    }

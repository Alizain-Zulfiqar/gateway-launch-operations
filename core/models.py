"""
core/models.py — Dataclasses for all domain objects.
These are plain Python dataclasses — no ORM, no magic.
"""
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, Dict, List


@dataclass
class Site:
    lat: float              # +N / -S decimal degrees
    lon: float              # +E / -W decimal degrees
    name: str = ""
    bbox_nm: float = 25.0
    platform_id: Optional[int] = None
    notes: str = ""
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    coord_code: Optional[str] = None

    def __post_init__(self):
        from core.utils import validate_lat, validate_lon
        validate_lat(self.lat)
        validate_lon(self.lon)

    @property
    def lat_dir(self) -> str:
        return "N" if self.lat >= 0 else "S"

    @property
    def lon_dir(self) -> str:
        return "E" if self.lon >= 0 else "W"

    @property
    def coord_str(self) -> str:
        return (
            f"{abs(self.lat):.4f}°{self.lat_dir}, "
            f"{abs(self.lon):.4f}°{self.lon_dir}"
        )


@dataclass
class Vehicle:
    name: str
    vehicle_class: str                   # slv_orb / slv_sub / mlv_orb / mlv_sub
    max_wind_kts: float
    max_gust_kts: float
    max_hs_m: float
    max_swell_ht_m: float
    max_swell_period_s: float
    max_wind_dir_tolerance_deg: float = 45.0
    max_sea_dir_tolerance_deg: float  = 60.0
    max_swell_dir_tolerance_deg: float= 60.0
    provider: str = ""
    mass_to_orbit_kg: Optional[float] = None
    propellant: str = ""
    recovery_mode: str = "expendable"   # expendable/rtls/droneship/parachute/glide
    notes: str = ""
    id: Optional[int] = None
    # Extended fields (Phase 2 expansion)
    height_m: Optional[float] = None
    diameter_m: Optional[float] = None
    gross_mass_kg: Optional[float] = None
    leo_payload_kg: Optional[float] = None
    sso_payload_kg: Optional[float] = None
    gto_payload_kg: Optional[float] = None
    stages: Optional[int] = None
    propellant_stage1: str = ""
    propellant_stage2: str = ""
    propellant_upper: str = ""
    status: str = "operational"
    first_flight_year: Optional[int] = None
    country: str = ""
    manufacturer: str = ""
    wind_hold_verified: bool = False
    sea_state_verified: bool = False
    data_source: str = "estimated"
    notes_extended: str = ""
    category_id: Optional[int] = None

    def thresholds(self) -> Dict[str, float]:
        """Return threshold dict keyed by parameter shortname."""
        return {
            "ws":   self.max_wind_kts,
            "wg":   self.max_gust_kts,
            "sh":   self.max_hs_m,
            "swh":  self.max_swell_ht_m,
            "swp":  self.max_swell_period_s,
            "wdV":  self.max_wind_dir_tolerance_deg,
            "sdV":  self.max_sea_dir_tolerance_deg,
            "swdV": self.max_swell_dir_tolerance_deg,
        }


@dataclass
class Platform:
    name: str
    hull_type: str          # semisub / jackup / tlp / spar / fixed
    hull_motion_factor: float
    dp_capable: bool = True
    max_hs_operating_m: Optional[float] = None
    typical_depth_m: Optional[float] = None
    payload_class: str = ""
    notes: str = ""
    id: Optional[int] = None
    # Extended fields
    deck_area_m2: Optional[float] = None
    draft_m: Optional[float] = None
    min_depth_m: float = 50.0
    abs_approval: str = ""
    first_deployment_yr: Optional[int] = None
    is_reference: bool = False
    # Vessel dimensions (Part B)
    loa_m: Optional[float] = None
    beam_m: Optional[float] = None
    grt: Optional[float] = None
    nrt: Optional[float] = None
    panama_canal_tons: Optional[float] = None
    displacement_t: Optional[float] = None
    min_air_gap_m: Optional[float] = None
    max_wave_crest_m: Optional[float] = None
    deck_elevation_m: Optional[float] = None
    dp_class: Optional[int] = None
    dp_class_notes: str = ""
    class_society: str = ""
    class_notation: str = ""
    flag_state: str = ""
    imo_number: str = ""
    transit_draft_m: Optional[float] = None
    launch_draft_m: Optional[float] = None
    specs_verified: bool = False
    specs_verified_source: str = ""
    specs_notes: str = ""
    vessel_code: Optional[str] = None   # pinned hull identifier (Pre-28B-1)


@dataclass
class PlatformContract:
    platform_id:                  int
    vessel_code:                  str
    contract_code:                str
    customer_name:                str
    contract_start:               str            # ISO date 'YYYY-MM-DD'
    contract_end:                 str            # ISO date 'YYYY-MM-DD'
    contract_tier:                str = "master"  # 'master'/'subcontract'/'amendment'
    parent_contract_id:           Optional[int] = None
    status:                       str = "active"
    warranted_max_wind_kts:       Optional[float] = None
    warranted_max_gust_kts:       Optional[float] = None
    warranted_max_hs_m:           Optional[float] = None
    warranted_max_swell_ht_m:     Optional[float] = None
    warranted_max_swell_period_s: Optional[float] = None
    warranted_verified:           bool = False
    warranted_verified_by:        Optional[str] = None
    warranted_verified_date:      Optional[str] = None
    warranted_source_doc:         Optional[str] = None
    document_url:                 Optional[str] = None
    document_unc_path:            Optional[str] = None
    notes:                        Optional[str] = None
    id:                           Optional[int] = None
    created_at:                   Optional[str] = None
    updated_at:                   Optional[str] = None
    is_archived:                  bool = False    # list-view visibility only (Pre-28B-2)

    def warranted_envelope(self) -> Dict[str, float]:
        """Return non-None warranted limits keyed by parameter shortname.
        Directional tolerances are not warranted at vessel level."""
        result: Dict[str, float] = {}
        if self.warranted_max_wind_kts is not None:
            result["ws"] = self.warranted_max_wind_kts
        if self.warranted_max_gust_kts is not None:
            result["wg"] = self.warranted_max_gust_kts
        if self.warranted_max_hs_m is not None:
            result["sh"] = self.warranted_max_hs_m
        if self.warranted_max_swell_ht_m is not None:
            result["swh"] = self.warranted_max_swell_ht_m
        if self.warranted_max_swell_period_s is not None:
            result["swp"] = self.warranted_max_swell_period_s
        return result


@dataclass
class LauncherConfig:
    launcher_name: str
    launcher_type: str    # rail / vertical_fixed / vertical_mobile / air_carrier
    mount_method: str
    vehicle_id: Optional[int] = None
    base_diameter_m: Optional[float] = None
    base_length_m: Optional[float] = None
    launcher_height_m: Optional[float] = None
    total_weight_kg: Optional[float] = None
    hold_down_pattern: Optional[str] = None
    umbilical_count: Optional[int] = None
    deck_load_kpa: Optional[float] = None
    rail_gauge_m: Optional[float] = None
    rail_length_m: Optional[float] = None
    min_deck_area_m2: Optional[float] = None
    blast_radius_m: Optional[float] = None
    launch_azimuth_min_deg: Optional[float] = None
    launch_azimuth_max_deg: Optional[float] = None
    specs_verified: bool = False
    specs_verified_source: str = ""
    data_source: str = "estimated"
    notes: str = ""
    id: Optional[int] = None


@dataclass
class AnalysisResult:
    site: Site
    vehicle: Vehicle
    platform: Platform
    mode: str                           # '45day' or 'historical'
    overall_prob: float
    param_probs: Dict[str, float]       # {"ws": 0.74, "sh": 0.61, ...}
    limiting_param: str
    data_sources: Dict[str, str]        # {"ws": "ndbc", "swh": "era5_model", ...}
    effective_means: Dict[str, float]   # effective climatological mean per param
    thresholds: Dict[str, float]        # vehicle thresholds used
    weights: Dict[str, float]           # normalized weights used
    active_params: set = field(default_factory=set)  # params with non-zero weight
    era_weight: float = 1.0
    confidence_rating: str = "model"    # 'high'/'moderate'/'low'/'model'
    year_start: Optional[int] = None
    year_end: Optional[int] = None
    month_filter: Optional[int] = None
    notes: str = ""
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    # Vessel pre-check gate (Pre-28B-1). None when no platform_contract supplied.
    vessel_verdict: Optional[str] = None            # 'GO'/'MARGINAL'/'NO-GO' or None
    vessel_limiting_param: Optional[str] = None
    vessel_param_probs: Dict[str, float] = field(default_factory=dict)
    vessel_contract_code: Optional[str] = None
    warranted_verified: bool = False                # governing contract verified?

    @property
    def verdict(self) -> str:
        from core.verdict_thresholds import classify_verdict
        return classify_verdict(self.overall_prob)

    @property
    def pct(self) -> int:
        return round(self.overall_prob * 100)


@dataclass
class Project:
    name: str
    code_name: str = ""
    description: str = ""
    status: str = "active"
    launch_date_start: Optional[str] = None  # ISO date string 'YYYY-MM-DD'
    launch_date_end: Optional[str] = None    # ISO date string 'YYYY-MM-DD'
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_archived: bool = False


@dataclass
class NDBCStation:
    station_id: str
    name: str
    lat: float
    lon: float
    has_spec: bool = False
    met_data: bool = False
    distance_nm: Optional[float] = None   # set by proximity search
    bearing_deg: Optional[float] = None


@dataclass
class Port:
    port_name: str
    lat: float              # +N / -S
    lon: float              # +E / -W
    country: str = ""
    wpi_number: str = ""
    harbor_size: str = ""
    depth_anch_m: Optional[float] = None
    fuel_oil: bool = False
    diesel: bool = False
    max_vessel_size: str = ""
    id: Optional[int] = None
    distance_nm: Optional[float] = None   # set by proximity search
    bearing_deg: Optional[float] = None

    @property
    def coord_str(self) -> str:
        lat_d = "N" if self.lat >= 0 else "S"
        lon_d = "E" if self.lon >= 0 else "W"
        return f"{abs(self.lat):.2f}°{lat_d}, {abs(self.lon):.2f}°{lon_d}"


# ── Voyage cost model ─────────────────────────────────────────────────────────
#
# A voyage is an ordered chain of port calls with the launch site in the middle:
#
#   [Mob] -> [Load] -> [Staging] -> Launch Site -> [Discharge] -> [Demob]
#
# Roles other than Load/Discharge are optional; empty ones collapse out of the
# sequence.  With only Load and Discharge set (both to the same port) the chain
# reduces to Port -> Site -> Port, i.e. a simple round trip.

PORT_ROLES: tuple[str, ...] = (
    "mob", "load", "staging", "launch_site", "discharge", "demob",
)

PORT_ROLE_LABELS: Dict[str, str] = {
    "mob":         "Mob Port",
    "load":        "Load Port",
    "staging":     "Staging Port",
    "launch_site": "Launch Site",
    "discharge":   "Discharge Port",
    "demob":       "Demob Port",
}

# Roles the user picks a port for (the launch site comes from the active Site).
SELECTABLE_PORT_ROLES: tuple[str, ...] = (
    "mob", "load", "staging", "discharge", "demob",
)

FEE_CATEGORIES: tuple[str, ...] = (
    "agents", "assist_tugs", "pilots", "wharfage", "loading_ops", "other",
)

FEE_CATEGORY_LABELS: Dict[str, str] = {
    "agents":      "Agents Fees",
    "assist_tugs": "Assist Tugs",
    "pilots":      "Pilots Fees",
    "wharfage":    "Wharfage / Dockage",
    "loading_ops": "Loading Ops",
    "other":       "Other",
}

VESSEL_KEYS: tuple[str, ...] = ("platform", "sv1", "sv2")

VESSEL_LABELS: Dict[str, str] = {
    "platform": "Gateway Platform",
    "sv1":      "Support Vessel 1",
    "sv2":      "Support Vessel 2",
}


@dataclass
class VoyageLeg:
    """One port-to-port hop.  On-site days belong to the leg's destination."""
    index: int
    from_role: str
    from_name: str
    from_lat: float
    from_lon: float
    to_role: str
    to_name: str
    to_lat: float
    to_lon: float
    distance_nm: float
    transit_days: float
    onsite_days: float = 0.0

    @property
    def label(self) -> str:
        return f"{self.from_name} -> {self.to_name}"


@dataclass
class VesselParams:
    """Charter and fuel rates for one vessel.

    charter_days=None means "bill the whole voyage" (the Gateway platform);
    a number means the vessel has independent on-hire/off-hire dates and bills
    only for that window, regardless of voyage length.
    """
    key: str
    name: str
    deployed: bool = True
    charter_rate_usd_day: float = 0.0
    charter_days: Optional[float] = None
    at_sea_gal_day: float = 0.0
    in_port_gal_day: float = 0.0
    fuel_usd_gal: float = 0.0

    @property
    def bills_full_voyage(self) -> bool:
        return self.charter_days is None


@dataclass
class PortFees:
    """The six flat fee categories charged for a single port call."""
    role: str
    agents_usd: float = 0.0
    assist_tugs_usd: float = 0.0
    pilots_usd: float = 0.0
    wharfage_usd: float = 0.0
    loading_ops_usd: float = 0.0
    other_usd: float = 0.0
    notes: str = ""

    @property
    def total_usd(self) -> float:
        return round(
            self.agents_usd + self.assist_tugs_usd + self.pilots_usd
            + self.wharfage_usd + self.loading_ops_usd + self.other_usd,
            2,
        )

    def amount(self, category: str) -> float:
        return float(getattr(self, f"{category}_usd", 0.0))


@dataclass
class VesselCostLine:
    """Computed charter + fuel result for one vessel over one voyage."""
    key: str
    name: str
    deployed: bool
    charter_days: float
    charter_rate_usd_day: float
    charter_usd: float
    underway_gal: float
    onsite_gal: float
    total_gal: float
    fuel_usd_gal: float
    fuel_usd: float


@dataclass
class VoyageCostBreakdown:
    """Full cost result for one voyage sequence.

    total_usd = sum of every vessel's charter + port fees + fuel.
    """
    site: Site
    port: Port                      # candidate Load/Discharge port this run used
    legs: List[VoyageLeg]
    vessels: List[VesselCostLine]
    port_fees: List[PortFees]
    speed_kts: float
    total_distance_nm: float
    total_transit_days: float
    total_onsite_days: float
    charter_total_usd: float
    port_fees_total_usd: float
    fuel_total_usd: float
    underway_gal: float
    onsite_gal: float
    fuel_total_gal: float
    total_usd: float
    launches: int = 1

    @property
    def voyage_days(self) -> float:
        return round(self.total_transit_days + self.total_onsite_days, 4)

    @property
    def total_formatted(self) -> str:
        return f"${self.total_usd:,.0f}"

    def cost_per_launch(self, launches: Optional[int] = None) -> float:
        n = self.launches if launches is None else launches
        if not n or n < 1:
            n = 1
        return round(self.total_usd / n, 2)

    def vessel(self, key: str) -> Optional[VesselCostLine]:
        for line in self.vessels:
            if line.key == key:
                return line
        return None

    def fees_for(self, role: str) -> Optional[PortFees]:
        for pf in self.port_fees:
            if pf.role == role:
                return pf
        return None


@dataclass
class Waypoint:
    leg: int
    description: str
    lat: float
    lon: float
    elapsed_hours: float
    elapsed_days: float
    cumulative_nm: float

    @property
    def coord_str(self) -> str:
        lat_d = "N" if self.lat >= 0 else "S"
        lon_d = "E" if self.lon >= 0 else "W"
        return f"{abs(self.lat):.3f}°{lat_d}, {abs(self.lon):.3f}°{lon_d}"


@dataclass
class VoyageSchedule:
    site: Site
    port: Port
    cost: VoyageCostBreakdown
    waypoints: List[Waypoint]
    departure_date: Optional[date] = None
    notes: str = ""

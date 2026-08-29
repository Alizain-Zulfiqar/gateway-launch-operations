"""
config.py — Application-wide constants, endpoints, and defaults.
"""
import os
import re
from datetime import date
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
    _pack_env = Path(__file__).parent / "packaging" / ".env"
    if _pack_env.is_file():
        load_dotenv(_pack_env, override=False)
except ImportError:
    pass  # dotenv not installed; .env values will not be loaded but app will still run

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
DB_PATH    = BASE_DIR / "gateway.db"
WPI_CSV    = BASE_DIR / "data" / "wpi.csv"   # NGA World Port Index — import before Phase 3
LOGO_PATH  = BASE_DIR / "assets" / "seagate_space_logo.png"


def logo_available() -> bool:
    """Return True if the Seagate Space logo PNG exists on disk."""
    return LOGO_PATH.exists()

# ── NDBC endpoints ────────────────────────────────────────────────────────────
NDBC_ACTIVE_STATIONS_URL = "https://www.ndbc.noaa.gov/activestations.xml"
NDBC_REALTIME_BASE       = "https://www.ndbc.noaa.gov/data/realtime2"
NDBC_HISTORY_BASE        = "https://www.ndbc.noaa.gov/station_history.php"
NDBC_STATION_SEARCH_RADIUS_NM = 200.0   # default search radius for nearest stations

# ── NCEI Data API ─────────────────────────────────────────────────────────────
NCEI_DATA_API    = "https://www.ncei.noaa.gov/access/services/data/v1"
NCEI_SEARCH_API  = "https://www.ncei.noaa.gov/access/services/search/v1/data"
NCEI_DATASET     = "global-marine"
NCEI_WIND_TYPES  = ["WIND_SPEED", "WIND_DIR"]

# ── WaveWatch III ERDDAP ──────────────────────────────────────────────────────
WW3_ERDDAP_BASE  = "https://coastwatch.pfeg.noaa.gov/erddap"

# ── ERA5 CDS ─────────────────────────────────────────────────────────────────
ERA5_DATASET     = "reanalysis-era5-single-levels"
ERA5_WAVE_VARS   = [
    "significant_height_of_combined_wind_waves_and_swell",
    "mean_wave_period",
    "mean_wave_direction",
    "peak_wave_period",
]

# ── Analysis year range (Historical mode spinboxes) ───────────────────────────
ANALYSIS_YEAR_MIN = 1960


def analysis_year_max() -> int:
    """Latest selectable analysis year (+1 for in-progress planning)."""
    return date.today().year + 1


def refresh_analysis_year_spins(start_spin, end_spin) -> None:
    """Update year spinbox ranges to current ANALYSIS_YEAR_MIN..analysis_year_max()."""
    ymax = analysis_year_max()
    ymin = ANALYSIS_YEAR_MIN
    start_spin.setRange(ymin, ymax)
    end_spin.setRange(ymin, ymax)
    if start_spin.value() > ymax:
        start_spin.setValue(ymin)
    if end_spin.value() > ymax:
        end_spin.setValue(min(date.today().year, ymax))
    if end_spin.value() < start_spin.value():
        end_spin.setValue(start_spin.value())


# ── Coordinate convention ─────────────────────────────────────────────────────
# +lat = North, -lat = South
# +lon = East,  -lon = West
# WGS-84 decimal degrees throughout
LAT_MIN, LAT_MAX = -90.0,  90.0
LON_MIN, LON_MAX = -180.0, 180.0

# ── Unit conversion ───────────────────────────────────────────────────────────
MS_TO_KTS   = 1.94384   # m/s → knots
KTS_TO_MS   = 0.514444  # knots → m/s
NM_TO_DEG   = 1.0 / 60  # 1 nautical mile = 1/60 degree of latitude (approximate)
NM_TO_KM    = 1.852

# ── Latitude band thresholds ──────────────────────────────────────────────────
LAT_BANDS = {
    "equatorial": (0,   10),
    "tropical":   (10,  30),
    "midlat":     (30,  60),
    "polar":      (60,  90),
}

# ── ICOADS climatological base values by latitude band ───────────────────────
# Keys: ws (wind speed kts), wg (gust kts), sh (Hs m), swh (swell ht m),
#       swp (swell period s), wdV (wind dir variance °), sdV (sea dir variance °),
#       swdV (swell dir variance °)
CLIMATE_BASE = {
    "equatorial": {"ws":19,"wg":28,"sh":2.0,"swh":2.5,"swp":11,"wdV":45,"sdV":55,"swdV":58},
    "tropical":   {"ws":13,"wg":19,"sh":1.3,"swh":1.7,"swp":12,"wdV":35,"sdV":45,"swdV":48},
    "midlat":     {"ws":24,"wg":36,"sh":2.4,"swh":3.0,"swp":9, "wdV":60,"sdV":65,"swdV":68},
    "polar":      {"ws":32,"wg":48,"sh":3.8,"swh":4.6,"swp":8, "wdV":80,"sdV":85,"swdV":85},
}

# ── Seasonal modifiers [Jan..Dec] × [ws, wg, sh, swh, swp, wdV, sdV, swdV] ──
SEASONAL_MOD = [
    [1.10,1.12,1.10,1.12,0.94,0.94,0.94,0.94],  # Jan
    [1.05,1.07,1.06,1.08,0.96,0.96,0.96,0.96],  # Feb
    [0.95,0.96,0.97,0.97,0.99,0.99,0.99,0.99],  # Mar
    [0.88,0.88,0.90,0.90,1.02,1.02,1.02,1.02],  # Apr
    [0.85,0.85,0.88,0.88,1.04,1.04,1.04,1.04],  # May
    [1.08,1.10,1.05,1.07,0.96,0.96,0.96,0.96],  # Jun
    [1.18,1.22,1.14,1.18,0.92,0.92,0.92,0.92],  # Jul
    [1.20,1.25,1.15,1.20,0.91,0.91,0.91,0.91],  # Aug
    [1.15,1.18,1.12,1.15,0.93,0.93,0.93,0.93],  # Sep
    [1.05,1.07,1.04,1.06,0.97,0.97,0.97,0.97],  # Oct
    [1.08,1.10,1.06,1.08,0.96,0.96,0.96,0.96],  # Nov
    [1.12,1.15,1.10,1.12,0.95,0.95,0.95,0.95],  # Dec
]
PARAM_INDICES = {"ws":0,"wg":1,"sh":2,"swh":3,"swp":4,"wdV":5,"sdV":6,"swdV":7}

# ── Hull motion factors ───────────────────────────────────────────────────────
# Applied ONLY to wave heights (sh, swh) — not wind, not swell period
HULL_MOTION_FACTOR = {
    "semisub": 0.78,   # Gateway S/X/XL default
    "jackup":  0.92,
    "tlp":     0.82,
    "spar":    0.75,
    "fixed":   1.00,
}
# Hull motion factor applies only to wave-HEIGHT magnitudes (sh, swh). Swell
# period is a property of the wave field, not a motion-amplified magnitude, so
# the hull factor must NOT scale it (previously it did, which wrongly shortened
# the effective swell period and inflated its probability).
SEA_STATE_PARAMS = {"sh", "swh"}

# ── Vehicle influence toggle ──────────────────────────────────────────────────
# When False, the vehicle's class and recovery-mode modifiers are NOT applied to
# the effective climatological mean, so the analysis depends purely on the
# parameter threshold values (see DEFAULT_THRESHOLDS / the Optimal Values panel)
# and the location/season/era/hull climatology — not on which vehicle is
# selected. Flip back to True to restore vehicle-class / recovery weighting.
APPLY_VEHICLE_MODIFIERS = False

# ── Default parameter thresholds (operating limits) ───────────────────────────
# System-wide default operating limits used to pre-fill the Optimal Values panel
# on the Analysis / Quick Analysis tabs, independent of the selected vehicle.
# Wave heights stored in metres (6 ft ≈ 1.83 m, 8 ft ≈ 2.44 m). The user can
# override any of these per-run in the Optimal Values panel.
FT_TO_M = 0.3048
DEFAULT_THRESHOLDS = {
    "ws":   20.0,                 # sustained wind ≤ 20 kt
    "wg":   25.0,                 # gust < 25 kt
    "sh":   round(6.0 * FT_TO_M, 2),   # wave height < 6 ft → 1.83 m
    "swh":  round(8.0 * FT_TO_M, 2),   # swell height ≤ 8 ft → 2.44 m
    "swp":  18.0,                 # swell period ≤ 18 s
    "wdV":  45.0,                 # wind direction tolerance (deg)
    "sdV":  60.0,                 # sea direction tolerance (deg)
    "swdV": 60.0,                 # swell direction tolerance (deg)
}

# ── Vehicle class modifiers ───────────────────────────────────────────────────
VEHICLE_CLASS_MOD = {
    "slv_orb": {"ws":1.00,"wg":1.00,"sh":1.00,"swh":1.00},
    "slv_sub": {"ws":1.10,"wg":1.10,"sh":0.88,"swh":0.88},
    "mlv_orb": {"ws":0.82,"wg":0.82,"sh":1.12,"swh":1.12},
    "mlv_sub": {"ws":0.90,"wg":0.90,"sh":1.05,"swh":1.05},
}

# ── Recovery mode modifiers (wind only — ws and wg) ──────────────────────────
RECOVERY_MOD = {
    "expendable": 1.00,
    "rtls":       0.88,
    "droneship":  0.93,
    "parachute":  0.90,
    "glide":      0.85,
}
WIND_PARAMS = {"ws", "wg"}   # recovery modifier applies only to these

# ── Default parameter weights (must sum to 1.0) ───────────────────────────────
# DEFAULT_WEIGHTS covers the five magnitude parameters only.
# Direction parameters (wdV, sdV, swdV) are excluded by default per
# Instruction 27B. When a user enables direction parameters in the Analysis
# section, DIRECTION_WEIGHTS provides their starting values before runtime
# renormalization.
# Last updated: Instruction 27B
DEFAULT_WEIGHTS = {
    "ws":  0.30,   # wind speed
    "wg":  0.26,   # wind gust
    "sh":  0.22,   # significant wave height
    "swh": 0.14,   # swell height
    "swp": 0.08,   # swell period
}

# Starting weights for the three direction parameters, applied only when the
# user explicitly enables them in the Analysis section. These are NOT part of
# DEFAULT_WEIGHTS; the engine renormalizes all active weights (magnitude + any
# included direction params) to sum to 1.0 at runtime, so these values are a
# starting point before renormalization.
# Last updated: Instruction 27B
DIRECTION_WEIGHTS = {
    "wdV":  0.04,
    "sdV":  0.03,
    "swdV": 0.03,
}

# ── Exceedance lookup (threshold/mean ratio → probability) ───────────────────
EXCEEDANCE_TABLE = [
    (2.0, 0.97),
    (1.5, 0.93),
    (1.2, 0.80),
    (1.0, 0.64),
    (0.8, 0.48),
    (0.6, 0.30),
    (0.4, 0.18),
    (0.0, 0.08),   # catch-all for ratio < 0.4
]

# ── Era weighting ─────────────────────────────────────────────────────────────
def era_weight(start_yr: int, end_yr: int) -> float:
    """
    Returns a confidence weight (0.0–1.0) for the selected date range.
    1960–present = full density 1°×1° ICOADS. Earlier = sparser ship observations.
    Sparser eras increase effective variability, reducing probability for tight thresholds.
    """
    mid = (start_yr + end_yr) / 2
    span = end_yr - start_yr + 1
    if mid >= 1960:
        base = 1.00
    elif mid >= 1925:
        base = 0.92
    elif mid >= 1900:
        base = 0.83
    else:
        base = 0.72
    bonus = min(0.05, (span - 10) / 200)
    return min(1.0, base + bonus)

# ── Voyage economics defaults ─────────────────────────────────────────────────
VOYAGE_DEFAULTS = {
    "platform_speed_kts":       6.0,
    "fuel_consumption_mt_day":  18.0,   # semi-sub tow typical
    "num_tugs":                 2,
    "weather_contingency_pct":  15.0,
}

# ── Platform contract codes ───────────────────────────────────────────────────
# Format: {CUSTOMER}_{VESSEL_CODE}_{MMDDYYYY}_{MMDDYYYY}
# e.g. LM1_0100_10012026_09302027
CONTRACT_CODE_PATTERN = re.compile(r'^[A-Z0-9]+_\d{4}_\d{8}_\d{8}$')


def validate_contract_code(code: str) -> bool:
    """
    Validate contract code format:
    {CUSTOMER}_{VESSEL_CODE}_{MMDDYYYY}_{MMDDYYYY}
    Example: LM1_0100_10012026_09302027. Returns True if valid.
    """
    return bool(CONTRACT_CODE_PATTERN.match(code.strip()))


# ── Project management constants ─────────────────────────────────────────────
PROJECT_STATUS_OPTIONS   = ["planning", "pending", "completed", "cancelled"]
CANDIDATE_STATUS_OPTIONS = ["candidate", "approved", "final", "rejected"]
ARCHIVABLE_STATUSES      = {"final", "rejected"}
ACCEPTED_DOCUMENT_EXTENSIONS = {
    ".pdf":  "PDF Document",
    ".docx": "Word Document",
    ".doc":  "Word Document (Legacy)",
    ".xlsx": "Excel Spreadsheet",
    ".xls":  "Excel Spreadsheet (Legacy)",
    ".png":  "PNG Image",
    ".jpg":  "JPEG Image",
    ".jpeg": "JPEG Image",
    ".txt":  "Text File",
    ".csv":  "CSV Data",
}
DOCS_DIR = BASE_DIR / "assets" / "project_documents"

# ── Gateway platform specs ────────────────────────────────────────────────────
GATEWAY_PLATFORMS = [
    {
        "name": "Gateway S",
        "hull_type": "semisub",
        "hull_motion_factor": 0.78,
        "dp_capable": True,
        "max_hs_operating_m": 2.5,
        "typical_depth_m": 500,
        "payload_class": "SLV",
        "notes": "Smallest Gateway variant. ABS AIP Dec 2025. MIT Sea Grant tested.",
    },
    {
        "name": "Gateway X",
        "hull_type": "semisub",
        "hull_motion_factor": 0.78,
        "dp_capable": True,
        "max_hs_operating_m": 3.5,
        "typical_depth_m": 800,
        "payload_class": "SLV/light MLV",
        "notes": "Primary MOU variant. Firefly Alpha / Lockheed Martin partnership 2026.",
    },
    {
        "name": "Gateway XL",
        "hull_type": "semisub",
        "hull_motion_factor": 0.78,
        "dp_capable": True,
        "max_hs_operating_m": 4.5,
        "typical_depth_m": 1200,
        "payload_class": "MLV",
        "notes": "Largest variant. Deepest draft. MLV-class payload.",
    },
]

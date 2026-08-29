"""
core/utils.py — Coordinate validation, unit conversion, and formatting.
All coordinate work in the application passes through here.

Convention enforced:
  +lat = North,  -lat = South
  +lon = East,   -lon = West
  WGS-84 decimal degrees
"""
import math
from config import LAT_MIN, LAT_MAX, LON_MIN, LON_MAX, MS_TO_KTS, KTS_TO_MS, LAT_BANDS


# ── Coordinate validation ────────────────────────────────────────────────────

def validate_lat(lat: float) -> float:
    """Validate latitude. Returns lat if valid, raises ValueError otherwise."""
    if not LAT_MIN <= lat <= LAT_MAX:
        raise ValueError(
            f"Invalid latitude {lat}. Must be {LAT_MIN}–{LAT_MAX}. "
            f"(+N, -S convention)"
        )
    return lat


def validate_lon(lon: float) -> float:
    """Validate longitude. Returns lon if valid, raises ValueError otherwise."""
    if not LON_MIN <= lon <= LON_MAX:
        raise ValueError(
            f"Invalid longitude {lon}. Must be {LON_MIN}–{LON_MAX}. "
            f"(+E, -W convention)"
        )
    return lon


def lat_dir(lat: float) -> str:
    return "N" if lat >= 0 else "S"


def lon_dir(lon: float) -> str:
    return "E" if lon >= 0 else "W"


def format_coord(lat: float, lon: float) -> str:
    """Format as '28.5000°N, 80.6000°W'."""
    return f"{abs(lat):.4f}°{lat_dir(lat)}, {abs(lon):.4f}°{lon_dir(lon)}"


def format_coord_dms(lat: float, lon: float) -> str:
    """Format as '28°30.00′N, 080°36.00′W'."""
    def _dms(deg: float) -> tuple:
        d = int(abs(deg))
        m = (abs(deg) - d) * 60
        return d, m
    ld, lm = _dms(lat)
    nd, nm = _dms(lon)
    return (
        f"{ld:02d}°{lm:05.2f}′{lat_dir(lat)}, "
        f"{nd:03d}°{nm:05.2f}′{lon_dir(lon)}"
    )


# ── Latitude band ────────────────────────────────────────────────────────────

def lat_to_band(lat: float) -> str:
    """
    Return ICOADS latitude band name from decimal latitude.
    Uses absolute value — works for N and S hemispheres.
    """
    a = abs(lat)
    for band, (lo, hi) in LAT_BANDS.items():
        if lo <= a < hi:
            return band
    return "polar"   # catches exactly 90°


def band_label(band: str) -> str:
    labels = {
        "equatorial": "Equatorial (0–10°)",
        "tropical":   "Tropical (10–30°)",
        "midlat":     "Mid-latitude (30–60°)",
        "polar":      "Polar (60–90°)",
    }
    return labels.get(band, band)


# ── Unit conversion ──────────────────────────────────────────────────────────

def ms_to_kts(ms: float) -> float:
    """Convert m/s to knots."""
    return ms * MS_TO_KTS


def kts_to_ms(kts: float) -> float:
    """Convert knots to m/s."""
    return kts * KTS_TO_MS


# ── Bounding box ─────────────────────────────────────────────────────────────

def bbox_from_center(lat: float, lon: float, radius_nm: float) -> dict:
    """
    Return a bounding box dict from a center point and radius in nautical miles.

    Returns:
        {'north': float, 'south': float, 'east': float, 'west': float}
        where N/S are lat in decimal degrees (+N/-S) and E/W are lon (+E/-W)

    NCEI API uses bbox format: "N,W,S,E" — use ncei_bbox() for that.
    """
    deg = radius_nm / 60.0   # 1 NM = 1/60 degree latitude (approximate)
    return {
        "north": min( 90.0, lat + deg),
        "south": max(-90.0, lat - deg),
        "east":  min( 180.0, lon + deg),
        "west":  max(-180.0, lon - deg),
    }


def ncei_bbox_str(lat: float, lon: float, radius_nm: float) -> str:
    """
    Return NCEI API bbox string in format 'N,W,S,E'.
    West and South may be negative (standard decimal degree convention).
    """
    bb = bbox_from_center(lat, lon, radius_nm)
    return f"{bb['north']:.4f},{bb['west']:.4f},{bb['south']:.4f},{bb['east']:.4f}"


# ── Great-circle distance ────────────────────────────────────────────────────

def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Great-circle distance in nautical miles between two points.
    Inputs in decimal degrees (+N/-S, +E/-W).
    """
    R = 3440.065   # Earth radius in nautical miles
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Initial bearing in degrees (0–360) from point 1 to point 2.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlam = math.radians(lon2 - lon1)
    x = math.sin(dlam) * math.cos(phi2)
    y = (math.cos(phi1) * math.sin(phi2)
         - math.sin(phi1) * math.cos(phi2) * math.cos(dlam))
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def intermediate_point(lat1: float, lon1: float,
                        lat2: float, lon2: float,
                        fraction: float) -> tuple:
    """
    Return the intermediate point at `fraction` (0.0–1.0) along the great
    circle from (lat1,lon1) to (lat2,lon2). Returns (lat, lon).
    """
    phi1 = math.radians(lat1)
    lam1 = math.radians(lon1)
    phi2 = math.radians(lat2)
    lam2 = math.radians(lon2)
    d_nm = haversine_nm(lat1, lon1, lat2, lon2)
    d_rad = math.radians(d_nm / 60.0)   # approximate angular distance
    a = math.sin((1 - fraction) * d_rad) / math.sin(d_rad)
    b = math.sin(fraction * d_rad) / math.sin(d_rad)
    x = a * math.cos(phi1) * math.cos(lam1) + b * math.cos(phi2) * math.cos(lam2)
    y = a * math.cos(phi1) * math.sin(lam1) + b * math.cos(phi2) * math.sin(lam2)
    z = a * math.sin(phi1)               + b * math.sin(phi2)
    lat_out = math.degrees(math.atan2(z, math.sqrt(x*x + y*y)))
    lon_out = math.degrees(math.atan2(y, x))
    return lat_out, lon_out


# ── Formatting helpers ───────────────────────────────────────────────────────

def fmt_nm(nm: float) -> str:
    return f"{nm:,.1f} NM"


def fmt_days(days: float) -> str:
    return f"{days:.1f} days"


def fmt_usd(usd: float) -> str:
    return f"${usd:,.0f}"


def fmt_prob(prob: float) -> str:
    return f"{round(prob * 100)}%"


def m_to_ft(meters: float) -> float:
    """Convert metres to feet."""
    return meters * 3.28084


def ft_to_m(feet: float) -> float:
    """Convert feet to metres."""
    return feet / 3.28084


def fmt_length(meters: float) -> str:
    """Format a length as '120.0 m (393.7 ft)'."""
    return f"{meters:.1f} m ({m_to_ft(meters):.1f} ft)"


def fmt_tonnage(tons: float) -> str:
    """Format tonnage with comma separator."""
    return f"{tons:,.0f}"


def generate_coord_code(lat: float, lon: float) -> str:
    """
    Generate a compact coordinate code from decimal degrees.
    Format: N32W061 (hemisphere + integer degrees; lon zero-padded to 3 digits).
    """
    validate_lat(lat)
    validate_lon(lon)
    lat_h = "N" if lat >= 0 else "S"
    lon_h = "E" if lon >= 0 else "W"
    return f"{lat_h}{int(abs(lat)):02d}{lon_h}{int(abs(lon)):03d}"


def month_name(month: int) -> str:
    """1-indexed month number to abbreviated name."""
    names = ["Jan","Feb","Mar","Apr","May","Jun",
             "Jul","Aug","Sep","Oct","Nov","Dec"]
    return names[month - 1] if 1 <= month <= 12 else str(month)


def open_local_path(path: str) -> None:
    """Open a local file/folder with the OS default application.

    Windows → os.startfile, macOS → ``open``, Linux → ``xdg-open``.
    Raises OSError / FileNotFoundError if the launcher cannot be started.
    """
    import os
    import subprocess
    import sys

    if not path:
        raise ValueError("path is empty")
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])

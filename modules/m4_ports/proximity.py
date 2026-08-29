"""
modules/m4_ports/proximity.py -- Nearest-port search using the WPI database.

Entry points:
    nearest_ports(site, n, min_depth_m, require_fuel) -> list[Port]
    search_ports(query, limit)                        -> list[Port]
    get_port(port_id)                                 -> Port | None
"""

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.database import get_connection
from core.models import Site, Port
from core.utils import haversine_nm, bearing_deg


def nearest_ports(
    site: Site,
    n: int = 5,
    min_depth_m: float = 10.0,
    require_fuel: bool = True,
) -> list[Port]:
    """
    Return the n nearest ports to site that meet depth and fuel criteria.

    Parameters
    ----------
    site          : Site with lat/lon set
    n             : number of ports to return
    min_depth_m   : minimum anchorage depth in metres (filters depth_anch_m)
    require_fuel  : if True, only ports with fuel_oil = 1 are considered

    Returns
    -------
    list[Port] sorted nearest-first, with distance_nm and bearing_deg populated.
    Ports with NULL depth_anch_m are excluded when min_depth_m > 0.
    """
    conn = get_connection()

    query = """
        SELECT id, wpi_number, port_name, country, lat, lon,
               harbor_size, max_vessel_size, depth_anch_m, fuel_oil, diesel
        FROM ports
        WHERE lat IS NOT NULL
          AND lon IS NOT NULL
    """
    params: list = []

    if min_depth_m > 0:
        query += " AND depth_anch_m >= ?"
        params.append(min_depth_m)

    if require_fuel:
        query += " AND fuel_oil = 1"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        return []

    candidates: list[tuple[float, Port]] = []
    for row in rows:
        port_lat = row["lat"]
        port_lon = row["lon"]
        dist = haversine_nm(site.lat, site.lon, port_lat, port_lon)
        brng = bearing_deg(site.lat, site.lon, port_lat, port_lon)

        port = Port(
            id              = row["id"],
            wpi_number      = row["wpi_number"] or "",
            port_name       = row["port_name"],
            country         = row["country"] or "",
            lat             = port_lat,
            lon             = port_lon,
            harbor_size     = row["harbor_size"] or "",
            max_vessel_size = row["max_vessel_size"] or "",
            depth_anch_m    = row["depth_anch_m"],
            fuel_oil        = bool(row["fuel_oil"]),
            diesel          = bool(row["diesel"]),
            distance_nm     = round(dist, 1),
            bearing_deg     = round(brng, 1),
        )
        candidates.append((dist, port))

    candidates.sort(key=lambda x: x[0])
    return [port for _, port in candidates[:n]]


_PORT_COLUMNS = """
    id, wpi_number, port_name, country, lat, lon,
    harbor_size, max_vessel_size, depth_anch_m, fuel_oil, diesel
"""


def _row_to_port(row) -> Port:
    return Port(
        id              = row["id"],
        wpi_number      = row["wpi_number"] or "",
        port_name       = row["port_name"],
        country         = row["country"] or "",
        lat             = row["lat"],
        lon             = row["lon"],
        harbor_size     = row["harbor_size"] or "",
        max_vessel_size = row["max_vessel_size"] or "",
        depth_anch_m    = row["depth_anch_m"],
        fuel_oil        = bool(row["fuel_oil"]),
        diesel          = bool(row["diesel"]),
    )


def search_ports(query: str = "", limit: int = 200) -> list[Port]:
    """
    Return ports whose name or country matches query, name-ordered.

    An empty query returns the first `limit` ports alphabetically, which is what
    the voyage-role pickers show before the user types anything.  No distance or
    bearing is populated -- these results are not relative to any site.
    """
    conn = get_connection()
    sql    = f"SELECT {_PORT_COLUMNS} FROM ports WHERE lat IS NOT NULL AND lon IS NOT NULL"
    params: list = []
    q = (query or "").strip()
    if q:
        sql += " AND (port_name LIKE ? OR country LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY port_name LIMIT ?"
    params.append(int(limit))

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [_row_to_port(row) for row in rows]


def get_port(port_id: int) -> Optional[Port]:
    """Return a single port by id, or None if it no longer exists."""
    if port_id is None:
        return None
    conn = get_connection()
    row = conn.execute(
        f"SELECT {_PORT_COLUMNS} FROM ports WHERE id = ?", (int(port_id),)
    ).fetchone()
    conn.close()
    return _row_to_port(row) if row else None

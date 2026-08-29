"""
scripts/import_wpi.py -- Import NGA World Port Index CSV into the ports table.

Download source:
    https://msi.nga.mil/Publications/WPI
Save the CSV to: data/wpi.csv  (resolved relative to this script file)

Handles both the current NGA MSI verbose-header format (2024+, depths in metres)
and the classic abbreviated-header format (depths in feet).  The script detects
which unit system is in use from the column header: if a depth column header
contains "(m)" the value is stored directly; otherwise it is converted from feet
(1 foot = 0.3048 m).

Supply fields accept "Yes"/"Y"/"L" as truthy -> INTEGER 1; everything else -> 0.
"""

import csv
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
WPI_CSV  = BASE_DIR / "data" / "wpi.csv"

sys.path.insert(0, str(BASE_DIR))

from core.database import get_connection, init_db

FEET_TO_M = 0.3048

# ---- Column name maps -------------------------------------------------------
# Each entry: (internal_key, [candidate CSV headers in priority order])
# All comparisons are made after lower-casing and collapsing underscores to spaces.
# Depth columns use the suffix (m) in the modern NGA format; the classic format
# omits it.  Both variants are listed so the resolver finds either.

_COLUMN_MAP = [
    ("wpi_number",    ["world port index number", "index_no", "wpi_no", "port number"]),
    ("port_name",     ["main port name", "port_name", "port name", "name"]),
    ("country",       ["country code", "country", "nation"]),
    ("lat",           ["latitude", "lat", "lat_deg"]),
    ("lon",           ["longitude", "long", "lon", "lng", "long_deg"]),
    ("harbor_size",   ["harbor size", "harbor_size", "harborsize"]),
    ("harbor_type",   ["harbor type", "harbor_type", "harbortype"]),
    ("shelter",       ["shelter afforded", "shelter"]),
    ("entry_tide",    ["entrance restriction - tide", "entry restriction - tide",
                       "entry_tide", "tide"]),
    ("max_vessel",    ["maximum vessel size", "max_vessel", "max vessel size",
                       "max_vessel_size", "maximum vessel length (m)"]),
    # Depth columns: modern "(m)" headers listed first; classic headers listed second.
    ("depth_anch",    ["anchorage depth (m)", "anchorage depth", "anch_depth",
                       "anchor depth", "depth_anch"]),
    ("depth_bar",     ["cargo pier depth (m)", "cargo pier depth",
                       "alongside depth (m)", "alongside depth",
                       "bar depth", "depth_bar", "moor_depth"]),
    ("depth_chan",    ["channel depth (m)", "channel depth", "chan_depth", "depth_chan"]),
    ("fuel_oil",      ["supplies - fuel oil", "fuel_oil", "fuel oil", "fuel"]),
    ("diesel",        ["supplies - diesel oil", "diesel_oil", "diesel oil", "diesel"]),
    ("ovhd_limits",   ["overhead limits", "ohd_limit", "ovhd_limits", "overhead"]),
    ("dry_dock",      ["dry dock", "dry_dock", "drydock"]),
    ("railway",       ["railway", "rail"]),
]


def _normalise(s: str) -> str:
    return s.lower().replace("_", " ").strip()


def _build_col_index(fieldnames: list[str]) -> tuple[dict, set]:
    """
    Map each internal key to the CSV column index.
    Also returns the set of internal keys whose matched header contains "(m)",
    meaning the value is already in metres and needs no conversion.
    """
    norm_to_idx = {_normalise(f): i for i, f in enumerate(fieldnames)}
    # Keep the original (lowered) header at each index for unit detection.
    idx_to_raw  = {i: f.lower() for i, f in enumerate(fieldnames)}

    col: dict[str, int | None] = {}
    already_metres: set[str] = set()

    for key, candidates in _COLUMN_MAP:
        matched_idx = None
        for c in candidates:
            n = _normalise(c)
            if n in norm_to_idx:
                matched_idx = norm_to_idx[n]
                break
        col[key] = matched_idx
        if matched_idx is not None and "(m)" in idx_to_raw.get(matched_idx, ""):
            already_metres.add(key)

    return col, already_metres


def _get(row: list, idx) -> str:
    if idx is None or idx >= len(row):
        return ""
    v = row[idx]
    return v.strip() if v else ""


def _yn_to_int(val: str) -> int:
    return 1 if val.strip().upper() in ("Y", "YES", "L") else 0


def _parse_depth(val: str, in_metres: bool):
    """Parse a depth string; convert from feet if not already in metres."""
    v = val.strip()
    if not v:
        return None
    try:
        num = float(v)
        if num <= 0:
            return None
        return round(num if in_metres else num * FEET_TO_M, 2)
    except ValueError:
        return None


def _latlon(val: str):
    v = val.strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def import_wpi(csv_path: Path = WPI_CSV) -> int:
    path = Path(csv_path).resolve()
    if not path.exists():
        print("ERROR: WPI CSV not found.")
        print(f"  Expected : {path}")
        print("  Download : https://msi.nga.mil/Publications/WPI")
        print("  Then save the file to that exact path and re-run.")
        sys.exit(1)

    init_db()
    conn = get_connection()

    # Detect delimiter (NGA downloads use commas; some regional exports use semicolons)
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
    delimiter = ";" if sample.count(";") > sample.count(",") else ","

    skipped = 0

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader     = csv.reader(f, delimiter=delimiter)
        fieldnames = next(reader)
        col, already_metres = _build_col_index(fieldnames)

        # Warn about unmapped critical columns
        for critical in ("port_name", "lat", "lon"):
            if col.get(critical) is None:
                print(f"WARNING: could not map '{critical}' -- check CSV headers")
                print(f"  First 20 headers: {fieldnames[:20]}")

        rows_to_insert = []
        for row in reader:
            if not row or all(c.strip() == "" for c in row):
                continue

            port_name = _get(row, col.get("port_name"))
            if not port_name:
                skipped += 1
                continue

            lat = _latlon(_get(row, col.get("lat")))
            lon = _latlon(_get(row, col.get("lon")))
            if lat is None or lon is None:
                skipped += 1
                continue

            rows_to_insert.append((
                _get(row, col.get("wpi_number")),
                port_name,
                _get(row, col.get("country")),
                lat,
                lon,
                _get(row, col.get("harbor_size")),
                _get(row, col.get("harbor_type")),
                _get(row, col.get("shelter")),
                _yn_to_int(_get(row, col.get("entry_tide"))),
                _get(row, col.get("max_vessel")),
                _parse_depth(_get(row, col.get("depth_anch")), "depth_anch" in already_metres),
                _parse_depth(_get(row, col.get("depth_bar")),  "depth_bar"  in already_metres),
                _parse_depth(_get(row, col.get("depth_chan")), "depth_chan" in already_metres),
                _yn_to_int(_get(row, col.get("fuel_oil"))),
                _yn_to_int(_get(row, col.get("diesel"))),
                _yn_to_int(_get(row, col.get("ovhd_limits"))),
                _get(row, col.get("dry_dock")),
                _get(row, col.get("railway")),
            ))

    with conn:
        conn.execute("DELETE FROM ports")
        conn.executemany(
            """
            INSERT INTO ports (
                wpi_number, port_name, country, lat, lon,
                harbor_size, harbor_type, shelter, entry_tide, max_vessel_size,
                depth_anch_m, depth_bar_m, depth_chan_m,
                fuel_oil, diesel, ovhd_limits, dry_dock, railway
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            rows_to_insert,
        )
        inserted = len(rows_to_insert)

    conn.close()

    print(f"Ports imported : {inserted:,}")
    if skipped:
        print(f"Rows skipped   : {skipped}  (missing name or coordinates)")
    print(f"Database       : gateway.db")
    return inserted


if __name__ == "__main__":
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else WPI_CSV
    import_wpi(csv_path)

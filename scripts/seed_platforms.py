"""
scripts/seed_platforms.py — Populate the platforms table from GATEWAY_PLATFORMS in config.py.
Safe to re-run: skips platforms that already exist by name.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import GATEWAY_PLATFORMS
from core.database import get_connection, init_db

INSERT_SQL = """
INSERT INTO platforms (
    name, hull_type, hull_motion_factor, dp_capable,
    max_hs_operating_m, typical_depth_m, payload_class, notes,
    draft_m, min_depth_m, abs_approval, first_deployment_yr, is_reference
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
"""

# Extended specs for Gateway reference variants
_GATEWAY_EXTRAS = {
    "Gateway S":  {
        "draft_m": 12.0, "min_depth_m": 60.0,
        # Operator-confirmed 2026-06-27
        "transit_draft_m": 2.591,       # 8.5 ft CONFIRMED
        "launch_draft_m":  4.267,       # 14.0 ft CONFIRMED
        "dp_class": 2,
        "dp_class_notes": "Assumed DP Class 2 — verify with classification society",
        "specs_verified": 1,
        "specs_verified_source": "Operator provided 2026-06-27",
        "specs_notes": (
            "Transit draft 8.5 ft and launch draft 14.0 ft confirmed by operator "
            "2026-06-27. min_depth_m = launch_draft × 1.5 = 6.401 m. "
            "DP Class 2 assumed pending class society confirmation."
        ),
    },
    "Gateway X":  {
        "draft_m": 15.0, "min_depth_m": 75.0,
        "transit_draft_m": None, "launch_draft_m": None,
        "dp_class": 0, "specs_verified": 0,
    },
    "Gateway XL": {
        "draft_m": 18.0, "min_depth_m": 90.0,
        "transit_draft_m": None, "launch_draft_m": None,
        "dp_class": 0, "specs_verified": 0,
    },
}
_ABS_APPROVAL = "ABS Approval in Principle December 2025"

# Pinned vessel codes (Pre-28B-1) — stable across DB wipes/reseeds.
_VESSEL_CODES = {
    "Gateway S":  "0100",
    "Gateway X":  "0101",
    "Gateway XL": "0102",
}


def _extras_update_sql(name: str, extras: dict) -> tuple[str, list]:
    """Build UPDATE SQL for the full extras dict including new vessel columns."""
    sets = [
        "draft_m=?", "min_depth_m=?", "abs_approval=?",
        "first_deployment_yr=?", "is_reference=?",
        "transit_draft_m=?", "launch_draft_m=?",
        "dp_class=?", "dp_class_notes=?",
        "specs_verified=?", "specs_verified_source=?", "specs_notes=?",
        "vessel_code=?",
    ]
    is_ref = 1 if name in _GATEWAY_EXTRAS else 0
    params = [
        extras.get("draft_m"),
        extras.get("min_depth_m", 50.0),
        _ABS_APPROVAL if name in _GATEWAY_EXTRAS else None,
        2027 if name in _GATEWAY_EXTRAS else None,
        is_ref,
        extras.get("transit_draft_m"),
        extras.get("launch_draft_m"),
        extras.get("dp_class", 0),
        extras.get("dp_class_notes"),
        extras.get("specs_verified", 0),
        extras.get("specs_verified_source"),
        extras.get("specs_notes"),
        _VESSEL_CODES.get(name),   # pinned code (None for non-reference platforms)
        name,  # WHERE clause
    ]
    sql = f"UPDATE platforms SET {', '.join(sets)} WHERE name=?"
    return sql, params


def seed():
    init_db()
    conn = get_connection()
    c = conn.cursor()

    existing = {row["name"] for row in c.execute("SELECT name FROM platforms")}
    inserted = 0
    skipped  = 0

    for p in GATEWAY_PLATFORMS:
        name = p["name"]
        extras = _GATEWAY_EXTRAS.get(name, {})
        if name in existing:
            sql, params = _extras_update_sql(name, extras)
            c.execute(sql, params)
            print(f"  UPDATE {name}  (is_reference={1 if name in _GATEWAY_EXTRAS else 0})")
            skipped += 1
        else:
            c.execute(INSERT_SQL, (
                name,
                p["hull_type"],
                p["hull_motion_factor"],
                int(p["dp_capable"]),
                p.get("max_hs_operating_m"),
                p.get("typical_depth_m"),
                p.get("payload_class", ""),
                p.get("notes", ""),
                extras.get("draft_m"),
                extras.get("min_depth_m", 50.0),
                _ABS_APPROVAL if name in _GATEWAY_EXTRAS else None,
                2027 if name in _GATEWAY_EXTRAS else None,
                1 if name in _GATEWAY_EXTRAS else 0,
            ))
            # Apply new vessel columns immediately after insert
            if extras:
                sql, params = _extras_update_sql(name, extras)
                c.execute(sql, params)
            inserted += 1
            row = c.execute(
                "SELECT * FROM platforms WHERE name = ?", (name,)
            ).fetchone()
            print(
                f"  INSERT id={row['id']}  name={row['name']}  "
                f"hull={row['hull_type']}  hmf={row['hull_motion_factor']}  "
                f"dp={bool(row['dp_capable'])}  "
                f"max_hs={row['max_hs_operating_m']}m  "
                f"depth={row['typical_depth_m']}m  "
                f"payload={row['payload_class']}  "
                f"is_ref={row['is_reference']}"
            )

    conn.commit()
    conn.close()

    print(f"\nDone — {inserted} inserted, {skipped} skipped. "
          f"Total Gateway platforms: {len(GATEWAY_PLATFORMS)}.")


if __name__ == "__main__":
    seed()

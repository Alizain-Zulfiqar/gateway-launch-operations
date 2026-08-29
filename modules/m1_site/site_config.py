"""
modules/m1_site/site_config.py — Site CRUD and bounding-box helpers.

Coordinate convention (enforced on Site creation via core/models.py):
  +lat = North,  -lat = South
  +lon = East,   -lon = West
  WGS-84 decimal degrees
"""
import sys
from pathlib import Path
from datetime import datetime
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.database import get_connection
from core.models import Site
from core.utils import bbox_from_center, generate_coord_code


# ── CRUD ─────────────────────────────────────────────────────────────────────

def save_site(site: Site) -> int:
    """
    Insert a Site into the sites table.
    Returns the new row id. Also sets site.id in place.
    """
    coord_code = generate_coord_code(site.lat, site.lon)
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO sites (name, lat, lon, bbox_nm, platform_id, notes, coord_code)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (site.name, site.lat, site.lon,
         site.bbox_nm, site.platform_id, site.notes, coord_code),
    )
    conn.commit()
    row_id = c.lastrowid
    conn.close()
    site.id = row_id
    site.coord_code = coord_code
    return row_id


def get_site(site_id: int) -> Site:
    """
    Retrieve a Site from the database by id.
    Raises ValueError if not found.
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM sites WHERE id = ?", (site_id,)
    ).fetchone()
    conn.close()
    if row is None:
        raise ValueError(f"No site with id={site_id}")
    return _row_to_site(row)


def list_sites() -> List[Site]:
    """Return all saved sites ordered by created_at descending."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM sites ORDER BY created_at DESC, id DESC"
    ).fetchall()
    conn.close()
    return [_row_to_site(r) for r in rows]


def update_site(site: Site) -> None:
    """
    Update an existing site's fields by site.id.
    Raises ValueError if site.id is None or the site does not exist.
    """
    if site.id is None:
        raise ValueError("Cannot update a site with no id")
    coord_code = generate_coord_code(site.lat, site.lon)
    conn = get_connection()
    try:
        affected = conn.execute(
            """
            UPDATE sites SET name=?, lat=?, lon=?, bbox_nm=?, platform_id=?, notes=?, coord_code=?
            WHERE id=?
            """,
            (site.name, site.lat, site.lon, site.bbox_nm,
             site.platform_id, site.notes, coord_code, site.id),
        ).rowcount
        conn.commit()
    finally:
        conn.close()
    if affected == 0:
        raise ValueError(f"No site with id={site.id}")
    site.coord_code = coord_code


def delete_site(site_id: int) -> None:
    """
    Delete a site by id.
    Raises ValueError if the site does not exist.
    Raises sqlite3.IntegrityError if the site is referenced by other tables
    (project_sites, reports, site_vehicles, voyage_schedules, etc — foreign
    keys are enforced). This function never cascades; use
    delete_site_cascade() if the caller has explicit authorization to
    remove a site's associations along with it.
    """
    conn = get_connection()
    try:
        affected = conn.execute(
            "DELETE FROM sites WHERE id = ?", (site_id,)
        ).rowcount
        conn.commit()
    finally:
        conn.close()
    if affected == 0:
        raise ValueError(f"No site with id={site_id}")


# Every table with a foreign key to sites(id) — kept in one place so
# delete_site_cascade() and get_site_associations() can't drift apart.
_SITE_REFERENCING_TABLES = (
    "project_sites",
    "project_site_status_history",
    "site_vehicles",
    "voyage_schedules",
    "analyses",
    "reports",
)


def get_site_associations(site_id: int) -> dict:
    """
    Return a count of rows in each table that references this site, keyed
    by table name. All-zero means the site can be deleted with plain
    delete_site(); any non-zero count means only delete_site_cascade() can
    remove it (delete_site() will raise sqlite3.IntegrityError).
    """
    conn = get_connection()
    try:
        return {
            table: conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE site_id=?", (site_id,)
            ).fetchone()[0]
            for table in _SITE_REFERENCING_TABLES
        }
    finally:
        conn.close()


def delete_site_cascade(site_id: int) -> dict:
    """
    Delete a site AND every row in other tables that references it
    (project_sites, project_site_status_history, site_vehicles,
    voyage_schedules, analyses, reports), then the site itself — as one
    atomic transaction (all-or-nothing).

    This deliberately breaks project_site_status_history's normal
    append-only rule ("never UPDATE or DELETE history rows") for the
    specific site being removed. That is an explicit exception scoped to
    this function only — no other code path deletes history rows, and no
    other site's history is touched.

    Report PDF files already written to disk are NOT deleted — only their
    `reports` table rows are removed. Any existing PDFs remain on disk,
    orphaned but harmless (not referenced by anything afterward).

    Raises ValueError if the site does not exist. Returns a dict of
    {table_name: rows_deleted} for the referencing tables, so callers can
    show the user what was removed.
    """
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM sites WHERE id=?", (site_id,)).fetchone()
        if row is None:
            raise ValueError(f"No site with id={site_id}")

        removed: dict = {}
        for table in _SITE_REFERENCING_TABLES:
            result = conn.execute(f"DELETE FROM {table} WHERE site_id=?", (site_id,))
            removed[table] = result.rowcount

        conn.execute("DELETE FROM sites WHERE id=?", (site_id,))
        conn.commit()
        return removed
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Bounding box ──────────────────────────────────────────────────────────────

def bbox_corners(site: Site) -> dict:
    """
    Return the bounding box for this site as a dict with keys:
      north, south, east, west  (decimal degrees, +N/-S, +E/-W)

    Uses site.bbox_nm as the radius. Delegates to core/utils.bbox_from_center().
    """
    return bbox_from_center(site.lat, site.lon, site.bbox_nm)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _row_to_site(row) -> Site:
    """Convert a sqlite3.Row from the sites table to a Site dataclass."""
    site = Site(
        lat=row["lat"],
        lon=row["lon"],
        name=row["name"] or "",
        bbox_nm=row["bbox_nm"] if row["bbox_nm"] is not None else 25.0,
        platform_id=row["platform_id"],
        notes=row["notes"] or "",
    )
    site.id = row["id"]
    site.created_at = (
        datetime.fromisoformat(row["created_at"])
        if row["created_at"] else None
    )
    try:
        site.coord_code = row["coord_code"]
    except (IndexError, KeyError):
        site.coord_code = None
    return site

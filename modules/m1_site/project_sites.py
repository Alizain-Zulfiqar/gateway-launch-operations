"""
modules/m1_site/project_sites.py — Project-site relationship management.

Write path for project_site_status_history (append-only) and project_sites
(current-state thin table). Never UPDATE or DELETE history rows — only INSERT.
"""
from __future__ import annotations

from typing import Optional

from core.database import get_connection
from config import ARCHIVABLE_STATUSES


# ── History write path ────────────────────────────────────────────────────────

def add_site_to_project(
    project_id: int,
    site_id: int,
    changed_by: str = "",
) -> int:
    """
    Add a site to a project with initial 'candidate' status.
    Returns the new history row id.
    Raises ValueError if the project-site pair already has any history.
    """
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM project_site_status_history "
            "WHERE project_id=? AND site_id=?",
            (project_id, site_id),
        ).fetchone()
        if existing:
            raise ValueError(
                f"Site {site_id} is already in project {project_id}"
            )

        c = conn.cursor()
        c.execute(
            """INSERT INTO project_site_status_history
               (project_id, site_id, status, changed_by)
               VALUES (?, ?, 'candidate', ?)""",
            (project_id, site_id, changed_by),
        )
        history_id = c.lastrowid

        c.execute(
            """INSERT OR REPLACE INTO project_sites
               (project_id, site_id, status, updated_at)
               VALUES (?, ?, 'candidate', CURRENT_TIMESTAMP)""",
            (project_id, site_id),
        )
        conn.commit()
        return history_id
    finally:
        conn.close()


def change_site_status(
    project_id: int,
    site_id: int,
    new_status: str,
    changed_by: str = "",
    approval_note: str = "",
    document_source_path: Optional[str] = None,
) -> int:
    """
    Insert a new history row for a status change.
    Copies attachment if document_source_path is provided.
    Updates the current-state project_sites row.
    Returns the new history row id.
    """
    document_path: Optional[str] = None
    if document_source_path:
        from core.file_attachments import copy_attachment
        result = copy_attachment(
            document_source_path,
            subfolder=f"project_{project_id}",
            prefix=f"site_{site_id}_{new_status}",
        )
        document_path = result["stored_path"]

    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """INSERT INTO project_site_status_history
               (project_id, site_id, status, changed_by, approval_note, document_path)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (project_id, site_id, new_status, changed_by, approval_note, document_path),
        )
        history_id = c.lastrowid

        c.execute(
            """INSERT OR REPLACE INTO project_sites
               (project_id, site_id, status, updated_at)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP)""",
            (project_id, site_id, new_status),
        )
        conn.commit()
        return history_id
    finally:
        conn.close()


# ── History read path ─────────────────────────────────────────────────────────

def get_site_history(
    project_id: int,
    site_id: int,
    include_archived: bool = False,
) -> list[dict]:
    """
    Return history rows for a site in a project, newest-first.
    Always includes the most recent row regardless of the archive flag.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT * FROM project_site_status_history
               WHERE project_id=? AND site_id=?
               ORDER BY id DESC""",
            (project_id, site_id),
        ).fetchall()

        result = []
        for i, row in enumerate(rows):
            # most recent (i==0) is always included
            if i == 0 or include_archived or not row["archived"]:
                result.append(dict(row))
        return result
    finally:
        conn.close()


def get_current_status(project_id: int, site_id: int) -> dict | None:
    """Return the current-state row for a project-site pair, or None."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM project_sites WHERE project_id=? AND site_id=?",
            (project_id, site_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_project_sites(
    project_id: int,
    status_filter: Optional[str | list[str]] = None,
) -> list[dict]:
    """
    Return current-state rows for all sites in a project, joined with site info.
    Optionally filter by status; accepts a single string or a list of strings.
    Includes platform_name and history_count in each result row.
    """
    # Normalise filter to list or None
    if isinstance(status_filter, str):
        statuses: Optional[list[str]] = [status_filter]
    else:
        statuses = list(status_filter) if status_filter else None

    conn = get_connection()
    try:
        base_select = """
            SELECT ps.*, s.name AS site_name, s.lat, s.lon, s.coord_code, s.bbox_nm,
                   p.name AS platform_name,
                   (SELECT COUNT(*) FROM project_site_status_history h
                    WHERE h.project_id = ps.project_id AND h.site_id = ps.site_id
                   ) AS history_count
            FROM project_sites ps
            JOIN sites s ON s.id = ps.site_id
            LEFT JOIN platforms p ON p.id = s.platform_id
        """
        if statuses:
            placeholders = ",".join("?" * len(statuses))
            rows = conn.execute(
                f"{base_select} WHERE ps.project_id=? AND ps.status IN ({placeholders})"
                " ORDER BY ps.updated_at DESC",
                (project_id, *statuses),
            ).fetchall()
        else:
            rows = conn.execute(
                f"{base_select} WHERE ps.project_id=? ORDER BY ps.updated_at DESC",
                (project_id,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Removal ──────────────────────────────────────────────────────────────────

def remove_site_from_project(project_id: int, site_id: int) -> None:
    """
    Unlink a site from a project (deletes the current-state project_sites row
    only). Does NOT delete the site itself or the append-only
    project_site_status_history audit trail — history is preserved for record
    -keeping even after the site is removed from the project's candidate list.
    """
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM project_sites WHERE project_id=? AND site_id=?",
            (project_id, site_id),
        )
        conn.commit()
    finally:
        conn.close()


# ── Archiving ─────────────────────────────────────────────────────────────────

def archive_site_history(project_id: int, site_id: int) -> int:
    """
    Archive all history rows except the most recent for a project-site pair.
    Guard: raises ValueError if current status is not in ARCHIVABLE_STATUSES.
    Returns the count of rows archived.
    """
    current = get_current_status(project_id, site_id)
    if not current or current["status"] not in ARCHIVABLE_STATUSES:
        status = current["status"] if current else None
        raise ValueError(
            f"Cannot archive: current status '{status}' "
            f"is not in {ARCHIVABLE_STATUSES}"
        )

    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id FROM project_site_status_history
               WHERE project_id=? AND site_id=? AND archived=0
               ORDER BY id DESC""",
            (project_id, site_id),
        ).fetchall()

        ids_to_archive = [r["id"] for r in rows[1:]]  # all except most recent
        if ids_to_archive:
            placeholders = ",".join("?" * len(ids_to_archive))
            conn.execute(
                f"UPDATE project_site_status_history SET archived=1 "
                f"WHERE id IN ({placeholders})",
                ids_to_archive,
            )
            conn.commit()
        return len(ids_to_archive)
    finally:
        conn.close()


def unarchive_site_history(project_id: int, site_id: int) -> int:
    """
    Unarchive all archived history rows for a project-site pair.
    Returns the count of rows unarchived.
    """
    conn = get_connection()
    try:
        result = conn.execute(
            """UPDATE project_site_status_history SET archived=0
               WHERE project_id=? AND site_id=? AND archived=1""",
            (project_id, site_id),
        )
        conn.commit()
        return result.rowcount
    finally:
        conn.close()


def archive_project_history(project_id: int) -> dict:
    """
    Archive history for all archivable sites in a project.
    Skips (does not error) sites whose current status is not in ARCHIVABLE_STATUSES.
    Returns {'archived_sites', 'skipped_sites', 'total_rows_archived'}.
    """
    sites = list_project_sites(project_id)
    archived_sites = 0
    skipped_sites = 0
    total_rows_archived = 0

    for site in sites:
        if site["status"] in ARCHIVABLE_STATUSES:
            rows = archive_site_history(project_id, site["site_id"])
            total_rows_archived += rows
            archived_sites += 1
        else:
            skipped_sites += 1

    return {
        "archived_sites": archived_sites,
        "skipped_sites": skipped_sites,
        "total_rows_archived": total_rows_archived,
    }

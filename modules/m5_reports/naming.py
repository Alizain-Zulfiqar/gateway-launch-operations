"""
modules/m5_reports/naming.py — Report filename generation and DB registration.
"""
from __future__ import annotations

import re
from datetime import date as _date, datetime, timezone
from typing import Optional


def sanitize(text: str) -> str:
    """Strip chars unsafe for Windows filenames; join words CamelCase (first-letter-only)."""
    cleaned = re.sub(r'[<>:"/\\|?*]', '', text)
    words = cleaned.strip().split()
    return ''.join(w[0].upper() + w[1:] if w else '' for w in words)


def next_sequence_number(
    report_type: str,
    project_id: Optional[int],
    site_id: int,
) -> int:
    """Return the next unused sequence number scoped to (project_id, type) or (site_id, type)."""
    from core.database import get_connection
    conn = get_connection()
    try:
        if project_id is not None:
            row = conn.execute(
                "SELECT MAX(sequence_number) FROM reports "
                "WHERE report_type=? AND project_id=?",
                (report_type, project_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT MAX(sequence_number) FROM reports "
                "WHERE report_type=? AND project_id IS NULL AND site_id=?",
                (report_type, site_id),
            ).fetchone()
        max_seq = row[0] if row and row[0] is not None else 0
        return max_seq + 1
    finally:
        conn.close()


def build_report_filename(
    report_type: str,
    site,          # Site dataclass
    project=None,  # Optional[Project] dataclass
) -> dict:
    """
    Build a structured report filename.

    With project:   {CODE}_{SiteName}-{coord}_{start}-{end}_{A|V}{NNN}.pdf
    Without project: UNASSIGNED_{SiteName}-{coord}_{date}_{A|V}{NNN}.pdf

    Returns dict: filename, sequence_number, type_prefix.
    """
    from core.utils import generate_coord_code

    type_prefix = "A" if report_type == "analysis" else "V"
    coord_code = site.coord_code or generate_coord_code(site.lat, site.lon)
    site_part = f"{sanitize(site.name)}-{coord_code}"

    if project is not None:
        seq = next_sequence_number(report_type, project.id, site.id)
        start = project.launch_date_start
        end = project.launch_date_end
        if isinstance(start, str):
            start = _date.fromisoformat(start)
        if isinstance(end, str):
            end = _date.fromisoformat(end)
        date_range = f"{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}"
        filename = f"{project.code_name}_{site_part}_{date_range}_{type_prefix}{seq:03d}.pdf"
    else:
        seq = next_sequence_number(report_type, None, site.id)
        gen_date = datetime.now(timezone.utc).strftime("%Y%m%d")
        filename = f"UNASSIGNED_{site_part}_{gen_date}_{type_prefix}{seq:03d}.pdf"

    return {
        "filename": filename,
        "sequence_number": seq,
        "type_prefix": type_prefix,
    }


def record_report(
    report_type: str,
    filename: str,
    file_path: str,
    sequence_number: int,
    site_id: Optional[int],
    project_id: Optional[int],
) -> None:
    """Insert a completed report into the reports table. Silently skips if site_id is None."""
    if site_id is None:
        return
    try:
        from core.database import get_connection
        conn = get_connection()
        conn.execute(
            """INSERT OR IGNORE INTO reports
               (project_id, site_id, report_type, filename, sequence_number, file_path)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (project_id, site_id, report_type, filename, sequence_number, file_path),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

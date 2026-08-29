"""
scripts/backfill_coord_codes.py — Backfill coord_code for existing sites.
Run once after deploying the coord_code migration.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import get_connection, init_db
from core.utils import generate_coord_code


def backfill() -> None:
    init_db()
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, lat, lon FROM sites WHERE coord_code IS NULL"
    ).fetchall()

    if not rows:
        print("No sites to backfill.")
        conn.close()
        return

    updated = 0
    for row in rows:
        code = generate_coord_code(row["lat"], row["lon"])
        conn.execute(
            "UPDATE sites SET coord_code=? WHERE id=?",
            (code, row["id"])
        )
        updated += 1

    conn.commit()
    conn.close()
    print(f"Backfilled coord_code for {updated} site(s).")


if __name__ == "__main__":
    backfill()

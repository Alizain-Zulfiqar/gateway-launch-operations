"""
scripts/migrate_27a.py — Instruction Set 27A database migration.

Creates a timestamped backup, then wipes all site/project/analysis data
inside a single transaction, applies the 27A schema additions, and sets
the direction-parameter exclusion defaults.

This script is the ONLY file that performs the database wipe. It must be
run explicitly by the user:

    py scripts/migrate_27a.py            # execute the migration
    py scripts/migrate_27a.py --dry-run  # backup + preview only, no changes

It must NOT run automatically on app startup or be called from any other
module.
"""
import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import BASE_DIR, DB_PATH
from core.database import get_connection, init_db

# Deletion order respects foreign keys (children before parents).
TABLES_IN_ORDER = [
    "project_site_status_history",
    "project_sites",
    "site_vehicles",
    "voyage_schedules",
    "analyses",
    "reports",
    "expenses",
    "session_state",
    "sites",
]


def create_backup() -> Path:
    """Copy the live DB into backups/ with a timestamped name. Abort on failure."""
    try:
        backups_dir = BASE_DIR / "backups"
        backups_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backups_dir / f"gateway_backup_{timestamp}.db"

        shutil.copy2(DB_PATH, backup_path)
        print(f"Backup created: {backup_path}")
        print(f"Backup size: {backup_path.stat().st_size:,} bytes")
        return backup_path
    except Exception as e:
        print(f"ERROR: Backup failed — {e}")
        print("Aborting. No changes were made to the database.")
        sys.exit(1)


def table_exists(conn, table: str) -> bool:
    return conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()[0] > 0


def dry_run(backup_path: Path) -> None:
    """Print every statement the wipe would execute; change nothing."""
    print("DRY RUN — no changes will be made.\n")
    print(f"Backup created: {backup_path}\n")

    conn = get_connection()
    try:
        for table in TABLES_IN_ORDER:
            if table_exists(conn, table):
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                print(f"Would DELETE {count} rows from {table}")
            else:
                print(f"Would skip {table} (table does not exist yet)")
        print("\nWould apply 27A schema additions via init_db()")
        print("Would INSERT OR REPLACE settings: "
              "exclude_wind_dir='1', exclude_sea_dir='1', exclude_swell_dir='1'")
    finally:
        conn.close()

    print("\nRun without --dry-run to execute.")


def wipe(backup_path: Path) -> None:
    """Delete all rows from TABLES_IN_ORDER inside a single transaction."""
    conn = get_connection()
    conn.isolation_level = None  # explicit transaction control
    try:
        conn.execute("BEGIN TRANSACTION")

        for table in TABLES_IN_ORDER:
            if table_exists(conn, table):
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                conn.execute(f"DELETE FROM {table}")
                print(f"Cleared {count} rows from {table}")
            else:
                print(f"Skipped {table} (table does not exist yet)")

        conn.execute("COMMIT")
        print("\nWipe completed successfully.")
        print(f"Backup available at: {backup_path}")
        print("To restore: copy the backup file back to gateway.db")

    except Exception as e:
        conn.execute("ROLLBACK")
        print(f"\nERROR: {e}")
        print("Transaction rolled back. Database unchanged.")
        print(f"Backup still available at: {backup_path}")
        raise
    finally:
        conn.close()


def migrate_settings() -> None:
    # Direction parameter UI checkbox defaults updated in Instruction 27B.
    # Config DEFAULT_WEIGHTS redistribution also handled in Instruction 27B.
    # These settings rows ensure the DB state is correct before 27B runs.
    conn = get_connection()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO settings (key, value) VALUES
            ('exclude_wind_dir', '1'),
            ('exclude_sea_dir', '1'),
            ('exclude_swell_dir', '1')
        """)
        conn.commit()
        print("Direction parameter exclusion defaults set "
              "(exclude_wind_dir, exclude_sea_dir, exclude_swell_dir = '1').")
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Instruction Set 27A migration")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview the wipe without making any changes "
                             "(the backup is still created)")
    args = parser.parse_args()

    backup_path = create_backup()

    if args.dry_run:
        dry_run(backup_path)
        return

    wipe(backup_path)

    print("\nApplying 27A schema additions…")
    init_db()
    migrate_settings()
    print("\nMigration 27A complete.")


if __name__ == "__main__":
    main()

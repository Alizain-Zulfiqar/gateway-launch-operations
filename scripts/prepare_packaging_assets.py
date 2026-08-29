#!/usr/bin/env python3
"""
Refresh packaging/ share files from the developer machine.

Copies Copernicus CDS credentials and optional .env into packaging/ so they
ship with the repository for clone-and-run teammates. Run before committing
when keys change:

    python scripts/prepare_packaging_assets.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "packaging"


def main() -> int:
    PACK.mkdir(parents=True, exist_ok=True)

    home_rc = Path.home() / ".cdsapirc"
    dst_rc = PACK / ".cdsapirc"
    if home_rc.is_file():
        shutil.copy2(home_rc, dst_rc)
        print(f"Updated {dst_rc.relative_to(ROOT)} from {home_rc}")
    elif dst_rc.is_file():
        print(f"Keeping existing {dst_rc.relative_to(ROOT)}")
    else:
        print("WARNING: No ~/.cdsapirc found and packaging/.cdsapirc is missing.")
        print("         ERA5 downloads will fail until credentials are added.")

    for src_name in (".env",):
        src = ROOT / src_name
        dst = PACK / src_name
        if src.is_file():
            shutil.copy2(src, dst)
            print(f"Updated {dst.relative_to(ROOT)}")

    db = ROOT / "gateway.db"
    seed = PACK / "gateway.db.seed"
    if db.is_file():
        shutil.copy2(db, seed)
        print(f"Refreshed {seed.relative_to(ROOT)} from gateway.db")
    elif seed.is_file():
        print(f"Keeping existing {seed.relative_to(ROOT)}")

    print("\nDone. Commit packaging/ when sharing updated credentials or seed DB.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

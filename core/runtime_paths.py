"""
core/runtime_paths.py — Path resolution for dev runs vs PyInstaller builds.

When frozen, writable data (database, reports, backups) lives next to the
executable. Read-only bundled resources are resolved from PyInstaller's
``_MEIPASS`` / ``_internal`` directory.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Writable application root (project root in dev, exe folder when frozen)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundle_dir() -> Path:
    """Directory where PyInstaller unpacks bundled read-only files."""
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        internal = app_dir() / "_internal"
        if internal.is_dir():
            return internal
    return app_dir()


def resource_path(*parts: str) -> Path:
    """Resolve a bundled resource, falling back to the app directory."""
    rel = Path(*parts)
    for root in (bundle_dir(), app_dir()):
        candidate = root / rel
        if candidate.exists():
            return candidate
    return app_dir() / rel


def _copy_if_missing(src: Path, dst: Path) -> None:
    if src.is_file() and not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _bundled_cdsapirc() -> Path | None:
    for candidate in (
        app_dir() / "packaging" / ".cdsapirc",
        app_dir() / ".cdsapirc",
        bundle_dir() / ".cdsapirc",
    ):
        if candidate.is_file():
            return candidate
    return None


def _bundled_dotenv() -> Path | None:
    for candidate in (
        app_dir() / "packaging" / ".env",
        app_dir() / ".env",
        bundle_dir() / ".env",
    ):
        if candidate.is_file():
            return candidate
    return None


def configure_dev_runtime() -> None:
    """First-run setup for clone-and-run development (Mac / Windows / Linux)."""
    if is_frozen():
        return

    base = app_dir()
    (base / "reports").mkdir(parents=True, exist_ok=True)
    (base / "backups").mkdir(parents=True, exist_ok=True)
    (base / "assets").mkdir(parents=True, exist_ok=True)

    mpl_dir = base / ".matplotlib_cache"
    mpl_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(mpl_dir))

    cds = _bundled_cdsapirc()
    if cds is not None:
        os.environ.setdefault("CDSAPI_RC", str(cds))

    dotenv_path = _bundled_dotenv()
    if dotenv_path is not None:
        try:
            from dotenv import load_dotenv
            load_dotenv(dotenv_path, override=False)
        except ImportError:
            pass

    db_dst = base / "gateway.db"
    if not db_dst.exists():
        for seed_name in ("gateway.db.seed", "gateway.db"):
            seed = base / "packaging" / seed_name
            if seed.is_file():
                shutil.copy2(seed, db_dst)
                break


def configure_frozen_runtime() -> None:
    """One-time bootstrap for PyInstaller builds (safe to call in dev — no-op)."""
    if not is_frozen():
        return

    base = app_dir()
    internal = bundle_dir()

    for folder in ("reports", "backups", "assets", "data", ".matplotlib_cache"):
        (base / folder).mkdir(parents=True, exist_ok=True)

    mpl_dir = base / ".matplotlib_cache"
    os.environ.setdefault("MPLCONFIGDIR", str(mpl_dir))

    # Copernicus CDS credentials — prefer a file beside the .exe.
    for src in (internal / ".cdsapirc", base / ".cdsapirc"):
        if src.is_file():
            dst = base / ".cdsapirc"
            _copy_if_missing(src, dst)
            os.environ["CDSAPI_RC"] = str(dst if dst.exists() else src)
            break

    # Optional .env (non-CDS secrets / overrides).
    for src in (internal / ".env", base / ".env"):
        if src.is_file():
            dst = base / ".env"
            _copy_if_missing(src, dst)
            break

    # Seed database on first launch if the build included one.
    db_dst = base / "gateway.db"
    for seed_name in ("gateway.db", "gateway.db.seed"):
        seed = internal / seed_name
        if seed.is_file():
            _copy_if_missing(seed, db_dst)
            break

    # World Port Index CSV (read-only reference data).
    wpi_dst = base / "data" / "wpi.csv"
    wpi_src = internal / "data" / "wpi.csv"
    if wpi_src.is_file() and not wpi_dst.exists():
        wpi_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(wpi_src, wpi_dst)

    # Logo / static assets — copy tree once if missing beside exe.
    assets_src = internal / "assets"
    assets_dst = base / "assets"
    if assets_src.is_dir() and not (assets_dst / "seagate_space_logo.png").exists():
        if assets_dst.exists():
            for item in assets_src.iterdir():
                target = assets_dst / item.name
                if item.is_dir():
                    shutil.copytree(item, target, dirs_exist_ok=True)
                elif not target.exists():
                    shutil.copy2(item, target)
        else:
            shutil.copytree(assets_src, assets_dst, dirs_exist_ok=True)


def bootstrap_runtime() -> None:
    """Call once at process start before database / CDS clients initialize."""
    if is_frozen():
        configure_frozen_runtime()
    else:
        configure_dev_runtime()

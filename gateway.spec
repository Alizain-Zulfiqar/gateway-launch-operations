# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — Gateway Launch Operations (Windows desktop build).

Build on Windows (Python 3.11–3.14):
    python scripts/prepare_packaging_assets.py
    build_windows.bat

Output: dist/GatewayLaunch/GatewayLaunch.exe (+ _internal folder)
Zip dist/GatewayLaunch and share the folder with testers.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH)

block_cipher = None

datas = [
    (str(ROOT / "assets"), "assets"),
    (str(ROOT / "data" / "wpi.csv"), "data"),
]

for optional in (".cdsapirc", ".env", "gateway.db.seed"):
    src = ROOT / "packaging" / optional
    if src.is_file():
        datas.append((str(src), "."))

binaries = []
hiddenimports = collect_submodules("modules")
hiddenimports += [
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "matplotlib.backends.backend_qtagg",
    "matplotlib.backends.backend_qt",
    "netCDF4",
    "xarray",
    "scipy.special._cdflib",
    "cdsapi",
    "ecmwf.datastores.legacy_client",
    "lxml.etree",
    "lxml._elementpath",
]

for pkg in ("matplotlib", "PyQt6", "scipy", "netCDF4"):
    try:
        tmp = collect_all(pkg)
        datas += tmp[0]
        binaries += tmp[1]
        hiddenimports += tmp[2]
    except Exception:
        pass

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "pytest_cov"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GatewayLaunch",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="GatewayLaunch",
)

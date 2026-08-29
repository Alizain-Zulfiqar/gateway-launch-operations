# Gateway Launch Operations

Desktop app for offshore launch site analysis and maritime mission planning (PyQt6 + SQLite).

## Quick start (Mac or Windows)

1. **Install [Python 3.11+](https://www.python.org/downloads/)** if you do not already have it.
2. **Download this repository** (green **Code → Download ZIP**, or `git clone`).
3. **Run the launcher for your OS** — first launch creates a virtual environment and installs dependencies automatically.

| Platform | What to run |
|----------|-------------|
| **macOS** | Double-click **`Run Gateway.command`**, or in Terminal: `./run_mac.sh` |
| **Windows** | Double-click **`runapp.bat`** |

The app window opens after the first-run setup finishes (may take a few minutes while packages install).

### Copernicus / ERA5 credentials

This repository includes **shared API credentials** under `packaging/.cdsapirc` so teammates do not need their own Copernicus CDS account for ERA5 weather downloads. The launchers wire those credentials automatically.

> **Security:** Anyone with access to this repo can use those credentials. Keep the repository **private** on GitHub unless you intend to rotate the key after sharing.

Optional `.env` overrides can be placed in `packaging/.env` (loaded automatically if present).

### First-time database

On first run, if `gateway.db` is missing, the app copies `packaging/gateway.db.seed` (sample sites, vehicles, and ports). Your own saves stay in `gateway.db` locally and are not committed.

---

## Developers

```bash
# Refresh bundled credentials / seed DB before committing updates
python scripts/prepare_packaging_assets.py

# Run tests (after venv exists)
./run_mac.sh test          # macOS / Linux
runapp.bat test            # Windows

# Standalone Windows build (no Python required for end users)
build_windows.bat          # → dist/GatewayLaunch/
```

See **`CLAUDE.md`** for architecture, modules, and operational notes.

## Requirements

- Python **3.11+** (3.14 tested on macOS)
- Network access for NDBC, NCEI, ERA5, and marine forecast APIs
- ~500 MB disk space for the virtual environment

## Project layout

```
main.py              Application entry
config.py            Constants and defaults
core/                Database, models, utilities
modules/             Analysis, weather, ports, reports
ui/                  PyQt6 desktop interface
packaging/           Bundled .cdsapirc, optional .env, gateway.db.seed
run_mac.sh           macOS / Linux launcher
Run Gateway.command  macOS double-click launcher
runapp.bat           Windows launcher
```

## License / branding

Seagate Space Corporation — internal mission planning tool.

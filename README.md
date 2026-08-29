# Gateway Launch Operations

Desktop app for offshore launch site analysis and maritime mission planning (PyQt6 + SQLite).

## Quick start (Mac or Windows)

1. **Install [Python 3.11+](https://www.python.org/downloads/)** if you do not already have it.
2. **Download this repository** (green **Code → Download ZIP**, or `git clone`).
3. **Run the launcher for your OS** — first launch creates a virtual environment and installs dependencies automatically.

| Platform | What to run |
|----------|-------------|
| **macOS** | **Terminal (recommended):** see [macOS Gatekeeper note](#macos-downloaded-from-github) below, then `./run_mac.sh` |
| **macOS** | Or double-click **`Run Gateway.command`** after removing quarantine once |
| **Windows** | Double-click **`runapp.bat`** |

The app window opens after the first-run setup finishes (may take a few minutes while packages install).

### macOS (downloaded from GitHub)

Apple may block **`Run Gateway.command`** with *“could not verify … is free of malware”* — that is normal for unsigned scripts from the internet, not a virus warning about this project.

**Use Terminal (easiest):**

1. Open **Terminal** (Applications → Utilities → Terminal).
2. Go to the folder where you unzipped or cloned the repo, for example:
   ```bash
   cd ~/Downloads/gateway-launch-operations
   ```
3. Run:
   ```bash
   xattr -dr com.apple.quarantine .
   chmod +x run_mac.sh
   ./run_mac.sh
   ```

The first command removes Apple’s download quarantine. `./run_mac.sh` creates the Python environment and starts the app.

**To use double-click later:** after step 3 succeeds once, **`Run Gateway.command`** usually opens normally. If not, right-click it → **Open** → **Open** (confirm once).

**Alternative:** System Settings → **Privacy & Security** → scroll to the blocked app → **Open Anyway**.

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

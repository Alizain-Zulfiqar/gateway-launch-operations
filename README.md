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

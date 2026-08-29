# Gateway Launch Operations — CLAUDE.md

## Project overview

Python 3.14 / PyQt6 6.11 desktop application for offshore launch site analysis
and maritime mission planning. SQLite database, no ORM, no external DB server.

## Environment

- **Python**: 3.14.6
- **UI**: PyQt6 6.11.0
- **Database**: SQLite via `core/database.py` (`init_db()` on first launch)
- **PDF**: fpdf2
- **Platform**: Windows 11

## Security rules — never violate

1. No hardcoded API keys — always use `.env` via `python-dotenv`
2. Never commit `.env` — it contains the ERA5 CDS key (credentials in `~/.cdsapirc`)
3. SQLite only — no ORM, no PostgreSQL, no external DB server
4. Hull motion factor applies **only** to `sh, swh, swp` — NOT to wind parameters
5. Recovery modifier applies **only** to `ws, wg` — NOT to sea state parameters
6. NDBC `.spec` files are not universal — always check availability before use
7. Coordinate convention: `+lat=N, -lat=S, +lon=E, -lon=W` — validate at every entry point

## Coordinate convention (WGS-84 decimal degrees)

```
+Latitude  = North   −Latitude  = South
+Longitude = East    −Longitude = West
```

Validated at every UI entry point and DB write. Never store in any other format.

## Assets

```
gateway_app/
└── assets/
    └── seagate_space_logo.png   ← Seagate Space branding (PNG, horizontal full-colour)
```

- `config.LOGO_PATH` points to this file
- `config.logo_available()` returns `bool` — all logo consumers check this before loading
- `core/database.init_db()` creates `assets/` if missing
- Fallback to text branding if file is absent — app must never crash due to missing logo
- Source file: `SEAGATE_SPACE_HORIZONTAL_LOGO_FULL_COLOR_BLUE_RGB.png`

## Dark theme palette

| Role             | Hex       |
|------------------|-----------|
| Background       | `#0f1923` |
| Widget bg        | `#1a2233` |
| Accent           | `#2563eb` |
| Text             | `#e2e8f0` |
| Bright text      | `#f1f5f9` |
| Secondary text   | `#94a3b8` |
| GO bg / fg       | `#14532d` / `#86efac` |
| MARGINAL bg / fg | `#422006` / `#fde68a` |
| NO-GO bg / fg    | `#450a0a` / `#fca5a5` |

## Key modules

Reflects the actual file tree as of the Pre-28 audit (2026-07-02). Every path
below EXISTS on disk. Planned-but-absent paths are tracked in the "Pre-28 audit"
section further down — do not delete those.

Entry point / core:

| Path | Purpose |
|------|---------|
| `main.py` | Application entry point — builds QApplication + `GatewayMainWindow` |
| `config.py` | App-wide constants, paths, climate tables, `DEFAULT_WEIGHTS` / `DIRECTION_WEIGHTS` |
| `core/database.py` | Schema creation, `get_connection()`, `ALTER TABLE` migration loop |
| `core/models.py` | Dataclasses: `Site`, `Vehicle`, `Platform`, `AnalysisResult`, `Project`, `Port`, …; voyage cost model (`VoyageLeg`, `VesselParams`, `PortFees`, `VesselCostLine`, `VoyageCostBreakdown`) plus its `PORT_ROLES` / `FEE_CATEGORIES` / `VESSEL_KEYS` vocabularies |
| `core/utils.py` | Coordinate validation, unit conversion, formatting, `generate_coord_code()` |
| `core/settings.py` | Persistent `settings` + `session_state` get/set helpers |
| `core/file_attachments.py` | Document validate/copy/open for project documents (Set 25) |

Modules (analysis pipeline):

| Path | Purpose |
|------|---------|
| `modules/m1_site/site_config.py` | Site CRUD + bounding-box helpers (`list_sites`, …) |
| `modules/m1_site/project_sites.py` | Project-site relationship management (write/read/archive) |
| `modules/m1_site/contracts.py` | Contract hierarchy traversal + vessel pre-check gate (Pre-28B-1) |
| `modules/m2_weather/ndbc.py` | NDBC station discovery, met/spec fetch, multi-station fetch (Set 22) |
| `modules/m2_weather/ndbc_history.py` | NaN tracking, `compute_period_statistics()`, `aggregate_station_statistics()` |
| `modules/m2_weather/data_manager.py` | Weather source selection + site weather summary; `_fetch_historical()` now also aggregates NCEI wave/swell fields into `sh`/`sdV`/`swdV` (Set 39), gated by a `NCEI_MAX_MONTHS` latency safety cap — see "NCEI historical data" section below |
| `modules/m2_weather/ncei.py` | NCEI Data Service API (historical wind, wave height, wave direction, swell height, swell direction — Set 39); `get_cached_month()`/`save_cached_month()` local cache helpers (Set 41) |
| `modules/m2_weather/era5.py` | ERA5 reanalysis + WaveWatch III swell retrieval |
| `modules/m2_weather/forecast.py` | Live NWS/Open-Meteo fetch + `compute_forecast_analysis()` (handles both a merged model DataFrame → per-hour `go_windows`/`period_hours`, and the legacy NDBC-aggregation stats dict) |
| `modules/m3_probability/engine.py` | `compute_probability()` — main analysis engine; `compute_annual_profile()` now accepts `mode`/`observed_means` (Set 34) |
| `modules/m3_probability/multipliers.py` | Hull/vehicle/recovery/season/era/exceedance multiplier functions |
| `modules/m4_ports/proximity.py` | Nearest-port search using the WPI database; `search_ports()` / `get_port()` back the voyage role pickers |
| `modules/m4_ports/voyage.py` | Multi-leg voyage cost model (`build_voyage_legs` + `compute_voyage_cost`), `VoyageCostParams` persistence, waypoint generation — see "Voyage cost model" below |
| `modules/m5_reports/pdf_report.py` | Analysis PDF (`generate_analysis_report`); optional `annual_profile=` param renders a full 12-month table page (Set 34) |
| `modules/m5_reports/voyage_pdf.py` | Voyage PDF (`generate_voyage_report`) — 6 pages: cover, leg-by-leg route (`_page_route`), cost breakdown (`_page_breakdown`), port comparison, waypoints, assumptions |
| `modules/m5_reports/comparison_pdf.py` | Multi-site comparison PDF; per-site parameter detail page (Set 35) |
| `modules/m5_reports/naming.py` | `sanitize`, `next_sequence_number`, `build_report_filename`, `record_report` (Set 7) |

UI — shell / tabs / sections:

| Path | Purpose |
|------|---------|
| `ui/main_window.py` | Root window, sidebar + `QStackedWidget`; `_SECTION_INDEX` wiring |
| `ui/sidebar.py` | 260px nav sidebar with branded header |
| `ui/styles.py` | Global QSS + `apply_table_colors()` helper |
| `ui/analysis_tab.py` | Analysis (12-month profile; direction checkboxes + Calculation Basis panel + `site_vehicles` upsert, Set 27B; Historical/45-Day mode radios + year-range spinboxes, Set 34; in-tab fetch-status banner for the synchronous live-data waits, Set 42 follow-up) |
| `ui/site_tab.py` | Tab 1 (legacy): site coordinates, vehicle, and platform selection |
| `ui/ports_tab.py` | Ports: proximity search + voyage economics (planned path was `ui/sections/ports.py`); "Voyage Cost Settings…" button opens the cost popup, per-port cost breakdown panel below the voyage table |
| `ui/sections/sites.py` | Site entry, "Apply & Save Site" with DB persist; "Vehicles Used" column (Set 27B) |
| `ui/sections/projects.py` | Projects section (`ProjectsSection`, nav index 0) |
| `ui/sections/comparison.py` | Multi-site ranking; "Export Detailed Report (PDF)" button wired to `generate_comparison_report()` (Set 35) |
| `ui/sections/ndbc.py` | NDBC station map + table; search-radius spinbox lives here now, actually wired into discovery (Set 36, moved from Settings) |
| `ui/sections/forecast.py` | Forecast section (live NWS/Open-Meteo model forecast primary + NDBC buoy overlay; horizon re-analyzes from cache; source badges) (Pre-28B-4); parameter cards show the vehicle's actual threshold; wind badge accurately reflects NDBC-buoy-only vs. no-source fallback (Set 36) |
| `ui/sections/reports.py` | Report generation + saved report list; visible "Delete Selected" button + incomplete-project flagging in the association dropdown (Set 37) |
| `ui/sections/vehicles.py` | Vehicle Manager section |
| `ui/sections/vessels.py` | Vessel (platform) specification section |
| `ui/sections/contracts.py` | Platform contract CRUD: list + filter by project/archived, `ContractEditorDialog` covers the full `platform_contracts` schema incl. hierarchy selector + 5 warranted fields (Pre-28B-2) |
| `ui/sections/launchers.py` | Launcher configuration manager |
| `ui/sections/history.py` | Read-only chronological view merging `analyses`/`project_site_status_history`/`reports`/`site_vehicles` (Set 40) — Type/Project/Site filters, double-click row to navigate |
| `ui/sections/settings.py` | Settings tabs including branded About tab; NDBC search radius removed (Set 36 — now lives on `ndbc.py`), NCEI timeout remains; "NCEI Historical Data Cache" download group added to Data Sources tab (Set 41); the old "Voyage Defaults" tab is now "Voyage Costs" — a read-only summary plus a button opening `VoyageCostEditorDialog` (its eight legacy `platform_speed_kts` / `num_tugs` / … settings keys are no longer read by anything) |

UI — dialogs / widgets:

| Path | Purpose |
|------|---------|
| `ui/dialogs/vehicle_editor.py` | Vehicle editor with Launchers tab (Tab 5) |
| `ui/dialogs/vessel_editor.py` | Add/Edit vessel (platform) — 4-tab QDialog |
| `ui/dialogs/launcher_editor.py` | Add/Edit launcher configuration — 2-tab QDialog |
| `ui/dialogs/voyage_cost_editor.py` | Voyage cost parameters — 4-tab QDialog (Route / Vessels / Port Fees / Summary); also exports `breakdown_summary_html()`, shared with the Ports tab |
| `ui/dialogs/site_history_viewer.py` | View site status history for a project-site pair |
| `ui/widgets/coord_input.py` | Dual-format coordinate input widget |
| `ui/widgets/spinbox.py` | Styled spin-boxes with clickable +/− on Windows |
| `ui/widgets/station_map.py` | Matplotlib NDBC station map widget |

Scripts:

| Path | Purpose |
|------|---------|
| `scripts/migrate_27a.py` | One-time DB wipe migration (Set 27A) — manual only, never on startup |
| `scripts/seed_vehicles.py` | Vehicle library seed |
| `scripts/seed_platforms.py` | Gateway platform seed |
| `scripts/backfill_coord_codes.py` | Backfill `coord_code` on existing sites (Set 25) |
| `scripts/import_wpi.py` | Import NGA World Port Index CSV |

## Actual UI File Locations (confirmed Pre-28 Audit)

The UI is split across two directories. This is intentional to document, not to
"fix" — see the note below. Confirmed by the `main_window.py` import audit
(every import resolves; there are **no basename collisions** across the two
directories, so the split causes no import conflict).

Files in `ui/` directly (not `sections/`):

```
ui/analysis_tab.py   -- Analysis UI (AnalysisTab, stack index 2)
ui/ports_tab.py      -- Ports UI (PortsTab, stack index 8)
ui/site_tab.py       -- legacy Site tab (SiteTab; NOT wired into main_window)
ui/sidebar.py
ui/main_window.py
ui/styles.py
```

Files in `ui/sections/`:

```
comparison.py, forecast.py, history.py, launchers.py, ndbc.py,
projects.py, reports.py, settings.py, sites.py, vehicles.py, vessels.py
```

**NOTE:** This split is a known structural inconsistency. Do NOT create new UI
files in `ui/` directly — all new UI sections go in `ui/sections/`. Consolidation
of the three `*_tab.py` files into `ui/sections/` is deferred to a future
maintenance pass (risks breaking working imports; out of scope for now).
`ui/site_tab.py` is legacy and unused by `main_window.py` (the wired Sites UI is
`ui/sections/sites.py`).

## Pre-28 audit — structure discrepancies (2026-07-02)

Read-only audit performed before Set 28. Every path in the module tables above
EXISTS on disk. The items below are planned-vs-actual gaps, kept here so their
intent is not lost — **do NOT delete these notes**; the referenced code still
needs to be created.

**Numbering note (added Set 29):** Despite the "(Set 28)" labels used
throughout this section, **Set 28 itself was never run.** A "Pre-28
correction set" was completed in its place and covers the items labeled
below. Set 28 remains an outstanding, unassigned instruction set number —
it was not superseded or skipped, just not yet executed under that number.
Do not assume "Set 28" is closed based on the labels below; they describe
what the Pre-28 correction set delivered, not a completed Set 28.

**RENAMED (planned path → actual path):**
- `ui/sections/analysis.py` → **`ui/analysis_tab.py`** (created as `analysis_tab.py`;
  Set 27B built the direction checkboxes + Calculation Basis panel here).
- `ui/sections/ports.py` → **`ui/ports_tab.py`** (Ports lives at the top-level
  `ui/` path, not under `ui/sections/`).

**MISSING — planned but absent (function-level) — RESOLVED in Set 28 remediation:**
- `modules/m2_weather/forecast.py`: `fetch_nws_marine_forecast()`,
  `fetch_openmeteo_marine_forecast()`, `fetch_combined_forecast()` — **ADDED (Set 28)**.
  `requests`/`pandas` are imported lazily inside them so the module still imports
  without those deps. `compute_forecast_analysis()` is **unchanged** — it still
  consumes the NDBC `aggregate_station_statistics()` dict (already has
  `horizon_hours`); the new fetch functions are standalone and not yet wired into
  the Forecast section UI (that wiring is a separate future task).
- `modules/m2_weather/ndbc_history.py`: `compare_periods()` — **ADDED (Set 28)**.
  Returns 15/30/45-day windows keyed `'15'`/`'30'`/`'45'`; a window is `None`
  when the frame holds <10% of expected records (days×24) for it.
- `ui/ports_tab.py`: per-row **remove button + undo snackbar + Reset**, backed by
  a session-only `_excluded_port_ids` set — **ADDED (Set 28)**. Adapted to the
  existing table UI (a `✕ Remove` button per row in a new actions column, not
  cards). CSV/PDF exports still use the full result set by design.

**EXTRA / observations:**
- `assets/…logo.png` filename — **RESOLVED (Set 28)**: renamed to
  `seagate_space_logo.png` to match `config.LOGO_PATH` exactly (case-sensitive-FS
  safe); `logo_available()` returns True.
- `modules/m1_site/__init__.py` — **RESOLVED (Set 28)**: package marker added.
- `.env.py` present in project root — `config.load_dotenv()` looks for `.env`,
  not `.env.py`. (Still present; low priority.)
- `Gateway App MD.md` — stray planning document in the project root. (Still present.)

**Instruction 21 coverage:**
- A) Direction exclusion checkboxes — **EXISTS** (functional). `ui/analysis_tab.py`
  has `cb_wind_dir` / `cb_sea_dir` / `cb_swell_dir`; inclusion is weight-driven
  (`_active_weights()`), NOT via an `exclude_params` build list as Instruction 21
  specified. Capability complete; implementation differs.
- B) Port card remove button + undo — **DONE (Set 28)** (table-row remove + undo
  snackbar + Reset; session-only exclusion).
- C) NDBC period statistics — **DONE (Set 28)** (`compute_period_statistics` +
  `compare_periods` both present).
- D) Marine forecast integration — **DONE (Pre-28B-4)**. `fetch_combined_forecast`
  is now wired into `_ForecastWorker` (live NWS wind + Open-Meteo wave/swell,
  NDBC buoys as overlay); `compute_forecast_analysis` gained a merged-DataFrame
  branch (`go_windows`/`period_hours`, optional `vehicle=`); horizon changes
  re-analyze from cached combined data; data-source badges added.

## Table colours

`ui/styles.py::apply_table_colors(table)` — call on every `QTableWidget` after
creation. QSS colour inheritance fails inside `QTabWidget` on Windows; explicit
`setStyleSheet` on each table is the only reliable fix.

## Known layout-height fixes

- **`ui/analysis_tab.py` — 12-month results table** (Cole-reported
  2026-07-11: "no 12 month forecast displayed" in Historical mode). The
  table itself and `self._profile` were populating correctly — this was
  purely a rendering bug. `self.basis_panel` (the Calculation Basis QLabel,
  RichText + wordWrap, populated by `update_basis_panel()`) has a sizeHint
  that scales with its content and measured 455px once populated; in a
  typical ~880px window that left almost no leftover space, so even after
  giving the table `stretch=1` it only grew to 46px — a stretch factor only
  redistributes *leftover* space, and there was none to redistribute (this
  is a different failure mode than the Candidate Sites bug below, where the
  competing item was a `QSpacerItem` — here the oversized item was a real
  widget with unbounded content-driven height). Fix: wrapped
  `self.basis_panel` in a `QScrollArea` with `setMaximumHeight(180)`, same
  as `basis_scroll`. This capped the panel and let the table's `stretch=1`
  actually claim the freed space — measured 383px after the fix, ~11.8 of
  12 rows visible without scrolling. `_reset_basis_panel()` and
  `update_basis_panel()` both had their own `border`/`border-radius` on the
  QLabel itself removed (now owned by the wrapping QScrollArea) to avoid a
  doubled border.
- **`ui/sections/contracts.py::ContractEditorDialog`** (Pre-28B-2 Step 3 grew
  this to cover the full `platform_contracts` schema). Form content is wrapped
  in a `QScrollArea` (`setWidgetResizable(True)`); the dialog's height is
  capped to a 700–800px band (`setMinimumHeight(700)`, `setMaximumHeight(800)`,
  `resize(500, 750)`) rather than sized to content, so this can't recur as
  fields are added later. Save/Cancel live in a separate bar outside the
  scroll area so they stay pinned and never scroll away with the content.
- **`ui/sections/projects.py::_build_right_panel` — Candidate Sites table**
  (line ~287, `_sites_table`). Target: **~10 visible rows** before internal
  scrolling engages. The constraint lives in two places: (1) the table's own
  `setMaximumHeight()`, computed from `verticalHeader().defaultSectionSize()`
  and the header height × 10 rows, right after `apply_table_colors()`;
  (2) the **absence** of a trailing `layout.addStretch(1)` in the outer
  right-panel layout — a previous version had one, which gave an invisible
  spacer an equal stretch factor to `_detail_widget` and silently starved the
  table down to ~1 visible row regardless of window height (confirmed by
  measurement: `_detail_widget` received only ~48% of the panel's leftover
  vertical space with the competing spacer in place). `_detail_widget`'s
  stretch=1 is now the only stretch item in that layout.
- **Audit (2026-07-08): checked for the same competing-stretch pattern in
  `ui/sections/contracts.py` (Contracts list table) and `ui/sections/sites.py`
  (All Sites + By Project tables) — all three are CLEAN, no fix needed.**
  Confirmed both by static read and by an offscreen empirical build (14-row
  seed data, real layout pass, measured actual `.height()`):
  - `ui/sections/contracts.py::ContractsSection._build()` — `self._table` is
    the sole stretch item in `root` (`root.addWidget(self._table, 1)`, line
    691, is the last item in `root` with nothing after it). The `addStretch()`
    calls at lines 375, 652, 674 are all on horizontal sub-layouts
    (`doc_row`/`filter_row`/`toolbar`) added to `root` via `addLayout(...)`
    with no stretch argument, so they never compete for `root`'s vertical
    space. Measured: 14 rows in a 1040px window → table height 864px, ~27.8
    rows visible (no starvation).
  - `ui/sections/sites.py::_build_all_sites_content()` — `self._table` (line
    376, `layout.addWidget(self._table, 1)`) is the sole stretch item in its
    own `layout`; `_status_lbl`/`hint` are added afterward at stretch=0. The
    `addStretch()` calls at lines 324/346 are on horizontal sub-layouts
    (`v_row`/`toolbar`), same harmless pattern as above.
  - `ui/sections/sites.py::_build_project_view()` — `_proj_empty_lbl` (line
    460) and `_proj_table` (line 474) both carry stretch=1 in the same
    `layout`, which at first read looks like the projects.py bug shape. It
    is NOT: unlike `addStretch()`'s `QSpacerItem` (always present, always
    competes), these are widgets that are mutually exclusively `.hide()`/
    `.show()`-toggled by `_on_project_combo_changed()`, and Qt's layout
    engine excludes a hidden widget from stretch-space allocation entirely
    — the visible one gets the full leftover space, not a proportional
    split. Also confirmed for `_build()`'s outer `root.addWidget(...,1)` on
    both `_all_sites_widget` (line 270) and `_project_view_widget` (line
    275) — same hidden-widget-doesn't-compete reasoning, same empirical
    confirmation. Measured: 14 rows in a 1040px window → `_proj_table`
    height 809px, ~26 rows visible; All Sites `_table` height 801px, ~25.7
    rows visible (no starvation in either case).
  - Takeaway for future audits: the projects.py bug required an
    always-present `QSpacerItem` sibling (`addStretch()`) at equal stretch
    to trigger; a hidden **widget** sibling with a stretch factor is safe
    because Qt doesn't reserve it any layout space while hidden.

## DB schema notes

- `platforms` has `NOT NULL` on `hull_type` and `hull_motion_factor`
- `sites.id` is `None` until saved with "Apply & Save Site" — analyses require a saved site
- Migration loop in `init_db()` uses `ALTER TABLE … ADD COLUMN` with try/except
  (SQLite has no `IF NOT EXISTS` for `ALTER TABLE`)
- `ncei_monthly_cache` (Set 41): caches `ncei.py::_summarise()`'s per-month
  output, `UNIQUE (bbox, month_start)`. `bbox` is the exact NCEI
  `boundingBox` string queried (not a site id) — two sites with the same
  `bbox_nm` and a similar area naturally share a cache row. No automatic
  expiry (climatological data); re-downloading overwrites via `ON CONFLICT`.
- `ww3_realtime_cache` (Set 42 follow-up): caches `era5.py::_do_fetch_ww3()`'s
  45-day summary, `UNIQUE (lat_bucket, lon_bucket)` (lat/lon rounded to the
  nearest whole degree). Unlike `ncei_monthly_cache`, this DOES expire —
  `get_cached_ww3()` treats rows older than 24h as a miss, since the 45-day
  window represents current conditions, not climatology. See "WW3 local
  cache" under the ERA5/WW3 section above.
- `site_vehicles` (Set 27A): per-site vehicle usage summary with composite
  primary key `(site_id, vehicle_id)` — one row per unique site+vehicle pair;
  `run_count` increments on each subsequent analysis and never creates
  duplicate rows. `last_used TIMESTAMP` defaults to `CURRENT_TIMESTAMP`.
  Written by `AnalysisTab._upsert_site_vehicle()` (Set 27B) via
  `INSERT … ON CONFLICT(site_id, vehicle_id) DO UPDATE` after each run; the
  upsert is non-fatal (logged, never surfaced). Surfaced in the Sites section
  "Vehicles Used" column (both All Sites and By Project modes).
- `project_sites.preferred_vehicle_id` (Set 27A): nullable
  `INTEGER REFERENCES vehicles(id)` — project-site level vehicle preference
  for pre-fill convenience; no preference until explicitly assigned.
- `platforms.vessel_code` (Pre-28B-1): pinned hull code. Gateway S/X/XL =
  `0100/0101/0102` (pinned in `seed_platforms.py` and `_assign_vessel_codes()`
  in `init_db`, which backfills any NULL codes idempotently on every launch).
- `platform_contracts` (Pre-28B-1): warranted operating envelopes per customer
  contract. `contract_code` is UNIQUE (format `CUST_VESSEL_MMDDYYYY_MMDDYYYY`,
  validated by `config.validate_contract_code`). `parent_contract_id` builds a
  master→subcontract→amendment hierarchy. Warranted limits are nullable; NULL
  falls back up the chain (see `modules/m1_site/contracts.py`). Direction
  tolerances are NOT warranted at vessel level.
- `projects.platform_contract_id` (Pre-28B-1): nullable link to the governing
  contract (UI wiring deferred to Pre-28B-2).

## Vessel pre-check gate (Pre-28B-1)

`modules/m1_site/contracts.py` is the single source of truth.
`resolve_warranted_envelope(contract_id)` walks the hierarchy most-specific-first
(with cycle detection) → `(envelope, contract_code)`. `apply_vessel_gate()`
takes the **more conservative** of warranted vs vehicle limit per parameter
(vessel↔vehicle safety rule only) and returns `(vessel_param_probs, verdict,
limiting)` — verdict/limiting restricted to `active_params` (same filter as the
Pre-28B-3 vehicle limiting fix). `compute_probability(..., platform_contract=)`
runs the gate only when a contract is passed; otherwise all vessel_* fields on
`AnalysisResult` stay None/empty. The Analysis tab shows a VESSEL verdict row
(or "No contract linked"). `AnalysisTab._resolve_active_platform_contract()`
(Pre-28B-2 Step 5) looks up `self.mw.active_project_id`'s
`projects.platform_contract_id` and passes the resolved `PlatformContract` to
`compute_annual_profile(..., platform_contract=)` on every run; returns `None`
(gate skipped, "No contract linked" unchanged) when there is no active
project, the project has no linked contract, or the lookup fails for any
reason — never raises.

## Direction parameters (wdV, sdV, swdV)

- Direction parameters **default to excluded** from the overall probability:
  settings keys `exclude_wind_dir`, `exclude_sea_dir`, `exclude_swell_dir` all
  default to `'1'` (Set 27A).
- As of Set 27B, `config.DEFAULT_WEIGHTS` covers only the **five magnitude
  parameters** (`ws 0.30, wg 0.26, sh 0.22, swh 0.14, swp 0.08`; sums to 1.0).
  Direction params are no longer in the default weight pool. `config.DIRECTION_WEIGHTS`
  (`wdV 0.04, sdV 0.03, swdV 0.03`) holds their starting values, applied only
  when the user opts in.
- The Analysis tab ([ui/analysis_tab.py](ui/analysis_tab.py)) has three direction
  checkboxes that read the `exclude_*_dir` settings on load (checked = INCLUDED =
  setting `'0'`), so they default **unchecked**. On run, `_active_weights()` starts
  from `DEFAULT_WEIGHTS` and adds each checked direction param's `DIRECTION_WEIGHTS`
  value; the engine's `normalize_weights()` renormalizes to 1.0. Excluded params
  simply carry weight 0 (the engine still computes their `param_probs`).
- The engine takes **no `exclude_params` argument** — inclusion is driven purely
  through the weights dict (weight 0 ⇒ excluded).
- **PDF reports must respect exclusion, not just the on-screen UI** (fixed
  post-Set-35, 2026-07-11). `AnalysisResult.active_params` is the
  authoritative "did this actually count toward overall_prob" set — the
  on-screen Calculation Basis panel already checked it correctly (Set 27B),
  but `pdf_report.py::_page2()` and `comparison_pdf.py::_page_site_params()`
  originally rendered all 8 parameters with identical colour-coded styling
  regardless of weight. Both now check `param in r.active_params` and mark
  excluded rows with "(excluded)", muted/italic text, and a grey (not
  colour-coded) probability cell — any new report page that lists
  per-parameter probabilities must do the same check, not just iterate
  `_PARAM_ORDER` uniformly.

## Analysis mode + year range (Set 34)

- The Analysis tab has real **Historical / 45-Day** radio buttons
  (`rb_historical` / `rb_45day`) and **Year start / Year end** `QSpinBox`
  controls (1960–2024), wired into `compute_annual_profile()`'s `mode`,
  `observed_means`, `year_start`, `year_end` parameters.
- **Historical mode** (default): no `observed_means`; year-range spinboxes
  are enabled and drive the ICOADS climatological era weighting, same as
  before Set 34 (previously the spinboxes didn't exist at all — the engine's
  hardcoded 1960–2024 default was always used regardless of Comparison tab's
  independent year-range setting).
- **45-Day mode**: year-range spinboxes disable automatically
  (`_on_mode_toggled`) since `compute_probability()` ignores them in this
  mode. On run, `modules/m2_weather/data_manager.get_site_weather_summary(site,
  mode='45day')` is called once — a live NDBC/near-term fetch, already fully
  implemented but previously never called from any UI — and its result is
  passed as `observed_means`, applied uniformly across all 12 months (it
  represents current conditions, not month-specific climatology). Wrapped in
  try/except; a network failure silently falls back to per-parameter model
  climatology rather than crashing the run.
- `compute_annual_profile()` in `modules/m3_probability/engine.py` gained
  `mode: str = "historical"` and `observed_means: Optional[Dict] = None`
  parameters (purely additive — both already existed on the
  `compute_probability()` it wraps; other callers like Comparison are
  unaffected since they don't pass these new kwargs).
- `GatewayMainWindow.platform` now resolves from the active site's own
  `platform_id` inside `on_site_changed()` (fresh DB lookup), instead of
  staying pinned to its `__init__` default ("Gateway X") for the entire
  session regardless of which platform the active site actually specifies.
  Falls back to leaving `self.platform` unchanged if the site has no
  `platform_id` or the lookup fails.
- PDF export (`generate_analysis_report(..., annual_profile=)`) now renders
  a full 12-month Month/Probability/Verdict/Limiting-Parameter table
  (`_page_annual()` in `pdf_report.py`), inserted right after the cover
  page. `AnalysisTab._export_pdf()` passes the already-computed
  `self._profile` instead of silently recomputing a single fresh month via
  `datetime.now()` with hardcoded engine defaults — the PDF's cover page
  now reflects the run's actual mode/year-range settings.

## Analysis tab fetch-status banner (Set 42 follow-up)

`_run()`'s live weather fetches (NCEI/ERA5 in Historical mode, NDBC in
45-Day mode) and the `compute_annual_profile()` call itself are all
synchronous — with only the small bottom-of-window main-status-bar text
(`self.mw.status()`) updating, a slow fetch (NCEI ~130s/month, WW3 ERDDAP up
to ~13min cold — see NCEI/WW3 sections below) made the whole app look
frozen with no obvious feedback in the tab actually doing the waiting.

- `AnalysisTab._build()` adds a `fetch_status_widget` row (an indeterminate
  `QProgressBar` + a `QLabel`) directly under the site label, hidden by
  default.
- `AnalysisTab._set_fetch_status(msg: str | None)` is the single toggle
  point: a string shows the banner, sets its text, disables `run_btn`
  (prevents re-entrant double-clicks during a multi-minute fetch), mirrors
  the message to `self.mw.status()`, and forces a repaint via
  `QApplication.processEvents()`. `None` hides the banner and re-enables
  `run_btn` (only if `self.mw.site` is set, matching `on_site_changed()`'s
  existing enable condition).
- `_run()`'s body (from the mode-specific fetch through `pdf_btn.setEnabled`)
  is now wrapped in `try/finally`, with `self._set_fetch_status(None)` in
  the `finally` — the banner and Run button are guaranteed to reset even if
  a fetch or `compute_annual_profile()` raises, not just on the success
  path. Verified with a test that mocks `compute_annual_profile` to raise
  `RuntimeError` and confirms the banner is hidden and Run re-enabled
  despite the exception propagating.
- Tests: `tests/test_analysis_fetch_status.py`.

## ERA5 / Copernicus CDS — client library and variable fixes (Set 42)

- **`cdsapi.Client` is broken against the current CDS backend — use
  `LegacyClient` instead.** Plain `cdsapi.Client().retrieve()` builds
  request URLs with an old path scheme (`/api/resources/{dataset}`) that
  Copernicus has retired; confirmed via direct live testing (404 Not
  Found), independent of which variables are requested. Fixed by switching
  to `ecmwf.datastores.legacy_client.LegacyClient` (already installed as a
  dependency of `cdsapi`, now also listed explicitly in
  `requirements.txt`) via the new `era5.py::_get_cds_client()` helper — it
  has the identical `retrieve(name, request, target)` signature, so it's a
  drop-in replacement, and uses the correct current path
  (`/api/retrieve/v1/processes/{dataset}/execution`). Confirmed working up
  through authentication; falls back to plain `cdsapi.Client` only if
  `ecmwf-datastores-client` somehow isn't installed.
- **`_ERA5_VARS` was requesting the wrong variable for swell height** —
  fixed. It previously requested
  `significant_height_of_combined_wind_waves_and_swell` (ERA5 shortname
  `swh`) to populate this app's `swh` (swell height) parameter, but that
  ERA5 variable is the **combined** wind-sea + swell height, not swell
  alone — confirmed against ECMWF's own parameter documentation. Now
  requests `significant_height_of_total_swell` / `mean_period_of_total_swell`
  / `mean_direction_of_total_swell` (shortnames `shts`/`mpts`/`mdts`),
  which are genuinely swell-only. `_parse_era5_nc()`'s netCDF key lookups
  updated to match. This mismatch predated Set 42 and had gone unnoticed
  because `_ERA5_VARS`/parsing were never exercised end-to-end before (the
  auth failure blocked it).
- **`check_era5_auth()` was giving a false positive.** It previously only
  instantiated `cdsapi.Client()`, which just parses `.cdsapirc` — it never
  made a network call, so Settings → "Test Connection" reported "Connected"
  even while every real request was failing. Now calls
  `LegacyClient(...).client.check_authentication()`, a real, lightweight
  account-verification request (no data job submitted).
- **401 blocker — RESOLVED.** The account/token-level `401 Unauthorized` at
  `/profiles/v1/account/verification/pat` described below was fixed by Cole
  regenerating the CDS API key as a current Personal Access Token — live CDS
  requests now authenticate and return real data.
- **Follow-up fix (2026-07-12): `_parse_era5_nc()` KeyError "No variable
  named 'time'".** Once auth started working, a genuine second bug surfaced
  that could only be found by parsing a real downloaded file: the time
  coordinate in current CDS monthly-means output is named `valid_time`, not
  the classic `time` — confirmed live (`Variables on the dataset include
  ['shts', 'mpts', 'mdts', 'number', 'valid_time', 'latitude', 'longitude',
  'expver']`, no `time` key at all). Fixed with a flexible lookup,
  `_first_nc_key(ds_pt, ["valid_time", "time"])`, used for both the
  `.dt.month` filter and the `.sel()` call, so it keeps working if Copernicus
  reverts or varies this across dataset versions. Verified live end-to-end:
  `fetch_swell_climatology(28.5, -80.5, 2020, 2020, months=[6])` →
  `{6: {'swh_mean_m': 0.511, 'swh_p90_m': 0.511, 'swp_mean_s': 6.169,
  'swd_mean_deg': 95.7, 'source': 'era5_reanalysis', ...}}`. Note: despite
  Cole reporting this error under "45D forecast", `_apply_era5_swell()` is
  only ever called from `_fetch_historical()` — this was actually a
  Historical-mode run; 45-Day mode never touches ERA5 at all.
- **Wind gust via ERA5 — IMPLEMENTED (2026-07-13).** NCEI Global Marine (the
  other historical wind source) carries no gust field at all (confirmed
  empirically — see NCEI section below), so `wg` had no live historical
  source and stayed `icoads_model` by design. Now that CDS auth works,
  `fetch_gust_climatology()` (`era5.py`) requests
  `instantaneous_10m_wind_gust` from the same
  `reanalysis-era5-single-levels-monthly-means` dataset used for swell —
  confirmed live it IS present in the monthly-averaged product (shortname
  `i10fg`) despite ECMWF's docs marking gust fields "forecast only".
  Structured identically to `fetch_swell_climatology()`
  (`_do_fetch_era5_gust()` / `_parse_era5_gust_nc()`), including the same
  `valid_time`/`time` coordinate flexibility fix. Converts m/s → knots via
  `config.MS_TO_KTS` to match this app's `ws`/`wg` unit convention.
  `data_manager.py::_apply_era5_gust()` wires it into `_fetch_historical()`
  the same way `_apply_era5_swell()` wires in swh/swp — populates
  `summary["wg"]` with `source: "era5_reanalysis"` on success, otherwise
  leaves `wg` as `icoads_model`. **Verified live**:
  `fetch_gust_climatology(28.5, -80.5, 2020, 2020, months=[6])` →
  `{6: {'wg_mean_kts': 11.81, 'wg_p90_kts': 11.81, ...}}`; and through the
  full data_manager path,
  `_apply_era5_gust(summary, 28.5, -80.5, 2020, 2020)` moved
  `summary["wg"]` from `{'mean': None, 'source': 'icoads_model'}` to
  `{'mean': 15.5, 'source': 'era5_reanalysis'}` — both physically plausible.

## WaveWatch III ERDDAP — variable name and query fixes (Set 42 follow-up)

Reported by Cole: "WW3 ERDDAP: no recognised SWH variable found in
NWW3_Global_Best". Live investigation of the real dataset (2026-07-13, via
`info/NWW3_Global_Best/index.json` and `.das`) found three independent bugs,
now all fixed in `modules/m2_weather/era5.py`:

- **Wrong variable name candidates — same "combined vs swell-only" mistake
  class as the ERA5 `_ERA5_VARS` bug above.** None of the old
  `_WW3_SWH_CANDIDATES`/`_WW3_MWD_CANDIDATES`/`_WW3_MWP_CANDIDATES` entries
  exist in the live dataset at all. The real variable names are short codes:
  `Thgt`/`Tdir`/`Tper` (combined/total wave — wrong), `whgt`/`wdir`/`wper`
  (wind-sea-only — also wrong, a third distinct physical quantity), and
  `shgt`/`sdir`/`sper` (confirmed via `standard_name`
  `sea_surface_swell_wave_*` — genuinely swell-only, correct). The three
  candidate lists now put `shgt`/`sdir`/`sper` first; the old long-name
  candidates are kept as fallbacks in case a different ERDDAP server/dataset
  version exposes those instead.
- **Missing `depth` constraint.** This griddap dataset has FOUR dims —
  `time, depth, latitude, longitude` — not three. `depth`'s `actual_range` is
  `0.0, 0.0` (surface-only). The original code's `e.constraints = {...}`
  wholesale-replaced the dict erddapy auto-populates on `e.dataset_id = ...`
  with one missing `depth` entirely.
- **Wholesale dict replacement also drops erddapy's internal `{dim}_step`
  keys**, which `_griddap_check_constraints()` requires to be present and
  unchanged — even after adding `depth>=`/`depth<=`, replacing the dict still
  raised `"keys in e.constraints have changed. Re-run e.griddap_initialize"`.
  Fixed by mutating the already-initialized `e.constraints` dict in place
  (`e.constraints.update({...})`) instead of reassigning it, so the
  `_step` keys survive.
- **Longitude convention mismatch.** This dataset's `longitude` uses
  0–360°E (`actual_range 0.0, 359.5`), not this app's `-180..180` (`+E/-W`)
  convention (see "Coordinate convention" above) — a raw `-80.5` query was
  entirely outside the dataset's valid range. Fixed with `lon % 360`,
  converted only at this API boundary; app-wide storage is unchanged.
- **Verified live end-to-end**: `fetch_swell_realtime_ww3(28.5, -80.5)` →
  `{'swh_mean_m': 0.452, 'swh_p90_m': 0.78, 'swd_mean_deg': 95.6,
  'swp_mean_s': 7.429, 'source': 'ww3_erddap', 'record_count': 6125}` —
  physically plausible values for a 45-day window off the Florida coast.
- **Note on latency**: live WW3 ERDDAP griddap queries against this dataset
  took ~13 minutes to return during testing (server-side aggregation over a
  45-day global-grid subset), separate from any code issue. This mirrors the
  NCEI latency pattern documented below — not fixable from this app's side.

### WW3 local cache (Set 42 follow-up, part 2)

Same latency-mitigation pattern as `ncei_monthly_cache` (see NCEI section
below), adapted for a rolling window instead of fixed calendar months:

- **`ww3_realtime_cache` table** (`core/database.py`): keyed by
  `(lat_bucket, lon_bucket)` — lat/lon rounded to the nearest whole degree,
  matching `_do_fetch_ww3()`'s own `+-0.5` deg query window, so nearby sites
  naturally share a cache row (same sharing rationale as NCEI's `bbox` key).
  `UNIQUE (lat_bucket, lon_bucket)`.
- **`get_cached_ww3(lat, lon)` / `save_cached_ww3(lat, lon, summary)`**
  (`modules/m2_weather/era5.py`) are the read/write helpers, mirroring
  `ncei.py`'s `get_cached_month()`/`save_cached_month()` shape
  (`INSERT ... ON CONFLICT DO UPDATE`).
- **Unlike NCEI's cache, this one expires.** NCEI's data is climatological
  (no natural staleness); WW3's 45-day window represents *current*
  conditions and shifts every day, so an old cache row is actively wrong,
  not just outdated. `get_cached_ww3()` computes `fetched_at` age in SQL
  (`julianday('now') - julianday(fetched_at)`) and returns `None` (cache
  miss) once a row is older than `_WW3_CACHE_MAX_AGE_HOURS` (24h) — the
  caller then does a normal live fetch and the miss gets a fresh entry.
- `fetch_swell_realtime_ww3()` is now cache-first: checks
  `get_cached_ww3()`, and only calls `_do_fetch_ww3()` (the ~13min live
  path) on a miss. Both the cache lookup and the cache write are wrapped in
  their own try/except and are non-fatal — a cache failure (e.g. DB locked)
  falls through to a live fetch or just skips the write, never blocks the
  live result from being returned to the caller.
- **Verified live**: first call against an empty cache took 215.8s and
  returned live data; an immediate second call for the same coordinates
  returned the identical result in 0.0s from `ww3_realtime_cache`.
- **Bug found+fixed after landing this: `tests/test_era5.py` had no DB
  isolation fixture** (unlike `test_contracts_and_pairing.py`,
  `test_analysis_fetch_status.py`), so once `fetch_swell_realtime_ww3()`
  started touching the DB, `TestFetchSwellRealtimeWW3`'s network-gated live
  test wrote real rows straight into **production** `gateway.db`'s
  `ww3_realtime_cache` — confirmed via direct inspection (two polluted rows,
  `(33, -61)` and `(40, -70)`, both purged with `DELETE FROM
  ww3_realtime_cache`). Worse, this then broke a *different* test in the
  same class (`test_returns_none_when_erddapy_missing`, which mocks the
  `erddapy` import to fail) because the cache-first check in
  `fetch_swell_realtime_ww3()` runs before `erddapy` is ever imported, so a
  fresh cache row from the prior test made the mocked-failure test return
  cached data instead of hitting the (intentionally broken) import path.
  Fixed by adding the same `monkeypatch.setattr(db_mod, "DB_PATH", ...)` +
  `db_mod.init_db()` autouse fixture the other test files already use.
  **Any future test that calls `fetch_swell_realtime_ww3()` (or anything
  that reaches `get_connection()`) must have this DB isolation — this class
  of bug is easy to reintroduce.**

## NCEI historical data — latency is real and NCEI-side, not this app's

- `_run()` calls `get_site_weather_summary(mode="historical", ...)` on
  every Historical-mode run (Set 39), same as 45-Day mode already did
  (Set 34). `data_manager._fetch_historical()` queries NCEI **one request
  per calendar month** in the selected range, and — confirmed via a direct
  live A/B test (2026-07-11) — each request takes **~130 seconds
  regardless of how many dataTypes are requested** (128.9s for the original
  2-field wind-only request vs 129.6s for the new 6-field wind+wave+swell
  request). This is NCEI's server-side query cost scaling with the date-
  range/station-day count, not something fixable by changing what fields
  this app asks for.
- Because the Analysis tab only offers year-granularity controls, the
  smallest possible request is 12 months ≈ 26 minutes if fetched live.
  `_fetch_historical()` therefore gates live fetching by **the whole
  requested range**, not per-month: `allow_live_fetch = len(windows) <=
  NCEI_MAX_LIVE_MONTHS` (3), checked once before the month loop. Any month
  is still checked against the local cache regardless of range size (a fast
  SQLite read, confirmed at 0.65s for a 780-month check) — only an actual
  *live* NCEI call is gated. **Do not change this to a per-month gate** —
  that exact mistake shipped briefly during Set 41 and made the full test
  suite take 3.5 hours (some tests exercise a large default range, and a
  per-month gate still let each of them attempt a few 130s live fetches
  before giving up). Verify any change here with a full `pytest` run, not
  just a single function call — the regression was invisible in isolated
  testing and only showed up as suite-wide duration.
- **Local cache (Set 41):** `ncei_monthly_cache` table (keyed by the exact
  NCEI `boundingBox` string + calendar month, not site id) lets
  `_fetch_historical()` use previously-fetched months for free, including
  for large ranges beyond the live-fetch gate. `ncei.py::get_cached_month()`
  / `save_cached_month()` are the read/write helpers. The only way to
  populate the cache for a large range is the explicit **"Download NCEI
  History"** action on Settings → Data Sources (`_NceiDownloadWorker`, a
  QThread with progress/cancel) — this has no range cap of its own since
  it's a deliberate, user-initiated, backgroundable action, not part of the
  interactive Analysis flow. Climatological data doesn't need automatic
  cache expiry; re-running the download action overwrites existing rows.
- `modules/m2_weather/ncei.py::fetch_wind_history()` now also fetches
  `WAVE_HGT`, `WAVE_DIR`, `SWELL_HGT`, `SWELL_DIR` (confirmed present via a
  live API query) alongside `WIND_SPEED`/`WIND_DIR`, feeding `sh`/`sdV`/
  `swdV` in `_fetch_historical()`'s output. Wind **gust** (`wg`) was
  confirmed empirically absent from this dataset (tried both
  `WIND_GUST_SPEED` and `GUST_SPEED` against 36k+ real records — neither
  ever appears) — `wg` has no live historical source and stays
  `icoads_model` by design, not by omission.

## Known limitations

- **`vehicles.name` has no DB-level UNIQUE constraint.** Uniqueness is enforced
  only at the application layer in `VehicleEditorDialog._on_save()` (Pre-28B-3).
  Direct database inserts can bypass this check. A future migration should add a
  proper `UNIQUE INDEX` on `vehicles(name)` (SQLite can't add it via `ALTER TABLE`,
  so it requires a table rebuild). Name-based row matching in
  `VehiclesSection._selected_row_data()` relies on this uniqueness.
- **`datetime.utcnow()` deprecation resolved (all production and test call
  sites)** via `datetime.now(timezone.utc).replace(tzinfo=None)` rather than
  migrating to full tz-aware comparison. This reproduces the exact naive-UTC
  value the old `.utcnow()` call produced, so behavior is unchanged, but the
  underlying `DatetimeIndex` being compared against in `ndbc_history.py`
  remains naive rather than tz-aware. A future pass could make both sides
  tz-aware instead of stripping tzinfo, which would be the more complete
  fix, but is out of scope for a deprecation-warning cleanup.

## Site+project activation pairing (session-only)

Resolved mechanism for "which site and project are active right now":

- **Where:** `ui/sections/sites.py`, **By Project view only**. The All Sites
  view has no Activate control — `_set_active()`/`_activate_row()` and the
  "Set Active Site ▼" toolbar button were removed (confirmed decision).
  All Sites' status column ("Active ★" / "Saved ✓" / "Unsaved") is now
  purely read-only: `self._active_id` is refreshed only from
  `self.mw.site.id` in `_load_from_db()`, with no write path left in that
  view. `self.mw.site` has exactly one writer — the By Project
  Activate/Deactivate handlers below.
- **Guards** (`_activation_guard_reasons()`, a pure function in `sites.py`):
  a per-row **Activate** button is enabled only when the parent project's
  `status` is `'planning'` or `'pending'` AND the row's `project_sites`
  candidate status is not `'rejected'`. Disabled rows show a tooltip stating
  which condition failed.
- **On Activate:** `session_state['active_site_id']` and
  `['active_project_id']` are set; `self.mw.site` is set to the loaded
  `Site`; `self.mw.active_project_id` is set; `self.mw.on_site_changed()`
  fires (refreshes Analysis/Ports as usual).
- **Deactivate** button is section-level (not row-scoped) — visible whenever
  a pairing is active, regardless of table selection. Clears both
  session_state keys to `''`, sets `self.mw.site = None` and
  `self.mw.active_project_id = None`, and calls `on_site_changed()`.
- **No persistence across restart.** `ui/main_window.py.__init__` clears
  both `active_site_id` and `active_project_id` to `''` on every launch,
  immediately after the existing `selected_ndbc_stations` clear (same
  precedent/rationale — Pre-28B-4 Fix A).
- **`self.mw.active_project_id`** is a plain instance attribute (default
  `None`), alongside `self.mw.site`. **Contracts UI
  (`ui/sections/contracts.py`) exists as of Pre-28B-2** (CRUD only — see the
  module table above). `active_project_id`'s **one real consumer** as of
  Pre-28B-2 Step 5 is the Analysis tab's vessel pre-check gate — see
  "Vessel pre-check gate" above. Project-aware vehicle pre-fill via
  `project_sites.preferred_vehicle_id` is still not wired to it. Any future
  consumer must read `self.mw.active_project_id`, not invent a new attribute
  name (confirmed via `main_window.py` audit: no `active_project` attribute
  existed prior to Pre-28B-2).

## Project ↔ contract linking (Pre-28B-2 Step 6)

`projects.platform_contract_id` is a single nullable `INTEGER` FK — a project
links to **exactly one** contract row at a time (not a join table, no
multi-contract support). That single row can be of any tier (master,
subcontract, amendment); `resolve_warranted_envelope()` already walks
`parent_contract_id` upward from whatever is linked, so linking a project to
a subcontract/amendment automatically pulls in the parent's values for any
warranted field the more specific row leaves unset. **There is no separate
"select which tier governs" control** — picking the single most-specific
contract that applies to the project is sufficient; the hierarchy fallback is
transparent from that point on.

The linking control lives on the **Projects tab** (`ui/sections/projects.py`),
not the Contracts form — the FK direction (`projects → platform_contracts`)
makes Projects the natural owner. A "Linked Contract" combo in the project
detail form is saved via `_on_save_project()`. The combo excludes archived
contracts by default (matching the Contracts tab's default filter), but
`_select_project()` re-adds the currently-linked contract with an
"[archived]" suffix if it happens to be archived, so an existing link is
never silently hidden. `ProjectsSection` gained a `showEvent` (it had none
before) that reloads the contract list so contracts added/archived on the
Contracts tab are current when the user returns to Projects.

## Voyage cost model

Replaces the old single-hop `VoyageCost` (fuel MT + tugs + crew + weather
contingency), which no longer exists. A voyage is an ordered chain of port
calls with the launch site in the middle:

```
[Mob] -> [Load] -> [Staging] -> Launch Site -> [Discharge] -> [Demob]
```

- Only Load and Discharge are effectively required; both default to the port
  selected in the nearest-ports table, so the default route collapses to
  `Port -> Site -> Port` (the previous round-trip behaviour). Unset optional
  roles drop out of the chain entirely.
- **On-site days belong to a leg's *destination*.** The first stop is the
  origin and is therefore never billed on-site time — a value typed into the
  origin role's on-site field is silently unused, by design.
- **`total_usd = charter hire (all vessels) + port fees + fuel`.**
- **Charter:** `VesselParams.charter_days is None` means "bill the full voyage"
  (transit + on-site) — that's the Gateway platform. A number means an
  independent on-hire/off-hire window (support vessels), billed regardless of
  voyage length. Undeployed vessels contribute exactly $0 and burn no fuel.
- **Fuel:** every *deployed* vessel burns across the **full leg list** even when
  it charters for a shorter window: `total_transit x at_sea_gal_day +
  total_onsite x in_port_gal_day`, times that vessel's `$/gal`.
- **Port fees:** 6 roles x 6 categories, flat per port call, and **only charged
  for roles the route actually visits** (`route_roles()`). Fees typed against a
  role with no port selected have no effect until that port is picked.
- **`compare_port_options()` reruns the entire route per candidate**, swapping
  the candidate into the Load and Discharge slots (only where the user has not
  pinned those roles explicitly), then ranks by `total_usd`.

Two things are deliberately *not* editable:

- **Transit days** — always `distance_nm / speed_kts / 24`. Speed is the only
  input. `VoyageLeg.transit_days` is rounded to **6 dp, not 4**: at a ~$20k/day
  platform rate, 4 dp visibly shifted the charter total (~$1.56 on the
  reference voyage). Don't coarsen it.
- **Leg distances** — great-circle `haversine_nm()`, no override. This reads
  low for routes that must round a landmass: Pascagoula -> Jacksonville is
  ~358 NM great-circle versus ~1,044 NM actual sailing distance, and there is
  no routing engine in this app. Gulf-to-Atlantic voyages will under-report
  distance, transit days and therefore charter hire. The PDF disclaimer says so
  explicitly.

`VoyageCostParams` (in `voyage.py`) holds every editable value and persists as
**one JSON blob** in `settings` under `voyage_cost_params` — no new table, no
schema migration. `from_dict()` is deliberately tolerant of missing keys and
bad types so a stale or hand-edited blob degrades to defaults rather than
raising. Defaults are seeded from the reference voyage sheet: 9 kts; platform
$20,000/day at 12/50 gal-day; SV1 $10,000/day for 18.5 days at 23/8 gal-day;
SV2 undeployed; $1.00/gal; on-site 2/4/2/4/2; Mob port fees
2500/4000/3500/1000/2000/1000; 1 launch.

`save_voyage_schedule()` writes the whole breakdown into the existing
`voyage_schedules.cost_summary_json` column. The table's
`fuel_consumption_mt_day`, `fuel_price_usd_mt`, `num_tugs`, `tug_day_rate_usd`,
`crew_day_rate_usd` and `weather_contingency_pct` columns belong to the old
model and are now always NULL — left in place (nullable) rather than migrated
away.

**Test isolation:** `calculate_voyage_cost()`, `compare_port_options()` and
`load_params()` all read the settings table, and `save_params()` writes it, so
`tests/test_voyage.py` uses an **autouse** DB-redirect fixture. Any new test
touching these must too — this is the same production-DB-pollution bug class
already documented for `tests/test_era5.py`.

## Database backups

Database backups are stored in `backups/` as full SQLite file copies named
`gateway_backup_{timestamp}.db`. To restore: stop the application, copy the
backup file back to `gateway.db`, restart.

`scripts/migrate_27a.py` is the only file that performs a database wipe; it
always creates a backup first and must be run explicitly by the user
(`py scripts/migrate_27a.py`, `--dry-run` to preview). It must never run on
app startup or be called from another module.

## Test fixtures

```python
# Redirect DB in tests:
monkeypatch.setattr(db_mod, "DB_PATH", str(db_file))
# Note: attribute name is DB_PATH (no underscore)
```

## Gateway platform specs

| Platform   | Status           |
|------------|------------------|
| Gateway S  | Transit 8.5 ft (2.591 m), launch 14.0 ft (4.267 m) — operator confirmed 2026-06-27 |
| Gateway X  | Drafts unverified |
| Gateway XL | Drafts unverified |

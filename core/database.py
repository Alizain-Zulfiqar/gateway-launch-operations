"""
core/database.py — SQLite connection management and schema creation.
All tables created here. Run init_db() once on first launch.
"""
import sqlite3
from pathlib import Path
from config import DB_PATH


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with row_factory set for dict-like access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _assign_vessel_codes(conn: sqlite3.Connection) -> None:
    """
    Assign vessel_code to any platform that lacks one. Gateway S/X/XL get pinned
    codes (stable across DB wipes/reseeds); other platforms get sequential codes
    starting at MAX+1 (floor 100). Idempotent — skips platforms already coded.
    """
    PINNED = {
        "Gateway S":  "0100",
        "Gateway X":  "0101",
        "Gateway XL": "0102",
    }
    for name, code in PINNED.items():
        conn.execute(
            "UPDATE platforms SET vessel_code = ? "
            "WHERE name = ? AND vessel_code IS NULL",
            (code, name),
        )

    rows = conn.execute(
        "SELECT id FROM platforms WHERE vessel_code IS NULL ORDER BY id"
    ).fetchall()
    if rows:
        max_row = conn.execute(
            "SELECT MAX(CAST(vessel_code AS INT)) FROM platforms "
            "WHERE vessel_code IS NOT NULL"
        ).fetchone()
        next_code = max(100, (max_row[0] or 99) + 1)
        for row in rows:
            conn.execute(
                "UPDATE platforms SET vessel_code = ? WHERE id = ?",
                (f"{next_code:04d}", row[0]),
            )
            next_code += 1

    conn.commit()


def init_db() -> None:
    """Create all tables if they do not already exist."""
    conn = get_connection()
    c = conn.cursor()

    c.executescript("""

    -- ── Vehicle categories ───────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS vehicle_categories (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT    NOT NULL UNIQUE,
        sort_order INTEGER DEFAULT 0
    );

    -- ── Settings ─────────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );

    -- ── Session state ──────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS session_state (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );

    -- ── Sites ────────────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS sites (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT    NOT NULL,
        lat         REAL    NOT NULL,   -- +N / -S decimal degrees
        lon         REAL    NOT NULL,   -- +E / -W decimal degrees
        bbox_nm     REAL    DEFAULT 25.0,
        platform_id INTEGER REFERENCES platforms(id),
        notes       TEXT,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- ── Vehicles ─────────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS vehicles (
        id                          INTEGER PRIMARY KEY AUTOINCREMENT,
        name                        TEXT    NOT NULL,
        provider                    TEXT,
        vehicle_class               TEXT    NOT NULL,
        mass_to_orbit_kg            REAL,
        propellant                  TEXT,
        recovery_mode               TEXT    DEFAULT 'expendable',
        max_wind_kts                REAL,
        max_gust_kts                REAL,
        max_hs_m                    REAL,
        max_swell_ht_m              REAL,
        max_swell_period_s          REAL,
        max_wind_dir_tolerance_deg  REAL    DEFAULT 45.0,
        max_sea_dir_tolerance_deg   REAL    DEFAULT 60.0,
        max_swell_dir_tolerance_deg REAL    DEFAULT 60.0,
        notes                       TEXT
    );

    -- ── Platforms ────────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS platforms (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        name                TEXT    NOT NULL,
        hull_type           TEXT    NOT NULL,
        hull_motion_factor  REAL    NOT NULL,
        dp_capable          INTEGER DEFAULT 1,
        max_hs_operating_m  REAL,
        typical_depth_m     REAL,
        payload_class       TEXT,
        notes               TEXT
    );

    -- ── Analyses ─────────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS analyses (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        site_id             INTEGER NOT NULL REFERENCES sites(id),
        vehicle_id          INTEGER NOT NULL REFERENCES vehicles(id),
        platform_id         INTEGER NOT NULL REFERENCES platforms(id),
        mode                TEXT    NOT NULL,   -- '45day' or 'historical'
        year_start          INTEGER,
        year_end            INTEGER,
        month_filter        INTEGER,            -- NULL=all months, 1-12=specific
        param_probs_json    TEXT,               -- JSON: per-parameter probability
        overall_prob        REAL,
        limiting_param      TEXT,
        data_sources_json   TEXT,               -- JSON: source tier per parameter
        confidence_rating   TEXT,               -- 'high','moderate','low','model'
        notes               TEXT,
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- ── NDBC station cache ───────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS ndbc_stations (
        station_id      TEXT    PRIMARY KEY,
        name            TEXT,
        lat             REAL,
        lon             REAL,
        has_spec        INTEGER DEFAULT 0,
        met_data        INTEGER DEFAULT 0,
        last_checked    TIMESTAMP
    );

    -- ── Ports (NGA World Port Index) ─────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS ports (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        wpi_number          TEXT,
        port_name           TEXT    NOT NULL,
        country             TEXT,
        lat                 REAL    NOT NULL,
        lon                 REAL    NOT NULL,
        harbor_size         TEXT,
        harbor_type         TEXT,
        shelter             TEXT,
        entry_tide          INTEGER,
        max_vessel_size     TEXT,
        depth_anch_m        REAL,
        depth_bar_m         REAL,
        depth_chan_m        REAL,
        fuel_oil            INTEGER DEFAULT 0,
        diesel              INTEGER DEFAULT 0,
        ovhd_limits         INTEGER DEFAULT 0,
        dry_dock            TEXT,
        railway             TEXT
    );

    -- ── Projects ─────────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS projects (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT    NOT NULL,
        description TEXT,
        status      TEXT    NOT NULL DEFAULT 'active',
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- ── Project site status history (append-only) ─────────────────────────────
    CREATE TABLE IF NOT EXISTS project_site_status_history (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id    INTEGER NOT NULL REFERENCES projects(id),
        site_id       INTEGER NOT NULL REFERENCES sites(id),
        status        TEXT    NOT NULL,
        changed_by    TEXT    DEFAULT '',
        approval_note TEXT    DEFAULT '',
        document_path TEXT,
        archived      INTEGER DEFAULT 0,
        created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- ── Project sites (current-state thin table) ──────────────────────────────
    CREATE TABLE IF NOT EXISTS project_sites (
        project_id  INTEGER NOT NULL REFERENCES projects(id),
        site_id     INTEGER NOT NULL REFERENCES sites(id),
        status      TEXT    NOT NULL DEFAULT 'candidate',
        updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (project_id, site_id)
    );

    -- ── Reports ──────────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS reports (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id      INTEGER REFERENCES projects(id),
        site_id         INTEGER NOT NULL REFERENCES sites(id),
        report_type     TEXT    NOT NULL,
        filename        TEXT    NOT NULL UNIQUE,
        sequence_number INTEGER NOT NULL,
        file_path       TEXT    NOT NULL,
        is_archived     INTEGER NOT NULL DEFAULT 0,
        generated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- ── Site-vehicle usage summary ────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS site_vehicles (
        site_id         INTEGER NOT NULL REFERENCES sites(id),
        vehicle_id      INTEGER NOT NULL REFERENCES vehicles(id),
        run_count       INTEGER NOT NULL DEFAULT 1,
        last_used       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (site_id, vehicle_id)
            -- composite key: one row per unique site+vehicle pair.
            -- run_count increments on each subsequent analysis.
            -- Never creates duplicate rows.
    );

    -- ── NCEI historical monthly cache (Set 41) ─────────────────────────────────
    -- Caches ncei.py::_summarise()'s per-month output, keyed by the exact
    -- NCEI boundingBox string queried (not site id — two sites sharing a
    -- bbox_nm and falling in the same area naturally share a cache row).
    -- Avoids the ~130s-per-month live NCEI query on repeat use. Climatological
    -- data, not live conditions — no automatic expiry; see get_cached_month()/
    -- save_cached_month() in ncei.py.
    CREATE TABLE IF NOT EXISTS ncei_monthly_cache (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        bbox                TEXT    NOT NULL,   -- exact NCEI boundingBox string
        month_start         TEXT    NOT NULL,   -- 'YYYY-MM-01'
        ws_mean_kts         REAL,
        ws_p90_kts          REAL,
        ws_max_kts          REAL,
        wdir_mean_deg       REAL,
        wave_hgt_mean_m     REAL,
        wave_hgt_p90_m      REAL,
        wave_dir_mean_deg   REAL,
        swell_hgt_mean_m    REAL,
        swell_dir_mean_deg  REAL,
        record_count        INTEGER NOT NULL DEFAULT 0,
        fetched_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (bbox, month_start)
    );

    -- ── WW3 real-time swell cache (Set 42 follow-up) ────────────────────────
    -- Caches era5.py::_do_fetch_ww3()'s 45-day summary, keyed by lat/lon
    -- rounded to the nearest whole degree (matching the +-0.5 deg query
    -- window, so nearby sites naturally share a cache row — same sharing
    -- rationale as ncei_monthly_cache's bbox key above). Unlike NCEI's
    -- climatological cache, this represents a rolling 45-day "current
    -- conditions" window, so it DOES expire — callers check fetched_at
    -- against a max-age (get_cached_ww3()'s default 24h) rather than
    -- treating any cached row as valid forever.
    CREATE TABLE IF NOT EXISTS ww3_realtime_cache (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        lat_bucket      REAL    NOT NULL,
        lon_bucket      REAL    NOT NULL,
        swh_mean_m      REAL,
        swh_p90_m       REAL,
        swd_mean_deg    REAL,
        swp_mean_s      REAL,
        record_count    INTEGER NOT NULL DEFAULT 0,
        fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (lat_bucket, lon_bucket)
    );

    -- ── ERA5 monthly marine cache (hybrid climatology) ───────────────────────
    -- Per calendar month per grid cell (0.25 deg buckets). Climatological — no expiry.
    CREATE TABLE IF NOT EXISTS era5_monthly_cache (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        lat_bucket      REAL    NOT NULL,
        lon_bucket      REAL    NOT NULL,
        month_start     TEXT    NOT NULL,
        ws_mean_kts     REAL,
        sh_mean_m       REAL,
        swh_mean_m      REAL,
        swp_mean_s      REAL,
        wg_mean_kts     REAL,
        record_count    INTEGER NOT NULL DEFAULT 1,
        fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (lat_bucket, lon_bucket, month_start)
    );

    -- ── ERA5 daily marine cache (Mission Timing tab) ─────────────────────────
    -- One row per calendar day per 0.25° grid cell. Climatological — no expiry.
    CREATE TABLE IF NOT EXISTS era5_daily_cache (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        lat_bucket      REAL    NOT NULL,
        lon_bucket      REAL    NOT NULL,
        date            TEXT    NOT NULL,
        ws_mean_kts     REAL,
        wg_max_kts      REAL,
        sh_mean_m       REAL,
        swh_mean_m      REAL,
        swp_mean_s      REAL,
        n_hours         INTEGER NOT NULL DEFAULT 0,
        fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (lat_bucket, lon_bucket, date)
    );

    -- ── Voyage schedules ─────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS voyage_schedules (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        site_id                 INTEGER NOT NULL REFERENCES sites(id),
        port_id                 INTEGER NOT NULL REFERENCES ports(id),
        analysis_id             INTEGER REFERENCES analyses(id),
        departure_date          DATE,
        platform_speed_kts      REAL    DEFAULT 6.0,
        fuel_consumption_mt_day REAL,
        fuel_price_usd_mt       REAL,
        num_tugs                INTEGER DEFAULT 2,
        tug_day_rate_usd        REAL,
        port_fees_usd           REAL,
        crew_day_rate_usd       REAL,
        weather_contingency_pct REAL    DEFAULT 15.0,
        round_trip              INTEGER DEFAULT 1,
        waypoints_json          TEXT,
        cost_summary_json       TEXT,
        created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS voyage_finalizations (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id              INTEGER NOT NULL REFERENCES projects(id),
        site_id                 INTEGER NOT NULL REFERENCES sites(id),
        load_port_id            INTEGER NOT NULL REFERENCES ports(id),
        finalized_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        notes                   TEXT    DEFAULT '',
        estimate_params_json    TEXT    NOT NULL,
        estimate_breakdown_json TEXT    NOT NULL,
        actual_breakdown_json   TEXT,
        actual_entered_at       TIMESTAMP,
        UNIQUE (project_id, site_id)
    );

    """)

    # Seed settings defaults (INSERT OR IGNORE so existing values are preserved)
    _SETTING_DEFAULTS = [
        ("go_threshold",            "0.70"),
        ("marginal_threshold",      "0.50"),
        ("ndbc_radius_nm",          "200"),
        ("platform_speed_kts",      "6.0"),
        ("fuel_consumption_mt_day", "18.0"),
        ("fuel_price_usd_mt",       "650.0"),
        ("num_tugs",                "2"),
        ("tug_day_rate_usd",        "25000.0"),
        ("port_fees_usd",           "15000.0"),
        ("crew_day_rate_usd",       "12000.0"),
        ("weather_contingency_pct", "15.0"),
        ("ncei_timeout_s",          "30"),
        # Direction parameters are excluded by default (Instruction 27A).
        # Direction parameter UI checkbox defaults updated in Instruction 27B.
        # Config DEFAULT_WEIGHTS redistribution also handled in Instruction 27B.
        # These settings rows ensure the DB state is correct before 27B runs.
        ("exclude_wind_dir",        "1"),
        ("exclude_sea_dir",         "1"),
        ("exclude_swell_dir",       "1"),
    ]
    c.executemany(
        "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
        _SETTING_DEFAULTS,
    )

    # ── Launcher tables (Part C) ──────────────────────────────────────────────
    c.executescript("""

    CREATE TABLE IF NOT EXISTS launcher_configs (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        vehicle_id              INTEGER REFERENCES vehicles(id),
        launcher_name           TEXT NOT NULL,
        launcher_type           TEXT NOT NULL,
        mount_method            TEXT,
        base_diameter_m         REAL,
        base_length_m           REAL,
        launcher_height_m       REAL,
        total_weight_kg         REAL,
        hold_down_pattern       TEXT,
        umbilical_count         INTEGER,
        deck_load_kpa           REAL,
        rail_gauge_m            REAL,
        rail_length_m           REAL,
        min_deck_area_m2        REAL,
        blast_radius_m          REAL,
        launch_azimuth_min_deg  REAL,
        launch_azimuth_max_deg  REAL,
        specs_verified          INTEGER DEFAULT 0,
        specs_verified_source   TEXT,
        specs_notes             TEXT,
        data_source             TEXT DEFAULT 'estimated',
        notes                   TEXT
    );

    CREATE TABLE IF NOT EXISTS launcher_vehicle_compat (
        launcher_id  INTEGER REFERENCES launcher_configs(id),
        vehicle_id   INTEGER REFERENCES vehicles(id),
        notes        TEXT,
        PRIMARY KEY (launcher_id, vehicle_id)
    );

    -- ── Platform contracts (Pre-28B-1) ────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS platform_contracts (
        id                           INTEGER PRIMARY KEY AUTOINCREMENT,
        platform_id                  INTEGER NOT NULL REFERENCES platforms(id),
        vessel_code                  TEXT NOT NULL,   -- copied from platform for display
        contract_code                TEXT NOT NULL UNIQUE,
        customer_name                TEXT NOT NULL,
        contract_tier                TEXT NOT NULL DEFAULT 'master',
        parent_contract_id           INTEGER REFERENCES platform_contracts(id),
        contract_start               DATE NOT NULL,
        contract_end                 DATE NOT NULL,
        status                       TEXT NOT NULL DEFAULT 'active',
        -- Warranted Operating Envelope (NULL = fall back to parent / vehicle)
        warranted_max_wind_kts       REAL,
        warranted_max_gust_kts       REAL,
        warranted_max_hs_m           REAL,
        warranted_max_swell_ht_m     REAL,
        warranted_max_swell_period_s REAL,
        -- Verification audit trail
        warranted_verified           INTEGER NOT NULL DEFAULT 0,
        warranted_verified_by        TEXT,
        warranted_verified_date      DATE,
        warranted_source_doc         TEXT,
        -- External document links (application stores links only, never copies)
        document_url                 TEXT,
        document_unc_path            TEXT,
        notes                        TEXT,
        created_at                   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at                   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    """)

    # ── Schema migrations: add new columns to existing tables ─────────────────
    # SQLite doesn't support IF NOT EXISTS for ALTER TABLE; we catch the error.
    _migrations = [
        # vehicles — physical characteristics
        ("vehicles", "height_m              REAL"),
        ("vehicles", "diameter_m            REAL"),
        ("vehicles", "gross_mass_kg         REAL"),
        # vehicles — performance
        ("vehicles", "leo_payload_kg        REAL"),
        ("vehicles", "sso_payload_kg        REAL"),
        ("vehicles", "gto_payload_kg        REAL"),
        # vehicles — propulsion
        ("vehicles", "stages                INTEGER"),
        ("vehicles", "propellant_stage1     TEXT"),
        ("vehicles", "propellant_stage2     TEXT"),
        ("vehicles", "propellant_upper      TEXT"),
        # vehicles — status / classification
        ("vehicles", "status                TEXT DEFAULT 'operational'"),
        ("vehicles", "first_flight_year     INTEGER"),
        ("vehicles", "country               TEXT"),
        ("vehicles", "manufacturer          TEXT"),
        # vehicles — constraint verification
        ("vehicles", "wind_hold_verified    INTEGER DEFAULT 0"),
        ("vehicles", "sea_state_verified    INTEGER DEFAULT 0"),
        ("vehicles", "data_source           TEXT    DEFAULT 'estimated'"),
        ("vehicles", "notes_extended        TEXT"),
        # vehicles — category FK and launcher preference
        ("vehicles", "category_id           INTEGER"),
        ("vehicles", "preferred_launcher_id INTEGER"),
        # platforms — existing additional fields
        ("platforms", "deck_area_m2          REAL"),
        ("platforms", "draft_m               REAL"),
        ("platforms", "min_depth_m           REAL DEFAULT 50.0"),
        ("platforms", "abs_approval          TEXT"),
        ("platforms", "first_deployment_yr   INTEGER"),
        ("platforms", "is_reference          INTEGER DEFAULT 0"),
        # platforms — vessel dimensions (Part B)
        ("platforms", "loa_m                 REAL"),
        ("platforms", "beam_m                REAL"),
        ("platforms", "grt                   REAL"),
        ("platforms", "nrt                   REAL"),
        ("platforms", "panama_canal_tons      REAL"),
        ("platforms", "displacement_t         REAL"),
        ("platforms", "min_air_gap_m          REAL"),
        ("platforms", "max_wave_crest_m       REAL"),
        ("platforms", "deck_elevation_m       REAL"),
        ("platforms", "dp_class               INTEGER"),
        ("platforms", "dp_class_notes         TEXT"),
        ("platforms", "class_society          TEXT"),
        ("platforms", "class_notation         TEXT"),
        ("platforms", "flag_state             TEXT"),
        ("platforms", "imo_number             TEXT"),
        # platforms — detailed draft fields
        ("platforms", "transit_draft_m        REAL"),
        ("platforms", "launch_draft_m         REAL"),
        # platforms — verification
        ("platforms", "specs_verified         INTEGER DEFAULT 0"),
        ("platforms", "specs_verified_source  TEXT"),
        ("platforms", "specs_notes            TEXT"),
        # platforms — pinned vessel code (Pre-28B-1)
        ("platforms", "vessel_code            TEXT"),
        # sites — coordinate code
        ("sites", "coord_code             TEXT"),
        # project_sites — project-level vehicle preference (nullable; unused
        # in the Analysis section until a future instruction set — see
        # DEFERRED note in CLAUDE.md)
        ("project_sites", "preferred_vehicle_id  INTEGER REFERENCES vehicles(id)"),
        # projects — naming and launch window
        ("projects", "code_name           TEXT    DEFAULT ''"),
        ("projects", "launch_date_start   TEXT"),
        ("projects", "launch_date_end     TEXT"),
        # projects — link to a governing platform contract (Pre-28B-1)
        ("projects", "platform_contract_id INTEGER REFERENCES platform_contracts(id)"),
        # platform_contracts — list-view archive flag (Pre-28B-2), mirrors
        # reports.is_archived exactly. UI-visibility only; does not affect
        # contract status or the vessel gate in modules/m1_site/contracts.py.
        ("platform_contracts", "is_archived INTEGER NOT NULL DEFAULT 0"),
        # projects — archive flag (Set 32), UI-visibility only
        ("projects", "is_archived INTEGER NOT NULL DEFAULT 0"),
        # ncei_monthly_cache — operability heatmap fields (main.html charts 5–6)
        ("ncei_monthly_cache", "pct_both_criteria REAL"),
        ("ncei_monthly_cache", "n_fully_operable_days INTEGER"),
    ]
    for table, col_def in _migrations:
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
        except Exception:
            pass  # column already exists

    # Assign vessel codes now that the platforms.vessel_code column exists.
    _assign_vessel_codes(conn)

    conn.commit()
    conn.close()

    # Ensure assets and reports directories exist
    from config import BASE_DIR, DOCS_DIR
    (BASE_DIR / "assets").mkdir(exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "reports").mkdir(exist_ok=True)

    print(f"Database initialized at {DB_PATH}")


if __name__ == "__main__":
    init_db()

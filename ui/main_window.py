"""
ui/main_window.py -- GatewayMainWindow: sidebar navigation + stacked section layout.
"""
import sys

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QStackedWidget,
    QStatusBar, QLabel, QApplication,
)
from PyQt6.QtGui import QFont, QIcon, QPixmap

from core.models import Site, Vehicle, Platform
from config import GATEWAY_PLATFORMS
from ui.styles import QSS_MAIN
from ui.sidebar import GatewaySidebar


# ── Built-in vehicle library ──────────────────────────────────────────────────

_VEHICLE_DEFAULTS: list[Vehicle] = [
    Vehicle(name="Firefly Alpha / Block 2", vehicle_class="slv_orb",
            recovery_mode="expendable",
            max_wind_kts=18,  max_gust_kts=25,  max_hs_m=1.5,
            max_swell_ht_m=2.0,  max_swell_period_s=12.0),
    Vehicle(name="Rocket Lab Electron",     vehicle_class="slv_orb",
            recovery_mode="expendable",
            max_wind_kts=15,  max_gust_kts=22,  max_hs_m=1.2,
            max_swell_ht_m=1.6,  max_swell_period_s=12.0),
    Vehicle(name="Minotaur IV",             vehicle_class="slv_orb",
            recovery_mode="expendable",
            max_wind_kts=20,  max_gust_kts=28,  max_hs_m=1.5,
            max_swell_ht_m=2.0,  max_swell_period_s=12.0),
    Vehicle(name="Pegasus XL",              vehicle_class="slv_orb",
            recovery_mode="expendable",
            max_wind_kts=28,  max_gust_kts=38,  max_hs_m=2.2,
            max_swell_ht_m=2.8,  max_swell_period_s=14.0),
    Vehicle(name="ABL RS1",                 vehicle_class="slv_orb",
            recovery_mode="expendable",
            max_wind_kts=17,  max_gust_kts=24,  max_hs_m=1.4,
            max_swell_ht_m=1.8,  max_swell_period_s=12.0),
    Vehicle(name="Vega-C",                  vehicle_class="slv_orb",
            recovery_mode="expendable",
            max_wind_kts=22,  max_gust_kts=30,  max_hs_m=1.7,
            max_swell_ht_m=2.2,  max_swell_period_s=13.0),
    Vehicle(name="Antares 230+",            vehicle_class="mlv_orb",
            recovery_mode="expendable",
            max_wind_kts=25,  max_gust_kts=35,  max_hs_m=2.0,
            max_swell_ht_m=2.5,  max_swell_period_s=14.0),
    Vehicle(name="Falcon 9",                vehicle_class="mlv_orb",
            recovery_mode="droneship",
            max_wind_kts=30,  max_gust_kts=40,  max_hs_m=2.5,
            max_swell_ht_m=3.0,  max_swell_period_s=14.0),
    Vehicle(name="Atlas V 401",             vehicle_class="mlv_orb",
            recovery_mode="expendable",
            max_wind_kts=28,  max_gust_kts=38,  max_hs_m=2.0,
            max_swell_ht_m=2.5,  max_swell_period_s=14.0),
    Vehicle(name="Vulcan Centaur",          vehicle_class="mlv_orb",
            recovery_mode="expendable",
            max_wind_kts=30,  max_gust_kts=40,  max_hs_m=2.2,
            max_swell_ht_m=2.8,  max_swell_period_s=14.0),
    Vehicle(name="New Glenn",               vehicle_class="mlv_orb",
            recovery_mode="droneship",
            max_wind_kts=32,  max_gust_kts=45,  max_hs_m=2.8,
            max_swell_ht_m=3.5,  max_swell_period_s=15.0),
    Vehicle(name="Ariane 6",                vehicle_class="mlv_orb",
            recovery_mode="expendable",
            max_wind_kts=27,  max_gust_kts=37,  max_hs_m=2.2,
            max_swell_ht_m=2.8,  max_swell_period_s=13.0),
    Vehicle(name="H3 (JAXA)",               vehicle_class="mlv_orb",
            recovery_mode="expendable",
            max_wind_kts=26,  max_gust_kts=36,  max_hs_m=2.0,
            max_swell_ht_m=2.5,  max_swell_period_s=13.0),
    Vehicle(name="New Shepard",             vehicle_class="slv_sub",
            recovery_mode="rtls",
            max_wind_kts=22,  max_gust_kts=30,  max_hs_m=1.8,
            max_swell_ht_m=2.2,  max_swell_period_s=12.0),
    Vehicle(name="Hypersonic test vehicle", vehicle_class="slv_sub",
            recovery_mode="expendable",
            max_wind_kts=25,  max_gust_kts=35,  max_hs_m=2.0,
            max_swell_ht_m=2.5,  max_swell_period_s=12.0),
]

# Section key → stacked widget index
_SECTION_INDEX: dict[str, int] = {
    "projects":   0,
    "sites":      1,
    "analysis":   2,
    "vehicles":   3,
    "launchers":  4,
    "comparison": 5,
    "mission_timing": 6,
    "ndbc":       7,
    "forecast":   8,
    "ports":      9,
    "mission_economics": 10,
    "vessels":    11,
    "contracts":  12,
    "reports":    13,
    "history":    14,
    "settings":   15,
    "quick_analysis": 16,
}


def _load_vehicles_from_db() -> list[Vehicle]:
    try:
        from core.database import get_connection
        conn = get_connection()
        rows = conn.execute(
            "SELECT name, vehicle_class, recovery_mode, "
            "max_wind_kts, max_gust_kts, max_hs_m, max_swell_ht_m, max_swell_period_s, "
            "max_wind_dir_tolerance_deg, max_sea_dir_tolerance_deg, "
            "max_swell_dir_tolerance_deg, id "
            "FROM vehicles ORDER BY name"
        ).fetchall()
        conn.close()
        result = []
        for r in rows:
            result.append(Vehicle(
                name=r["name"],
                vehicle_class=r["vehicle_class"],
                recovery_mode=r["recovery_mode"],
                max_wind_kts=r["max_wind_kts"],
                max_gust_kts=r["max_gust_kts"],
                max_hs_m=r["max_hs_m"],
                max_swell_ht_m=r["max_swell_ht_m"],
                max_swell_period_s=r["max_swell_period_s"],
                max_wind_dir_tolerance_deg=r["max_wind_dir_tolerance_deg"] or 45.0,
                max_sea_dir_tolerance_deg=r["max_sea_dir_tolerance_deg"] or 60.0,
                max_swell_dir_tolerance_deg=r["max_swell_dir_tolerance_deg"] or 60.0,
                id=r["id"],
            ))
        return result
    except Exception:
        return []


# ── Main window ───────────────────────────────────────────────────────────────

class GatewayMainWindow(QMainWindow):
    """Root application window — sidebar navigation + QStackedWidget content."""

    def __init__(self):
        super().__init__()

        # Clear any stale NDBC station selection from a prior session so the
        # Forecast section starts model-only until the user selects stations
        # in the current session (Pre-28B / Step 11 Fix A). Runs once per launch.
        from core.settings import set_session
        set_session("selected_ndbc_stations", "[]")
        # Clear any stale site/project activation from a prior session (Step 4).
        # Same no-persistence-across-restart precedent as the NDBC clear above.
        set_session("active_site_id", "")
        set_session("active_project_id", "")

        self.setWindowTitle(
            "Seagate Space — Gateway Launch Operations  "
            "Site Analysis & Mission Planning"
        )
        self.setMinimumSize(1280, 800)

        # Window icon from logo
        from config import LOGO_PATH
        icon_pixmap = QPixmap(str(LOGO_PATH))
        if not icon_pixmap.isNull():
            self.setWindowIcon(QIcon(icon_pixmap))

        # Apply global dark theme
        self.setStyleSheet(QSS_MAIN)

        # ── Shared application state ──────────────────────────────────────────
        self.site: Site | None = None
        # Set only by the By Project view's Activate/Deactivate pairing (sites.py
        # Step 3) and by open_project() below (which also keeps it in sync for
        # the vessel pre-check contract gate).
        self.active_project_id: int | None = None
        # Project-mode state (Project-Scoped UI Overhaul). open_project_id is the
        # currently-opened project; open_project_sites holds its Site objects,
        # loaded from project_sites, and drives the Analysis site selector and
        # the Comparison auto-loaded site list.
        self.open_project_id: int | None = None
        self.open_project_name: str = ""
        self.open_project_sites: list[Site] = []

        vehicles = _load_vehicles_from_db() or _VEHICLE_DEFAULTS
        self.vehicles: list[Vehicle] = vehicles
        self.vehicle: Vehicle        = vehicles[0]

        self.platforms: list[Platform] = [
            Platform(
                name=p["name"],
                hull_type=p["hull_type"],
                hull_motion_factor=p["hull_motion_factor"],
                dp_capable=p["dp_capable"],
                max_hs_operating_m=p["max_hs_operating_m"],
                typical_depth_m=p["typical_depth_m"],
                payload_class=p["payload_class"],
            )
            for p in GATEWAY_PLATFORMS
        ]
        self.platform: Platform = self.platforms[1]  # Gateway X default

        # ── Build section widgets (late imports to avoid circulars) ───────────
        from ui.sections.projects    import ProjectsSection
        from ui.sections.sites       import SitesSection
        from ui.analysis_tab         import AnalysisTab
        from ui.sections.vehicles    import VehiclesSection
        from ui.sections.launchers   import LaunchersSection
        from ui.sections.comparison  import ComparisonSection
        from ui.sections.mission_timing import MissionTimingSection
        from ui.sections.ndbc        import NDCBSection
        from ui.sections.forecast    import ForecastSection
        from ui.ports_tab            import PortsTab
        from ui.sections.vessels     import VesselsSection
        from ui.sections.contracts   import ContractsSection
        from ui.sections.reports     import ReportsSection
        from ui.sections.history     import HistorySection
        from ui.sections.mission_economics import MissionEconomicsSection
        from ui.sections.settings    import SettingsTab
        from ui.sections.quick_analysis import QuickAnalysisSection

        self.projects_section   = ProjectsSection(self)
        self.sites_section      = SitesSection(self)
        self.analysis_tab       = AnalysisTab(self)
        self.vehicles_section   = VehiclesSection(self)
        self.launchers_section  = LaunchersSection(self)
        self.comparison_section = ComparisonSection(self)
        self.mission_timing_section = MissionTimingSection(self)
        self.ndbc_section       = NDCBSection(self)
        self.forecast_section   = ForecastSection(self)
        self.ports_tab          = PortsTab(self)
        self.mission_economics_section = MissionEconomicsSection(self)
        self.vessels_section    = VesselsSection(self)
        self.contracts_section  = ContractsSection(self)
        self.reports_section    = ReportsSection(self)
        self.history_section    = HistorySection(self)
        self.settings_tab       = SettingsTab(self)
        self.quick_analysis_section = QuickAnalysisSection(self)

        # ── Root layout: sidebar | stacked content ────────────────────────────
        root_widget = QWidget()
        root_widget.setStyleSheet("background-color: #0f1923;")
        root_layout = QHBoxLayout(root_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = GatewaySidebar(self)
        self.sidebar.section_changed.connect(self._on_section_changed)
        self.sidebar.project_closed.connect(self.close_project)
        root_layout.addWidget(self.sidebar)

        # Cross-section signals
        self.sites_section.site_saved.connect(
            self.comparison_section.refresh_site_list
        )

        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background-color: #0f1923;")
        # Order must match _SECTION_INDEX
        for widget in [
            self.projects_section,   # 0
            self.sites_section,      # 1
            self.analysis_tab,       # 2
            self.vehicles_section,   # 3
            self.launchers_section,  # 4
            self.comparison_section, # 5
            self.mission_timing_section,  # 6
            self.ndbc_section,       # 7
            self.forecast_section,   # 8
            self.ports_tab,          # 9
            self.mission_economics_section,  # 10
            self.vessels_section,    # 11
            self.contracts_section,  # 12
            self.reports_section,    # 13
            self.history_section,    # 14
            self.settings_tab,       # 15
            self.quick_analysis_section,  # 16
        ]:
            self.stack.addWidget(widget)

        root_layout.addWidget(self.stack, 1)
        self.setCentralWidget(root_widget)

        # ── Status bar ────────────────────────────────────────────────────────
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._status_left  = QLabel("Ready  —  enter site coordinates to begin.")
        self._status_right = QLabel("No site selected")
        sb.addWidget(self._status_left, 1)
        sb.addPermanentWidget(self._status_right)

        # Default view: Sites
        self.stack.setCurrentIndex(0)

    # ── Cross-section coordination ────────────────────────────────────────────

    def reload_platforms(self) -> None:
        """Reload platforms from DB and notify sections that show a platform list."""
        if hasattr(self, "sites_section"):
            self.sites_section._reload_platforms()

    def status(self, msg: str) -> None:
        self._status_left.setText(msg)

    def on_site_changed(self) -> None:
        """Called by SitesSection after site/vehicle have been updated.

        Resolves self.platform from the active site's own platform_id (Set
        34, item 11 fix) — previously self.platform stayed pinned to its
        __init__ default ("Gateway X") regardless of which platform the
        active site actually specified, so Analysis always showed the
        wrong platform for any site assigned a different one. Falls back
        to leaving self.platform unchanged if the site has no platform_id
        set, or the lookup fails for any reason — never raises.
        """
        if self.site and self.site.platform_id:
            try:
                from core.database import get_connection
                conn = get_connection()
                row = conn.execute(
                    "SELECT * FROM platforms WHERE id=?", (self.site.platform_id,)
                ).fetchone()
                conn.close()
                if row:
                    self.platform = Platform(
                        id=row["id"], name=row["name"],
                        hull_type=row["hull_type"],
                        hull_motion_factor=row["hull_motion_factor"],
                        dp_capable=bool(row["dp_capable"]),
                        max_hs_operating_m=row["max_hs_operating_m"],
                        typical_depth_m=row["typical_depth_m"],
                        payload_class=row["payload_class"] or "",
                        notes=row["notes"] or "",
                    )
            except Exception:
                pass

        self.analysis_tab.on_site_changed()
        self.ports_tab.on_site_changed()
        econ = getattr(self, "mission_economics_section", None)
        if econ is not None and hasattr(econ, "on_site_changed"):
            econ.on_site_changed()
        if self.site:
            coord = self.site.coord_str
            self._status_right.setText(
                f"{coord}  |  {self.vehicle.name}  |  {self.platform.name}"
            )
            self.status(f"Site applied: {coord}")

    # ── Project mode ──────────────────────────────────────────────────────────

    def _load_open_project_sites(self) -> None:
        """Load the Site objects for the currently open project into
        self.open_project_sites (empty when no project is open)."""
        self.open_project_sites = []
        if self.open_project_id is None:
            return
        try:
            from modules.m1_site.project_sites import list_project_sites
            from modules.m1_site.site_config import get_site
            for row in list_project_sites(self.open_project_id):
                try:
                    self.open_project_sites.append(get_site(row["site_id"]))
                except Exception:
                    pass
        except Exception:
            pass

    def open_project(self, project_id: int, project_name: str = "") -> None:
        """Enter project mode: reveal the project-scoped sidebar group, load the
        project's sites, activate the first one, and jump to the Analysis tab.

        All project sites are considered "activated" for the session — the
        Analysis tab exposes a selector when the project has more than one."""
        self.open_project_id = project_id
        self.open_project_name = project_name
        self.active_project_id = project_id  # keep the contract gate in sync
        from core.settings import set_session
        set_session("active_project_id", str(project_id))

        self._load_open_project_sites()
        self.sidebar.set_project_mode(True, project_name)

        # Activate the first project site (if any) so downstream single-site
        # consumers (Ports, Forecast) have a site to work with.
        self.site = self.open_project_sites[0] if self.open_project_sites else None

        # Notify project-aware sections (guarded — not every section implements
        # the hook).
        for section in (
            self.analysis_tab, self.comparison_section, self.reports_section,
            self.history_section, self.ports_tab, self.forecast_section,
            self.mission_timing_section, self.ndbc_section,
            self.mission_economics_section,
        ):
            hook = getattr(section, "on_project_changed", None)
            if callable(hook):
                try:
                    hook()
                except Exception:
                    pass

        self.on_site_changed()
        self.sidebar.select_section("analysis")
        self.stack.setCurrentIndex(_SECTION_INDEX["analysis"])

    def close_project(self) -> None:
        """Exit project mode: hide the project-scoped sidebar group and return
        to the Projects (home) view."""
        self.open_project_id = None
        self.open_project_name = ""
        self.open_project_sites = []
        self.active_project_id = None
        self.site = None
        from core.settings import set_session
        set_session("active_project_id", "")

        self.sidebar.set_project_mode(False)
        for section in (
            self.analysis_tab, self.comparison_section, self.reports_section,
            self.history_section, self.ports_tab, self.forecast_section,
            self.mission_timing_section, self.ndbc_section,
            self.mission_economics_section,
        ):
            hook = getattr(section, "on_project_changed", None)
            if callable(hook):
                try:
                    hook()
                except Exception:
                    pass

        self.sidebar.select_section("projects")
        self.stack.setCurrentIndex(_SECTION_INDEX["projects"])

    def refresh_open_project_sites(self) -> None:
        """Reload the open project's sites and re-notify the Analysis/Comparison
        selectors. Called by Projects after a site is added/created/removed."""
        if self.open_project_id is None:
            return
        prev_site_id = getattr(self.site, "id", None)
        self._load_open_project_sites()
        # Preserve the currently active site if it's still in the project.
        if prev_site_id is not None:
            match = next(
                (s for s in self.open_project_sites if s.id == prev_site_id), None
            )
            self.site = match or (
                self.open_project_sites[0] if self.open_project_sites else None
            )
        else:
            self.site = self.open_project_sites[0] if self.open_project_sites else None

        for section in (self.analysis_tab, self.comparison_section, self.mission_timing_section, self.ndbc_section):
            hook = getattr(section, "on_project_changed", None)
            if callable(hook):
                try:
                    hook()
                except Exception:
                    pass
        self.on_site_changed()

    # ── Sidebar navigation ────────────────────────────────────────────────────

    def _on_section_changed(self, key: str) -> None:
        idx = _SECTION_INDEX.get(key, 0)
        self.stack.setCurrentIndex(idx)


# ── App entry point ───────────────────────────────────────────────────────────

def launch_ui() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Gateway Launch Operations")
    app.setFont(QFont("Segoe UI", 9))
    win = GatewayMainWindow()
    win.show()
    sys.exit(app.exec())

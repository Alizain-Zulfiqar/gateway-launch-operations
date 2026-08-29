"""
ui/sidebar.py -- GatewaySidebar: fixed-width dark sidebar with NavButtons.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QButtonGroup, QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QImage, QPixmap
from config import LOGO_PATH


_NAV_BTN_STYLE = """
QPushButton {
    background-color: transparent;
    border: none;
    border-left-width: 4px;
    border-left-style: solid;
    border-left-color: transparent;
    border-radius: 0px;
    color: #94a3b8;
    text-align: left;
    padding: 0px 12px 0px 12px;
    font-size: 16pt;
}
QPushButton:hover {
    background-color: #1e2d3d;
    color: #f1f5f9;
    border-left-color: transparent;
}
QPushButton:checked {
    background-color: #1e3a5f;
    color: #ffffff;
    font-weight: bold;
    border-left-color: #2563eb;
}
"""


class NavButton(QPushButton):
    """48px tall sidebar navigation button with active/hover states."""

    def __init__(self, icon_char: str, label: str, tooltip: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFlat(True)
        self.setMinimumHeight(48)
        self.setMaximumHeight(48)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setText(f"  {icon_char}   {label}")
        self.setStyleSheet(_NAV_BTN_STYLE)
        if tooltip:
            self.setToolTip(tooltip)


def _separator() -> QFrame:
    sep = QFrame()
    sep.setFixedHeight(1)
    sep.setStyleSheet("background-color: #1e2d3d; border: none;")
    return sep


class GatewaySidebar(QWidget):
    """260px fixed dark sidebar.  Emits section_changed(str) on nav click.

    Two-level navigation: a Home layer (Projects + Quick Analysis, always
    visible) and a Project layer (all mission tabs, shown only while a
    project is open via set_project_mode()).
    """

    section_changed = pyqtSignal(str)
    project_closed  = pyqtSignal()

    # Always-visible home navigation.
    _HOME_NAV = [
        ("\U0001f4c1", "Projects",       "projects"),
        ("\U0001f4c8", "Quick Analysis", "quick_analysis"),
    ]

    # Project-scoped navigation — hidden until a project is opened.
    _PROJECT_NAV = [
        ("\U0001f310", "Sites",         "sites"),
        ("\U0001f4ca", "Analysis",      "analysis"),
        ("\U0001f680", "Vehicles",      "vehicles"),
        ("\U0001f527", "Launchers",     "launchers"),
        ("\U0001f500", "Comparison",    "comparison"),
        ("\U0001f4c5", "Mission Timing", "mission_timing"),
        ("\U0001f4e1", "NDBC Stations", "ndbc"),
        ("\U0001f324", "Forecast",      "forecast"),
        ("⚓",     "Ports",         "ports"),
        ("\U0001f4b0", "Mission Economics", "mission_economics"),
        ("\U0001f6e0", "Vessels",       "vessels"),
        ("\U0001f4dc", "Contracts",     "contracts"),
        ("\U0001f4c4", "Reports",       "reports"),
        ("\U0001f550", "History",       "history"),
    ]

    _TOOLTIPS = {
        "projects":  "Manage mission projects",
        "quick_analysis": "Run an ad-hoc, unsaved analysis",
        "sites":     "Define and select launch sites",
        "analysis":  "Run probability analysis",
        "vehicles":  "Manage launch vehicles",
        "launchers": "Configure launcher systems",
        "comparison": "Compare site analyses",
        "mission_timing": "Consecutive GO-day windows for launch planning",
        "ndbc":      "View NDBC weather stations",
        "forecast":  "Live weather forecasts",
        "ports":     "Identify recovery ports",
        "mission_economics": "Finalized estimate vs actual voyage costs",
        "vessels":   "Define vessel specifications",
        "contracts": "Manage platform contracts",
        "reports":   "Generate and view reports",
        "history":   "Session activity history",
    }

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedWidth(260)
        self.setStyleSheet("background-color: #151c27;")

        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)

        self._section_keys: list[str] = []
        self._buttons: list[NavButton] = []
        self._buttons_by_key: dict[str, NavButton] = {}
        self._btn_index = 0

        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_logo_section(self) -> QWidget:
        container = QWidget()
        container.setStyleSheet("background-color: #151c27;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 8)
        layout.setSpacing(4)

        logo_label = QLabel()
        logo_label.setMinimumHeight(50)
        logo_label.setMaximumHeight(80)
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_label.setStyleSheet("background-color: transparent;")

        pixmap = QPixmap()
        if LOGO_PATH.exists():
            pixmap = QPixmap(str(LOGO_PATH))
            if pixmap.isNull():
                img = QImage(str(LOGO_PATH))
                if not img.isNull():
                    pixmap = QPixmap.fromImage(img)

        if not pixmap.isNull():
            scaled = pixmap.scaledToWidth(
                228, Qt.TransformationMode.SmoothTransformation
            )
            logo_label.setPixmap(scaled)
        else:
            logo_label.setText("Seagate Space")
            logo_label.setStyleSheet("""
                color: #f1f5f9;
                font-size: 20px;
                font-weight: 700;
                letter-spacing: 0.03em;
                background-color: transparent;
                padding: 8px 0px;
            """)

        layout.addWidget(logo_label)

        title = QLabel("GATEWAY LAUNCH OPERATIONS")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("""
            color: #f1f5f9;
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 0.10em;
            background-color: transparent;
            padding: 4px 0px 0px 0px;
        """)
        layout.addWidget(title)

        subtitle = QLabel("Site Analysis & Mission Planning")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("""
            color: #64748b;
            font-size: 9px;
            background-color: transparent;
            padding: 0px 0px 8px 0px;
        """)
        layout.addWidget(subtitle)

        return container

    def _add_nav_button(self, layout, icon: str, label: str, key: str) -> NavButton:
        """Create a NavButton, register it with the button group, and add it to
        the given layout. Keeps _section_keys / _buttons index-aligned with the
        button group ids so _on_nav_clicked() can map a click back to its key."""
        tooltip = self._TOOLTIPS.get(key, "")
        btn = NavButton(icon, label, tooltip, self)
        self._btn_group.addButton(btn, self._btn_index)
        self._section_keys.append(key)
        self._buttons.append(btn)
        self._buttons_by_key[key] = btn
        btn.clicked.connect(self._on_nav_clicked)
        layout.addWidget(btn)
        self._btn_index += 1
        return btn

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_logo_section())
        root.addWidget(_separator())

        # ── Home nav buttons (always visible) ─────────────────────────────────
        for icon, label, key in self._HOME_NAV:
            self._add_nav_button(root, icon, label, key)

        # ── Project group (hidden until a project is opened) ───────────────────
        self._project_container = QWidget()
        self._project_container.setStyleSheet("background-color: #151c27;")
        pc = QVBoxLayout(self._project_container)
        pc.setContentsMargins(0, 0, 0, 0)
        pc.setSpacing(0)

        pc.addWidget(_separator())
        self._project_header = QLabel("PROJECT")
        self._project_header.setWordWrap(True)
        self._project_header.setContentsMargins(16, 8, 16, 2)
        self._project_header.setStyleSheet(
            "color: #93c5fd; font-size: 9pt; font-weight: 700;"
            " letter-spacing: 0.06em; background: transparent;"
        )
        pc.addWidget(self._project_header)

        self._close_project_btn = QPushButton("✕  Close Project")
        self._close_project_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #94a3b8; border: none;"
            " text-align: left; padding: 2px 16px 8px 16px; font-size: 9pt; }"
            "QPushButton:hover { color: #fca5a5; }"
        )
        self._close_project_btn.clicked.connect(lambda: self.project_closed.emit())
        pc.addWidget(self._close_project_btn)

        for icon, label, key in self._PROJECT_NAV:
            self._add_nav_button(pc, icon, label, key)

        root.addWidget(self._project_container)
        self._project_container.setVisible(False)

        root.addStretch(1)
        root.addWidget(_separator())

        # ── Coord convention block ────────────────────────────────────────────
        coord_lbl = QLabel("+Lat = N  −Lat = S\n+Lon = E  −Lon = W")
        coord_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        coord_lbl.setContentsMargins(0, 8, 0, 8)
        coord_lbl.setStyleSheet(
            "color: #64748b; font-size: 8pt; background: transparent; line-height: 160%;"
        )
        root.addWidget(coord_lbl)

        # ── Settings button (always visible) ──────────────────────────────────
        settings_btn = NavButton("⚙", "Settings", "Application settings", self)
        settings_btn.setObjectName("settingsBtn")
        self._btn_group.addButton(settings_btn, self._btn_index)
        self._section_keys.append("settings")
        self._buttons.append(settings_btn)
        self._buttons_by_key["settings"] = settings_btn
        settings_btn.clicked.connect(self._on_nav_clicked)
        self._btn_index += 1
        root.addWidget(settings_btn)

        # ── Version label ─────────────────────────────────────────────────────
        ver_lbl = QLabel("v0.1.0")
        ver_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver_lbl.setContentsMargins(0, 6, 0, 10)
        ver_lbl.setStyleSheet("color: #374151; font-size: 7.5pt; background: transparent;")
        root.addWidget(ver_lbl)

        # Default: Projects selected (home layer)
        self._buttons_by_key["projects"].setChecked(True)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_nav_clicked(self) -> None:
        btn = self._btn_group.checkedButton()
        if btn is None:
            return
        idx = self._btn_group.id(btn)
        self.section_changed.emit(self._section_keys[idx])

    # ── Public API ────────────────────────────────────────────────────────────

    def select_section(self, key: str) -> None:
        """Programmatically activate a nav button by its section key."""
        btn = self._buttons_by_key.get(key)
        if btn is not None:
            btn.setChecked(True)

    def set_project_mode(self, enabled: bool, project_name: str = "") -> None:
        """Show or hide the project-scoped nav group. When enabling, the header
        shows the open project's name."""
        self._project_container.setVisible(enabled)
        if enabled:
            name = project_name.strip() or "Untitled"
            self._project_header.setText(f"PROJECT:  {name}")

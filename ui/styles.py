"""
ui/styles.py -- Global dark QSS stylesheet for Gateway Launch Operations.
"""

from PyQt6.QtWidgets import QTableWidget


def apply_table_colors(
    table: QTableWidget,
    header_color: str = '#94a3b8',
    cell_color: str = '#f1f5f9',
    alt_bg: str = '#252d3a',
    base_bg: str = '#1e2530',
) -> None:
    """Apply consistent dark-theme colors to any QTableWidget."""
    table.setStyleSheet(f"""
        QTableWidget {{
            color: {cell_color};
            background-color: {base_bg};
            alternate-background-color: {alt_bg};
            gridline-color: #374151;
            border: 1px solid #374151;
            selection-background-color: #2563eb;
            selection-color: #ffffff;
        }}
        QHeaderView::section {{
            color: {header_color};
            background-color: #151c27;
            font-size: 11px;
            font-weight: 500;
            padding: 6px 8px;
            border-bottom: 1px solid #374151;
            border-right: 1px solid #374151;
        }}
    """)
    table.setAlternatingRowColors(True)


QSS_MAIN = """
/* ── Root window & generic widgets ─────────────────────────────────────── */
QMainWindow, QDialog {
    background-color: #0f1923;
    color: #e2e8f0;
}

QWidget {
    background-color: #0f1923;
    color: #e2e8f0;
    font-family: "Segoe UI", sans-serif;
    font-size: 9pt;
}

/* ── Labels ─────────────────────────────────────────────────────────────── */
QLabel {
    background: transparent;
    color: #e2e8f0;
}

QLabel#sectionTitle {
    font-size: 14pt;
    font-weight: bold;
    color: #f1f5f9;
    padding-bottom: 4px;
}

QLabel#fieldHint {
    font-size: 8pt;
    color: #64748b;
}

/* ── Line edits & date edits ────────────────────────────────────────────── */
QLineEdit, QDateEdit, QTimeEdit, QDateTimeEdit {
    background-color: #1a2233;
    border: 1px solid #374151;
    border-radius: 4px;
    color: #e2e8f0;
    padding: 4px 8px;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}

QLineEdit:focus, QDateEdit:focus, QTimeEdit:focus { border-color: #2563eb; }
QLineEdit:disabled { background-color: #111827; color: #4b5563; border-color: #1f2937; }

/* ── Spin boxes — explicit button sub-elements required for Windows hit-test */
QSpinBox, QDoubleSpinBox {
    background-color: #2d3748;
    border: 1px solid #374151;
    border-radius: 4px;
    padding: 4px 28px 4px 8px;
    color: #f1f5f9;
    selection-background-color: #2563eb;
    min-height: 28px;
}
QSpinBox:focus, QDoubleSpinBox:focus { border-color: #2563eb; }
QSpinBox:disabled, QDoubleSpinBox:disabled {
    background-color: #111827; color: #4b5563; border-color: #1f2937;
}
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 20px;
    height: 14px;
    border-left: 1px solid #374151;
    border-bottom: 1px solid #374151;
    border-top-right-radius: 4px;
    background-color: #374151;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover { background-color: #4b5563; }
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed { background-color: #2563eb; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    width: 0; height: 0; image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 6px solid #94a3b8;
}
QSpinBox::up-arrow:pressed, QDoubleSpinBox::up-arrow:pressed { border-bottom-color: #ffffff; }
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 20px;
    height: 14px;
    border-left: 1px solid #374151;
    border-top: 1px solid #374151;
    border-bottom-right-radius: 4px;
    background-color: #374151;
}
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background-color: #4b5563; }
QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed { background-color: #2563eb; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    width: 0; height: 0; image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid #94a3b8;
}
QSpinBox::down-arrow:pressed, QDoubleSpinBox::down-arrow:pressed { border-top-color: #ffffff; }

/* ── Combo boxes ────────────────────────────────────────────────────────── */
QComboBox {
    background-color: #1a2233;
    border: 1px solid #374151;
    border-radius: 4px;
    color: #e2e8f0;
    padding: 4px 8px;
    min-height: 24px;
}

QComboBox:focus { border-color: #2563eb; }
QComboBox:disabled { background-color: #111827; color: #4b5563; }

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #94a3b8;
    width: 0;
    height: 0;
}

QComboBox QAbstractItemView {
    background-color: #1e2d3d;
    border: 1px solid #374151;
    color: #e2e8f0;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
    outline: none;
}

/* ── Push buttons ───────────────────────────────────────────────────────── */
QPushButton {
    background-color: #1e2d3d;
    border: 1px solid #374151;
    border-radius: 4px;
    color: #e2e8f0;
    padding: 5px 16px;
    min-height: 26px;
}

QPushButton:hover {
    background-color: #2d3f55;
    border-color: #4b5563;
}

QPushButton:pressed {
    background-color: #1a2d47;
}

QPushButton:disabled {
    background-color: #111827;
    color: #4b5563;
    border-color: #1f2937;
}

QPushButton#primaryBtn {
    background-color: #2563eb;
    border-color: #1d4ed8;
    color: #ffffff;
    font-weight: bold;
}

QPushButton#primaryBtn:hover { background-color: #1d4ed8; }
QPushButton#primaryBtn:pressed { background-color: #1e40af; }
QPushButton#primaryBtn:disabled { background-color: #1e3a5f; color: #64748b; }

/* ── Group boxes ─────────────────────────────────────────────────────────── */
QGroupBox {
    background-color: #111827;
    border: 1px solid #374151;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 10px;
    color: #94a3b8;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: #94a3b8;
    background-color: #111827;
}

/* ── Frames ──────────────────────────────────────────────────────────────── */
QFrame#card {
    background-color: #111827;
    border: 1px solid #374151;
    border-radius: 6px;
}

QFrame#divider {
    background-color: #374151;
    max-height: 1px;
    min-height: 1px;
    border: none;
}

/* ── Tables ──────────────────────────────────────────────────────────────── */
QTableWidget, QTableView {
    background-color: #111827;
    alternate-background-color: #141f2e;
    gridline-color: #1f2937;
    color: #e2e8f0;
    border: 1px solid #374151;
    selection-background-color: #1e3a5f;
    selection-color: #ffffff;
    outline: none;
}

QHeaderView::section {
    background-color: #1a2233;
    color: #94a3b8;
    border: none;
    border-right: 1px solid #374151;
    border-bottom: 1px solid #374151;
    padding: 4px 8px;
    font-weight: bold;
    font-size: 8.5pt;
}

QHeaderView::section:last { border-right: none; }

/* ── Tab widget (inner tabs used by Settings) ────────────────────────────── */
QTabWidget::pane {
    background-color: #111827;
    border: 1px solid #374151;
    border-radius: 0 4px 4px 4px;
}

QTabBar::tab {
    background-color: #1a2233;
    color: #94a3b8;
    border: 1px solid #374151;
    border-bottom: none;
    border-radius: 4px 4px 0 0;
    padding: 5px 14px;
    min-width: 60px;
}

QTabBar::tab:selected {
    background-color: #111827;
    color: #f1f5f9;
    border-bottom-color: #111827;
}

QTabBar::tab:hover:!selected {
    background-color: #1e2d3d;
    color: #e2e8f0;
}

/* ── Scroll bars ─────────────────────────────────────────────────────────── */
QScrollBar:vertical {
    background-color: #0f1923;
    width: 8px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background-color: #374151;
    border-radius: 4px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover { background-color: #4b5563; }

QScrollBar:horizontal {
    background-color: #0f1923;
    height: 8px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background-color: #374151;
    border-radius: 4px;
    min-width: 20px;
}

QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }

/* ── Sliders ─────────────────────────────────────────────────────────────── */
QSlider::groove:horizontal {
    height: 4px;
    background-color: #374151;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    background-color: #2563eb;
    border: none;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}

QSlider::sub-page:horizontal {
    background-color: #2563eb;
    border-radius: 2px;
}

/* ── Status bar ──────────────────────────────────────────────────────────── */
QStatusBar {
    background-color: #0a1020;
    color: #64748b;
    border-top: 1px solid #1f2937;
    font-size: 8pt;
}

QStatusBar QLabel { background: transparent; color: #64748b; }

/* ── Stacked widget (no additional styling needed) ───────────────────────── */
QStackedWidget { background: transparent; }

/* ── Checkboxes & radio buttons ──────────────────────────────────────────── */
QCheckBox, QRadioButton {
    color: #e2e8f0;
    spacing: 6px;
    background: transparent;
}

QCheckBox::indicator, QRadioButton::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #374151;
    border-radius: 3px;
    background-color: #1a2233;
}

QCheckBox::indicator:checked {
    background-color: #2563eb;
    border-color: #2563eb;
}

QRadioButton::indicator { border-radius: 7px; }
QRadioButton::indicator:checked { background-color: #2563eb; border-color: #2563eb; }

/* ── Message boxes ───────────────────────────────────────────────────────── */
QMessageBox {
    background-color: #1a2233;
    color: #e2e8f0;
}

/* ── Tool tips ───────────────────────────────────────────────────────────── */
QToolTip {
    background-color: #1e2d3d;
    color: #e2e8f0;
    border: 1px solid #374151;
    border-radius: 3px;
    padding: 4px 8px;
    font-size: 8.5pt;
}
"""

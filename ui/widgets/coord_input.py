"""
ui/widgets/coord_input.py -- Dual-format coordinate input widget.

Supports decimal degrees, DDM, DMS, and compact nautical formats.
Coordinate convention: +lat = N, -lat = S, +lon = E, -lon = W.
"""
from __future__ import annotations

import re

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QButtonGroup,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal


# ── Standalone parsing function (importable for tests) ────────────────────────

def parse_coordinate(text: str, coord_type: str) -> float | None:
    """
    Parse a free-text coordinate string.

    coord_type: 'lat' (range -90..90) or 'lon' (range -180..180).
    Returns decimal degrees as float, or None if unrecognised or out of range.

    Recognised formats:
      - Decimal degrees:  "28.5"  "-80.6"
      - DDM:  "28 30.00 N"  "28°30.00′N"  "28°30.00'N"  "28 30.00N"  "28-30.00-N"
      - Compact DDM:  "2830.00N"  (first 2–3 digits = degrees, rest = minutes)
      - DMS:  "28°30′00″N"  "28 30 00 N"
    """
    if not text:
        return None
    text = text.strip()
    if not text:
        return None

    _lo, _hi = (-90.0, 90.0) if coord_type == "lat" else (-180.0, 180.0)

    def validate(dd: float) -> float | None:
        return dd if _lo <= dd <= _hi else None

    upper = text.upper()
    hemi: str | None = None

    # Trailing hemisphere: must be preceded by a digit, decimal point,
    # or a degree/minute/second symbol — not a plain letter.
    m_trail = re.search(r'[\d.°′\'″"]\s*([NSEW])\s*$', upper)
    if m_trail:
        hemi = m_trail.group(1)
        upper = upper[: m_trail.start(1)].strip()
    else:
        # Leading hemisphere: must be immediately followed by a digit.
        m_lead = re.match(r'^([NSEW])\s*(\d)', upper)
        if m_lead:
            hemi = m_lead.group(1)
            upper = upper[m_lead.start(2):].strip()

    # Strip leading minus (negative decimal degrees without hemisphere).
    has_minus = False
    if upper.startswith('-'):
        has_minus = True
        upper = upper[1:].strip()

    # Replace degree/minute/second symbols and hyphens with spaces.
    # (Leading minus was already stripped; remaining hyphens are separators.)
    normalized = re.sub(r'[°′″\'"]+', ' ', upper)
    normalized = re.sub(r'-+', ' ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()

    parts = normalized.split()

    def apply_sign(dd: float) -> float:
        if hemi in ('S', 'W') or has_minus:
            return -abs(dd)
        return dd  # hemi N/E or no hemi: keep sign as-is

    # ── Single number: decimal degrees, or compact DDM fallback ──────────────
    if len(parts) == 1:
        try:
            dd = float(parts[0])
        except ValueError:
            return None

        result = validate(apply_sign(dd))
        if result is not None:
            return result

        # Out of valid range — could be compact DDM e.g. "2830.00" → 28°30.00'
        # Pattern: 1–3 leading digits (degrees) then exactly 2 digits (minutes int part).
        compact = re.fullmatch(r'(\d{1,3})(\d{2}(?:\.\d+)?)', parts[0])
        if compact:
            try:
                deg  = float(compact.group(1))
                mins = float(compact.group(2))
                if 0.0 <= mins < 60.0:
                    return validate(apply_sign(deg + mins / 60.0))
            except ValueError:
                pass

        return None

    # ── Two numbers: DDM (degrees + decimal minutes) ──────────────────────────
    if len(parts) == 2:
        try:
            deg, mins = float(parts[0]), float(parts[1])
        except ValueError:
            return None
        if not (0.0 <= mins < 60.0):
            return None
        return validate(apply_sign(deg + mins / 60.0))

    # ── Three numbers: DMS (degrees + integer minutes + seconds) ─────────────
    if len(parts) == 3:
        try:
            deg, mins, secs = float(parts[0]), float(parts[1]), float(parts[2])
        except ValueError:
            return None
        if not (0.0 <= mins < 60.0 and 0.0 <= secs < 60.0):
            return None
        return validate(apply_sign(deg + mins / 60.0 + secs / 3600.0))

    return None


# ── Hemisphere button stylesheet ──────────────────────────────────────────────

_HEMI_BTN_STYLE = """
QPushButton {
    background-color: #1e2d3d;
    border: 1px solid #374151;
    border-radius: 3px;
    color: #94a3b8;
    font-size: 9pt;
    font-weight: bold;
    min-width: 30px;
    max-width: 30px;
    min-height: 26px;
    max-height: 26px;
    padding: 0px;
}
QPushButton:checked {
    background-color: #2563eb;
    border-color: #1d4ed8;
    color: #ffffff;
}
QPushButton:hover:!checked {
    background-color: #2d3f55;
    color: #f1f5f9;
}
"""

_INPUT_NORMAL  = ""
_INPUT_VALID   = "QLineEdit { border: 1px solid #22c55e; }"
_INPUT_INVALID = "QLineEdit { border: 1px solid #ef4444; }"


# ── Widget ────────────────────────────────────────────────────────────────────

class CoordInputWidget(QWidget):
    """
    Free-text coordinate entry with automatic format detection.

    Emits:
      value_changed(float)  — when a valid coordinate is parsed
      format_detected(str)  — format key: 'dd', 'ddm', 'dms', 'compact'
    """

    value_changed  = pyqtSignal(float)
    format_detected = pyqtSignal(str)

    def __init__(self, coord_type: str, parent: QWidget | None = None):
        """
        coord_type: 'lat' or 'lon'.
        """
        super().__init__(parent)
        self._coord_type = coord_type
        self._current_value: float | None = None

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._parse_current)

        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(3)

        # Input row
        row = QHBoxLayout()
        row.setSpacing(4)

        self._input = QLineEdit()
        if self._coord_type == 'lat':
            self._input.setPlaceholderText("e.g. 28.5  or  28 30.00 N")
        else:
            self._input.setPlaceholderText("e.g. -80.6  or  80 36.00 W")
        self._input.textChanged.connect(self._on_text_changed)
        row.addWidget(self._input)

        # Hemisphere toggle buttons
        if self._coord_type == 'lat':
            pos_label, neg_label = 'N', 'S'
        else:
            pos_label, neg_label = 'E', 'W'

        self._pos_btn = QPushButton(pos_label)
        self._neg_btn = QPushButton(neg_label)
        self._pos_btn.setCheckable(True)
        self._neg_btn.setCheckable(True)
        self._pos_btn.setStyleSheet(_HEMI_BTN_STYLE)
        self._neg_btn.setStyleSheet(_HEMI_BTN_STYLE)

        self._hemi_group = QButtonGroup(self)
        self._hemi_group.setExclusive(True)
        self._hemi_group.addButton(self._pos_btn, 0)
        self._hemi_group.addButton(self._neg_btn, 1)
        self._pos_btn.setChecked(True)

        self._pos_btn.clicked.connect(self._on_hemi_clicked)
        self._neg_btn.clicked.connect(self._on_hemi_clicked)

        row.addWidget(self._pos_btn)
        row.addWidget(self._neg_btn)
        root.addLayout(row)

        # Conversion hint label
        self._hint = QLabel()
        self._hint.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._hint.setStyleSheet("color: #64748b; font-size: 7.5pt; background: transparent;")
        root.addWidget(self._hint)

    # ── Internal update ───────────────────────────────────────────────────────

    def _on_text_changed(self) -> None:
        self._debounce.start()  # restarts 300ms countdown on each keystroke

    def _parse_current(self) -> None:
        text = self._input.text()

        if not text.strip():
            self._current_value = None
            self._input.setStyleSheet(_INPUT_NORMAL)
            self._hint.setText("")
            return

        result = parse_coordinate(text, self._coord_type)

        if result is None:
            self._input.setStyleSheet(_INPUT_INVALID)
            self._input.setToolTip(
                "Unrecognised format — try  28.5  or  28 30.00 N  or  28°30.00′N"
            )
            self._hint.setText("")
        else:
            self._current_value = result
            self._input.setStyleSheet(_INPUT_VALID)
            self._input.setToolTip("")
            self._update_hint()
            self._update_hemi_buttons()
            self.value_changed.emit(result)
            self.format_detected.emit(self._detect_format(text))

            # Clear green border after 600 ms so it doesn't linger
            QTimer.singleShot(600, self._clear_input_style)

    def _clear_input_style(self) -> None:
        # Only clear if still valid (don't overwrite a red border set after)
        if self._current_value is not None:
            self._input.setStyleSheet(_INPUT_NORMAL)

    def _update_hint(self) -> None:
        dd = self._current_value
        if dd is None:
            self._hint.setText("")
            return

        abs_dd = abs(dd)
        deg    = int(abs_dd)
        mins   = (abs_dd - deg) * 60.0

        if self._coord_type == 'lat':
            hemi = 'N' if dd >= 0 else 'S'
        else:
            hemi = 'E' if dd >= 0 else 'W'

        self._hint.setText(
            f"{deg}°{mins:.3f}′{hemi}  =  {dd:.4f}°"
        )

    def _update_hemi_buttons(self) -> None:
        if self._current_value is None:
            return
        if self._current_value >= 0:
            self._pos_btn.setChecked(True)
        else:
            self._neg_btn.setChecked(True)

    def _on_hemi_clicked(self) -> None:
        if self._current_value is None:
            return
        neg_selected = self._neg_btn.isChecked()
        new_val = -abs(self._current_value) if neg_selected else abs(self._current_value)
        if new_val != self._current_value:
            self._current_value = new_val
            self._update_hint()
            self.value_changed.emit(self._current_value)

    @staticmethod
    def _detect_format(text: str) -> str:
        upper = text.strip().upper()
        # Strip trailing hemisphere
        m = re.search(r'([NSEW])\s*$', upper)
        if m:
            upper = upper[: m.start()].strip()
        # Strip leading hemisphere
        m2 = re.match(r'^([NSEW])\s*', upper)
        if m2:
            upper = upper[m2.end():].strip()
        # Strip leading minus
        if upper.startswith('-'):
            upper = upper[1:].strip()
        # Replace symbols with spaces
        norm = re.sub(r'[°′″\'"]+', ' ', upper)
        norm = re.sub(r'-+', ' ', norm)
        norm = re.sub(r'\s+', ' ', norm).strip()
        parts = norm.split()
        if len(parts) == 1:
            p = parts[0]
            # Compact DDM: would have been too large for range check to pass as DD
            if re.fullmatch(r'\d{4,}(\.\d+)?', p):
                return 'compact'
            return 'dd'
        if len(parts) == 2:
            return 'ddm'
        if len(parts) == 3:
            return 'dms'
        return 'unknown'

    # ── Public API ────────────────────────────────────────────────────────────

    def set_value(self, dd: float) -> None:
        """Populate the widget from a decimal-degree value."""
        self._current_value = dd
        abs_dd = abs(dd)
        deg    = int(abs_dd)
        mins   = (abs_dd - deg) * 60.0
        if self._coord_type == 'lat':
            hemi = 'N' if dd >= 0 else 'S'
        else:
            hemi = 'E' if dd >= 0 else 'W'
        self._input.setText(f"{deg}°{mins:.3f}′{hemi}")
        self._update_hint()
        self._update_hemi_buttons()
        self._input.setStyleSheet(_INPUT_NORMAL)

    def value(self) -> float | None:
        """Return the parsed decimal-degree value, or None if invalid/empty."""
        return self._current_value

    def is_valid(self) -> bool:
        """True if the current input parses to a valid coordinate."""
        return self._current_value is not None

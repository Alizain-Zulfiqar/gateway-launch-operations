"""
ui/widgets/threshold_editor.py — editable "optimal values" (thresholds) panel.

Lets the operator override the per-parameter operating limits used by the
probability engine for a run. Fields are pre-filled from the active vehicle's
own thresholds (the system default "based on which analysis is currently
happening"); if the operator does not touch them, `values()` simply returns
those defaults, so the run is identical to using the vehicle limits.

Shared by the Analysis tab, Quick Analysis tab, and Comparison tab.
"""
from __future__ import annotations

from typing import Dict, Optional

from PyQt6.QtWidgets import (
    QWidget, QGridLayout, QVBoxLayout, QHBoxLayout, QLabel,
    QDoubleSpinBox, QPushButton, QFrame, QSizePolicy,
)

# (param key, label, unit, max, decimals)
_FIELDS = [
    ("ws",   "Max wind",        "kt", 150.0, 1),
    ("wg",   "Max gust",        "kt", 200.0, 1),
    ("sh",   "Max sig. wave Hs", "m", 20.0,  2),
    ("swh",  "Max swell height", "m", 20.0,  2),
    ("swp",  "Max swell period", "s", 40.0,  1),
    ("wdV",  "Wind dir tol.",   "°",  180.0, 0),
    ("sdV",  "Sea dir tol.",    "°",  180.0, 0),
    ("swdV", "Swell dir tol.",  "°",  180.0, 0),
]

# Shorter labels for narrow sidebars (Comparison tab).
_FIELDS_COMPACT = [
    ("ws",   "Wind",     "kt", 150.0, 1),
    ("wg",   "Gust",     "kt", 200.0, 1),
    ("sh",   "Sig. Hs",  "m",  20.0,  2),
    ("swh",  "Swell H",  "m",  20.0,  2),
    ("swp",  "Swell T",  "s",  40.0,  1),
    ("wdV",  "Wind dir", "°",  180.0, 0),
    ("sdV",  "Sea dir",  "°",  180.0, 0),
    ("swdV", "Swell dir","°",  180.0, 0),
]


def threshold_editor_stylesheet(*, flat: bool = False) -> str:
    """Shared dark-theme QSS for ThresholdEditorWidget."""
    shell = (
        "#thresholdEditor { background: transparent; border: none; }"
        if flat else
        "#thresholdEditor { background:#1a2233; border:1px solid #374151;"
        " border-radius:6px; }"
    )
    return (
        shell
        + "#thresholdEditor QLabel { color:#e2e8f0; }"
        "#thresholdEditor QDoubleSpinBox { background:#0f1923; color:#e2e8f0;"
        " border:1px solid #374151; border-radius:4px; padding:2px 6px; }"
        "#thresholdEditor QPushButton { background:#2d3748; color:#e2e8f0;"
        " border:1px solid #374151; border-radius:4px; padding:4px 8px; }"
        "#thresholdEditor QPushButton:hover { background:#374151; }"
    )


class ThresholdEditorWidget(QFrame):
    """Grid of spin-boxes for the eight operating limits, plus a reset button.

    Call :meth:`set_defaults` whenever the active vehicle changes so the fields
    reflect the current analysis basis; call :meth:`values` at run time to get
    the (possibly overridden) thresholds dict to pass to the engine.

    Parameters
    ----------
    compact : bool
        Single-column layout with short labels — for narrow sidebars (~300px).
    show_header : bool
        When False, omit the inner title (parent QGroupBox may supply it).
    show_hint : bool
        When False, omit the explanatory hint paragraph.
    """

    def __init__(
        self,
        parent=None,
        *,
        compact: bool = False,
        show_header: bool = True,
        show_hint: bool = True,
    ):
        super().__init__(parent)
        self.setObjectName("thresholdEditor")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._compact = compact
        self._show_header = show_header
        self._show_hint = show_hint
        self._spins: Dict[str, QDoubleSpinBox] = {}
        self._defaults: Dict[str, float] = {}
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        if self._compact:
            root.setContentsMargins(6, 6, 6, 6)
            root.setSpacing(5)
        else:
            root.setContentsMargins(10, 8, 10, 8)
            root.setSpacing(6)

        if self._show_header:
            header = QHBoxLayout()
            header.setSpacing(6)
            title = QLabel(
                "Operating limits" if self._compact else "Optimal values (operating limits)"
            )
            title.setStyleSheet("font-weight: 600;")
            header.addWidget(title, 1)
            self.reset_btn = QPushButton(
                "Reset" if self._compact else "Reset to vehicle defaults"
            )
            self.reset_btn.setToolTip(
                "Restore every limit to the active vehicle's own thresholds."
            )
            if self._compact:
                self.reset_btn.setFixedHeight(24)
            self.reset_btn.clicked.connect(self.reset)
            header.addWidget(self.reset_btn)
            root.addLayout(header)
        else:
            self.reset_btn = QPushButton("Reset defaults")
            self.reset_btn.setToolTip(
                "Restore every limit to the active vehicle's own thresholds."
            )
            if self._compact:
                self.reset_btn.setFixedHeight(24)
            self.reset_btn.clicked.connect(self.reset)
            root.addWidget(self.reset_btn)

        if self._show_hint:
            hint = QLabel(
                "Leave as-is for vehicle defaults, or edit limits for this run."
                if self._compact else
                "Leave these as-is to use the system defaults for the current "
                "vehicle, or edit any limit to re-run the analysis against your "
                "own optimal value."
            )
            hint.setWordWrap(True)
            hint.setStyleSheet(
                "color: #94a3b8; font-size: 8pt;" if self._compact
                else "color: #94a3b8; font-size: 11px;"
            )
            root.addWidget(hint)

        fields = _FIELDS_COMPACT if self._compact else _FIELDS
        grid = QGridLayout()
        grid.setHorizontalSpacing(8 if self._compact else 12)
        grid.setVerticalSpacing(5 if self._compact else 6)

        if self._compact:
            # One parameter per row: label | spin (fits ~300px sidebars).
            for i, (key, label, unit, maximum, decimals) in enumerate(fields):
                lbl = QLabel(f"{label} ({unit})")
                lbl.setStyleSheet("font-size: 8pt;")
                spin = self._make_spin(maximum, decimals)
                self._spins[key] = spin
                grid.addWidget(lbl, i, 0)
                grid.addWidget(spin, i, 1)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
        else:
            cols = 2
            for i, (key, label, unit, maximum, decimals) in enumerate(fields):
                r, c = divmod(i, cols)
                lbl = QLabel(f"{label} ({unit})")
                spin = self._make_spin(maximum, decimals)
                self._spins[key] = spin
                grid.addWidget(lbl, r, c * 2)
                grid.addWidget(spin, r, c * 2 + 1)
            grid.setColumnStretch(1, 1)
            grid.setColumnStretch(3, 1)

        root.addLayout(grid)

    def _make_spin(self, maximum: float, decimals: int) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(decimals)
        spin.setRange(0.0, maximum)
        spin.setSingleStep(1.0 if decimals == 0 else 0.1)
        if self._compact:
            spin.setMinimumWidth(76)
            spin.setFixedHeight(26)
        else:
            spin.setMinimumWidth(90)
        spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return spin

    def set_defaults(self, thresholds: Optional[Dict[str, float]]) -> None:
        """Fill the fields from a vehicle's threshold dict and remember them as
        the reset target. Silently ignores missing keys."""
        thresholds = thresholds or {}
        self._defaults = {}
        for key, spin in self._spins.items():
            val = thresholds.get(key)
            if val is None:
                continue
            self._defaults[key] = float(val)
            spin.blockSignals(True)
            spin.setValue(float(val))
            spin.blockSignals(False)

    def reset(self) -> None:
        """Restore the fields to the last-set vehicle defaults."""
        for key, spin in self._spins.items():
            if key in self._defaults:
                spin.blockSignals(True)
                spin.setValue(self._defaults[key])
                spin.blockSignals(False)

    def values(self) -> Dict[str, float]:
        """Current per-parameter operating limits (always populated)."""
        return {key: spin.value() for key, spin in self._spins.items()}

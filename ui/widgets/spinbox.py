"""
ui/widgets/spinbox.py — Styled spin-box widgets with guaranteed clickable +/−
buttons on Windows. Use in place of QDoubleSpinBox / QSpinBox in all dialogs.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton
from PyQt6.QtCore import pyqtSignal

_BTN_STYLE = """
QPushButton {
    background-color: #374151;
    border: 1px solid #4b5563;
    border-radius: 3px;
    color: #f1f5f9;
    font-size: 14px;
    font-weight: bold;
    min-width: 26px;
    min-height: 26px;
    max-width: 26px;
    max-height: 26px;
    padding: 0px;
}
QPushButton:hover  { background-color: #4b5563; }
QPushButton:pressed { background-color: #2563eb; }
"""

_EDIT_STYLE = """
QLineEdit {
    background-color: #2d3748;
    border: 1px solid #374151;
    border-radius: 4px;
    padding: 4px 8px;
    color: #f1f5f9;
    min-height: 26px;
}
QLineEdit:focus { border-color: #2563eb; }
QLineEdit:disabled { background-color: #111827; color: #4b5563; }
"""


class StyledDoubleSpinBox(QWidget):
    """Float spin box with explicit +/− buttons that always respond on Windows."""

    valueChanged = pyqtSignal(float)

    def __init__(self,
                 minimum: float = 0.0,
                 maximum: float = 9999.0,
                 step: float = 1.0,
                 decimals: int = 2,
                 suffix: str = "",
                 parent=None):
        super().__init__(parent)
        self._value   = minimum
        self._min     = minimum
        self._max     = maximum
        self._step    = step
        self._decimals = decimals
        self._suffix  = suffix
        self._build()

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._edit = QLineEdit()
        self._edit.setStyleSheet(_EDIT_STYLE)
        self._edit.editingFinished.connect(self._on_edit)
        layout.addWidget(self._edit)

        self._down_btn = QPushButton("−")   # minus sign
        self._down_btn.setStyleSheet(_BTN_STYLE)
        self._down_btn.clicked.connect(self._step_down)
        layout.addWidget(self._down_btn)

        self._up_btn = QPushButton("+")
        self._up_btn.setStyleSheet(_BTN_STYLE)
        self._up_btn.clicked.connect(self._step_up)
        layout.addWidget(self._up_btn)

        self._update_display()

    def _update_display(self) -> None:
        text = f"{self._value:.{self._decimals}f}"
        if self._suffix:
            text += f" {self._suffix}"
        self._edit.setText(text)

    def _on_edit(self) -> None:
        text = self._edit.text().replace(self._suffix, "").strip()
        try:
            self.setValue(float(text))
        except ValueError:
            self._update_display()

    def _step_up(self)   -> None: self.setValue(self._value + self._step)
    def _step_down(self) -> None: self.setValue(self._value - self._step)

    def setValue(self, value: float) -> None:
        clamped = max(self._min, min(self._max, value))
        changed = abs(clamped - self._value) > 1e-9
        self._value = clamped
        self._update_display()
        if changed:
            self.valueChanged.emit(self._value)

    def value(self) -> float: return self._value

    def setMinimum(self, v: float) -> None: self._min = v
    def setMaximum(self, v: float) -> None: self._max = v
    def setSingleStep(self, v: float) -> None: self._step = v
    def setDecimals(self, v: int)   -> None: self._decimals = v
    def setSuffix(self, s: str)     -> None: self._suffix = s
    def setRange(self, lo: float, hi: float) -> None:
        self._min = lo; self._max = hi


class StyledSpinBox(QWidget):
    """Integer spin box with explicit +/− buttons that always respond on Windows."""

    valueChanged = pyqtSignal(int)

    def __init__(self,
                 minimum: int = 0,
                 maximum: int = 9999,
                 step: int = 1,
                 parent=None):
        super().__init__(parent)
        self._value = minimum
        self._min   = minimum
        self._max   = maximum
        self._step  = step
        self._build()

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._edit = QLineEdit()
        self._edit.setStyleSheet(_EDIT_STYLE)
        self._edit.editingFinished.connect(self._on_edit)
        layout.addWidget(self._edit)

        self._down_btn = QPushButton("−")
        self._down_btn.setStyleSheet(_BTN_STYLE)
        self._down_btn.clicked.connect(self._step_down)
        layout.addWidget(self._down_btn)

        self._up_btn = QPushButton("+")
        self._up_btn.setStyleSheet(_BTN_STYLE)
        self._up_btn.clicked.connect(self._step_up)
        layout.addWidget(self._up_btn)

        self._update_display()

    def _update_display(self) -> None:
        self._edit.setText(str(self._value))

    def _on_edit(self) -> None:
        try:
            self.setValue(int(self._edit.text().strip()))
        except ValueError:
            self._update_display()

    def _step_up(self)   -> None: self.setValue(self._value + self._step)
    def _step_down(self) -> None: self.setValue(self._value - self._step)

    def setValue(self, value: int) -> None:
        clamped = max(self._min, min(self._max, int(value)))
        changed = clamped != self._value
        self._value = clamped
        self._update_display()
        if changed:
            self.valueChanged.emit(self._value)

    def value(self) -> int: return self._value

    def setMinimum(self, v: int) -> None: self._min = v
    def setMaximum(self, v: int) -> None: self._max = v
    def setSingleStep(self, v: int) -> None: self._step = v
    def setRange(self, lo: int, hi: int) -> None:
        self._min = lo; self._max = hi

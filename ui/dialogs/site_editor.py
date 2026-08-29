"""
ui/dialogs/site_editor.py — Edit an existing site's fields.

Coordinate convention: +lat = N, -lat = S, +lon = E, -lon = W (WGS-84).
Add is handled inline in ui/sections/sites.py's All Sites table; this dialog
covers Edit only, reused from both the Sites tab and the Projects tab's
Candidate Sites table.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLabel, QLineEdit, QComboBox,
    QDoubleSpinBox, QTextEdit, QDialogButtonBox, QMessageBox,
)

from core.database import get_connection
from core.models import Site
from ui.widgets.coord_input import CoordInputWidget


class SiteEditorDialog(QDialog):
    """Edit dialog for an existing Site. Pass the Site to edit; on accept,
    self.updated_site holds the edited (not-yet-persisted) Site."""

    def __init__(self, parent=None, site: Site | None = None):
        super().__init__(parent)
        if site is None or site.id is None:
            raise ValueError("SiteEditorDialog requires an existing saved Site")
        self._site = site
        self.updated_site: Site | None = None

        self.setWindowTitle("Edit Site")
        self.setMinimumWidth(420)
        self.setModal(True)

        self._load_platforms()
        self._build()
        self._populate()

    def _load_platforms(self) -> None:
        try:
            conn = get_connection()
            self._platforms = conn.execute(
                "SELECT id, name FROM platforms ORDER BY name"
            ).fetchall()
            conn.close()
        except Exception:
            self._platforms = []

    def _build(self) -> None:
        root = QVBoxLayout(self)
        form = QFormLayout()

        self._name_edit = QLineEdit()
        form.addRow("Site Name", self._name_edit)

        self._lat_input = CoordInputWidget("lat")
        form.addRow("Latitude", self._lat_input)

        self._lon_input = CoordInputWidget("lon")
        form.addRow("Longitude", self._lon_input)

        self._bbox_spin = QDoubleSpinBox()
        self._bbox_spin.setRange(1.0, 500.0)
        self._bbox_spin.setDecimals(1)
        self._bbox_spin.setSuffix(" NM")
        form.addRow("Bounding Box Radius", self._bbox_spin)

        self._platform_combo = QComboBox()
        self._platform_combo.addItem("(none)", userData=None)
        for p in self._platforms:
            self._platform_combo.addItem(p["name"], userData=p["id"])
        form.addRow("Vessel Platform", self._platform_combo)

        self._notes_edit = QTextEdit()
        self._notes_edit.setMaximumHeight(80)
        form.addRow("Notes", self._notes_edit)

        root.addLayout(form)

        hint = QLabel(
            "+Lat = N, −Lat = S, +Lon = E, −Lon = W. "
            "Editing coordinates updates this site's coordinate code."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #64748b; font-size: 8pt;")
        root.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _populate(self) -> None:
        self._name_edit.setText(self._site.name or "")
        self._lat_input.set_value(self._site.lat)
        self._lon_input.set_value(self._site.lon)
        self._bbox_spin.setValue(self._site.bbox_nm or 25.0)
        idx = self._platform_combo.findData(self._site.platform_id)
        if idx >= 0:
            self._platform_combo.setCurrentIndex(idx)
        self._notes_edit.setPlainText(self._site.notes or "")

    def _on_save(self) -> None:
        if not self._lat_input.is_valid():
            QMessageBox.warning(self, "Invalid Latitude", "Enter a valid latitude.")
            return
        if not self._lon_input.is_valid():
            QMessageBox.warning(self, "Invalid Longitude", "Enter a valid longitude.")
            return

        name = self._name_edit.text().strip()
        lat = self._lat_input.value()
        lon = self._lon_input.value()
        bbox = self._bbox_spin.value()
        platform_id = self._platform_combo.currentData()
        notes = self._notes_edit.toPlainText().strip()

        try:
            updated = Site(
                lat=lat, lon=lon, name=name, bbox_nm=bbox,
                platform_id=platform_id, notes=notes,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Validation Error", str(exc))
            return

        updated.id = self._site.id
        self.updated_site = updated
        self.accept()

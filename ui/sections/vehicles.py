"""
ui/sections/vehicles.py — Vehicle Manager section.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox, QSizePolicy,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from core.database import get_connection

# Status → row background colour
_STATUS_COLORS = {
    "development": "#1e3a5f",
    "retired":     "#1e1e1e",
    "proposed":    "#2a1f00",
}

_COLUMNS = [
    "Name", "Provider", "Country", "Category", "Status",
    "LEO kg", "Height m", "Max Wind", "Max Hs", "Data Source", "Verified",
]
_COL = {name: i for i, name in enumerate(_COLUMNS)}


class VehiclesSection(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left filter panel ────────────────────────────────────────────────
        left = QWidget()
        left.setFixedWidth(280)
        left.setStyleSheet("background: #151c27; border-right: 1px solid #374151;")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(12, 16, 12, 16)
        lv.setSpacing(10)

        lv.addWidget(QLabel("Vehicles"))

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search by name…")
        self._search_edit.textChanged.connect(self._reload_table)
        lv.addWidget(self._search_edit)

        self._cat_filter = QComboBox()
        self._cat_filter.addItem("All Categories")
        self._cat_filter.currentIndexChanged.connect(self._reload_table)
        lv.addWidget(self._cat_filter)

        self._status_filter = QComboBox()
        self._status_filter.addItems([
            "All Statuses", "operational", "development", "retired", "proposed"
        ])
        self._status_filter.currentIndexChanged.connect(self._reload_table)
        lv.addWidget(self._status_filter)

        self._country_filter = QComboBox()
        self._country_filter.addItem("All Countries")
        self._country_filter.currentIndexChanged.connect(self._reload_table)
        lv.addWidget(self._country_filter)

        lv.addSpacing(8)

        self._add_btn = QPushButton("Add Vehicle")
        self._add_btn.clicked.connect(self._on_add)
        lv.addWidget(self._add_btn)

        self._edit_btn = QPushButton("Edit Vehicle")
        self._edit_btn.clicked.connect(self._on_edit)
        lv.addWidget(self._edit_btn)

        self._del_btn = QPushButton("Delete Vehicle")
        self._del_btn.setStyleSheet(
            "background: #7f1d1d; color: #fca5a5;"
        )
        self._del_btn.clicked.connect(self._on_delete)
        lv.addWidget(self._del_btn)

        lv.addStretch()

        self._count_label = QLabel("0 vehicles")
        self._count_label.setStyleSheet("color: #64748b; font-size: 8pt;")
        lv.addWidget(self._count_label)

        root.addWidget(left)

        # ── Right table ──────────────────────────────────────────────────────
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._table.setSortingEnabled(True)
        self._table.doubleClicked.connect(self._on_edit)
        rv.addWidget(self._table)

        root.addWidget(right)

    # ── Data ─────────────────────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._reload_filters()
        self._reload_table()

    def _reload_filters(self) -> None:
        conn = get_connection()
        cats = [r[0] for r in conn.execute(
            "SELECT name FROM vehicle_categories ORDER BY sort_order"
        ).fetchall()]
        countries = [r[0] for r in conn.execute(
            "SELECT DISTINCT country FROM vehicles WHERE country IS NOT NULL ORDER BY country"
        ).fetchall()]
        conn.close()

        cur_cat = self._cat_filter.currentText()
        self._cat_filter.blockSignals(True)
        self._cat_filter.clear()
        self._cat_filter.addItem("All Categories")
        self._cat_filter.addItems(cats)
        idx = self._cat_filter.findText(cur_cat, Qt.MatchFlag.MatchFixedString)
        self._cat_filter.setCurrentIndex(max(0, idx))
        self._cat_filter.blockSignals(False)

        cur_country = self._country_filter.currentText()
        self._country_filter.blockSignals(True)
        self._country_filter.clear()
        self._country_filter.addItem("All Countries")
        self._country_filter.addItems(countries)
        idx = self._country_filter.findText(cur_country, Qt.MatchFlag.MatchFixedString)
        self._country_filter.setCurrentIndex(max(0, idx))
        self._country_filter.blockSignals(False)

    def _reload_table(self) -> None:
        search  = self._search_edit.text().strip().lower()
        cat_sel = self._cat_filter.currentText()
        st_sel  = self._status_filter.currentText()
        co_sel  = self._country_filter.currentText()

        sql = """
            SELECT v.id, v.name, v.provider, v.country,
                   c.name AS category_name, v.status,
                   v.leo_payload_kg, v.height_m,
                   v.max_wind_kts, v.max_hs_m,
                   v.data_source,
                   v.wind_hold_verified, v.sea_state_verified,
                   v.vehicle_class, v.recovery_mode,
                   v.max_gust_kts, v.max_swell_ht_m, v.max_swell_period_s,
                   v.max_wind_dir_tolerance_deg, v.max_sea_dir_tolerance_deg,
                   v.max_swell_dir_tolerance_deg,
                   v.diameter_m, v.gross_mass_kg, v.stages,
                   v.propellant_stage1, v.propellant_stage2, v.propellant_upper,
                   v.first_flight_year, v.manufacturer, v.notes,
                   v.notes_extended, v.category_id,
                   v.sso_payload_kg, v.gto_payload_kg
              FROM vehicles v
         LEFT JOIN vehicle_categories c ON v.category_id = c.id
             WHERE 1=1
        """
        params: list = []

        if search:
            sql += " AND LOWER(v.name) LIKE ?"
            params.append(f"%{search}%")
        if cat_sel != "All Categories":
            sql += " AND c.name = ?"
            params.append(cat_sel)
        if st_sel != "All Statuses":
            sql += " AND v.status = ?"
            params.append(st_sel)
        if co_sel != "All Countries":
            sql += " AND v.country = ?"
            params.append(co_sel)

        sql += " ORDER BY v.name"

        conn = get_connection()
        rows = conn.execute(sql, params).fetchall()
        conn.close()

        self._rows = [dict(r) for r in rows]

        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        self._table.setRowCount(len(self._rows))

        for row_idx, r in enumerate(self._rows):
            w = self._wind_verified = None  # re-used variable name below

            wind_v = bool(r.get("wind_hold_verified"))
            sea_v  = bool(r.get("sea_state_verified"))
            if wind_v and sea_v:
                verified_str = "✓"
            elif wind_v or sea_v:
                verified_str = "~"
            else:
                verified_str = "✗"

            values = [
                r.get("name", ""),
                r.get("provider") or "",
                r.get("country") or "",
                r.get("category_name") or "",
                r.get("status") or "",
                _fmt(r.get("leo_payload_kg")),
                _fmt(r.get("height_m"), dec=1),
                _fmt(r.get("max_wind_kts"), dec=0, suffix=" kts"),
                _fmt(r.get("max_hs_m"), dec=2, suffix=" m"),
                r.get("data_source") or "",
                verified_str,
            ]

            bg = _STATUS_COLORS.get(r.get("status", ""), "")

            for col_idx, val in enumerate(values):
                item = QTableWidgetItem(str(val))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if bg:
                    item.setBackground(QColor(bg))
                self._table.setItem(row_idx, col_idx, item)

        self._table.setSortingEnabled(True)
        self._count_label.setText(f"{len(self._rows)} vehicle{'s' if len(self._rows) != 1 else ''}")

    # ── Actions ───────────────────────────────────────────────────────────────

    def _selected_row_data(self) -> dict | None:
        sel = self._table.selectedItems()
        if not sel:
            return None
        row = self._table.row(sel[0])
        name = self._table.item(row, _COL["Name"]).text()
        for r in self._rows:
            if r.get("name") == name:
                return r
        return None

    def _on_add(self) -> None:
        from ui.dialogs.vehicle_editor import VehicleEditorDialog
        dlg = VehicleEditorDialog(self)
        if dlg.exec():
            self._reload_filters()
            self._reload_table()

    def _on_edit(self) -> None:
        data = self._selected_row_data()
        if not data:
            QMessageBox.information(self, "No selection", "Select a vehicle to edit.")
            return
        from ui.dialogs.vehicle_editor import VehicleEditorDialog
        dlg = VehicleEditorDialog(self, vehicle_data=data)
        if dlg.exec():
            self._reload_filters()
            self._reload_table()

    def _on_delete(self) -> None:
        data = self._selected_row_data()
        if not data:
            QMessageBox.information(self, "No selection", "Select a vehicle to delete.")
            return
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete '{data['name']}'? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            conn = get_connection()
            conn.execute("DELETE FROM vehicles WHERE id=?", (data["id"],))
            conn.commit()
            conn.close()
            self._reload_table()


def _fmt(val, dec: int = 0, suffix: str = "") -> str:
    if val is None:
        return "—"
    if dec == 0:
        return f"{int(val)}{suffix}"
    return f"{val:.{dec}f}{suffix}"

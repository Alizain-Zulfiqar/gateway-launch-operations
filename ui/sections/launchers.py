"""
ui/sections/launchers.py — Launcher configuration manager.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QComboBox,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox, QFrame,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from core.database import get_connection

_LAUNCHER_TYPE_DISPLAY = {
    "rail":            "Rail",
    "vertical_fixed":  "Vertical Fixed",
    "vertical_mobile": "Vertical Mobile",
    "air_carrier":     "Air Carrier",
}

_COLUMNS = [
    "Launcher Name", "Type", "Mount Method", "Vehicle",
    "Base Ø (m)", "Weight (kg)", "Deck Load (kPa)",
    "Min Deck Area (m²)", "Data Source", "Verified",
]
_COL = {n: i for i, n in enumerate(_COLUMNS)}


class LaunchersSection(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[dict] = []
        self._build()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._reload_vehicle_filter()
        self._reload_table()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left panel ───────────────────────────────────────────────────────
        left = QWidget()
        left.setFixedWidth(300)
        left.setStyleSheet("background: #151c27; border-right: 1px solid #374151;")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(12, 16, 12, 16)
        lv.setSpacing(10)

        lv.addWidget(QLabel("Launcher Configurations"))

        lv.addWidget(QLabel("Launcher type"))
        self._type_filter = QComboBox()
        self._type_filter.addItems(
            ["All", "Rail", "Vertical Fixed", "Vertical Mobile", "Air Carrier"]
        )
        self._type_filter.currentIndexChanged.connect(self._reload_table)
        lv.addWidget(self._type_filter)

        lv.addWidget(QLabel("Vehicle"))
        self._vehicle_filter = QComboBox()
        self._vehicle_filter.addItem("All vehicles")
        self._vehicle_filter.currentIndexChanged.connect(self._reload_table)
        lv.addWidget(self._vehicle_filter)

        lv.addWidget(QLabel("Verified status"))
        self._ver_filter = QComboBox()
        self._ver_filter.addItems(["All", "Verified", "Unverified"])
        self._ver_filter.currentIndexChanged.connect(self._reload_table)
        lv.addWidget(self._ver_filter)

        lv.addSpacing(8)

        add_btn = QPushButton("+ Add Launcher Config")
        add_btn.setStyleSheet(
            "background: #2563eb; color: white; border-radius: 4px; "
            "padding: 8px; font-weight: bold;"
        )
        add_btn.clicked.connect(self._on_add)
        lv.addWidget(add_btn)

        edit_btn = QPushButton("Edit Selected")
        edit_btn.clicked.connect(self._on_edit)
        lv.addWidget(edit_btn)

        dup_btn = QPushButton("Duplicate Selected")
        dup_btn.clicked.connect(self._on_duplicate)
        lv.addWidget(dup_btn)

        del_btn = QPushButton("Delete Selected")
        del_btn.setStyleSheet("background: #7f1d1d; color: #fca5a5;")
        del_btn.clicked.connect(self._on_delete)
        lv.addWidget(del_btn)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #374151;")
        lv.addWidget(sep)

        info = QLabel(
            "Launcher configurations define the physical interface between a "
            "launch vehicle and the offshore platform deck.  Each vehicle may "
            "have multiple launcher options.  Specifications marked Estimated "
            "require verification against manufacturer or integration contractor ICD."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #64748b; font-size: 8pt;")
        lv.addWidget(info)

        lv.addStretch()

        self._count_lbl = QLabel("0 launchers")
        self._count_lbl.setStyleSheet("color: #64748b; font-size: 8pt;")
        lv.addWidget(self._count_lbl)

        root.addWidget(left)

        # ── Right table ──────────────────────────────────────────────────────
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)

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
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSortingEnabled(True)
        self._table.doubleClicked.connect(self._on_edit)
        rv.addWidget(self._table)

        root.addWidget(right, 1)

    # ── Data ─────────────────────────────────────────────────────────────────

    def _reload_vehicle_filter(self) -> None:
        cur = self._vehicle_filter.currentText()
        self._vehicle_filter.blockSignals(True)
        self._vehicle_filter.clear()
        self._vehicle_filter.addItem("All vehicles")
        try:
            conn = get_connection()
            rows = conn.execute(
                "SELECT id, name FROM vehicles ORDER BY name"
            ).fetchall()
            conn.close()
            for r in rows:
                self._vehicle_filter.addItem(r["name"], r["id"])
        except Exception:
            pass
        idx = self._vehicle_filter.findText(cur, Qt.MatchFlag.MatchFixedString)
        self._vehicle_filter.setCurrentIndex(max(0, idx))
        self._vehicle_filter.blockSignals(False)

    def _reload_table(self) -> None:
        type_sel = self._type_filter.currentText()
        ver_sel  = self._ver_filter.currentText()
        vid_data = self._vehicle_filter.currentData()

        # Map display type to db key
        type_key_map = {
            "Rail":            "rail",
            "Vertical Fixed":  "vertical_fixed",
            "Vertical Mobile": "vertical_mobile",
            "Air Carrier":     "air_carrier",
        }

        sql = """
            SELECT lc.*, v.name AS vehicle_name
              FROM launcher_configs lc
         LEFT JOIN vehicles v ON lc.vehicle_id = v.id
             WHERE 1=1
        """
        params: list = []
        if type_sel != "All":
            sql += " AND lc.launcher_type=?"
            params.append(type_key_map.get(type_sel, type_sel.lower().replace(" ", "_")))
        if ver_sel == "Verified":
            sql += " AND lc.specs_verified=1"
        elif ver_sel == "Unverified":
            sql += " AND lc.specs_verified=0"
        if vid_data:
            sql += " AND lc.vehicle_id=?"
            params.append(vid_data)
        sql += " ORDER BY lc.launcher_name"

        try:
            conn = get_connection()
            rows = conn.execute(sql, params).fetchall()
            conn.close()
            self._rows = [dict(r) for r in rows]
        except Exception:
            self._rows = []

        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        self._table.setRowCount(len(self._rows))

        for ri, r in enumerate(self._rows):
            verified    = bool(r.get("specs_verified"))
            ver_str     = "✓" if verified else "✗"
            ver_color   = QColor("#86efac") if verified else QColor("#fca5a5")
            mount_label = (r.get("mount_method") or "").replace("_", " ").title()
            type_label  = _LAUNCHER_TYPE_DISPLAY.get(r.get("launcher_type", ""), r.get("launcher_type", ""))

            values = [
                r.get("launcher_name", ""),
                type_label,
                mount_label,
                r.get("vehicle_name") or "Generic",
                _fmt(r.get("base_diameter_m"), dec=2),
                _fmt(r.get("total_weight_kg"), dec=0),
                _fmt(r.get("deck_load_kpa"), dec=1),
                _fmt(r.get("min_deck_area_m2"), dec=1),
                r.get("data_source") or "",
                ver_str,
            ]
            for ci, val in enumerate(values):
                item = QTableWidgetItem(str(val))
                item.setForeground(QColor("#f1f5f9"))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if ci == _COL["Verified"]:
                    item.setForeground(ver_color)
                self._table.setItem(ri, ci, item)

        self._table.setSortingEnabled(True)
        self._count_lbl.setText(
            f"{len(self._rows)} launcher{'s' if len(self._rows) != 1 else ''}"
        )

    # ── Actions ───────────────────────────────────────────────────────────────

    def _selected_data(self) -> dict | None:
        sel = self._table.selectedItems()
        if not sel:
            return None
        row = self._table.row(sel[0])
        name = self._table.item(row, _COL["Launcher Name"]).text()
        for r in self._rows:
            if r.get("launcher_name") == name:
                return r
        return None

    def _on_add(self) -> None:
        from ui.dialogs.launcher_editor import LauncherEditorDialog
        dlg = LauncherEditorDialog(self)
        if dlg.exec():
            self._reload_table()

    def _on_edit(self) -> None:
        data = self._selected_data()
        if not data:
            QMessageBox.information(self, "No selection", "Select a launcher to edit.")
            return
        from ui.dialogs.launcher_editor import LauncherEditorDialog
        dlg = LauncherEditorDialog(self, launcher_data=data)
        if dlg.exec():
            self._reload_table()

    def _on_duplicate(self) -> None:
        data = self._selected_data()
        if not data:
            QMessageBox.information(self, "No selection", "Select a launcher to duplicate.")
            return
        dup = dict(data)
        dup.pop("id", None)
        dup["launcher_name"] = data["launcher_name"] + " (copy)"
        from ui.dialogs.launcher_editor import LauncherEditorDialog
        dlg = LauncherEditorDialog(self, launcher_data=dup)
        if dlg.exec():
            self._reload_table()

    def _on_delete(self) -> None:
        data = self._selected_data()
        if not data:
            QMessageBox.information(self, "No selection", "Select a launcher to delete.")
            return
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete '{data['launcher_name']}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                conn = get_connection()
                conn.execute("DELETE FROM launcher_vehicle_compat WHERE launcher_id=?",
                             (data["id"],))
                conn.execute("DELETE FROM launcher_configs WHERE id=?", (data["id"],))
                conn.commit()
                conn.close()
            except Exception as exc:
                QMessageBox.critical(self, "Error", str(exc))
            self._reload_table()


def _fmt(val, dec: int = 0) -> str:
    if val is None:
        return "—"
    if dec == 0:
        return f"{int(val)}"
    return f"{val:.{dec}f}"

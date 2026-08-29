"""
ui/sections/vessels.py — Vessel (platform) specification section.
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

_HULL_TYPES   = ["All", "semisub", "tlp", "jackup", "spar", "fixed"]
_PAYLOAD_CLS  = ["All", "SLV", "MLV", "HLV", "SHLV", "Universal"]

_COLUMNS = [
    "Name", "Hull Type", "Payload Class", "DP", "Max Hs", "Depth", "Motion Factor", "Notes"
]
_COL = {n: i for i, n in enumerate(_COLUMNS)}

_FACTOR_REFERENCE = [
    ("semisub", 0.78, "Semi-submersible"),
    ("tlp",     0.82, "Tension Leg Platform"),
    ("jackup",  0.92, "Jack-up"),
    ("spar",    0.75, "Spar"),
    ("fixed",   1.00, "Fixed / monopile"),
]


class VesselsSection(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[dict] = []
        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left panel ───────────────────────────────────────────────────────
        left = QWidget()
        left.setFixedWidth(260)
        left.setStyleSheet("background: #151c27; border-right: 1px solid #374151;")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(12, 16, 12, 16)
        lv.setSpacing(10)

        lv.addWidget(QLabel("Vessels"))

        lv.addWidget(QLabel("Hull type"))
        self._hull_filter = QComboBox()
        self._hull_filter.addItems(_HULL_TYPES)
        self._hull_filter.currentIndexChanged.connect(self._reload_table)
        lv.addWidget(self._hull_filter)

        lv.addWidget(QLabel("Payload class"))
        self._payload_filter = QComboBox()
        self._payload_filter.addItems(_PAYLOAD_CLS)
        self._payload_filter.currentIndexChanged.connect(self._reload_table)
        lv.addWidget(self._payload_filter)

        lv.addSpacing(8)

        self._add_btn = QPushButton("Add Vessel")
        self._add_btn.clicked.connect(self._on_add)
        lv.addWidget(self._add_btn)

        self._edit_btn = QPushButton("Edit Vessel")
        self._edit_btn.clicked.connect(self._on_edit)
        lv.addWidget(self._edit_btn)

        self._dup_btn = QPushButton("Duplicate Vessel")
        self._dup_btn.clicked.connect(self._on_duplicate)
        lv.addWidget(self._dup_btn)

        self._del_btn = QPushButton("Delete Vessel")
        self._del_btn.setStyleSheet("background: #7f1d1d; color: #fca5a5;")
        self._del_btn.clicked.connect(self._on_delete)
        lv.addWidget(self._del_btn)

        lv.addSpacing(12)

        # Motion factor reference card
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #374151;")
        lv.addWidget(sep)

        lv.addWidget(QLabel("Hull Motion Factors"))
        for hull, factor, label in _FACTOR_REFERENCE:
            row_lbl = QLabel(f"  {label}: {factor:.2f}")
            row_lbl.setStyleSheet("color: #94a3b8; font-size: 8pt;")
            lv.addWidget(row_lbl)

        note = QLabel("Applies to Hs and swell only — not to wind.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #64748b; font-size: 8pt; margin-top: 4px;")
        lv.addWidget(note)

        lv.addStretch()

        self._count_label = QLabel("0 vessels")
        self._count_label.setStyleSheet("color: #64748b; font-size: 8pt;")
        lv.addWidget(self._count_label)

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

        root.addWidget(right)

    # ── Data ─────────────────────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._reload_table()

    def _reload_table(self) -> None:
        hull_sel    = self._hull_filter.currentText()
        payload_sel = self._payload_filter.currentText()

        sql = "SELECT * FROM platforms WHERE 1=1"
        params: list = []
        if hull_sel != "All":
            sql += " AND hull_type=?"
            params.append(hull_sel)
        if payload_sel != "All":
            sql += " AND payload_class=?"
            params.append(payload_sel)
        sql += " ORDER BY is_reference DESC, name"

        conn = get_connection()
        rows = conn.execute(sql, params).fetchall()
        conn.close()

        self._rows = [dict(r) for r in rows]

        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        self._table.setRowCount(len(self._rows))

        for row_idx, r in enumerate(self._rows):
            is_ref   = bool(r.get("is_reference"))
            name_str = ("🔒 " if is_ref else "") + (r.get("name") or "")

            values = [
                name_str,
                r.get("hull_type") or "",
                r.get("payload_class") or "",
                "✓" if r.get("dp_capable") else "✗",
                _fmt(r.get("max_hs_operating_m"), dec=2, suffix=" m"),
                _fmt(r.get("typical_depth_m"), dec=0, suffix=" m"),
                f"{r.get('hull_motion_factor', 1.00):.2f}",
                (r.get("notes") or "")[:60],
            ]

            for col_idx, val in enumerate(values):
                item = QTableWidgetItem(str(val))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if is_ref:
                    item.setForeground(QColor("#94a3b8"))
                self._table.setItem(row_idx, col_idx, item)

        self._table.setSortingEnabled(True)
        self._count_label.setText(f"{len(self._rows)} vessel{'s' if len(self._rows) != 1 else ''}")

    # ── Actions ───────────────────────────────────────────────────────────────

    def _selected_row_data(self) -> dict | None:
        sel = self._table.selectedItems()
        if not sel:
            return None
        row = self._table.row(sel[0])
        # Strip 🔒 prefix to find name
        name_cell = self._table.item(row, _COL["Name"]).text()
        name = name_cell.lstrip("🔒 ")
        for r in self._rows:
            if r.get("name") == name:
                return r
        return None

    def _main_window(self):
        p = self.parent()
        while p is not None:
            if hasattr(p, "reload_platforms"):
                return p
            p = p.parent() if hasattr(p, "parent") else None
        return None

    def _on_add(self) -> None:
        from ui.dialogs.vessel_editor import VesselEditorDialog
        dlg = VesselEditorDialog(self, main_window=self._main_window())
        if dlg.exec():
            self._reload_table()

    def _on_edit(self) -> None:
        data = self._selected_row_data()
        if not data:
            QMessageBox.information(self, "No selection", "Select a vessel to edit.")
            return
        if data.get("is_reference"):
            reply = QMessageBox.question(
                self, "Reference Platform",
                f"'{data['name']}' is a Gateway reference platform. Edit anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        from ui.dialogs.vessel_editor import VesselEditorDialog
        dlg = VesselEditorDialog(self, platform_data=data,
                                  main_window=self._main_window())
        if dlg.exec():
            self._reload_table()

    def _on_duplicate(self) -> None:
        data = self._selected_row_data()
        if not data:
            QMessageBox.information(self, "No selection", "Select a vessel to duplicate.")
            return
        dup = dict(data)
        dup.pop("id", None)
        dup["name"] = data["name"] + " (copy)"
        dup["is_reference"] = 0
        from ui.dialogs.vessel_editor import VesselEditorDialog
        dlg = VesselEditorDialog(self, platform_data=dup,
                                  main_window=self._main_window())
        if dlg.exec():
            self._reload_table()

    def _on_delete(self) -> None:
        data = self._selected_row_data()
        if not data:
            QMessageBox.information(self, "No selection", "Select a vessel to delete.")
            return
        if data.get("is_reference"):
            QMessageBox.warning(self, "Protected",
                                "Gateway reference platforms cannot be deleted.")
            return
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete '{data['name']}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            conn = get_connection()
            conn.execute("DELETE FROM platforms WHERE id=?", (data["id"],))
            conn.commit()
            conn.close()
            self._reload_table()
            mw = self._main_window()
            if mw:
                mw.reload_platforms()


def _fmt(val, dec: int = 0, suffix: str = "") -> str:
    if val is None:
        return "—"
    if dec == 0:
        return f"{int(val)}{suffix}"
    return f"{val:.{dec}f}{suffix}"

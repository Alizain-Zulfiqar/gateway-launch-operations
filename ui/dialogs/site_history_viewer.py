"""
ui/dialogs/site_history_viewer.py — View site status history for a project-site pair.

Table is newest-first. Archived rows are dimmed. Show Archived checkbox toggles them.
Document cells are clickable when a stored path exists.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QCheckBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont

from ui.styles import apply_table_colors

_DIM_FG   = QColor("#475569")
_NORMAL_FG = QColor("#e2e8f0")

_STATUS_COLORS = {
    "candidate": ("#1e2d3d", "#93c5fd"),
    "approved":  ("#14532d", "#86efac"),
    "final":     ("#1e3a8a", "#bfdbfe"),
    "rejected":  ("#450a0a", "#fca5a5"),
}

_COLS = ["Date", "Status", "Changed By", "Note", "Document"]
_COL_DATE   = 0
_COL_STATUS = 1
_COL_BY     = 2
_COL_NOTE   = 3
_COL_DOC    = 4


class SiteHistoryViewer(QDialog):
    """Modal dialog showing full status history for a project-site pair."""

    def __init__(
        self,
        project_id: int,
        site_id: int,
        parent=None,
    ):
        super().__init__(parent)
        self._project_id = project_id
        self._site_id = site_id
        self._build()
        self._load()

    def _build(self) -> None:
        self.setWindowTitle("Site Status History")
        self.setMinimumSize(720, 440)
        self.setStyleSheet("background:#0f1923; color:#e2e8f0;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # Header row
        hdr = QHBoxLayout()
        self._title_lbl = QLabel("History")
        self._title_lbl.setStyleSheet(
            "color:#f1f5f9; font-size:11pt; font-weight:bold;"
        )
        hdr.addWidget(self._title_lbl, 1)

        self._show_archived_cb = QCheckBox("Show Archived")
        self._show_archived_cb.setStyleSheet("color:#94a3b8;")
        self._show_archived_cb.stateChanged.connect(self._load)
        hdr.addWidget(self._show_archived_cb)
        layout.addLayout(hdr)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(len(_COLS))
        self._table.setHorizontalHeaderLabels(_COLS)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionResizeMode(
            _COL_NOTE, QHeaderView.ResizeMode.Stretch
        )
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        apply_table_colors(self._table)
        self._table.cellClicked.connect(self._on_cell_clicked)
        layout.addWidget(self._table, 1)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(
            "QPushButton { background:#1e2d3d; color:#e2e8f0; border:1px solid #374151;"
            "border-radius:4px; padding:6px 20px; }"
            "QPushButton:hover { background:#2d3f55; }"
        )
        close_btn.clicked.connect(self.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _load(self) -> None:
        include_archived = self._show_archived_cb.isChecked()

        try:
            from modules.m1_site.project_sites import get_site_history
            from core.database import get_connection
            rows = get_site_history(
                self._project_id, self._site_id, include_archived=include_archived
            )
            conn = get_connection()
            site_row = conn.execute(
                "SELECT name FROM sites WHERE id=?", (self._site_id,)
            ).fetchone()
            conn.close()
            site_name = site_row["name"] if site_row else f"Site {self._site_id}"
        except Exception:
            rows = []
            site_name = f"Site {self._site_id}"

        self._title_lbl.setText(f"History — {site_name}")
        self._table.setRowCount(len(rows))
        self._doc_paths: list[str | None] = []

        for row_idx, row in enumerate(rows):
            archived = bool(row.get("archived", 0))
            fg = _DIM_FG if archived else _NORMAL_FG

            # Date
            created = str(row.get("created_at", ""))[:19]
            self._table.setItem(row_idx, _COL_DATE, _cell(created, fg))

            # Status
            status = row.get("status", "")
            st_item = _cell(status.replace("_", " ").title(), fg)
            bg_hex, fg_hex = _STATUS_COLORS.get(status, ("#374151", "#94a3b8"))
            if not archived:
                st_item.setBackground(QColor(bg_hex))
                st_item.setForeground(QColor(fg_hex))
            self._table.setItem(row_idx, _COL_STATUS, st_item)

            # Changed by
            self._table.setItem(
                row_idx, _COL_BY, _cell(row.get("changed_by") or "—", fg)
            )

            # Note
            self._table.setItem(
                row_idx, _COL_NOTE, _cell(row.get("approval_note") or "", fg)
            )

            # Document
            doc_path = row.get("document_path")
            self._doc_paths.append(doc_path)
            if doc_path:
                from pathlib import Path
                doc_item = _cell(f"📎 {Path(doc_path).name}", fg if archived else QColor("#93c5fd"))
                doc_item.setData(Qt.ItemDataRole.UserRole, doc_path)
            else:
                doc_item = _cell("—", fg)
            self._table.setItem(row_idx, _COL_DOC, doc_item)

        self._table.resizeColumnsToContents()
        self._table.horizontalHeader().setSectionResizeMode(
            _COL_NOTE, QHeaderView.ResizeMode.Stretch
        )

    def _on_cell_clicked(self, row: int, col: int) -> None:
        if col != _COL_DOC:
            return
        item = self._table.item(row, col)
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path:
            return
        try:
            from core.file_attachments import open_attachment
            open_attachment(path)
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Cannot Open", str(e))


def _cell(text: str, fg: QColor) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setForeground(fg)
    return item

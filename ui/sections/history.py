"""
ui/sections/history.py — Session/analysis history (Set 40).

Read-only chronological view merging four already-timestamped, already-
existing tables: analyses, project_site_status_history, reports, and
site_vehicles. No new schema — see UX_Audit_Backlog_001.md's Set 40 scope
for why. Explicitly no edit/delete here: project_site_status_history is
append-only elsewhere in this app, and History should stay consistent with
that rule rather than invent a new mutation path.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt

from core.database import get_connection
from ui.styles import apply_table_colors

_BTN_SECONDARY = (
    "QPushButton {"
    "  background: #1e293b; color: #cbd5e1;"
    "  border: 1px solid #374151; border-radius: 4px; padding: 6px 16px;"
    "}"
    "QPushButton:hover { background: #334155; }"
)
_COMBO_STYLE = (
    "QComboBox { background: #1a2233; color: #e2e8f0; border: 1px solid #374151;"
    " border-radius: 3px; padding: 2px 8px; }"
    "QComboBox QAbstractItemView { background: #1a2233; color: #e2e8f0; }"
)

_TYPE_LABELS = {
    "analysis":  "Analysis run",
    "status":    "Status change",
    "report":    "Report generated",
    "vehicle":   "Vehicle used",
}

# event type -> section key to jump to on row activation
_TYPE_SECTION = {
    "analysis": "analysis",
    "status":   "projects",
    "report":   "reports",
    "vehicle":  "sites",
}

_COLUMNS = ["Type", "Timestamp", "Project", "Site", "Summary"]


class HistorySection(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._events: list[dict] = []
        self._build()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._reload_filters()
        self.refresh_history()

    def on_project_changed(self) -> None:
        """Default the project filter to the open project (or All Projects when
        closed). Called by GatewayMainWindow.open_project()/close_project()."""
        self._reload_filters()
        open_id = getattr(self.mw, "open_project_id", None)
        idx = self._project_combo.findData(open_id) if open_id is not None else 0
        self._project_combo.blockSignals(True)
        self._project_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._project_combo.blockSignals(False)
        self.refresh_history()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        title = QLabel("History")
        title.setObjectName("sectionTitle")
        root.addWidget(title)

        hint = QLabel(
            "Analysis runs, project status changes, generated reports, and "
            "vehicle usage across every site and project — newest first."
        )
        hint.setStyleSheet("color: #64748b; font-size: 10pt;")
        hint.setWordWrap(True)
        root.addWidget(hint)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        filter_row.addWidget(QLabel("Type:"))
        self._type_combo = QComboBox()
        self._type_combo.setStyleSheet(_COMBO_STYLE)
        self._type_combo.addItem("All Types", userData=None)
        for key, label in _TYPE_LABELS.items():
            self._type_combo.addItem(label, userData=key)
        self._type_combo.currentIndexChanged.connect(self.refresh_history)
        filter_row.addWidget(self._type_combo)

        filter_row.addWidget(QLabel("Project:"))
        self._project_combo = QComboBox()
        self._project_combo.setStyleSheet(_COMBO_STYLE)
        self._project_combo.setMinimumWidth(160)
        self._project_combo.currentIndexChanged.connect(self.refresh_history)
        filter_row.addWidget(self._project_combo)

        filter_row.addWidget(QLabel("Site:"))
        self._site_combo = QComboBox()
        self._site_combo.setStyleSheet(_COMBO_STYLE)
        self._site_combo.setMinimumWidth(160)
        self._site_combo.currentIndexChanged.connect(self.refresh_history)
        filter_row.addWidget(self._site_combo)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setStyleSheet(_BTN_SECONDARY)
        refresh_btn.clicked.connect(self.refresh_history)
        filter_row.addWidget(refresh_btn)

        filter_row.addStretch()
        root.addLayout(filter_row)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch
        )
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.cellDoubleClicked.connect(self._on_row_activated)
        apply_table_colors(self._table)
        root.addWidget(self._table, 1)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: #64748b; font-size: 8pt;")
        root.addWidget(self._status_lbl)

        note = QLabel(
            "Double-click a row to jump to the relevant section. History is "
            "read-only — edit or delete entries from their own section "
            "(Analysis, Projects, Reports)."
        )
        note.setStyleSheet("color: #475569; font-size: 7.5pt; font-style: italic;")
        note.setWordWrap(True)
        root.addWidget(note)

    # ── Filter combos ────────────────────────────────────────────────────────

    def _reload_filters(self) -> None:
        try:
            conn = get_connection()
            projects = conn.execute(
                "SELECT id, name FROM projects ORDER BY name"
            ).fetchall()
            sites = conn.execute(
                "SELECT id, name FROM sites ORDER BY name"
            ).fetchall()
            conn.close()
        except Exception:
            projects, sites = [], []

        prev_proj = self._project_combo.currentData()
        self._project_combo.blockSignals(True)
        self._project_combo.clear()
        self._project_combo.addItem("All Projects", userData=None)
        for p in projects:
            self._project_combo.addItem(p["name"], userData=p["id"])
        idx = self._project_combo.findData(prev_proj)
        self._project_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._project_combo.blockSignals(False)

        prev_site = self._site_combo.currentData()
        self._site_combo.blockSignals(True)
        self._site_combo.clear()
        self._site_combo.addItem("All Sites", userData=None)
        for s in sites:
            self._site_combo.addItem(s["name"] or f"Site {s['id']}", userData=s["id"])
        idx = self._site_combo.findData(prev_site)
        self._site_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._site_combo.blockSignals(False)

    # ── Data loading ──────────────────────────────────────────────────────────

    def refresh_history(self, *_) -> None:
        try:
            self._events = self._load_events()
        except Exception as exc:
            self._events = []
            self._status_lbl.setText(f"Error loading history: {exc}")
            self._table.setRowCount(0)
            return

        type_filter = self._type_combo.currentData()
        project_filter = self._project_combo.currentData()
        site_filter = self._site_combo.currentData()

        rows = [
            e for e in self._events
            if (type_filter is None or e["type"] == type_filter)
            and (project_filter is None or e["project_id"] == project_filter)
            and (site_filter is None or e["site_id"] == site_filter)
        ]

        self._table.setRowCount(0)
        for row in rows:
            row_idx = self._table.rowCount()
            self._table.insertRow(row_idx)
            cells = [
                _TYPE_LABELS.get(row["type"], row["type"]),
                row["timestamp"] or "",
                row["project_name"] or "—",
                row["site_name"] or "—",
                row["summary"],
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(str(text))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row)
                self._table.setItem(row_idx, col, item)

        self._status_lbl.setText(
            f"{len(rows)} event{'s' if len(rows) != 1 else ''}"
            + (f" (of {len(self._events)} total)" if len(rows) != len(self._events) else "")
        )

    def _load_events(self) -> list[dict]:
        conn = get_connection()
        try:
            events: list[dict] = []

            for r in conn.execute(
                """
                SELECT a.id, a.created_at, a.overall_prob, a.mode,
                       s.id AS site_id, s.name AS site_name,
                       v.name AS vehicle_name
                  FROM analyses a
                  JOIN sites s    ON s.id = a.site_id
                  JOIN vehicles v ON v.id = a.vehicle_id
                 ORDER BY a.created_at DESC
                """
            ).fetchall():
                pct = round((r["overall_prob"] or 0) * 100)
                events.append({
                    "type": "analysis",
                    "timestamp": r["created_at"],
                    "site_id": r["site_id"],
                    "site_name": r["site_name"],
                    "project_id": None,
                    "project_name": None,
                    "summary": f"{r['vehicle_name']} — {r['mode']}, {pct}%",
                })

            for r in conn.execute(
                """
                SELECT h.id, h.created_at, h.status, h.changed_by,
                       s.id AS site_id, s.name AS site_name,
                       p.id AS project_id, p.name AS project_name
                  FROM project_site_status_history h
                  JOIN sites s    ON s.id = h.site_id
                  JOIN projects p ON p.id = h.project_id
                 ORDER BY h.created_at DESC
                """
            ).fetchall():
                summary = f"Status → {r['status']}"
                if r["changed_by"]:
                    summary += f" (by {r['changed_by']})"
                events.append({
                    "type": "status",
                    "timestamp": r["created_at"],
                    "site_id": r["site_id"],
                    "site_name": r["site_name"],
                    "project_id": r["project_id"],
                    "project_name": r["project_name"],
                    "summary": summary,
                })

            for r in conn.execute(
                """
                SELECT rp.id, rp.generated_at, rp.filename, rp.report_type,
                       s.id AS site_id, s.name AS site_name,
                       p.id AS project_id, p.name AS project_name
                  FROM reports rp
                  JOIN sites s        ON s.id = rp.site_id
                  LEFT JOIN projects p ON p.id = rp.project_id
                 ORDER BY rp.generated_at DESC
                """
            ).fetchall():
                events.append({
                    "type": "report",
                    "timestamp": r["generated_at"],
                    "site_id": r["site_id"],
                    "site_name": r["site_name"],
                    "project_id": r["project_id"],
                    "project_name": r["project_name"],
                    "summary": f"{r['report_type'].title()} report: {r['filename']}",
                })

            for r in conn.execute(
                """
                SELECT sv.last_used, sv.run_count,
                       s.id AS site_id, s.name AS site_name,
                       v.name AS vehicle_name
                  FROM site_vehicles sv
                  JOIN sites s    ON s.id = sv.site_id
                  JOIN vehicles v ON v.id = sv.vehicle_id
                 ORDER BY sv.last_used DESC
                """
            ).fetchall():
                events.append({
                    "type": "vehicle",
                    "timestamp": r["last_used"],
                    "site_id": r["site_id"],
                    "site_name": r["site_name"],
                    "project_id": None,
                    "project_name": None,
                    "summary": f"{r['vehicle_name']} used ({r['run_count']}x)",
                })

            events.sort(key=lambda e: e["timestamp"] or "", reverse=True)
            return events
        finally:
            conn.close()

    # ── Navigation ────────────────────────────────────────────────────────────

    def _on_row_activated(self, row: int, _col: int) -> None:
        item = self._table.item(row, 0)
        if item is None:
            return
        event = item.data(Qt.ItemDataRole.UserRole)
        if not event:
            return
        key = _TYPE_SECTION.get(event["type"])
        if key:
            self._go_to_section(key)

    def _go_to_section(self, key: str) -> None:
        if hasattr(self.mw, "_on_section_changed"):
            self.mw._on_section_changed(key)
            if hasattr(self.mw, "sidebar"):
                self.mw.sidebar.select_section(key)

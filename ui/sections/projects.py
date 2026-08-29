"""
ui/sections/projects.py — Projects section: manage launch site evaluation projects.

Left panel (360px): project list + create button.
Right panel: project detail form + candidate sites table with History/Actions.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QLineEdit, QTextEdit, QComboBox, QMessageBox, QSplitter,
    QFrame, QScrollArea, QSizePolicy, QCheckBox, QDialog,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont

from config import PROJECT_STATUS_OPTIONS, CANDIDATE_STATUS_OPTIONS
from ui.styles import apply_table_colors


# ── Styles ────────────────────────────────────────────────────────────────────

_BTN_PRIMARY = (
    "QPushButton { background:#2563eb; color:white; border-radius:4px;"
    "padding:6px 16px; font-weight:bold; border:none; }"
    "QPushButton:hover { background:#1d4ed8; }"
    "QPushButton:disabled { background:#1e3a5f; color:#64748b; }"
)
_BTN_SECONDARY = (
    "QPushButton { background:#1e2d3d; color:#e2e8f0; border:1px solid #374151;"
    "border-radius:4px; padding:5px 12px; }"
    "QPushButton:hover { background:#2d3f55; }"
    "QPushButton:disabled { color:#4b5563; }"
)
_BTN_DANGER = (
    "QPushButton { background:#450a0a; color:#fca5a5; border:1px solid #7f1d1d;"
    "border-radius:4px; padding:5px 12px; }"
    "QPushButton:hover { background:#7f1d1d; color:#fee2e2; }"
)
_INPUT_STYLE = (
    "QLineEdit, QTextEdit, QComboBox { background:#1a2233; color:#e2e8f0;"
    "border:1px solid #374151; border-radius:4px; padding:4px 8px; }"
    "QLineEdit:focus, QTextEdit:focus, QComboBox:focus { border-color:#2563eb; }"
    "QComboBox::drop-down { border:none; width:20px; }"
    "QComboBox QAbstractItemView { background:#1a2233; color:#e2e8f0; "
    "selection-background-color:#2563eb; }"
)
_LABEL_STYLE = "color:#94a3b8; font-size:8pt;"
_SECTION_TITLE = "color:#f1f5f9; font-size:11pt; font-weight:bold;"

_STATUS_COLORS = {
    "candidate": ("#1e2d3d", "#93c5fd"),
    "approved":  ("#14532d", "#86efac"),
    "final":     ("#1e3a8a", "#bfdbfe"),
    "rejected":  ("#450a0a", "#fca5a5"),
    "planning":  ("#1e2d3d", "#93c5fd"),
    "pending":   ("#422006", "#fde68a"),
    "completed": ("#1e3a8a", "#bfdbfe"),
    "cancelled": ("#450a0a", "#fca5a5"),
}


def _status_badge(status: str) -> QLabel:
    bg, fg = _STATUS_COLORS.get(status, ("#374151", "#94a3b8"))
    lbl = QLabel(status.replace("_", " ").title())
    lbl.setStyleSheet(
        f"background:{bg}; color:{fg}; border-radius:3px;"
        f"padding:2px 8px; font-size:8pt; font-weight:600;"
    )
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lbl


class _ProjectListItem(QPushButton):
    def __init__(self, project_id: int, name: str, status: str, parent=None):
        super().__init__(parent)
        self.project_id = project_id
        self.setCheckable(True)
        self.setFlat(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(52)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet("color:#e2e8f0; font-weight:600; background:transparent;")
        name_lbl.setWordWrap(True)
        layout.addWidget(name_lbl, 1)
        layout.addWidget(_status_badge(status))

        self.setStyleSheet(
            "QPushButton { background:transparent; border:none; text-align:left; "
            "border-left:3px solid transparent; }"
            "QPushButton:hover { background:#1e2d3d; border-left-color:#374151; }"
            "QPushButton:checked { background:#1e3a5f; border-left-color:#2563eb; }"
        )


class ProjectsSection(QWidget):
    """Projects section — left panel list, right panel detail + sites table."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.mw = parent  # GatewayMainWindow — owns open/close project state
        self._current_project_id: Optional[int] = None
        self._show_archived: bool = False
        self._build()
        self._refresh_project_list()
        self._reload_contract_combo()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Refresh the contract picker so contracts added/archived elsewhere
        # (Contracts tab) are current when the user returns here.
        self._reload_contract_combo()

    # ── Build ──────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background:#1e2d3d; }")

        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([360, 900])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)

        root.addWidget(splitter)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(360)
        panel.setStyleSheet("background:#0f1923; border-right:1px solid #1e2d3d;")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setStyleSheet("background:#1a2233; border-bottom:1px solid #1e2d3d;")
        hdr_layout = QHBoxLayout(header)
        hdr_layout.setContentsMargins(16, 12, 16, 12)
        title = QLabel("Projects")
        title.setStyleSheet(_SECTION_TITLE)
        hdr_layout.addWidget(title, 1)
        self._new_project_btn = QPushButton("+ New")
        self._new_project_btn.setStyleSheet(_BTN_PRIMARY)
        self._new_project_btn.setFixedWidth(70)
        self._new_project_btn.clicked.connect(self._on_new_project)
        hdr_layout.addWidget(self._new_project_btn)
        layout.addWidget(header)

        # Archive filter checkbox
        filter_widget = QWidget()
        filter_widget.setStyleSheet("background:#0f1923; border-bottom:1px solid #1e2d3d;")
        filter_layout = QHBoxLayout(filter_widget)
        filter_layout.setContentsMargins(16, 6, 16, 6)
        self._show_archived_check = QCheckBox("Show archived")
        self._show_archived_check.setStyleSheet("color:#94a3b8; spacing:4px;")
        self._show_archived_check.stateChanged.connect(self._on_archive_filter_changed)
        filter_layout.addWidget(self._show_archived_check)
        filter_layout.addStretch(1)
        layout.addWidget(filter_widget)

        # Scrollable list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { border:none; background:#0f1923; }"
            "QScrollBar:vertical { background:#0f1923; width:6px; }"
            "QScrollBar::handle:vertical { background:#374151; border-radius:3px; }"
        )
        self._list_container = QWidget()
        self._list_container.setStyleSheet("background:#0f1923;")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 4, 0, 4)
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch(1)
        scroll.setWidget(self._list_container)
        layout.addWidget(scroll, 1)

        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background:#0f1923;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # ── Placeholder when no project selected ──────────────────────────────
        self._placeholder = QLabel(
            "Select a project from the left panel\nor create a new one."
        )
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet("color:#475569; font-size:12pt;")
        layout.addWidget(self._placeholder)

        # ── Detail form ───────────────────────────────────────────────────────
        self._detail_widget = QWidget()
        self._detail_widget.hide()
        detail_layout = QVBoxLayout(self._detail_widget)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(12)

        # Open / Close project bar — the primary action that reveals the
        # project-scoped tabs (Sites, Analysis, Comparison, …) in the sidebar.
        open_bar = QHBoxLayout()
        self._open_project_btn = QPushButton("▶  Open Project")
        self._open_project_btn.setStyleSheet(_BTN_PRIMARY)
        self._open_project_btn.setMinimumHeight(36)
        self._open_project_btn.clicked.connect(self._on_open_project)
        open_bar.addWidget(self._open_project_btn)
        self._close_project_btn = QPushButton("Close Project")
        self._close_project_btn.setStyleSheet(_BTN_SECONDARY)
        self._close_project_btn.setMinimumHeight(36)
        self._close_project_btn.clicked.connect(self._on_close_project)
        self._close_project_btn.hide()
        open_bar.addWidget(self._close_project_btn)
        self._open_state_lbl = QLabel("")
        self._open_state_lbl.setStyleSheet("color:#86efac; font-size:9pt; font-weight:600;")
        open_bar.addWidget(self._open_state_lbl, 1)
        detail_layout.addLayout(open_bar)

        # Project name
        detail_layout.addWidget(_lbl("Project Name"))
        self._name_edit = QLineEdit()
        self._name_edit.setStyleSheet(_INPUT_STYLE)
        self._name_edit.setPlaceholderText("Enter project name…")
        detail_layout.addWidget(self._name_edit)

        # Description
        detail_layout.addWidget(_lbl("Description"))
        self._desc_edit = QTextEdit()
        self._desc_edit.setStyleSheet(_INPUT_STYLE)
        self._desc_edit.setMaximumHeight(80)
        self._desc_edit.setPlaceholderText("Optional description…")
        detail_layout.addWidget(self._desc_edit)

        # Status
        row = QHBoxLayout()
        status_col = QVBoxLayout()
        status_col.addWidget(_lbl("Project Status"))
        self._status_combo = QComboBox()
        self._status_combo.setStyleSheet(_INPUT_STYLE)
        for s in PROJECT_STATUS_OPTIONS:
            self._status_combo.addItem(s.replace("_", " ").title(), s)
        status_col.addWidget(self._status_combo)
        row.addLayout(status_col)
        row.addStretch(1)

        btn_col = QVBoxLayout()
        btn_col.addStretch(1)
        btn_row = QHBoxLayout()
        self._save_project_btn = QPushButton("Save")
        self._save_project_btn.setStyleSheet(_BTN_PRIMARY)
        self._save_project_btn.clicked.connect(self._on_save_project)
        btn_row.addWidget(self._save_project_btn)
        self._archive_project_btn = QPushButton("Archive")
        self._archive_project_btn.setStyleSheet(_BTN_SECONDARY)
        self._archive_project_btn.clicked.connect(self._on_archive_project)
        btn_row.addWidget(self._archive_project_btn)
        btn_col.addLayout(btn_row)
        row.addLayout(btn_col)
        detail_layout.addLayout(row)

        # Linked platform contract — governs the vessel pre-check gate for
        # this project (Pre-28B-2 Step 6). A project links to exactly one
        # contract row (projects.platform_contract_id is a single nullable
        # FK, not a join table); if that row is a subcontract/amendment,
        # resolve_warranted_envelope() already walks parent_contract_id
        # upward for any warranted field the linked row leaves unset — link
        # to whichever single contract is most specific to this project.
        detail_layout.addWidget(_lbl("Linked Contract (vessel pre-check gate)"))
        self._contract_combo = QComboBox()
        self._contract_combo.setStyleSheet(_INPUT_STYLE)
        detail_layout.addWidget(self._contract_combo)

        # Divider
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background:#1e2d3d;")
        detail_layout.addWidget(sep)

        # Sites sub-section
        sites_header = QHBoxLayout()
        sites_title = QLabel("Candidate Sites")
        sites_title.setStyleSheet("color:#f1f5f9; font-size:10pt; font-weight:600;")
        sites_header.addWidget(sites_title, 1)
        self._create_site_btn = QPushButton("+ Create New Site")
        self._create_site_btn.setStyleSheet(_BTN_PRIMARY)
        self._create_site_btn.clicked.connect(self._on_create_site)
        sites_header.addWidget(self._create_site_btn)
        self._add_site_btn = QPushButton("Add Existing")
        self._add_site_btn.setStyleSheet(_BTN_SECONDARY)
        self._add_site_btn.clicked.connect(self._on_add_site)
        sites_header.addWidget(self._add_site_btn)
        detail_layout.addLayout(sites_header)

        sites_note = QLabel(
            "“Create New Site” adds a brand-new site record and links it to this "
            "project in one step — no need to visit the Sites tab first. “Add "
            "Existing” links an already-saved site via a picker. Add as many "
            "sites as you like; opening the project makes them all available in "
            "the Analysis tab."
        )
        sites_note.setWordWrap(True)
        sites_note.setStyleSheet("color:#64748b; font-size:8pt; padding-bottom:4px;")
        detail_layout.addWidget(sites_note)

        self._sites_table = QTableWidget()
        self._sites_table.setColumnCount(6)
        self._sites_table.setHorizontalHeaderLabels(
            ["Site Name", "Coord Code", "Lat", "Lon", "Status", "Actions"]
        )
        self._sites_table.horizontalHeader().setStretchLastSection(False)
        self._sites_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._sites_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._sites_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._sites_table.verticalHeader().setVisible(False)
        self._sites_table.setAlternatingRowColors(True)
        apply_table_colors(self._sites_table)
        # Cap visible rows to ~10 before internal scrolling engages, rather
        # than leaving the table unbounded now that it is no longer starved
        # of vertical space (see the removed layout.addStretch(1) below) —
        # otherwise a tall window would let it push toward infinite height.
        _row_h = self._sites_table.verticalHeader().defaultSectionSize()
        _hdr_h = self._sites_table.horizontalHeader().height()
        self._sites_table.setMaximumHeight(_hdr_h + _row_h * 10 + 4)
        detail_layout.addWidget(self._sites_table, 1)

        layout.addWidget(self._detail_widget, 1)
        # NOTE: no trailing addStretch(1) here — a previous version had one,
        # which gave the invisible spacer an equal stretch factor to
        # _detail_widget above and silently claimed ~half the panel's leftover
        # vertical space, starving the Candidate Sites table down to ~1 visible
        # row regardless of window height. _detail_widget's own stretch=1 is
        # now the only stretch item in this layout, so it (and the table
        # inside it, up to the cap above) receives all of the panel's leftover
        # space instead of splitting it with a spacer.

        return panel

    # ── Project list ───────────────────────────────────────────────────────────

    def _refresh_project_list(self) -> None:
        try:
            from core.database import get_connection
            conn = get_connection()
            where_clause = "" if self._show_archived else "WHERE is_archived = 0"
            rows = conn.execute(
                f"SELECT id, name, status FROM projects {where_clause} ORDER BY updated_at DESC, id DESC"
            ).fetchall()
            conn.close()
        except Exception:
            rows = []

        # Clear existing items (keep stretch)
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._project_buttons: list[_ProjectListItem] = []
        for row in rows:
            btn = _ProjectListItem(row["id"], row["name"], row["status"])
            btn.clicked.connect(lambda checked, pid=row["id"]: self._select_project(pid))
            self._list_layout.insertWidget(self._list_layout.count() - 1, btn)
            self._project_buttons.append(btn)

        if not rows:
            hint = QLabel("No projects yet.\nClick + New to create one.")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setStyleSheet("color:#475569; font-size:9pt; padding:24px;")
            self._list_layout.insertWidget(0, hint)

    def _on_archive_filter_changed(self) -> None:
        """Toggle archive filter and refresh list."""
        self._show_archived = self._show_archived_check.isChecked()
        self._refresh_project_list()

    def _reload_contract_combo(self) -> None:
        """Populate the Linked Contract combo. Archived contracts are excluded
        from the general list (matching the Contracts tab's default filter),
        but _select_project() re-adds the currently-linked one if it happens
        to be archived, so an existing link is never silently hidden."""
        try:
            from core.database import get_connection
            conn = get_connection()
            rows = conn.execute(
                "SELECT id, contract_code, customer_name FROM platform_contracts "
                "WHERE is_archived=0 ORDER BY contract_code"
            ).fetchall()
            conn.close()
            contracts = [dict(r) for r in rows]
        except Exception:
            contracts = []

        prev = self._contract_combo.currentData()
        self._contract_combo.blockSignals(True)
        self._contract_combo.clear()
        self._contract_combo.addItem("— No linked contract —", userData=None)
        for c in contracts:
            self._contract_combo.addItem(
                f"{c['contract_code']} ({c['customer_name']})", userData=c["id"]
            )
        if prev is not None:
            idx = self._contract_combo.findData(prev)
            self._contract_combo.setCurrentIndex(idx if idx >= 0 else 0)
        else:
            self._contract_combo.setCurrentIndex(0)
        self._contract_combo.blockSignals(False)

    def _select_project(self, project_id: int) -> None:
        self._current_project_id = project_id
        for btn in self._project_buttons:
            btn.setChecked(btn.project_id == project_id)

        try:
            from core.database import get_connection
            conn = get_connection()
            row = conn.execute(
                "SELECT * FROM projects WHERE id=?", (project_id,)
            ).fetchone()
            conn.close()
        except Exception:
            return

        if not row:
            return

        self._name_edit.setText(row["name"])
        self._desc_edit.setPlainText(row["description"] or "")
        idx = self._status_combo.findData(row["status"])
        if idx >= 0:
            self._status_combo.setCurrentIndex(idx)

        contract_id = row["platform_contract_id"]
        c_idx = self._contract_combo.findData(contract_id)
        if contract_id is not None and c_idx < 0:
            # Linked contract is archived (or otherwise absent from the active
            # list) — inject it so the existing link stays visible rather than
            # silently appearing unlinked.
            try:
                from core.database import get_connection
                conn = get_connection()
                crow = conn.execute(
                    "SELECT contract_code, customer_name FROM platform_contracts "
                    "WHERE id=?", (contract_id,)
                ).fetchone()
                conn.close()
            except Exception:
                crow = None
            if crow:
                self._contract_combo.addItem(
                    f"{crow['contract_code']} ({crow['customer_name']}) [archived]",
                    userData=contract_id,
                )
                c_idx = self._contract_combo.count() - 1
        self._contract_combo.setCurrentIndex(c_idx if c_idx >= 0 else 0)

        self._placeholder.hide()
        self._detail_widget.show()
        self._refresh_sites_table()
        self._update_open_state()

    def _update_open_state(self) -> None:
        """Reflect whether the selected project is the one currently open."""
        open_id = getattr(self.mw, "open_project_id", None) if self.mw else None
        is_open = open_id is not None and open_id == self._current_project_id
        self._open_project_btn.setVisible(not is_open)
        self._close_project_btn.setVisible(is_open)
        self._open_state_lbl.setText("● Project open" if is_open else "")

    def _on_open_project(self) -> None:
        if self._current_project_id is None or not self.mw:
            return
        # Persist any pending edits first so the opened project reflects them.
        name = self._name_edit.text().strip() or "Untitled"
        self.mw.open_project(self._current_project_id, name)
        self._update_open_state()

    def _on_close_project(self) -> None:
        if not self.mw:
            return
        self.mw.close_project()
        self._update_open_state()

    def _refresh_sites_table(self) -> None:
        if self._current_project_id is None:
            return
        try:
            from modules.m1_site.project_sites import list_project_sites
            sites = list_project_sites(self._current_project_id)
        except Exception:
            sites = []

        self._sites_table.setRowCount(len(sites))
        for row_idx, site in enumerate(sites):
            self._sites_table.setItem(
                row_idx, 0, QTableWidgetItem(site.get("site_name", ""))
            )
            self._sites_table.setItem(
                row_idx, 1, QTableWidgetItem(site.get("coord_code") or "—")
            )
            self._sites_table.setItem(
                row_idx, 2, QTableWidgetItem(f"{site.get('lat', 0):.4f}°")
            )
            self._sites_table.setItem(
                row_idx, 3, QTableWidgetItem(f"{site.get('lon', 0):.4f}°")
            )
            status = site.get("status", "candidate")
            status_item = QTableWidgetItem(status.replace("_", " ").title())
            bg, fg = _STATUS_COLORS.get(status, ("#374151", "#94a3b8"))
            status_item.setBackground(QColor(bg))
            status_item.setForeground(QColor(fg))
            self._sites_table.setItem(row_idx, 4, status_item)

            # Actions cell: History + Status buttons
            actions = QWidget()
            actions.setStyleSheet("background:transparent;")
            act_layout = QHBoxLayout(actions)
            act_layout.setContentsMargins(4, 2, 4, 2)
            act_layout.setSpacing(4)

            hist_btn = QPushButton("History")
            hist_btn.setStyleSheet(_BTN_SECONDARY)
            hist_btn.setFixedHeight(24)
            hist_btn.clicked.connect(
                lambda _, sid=site["site_id"]: self._show_history(sid)
            )
            act_layout.addWidget(hist_btn)

            status_btn = QPushButton("Change…")
            status_btn.setStyleSheet(_BTN_SECONDARY)
            status_btn.setFixedHeight(24)
            status_btn.clicked.connect(
                lambda _, sid=site["site_id"], st=status: self._change_status(sid, st)
            )
            act_layout.addWidget(status_btn)

            edit_btn = QPushButton("Edit")
            edit_btn.setStyleSheet(_BTN_SECONDARY)
            edit_btn.setFixedHeight(24)
            edit_btn.clicked.connect(
                lambda _, sid=site["site_id"]: self._on_edit_site(sid)
            )
            act_layout.addWidget(edit_btn)

            remove_btn = QPushButton("Remove")
            remove_btn.setStyleSheet(_BTN_SECONDARY)
            remove_btn.setFixedHeight(24)
            remove_btn.clicked.connect(
                lambda _, sid=site["site_id"], nm=site.get("site_name", ""):
                    self._on_remove_candidate_site(sid, nm)
            )
            act_layout.addWidget(remove_btn)
            act_layout.addStretch(1)

            self._sites_table.setCellWidget(row_idx, 5, actions)

        self._sites_table.resizeColumnsToContents()
        self._sites_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )

    # ── Slots ──────────────────────────────────────────────────────────────────

    def _on_new_project(self) -> None:
        name, ok = _input_dialog(self, "New Project", "Project name:")
        if not ok or not name.strip():
            return
        try:
            from core.database import get_connection
            conn = get_connection()
            c = conn.cursor()
            c.execute(
                "INSERT INTO projects (name, status) VALUES (?, 'planning')",
                (name.strip(),),
            )
            conn.commit()
            new_id = c.lastrowid
            conn.close()
            self._refresh_project_list()
            self._select_project(new_id)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_save_project(self) -> None:
        if self._current_project_id is None:
            return
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Project name is required.")
            return
        desc = self._desc_edit.toPlainText().strip()
        status = self._status_combo.currentData()
        contract_id = self._contract_combo.currentData()
        try:
            from core.database import get_connection
            conn = get_connection()
            conn.execute(
                """UPDATE projects SET name=?, description=?, status=?,
                   platform_contract_id=?, updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (name, desc, status, contract_id, self._current_project_id),
            )
            conn.commit()
            conn.close()
            self._refresh_project_list()
            # Re-select to refresh button highlight
            self._select_project(self._current_project_id)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_archive_project(self) -> None:
        if self._current_project_id is None:
            return
        reply = QMessageBox.question(
            self, "Archive Project",
            "Archive this project? It will be hidden from the list but remain in the database.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            from core.database import get_connection
            conn = get_connection()
            conn.execute(
                "UPDATE projects SET is_archived=1, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (self._current_project_id,),
            )
            conn.commit()
            conn.close()
            self._current_project_id = None
            self._refresh_project_list()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_add_site(self) -> None:
        if self._current_project_id is None:
            return
        try:
            from modules.m1_site.site_config import list_sites
            sites = list_sites()
        except Exception:
            sites = []

        if not sites:
            QMessageBox.information(
                self, "No Sites",
                "No saved sites found. Save a site in the Sites section first."
            )
            return

        from PyQt6.QtWidgets import QInputDialog
        choices = [f"{s.name} ({s.coord_code or 'no code'})" for s in sites]
        choice, ok = QInputDialog.getItem(
            self, "Add Site to Project", "Select site:", choices, 0, False
        )
        if not ok:
            return
        idx = choices.index(choice)
        site = sites[idx]

        try:
            from modules.m1_site.project_sites import add_site_to_project
            add_site_to_project(self._current_project_id, site.id)
            self._refresh_sites_table()
            self._sync_open_project()
        except ValueError as e:
            QMessageBox.warning(self, "Already Added", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_create_site(self) -> None:
        """Create a brand-new site record and link it to the current project in
        one step (no Sites-tab round-trip required)."""
        if self._current_project_id is None:
            return
        dlg = _CreateSiteDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.new_site is None:
            return
        try:
            from modules.m1_site.site_config import save_site
            from modules.m1_site.project_sites import add_site_to_project
            save_site(dlg.new_site)  # sets new_site.id
            add_site_to_project(self._current_project_id, dlg.new_site.id)
            self._refresh_sites_table()
            self._sync_open_project()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _sync_open_project(self) -> None:
        """If the project being edited is the one currently open, refresh the
        main window's cached project sites so the Analysis/Comparison selectors
        stay in step after a site is added, created, or removed."""
        if not self.mw:
            return
        if getattr(self.mw, "open_project_id", None) == self._current_project_id:
            refresh = getattr(self.mw, "refresh_open_project_sites", None)
            if callable(refresh):
                refresh()

    def _show_history(self, site_id: int) -> None:
        if self._current_project_id is None:
            return
        from ui.dialogs.site_history_viewer import SiteHistoryViewer
        dlg = SiteHistoryViewer(self._current_project_id, site_id, parent=self)
        dlg.exec()

    def _change_status(self, site_id: int, current_status: str) -> None:
        if self._current_project_id is None:
            return
        from PyQt6.QtWidgets import QInputDialog
        choices = [s for s in CANDIDATE_STATUS_OPTIONS if s != current_status]
        if not choices:
            return
        choice, ok = QInputDialog.getItem(
            self, "Change Status",
            f"New status for site (current: {current_status}):",
            choices, 0, False,
        )
        if not ok:
            return
        note, ok2 = _input_dialog(self, "Approval Note", "Note (optional):")
        if not ok2:
            return
        try:
            from modules.m1_site.project_sites import change_site_status
            change_site_status(
                self._current_project_id, site_id, choice,
                approval_note=note.strip(),
            )
            self._refresh_sites_table()
        except Exception:
            QMessageBox.critical(
                self, "Error",
                "This site's status could not be changed. Please try again."
            )

    def _on_edit_site(self, site_id: int) -> None:
        from modules.m1_site.site_config import get_site, update_site
        from ui.dialogs.site_editor import SiteEditorDialog
        try:
            site = get_site(site_id)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return

        dlg = SiteEditorDialog(self, site=site)
        if dlg.exec() != SiteEditorDialog.DialogCode.Accepted or dlg.updated_site is None:
            return
        try:
            update_site(dlg.updated_site)
            self._refresh_sites_table()
            self._sync_open_project()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_remove_candidate_site(self, site_id: int, site_name: str) -> None:
        if self._current_project_id is None:
            return
        reply = QMessageBox.question(
            self, "Remove Site",
            f"Remove '{site_name or 'this site'}' from this project's candidate "
            "list? The site itself is not deleted — only its association with "
            "this project.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            from modules.m1_site.project_sites import remove_site_from_project
            remove_site_from_project(self._current_project_id, site_id)

            # If this site+project pairing was the active one, clear it so no
            # stale reference lingers (this section has no mw handle — it can
            # only clear the DB-backed session_state, not the live
            # self.mw.site/on_site_changed() wiring owned by SitesSection).
            from core.settings import get_session, set_session
            if (get_session("active_project_id", "") == str(self._current_project_id)
                    and get_session("active_site_id", "") == str(site_id)):
                set_session("active_site_id", "")
                set_session("active_project_id", "")
                QMessageBox.information(
                    self, "Active Site Cleared",
                    "This was the active site for this project — the active "
                    "pairing has been cleared. Re-activate a site from the "
                    "Sites tab (By Project view) if needed."
                )

            self._refresh_sites_table()
            self._sync_open_project()
        except Exception:
            QMessageBox.critical(
                self, "Error",
                "This site could not be removed from the project. Please try again."
            )


# ── New-site dialog ────────────────────────────────────────────────────────────

class _CreateSiteDialog(QDialog):
    """Minimal create-a-site dialog used by the Projects tab so a user can add a
    brand-new site without visiting the Sites tab. On accept, self.new_site
    holds a validated (not-yet-persisted) Site."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.new_site = None
        self.setWindowTitle("Create New Site")
        self.setMinimumWidth(420)
        self.setModal(True)
        self._load_platforms()
        self._build()

    def _load_platforms(self) -> None:
        try:
            from core.database import get_connection
            conn = get_connection()
            self._platforms = conn.execute(
                "SELECT id, name FROM platforms ORDER BY name"
            ).fetchall()
            conn.close()
        except Exception:
            self._platforms = []

    def _build(self) -> None:
        from PyQt6.QtWidgets import (
            QFormLayout, QDoubleSpinBox, QDialogButtonBox,
        )
        from ui.widgets.coord_input import CoordInputWidget

        root = QVBoxLayout(self)
        form = QFormLayout()

        self._name_edit = QLineEdit()
        self._name_edit.setStyleSheet(_INPUT_STYLE)
        form.addRow("Site Name", self._name_edit)

        self._lat_input = CoordInputWidget("lat")
        form.addRow("Latitude", self._lat_input)
        self._lon_input = CoordInputWidget("lon")
        form.addRow("Longitude", self._lon_input)

        self._bbox_spin = QDoubleSpinBox()
        self._bbox_spin.setRange(1.0, 500.0)
        self._bbox_spin.setDecimals(1)
        self._bbox_spin.setValue(25.0)
        self._bbox_spin.setSuffix(" NM")
        self._bbox_spin.setStyleSheet(_INPUT_STYLE)
        form.addRow("Bounding Box Radius", self._bbox_spin)

        self._platform_combo = QComboBox()
        self._platform_combo.setStyleSheet(_INPUT_STYLE)
        self._platform_combo.addItem("(none)", userData=None)
        for p in self._platforms:
            self._platform_combo.addItem(p["name"], userData=p["id"])
        form.addRow("Vessel Platform", self._platform_combo)

        root.addLayout(form)

        hint = QLabel("+Lat = N, −Lat = S, +Lon = E, −Lon = W (WGS-84).")
        hint.setStyleSheet("color:#64748b; font-size:8pt;")
        root.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _on_save(self) -> None:
        from core.models import Site
        if not self._lat_input.is_valid():
            QMessageBox.warning(self, "Invalid Latitude", "Enter a valid latitude.")
            return
        if not self._lon_input.is_valid():
            QMessageBox.warning(self, "Invalid Longitude", "Enter a valid longitude.")
            return
        try:
            self.new_site = Site(
                lat=self._lat_input.value(),
                lon=self._lon_input.value(),
                name=self._name_edit.text().strip(),
                bbox_nm=self._bbox_spin.value(),
                platform_id=self._platform_combo.currentData(),
            )
        except Exception as exc:
            QMessageBox.warning(self, "Validation Error", str(exc))
            return
        self.accept()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _lbl(text: str) -> QLabel:
    l = QLabel(text)
    l.setStyleSheet(_LABEL_STYLE)
    return l


def _input_dialog(parent: QWidget, title: str, label: str) -> tuple[str, bool]:
    from PyQt6.QtWidgets import QInputDialog
    return QInputDialog.getText(parent, title, label)

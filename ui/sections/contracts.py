"""
ui/sections/contracts.py — Platform contract management (Pre-28B-2).

List view of platform_contracts: contract_code, customer, vessel_code, tier,
status, effective dates. Filterable by linked project. Add / Edit / Archive
actions. The edit dialog (ContractEditorDialog) covers every field in the
platform_contracts schema: identity/tier/status/dates, the parent_contract_id
hierarchy selector (subcontract/amendment tiers only), the five nullable
warranted-envelope fields (Step 3), the verification audit trail, external
document links, and notes.

This section is pure CRUD UI — it does not call resolve_warranted_envelope()
or apply_vessel_gate() (modules/m1_site/contracts.py, unmodified here).
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QComboBox, QLineEdit, QDateEdit, QDialog, QDialogButtonBox,
    QFormLayout, QMessageBox, QDoubleSpinBox, QCheckBox, QTextEdit, QFrame,
    QScrollArea,
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QColor

from core.database import get_connection
from ui.styles import apply_table_colors


# ── Styles ─────────────────────────────────────────────────────────────────────

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
_COMBO_STYLE = (
    "QComboBox { background: #1a2233; color: #e2e8f0; border: 1px solid #374151;"
    " border-radius: 3px; padding: 4px 8px; }"
    "QComboBox::drop-down { border: none; width: 18px; }"
    "QComboBox QAbstractItemView { background: #1a2233; color: #e2e8f0;"
    " selection-background-color: #2563eb; }"
)
_INPUT_STYLE = (
    "QLineEdit, QDateEdit, QComboBox { background:#1a2233; color:#e2e8f0;"
    "border:1px solid #374151; border-radius:4px; padding:4px 8px; }"
    "QLineEdit:focus, QDateEdit:focus, QComboBox:focus { border-color:#2563eb; }"
)

_STATUS_COLORS = {
    "active":    ("#14532d", "#86efac"),
    "pending":   ("#422006", "#fde68a"),
    "expired":   ("#374151", "#94a3b8"),
    "cancelled": ("#450a0a", "#fca5a5"),
}
_TIER_OPTIONS   = ["master", "subcontract", "amendment"]
_STATUS_OPTIONS = ["active", "pending", "expired", "cancelled"]

_COLUMNS = ["Contract Code", "Customer", "Vessel Code", "Tier", "Status",
            "Start Date", "End Date"]
_COL_CODE, _COL_CUSTOMER, _COL_VESSEL, _COL_TIER, _COL_STATUS, \
    _COL_START, _COL_END = range(7)


def _item(text, editable: bool = False) -> QTableWidgetItem:
    it = QTableWidgetItem(str(text))
    it.setForeground(Qt.GlobalColor.white)
    if not editable:
        it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return it


def _iso_to_qdate(iso: Optional[str]) -> QDate:
    if iso:
        d = QDate.fromString(iso, "yyyy-MM-dd")
        if d.isValid():
            return d
    return QDate.currentDate()


def _warranted_spin(hi: float, dec: int = 1) -> QDoubleSpinBox:
    """
    Nullable numeric field, matching vehicle_editor.py's established convention
    (Physical/Performance tabs): range starts at 0, which is the special value
    displayed as "Not warranted" — the sentinel for NULL. Read back with
    _spin_val() (value > 0 → real value, else None), never an `or` fallback —
    this is the exact bug class Pre-28B-3 fixed for a different field. Safe
    here because the sentinel (0) and the disabled-state fallback are the same
    value, unlike that bug's mismatched-default case.
    """
    s = QDoubleSpinBox()
    s.setRange(0, hi)
    s.setDecimals(dec)
    s.setSpecialValueText("Not warranted (falls back to parent)")
    return s


def _spin_val(spin: QDoubleSpinBox) -> Optional[float]:
    v = spin.value()
    return v if v > 0 else None


def _section_sep(title: str) -> QWidget:
    """Small uppercase section-divider label, matching the analysis Calculation
    Basis panel's header style used elsewhere in this app."""
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 6, 0, 2)
    lay.setSpacing(2)
    lbl = QLabel(title)
    lbl.setStyleSheet(
        "color:#64748b; font-size:9px; font-weight:bold; letter-spacing:1px;"
    )
    lay.addWidget(lbl)
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("background:#374151; max-height:1px;")
    lay.addWidget(line)
    return box


# ── Contract editor dialog ───────────────────────────────────────────────────

class ContractEditorDialog(QDialog):
    """
    Add / Edit dialog for a platform_contracts row.

    Pass contract_data=None for Add mode; pass a dict (a platform_contracts
    row) for Edit mode. Covers every field in the platform_contracts schema.
    """

    def __init__(self, parent=None, contract_data: Optional[dict] = None):
        super().__init__(parent)
        self._data = contract_data or {}
        self._edit_mode = bool(contract_data)
        self._platforms: list[dict] = []
        self._other_contracts: list[dict] = []

        self.setWindowTitle("Edit Contract" if self._edit_mode else "Add Contract")
        self.setMinimumWidth(460)
        # Cap height to a band that fits common screen resolutions (a 1080p
        # screen has ~1040px of usable vertical space after window chrome/
        # taskbar) rather than sizing to content — the form content scrolls
        # inside a QScrollArea instead of growing the dialog. This is fixed
        # regardless of how many fields this dialog gains in the future.
        self.setMinimumHeight(700)
        self.setMaximumHeight(800)
        self.resize(500, 750)
        self.setModal(True)

        self._load_platforms()
        self._load_other_contracts()
        self._build()
        if self._edit_mode:
            self._populate(self._data)
        else:
            self._on_platform_changed()
            self._on_tier_changed(self._tier_combo.currentText())

    # ── DB helpers ────────────────────────────────────────────────────────────

    def _load_platforms(self) -> None:
        """Only platforms with a vessel_code can back a contract (vessel_code
        is copied from the platform and is NOT NULL on platform_contracts)."""
        try:
            conn = get_connection()
            rows = conn.execute(
                "SELECT id, name, vessel_code FROM platforms "
                "WHERE vessel_code IS NOT NULL ORDER BY name"
            ).fetchall()
            conn.close()
            self._platforms = [dict(r) for r in rows]
        except Exception:
            self._platforms = []

    def _load_other_contracts(self) -> None:
        """Candidates for the parent-contract selector. Excludes the contract
        being edited (a contract can't be its own parent); deeper-cycle
        prevention beyond that is the engine's job — resolve_warranted_envelope()
        already detects and safely breaks cycles."""
        try:
            conn = get_connection()
            rows = conn.execute(
                "SELECT id, contract_code, contract_tier FROM platform_contracts "
                "WHERE id != ? ORDER BY contract_code",
                (self._data.get("id", -1),),
            ).fetchall()
            conn.close()
            self._other_contracts = [dict(r) for r in rows]
        except Exception:
            self._other_contracts = []

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        dlg_layout = QVBoxLayout(self)
        dlg_layout.setContentsMargins(0, 0, 0, 0)
        dlg_layout.setSpacing(0)

        # All form content lives inside a scrolling area — this dialog has
        # grown to cover the full platform_contracts schema (Step 3) and no
        # longer fits a fixed-height window. Save/Cancel are added to
        # dlg_layout directly, below, so they stay pinned and never scroll
        # away with the content.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        root = QVBoxLayout(content)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(10)

        self._platform_combo = QComboBox()
        self._platform_combo.setStyleSheet(_INPUT_STYLE)
        for p in self._platforms:
            self._platform_combo.addItem(
                f"{p['name']} ({p['vessel_code']})", userData=p
            )
        self._platform_combo.currentIndexChanged.connect(self._on_platform_changed)
        form.addRow("Platform (vessel) *", self._platform_combo)

        self._vessel_code_lbl = QLabel("—")
        self._vessel_code_lbl.setStyleSheet("color:#94a3b8;")
        form.addRow("Vessel code", self._vessel_code_lbl)

        self._code_edit = QLineEdit()
        self._code_edit.setStyleSheet(_INPUT_STYLE)
        self._code_edit.setPlaceholderText("CUSTOMER_VESSELCODE_MMDDYYYY_MMDDYYYY")
        form.addRow("Contract code *", self._code_edit)

        self._customer_edit = QLineEdit()
        self._customer_edit.setStyleSheet(_INPUT_STYLE)
        form.addRow("Customer *", self._customer_edit)

        self._tier_combo = QComboBox()
        self._tier_combo.setStyleSheet(_INPUT_STYLE)
        self._tier_combo.addItems(_TIER_OPTIONS)
        form.addRow("Tier", self._tier_combo)

        self._status_combo = QComboBox()
        self._status_combo.setStyleSheet(_INPUT_STYLE)
        self._status_combo.addItems(_STATUS_OPTIONS)
        form.addRow("Status", self._status_combo)

        self._start_edit = QDateEdit()
        self._start_edit.setStyleSheet(_INPUT_STYLE)
        self._start_edit.setCalendarPopup(True)
        self._start_edit.setDate(QDate.currentDate())
        form.addRow("Contract start *", self._start_edit)

        self._end_edit = QDateEdit()
        self._end_edit.setStyleSheet(_INPUT_STYLE)
        self._end_edit.setCalendarPopup(True)
        self._end_edit.setDate(QDate.currentDate().addYears(1))
        form.addRow("Contract end *", self._end_edit)

        root.addLayout(form)

        # ── Hierarchy ─────────────────────────────────────────────────────────
        root.addWidget(_section_sep("HIERARCHY"))
        hform = QFormLayout()
        hform.setSpacing(10)

        self._parent_combo = QComboBox()
        self._parent_combo.setStyleSheet(_INPUT_STYLE)
        self._parent_combo.addItem("— None —", userData=None)
        for c in self._other_contracts:
            self._parent_combo.addItem(
                f"{c['contract_code']} ({c['contract_tier']})", userData=c["id"]
            )
        hform.addRow("Parent contract", self._parent_combo)
        root.addLayout(hform)

        parent_hint = QLabel(
            "Only used for subcontract/amendment tiers — disabled for master. "
            "NULL falls back to the vehicle threshold only (no vessel constraint)."
        )
        parent_hint.setWordWrap(True)
        parent_hint.setStyleSheet("color:#64748b; font-size:8pt; font-style:italic;")
        root.addWidget(parent_hint)

        self._tier_combo.currentTextChanged.connect(self._on_tier_changed)

        # ── Warranted operating envelope ─────────────────────────────────────
        root.addWidget(_section_sep("WARRANTED OPERATING ENVELOPE"))
        wform = QFormLayout()
        wform.setSpacing(10)

        self._w_wind_spin  = _warranted_spin(80, 1)
        self._w_gust_spin  = _warranted_spin(80, 1)
        self._w_hs_spin    = _warranted_spin(20, 2)
        self._w_swh_spin   = _warranted_spin(20, 2)
        self._w_swp_spin   = _warranted_spin(30, 1)
        wform.addRow("Max wind (kts)",       self._w_wind_spin)
        wform.addRow("Max gust (kts)",       self._w_gust_spin)
        wform.addRow("Max sig. wave Hs (m)", self._w_hs_spin)
        wform.addRow("Max swell height (m)", self._w_swh_spin)
        wform.addRow("Max swell period (s)", self._w_swp_spin)
        root.addLayout(wform)

        env_hint = QLabel(
            "Nullable — a parameter left at \"Not warranted\" falls back to the "
            "parent contract (see resolve_warranted_envelope()), or to the "
            "vehicle threshold alone if no contract in the chain warrants it. "
            "Directional tolerances are never warranted at vessel level."
        )
        env_hint.setWordWrap(True)
        env_hint.setStyleSheet("color:#64748b; font-size:8pt; font-style:italic;")
        root.addWidget(env_hint)

        # ── Verification ──────────────────────────────────────────────────────
        root.addWidget(_section_sep("VERIFICATION"))
        self._verified_check = QCheckBox(
            "Warranted values verified against the signed contract document"
        )
        root.addWidget(self._verified_check)

        vform = QFormLayout()
        vform.setSpacing(10)
        self._verified_by_edit = QLineEdit()
        self._verified_by_edit.setStyleSheet(_INPUT_STYLE)
        vform.addRow("Verified by", self._verified_by_edit)

        self._verified_date_edit = QDateEdit()
        self._verified_date_edit.setStyleSheet(_INPUT_STYLE)
        self._verified_date_edit.setCalendarPopup(True)
        self._verified_date_edit.setDate(QDate.currentDate())
        vform.addRow("Verified date", self._verified_date_edit)

        self._source_doc_edit = QLineEdit()
        self._source_doc_edit.setStyleSheet(_INPUT_STYLE)
        self._source_doc_edit.setPlaceholderText("Document name, revision, section")
        vform.addRow("Source document", self._source_doc_edit)
        root.addLayout(vform)

        self._verified_check.toggled.connect(self._on_verified_toggled)
        self._on_verified_toggled(False)

        # ── External document links ──────────────────────────────────────────
        root.addWidget(_section_sep("EXTERNAL DOCUMENT LINKS"))
        dform = QFormLayout()
        dform.setSpacing(10)
        self._doc_url_edit = QLineEdit()
        self._doc_url_edit.setStyleSheet(_INPUT_STYLE)
        self._doc_url_edit.setPlaceholderText("https://…")
        dform.addRow("Document URL", self._doc_url_edit)

        self._doc_unc_edit = QLineEdit()
        self._doc_unc_edit.setStyleSheet(_INPUT_STYLE)
        self._doc_unc_edit.setPlaceholderText(r"\\server\contracts\...")
        dform.addRow("Document UNC path", self._doc_unc_edit)
        root.addLayout(dform)

        doc_row = QHBoxLayout()
        open_doc_btn = QPushButton("Open Document")
        open_doc_btn.setStyleSheet(_BTN_SECONDARY)
        open_doc_btn.clicked.connect(self._on_open_document)
        doc_row.addWidget(open_doc_btn)
        doc_row.addStretch()
        root.addLayout(doc_row)

        doc_hint = QLabel(
            "The application stores links only — it never copies the contract "
            "document. Opening tries the URL first, then falls back to the "
            "UNC path."
        )
        doc_hint.setWordWrap(True)
        doc_hint.setStyleSheet("color:#64748b; font-size:8pt; font-style:italic;")
        root.addWidget(doc_hint)

        # ── Notes ─────────────────────────────────────────────────────────────
        root.addWidget(_section_sep("NOTES"))
        self._notes_edit = QTextEdit()
        self._notes_edit.setStyleSheet(_INPUT_STYLE)
        self._notes_edit.setFixedHeight(60)
        root.addWidget(self._notes_edit)

        scroll.setWidget(content)
        dlg_layout.addWidget(scroll, 1)

        # Pinned outside the scroll area — Save/Cancel never scroll away.
        btn_bar = QWidget()
        btn_bar.setStyleSheet("background: #151c27; border-top: 1px solid #374151;")
        btn_bar_layout = QVBoxLayout(btn_bar)
        btn_bar_layout.setContentsMargins(16, 8, 16, 8)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        btn_bar_layout.addWidget(buttons)
        dlg_layout.addWidget(btn_bar)

    def _on_platform_changed(self) -> None:
        p = self._platform_combo.currentData()
        self._vessel_code_lbl.setText(p["vessel_code"] if p else "—")

    def _on_tier_changed(self, tier: str) -> None:
        self._parent_combo.setEnabled(tier != "master")
        if tier == "master":
            self._parent_combo.setCurrentIndex(0)   # force "— None —"

    def _on_verified_toggled(self, checked: bool) -> None:
        self._verified_by_edit.setEnabled(checked)
        self._verified_date_edit.setEnabled(checked)
        self._source_doc_edit.setEnabled(checked)

    def _on_open_document(self) -> None:
        url = self._doc_url_edit.text().strip() or None
        unc = self._doc_unc_edit.text().strip() or None
        if not url and not unc:
            QMessageBox.information(self, "No Document Link",
                                    "Enter a document URL or UNC path first.")
            return
        from core.file_attachments import open_external_document, DocumentNotReachableError
        try:
            open_external_document(url, unc)
        except DocumentNotReachableError as exc:
            QMessageBox.warning(self, "Could Not Open Document", str(exc))

    def _populate(self, d: dict) -> None:
        for i, p in enumerate(self._platforms):
            if p["id"] == d.get("platform_id"):
                self._platform_combo.setCurrentIndex(i)
                break
        self._on_platform_changed()

        self._code_edit.setText(d.get("contract_code", ""))
        self._customer_edit.setText(d.get("customer_name", ""))
        if d.get("contract_tier") in _TIER_OPTIONS:
            self._tier_combo.setCurrentText(d["contract_tier"])
        if d.get("status") in _STATUS_OPTIONS:
            self._status_combo.setCurrentText(d["status"])
        self._start_edit.setDate(_iso_to_qdate(d.get("contract_start")))
        self._end_edit.setDate(_iso_to_qdate(d.get("contract_end")))

        parent_idx = self._parent_combo.findData(d.get("parent_contract_id"))
        self._parent_combo.setCurrentIndex(parent_idx if parent_idx >= 0 else 0)
        self._on_tier_changed(self._tier_combo.currentText())

        self._w_wind_spin.setValue(d.get("warranted_max_wind_kts") or 0)
        self._w_gust_spin.setValue(d.get("warranted_max_gust_kts") or 0)
        self._w_hs_spin.setValue(d.get("warranted_max_hs_m") or 0)
        self._w_swh_spin.setValue(d.get("warranted_max_swell_ht_m") or 0)
        self._w_swp_spin.setValue(d.get("warranted_max_swell_period_s") or 0)

        verified = bool(d.get("warranted_verified"))
        self._verified_check.setChecked(verified)
        self._verified_by_edit.setText(d.get("warranted_verified_by") or "")
        self._verified_date_edit.setDate(
            _iso_to_qdate(d.get("warranted_verified_date"))
        )
        self._source_doc_edit.setText(d.get("warranted_source_doc") or "")
        self._on_verified_toggled(verified)

        self._doc_url_edit.setText(d.get("document_url") or "")
        self._doc_unc_edit.setText(d.get("document_unc_path") or "")
        self._notes_edit.setPlainText(d.get("notes") or "")

    # ── Save ──────────────────────────────────────────────────────────────────

    def _on_save(self) -> None:
        platform = self._platform_combo.currentData()
        if platform is None:
            QMessageBox.warning(
                self, "Validation",
                "No platform available. A platform must have a vessel_code "
                "assigned before it can be linked to a contract."
            )
            return

        code = self._code_edit.text().strip().upper()
        customer = self._customer_edit.text().strip()
        if not code or not customer:
            QMessageBox.warning(self, "Validation",
                                "Contract code and customer are required.")
            return

        from config import validate_contract_code
        if not validate_contract_code(code):
            QMessageBox.warning(
                self, "Validation",
                "Contract code must match CUSTOMER_VESSELCODE_MMDDYYYY_MMDDYYYY "
                "(e.g. LM1_0100_10012026_09302027)."
            )
            return

        start = self._start_edit.date()
        end = self._end_edit.date()
        if end <= start:
            QMessageBox.warning(self, "Validation",
                                "Contract end date must be after the start date.")
            return

        tier = self._tier_combo.currentText()
        parent_id = self._parent_combo.currentData() if tier != "master" else None
        if parent_id == self._data.get("id"):
            # Defensive: _load_other_contracts already excludes self from the
            # combo, so this should be unreachable, but never persist a
            # contract as its own parent.
            parent_id = None

        verified = self._verified_check.isChecked()

        data = dict(
            platform_id=platform["id"],
            vessel_code=platform["vessel_code"],
            contract_code=code,
            customer_name=customer,
            contract_tier=tier,
            parent_contract_id=parent_id,
            status=self._status_combo.currentText(),
            contract_start=start.toString("yyyy-MM-dd"),
            contract_end=end.toString("yyyy-MM-dd"),
            warranted_max_wind_kts=_spin_val(self._w_wind_spin),
            warranted_max_gust_kts=_spin_val(self._w_gust_spin),
            warranted_max_hs_m=_spin_val(self._w_hs_spin),
            warranted_max_swell_ht_m=_spin_val(self._w_swh_spin),
            warranted_max_swell_period_s=_spin_val(self._w_swp_spin),
            warranted_verified=int(verified),
            # Verified-by/date/source only persist when the verified checkbox
            # is checked, avoiding an inconsistent "verified by nobody" state.
            warranted_verified_by=(
                self._verified_by_edit.text().strip() or None if verified else None
            ),
            warranted_verified_date=(
                self._verified_date_edit.date().toString("yyyy-MM-dd") if verified else None
            ),
            warranted_source_doc=(
                self._source_doc_edit.text().strip() or None if verified else None
            ),
            document_url=self._doc_url_edit.text().strip() or None,
            document_unc_path=self._doc_unc_edit.text().strip() or None,
            notes=self._notes_edit.toPlainText().strip() or None,
        )

        conn = get_connection()
        try:
            existing = conn.execute(
                "SELECT id FROM platform_contracts WHERE contract_code=? AND id != ?",
                (code, self._data.get("id", -1)),
            ).fetchone()
            if existing:
                QMessageBox.warning(
                    self, "Duplicate Contract Code",
                    f"A contract with code '{code}' already exists."
                )
                return

            if self._edit_mode:
                sets = ", ".join(f"{k}=:{k}" for k in data)
                data["_id"] = self._data["id"]
                conn.execute(
                    f"UPDATE platform_contracts SET {sets}, "
                    f"updated_at=CURRENT_TIMESTAMP WHERE id=:_id", data
                )
            else:
                cols = ", ".join(data.keys())
                vals = ", ".join(f":{k}" for k in data)
                conn.execute(
                    f"INSERT INTO platform_contracts ({cols}) VALUES ({vals})", data
                )
            conn.commit()
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", str(exc))
            return
        finally:
            conn.close()

        self.accept()


# ── Section ────────────────────────────────────────────────────────────────────

class ContractsSection(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._rows: list[dict] = []
        self._build()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._reload_project_filter()
        self._refresh_table()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        title = QLabel("Platform Contracts")
        title.setObjectName("sectionTitle")
        root.addWidget(title)

        subtitle = QLabel(
            "Manage warranted-operating-envelope contracts per vessel. "
            "Link a contract to a project from the Projects tab to enable "
            "the vessel pre-check gate for that project."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #94a3b8;")
        root.addWidget(subtitle)

        # Filter row
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)

        filter_row.addWidget(QLabel("Project:"))
        self._proj_filter_combo = QComboBox()
        self._proj_filter_combo.setMinimumWidth(220)
        self._proj_filter_combo.setStyleSheet(_COMBO_STYLE)
        self._proj_filter_combo.currentIndexChanged.connect(
            lambda _: self._refresh_table()
        )
        filter_row.addWidget(self._proj_filter_combo)

        filter_row.addWidget(QLabel("Show:"))
        self._show_filter_combo = QComboBox()
        self._show_filter_combo.setStyleSheet(_COMBO_STYLE)
        self._show_filter_combo.addItem("Active",   userData="active")
        self._show_filter_combo.addItem("Archived", userData="archived")
        self._show_filter_combo.addItem("All",      userData=None)
        self._show_filter_combo.currentIndexChanged.connect(
            lambda _: self._refresh_table()
        )
        filter_row.addWidget(self._show_filter_combo)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setStyleSheet(_BTN_SECONDARY)
        refresh_btn.clicked.connect(self._on_refresh)
        filter_row.addWidget(refresh_btn)
        filter_row.addStretch()
        root.addLayout(filter_row)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self._add_btn = QPushButton("+ Add Contract")
        self._add_btn.setStyleSheet(_BTN_PRIMARY)
        self._add_btn.clicked.connect(self._on_add)
        toolbar.addWidget(self._add_btn)

        self._edit_btn = QPushButton("Edit Contract")
        self._edit_btn.setStyleSheet(_BTN_SECONDARY)
        self._edit_btn.clicked.connect(self._on_edit)
        toolbar.addWidget(self._edit_btn)

        self._archive_btn = QPushButton("Archive")
        self._archive_btn.setStyleSheet(_BTN_SECONDARY)
        self._archive_btn.clicked.connect(self._on_toggle_archive)
        toolbar.addWidget(self._archive_btn)

        toolbar.addStretch()
        root.addLayout(toolbar)

        # Table
        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_CUSTOMER, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.doubleClicked.connect(self._on_edit)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        apply_table_colors(self._table)
        root.addWidget(self._table, 1)

        self._on_selection_changed()

    # ── Data loading ──────────────────────────────────────────────────────────

    def _reload_project_filter(self) -> None:
        try:
            conn = get_connection()
            rows = conn.execute(
                "SELECT id, name FROM projects ORDER BY name"
            ).fetchall()
            conn.close()
            projects = [dict(r) for r in rows]
        except Exception:
            projects = []

        prev = self._proj_filter_combo.currentData()
        self._proj_filter_combo.blockSignals(True)
        self._proj_filter_combo.clear()
        self._proj_filter_combo.addItem("All Contracts", userData=None)
        self._proj_filter_combo.addItem("Unlinked (no project)", userData="UNLINKED")
        for p in projects:
            self._proj_filter_combo.addItem(p["name"], userData=p["id"])
        if prev is not None:
            idx = self._proj_filter_combo.findData(prev)
            self._proj_filter_combo.setCurrentIndex(idx if idx >= 0 else 0)
        else:
            self._proj_filter_combo.setCurrentIndex(0)
        self._proj_filter_combo.blockSignals(False)

    def _refresh_table(self) -> None:
        proj_filter = self._proj_filter_combo.currentData()
        show_filter = self._show_filter_combo.currentData()

        conditions: list[str] = []
        params: list = []

        if show_filter == "active":
            conditions.append("c.is_archived = 0")
        elif show_filter == "archived":
            conditions.append("c.is_archived = 1")

        if proj_filter == "UNLINKED":
            conditions.append(
                "NOT EXISTS (SELECT 1 FROM projects p "
                "WHERE p.platform_contract_id = c.id)"
            )
        elif isinstance(proj_filter, int):
            conditions.append(
                "EXISTS (SELECT 1 FROM projects p "
                "WHERE p.platform_contract_id = c.id AND p.id = ?)"
            )
            params.append(proj_filter)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        try:
            conn = get_connection()
            rows = conn.execute(
                f"SELECT * FROM platform_contracts c {where} "
                f"ORDER BY c.contract_code", params
            ).fetchall()
            conn.close()
            self._rows = [dict(r) for r in rows]
        except Exception:
            self._rows = []

        self._table.setRowCount(len(self._rows))
        for row_idx, r in enumerate(self._rows):
            status = r.get("status", "active")
            bg, fg = _STATUS_COLORS.get(status, ("#374151", "#94a3b8"))

            cells = [
                r.get("contract_code", ""),
                r.get("customer_name", ""),
                r.get("vessel_code", ""),
                (r.get("contract_tier") or "").title(),
                status.title(),
                r.get("contract_start", ""),
                r.get("contract_end", ""),
            ]
            for col, text in enumerate(cells):
                it = _item(text)
                if col == _COL_STATUS:
                    it.setBackground(QColor(bg))
                    it.setForeground(QColor(fg))
                else:
                    it.setForeground(QColor("#f1f5f9"))
                self._table.setItem(row_idx, col, it)

        self._on_selection_changed()

    # ── Actions ───────────────────────────────────────────────────────────────

    def _on_refresh(self) -> None:
        self._reload_project_filter()
        self._refresh_table()

    def _selected_row_data(self) -> Optional[dict]:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._rows):
            return None
        return self._rows[row]

    def _on_selection_changed(self) -> None:
        data = self._selected_row_data()
        has_sel = data is not None
        self._edit_btn.setEnabled(has_sel)
        self._archive_btn.setEnabled(has_sel)
        if has_sel:
            self._archive_btn.setText(
                "Unarchive" if data.get("is_archived") else "Archive"
            )
        else:
            self._archive_btn.setText("Archive")

    def _on_add(self) -> None:
        dlg = ContractEditorDialog(self)
        if dlg.exec():
            self._refresh_table()

    def _on_edit(self) -> None:
        data = self._selected_row_data()
        if not data:
            QMessageBox.information(self, "No selection", "Select a contract to edit.")
            return
        dlg = ContractEditorDialog(self, contract_data=data)
        if dlg.exec():
            self._refresh_table()

    def _on_toggle_archive(self) -> None:
        data = self._selected_row_data()
        if not data:
            QMessageBox.information(self, "No selection", "Select a contract first.")
            return
        new_state = 0 if data.get("is_archived") else 1
        try:
            conn = get_connection()
            conn.execute(
                "UPDATE platform_contracts SET is_archived=? WHERE id=?",
                (new_state, data["id"]),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            QMessageBox.warning(self, "Error", str(exc))
            return
        self._refresh_table()

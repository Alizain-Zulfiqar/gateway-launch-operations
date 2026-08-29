"""
tests/test_contracts_and_pairing.py — Pre-28B-2 Steps 2/3/6 (Contracts CRUD +
project linking) and Steps 5's consumer (AnalysisTab._resolve_active_platform_
contract → compute_annual_profile(platform_contract=)).

Drives the real widgets (ContractEditorDialog, ContractsSection,
ProjectsSection, AnalysisTab) rather than raw SQL wherever the instruction
calls for "the same path the UI uses" — raw SQL is used only for the parts of
each fixture explicitly described as independent/pre-existing setup.

Requires PyQt6; runs under the venv interpreter (offscreen platform). Skips
cleanly under the system interpreter, matching every other PyQt-dependent test
in this suite (test_pre28b3.py, test_pairing_activation.py, etc.).
"""
from __future__ import annotations

import os

import pytest
import core.database as db_mod

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

# A single QApplication for the whole test session; QMessageBox methods are
# stubbed to no-ops so a validation warning/info/critical popup can never
# block headless execution (QMessageBox.exec() blocks for a real click even
# under the offscreen platform).
_app = QApplication.instance() or QApplication([])
QMessageBox.warning = staticmethod(lambda *a, **k: None)
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.critical = staticmethod(lambda *a, **k: None)


@pytest.fixture()
def db_file(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture(autouse=True)
def _patch_db(db_file, monkeypatch):
    monkeypatch.setattr(db_mod, "DB_PATH", str(db_file))
    db_mod.init_db()


def _seed_platform():
    from core.database import get_connection
    conn = get_connection()
    conn.execute(
        "INSERT INTO platforms (name, hull_type, hull_motion_factor, vessel_code) "
        "VALUES ('Gateway S','semisub',0.78,'0100')"
    )
    conn.commit()
    conn.close()


def _add_contract_via_dialog(code="LM1_0100_10012026_09302027",
                              customer="Lockheed Martin", warranted_hs=None):
    """Create a contract through ContractEditorDialog._on_save() — the exact
    path the Add button in ContractsSection uses. Returns the new id."""
    from ui.sections.contracts import ContractEditorDialog
    from core.database import get_connection

    dlg = ContractEditorDialog(None)
    dlg._platform_combo.setCurrentIndex(0)
    dlg._code_edit.setText(code)
    dlg._customer_edit.setText(customer)
    if warranted_hs is not None:
        dlg._w_hs_spin.setValue(warranted_hs)
    dlg._on_save()
    assert dlg.result() == dlg.DialogCode.Accepted, "contract save should succeed"

    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM platform_contracts WHERE contract_code=?", (code,)
    ).fetchone()
    conn.close()
    return row["id"]


def _add_project(name="ProjA", status="planning"):
    """Plain INSERT — the same statement ProjectsSection._on_new_project()
    issues once past its (modal, name-prompting) QInputDialog step."""
    from core.database import get_connection
    conn = get_connection()
    conn.execute("INSERT INTO projects (name, status) VALUES (?, ?)", (name, status))
    conn.commit()
    row = conn.execute("SELECT id FROM projects WHERE name=?", (name,)).fetchone()
    conn.close()
    return row["id"]


def _mw_for(project_id, site_id=1):
    """Minimal main-window stand-in for AnalysisTab, matching the shape used
    throughout this session's Step 5/6 smoke tests."""
    from core.models import Site, Vehicle, Platform

    class MW:
        site = Site(lat=28.5, lon=-80.6, name="CC")
        site.id = site_id
        vehicle = Vehicle(
            name="V", vehicle_class="slv_orb", recovery_mode="expendable",
            max_wind_kts=18, max_gust_kts=25, max_hs_m=1.5,
            max_swell_ht_m=2.0, max_swell_period_s=12,
        )
        platform = Platform("Gateway X", "semisub", 0.78)
        active_project_id = project_id

        def status(self, msg):
            pass

    return MW()


# ── test_contract_crud ────────────────────────────────────────────────────────

def test_contract_crud():
    from ui.sections.contracts import ContractEditorDialog, ContractsSection
    from modules.m1_site.contracts import get_contract
    from core.database import get_connection

    _seed_platform()

    # Add — same insert path ContractEditorDialog uses.
    contract_id = _add_contract_via_dialog()
    contract = get_contract(contract_id)
    assert contract is not None
    assert contract.contract_code == "LM1_0100_10012026_09302027"
    assert contract.customer_name == "Lockheed Martin"
    assert contract.is_archived is False

    # Edit — one field, via the dialog's real edit path (Edit mode).
    edit_dlg = ContractEditorDialog(None, contract_data=dict(contract.__dict__))
    assert edit_dlg._code_edit.text() == "LM1_0100_10012026_09302027"
    edit_dlg._customer_edit.setText("Lockheed Martin Space")
    edit_dlg._on_save()
    assert edit_dlg.result() == edit_dlg.DialogCode.Accepted

    contract2 = get_contract(contract_id)
    assert contract2.customer_name == "Lockheed Martin Space"

    # Archive — same toggle path ContractsSection's Archive button uses.
    section = ContractsSection(None)
    section._refresh_table()   # default filter is "Active"
    assert len(section._rows) == 1
    section._table.selectRow(0)
    assert section._archive_btn.text() == "Archive"
    section._on_toggle_archive()

    # Drops out of the default (non-archived) list query.
    section._refresh_table()
    assert len(section._rows) == 0

    # Remains reachable via the Archived filter.
    section._show_filter_combo.setCurrentIndex(
        section._show_filter_combo.findData("archived")
    )
    section._refresh_table()
    assert len(section._rows) == 1
    assert section._rows[0]["contract_code"] == "LM1_0100_10012026_09302027"
    assert section._rows[0]["is_archived"] == 1

    # Remains reachable via the All filter.
    section._show_filter_combo.setCurrentIndex(section._show_filter_combo.findData(None))
    section._refresh_table()
    assert len(section._rows) == 1


# ── test_contract_linked_to_project ──────────────────────────────────────────

def test_contract_linked_to_project():
    from ui.sections.projects import ProjectsSection
    from core.database import get_connection

    _seed_platform()
    contract_id = _add_contract_via_dialog()      # contract, independently
    project_id = _add_project("ProjA", "planning")  # project, independently

    # Link — via the exact same UI path Step 6 added: the Linked Contract
    # combo + _on_save_project()'s UPDATE projects SET platform_contract_id.
    section = ProjectsSection()
    section._select_project(project_id)
    assert section._contract_combo.currentData() is None   # unlinked initially

    idx = section._contract_combo.findData(contract_id)
    assert idx >= 0, "the newly-created contract must appear in the combo"
    section._contract_combo.setCurrentIndex(idx)
    section._on_save_project()

    # Round-trips on reload.
    conn = get_connection()
    row = conn.execute(
        "SELECT platform_contract_id FROM projects WHERE id=?", (project_id,)
    ).fetchone()
    conn.close()
    assert row["platform_contract_id"] == contract_id

    section2 = ProjectsSection()
    section2._select_project(project_id)
    assert section2._contract_combo.currentData() == contract_id

    # Unlink — FK clears to NULL, not a stale reference.
    section2._contract_combo.setCurrentIndex(0)   # "— No linked contract —"
    section2._on_save_project()

    conn = get_connection()
    row2 = conn.execute(
        "SELECT platform_contract_id FROM projects WHERE id=?", (project_id,)
    ).fetchone()
    conn.close()
    assert row2["platform_contract_id"] is None


# ── test_active_pairing_with_no_contract_still_produces_no_contract_linked ──

def test_active_pairing_with_no_contract_still_produces_no_contract_linked():
    from ui.analysis_tab import AnalysisTab

    project_id = _add_project("NoContractProj", "planning")
    # No platform_contract_id set — stays NULL.

    tab = AnalysisTab(_mw_for(project_id))

    result = tab._resolve_active_platform_contract()
    assert result is None

    # The existing "No contract linked" path fires — not a crash, not a
    # default/fallback contract.
    tab._run()
    assert "No contract linked" in tab.vessel_label.text()
    any_month = next(iter(tab._profile.values()))
    assert any_month.vessel_verdict is None
    assert any_month.vessel_contract_code is None


# ── test_active_pairing_with_linked_contract_passes_platform_contract ───────

def test_active_pairing_with_linked_contract_passes_platform_contract():
    from unittest.mock import patch
    from ui.sections.projects import ProjectsSection
    from ui.analysis_tab import AnalysisTab
    import modules.m3_probability.engine as engine_mod

    _seed_platform()
    contract_id = _add_contract_via_dialog(warranted_hs=1.0)   # built via the
    project_id = _add_project("LinkedProj", "planning")        # app's own paths

    proj_section = ProjectsSection()
    proj_section._select_project(project_id)
    idx = proj_section._contract_combo.findData(contract_id)
    proj_section._contract_combo.setCurrentIndex(idx)
    proj_section._on_save_project()

    tab = AnalysisTab(_mw_for(project_id))

    resolved = tab._resolve_active_platform_contract()
    assert resolved is not None
    assert resolved.contract_code == "LM1_0100_10012026_09302027"
    assert resolved.warranted_max_hs_m == 1.0

    # Confirm compute_annual_profile is actually invoked with
    # platform_contract= the resolved contract (not just that the resolver
    # works in isolation).
    real_fn = engine_mod.compute_annual_profile

    def spy(*args, **kwargs):
        return real_fn(*args, **kwargs)

    with patch.object(engine_mod, "compute_annual_profile", side_effect=spy) as mock_fn:
        tab._run()

    assert mock_fn.called
    _, call_kwargs = mock_fn.call_args
    passed_contract = call_kwargs.get("platform_contract")
    assert passed_contract is not None
    assert passed_contract.contract_code == "LM1_0100_10012026_09302027"

    # End-to-end (matching the informal Step 5 verification): the resulting
    # profile actually carries a vessel verdict, and the UI reflects it.
    any_month = next(iter(tab._profile.values()))
    assert any_month.vessel_verdict in ("GO", "MARGINAL", "NO-GO")
    assert any_month.vessel_contract_code == "LM1_0100_10012026_09302027"
    assert "No contract linked" not in tab.vessel_label.text()

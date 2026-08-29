"""
tests/test_pairing_activation.py — site+project activation pairing.

Covers the By Project view's Activate/Deactivate guard logic
(`_activation_guard_reasons` — a pure function, no Qt/DB) and the session-
state behaviour of Activate/Deactivate and the app-startup clear. The latter
two require PyQt6 and run under the venv interpreter (see test_pre28b3.py for
the same importorskip/offscreen precedent used here).
"""
from __future__ import annotations

import os

import pytest
import core.database as db_mod


# ── Pure guard-function tests (no Qt, no DB) ─────────────────────────────────

def test_activate_blocked_when_rejected():
    from ui.sections.sites import _activation_guard_reasons
    reasons = _activation_guard_reasons("planning", "rejected")
    assert reasons, "rejected candidate status must block activation"
    assert any("rejected" in r for r in reasons)

    reasons = _activation_guard_reasons("pending", "rejected")
    assert reasons, "rejected candidate status must block activation regardless of project status"


def test_activate_blocked_when_project_completed_or_cancelled():
    from ui.sections.sites import _activation_guard_reasons

    reasons = _activation_guard_reasons("completed", "candidate")
    assert reasons, "completed project must block activation"
    assert any("completed" in r for r in reasons)

    reasons = _activation_guard_reasons("cancelled", "approved")
    assert reasons, "cancelled project must block activation"
    assert any("cancelled" in r for r in reasons)


def test_activate_allowed_when_planning_or_pending_and_not_rejected():
    from ui.sections.sites import _activation_guard_reasons

    for project_status in ("planning", "pending"):
        for candidate_status in ("candidate", "approved", "final"):
            reasons = _activation_guard_reasons(project_status, candidate_status)
            assert reasons == [], (
                f"expected activation allowed for project={project_status!r} "
                f"candidate={candidate_status!r}, got reasons={reasons}"
            )


# ── Session-state fixtures (real temp DB, no Qt) ─────────────────────────────

@pytest.fixture()
def db_file(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture(autouse=True)
def _patch_db(db_file, monkeypatch):
    monkeypatch.setattr(db_mod, "DB_PATH", str(db_file))
    db_mod.init_db()


# ── Deactivate — requires PyQt6 (drives the real SitesSection handler) ───────

def test_deactivate_clears_both_keys():
    """_on_deactivate_site() clears both session keys, self.mw.site, and
    self.mw.active_project_id — driven through the real handler, not a mock."""
    pytest.importorskip("PyQt6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    from core.settings import get_session, set_session
    from ui.sections.sites import SitesSection

    app = QApplication.instance() or QApplication([])

    set_session("active_site_id", "42")
    set_session("active_project_id", "7")

    class MW:
        site = "not-none-sentinel"   # SitesSection._build reads mw.vehicles etc.
        vehicle = None
        vehicles = []
        platform = None
        active_project_id = 7
        def on_site_changed(self):
            pass

    mw = MW()
    tab = SitesSection(mw)
    tab._on_deactivate_site()

    assert get_session("active_site_id") == ""
    assert get_session("active_project_id") == ""
    assert mw.site is None
    assert mw.active_project_id is None
    assert tab._active_status_lbl.text() == "No active site."
    assert tab._deactivate_btn.isHidden()


# ── Startup clear — requires PyQt6 (constructs the real GatewayMainWindow) ───

def test_startup_clears_both_keys():
    """GatewayMainWindow.__init__ clears active_site_id/active_project_id on
    every launch, matching the selected_ndbc_stations precedent."""
    pytest.importorskip("PyQt6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    from core.settings import get_session, set_session
    from ui.main_window import GatewayMainWindow

    # Simulate stale state left over from a prior session.
    set_session("active_site_id", "99")
    set_session("active_project_id", "3")

    app = QApplication.instance() or QApplication([])
    win = GatewayMainWindow()

    assert get_session("active_site_id") == ""
    assert get_session("active_project_id") == ""
    assert win.active_project_id is None
    assert win.site is None


# ── All Sites mode has no Activate control ───────────────────────────────────

def test_all_sites_view_has_no_activate_control():
    """All Sites mode must not offer any way to change the active site —
    Activate exists only in the By Project view (confirmed design decision).
    The status column there is read-only, reflecting whatever is active via
    the By Project pairing mechanism."""
    pytest.importorskip("PyQt6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication, QPushButton
    from ui.sections.sites import SitesSection

    app = QApplication.instance() or QApplication([])

    class MW:
        site = None
        vehicle = None
        vehicles = []
        platform = None
        active_project_id = None
        def on_site_changed(self):
            pass

    tab = SitesSection(MW())

    # By Project is the default selected mode (reinforces locked rule: activation only in By Project).
    assert tab._by_project_btn.isChecked()

    # No leftover attributes for the removed control.
    assert not hasattr(tab, "_activate_btn")
    assert not hasattr(tab, "_set_active")
    assert not hasattr(tab, "_activate_row")

    # No button anywhere in the All Sites widget subtree offers to change the
    # active site (checked by label text, so a rename can't silently defeat
    # this test).
    labels = [b.text() for b in tab._all_sites_widget.findChildren(QPushButton)]
    assert not any("Activate" in t or "Active Site" in t for t in labels), labels

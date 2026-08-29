"""
ui/widgets/project_site_selector.py — site picker for project-scoped tabs.

When the open project has one site, shows a read-only name label.
When it has multiple sites, shows a combo box populated from
main_window.open_project_sites.
"""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox

from core.models import Site


def refresh_project_site_selector(
    mw,
    combo: QComboBox,
    name_label: QLabel,
    *,
    prefer_site: Optional[Site] = None,
) -> Optional[Site]:
    """Rebuild combo from open project sites; return the currently selected site."""
    sites = getattr(mw, "open_project_sites", []) or []
    active = prefer_site or getattr(mw, "site", None)

    combo.blockSignals(True)
    combo.clear()
    for s in sites:
        label = f"{s.name or 'Unnamed'}  ({s.coord_str})"
        combo.addItem(label, s.id)

    target = 0
    active_id = getattr(active, "id", None)
    if active_id is not None:
        for i, s in enumerate(sites):
            if s.id == active_id:
                target = i
                break
    if sites:
        combo.setCurrentIndex(target)
    combo.blockSignals(False)

    multi = len(sites) > 1
    combo.setVisible(multi)
    name_label.setVisible(not multi)

    if not sites:
        name_label.setText("No project sites — open a project and add sites")
        name_label.setStyleSheet("color: #fde68a; font-weight: 600;")
        return None

    selected = sites[target] if sites else None
    if not multi and selected:
        name_label.setText(selected.name or selected.coord_str)
        name_label.setStyleSheet("color: #86efac; font-weight: 600;")
    return selected


def selected_project_site(mw, combo: QComboBox) -> Optional[Site]:
    """Return the Site object for the combo's current row."""
    sites = getattr(mw, "open_project_sites", []) or []
    idx = combo.currentIndex()
    if idx < 0 or idx >= len(sites):
        return getattr(mw, "site", None)
    return sites[idx]


def wire_project_site_combo(
    mw,
    combo: QComboBox,
    on_changed: Callable[[], None],
) -> None:
    combo.currentIndexChanged.connect(lambda _idx: on_changed())

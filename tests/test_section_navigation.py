"""tests/test_section_navigation.py — Sidebar ↔ QStackedWidget wiring."""
from __future__ import annotations


def test_all_sections_have_stack_index():
    """Every nav section key has an entry in _SECTION_INDEX, indices are contiguous."""
    from ui.main_window import _SECTION_INDEX

    expected_keys = {
        "projects", "quick_analysis",
        "sites", "analysis", "vehicles", "launchers", "comparison",
        "ndbc", "forecast", "ports", "vessels", "contracts",
        "reports", "history", "settings",
    }
    assert set(_SECTION_INDEX.keys()) == expected_keys
    # Indices must form a contiguous 0..N-1 range (no gaps, no duplicates)
    assert set(_SECTION_INDEX.values()) == set(range(len(_SECTION_INDEX)))


def test_forecast_section_importable():
    """ForecastSection can be imported without PyQt6 display (no QApplication needed)."""
    import importlib
    mod = importlib.util.find_spec("ui.sections.forecast")
    assert mod is not None, "ui.sections.forecast module not found"


def _sidebar_nav_keys() -> list[str]:
    """Gather all string keys declared in GatewaySidebar's _HOME_NAV and
    _PROJECT_NAV lists by parsing the source (avoids importing PyQt6)."""
    import importlib, ast, pathlib
    spec = importlib.util.find_spec("ui.sidebar")
    assert spec is not None
    src = pathlib.Path(spec.origin).read_text(encoding="utf-8")
    tree = ast.parse(src)
    keys: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "GatewaySidebar":
            for item in ast.walk(node):
                if isinstance(item, ast.Assign):
                    for t in item.targets:
                        if isinstance(t, ast.Name) and t.id in ("_HOME_NAV", "_PROJECT_NAV"):
                            for elt in ast.walk(item.value):
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    keys.append(elt.value)
    return keys


def test_sidebar_nav_items_contain_projects_and_quick_analysis():
    """The home nav must expose 'projects' and the new 'quick_analysis' section."""
    keys = _sidebar_nav_keys()
    assert "projects" in keys, f"'projects' not found in sidebar nav keys: {keys}"
    assert "quick_analysis" in keys, f"'quick_analysis' not found in sidebar nav keys: {keys}"


def test_sidebar_nav_items_contain_forecast():
    """The project nav must include a 'forecast' key."""
    keys = _sidebar_nav_keys()
    assert "forecast" in keys, f"'forecast' not found in sidebar nav keys: {keys}"

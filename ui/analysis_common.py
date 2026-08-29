"""
ui/analysis_common.py — Shared analysis rendering helpers.

Pure(ish) helpers used by both the project Analysis tab (ui/analysis_tab.py)
and the ephemeral Quick Analysis tab (ui/sections/quick_analysis.py) so the
12-month results table, summary strip, data-source badges, and Calculation
Basis panel are rendered identically from a single source of truth.

All functions take a `profile` (dict[int, AnalysisResult]) or a single
`AnalysisResult` and write into caller-supplied widgets or return HTML — they
hold no state of their own.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTableWidgetItem
from PyQt6.QtGui import QColor

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

_MAGNITUDE_PARAMS = ["ws", "wg", "sh", "swh", "swp"]
_DIRECTION_PARAMS = ["wdV", "sdV", "swdV"]

_PARAM_FULL = {
    "ws": "Wind speed", "wg": "Wind gust", "sh": "Sea wave height",
    "swh": "Swell height", "swp": "Swell period",
    "wdV": "Wind direction", "sdV": "Sea direction", "swdV": "Swell direction",
}

# Dark-theme verdict colors
_GO_BG       = QColor('#14532d')
_GO_FG       = QColor('#86efac')
_MARGINAL_BG = QColor('#422006')
_MARGINAL_FG = QColor('#fde68a')
_NOGO_BG     = QColor('#450a0a')
_NOGO_FG     = QColor('#fca5a5')
_DEFAULT_FG  = QColor('#f1f5f9')

_BG_MAP = {"GO": _GO_BG, "MARGINAL": _MARGINAL_BG, "NO-GO": _NOGO_BG}
_FG_MAP = {"GO": _GO_FG, "MARGINAL": _MARGINAL_FG, "NO-GO": _NOGO_FG}
_VERDICT_LABEL = {"GO": "  GO", "MARGINAL": "  MARGINAL", "NO-GO": "  NO-GO"}


def unit_for(param: str) -> str:
    return {
        "ws": "kts", "wg": "kts", "sh": "m", "swh": "m", "swp": "s",
        "wdV": "°", "sdV": "°", "swdV": "°",
    }.get(param, "")


def clear_profile_table(table) -> None:
    for row in range(12):
        for col in range(4):
            item = QTableWidgetItem("")
            item.setForeground(_DEFAULT_FG)
            table.setItem(row, col, item)


def populate_profile_table(table, profile: dict) -> None:
    """Fill a 12×4 table (Month / Probability / Verdict / Limiting Parameter)."""
    for row, (month, result) in enumerate(profile.items()):
        data = [
            MONTHS[month - 1],
            f"{result.pct}%",
            _VERDICT_LABEL[result.verdict],
            result.limiting_param,
        ]
        verdict = result.verdict
        for col, text in enumerate(data):
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if col == 2:
                item.setBackground(_BG_MAP[verdict])
                item.setForeground(_FG_MAP[verdict])
            else:
                item.setForeground(_DEFAULT_FG)
            table.setItem(row, col, item)


def summary_html(profile: dict) -> str:
    from core.verdict_thresholds import go_pct_threshold
    from modules.m3_probability.engine import best_launch_months, annual_go_fraction

    go_pct = go_pct_threshold()
    go_thr = go_pct / 100.0
    go_frac   = annual_go_fraction(profile, go_threshold=go_thr)
    best      = best_launch_months(profile, go_threshold=go_thr)
    go_months = sum(1 for r in profile.values() if r.verdict == "GO")
    best_str  = (
        ", ".join(f"{MONTHS[m-1]} ({round(p*100)}%)" for m, p in best[:4])
        if best else f"None (no month meets the {go_pct:.0f}% GO threshold)"
    )
    return (
        f"<b style='color:#f1f5f9;'>Annual GO fraction:</b> "
        f"<span style='color:#86efac;'>{round(go_frac * 100)}%</span>  "
        f"<span style='color:#94a3b8;'>({go_months}/12 months at or above "
        f"{go_pct:.0f}%)</span>"
        f"<br><b style='color:#f1f5f9;'>Best launch months:</b> "
        f"<span style='color:#e2e8f0;'>{best_str}</span>"
    )


def sources_html(profile: dict) -> str | None:
    if not profile:
        return None
    first = next(iter(profile.values()))
    sources = getattr(first, "data_sources", {})
    if not sources:
        return None
    _SOURCE_BADGE = {
        "ndbc_realtime":      ("NDBC Realtime",      "#14532d", "#86efac"),
        "ncei_global_marine": ("NCEI Global Marine", "#1e3a5f", "#93c5fd"),
        "era5_reanalysis":    ("ERA5 Reanalysis",    "#3b0764", "#d8b4fe"),
        "ww3_erddap":         ("WW3 ERDDAP",         "#082f49", "#7dd3fc"),
        "icoads_model":       ("ICOADS Model",       "#374151", "#94a3b8"),
    }
    _PARAM_SHORT = {
        "ws": "Wind speed", "wg": "Gust", "sh": "Sea Hs", "swh": "Swell Ht",
        "swp": "Swell Per", "wdV": "Wind Dir", "sdV": "Sea Dir", "swdV": "Swell Dir",
    }
    parts = ["<b style='color:#94a3b8;'>Data Sources:</b>&nbsp; "]
    for param, src in sources.items():
        label_txt, bg, fg = _SOURCE_BADGE.get(src, (src, "#374151", "#94a3b8"))
        pname = _PARAM_SHORT.get(param, param)
        parts.append(
            f'<span style="background:{bg};color:{fg};border-radius:3px;'
            f'padding:1px 5px;font-size:7.5pt;">'
            f'<b>{pname}</b>: {label_txt}</span>&nbsp;'
        )
    return "".join(parts)


def active_weights(inc_wind_dir: bool, inc_sea_dir: bool, inc_swell_dir: bool) -> dict:
    """Build the active weight dict — five magnitude weights plus any direction
    parameter opted in. The engine renormalizes, so values need not sum to 1.0."""
    from config import DEFAULT_WEIGHTS, DIRECTION_WEIGHTS
    weights = DEFAULT_WEIGHTS.copy()
    if inc_wind_dir:
        weights["wdV"] = DIRECTION_WEIGHTS["wdV"]
    if inc_sea_dir:
        weights["sdV"] = DIRECTION_WEIGHTS["sdV"]
    if inc_swell_dir:
        weights["swdV"] = DIRECTION_WEIGHTS["swdV"]
    return weights


def basis_html(result) -> str:
    """Build the Calculation Basis panel HTML for one AnalysisResult."""
    from core.utils import band_label, lat_to_band, format_coord_dms

    site, veh, plat = result.site, result.vehicle, result.platform
    weights = result.weights or {}
    sources = result.data_sources or {}
    thr = result.thresholds or {}

    active = getattr(result, "active_params", None)
    if not active:
        active = {p for p in (_MAGNITUDE_PARAMS + _DIRECTION_PARAMS)
                  if weights.get(p, 0.0) > 0}

    def incl(p: str) -> bool:
        return p in active

    def wpct(p: str) -> str:
        return f"{round(weights.get(p, 0.0) * 100)}%"

    _L = 'style="color:#94a3b8;font-size:11px;"'
    _V = 'style="color:#f1f5f9;font-size:12px;font-weight:600;"'
    _H = 'style="color:#64748b;font-size:10px;font-weight:bold;"'

    def rowline(lbl: str, val: str) -> str:
        return f'<tr><td {_L}>{lbl}</td><td {_V}>&nbsp;{val}</td></tr>'

    def hdr(txt: str) -> str:
        return f'<tr><td colspan="2" {_H}>&nbsp;<br>{txt}</td></tr>'

    badge_incl = ('<span style="background:#14532d;color:#86efac;'
                  'font-size:10px;">&nbsp;INCLUDED&nbsp;</span>')
    badge_excl = ('<span style="background:#374151;color:#64748b;'
                  'font-size:10px;font-style:italic;">&nbsp;EXCLUDED&nbsp;</span>')

    mode_label = {"historical": "Historical", "45day": "45-Day NDBC",
                  "observed": "Observed (NDBC)"}.get(result.mode, str(result.mode))

    left = ['<table cellspacing="0" cellpadding="2">']
    left.append(hdr("SITE"))
    left.append(rowline("Name:", site.name or "—"))
    left.append(rowline("Coordinates:", format_coord_dms(site.lat, site.lon)))
    left.append(rowline("Coord code:", site.coord_code or "—"))
    left.append(rowline("Bbox:", f"{site.bbox_nm:.0f} NM"))
    left.append(rowline("Lat band:", band_label(lat_to_band(site.lat))))
    left.append(hdr("VEHICLE"))
    left.append(rowline("Name:", veh.name))
    left.append(rowline("Class:", veh.vehicle_class))
    left.append(rowline("Recovery:", veh.recovery_mode))
    left.append(rowline("Provider:", veh.provider or "—"))
    left.append(hdr("PLATFORM"))
    left.append(rowline("Name:", plat.name))
    left.append(rowline("Hull type:", plat.hull_type))
    left.append(rowline("Motion factor:", f"{plat.hull_motion_factor}"))
    left.append(rowline(
        "Max op. Hs:",
        f"{plat.max_hs_operating_m} m" if plat.max_hs_operating_m else "—"))
    left.append("</table>")

    right = ['<table cellspacing="0" cellpadding="2">']
    right.append(hdr("ANALYSIS PARAMETERS"))
    right.append(rowline("Mode:", mode_label))
    right.append(rowline("Year range:", f"{result.year_start} – {result.year_end}"))
    right.append(rowline("Era weight:", f"{result.era_weight:.2f}"))
    right.append(rowline("Confidence:", result.confidence_rating))
    right.append(hdr("VEHICLE THRESHOLDS USED"))
    right.append(rowline("Wind speed:", f"{thr.get('ws')} kts"))
    right.append(rowline("Wind gust:", f"{thr.get('wg')} kts"))
    right.append(rowline("Sea Hs:", f"{thr.get('sh')} m"))
    right.append(rowline("Swell height:", f"{thr.get('swh')} m"))
    right.append(rowline("Swell period:", f"{thr.get('swp')} s"))
    for p, lbl in (("wdV", "Wind dir:"), ("sdV", "Sea dir:"), ("swdV", "Swell dir:")):
        if incl(p):
            right.append(rowline(lbl, f"{thr.get(p)}{unit_for(p)} {badge_incl}"))
        else:
            right.append(rowline(lbl, f"— {badge_excl}"))
    right.append(hdr("PARAMETER WEIGHTS (NORMALIZED)"))
    for p in _MAGNITUDE_PARAMS:
        right.append(rowline(
            f"{p}:",
            f"{wpct(p)} &nbsp;<span style='color:#94a3b8'>{_PARAM_FULL[p]}</span>"))
    for p in _DIRECTION_PARAMS:
        if incl(p):
            right.append(rowline(
                f"{p}:",
                f"{wpct(p)} &nbsp;<span style='color:#94a3b8'>{_PARAM_FULL[p]}</span>"))
        else:
            right.append(rowline(
                f"{p}:",
                f"— {badge_excl} &nbsp;<span style='color:#64748b'>{_PARAM_FULL[p]}</span>"))
    right.append(hdr("DATA SOURCES"))
    _SRC = {"ndbc_realtime": "NDBC Realtime", "ncei_global_marine": "NCEI Global Marine",
            "ncei": "NCEI", "era5_reanalysis": "ERA5 Reanalysis",
            "ww3_erddap": "WW3 ERDDAP", "icoads_model": "ICOADS Model"}
    for p in _MAGNITUDE_PARAMS + [d for d in _DIRECTION_PARAMS if incl(d)]:
        src = sources.get(p, "—")
        right.append(rowline(f"{p}:", _SRC.get(src, src)))
    right.append("</table>")

    title = ('<span style="color:#94a3b8;font-size:11px;font-weight:600;">'
             'CALCULATION BASIS</span>')
    body = ('<table width="100%"><tr>'
            f'<td valign="top" width="50%">{"".join(left)}</td>'
            f'<td valign="top" width="50%">{"".join(right)}</td>'
            '</tr></table>')
    return title + body

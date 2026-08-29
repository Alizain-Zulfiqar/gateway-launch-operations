"""
modules/m5_reports/comparison_pdf.py -- Multi-site comparison PDF report.

Entry point:
    generate_comparison_report(site_results, vehicle, platform, output_path,
                               full_results=...) -> str

Pages:
    Page 1  -- Cover (title, vehicle/platform, site count, timestamp)
    Page 2  -- Ranking table (sorted by Annual GO% desc)
    Page 3+ -- Per site: 12-month table, parameter detail, then charts 1–12
               (same per-chart pages as Main Analysis PDF when full_results given)
    Final   -- Data basis disclaimer
"""
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fpdf import XPos, YPos

from modules.m5_reports.pdf_report import (
    _GatewayPDF, _s, _section_heading, _kv,
    _BLACK, _DKGREY, _LTGREY, _WHITE, _NAVY,
    _GREEN, _AMBER, _RED, _verdict_colour, _prob_colour,
    _PARAM_LABELS, _PARAM_UNITS, _PARAM_ORDER, _SOURCE_LABELS,
    _normalize_chart_pages, _page_chart_pages,
)
from core.models import Site, Vehicle, Platform, AnalysisResult
from core.utils import month_name

_MO = ["Jan","Feb","Mar","Apr","May","Jun",
       "Jul","Aug","Sep","Oct","Nov","Dec"]

_GO_FILL       = (210, 240, 210)
_MARGINAL_FILL = (255, 243, 190)
_NOGO_FILL     = (250, 215, 215)
_LTBLUE        = (210, 228, 250)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _annual_go_pct(profile: dict[int, AnalysisResult]) -> float:
    if not profile:
        return 0.0
    return sum(1 for r in profile.values() if r.verdict == "GO") / len(profile) * 100


def _annual_mean_prob(profile: dict[int, AnalysisResult]) -> float:
    if not profile:
        return 0.0
    return sum(r.overall_prob for r in profile.values()) / len(profile)


def _best_month(profile: dict[int, AnalysisResult]) -> tuple[int, float] | None:
    if not profile:
        return None
    best = max(profile.items(), key=lambda kv: kv[1].overall_prob)
    return best[0], best[1].overall_prob


def _rank_sites(site_results: list[tuple[Site, dict]]) -> list[tuple[int, Site, dict]]:
    """Return list of (rank, site, profile) sorted by annual GO% desc."""
    scored = [
        (i, site, profile, _annual_go_pct(profile))
        for i, (site, profile) in enumerate(site_results)
    ]
    scored.sort(key=lambda x: x[3], reverse=True)
    return [(rank + 1, item[1], item[2]) for rank, item in enumerate(scored)]


# ── Page 1: Cover ─────────────────────────────────────────────────────────────

def _page_cover(
    pdf: _GatewayPDF,
    site_results: list,
    vehicle: Vehicle,
    platform: Platform,
) -> None:
    pdf.add_page()

    # Navy header band
    pdf.set_fill_color(*_NAVY)
    pdf.rect(0, 0, pdf.w, 42, "F")

    pdf.set_y(9)
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*_WHITE)
    pdf.cell(0, 10, "Multi-Site Comparison Report",
             align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, "Launch Window Probability  --  Site Ranking & Analysis",
             align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, "Seagate Space Corporation  --  Site Analysis & Mission Planning",
             align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*_BLACK)
    pdf.ln(16)

    _section_heading(pdf, "Vehicle")
    _kv(pdf, "Name", vehicle.name)
    _kv(pdf, "Class", vehicle.vehicle_class)
    _kv(pdf, "Recovery mode", vehicle.recovery_mode)
    pdf.ln(2)

    _section_heading(pdf, "Platform")
    _kv(pdf, "Name", platform.name)
    _kv(pdf, "Hull type", platform.hull_type)
    _kv(pdf, "Hull motion factor", f"{platform.hull_motion_factor:.2f}")
    pdf.ln(2)

    _section_heading(pdf, "Analysis Overview")
    n = len(site_results)
    _kv(pdf, "Sites compared", str(n))
    _kv(pdf, "Analysis mode", "Historical (Copernicus ERA5 day-fraction GO%)")
    _kv(pdf, "Coordinate convention", "+lat=N, -lat=S  /  +lon=E, -lon=W  (WGS-84)")
    from core.verdict_thresholds import go_pct_threshold, marginal_pct_threshold
    go_pct = go_pct_threshold()
    marg_pct = marginal_pct_threshold()
    _kv(pdf, "GO threshold", f"{go_pct:.0f}% overall probability")
    pdf.ln(2)

    # Quick site list
    _section_heading(pdf, "Sites Included")
    pdf.ln(1)
    for i, (site, _profile) in enumerate(site_results, 1):
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(12, 6, f"  {i}.", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_font("Helvetica", "B", 9)
        label = site.name or site.coord_str
        pdf.cell(0, 6, label, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(8)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*_DKGREY)
    pdf.cell(0, 5, f"Generated: {ts}", align="R",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*_BLACK)


# ── Page 2: Ranking table ─────────────────────────────────────────────────────

def _page_ranking(
    pdf: _GatewayPDF,
    ranked: list[tuple[int, Site, dict]],
) -> None:
    pdf.add_page()
    _section_heading(pdf, "Site Ranking  --  Annual GO Fraction")
    pdf.ln(2)

    cw = [10, 42, 36, 22, 26, 24, 22]
    hdrs = ["Rank", "Site Name", "Coordinates", "Annual\nGO%", "Best\nMonth",
            "Best Mo\nProb", "Annual\nMean%"]
    hdr_h = 8

    pdf.set_fill_color(*_NAVY)
    pdf.set_text_color(*_WHITE)
    pdf.set_font("Helvetica", "B", 7)
    for h, w in zip(hdrs, cw):
        pdf.multi_cell(w, hdr_h / (1 + h.count("\n")), h, border=0,
                       fill=True, align="C",
                       new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.ln(hdr_h)
    pdf.set_text_color(*_BLACK)

    for rank, site, profile in ranked:
        go_pct  = _annual_go_pct(profile)
        mean_p  = _annual_mean_prob(profile)
        bm      = _best_month(profile)
        bm_name = _MO[bm[0] - 1] if bm else "--"
        bm_pct  = f"{round(bm[1]*100)}%" if bm else "--"

        from core.verdict_thresholds import go_pct_threshold, marginal_pct_threshold
        go_thr = go_pct_threshold()
        marg_thr = marginal_pct_threshold()

        fill = (
            _GO_FILL if go_pct >= go_thr
            else (_MARGINAL_FILL if go_pct >= marg_thr else _NOGO_FILL)
        )
        pdf.set_fill_color(*fill)
        row_h = 6

        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(cw[0], row_h, str(rank), fill=True, align="C",
                 new_x=XPos.RIGHT, new_y=YPos.TOP)
        label = site.name or site.coord_str
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(cw[1], row_h, label[:28], fill=True, new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(cw[2], row_h, site.coord_str, fill=True, align="C",
                 new_x=XPos.RIGHT, new_y=YPos.TOP)

        # Annual GO% with colour background
        go_col = (
            _GREEN if go_pct >= go_thr
            else (_AMBER if go_pct >= marg_thr else _RED)
        )
        pdf.set_fill_color(*go_col)
        pdf.set_text_color(*_WHITE)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(cw[3], row_h, f"{round(go_pct)}%", fill=True, align="C",
                 new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_text_color(*_BLACK)

        pdf.set_fill_color(*fill)
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(cw[4], row_h, bm_name, fill=True, align="C",
                 new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(cw[5], row_h, bm_pct, fill=True, align="C",
                 new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(cw[6], row_h, f"{round(mean_p*100)}%", fill=True, align="C",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(6)
    from core.verdict_thresholds import go_pct_threshold
    go_pct = go_pct_threshold()
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*_DKGREY)
    pdf.cell(0, 5,
             f"GO% = fraction of months with overall_prob >= {go_pct:.0f}%  |  "
             "Best Month = highest single-month probability  |  "
             "Annual Mean = mean of all 12 monthly probabilities",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*_BLACK)


# ── Page 3+: One page per site ────────────────────────────────────────────────

def _page_site(
    pdf: _GatewayPDF,
    rank: int,
    site: Site,
    profile: dict[int, AnalysisResult],
    total_sites: int,
) -> None:
    pdf.add_page()
    go_pct = _annual_go_pct(profile)
    col    = _verdict_colour(go_pct / 100)
    bm     = _best_month(profile)

    _section_heading(
        pdf,
        f"Site {rank} of {total_sites}  --  {site.name or site.coord_str}"
    )
    pdf.ln(1)

    _kv(pdf, "Coordinates", site.coord_str)
    _kv(pdf, "Annual GO fraction", f"{round(go_pct)}%")
    if bm:
        _kv(pdf, "Best launch month", f"{_MO[bm[0]-1]}  ({round(bm[1]*100)}%)")
    pdf.ln(4)

    # 12-month table
    cw = [24, 22, 32, 94]
    hdrs = ["Month", "Prob%", "Verdict", "Limiting Parameter"]
    pdf.set_fill_color(*_NAVY)
    pdf.set_text_color(*_WHITE)
    pdf.set_font("Helvetica", "B", 8)
    for h, w in zip(hdrs, cw):
        pdf.cell(w, 7, h, fill=True, align="C",
                 new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.ln(7)
    pdf.set_text_color(*_BLACK)

    for month in range(1, 13):
        result = profile.get(month)
        if result is None:
            continue

        verdict = result.verdict
        if verdict == "GO":
            fill = _GO_FILL
        elif verdict == "MARGINAL":
            fill = _MARGINAL_FILL
        else:
            fill = _NOGO_FILL

        is_best = bm and month == bm[0]

        pdf.set_fill_color(*(_LTBLUE if is_best else fill))
        pdf.set_font("Helvetica", "B" if is_best else "", 8)

        pdf.cell(cw[0], 6, _MO[month - 1], fill=True, align="C",
                 new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(cw[1], 6, f"{result.pct}%", fill=True, align="C",
                 new_x=XPos.RIGHT, new_y=YPos.TOP)

        vc_col = _GREEN if verdict == "GO" else (_AMBER if verdict == "MARGINAL" else _RED)
        pdf.set_fill_color(*vc_col)
        pdf.set_text_color(*_WHITE)
        pdf.cell(cw[2], 6, verdict, fill=True, align="C",
                 new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_text_color(*_BLACK)

        pdf.set_fill_color(*(_LTBLUE if is_best else fill))
        from modules.m5_reports.pdf_report import _PARAM_LABELS
        limit_label = _PARAM_LABELS.get(result.limiting_param, result.limiting_param)
        pdf.cell(cw[3], 6, limit_label, fill=True,
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(*_DKGREY)
    pdf.cell(0, 5, "Light blue row = best launch month for this site.",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*_BLACK)


# ── Page 3b+: Per-site threshold/probability parameter detail (Set 35) ───────

def _page_site_params(
    pdf: _GatewayPDF,
    rank: int,
    site: Site,
    profile: dict[int, AnalysisResult],
    total_sites: int,
) -> None:
    """Threshold-vs-probability breakdown for this site's best month, one
    row per parameter — closes the 'threshold params vs. site probability'
    gap in the comparison report (previously only the monthly verdict +
    limiting-parameter NAME was shown, never the underlying threshold,
    effective mean, or per-parameter probability)."""
    bm = _best_month(profile)
    month = bm[0] if bm else next(iter(profile))
    r = profile[month]

    pdf.add_page()
    _section_heading(
        pdf,
        f"Site {rank} of {total_sites}  --  {site.name or site.coord_str}  "
        f"--  Parameter Detail ({_MO[month - 1]})"
    )
    pdf.ln(1)

    cw = [46, 22, 30, 24, 28, 24]
    hdrs = ["Parameter", "Threshold", "Eff. climate\nmean", "Prob.", "Data source", ""]
    hdr_h = 9
    pdf.set_fill_color(*_NAVY)
    pdf.set_text_color(*_WHITE)
    pdf.set_font("Helvetica", "B", 8)
    for h, w in zip(hdrs, cw):
        pdf.multi_cell(w, hdr_h / (1 + h.count("\n")), h, border=0,
                       fill=True, align="C",
                       new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.ln(hdr_h)
    pdf.set_text_color(*_BLACK)

    # Params NOT in active_params carried zero weight and did not contribute
    # to overall_prob (Set 27B: direction params default excluded unless
    # checked) — must be visually distinguished, not styled identically to
    # included params (see the matching fix in pdf_report.py::_page2).
    active = r.active_params or set()

    for idx, param in enumerate(_PARAM_ORDER):
        fill_bg = _LTGREY if idx % 2 == 0 else _WHITE
        pdf.set_fill_color(*fill_bg)

        thresh   = r.thresholds.get(param, 0.0)
        eff      = r.effective_means.get(param, 0.0)
        prob     = r.param_probs.get(param, 0.0)
        src      = r.data_sources.get(param, "icoads_model")
        unit     = _PARAM_UNITS.get(param, "")
        is_limit = (param == r.limiting_param)
        is_active = param in active

        label = _PARAM_LABELS.get(param, param)
        if not is_active:
            label += "  (excluded)"
        pdf.set_font("Helvetica", "B" if is_limit else ("I" if not is_active else ""), 8)
        pdf.set_text_color(*(_DKGREY if not is_active else _BLACK))
        pdf.cell(cw[0], 7, label,
                 fill=True, new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_text_color(*_BLACK)

        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*(_DKGREY if not is_active else _BLACK))
        pdf.cell(cw[1], 7, f"{thresh:.1f} {unit}",
                 fill=True, align="R", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(cw[2], 7, f"{eff:.2f} {unit}",
                 fill=True, align="R", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_text_color(*_BLACK)

        pdf.set_fill_color(*(_prob_colour(prob) if is_active else _LTGREY))
        pdf.set_text_color(*_WHITE if is_active else _DKGREY)
        pdf.set_font("Helvetica", "B" if is_active else "", 8)
        pdf.cell(cw[3], 7, f"{round(prob*100)}%",
                 fill=True, align="C", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_text_color(*_BLACK)
        pdf.set_fill_color(*fill_bg)

        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(*(_DKGREY if not is_active else _BLACK))
        pdf.cell(cw[4], 7, _SOURCE_LABELS.get(src, src),
                 fill=True, align="C", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_text_color(*_BLACK)

        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*_RED if is_limit else _BLACK)
        pdf.cell(cw[5], 7, "< LIMIT" if is_limit else "",
                 fill=True, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(*_BLACK)

    pdf.ln(2)
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(*_DKGREY)
    pdf.cell(0, 5,
             "(excluded) = parameter carried zero weight and did not "
             "contribute to the overall probability for this run.",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "I", 7)
    pdf.cell(0, 5,
             f"Shown for {_MO[month-1]} (this site's best launch month). "
             "'< LIMIT' marks the parameter driving this month's overall verdict.",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*_BLACK)


# ── Final page: Data basis ────────────────────────────────────────────────────

def _page_data_basis(pdf: _GatewayPDF) -> None:
    pdf.add_page()
    _section_heading(pdf, "Data Basis and Disclaimer")
    pdf.ln(2)

    _kv(pdf, "Primary data source", "Copernicus ERA5 monthly means (CDS API)")
    _kv(pdf, "GO metric", "Day-fraction: % of days/month meeting all active criteria")
    _kv(pdf, "Operability charts", "Last 10 calendar years from era5_monthly_cache")
    _kv(pdf, "Coordinate convention", "+lat = North, -lat = South  /  +lon = East, -lon = West  (WGS-84)")
    _kv(pdf, "Probability model",
        "ERA5 means x seasonal/era modifiers x hull motion x vehicle class x recovery mode")
    pdf.ln(6)

    pdf.set_fill_color(*_LTGREY)
    margin = pdf.l_margin
    pdf.rect(margin, pdf.get_y(), pdf.w - 2 * margin, 30, "F")
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(0, 5, "DISCLAIMER", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 8)
    disclaimer = (
        "Historical window-probability estimates are provided for mission planning "
        "purposes only -- not day-of-launch forecasts. Probabilities represent "
        "estimated day-fractions from monthly ERA5 means below vehicle thresholds, "
        "adjusted for hull motion, vehicle class, and recovery mode. They do not "
        "account for real-time synoptic weather events, tropical cyclones, or "
        "equipment status. All launch decisions require current-day meteorological "
        "clearance from authorised Range Safety personnel."
    )
    pdf.set_x(margin + 4)
    pdf.multi_cell(pdf.w - 2 * margin - 8, 4.5, disclaimer, align="J")
    pdf.ln(3)


def _page_site_chart_section(
    pdf: _GatewayPDF,
    rank: int,
    site: Site,
    n: int,
    chart_pages: list,
) -> None:
    """Insert Main Analysis-style chart pages for one site, with site context."""
    pages = _normalize_chart_pages(chart_pages, None)
    if not pages:
        return
    label = site.name or site.coord_str
    # Prefix each chart title with site rank/name so pages stay identifiable.
    for p in pages:
        p["title"] = f"Site {rank}/{n}: {label} — {p['title']}"
    _page_chart_pages(pdf, pages)


# ── Public entry point ────────────────────────────────────────────────────────

def generate_comparison_report(
    site_results: list[tuple[Site, dict[int, AnalysisResult]]],
    vehicle: Vehicle,
    platform: Platform,
    output_path: str,
    *,
    full_results: Optional[list] = None,
    chart_tmpdir: Optional[str] = None,
    chart_context: Optional[dict] = None,
) -> str:
    """
    Generate a multi-site comparison PDF report.

    Parameters
    ----------
    site_results : list of (Site, profile) where profile is dict[month, AnalysisResult]
    vehicle      : Vehicle used for all sites
    platform     : Platform used for all sites
    output_path  : Destination path for the PDF
    full_results : optional list of (Site, profile, climatology, operability, day_frac) —
                   when provided, charts 1–12 are rendered per site like Main Analysis
    chart_tmpdir : directory for temporary chart PNGs (required with full_results)
    chart_context : optional {"thresholds", "active_criteria"} from the comparison run

    Returns
    -------
    Absolute path string of the written PDF.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    n = len(site_results)
    title = f"Multi-Site Comparison  --  {n} site{'s' if n != 1 else ''}  --  {vehicle.name}"

    pdf = _GatewayPDF(title=title)
    pdf.set_author("Seagate Space Corporation -- Gateway Launch Operations")
    pdf.set_title(title)
    pdf.set_subject(f"{vehicle.name} / {platform.name}")

    ranked = _rank_sites(site_results)

    # Map site id → extras for chart rendering
    extras_by_id: dict = {}
    if full_results:
        for row in full_results:
            site, profile, clim, oper = row[0], row[1], row[2], row[3]
            day_frac = row[4] if len(row) > 4 else None
            param_frac = row[5] if len(row) > 5 else None
            sid = getattr(site, "id", None)
            key = sid if sid is not None else id(site)
            extras_by_id[key] = (profile, clim, oper, day_frac, param_frac)

    _page_cover(pdf, site_results, vehicle, platform)
    _page_ranking(pdf, ranked)
    for rank, site, profile in ranked:
        _page_site(pdf, rank, site, profile, n)
        _page_site_params(pdf, rank, site, profile, n)
        if chart_tmpdir and extras_by_id:
            from modules.m5_reports.analysis_chart_pages import (
                build_analysis_chart_pages,
            )
            sid = getattr(site, "id", None)
            key = sid if sid is not None else None
            bundle = None
            if key is not None and key in extras_by_id:
                bundle = extras_by_id[key]
            else:
                # Fall back to name match
                for row in (full_results or []):
                    if row[0] is site or (
                        getattr(row[0], "name", None) == getattr(site, "name", None)
                        and getattr(row[0], "lat", None) == getattr(site, "lat", None)
                    ):
                        bundle = (
                            row[1], row[2], row[3],
                            row[4] if len(row) > 4 else None,
                            row[5] if len(row) > 5 else None,
                        )
                        break
            if bundle is not None:
                if len(bundle) >= 5:
                    _prof, clim, oper, day_frac, param_frac = bundle
                else:
                    _prof, clim, oper, day_frac = (
                        bundle[0], bundle[1], bundle[2],
                        bundle[3] if len(bundle) > 3 else None,
                    )
                    param_frac = None
                site_dir = Path(chart_tmpdir) / f"site_{rank}"
                site_dir.mkdir(parents=True, exist_ok=True)
                ctx = chart_context or {}
                chart_pages = build_analysis_chart_pages(
                    site_dir,
                    _prof or profile,
                    climatology=clim,
                    operability=oper,
                    thresholds=ctx.get("thresholds"),
                    active_criteria=ctx.get("active_criteria"),
                    day_fractions=day_frac,
                    param_fractions=param_frac,
                )
                _page_site_chart_section(pdf, rank, site, n, chart_pages)
    _page_data_basis(pdf)

    pdf.output(str(out))
    return str(out.resolve())

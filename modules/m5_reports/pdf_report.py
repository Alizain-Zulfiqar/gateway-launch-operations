"""
modules/m5_reports/pdf_report.py -- PDF analysis report generation (fpdf2).

Entry point:
    generate_analysis_report(result: AnalysisResult, output_path: str) -> str

Produces an A4 PDF:
    Page 1 -- Cover / Summary
    Optional -- 12-Month Annual Profile table
    Parameter Detail table
    Data basis and confidence
    Decision Charts — one page per chart with title, figure, and conclusion
    Optional buoy / forecast pages
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fpdf import FPDF, XPos, YPos

from core.models import AnalysisResult
from core.utils import month_name

# ---- Colour palette (R, G, B) -----------------------------------------------
_GREEN  = (34,  139, 34)
_AMBER  = (204, 120,  0)
_RED    = (180,  30, 30)
_BLACK  = (20,   20, 20)
_DKGREY = (80,   80, 80)
_LTGREY = (230, 230, 230)
_WHITE  = (255, 255, 255)
_NAVY   = (15,   40, 80)

# ---- Parameter display names -------------------------------------------------
_PARAM_LABELS = {
    "ws":   "Wind speed",
    "wg":   "Wind gust",
    "sh":   "Sea wave height (Hs)",
    "swh":  "Swell height",
    "swp":  "Swell period",
    "wdV":  "Wind dir. tolerance",
    "sdV":  "Sea dir. tolerance",
    "swdV": "Swell dir. tolerance",
}

_PARAM_UNITS = {
    "ws":   "kts",
    "wg":   "kts",
    "sh":   "m",
    "swh":  "m",
    "swp":  "s",
    "wdV":  "deg",
    "sdV":  "deg",
    "swdV": "deg",
}

_SOURCE_LABELS = {
    "ndbc_realtime":      "NDBC realtime",
    "ncei_global_marine": "NCEI Global Marine",
    "icoads_model":       "ICOADS model",
}

_PARAM_ORDER = ["ws", "wg", "sh", "swh", "swp", "wdV", "sdV", "swdV"]

_NAVY_HEADER = (27, 58, 107)   # #1B3A6B


def _draw_report_header(pdf: "FPDF", title: str, subtitle: str) -> None:
    """Branded header bar with logo, title, subtitle, and timestamp."""
    from config import LOGO_PATH
    pdf.set_fill_color(*_NAVY_HEADER)
    pdf.rect(0, 0, 210, 28, style="F")

    try:
        pdf.image(str(LOGO_PATH), x=8, y=4, w=60)
    except Exception:
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(8, 8)
        pdf.cell(80, 10, "SeagateSpace", align="L")

    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(75, 6)
    pdf.cell(130, 7, _s(title), align="R")

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(147, 197, 253)
    pdf.set_xy(75, 14)
    pdf.cell(130, 6, _s(subtitle), align="R")

    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(100, 116, 139)
    pdf.set_xy(75, 20)
    timestamp = datetime.now(timezone.utc).strftime("%B %d, %Y  %H:%M UTC")
    pdf.cell(130, 5, f"Generated: {_s(timestamp)}", align="R")

    pdf.set_y(32)
    pdf.set_text_color(*_BLACK)


# ---- Sanitise strings for latin-1 core fonts ---------------------------------

def _s(text: str) -> str:
    # Replace characters outside latin-1 so Helvetica can render them.
    text = text.replace("—", "--")   # em dash
    text = text.replace("–", "-")    # en dash
    text = text.replace("≥", ">=")   # greater-than-or-equal
    text = text.replace("≤", "<=")   # less-than-or-equal
    text = text.replace("◄", "<")    # left-filled triangle (limit marker)
    text = text.replace("►", ">")    # right-filled triangle
    text = text.replace("’", "'")    # right single quotation mark
    text = text.replace("‘", "'")    # left single quotation mark
    text = text.replace("“", '"')    # left double quotation mark
    text = text.replace("”", '"')    # right double quotation mark
    return text.encode("latin-1", errors="replace").decode("latin-1")


# ---- Colour helpers ----------------------------------------------------------

def _verdict_colour(prob: float) -> tuple:
    from core.verdict_thresholds import get_go_threshold, get_marginal_threshold
    if prob >= get_go_threshold():
        return _GREEN
    if prob >= get_marginal_threshold():
        return _AMBER
    return _RED


def _prob_colour(prob: float) -> tuple:
    return _verdict_colour(prob)


# ---- PDF class ---------------------------------------------------------------

class _GatewayPDF(FPDF):
    """Custom FPDF subclass with header/footer for interior pages."""

    def __init__(self, title: str = "Launch Window Probability Report"):
        super().__init__(orientation="P", unit="mm", format="A4")
        self._report_title = title
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(left=18, top=18, right=18)

    # Wrap all text output through _s() so no non-latin-1 char reaches fpdf2.
    def cell(self, w=0, h=0, text="", *args, **kwargs):
        return super().cell(w, h, _s(str(text)), *args, **kwargs)

    def multi_cell(self, w, h=0, text="", *args, **kwargs):
        return super().multi_cell(w, h, _s(str(text)), *args, **kwargs)

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "B", 7)
        self.set_text_color(*_DKGREY)
        self.cell(0, 6, self._report_title, align="L",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*_LTGREY)
        self.line(self.l_margin, self.get_y(),
                  self.w - self.r_margin, self.get_y())
        self.ln(2)
        self.set_text_color(*_BLACK)

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*_DKGREY)
        self.cell(0, 5,
                  "SEAGATE SPACE CORPORATION -- CONFIDENTIAL -- NOT FOR FLIGHT USE",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 5, f"Page {self.page_no()}", align="C")
        self.set_text_color(*_BLACK)


# ---- Table header helper ----------------------------------------------------

def _tbl_header(
    pdf: "_GatewayPDF",
    headers: list,
    widths: list,
    row_h: float = 7.0,
) -> None:
    """Render one navy header row."""
    pdf.set_fill_color(*_NAVY)
    pdf.set_text_color(*_WHITE)
    pdf.set_font("Helvetica", "B", 8)
    for h, w in zip(headers, widths):
        pdf.cell(w, row_h, h, fill=True, align="C",
                 new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.ln(row_h)
    pdf.set_text_color(*_BLACK)


# ---- Section helpers ---------------------------------------------------------

def _section_heading(pdf: _GatewayPDF, text: str):
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(*_NAVY)
    pdf.set_text_color(*_WHITE)
    pdf.cell(0, 7, f"  {text}", fill=True,
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*_BLACK)
    pdf.ln(2)


def _kv(pdf: _GatewayPDF, key: str, value: str, key_w: float = 58):
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(key_w, 6, key, new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


# ---- Page 1: Cover / Summary -------------------------------------------------

def _page1(pdf: _GatewayPDF, r: AnalysisResult):
    pdf.add_page()
    _draw_report_header(
        pdf,
        "Launch Window Probability Report",
        "Gateway Series -- Offshore Launch Site Analysis",
    )
    pdf.ln(6)

    # Overall probability box
    col = _verdict_colour(r.overall_prob)
    box_x = (pdf.w - 80) / 2
    pdf.set_fill_color(*col)
    pdf.set_draw_color(*col)
    pdf.rect(box_x, pdf.get_y(), 80, 28, "F")

    pdf.set_y(pdf.get_y() + 4)
    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(*_WHITE)
    pdf.cell(0, 12, f"{r.pct}%", align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, r.verdict, align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*_BLACK)
    pdf.ln(8)

    # Site / vehicle / platform details
    _section_heading(pdf, "Site")
    site = r.site
    _kv(pdf, "Name", site.name or "-")
    _kv(pdf, "Coordinates", site.coord_str)
    _kv(pdf, "Bounding box", f"{site.bbox_nm:.1f} NM radius")
    pdf.ln(2)

    _section_heading(pdf, "Vehicle")
    v = r.vehicle
    _kv(pdf, "Name", v.name)
    _kv(pdf, "Class", v.vehicle_class)
    _kv(pdf, "Recovery mode", v.recovery_mode)
    if v.mass_to_orbit_kg:
        _kv(pdf, "Payload (LEO)", f"{v.mass_to_orbit_kg:,.0f} kg")
    pdf.ln(2)

    _section_heading(pdf, "Platform")
    p = r.platform
    _kv(pdf, "Name", p.name)
    _kv(pdf, "Hull type", p.hull_type)
    _kv(pdf, "Hull motion factor", f"{p.hull_motion_factor:.2f}")
    if p.max_hs_operating_m:
        _kv(pdf, "Max operating Hs", f"{p.max_hs_operating_m:.1f} m")
    pdf.ln(2)

    _section_heading(pdf, "Analysis")
    mo_label = month_name(r.month_filter) if r.month_filter else "All months"
    _kv(pdf, "Month analysed", mo_label)
    _kv(pdf, "Mode", r.mode)
    yr_s = r.year_start or 1960
    yr_e = r.year_end   or 2024
    _kv(pdf, "Era", f"{yr_s}-{yr_e}  ({yr_e - yr_s + 1} years)")
    _kv(pdf, "ERA weight", f"{r.era_weight:.3f}  ({r.confidence_rating} confidence)")
    _kv(pdf, "Limiting parameter",
        f"{r.limiting_param}  -  {_PARAM_LABELS.get(r.limiting_param, r.limiting_param)}"
        f"  ({round(r.param_probs[r.limiting_param]*100)}%)")
    pdf.ln(2)



# ---- Page 2: Parameter detail table -----------------------------------------

def _page2(pdf: _GatewayPDF, r: AnalysisResult):
    pdf.add_page()
    _section_heading(pdf, "Parameter Detail")
    pdf.ln(1)

    # Column widths (total ~174 mm usable)
    cw = [46, 22, 30, 24, 28, 24]
    hdrs = ["Parameter", "Threshold", "Eff. climate\nmean", "Prob.", "Data source", ""]
    row_h = 7
    hdr_h = 9

    # Header row
    pdf.set_fill_color(*_NAVY)
    pdf.set_text_color(*_WHITE)
    pdf.set_font("Helvetica", "B", 8)
    for i, (h, w) in enumerate(zip(hdrs, cw)):
        pdf.multi_cell(w, hdr_h / (1 + h.count("\n")), h, border=0,
                       fill=True, align="C",
                       new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.ln(hdr_h)
    pdf.set_text_color(*_BLACK)

    thresholds   = r.thresholds
    eff_means    = r.effective_means
    param_probs  = r.param_probs
    data_sources = r.data_sources
    # Params NOT in active_params carry zero weight and did not contribute
    # to overall_prob (Set 27B: direction params default excluded unless
    # checked). Row styling below must make this visually unmistakable —
    # previously every parameter got the same colour-coded probability
    # treatment regardless of inclusion, which misrepresented excluded
    # direction params as having counted toward the verdict.
    active = r.active_params or set()

    for idx, param in enumerate(_PARAM_ORDER):
        fill_bg = _LTGREY if idx % 2 == 0 else _WHITE
        pdf.set_fill_color(*fill_bg)

        thresh   = thresholds.get(param, 0.0)
        eff      = eff_means.get(param, 0.0)
        prob     = param_probs.get(param, 0.0)
        src      = data_sources.get(param, "icoads_model")
        unit     = _PARAM_UNITS.get(param, "")
        is_limit = (param == r.limiting_param)
        is_active = param in active
        prob_col = _prob_colour(prob) if is_active else _LTGREY

        # Col 0 -- parameter name (+ excluded marker)
        label = _PARAM_LABELS.get(param, param)
        if not is_active:
            label += "  (excluded)"
        pdf.set_font("Helvetica", "B" if is_limit else ("I" if not is_active else ""), 8)
        pdf.set_text_color(*(_DKGREY if not is_active else _BLACK))
        pdf.set_fill_color(*fill_bg)
        pdf.cell(cw[0], row_h, label,
                 fill=True, new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_text_color(*_BLACK)

        # Col 1 -- threshold
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*(_DKGREY if not is_active else _BLACK))
        pdf.cell(cw[1], row_h, f"{thresh:.1f} {unit}",
                 fill=True, align="R", new_x=XPos.RIGHT, new_y=YPos.TOP)

        # Col 2 -- effective climate mean
        pdf.cell(cw[2], row_h, f"{eff:.2f} {unit}",
                 fill=True, align="R", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_text_color(*_BLACK)

        # Col 3 -- probability (colour background only when active; grey
        # and unfilled-looking when excluded, matching the on-screen
        # Calculation Basis panel's INCLUDED/EXCLUDED badge distinction)
        pdf.set_fill_color(*prob_col)
        pdf.set_text_color(*_WHITE if is_active else _DKGREY)
        pdf.set_font("Helvetica", "B" if is_active else "", 8)
        pdf.cell(cw[3], row_h, f"{round(prob*100)}%",
                 fill=True, align="C", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_text_color(*_BLACK)
        pdf.set_fill_color(*fill_bg)

        # Col 4 -- data source
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(*(_DKGREY if not is_active else _BLACK))
        pdf.cell(cw[4], row_h, _SOURCE_LABELS.get(src, src),
                 fill=True, align="C", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_text_color(*_BLACK)

        # Col 5 -- limiting flag (excluded params can never be limiting —
        # the engine only selects from active_params)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*_RED if is_limit else _BLACK)
        pdf.cell(cw[5], row_h, "< LIMIT" if is_limit else "",
                 fill=True, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(*_BLACK)

    pdf.ln(2)
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(*_DKGREY)
    pdf.cell(0, 5,
             "(excluded) = parameter carried zero weight and did not "
             "contribute to the overall probability for this run.",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*_BLACK)

    pdf.ln(4)

    # ---- Weighted probability breakdown --------------------------------------
    _section_heading(pdf, "Parameter Weights and Contribution")
    pdf.ln(1)

    cw2 = [46, 22, 22, 30, 54]
    hdrs2 = ["Parameter", "Weight", "Prob.", "Weighted contrib.", "Notes"]
    pdf.set_fill_color(*_NAVY)
    pdf.set_text_color(*_WHITE)
    pdf.set_font("Helvetica", "B", 8)
    for h, w in zip(hdrs2, cw2):
        pdf.cell(w, 7, h, fill=True, align="C",
                 new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.ln(7)
    pdf.set_text_color(*_BLACK)

    weights_used = r.weights
    for idx, param in enumerate(_PARAM_ORDER):
        fill_bg = _LTGREY if idx % 2 == 0 else _WHITE
        pdf.set_fill_color(*fill_bg)
        wt      = weights_used.get(param, 0.0)
        prob    = param_probs.get(param, 0.0)
        contrib = prob * wt

        pdf.set_font("Helvetica", "", 8)
        pdf.cell(cw2[0], 6, _PARAM_LABELS.get(param, param),
                 fill=True, new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(cw2[1], 6, f"{wt:.3f}",
                 fill=True, align="R", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(cw2[2], 6, f"{round(prob*100)}%",
                 fill=True, align="R", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(cw2[3], 6, f"{contrib:.4f}",
                 fill=True, align="R", new_x=XPos.RIGHT, new_y=YPos.TOP)
        note = "limiting constraint" if param == r.limiting_param else ""
        pdf.set_font("Helvetica", "I", 7)
        pdf.cell(cw2[4], 6, note, fill=True,
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 9)
    overall_check = sum(
        param_probs[p] * weights_used.get(p, 0.0) for p in _PARAM_ORDER
    )
    pdf.cell(0, 6, f"Overall probability (weighted sum): {round(overall_check*100)}%",
             align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)


# ---- Page 3: Data basis and confidence --------------------------------------

def _page3(pdf: _GatewayPDF, r: AnalysisResult):
    pdf.add_page()
    _section_heading(pdf, "Data Basis and Confidence")
    pdf.ln(2)

    yr_s = r.year_start or 1960
    yr_e = r.year_end   or 2024
    span = yr_e - yr_s + 1

    _kv(pdf, "ICOADS era analysed",  f"{yr_s}-{yr_e}  ({span} years)")
    _kv(pdf, "Spatial resolution",
        "1 x 1 deg (post-1960 ICOADS C00606)  /  2 x 2 deg (pre-1960)")
    _kv(pdf, "ERA weight",           f"{r.era_weight:.4f}")
    _kv(pdf, "Confidence rating",    r.confidence_rating.upper())
    _kv(pdf, "Probability model",
        "ICOADS climatological base x seasonal x hull x vehicle class x recovery")
    pdf.ln(4)

    _section_heading(pdf, "Data Source per Parameter")
    pdf.ln(1)

    cw = [56, 40, 78]
    hdrs = ["Parameter", "Source tier", "Description"]
    pdf.set_fill_color(*_NAVY)
    pdf.set_text_color(*_WHITE)
    pdf.set_font("Helvetica", "B", 8)
    for h, w in zip(hdrs, cw):
        pdf.cell(w, 7, h, fill=True, align="C",
                 new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.ln(7)
    pdf.set_text_color(*_BLACK)

    src_desc = {
        "ndbc_realtime":      "NDBC 45-day realtime buoy/station obs",
        "ncei_global_marine": "NCEI Global Marine (ICOADS ship/buoy, historical)",
        "icoads_model":       "ICOADS C00606 climatological model (default)",
    }

    for idx, param in enumerate(_PARAM_ORDER):
        fill_bg = _LTGREY if idx % 2 == 0 else _WHITE
        pdf.set_fill_color(*fill_bg)
        src = r.data_sources.get(param, "icoads_model")

        pdf.set_font("Helvetica", "", 8)
        pdf.cell(cw[0], 6, _PARAM_LABELS.get(param, param),
                 fill=True, new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(cw[1], 6, _SOURCE_LABELS.get(src, src),
                 fill=True, align="C", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_font("Helvetica", "I", 7)
        pdf.cell(cw[2], 6, src_desc.get(src, src),
                 fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(8)

    # ---- ERA weight explanation ----------------------------------------------
    _section_heading(pdf, "ERA Weight Interpretation")
    pdf.ln(2)

    era_rows = [
        (">=0.95", "high",     "1960-present  -  Full 1 deg ICOADS density"),
        (">=0.85", "moderate", "1925-1959     -  Pre-satellite, reduced density"),
        (">=0.72", "low",      "1900-1924     -  Sparse ship reports"),
        ("<0.72",  "model",    "Pre-1900      -  Climatological estimate only"),
    ]
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(*_NAVY)
    pdf.set_text_color(*_WHITE)
    for h, w in zip(["ERA weight", "Rating", "Meaning"], [28, 26, 120]):
        pdf.cell(w, 7, h, fill=True, align="C",
                 new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.ln(7)
    pdf.set_text_color(*_BLACK)

    for idx, (wt_str, rating, meaning) in enumerate(era_rows):
        fill_bg = _LTGREY if idx % 2 == 0 else _WHITE
        pdf.set_fill_color(*fill_bg)
        pdf.set_font("Helvetica", "", 8)
        for val, w in zip([wt_str, rating, meaning], [28, 26, 120]):
            pdf.cell(w, 6, val, fill=True, align="C" if w < 50 else "L",
                     new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.ln(6)

    pdf.ln(10)

    # ---- Disclaimer ---------------------------------------------------------
    pdf.set_fill_color(*_LTGREY)
    pdf.set_draw_color(*_DKGREY)
    margin = pdf.l_margin
    pdf.rect(margin, pdf.get_y(), pdf.w - 2 * margin, 24, "F")
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(0, 5, "DISCLAIMER", align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 8)
    disclaimer = (
        "Historical window-probability estimates are provided for mission planning "
        "purposes only -- not day-of-launch forecasts. Probabilities represent the "
        "fraction of historical observations below vehicle thresholds, adjusted for "
        "hull motion, vehicle class, and recovery mode. They do not account for "
        "real-time synoptic weather events, tropical cyclones, or equipment status. "
        "All launch decisions require current-day meteorological clearance from "
        "authorised Range Safety personnel."
    )
    pdf.set_x(margin + 4)
    pdf.multi_cell(pdf.w - 2 * margin - 8, 4.5, disclaimer, align="J")
    pdf.ln(4)

    # Footer note
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(*_DKGREY)
    pdf.cell(0, 5,
             "Multiplier chain: Base x Season x Era_Var x Hull_Factor x VC_Mod x Rec_Mod x Basin_Mod",
             align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*_BLACK)


# ---- Page: 12-Month Annual Profile (Set 34, item 13) ------------------------

def _page_annual(pdf: "_GatewayPDF", annual_profile: dict) -> None:
    """Full 12-month table matching the on-screen Analysis tab (Month /
    Probability / Verdict / Limiting Parameter) — the PDF previously only
    ever showed a single recomputed month, never the full profile."""
    pdf.add_page()
    _section_heading(pdf, "12-Month Annual Profile")
    pdf.ln(1)

    cw = [40, 30, 34, 70]
    hdrs = ["Month", "Probability", "Verdict", "Limiting Parameter"]
    _tbl_header(pdf, hdrs, cw, row_h=8)

    for month in range(1, 13):
        r = annual_profile.get(month)
        if r is None:
            continue
        fill_bg = _LTGREY if month % 2 == 0 else _WHITE
        verdict_col = _verdict_colour(r.overall_prob)

        pdf.set_font("Helvetica", "", 9)
        pdf.set_fill_color(*fill_bg)
        pdf.cell(cw[0], 7, month_name(month), fill=True,
                 new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(cw[1], 7, f"{r.pct}%", fill=True, align="C",
                 new_x=XPos.RIGHT, new_y=YPos.TOP)

        pdf.set_fill_color(*verdict_col)
        pdf.set_text_color(*_WHITE)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(cw[2], 7, r.verdict, fill=True, align="C",
                 new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_text_color(*_BLACK)
        pdf.set_fill_color(*fill_bg)

        pdf.set_font("Helvetica", "", 9)
        limit_label = _PARAM_LABELS.get(r.limiting_param, r.limiting_param)
        pdf.cell(cw[3], 7, limit_label, fill=True,
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)


# ---- Page 4: Near-term Outlook (3-box verdicts) -----------------------------

def _page4(
    pdf: _GatewayPDF,
    result: AnalysisResult,
    blended_result: "Optional[AnalysisResult]",
    observed_result: "Optional[AnalysisResult]",
) -> None:
    pdf.add_page()
    _draw_report_header(
        pdf,
        "Near-term Outlook",
        "Combined Climate + Buoy Probability Assessment",
    )
    pdf.ln(6)

    _section_heading(pdf, "Launch Probability — Three-Source Comparison")
    pdf.ln(4)

    boxes = [
        ("Climate Model",  result,          "Historical ICOADS climatology"),
        ("Blended",        blended_result,  "Climate + NDBC observed data"),
        ("Observed Only",  observed_result, "NDBC buoy observations only"),
    ]

    box_w   = 56.0
    gap     = 5.0
    total_w = 3 * box_w + 2 * gap
    x0      = (pdf.w - total_w) / 2
    box_h   = 38.0
    y0      = pdf.get_y()

    for i, (title, res, caption) in enumerate(boxes):
        x = x0 + i * (box_w + gap)

        if res is None:
            col        = _DKGREY
            pct_text   = "--"
            verd_text  = "N/A"
        else:
            col        = _verdict_colour(res.overall_prob)
            pct_text   = f"{res.pct}%"
            verd_text  = res.verdict

        pdf.set_fill_color(*col)
        pdf.rect(x, y0, box_w, box_h, "F")

        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*_WHITE)
        pdf.set_xy(x, y0 + 2)
        pdf.cell(box_w, 6, _s(title), align="C",
                 new_x=XPos.RIGHT, new_y=YPos.TOP)

        pdf.set_font("Helvetica", "B", 20)
        pdf.set_xy(x, y0 + 10)
        pdf.cell(box_w, 13, pct_text, align="C",
                 new_x=XPos.RIGHT, new_y=YPos.TOP)

        pdf.set_font("Helvetica", "B", 10)
        pdf.set_xy(x, y0 + 26)
        pdf.cell(box_w, 8, _s(verd_text), align="C",
                 new_x=XPos.RIGHT, new_y=YPos.TOP)

        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(200, 200, 200)
        pdf.set_xy(x, y0 + box_h + 2)
        pdf.cell(box_w, 5, _s(caption), align="C",
                 new_x=XPos.RIGHT, new_y=YPos.TOP)

    pdf.set_text_color(*_BLACK)
    pdf.set_y(y0 + box_h + 12)
    pdf.ln(4)

    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*_DKGREY)
    pdf.multi_cell(
        0, 4.5,
        "Climate Model: ICOADS historical climatology (1960-2024). "
        "Blended: climate base with real-time NDBC buoy observations substituted "
        "for available parameters. "
        "Observed Only: probability estimated from current buoy conditions with "
        "hull and vehicle modifiers applied.",
        align="J",
    )
    pdf.set_text_color(*_BLACK)


# ---- Page 5: Buoy Observation Detail ----------------------------------------

def _page5(
    pdf: _GatewayPDF,
    ndbc_combined: dict,
    vehicle: "AnalysisResult",
    forecast_horizon_hours: int,
) -> None:
    _HOR_LABEL = {
        24: "24-hour", 48: "48-hour", 72: "72-hour", 120: "5-day", 168: "7-day",
    }
    horizon_label = _HOR_LABEL.get(forecast_horizon_hours, f"{forecast_horizon_hours}h")

    pdf.add_page()
    _section_heading(pdf, f"NDBC Buoy Observations -- {_s(horizon_label)} Window")
    pdf.ln(2)

    n    = ndbc_combined.get("station_count", 0)
    sids = ndbc_combined.get("station_ids", [])
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(
        0, 5,
        f"Contributing stations ({n}): {_s(', '.join(sids))}",
        new_x=XPos.LMARGIN, new_y=YPos.NEXT,
    )
    pdf.ln(2)

    thresholds = vehicle.thresholds()

    cw   = [48, 26, 26, 22, 26, 18]
    hdrs = ["Parameter", "Mean", "Network Max", "P90", "Vehicle Limit", "Status"]
    _tbl_header(pdf, hdrs, cw)

    _PARAM_ROWS = [
        ("Wind Speed",   "wind_speed",   "weighted_mean_kts", "network_max_kts", "network_p90_kts", "ws",  "kts"),
        ("Wind Gust",    "wind_gust",    "weighted_mean_kts", "network_max_kts", "network_p90_kts", "wg",  "kts"),
        ("Wave Ht (Hs)", "wave_height",  "weighted_mean_m",   "network_max_m",   "network_p90_m",   "sh",  "m"),
        ("Swell Height", "swell_height", "weighted_mean_m",   "network_max_m",   "network_p90_m",   "swh", "m"),
        ("Swell Period", "swell_period", "weighted_mean_s",   "network_max_s",   "network_p90_s",   "swp", "s"),
    ]

    def _fmt(v, u):
        return f"{v:.2f} {u}" if v is not None else "--"

    for idx, (label, param_key, mk, maxk, p90k, thresh_k, unit) in enumerate(_PARAM_ROWS):
        block   = ndbc_combined.get(param_key, {})
        mean_v  = block.get(mk)
        max_v   = block.get(maxk)
        p90_v   = block.get(p90k)
        thresh_v = thresholds.get(thresh_k, 0.0)

        fill_bg = _LTGREY if idx % 2 == 0 else _WHITE
        pdf.set_fill_color(*fill_bg)

        if mean_v is not None and thresh_v > 0:
            ratio = mean_v / thresh_v
            if ratio < 0.7:     status, s_col = "GO",      _GREEN
            elif ratio < 1.0:   status, s_col = "MARGINAL", _AMBER
            else:               status, s_col = "NO-GO",   _RED
        else:
            status, s_col = "N/A", _DKGREY

        pdf.set_font("Helvetica", "", 8)
        row_vals = [
            label,
            _fmt(mean_v, unit),
            _fmt(max_v,  unit),
            _fmt(p90_v,  unit),
            f"{thresh_v:.1f} {unit}",
        ]
        for val, w in zip(row_vals, cw[:-1]):
            pdf.cell(w, 6, _s(val), fill=True, align="C",
                     new_x=XPos.RIGHT, new_y=YPos.TOP)

        pdf.set_fill_color(*s_col)
        pdf.set_text_color(*_WHITE)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(cw[-1], 6, status, fill=True, align="C",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(*_BLACK)

    pdf.ln(4)

    weights = ndbc_combined.get("weights", {})
    if weights:
        pdf.set_font("Helvetica", "I", 7)
        pdf.set_text_color(*_DKGREY)
        wt_parts = [
            f"{sid}: {w*100:.1f}%"
            for sid, w in sorted(weights.items(), key=lambda kv: -kv[1])
        ]
        pdf.cell(
            0, 5,
            _s("IDW blend weights:  " + "  |  ".join(wt_parts)),
            new_x=XPos.LMARGIN, new_y=YPos.NEXT,
        )
        pdf.set_text_color(*_BLACK)


# ---- Page 6: Forecast Detail ------------------------------------------------

def _page6(
    pdf: _GatewayPDF,
    forecast_data: dict,
    forecast_horizon_hours: int,
) -> None:
    horizon_label = forecast_data.get(
        "horizon_label",
        f"{forecast_horizon_hours}h",
    )

    pdf.add_page()
    _section_heading(pdf, f"Forecast Window -- {_s(horizon_label)}")
    pdf.ln(2)

    confidence  = forecast_data.get("confidence", 0)
    go_pct      = forecast_data.get("go_pct")
    go_hours    = forecast_data.get("go_hours")
    total_hours = forecast_data.get("total_hours", forecast_horizon_hours)
    n_stn       = forecast_data.get("station_count", 0)

    pdf.set_font("Helvetica", "", 8)
    pdf.cell(
        0, 5,
        f"Stations blended: {n_stn}   |   Horizon: {_s(horizon_label)}"
        f"   |   Confidence: {confidence}/5",
        new_x=XPos.LMARGIN, new_y=YPos.NEXT,
    )
    pdf.ln(4)

    # GO window banner
    if go_pct is not None:
        col = _GREEN if go_pct >= 70 else _AMBER if go_pct >= 40 else _RED
        margin  = pdf.l_margin
        box_top = pdf.get_y()
        pdf.set_fill_color(*col)
        pdf.rect(margin, box_top, pdf.w - 2 * margin, 24, "F")
        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(*_WHITE)
        pdf.set_xy(margin, box_top + 2)
        pdf.cell(
            pdf.w - 2 * margin, 10,
            f"{go_hours} of {total_hours} hours GO  ({go_pct:.0f}%)",
            align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT,
        )
        pdf.set_font("Helvetica", "", 9)
        pdf.set_xy(margin, box_top + 14)
        pdf.cell(
            pdf.w - 2 * margin, 8,
            _s(f"{horizon_label} forecast window"),
            align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT,
        )
        pdf.set_text_color(*_BLACK)
        pdf.set_y(box_top + 28)
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*_DKGREY)
        pdf.cell(
            0, 8,
            "Insufficient data to compute GO window.",
            new_x=XPos.LMARGIN, new_y=YPos.NEXT,
        )
        pdf.set_text_color(*_BLACK)

    pdf.ln(6)

    cards = forecast_data.get("cards", [])
    if cards:
        _section_heading(pdf, "Parameter Status")
        pdf.ln(2)
        cw2 = [72, 50, 40]
        _tbl_header(pdf, ["Parameter", "Observed Value", "Status"], cw2)

        _SCOL = {"GO": _GREEN, "MARGINAL": _AMBER, "NO-GO": _RED}

        for idx, card in enumerate(cards):
            fill_bg = _LTGREY if idx % 2 == 0 else _WHITE
            s_col   = _SCOL.get(card.get("status", ""), _DKGREY)
            pdf.set_fill_color(*fill_bg)
            pdf.set_font("Helvetica", "", 8)
            pdf.cell(cw2[0], 6, _s(card.get("param", "")),
                     fill=True, new_x=XPos.RIGHT, new_y=YPos.TOP)
            pdf.cell(cw2[1], 6, _s(card.get("value", "--")),
                     fill=True, align="C", new_x=XPos.RIGHT, new_y=YPos.TOP)
            pdf.set_fill_color(*s_col)
            pdf.set_text_color(*_WHITE)
            pdf.set_font("Helvetica", "B", 8)
            pdf.cell(cw2[2], 6, _s(card.get("status", "--")),
                     fill=True, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(*_BLACK)

    pdf.ln(6)

    _section_heading(pdf, "Forecast Confidence Table")
    pdf.ln(1)
    conf_rows = [
        ("24-hour", "5/5", "Recent obs, minimal extrapolation"),
        ("48-hour", "4/5", "Short-range, good buoy coverage"),
        ("72-hour", "4/5", "Model skill generally reliable to 3 days"),
        ("5-day",   "3/5", "Increased uncertainty beyond 72 h"),
        ("7-day",   "2/5", "Climatological guidance only; high uncertainty"),
    ]
    for idx, (h, c, desc) in enumerate(conf_rows):
        is_cur  = (h == horizon_label)
        fill_bg = _LTGREY if idx % 2 == 0 else _WHITE
        pdf.set_fill_color(*fill_bg)
        pdf.set_font("Helvetica", "B" if is_cur else "", 8)
        pdf.cell(30, 6, h, fill=True, new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(20, 6, c, fill=True, align="C", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_font("Helvetica", "I" if is_cur else "", 7)
        pdf.cell(0, 6, _s(desc), fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


# ---- Decision Charts pages ---------------------------------------------------

def _normalize_chart_pages(chart_pages: Optional[list], chart_images: Optional[list]) -> list:
    """Accept ChartPage objects, dicts, or legacy bare PNG path lists."""
    pages = []
    for item in (chart_pages or []):
        if item is None:
            continue
        if isinstance(item, dict):
            path = item.get("path") or item.get("image") or ""
            pages.append({
                "number": item.get("number"),
                "title": item.get("title") or "Decision Chart",
                "path": path,
                "conclusion": item.get("conclusion") or "",
            })
        else:
            path = getattr(item, "path", "") or ""
            pages.append({
                "number": getattr(item, "number", None),
                "title": getattr(item, "title", None) or "Decision Chart",
                "path": path,
                "conclusion": getattr(item, "conclusion", "") or "",
            })
    # Legacy: list of image paths only
    if not pages and chart_images:
        for i, path in enumerate(chart_images):
            pages.append({
                "number": i + 1,
                "title": f"Decision Chart {i + 1}",
                "path": path,
                "conclusion": "",
            })
    return [p for p in pages if p.get("path") and Path(p["path"]).is_file()]


def _page_chart_pages(pdf: "_GatewayPDF", chart_pages: list) -> None:
    """One A4 page per chart: title, chart image, then conclusion below (no overlap)."""
    pages = chart_pages or []
    if not pages:
        return

    # Fixed band at the bottom of the page for the conclusion text so it can
    # never sit on top of the chart (keep_aspect_ratio + rendered_height was
    # placing the cursor inside the image box).
    _CONCLUSION_BAND_MM = 42.0
    _GAP_MM = 4.0

    n = len(pages)
    for i, page in enumerate(pages):
        pdf.add_page()
        num = page.get("number") or (i + 1)
        title = page.get("title") or f"Decision Chart {num}"
        _section_heading(pdf, f"Decision Chart {num} of {n}")
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*_BLACK)
        pdf.multi_cell(0, 5, _s(title), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(1)

        conclusion = (page.get("conclusion") or "").strip()
        x = pdf.l_margin
        y_img = pdf.get_y()
        max_w = pdf.w - pdf.l_margin - pdf.r_margin
        page_bottom = pdf.h - pdf.b_margin

        if conclusion:
            concl_top = page_bottom - _CONCLUSION_BAND_MM
            max_img_h = max(40.0, concl_top - y_img - _GAP_MM)
        else:
            concl_top = page_bottom
            max_img_h = max(40.0, page_bottom - y_img - 2.0)

        # Fit chart entirely inside the upper region (above the conclusion band).
        try:
            pdf.image(
                str(page["path"]),
                x=x,
                y=y_img,
                w=max_w,
                h=max_img_h,
                keep_aspect_ratio=True,
            )
        except TypeError:
            pdf.image(str(page["path"]), x=x, y=y_img, w=max_w)

        if not conclusion:
            continue

        # Conclusion always starts at the reserved band — never over the chart.
        pdf.set_y(concl_top)
        pdf.set_fill_color(241, 245, 249)  # slate-100
        pdf.set_draw_color(*_LTGREY)
        pdf.rect(x, concl_top, max_w, _CONCLUSION_BAND_MM - 1.0, style="DF")

        pdf.set_xy(x + 3, concl_top + 2.5)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*_NAVY)
        pdf.cell(max_w - 6, 5, "Conclusion", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.set_x(x + 3)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*_BLACK)
        # Constrain multi_cell width so text stays inside the band.
        pdf.multi_cell(
            max_w - 6,
            3.6,
            _s(conclusion),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )


# ---- Public entry point ------------------------------------------------------

def generate_analysis_report(
    result: AnalysisResult,
    output_path: str,
    include_buoy_forecast: bool = False,
    blended_result: Optional[AnalysisResult] = None,
    observed_result: Optional[AnalysisResult] = None,
    forecast_data: Optional[dict] = None,
    ndbc_combined: Optional[dict] = None,
    forecast_horizon_hours: int = 72,
    project=None,  # Optional[Project]
    annual_profile: Optional[dict] = None,  # {1..12: AnalysisResult}, Set 34 item 13
    chart_images: Optional[list] = None,  # legacy PNG path list
    chart_pages: Optional[list] = None,  # per-chart pages with conclusions
) -> str:
    """
    Generate a PDF analysis report and write it to output_path.

    Parameters
    ----------
    result                 : AnalysisResult from compute_probability()
    output_path            : Full .pdf path (legacy) OR output directory — when a
                             directory is given, the filename is generated via naming.py
    include_buoy_forecast  : If True, append pages 4-6 (Near-term Outlook,
                             Buoy Observation Detail, Forecast Detail)
    blended_result         : Climate + observed blended AnalysisResult (page 4)
    observed_result        : Observed-only AnalysisResult (page 4)
    forecast_data          : Output of compute_forecast_analysis() (page 6)
    ndbc_combined          : Output of aggregate_station_statistics() (page 5)
    forecast_horizon_hours : Forecast window in hours (24/48/72/120/168)
    project                : Optional Project dataclass; drives filename generation
    annual_profile         : Optional dict {1..12: AnalysisResult} from
                             compute_annual_profile() — when supplied, inserts
                             a 12-Month Annual Profile table page right after
                             the cover page. Previously the PDF only ever
                             showed the single `result` month.
    chart_images           : Legacy list of PNG paths (still accepted).
    chart_pages            : Preferred — list of ChartPage / dicts with
                             path, title, conclusion for each decision chart.

    Returns
    -------
    Absolute path string of the written PDF.
    """
    out = Path(output_path)
    sequence_number = 0
    if out.suffix.lower() == ".pdf":
        filename = out.name
    else:
        from modules.m5_reports.naming import build_report_filename
        info = build_report_filename("analysis", result.site, project)
        filename = info["filename"]
        sequence_number = info["sequence_number"]
        out = out / filename
    out.parent.mkdir(parents=True, exist_ok=True)

    pdf = _GatewayPDF()
    pdf.set_author("Seagate Space Corporation -- Gateway Launch Operations")
    pdf.set_title("Launch Window Probability Report")
    pdf.set_subject(
        f"{result.site.name or result.site.coord_str} / "
        f"{result.vehicle.name} / {result.platform.name}"
    )

    _page1(pdf, result)
    if annual_profile:
        _page_annual(pdf, annual_profile)
    _page2(pdf, result)
    _page3(pdf, result)
    _page_chart_pages(pdf, _normalize_chart_pages(chart_pages, chart_images))

    if include_buoy_forecast:
        _page4(pdf, result, blended_result, observed_result)
        if ndbc_combined:
            _page5(pdf, ndbc_combined, result.vehicle, forecast_horizon_hours)
        if forecast_data:
            _page6(pdf, forecast_data, forecast_horizon_hours)

    pdf.output(str(out))

    from modules.m5_reports.naming import record_report
    record_report(
        "analysis", filename, str(out.resolve()),
        sequence_number, result.site.id,
        project.id if project else None,
    )

    return str(out.resolve())

"""
modules/m5_reports/voyage_pdf.py -- Voyage & Mission Planning PDF report.

Entry point:
    generate_voyage_report(schedule, all_port_costs, analysis_result,
                           output_path) -> str

Produces a 6-page A4 PDF:
    Page 1 -- Cover / Mission Summary
    Page 2 -- Voyage Route (leg-by-leg)
    Page 3 -- Cost Breakdown (charter / port fees / fuel / per-launch)
    Page 4 -- Port Comparison Table
    Page 5 -- Voyage Schedule (waypoints)
    Page 6 -- Data Basis and Assumptions

Imports shared style (colours, _GatewayPDF, helpers) from pdf_report.py so
both reports remain visually consistent.
"""

import sys
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fpdf import XPos, YPos

# Shared style layer -- colours, sanitiser, PDF class, section helpers.
from modules.m5_reports.pdf_report import (
    _GatewayPDF, _s, _section_heading, _kv, _draw_report_header,
    _BLACK, _DKGREY, _LTGREY, _WHITE, _NAVY,
    _GREEN, _AMBER, _RED,
)

from core.models import (
    VoyageCostBreakdown, VoyageSchedule, AnalysisResult, PORT_ROLE_LABELS,
    FEE_CATEGORIES, FEE_CATEGORY_LABELS,
)
from core.utils import month_name

# Light blue highlight for the selected port row in the comparison table.
_LTBLUE = (210, 228, 250)

# Fee-column headers must stay single-line: a wrapped header fills 8 mm while its
# neighbours fill 4 mm, leaving a ragged navy band.
_FEE_PDF_HEADERS = {
    "agents":      "Agents",
    "assist_tugs": "Tugs",
    "pilots":      "Pilots",
    "wharfage":    "Wharfage",
    "loading_ops": "Loading",
    "other":       "Other",
}


# ---- Small shared helpers ---------------------------------------------------

def _fmt_usd(v: float) -> str:
    return f"${v:,.0f}"


def _table_header(pdf: _GatewayPDF, headers: list[str], widths: list[float],
                  row_h: float = 7.0):
    """Render one navy header row and leave cursor at next line."""
    pdf.set_fill_color(*_NAVY)
    pdf.set_text_color(*_WHITE)
    pdf.set_font("Helvetica", "B", 7)
    for h, w in zip(headers, widths):
        pdf.cell(w, row_h, h, fill=True, align="C",
                 new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.ln(row_h)
    pdf.set_text_color(*_BLACK)


def _footer_note(pdf: _GatewayPDF, text: str):
    """Italic small note line at current cursor position."""
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(*_DKGREY)
    pdf.cell(0, 5, text, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*_BLACK)


def _disclaimer_box(pdf: _GatewayPDF, text: str, box_h: float = 28.0):
    """Grey box with centred DISCLAIMER heading + justified body text."""
    margin = pdf.l_margin
    pdf.set_fill_color(*_LTGREY)
    pdf.set_draw_color(*_DKGREY)
    pdf.rect(margin, pdf.get_y(), pdf.w - 2 * margin, box_h, "F")
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(0, 5, "DISCLAIMER", align="C",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_x(margin + 4)
    pdf.multi_cell(pdf.w - 2 * margin - 8, 4.5, text, align="J")


# ---- Page 1: Cover / Mission Summary ----------------------------------------

def _page1(pdf: _GatewayPDF,
           schedule: VoyageSchedule,
           analysis_result: Optional[AnalysisResult]) -> None:
    pdf.add_page()
    _draw_report_header(
        pdf,
        "Voyage & Mission Planning Report",
        "Gateway Series -- Maritime Logistics Planning",
    )
    pdf.ln(6)

    cost = schedule.cost

    # ---- Mission Parameters --------------------------------------------------
    _section_heading(pdf, "Mission Parameters")
    _kv(pdf, "Launch site", schedule.site.name or "-")
    _kv(pdf, "Coordinates", schedule.site.coord_str)
    _kv(pdf, "Bounding box", f"{schedule.site.bbox_nm:.1f} NM radius")
    if schedule.site.platform_id:
        _kv(pdf, "Platform ID", str(schedule.site.platform_id))
    _kv(pdf, "Load / discharge port",
        f"{schedule.port.port_name}  ({schedule.port.country})")
    _kv(pdf, "Route",
        " -> ".join([cost.legs[0].from_name] + [leg.to_name for leg in cost.legs])
        if cost.legs else "-")
    _kv(pdf, "Total route distance", f"{cost.total_distance_nm:,.1f} NM")
    if schedule.departure_date:
        _kv(pdf, "Departure date", schedule.departure_date.isoformat())
    pdf.ln(3)

    # ---- Launch analysis (optional) ------------------------------------------
    if analysis_result is not None:
        _section_heading(pdf, "Launch Window Analysis")
        v = analysis_result.vehicle
        _kv(pdf, "Launch vehicle", f"{v.name}  ({v.vehicle_class})")
        _kv(pdf, "Recovery mode", v.recovery_mode)

        try:
            from modules.m3_probability.engine import (
                compute_annual_profile, best_launch_months, annual_go_fraction,
            )
            profile  = compute_annual_profile(
                analysis_result.site,
                analysis_result.vehicle,
                analysis_result.platform,
            )
            best = best_launch_months(profile)
            go_f = annual_go_fraction(profile)
            if best:
                bm, bp = best[0]
                _kv(pdf, "Best launch month",
                    f"{month_name(bm)}  ({round(bp * 100)}%)")
            _kv(pdf, "Annual GO fraction",
                f"{round(go_f * 100)}%  "
                f"({sum(1 for r in profile.values() if r.verdict == 'GO')}/12 months >= 70%)")
        except Exception:
            mo = month_name(analysis_result.month_filter) \
                if analysis_result.month_filter else "N/A"
            _kv(pdf, "Month analysed",
                f"{mo}  --  {analysis_result.pct}%  {analysis_result.verdict}")
        pdf.ln(3)

    # ---- Cost Summary (prominent box) ----------------------------------------
    _section_heading(pdf, "Voyage Cost Summary")
    pdf.set_fill_color(*_LTGREY)
    margin = pdf.l_margin
    box_top = pdf.get_y()
    pdf.rect(margin, box_top, pdf.w - 2 * margin, 54, "F")
    pdf.ln(2)

    # Two columns inside the box
    col_l = margin + 2
    col_r = margin + (pdf.w - 2 * margin) / 2 + 2
    col_w = (pdf.w - 2 * margin) / 2 - 4

    def _kv2(label: str, val: str, col_x: float):
        pdf.set_x(col_x)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(44, 5.5, label, new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(col_w - 44, 5.5, val, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    y0 = pdf.get_y()

    # Left column -- schedule
    _kv2("Legs:", str(len(cost.legs)), col_l)
    _kv2("Distance:", f"{cost.total_distance_nm:,.1f} NM", col_l)
    _kv2("Transit days:", f"{cost.total_transit_days:.2f}", col_l)
    _kv2("On-site days:", f"{cost.total_onsite_days:.2f}", col_l)
    _kv2("Voyage days:", f"{cost.voyage_days:.2f}", col_l)

    # Right column -- money (reset y)
    pdf.set_y(y0)
    _kv2("Charter hire:", _fmt_usd(cost.charter_total_usd), col_r)
    _kv2("Port fees:", _fmt_usd(cost.port_fees_total_usd), col_r)
    _kv2("Fuel:", f"{_fmt_usd(cost.fuel_total_usd)}  "
                  f"({cost.fuel_total_gal:,.0f} gal)", col_r)
    _kv2("Launches:", str(cost.launches), col_r)
    _kv2("Cost per launch:", _fmt_usd(cost.cost_per_launch()), col_r)

    # Move past the box, print the grand total prominently
    pdf.set_y(box_top + 38)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*_NAVY)
    pdf.cell(0, 8,
             f"Total Voyage Cost:  {_fmt_usd(cost.total_usd)}",
             align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*_BLACK)
    pdf.ln(4)

    # Timestamp
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*_DKGREY)
    pdf.cell(0, 5, f"Generated: {ts}", align="R",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*_BLACK)


# ---- Page 2: Voyage Route and Cost Breakdown --------------------------------

def _page_route(pdf: _GatewayPDF, schedule: VoyageSchedule) -> None:
    pdf.add_page()
    cost = schedule.cost

    _section_heading(pdf, "Voyage Route -- Leg Detail")
    pdf.ln(1)

    cw   = [10, 46, 46, 24, 24, 24]
    hdrs = ["Leg", "From", "To", "Distance NM", "Transit days", "On-site days"]
    _table_header(pdf, hdrs, cw)

    for leg in cost.legs:
        pdf.set_fill_color(*(_LTGREY if leg.index % 2 == 0 else (255, 255, 255)))
        pdf.set_font("Helvetica", "", 7)
        vals = [
            str(leg.index),
            _s(leg.from_name)[:30],
            _s(leg.to_name)[:30],
            f"{leg.distance_nm:,.1f}",
            f"{leg.transit_days:.2f}",
            f"{leg.onsite_days:.2f}",
        ]
        for val, w, align in zip(vals, cw, ["C", "L", "L", "R", "R", "R"]):
            pdf.cell(w, 6, val, fill=True, align=align,
                     new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.ln(6)

    # Totals row
    pdf.set_fill_color(*_NAVY)
    pdf.set_text_color(*_WHITE)
    pdf.set_font("Helvetica", "B", 7)
    totals = ["", "TOTAL", "", f"{cost.total_distance_nm:,.1f}",
              f"{cost.total_transit_days:.2f}", f"{cost.total_onsite_days:.2f}"]
    for val, w, align in zip(totals, cw, ["C", "L", "L", "R", "R", "R"]):
        pdf.cell(w, 6, val, fill=True, align=align,
                 new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.ln(6)
    pdf.set_text_color(*_BLACK)
    pdf.ln(2)
    _footer_note(pdf,
                 f"Transit days = distance NM / {cost.speed_kts:g} kts / 24. "
                 f"On-site days belong to each leg's destination, so the voyage "
                 f"origin is never billed on-site time.")
    _footer_note(pdf,
                 "Distances are great-circle and ignore landmasses; actual "
                 "sailing distances may be materially longer.")


# ---- Page 3: Cost Breakdown --------------------------------------------------

def _page_breakdown(pdf: _GatewayPDF, schedule: VoyageSchedule) -> None:
    pdf.add_page()
    cost = schedule.cost

    # ---- Charter hire --------------------------------------------------------
    _section_heading(pdf, "Charter Hire")
    cw2   = [58, 28, 30, 30, 28]
    hdrs2 = ["Vessel", "Status", "Hire days", "Day rate", "Charter cost"]
    _table_header(pdf, hdrs2, cw2)
    for idx, line in enumerate(cost.vessels):
        pdf.set_fill_color(*(_LTGREY if idx % 2 == 0 else (255, 255, 255)))
        pdf.set_font("Helvetica", "", 7)
        vals = [
            _s(line.name),
            "Deployed" if line.deployed else "Not deployed",
            f"{line.charter_days:.2f}" if line.deployed else "-",
            _fmt_usd(line.charter_rate_usd_day) if line.deployed else "-",
            _fmt_usd(line.charter_usd),
        ]
        for val, w, align in zip(vals, cw2, ["L", "C", "R", "R", "R"]):
            pdf.cell(w, 6, val, fill=True, align=align,
                     new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.ln(6)
    _kv(pdf, "Charter hire total", _fmt_usd(cost.charter_total_usd))
    pdf.ln(3)

    # ---- Port fees ----------------------------------------------------------
    _section_heading(pdf, "Port Fees")
    if cost.port_fees and any(pf.total_usd for pf in cost.port_fees):
        # Widths must sum to the 174 mm printable band, or fpdf wraps the row.
        cw3 = [30] + [20] * len(FEE_CATEGORIES) + [24]
        hdrs3 = ["Port Role"] + [_FEE_PDF_HEADERS[c] for c in FEE_CATEGORIES] \
            + ["Total"]
        _table_header(pdf, hdrs3, cw3, row_h=6.0)

        for idx, pf in enumerate(cost.port_fees):
            pdf.set_fill_color(*(_LTGREY if idx % 2 == 0 else (255, 255, 255)))
            pdf.set_font("Helvetica", "", 7)
            vals = [_s(PORT_ROLE_LABELS.get(pf.role, pf.role))] \
                + [_fmt_usd(pf.amount(c)) for c in FEE_CATEGORIES] \
                + [_fmt_usd(pf.total_usd)]
            for val, w, align in zip(vals, cw3, ["L"] + ["R"] * (len(cw3) - 1)):
                pdf.cell(w, 6, val, fill=True, align=align,
                         new_x=XPos.RIGHT, new_y=YPos.TOP)
            pdf.ln(6)
    else:
        _footer_note(pdf, "No port fees entered for the ports on this route.")
    _kv(pdf, "Port fees total", _fmt_usd(cost.port_fees_total_usd))
    pdf.ln(3)

    # ---- Fuel ---------------------------------------------------------------
    _section_heading(pdf, "Fuel")
    cw4   = [50, 28, 28, 26, 20, 22]
    hdrs4 = ["Vessel", "Underway gal", "On-site gal", "Total gal",
             "$ / gal", "Fuel cost"]
    _table_header(pdf, hdrs4, cw4)
    for idx, line in enumerate(cost.vessels):
        pdf.set_fill_color(*(_LTGREY if idx % 2 == 0 else (255, 255, 255)))
        pdf.set_font("Helvetica", "", 7)
        vals = [
            _s(line.name),
            f"{line.underway_gal:,.2f}",
            f"{line.onsite_gal:,.2f}",
            f"{line.total_gal:,.2f}",
            f"${line.fuel_usd_gal:,.2f}",
            _fmt_usd(line.fuel_usd),
        ]
        for val, w, align in zip(vals, cw4, ["L", "R", "R", "R", "R", "R"]):
            pdf.cell(w, 6, val, fill=True, align=align,
                     new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.ln(6)
    _kv(pdf, "Fuel total",
        f"{_fmt_usd(cost.fuel_total_usd)}  ({cost.fuel_total_gal:,.2f} gal)")
    pdf.ln(4)

    # ---- Grand total + economy of scale -------------------------------------
    _section_heading(pdf, "Total and Per-Launch Cost")
    _kv(pdf, "Charter hire",  _fmt_usd(cost.charter_total_usd))
    _kv(pdf, "Port fees",     _fmt_usd(cost.port_fees_total_usd))
    _kv(pdf, "Fuel",          _fmt_usd(cost.fuel_total_usd))
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*_NAVY)
    pdf.cell(0, 7, f"TOTAL VOYAGE COST:  {_fmt_usd(cost.total_usd)}",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*_BLACK)
    pdf.ln(2)

    cw5 = [40, 44]
    _table_header(pdf, ["Launches", "Cost per launch"], cw5)
    for n in range(1, max(3, cost.launches) + 1):
        pdf.set_fill_color(*(_LTBLUE if n == cost.launches else
                             (_LTGREY if n % 2 == 0 else (255, 255, 255))))
        pdf.set_font("Helvetica", "B" if n == cost.launches else "", 7)
        pdf.cell(cw5[0], 6, str(n), fill=True, align="C",
                 new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(cw5[1], 6, _fmt_usd(cost.cost_per_launch(n)), fill=True,
                 align="R", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.ln(6)


# ---- Page 4: Port Comparison Table ------------------------------------------

def _page2(pdf: _GatewayPDF,
           schedule: VoyageSchedule,
           all_port_costs: list[VoyageCostBreakdown]) -> None:
    pdf.add_page()
    _section_heading(pdf, "Nearest Port Options -- Full-Route Cost Comparison")
    pdf.ln(1)

    cw   = [8, 34, 22, 18, 16, 26, 20, 16, 24]
    hdrs = ["#", "Port Name", "Country", "Dist NM", "Voyage\ndays",
            "Charter", "Port fees", "Fuel", "Total"]

    pdf.set_fill_color(*_NAVY)
    pdf.set_text_color(*_WHITE)
    pdf.set_font("Helvetica", "B", 7)
    row_h = 8
    for h, w in zip(hdrs, cw):
        pdf.multi_cell(w, row_h / 2, h, fill=True, align="C",
                       border=0, new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.ln(row_h)
    pdf.set_text_color(*_BLACK)

    selected_port_id = schedule.port.id
    selected_port_name = schedule.port.port_name

    for rank, vc in enumerate(all_port_costs, 1):
        is_selected = (
            vc.port.id is not None and vc.port.id == selected_port_id
        ) or vc.port.port_name == selected_port_name

        fill = _LTBLUE if is_selected else (_LTGREY if rank % 2 == 0 else (255, 255, 255))
        pdf.set_fill_color(*fill)

        pdf.set_font("Helvetica", "B" if is_selected else "", 7)

        vals = [
            str(rank),
            _s(vc.port.port_name)[:32],
            _s(vc.port.country)[:20],
            f"{vc.total_distance_nm:,.0f}",
            f"{vc.voyage_days:.2f}",
            _fmt_usd(vc.charter_total_usd),
            _fmt_usd(vc.port_fees_total_usd),
            _fmt_usd(vc.fuel_total_usd),
            _fmt_usd(vc.total_usd),
        ]
        aligns = ["C", "L", "L", "R", "R", "R", "R", "R", "R"]
        for val, w, align in zip(vals, cw, aligns):
            pdf.cell(w, 6, val, fill=True, align=align,
                     new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.ln(6)

    pdf.ln(4)
    cost = schedule.cost
    _footer_note(
        pdf,
        f"Speed: {cost.speed_kts:g} kts  |  "
        f"Each candidate is costed over the full multi-leg route, substituted "
        f"into the load and discharge roles  |  "
        f"{cost.launches} launch(es) per voyage."
    )


# ---- Page 3: Voyage Schedule ------------------------------------------------

def _page3(pdf: _GatewayPDF, schedule: VoyageSchedule) -> None:
    pdf.add_page()
    heading = (f"Transit Schedule -- {schedule.port.port_name} "
               f"to {schedule.site.name or schedule.site.coord_str}")
    _section_heading(pdf, heading)
    pdf.ln(1)

    has_date = schedule.departure_date is not None
    dep_dt: Optional[datetime] = None
    if has_date:
        dep_dt = datetime(
            schedule.departure_date.year,
            schedule.departure_date.month,
            schedule.departure_date.day,
            0, 0, 0,
        )

    if has_date:
        cw = [8, 28, 38, 16, 16, 18, 32]
        hdrs = ["Leg", "Description", "Position",
                "Elapsed\n(hrs)", "Elapsed\n(days)", "Cum. NM", "Est. Date/Time (UTC)"]
    else:
        cw = [8, 36, 46, 20, 20, 22, 22]
        hdrs = ["Leg", "Description", "Position",
                "Elapsed\n(hrs)", "Elapsed\n(days)", "Cum. NM", ""]

    # Header
    pdf.set_fill_color(*_NAVY)
    pdf.set_text_color(*_WHITE)
    pdf.set_font("Helvetica", "B", 7)
    row_h = 8
    for h, w in zip(hdrs, cw):
        pdf.multi_cell(w, row_h / 2, h, fill=True, align="C",
                       border=0, new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.ln(row_h)
    pdf.set_text_color(*_BLACK)

    for idx, wp in enumerate(schedule.waypoints):
        fill = _LTGREY if idx % 2 == 0 else (255, 255, 255)
        pdf.set_fill_color(*fill)
        pdf.set_font("Helvetica", "B" if wp.description in ("Departure", "Arrival at site") else "", 7)

        lat_s = f"{abs(wp.lat):.4f}{'N' if wp.lat >= 0 else 'S'}"
        lon_s = f"{abs(wp.lon):.4f}{'E' if wp.lon >= 0 else 'W'}"
        pos   = f"{lat_s}, {lon_s}"

        if has_date and dep_dt is not None:
            est_dt  = dep_dt + timedelta(hours=wp.elapsed_hours)
            date_str = est_dt.strftime("%Y-%m-%d %H:%M")
        else:
            date_str = ""

        vals = [
            str(wp.leg),
            wp.description,
            pos,
            f"{wp.elapsed_hours:.1f}",
            f"{wp.elapsed_days:.3f}",
            f"{wp.cumulative_nm:.1f}",
            date_str,
        ]
        aligns = ["C", "L", "L", "R", "R", "R", "C"]
        row_h2 = 6
        for val, w, align in zip(vals, cw, aligns):
            pdf.cell(w, row_h2, val, fill=True, align=align,
                     new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.ln(row_h2)

    pdf.ln(4)
    _footer_note(pdf,
                 "Great-circle route computed via haversine formula. "
                 "All times UTC. Positions in decimal degrees (+N/-S, +E/-W).")
    if has_date:
        _footer_note(pdf,
                     "Estimated times assume constant speed with no stops. "
                     "Actual ETA will vary with weather and tidal conditions.")


# ---- Page 4: Data Basis and Assumptions -------------------------------------

def _page4(pdf: _GatewayPDF, schedule: VoyageSchedule) -> None:
    pdf.add_page()
    _section_heading(pdf, "Data Basis and Assumptions")
    pdf.ln(2)

    cost = schedule.cost
    _section_heading(pdf, "Voyage Economics Assumptions")
    _kv(pdf, "Cost formula",
        "Charter hire (all vessels) + port fees + fuel")
    _kv(pdf, "Transit speed",       f"{cost.speed_kts:g} knots")
    _kv(pdf, "Transit day formula", "distance NM / speed kts / 24  (fixed)")
    _kv(pdf, "Route",               f"{len(cost.legs)} leg(s), "
                                    f"{cost.total_distance_nm:,.1f} NM total")
    _kv(pdf, "Voyage duration",
        f"{cost.total_transit_days:.2f} transit + {cost.total_onsite_days:.2f} "
        f"on-site = {cost.voyage_days:.2f} days")
    for line in cost.vessels:
        if not line.deployed:
            _kv(pdf, line.name, "Not deployed")
            continue
        basis = ("full voyage" if abs(line.charter_days - cost.voyage_days) < 1e-6
                 else "independent on-hire / off-hire window")
        _kv(pdf, line.name,
            f"${line.charter_rate_usd_day:,.0f}/day x {line.charter_days:.2f} d "
            f"({basis});  fuel {line.total_gal:,.2f} gal at "
            f"${line.fuel_usd_gal:,.2f}/gal")
    _kv(pdf, "Launches per voyage", str(cost.launches))
    pdf.ln(4)

    _section_heading(pdf, "Port Data Source")
    _kv(pdf, "Publication",   "NGA World Port Index (WPI) -- Pub. 150")
    _kv(pdf, "Publisher",     "National Geospatial-Intelligence Agency (NGA)")
    _kv(pdf, "Data fields",
        "Port name, coordinates, harbor size, anchorage depth, fuel availability")
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*_DKGREY)
    pdf.multi_cell(
        0, 5,
        "NOTE: Port depths, fuel availability, and facilities reflect the WPI "
        "publication date and may not represent current conditions. Verify with "
        "port authorities and current Notices to Mariners before operational use.",
        align="J", new_x=XPos.LMARGIN, new_y=YPos.NEXT,
    )
    pdf.set_text_color(*_BLACK)
    pdf.ln(4)

    _section_heading(pdf, "Coordinate Convention")
    _kv(pdf, "+Latitude",  "North  (e.g. 28.5000 N)")
    _kv(pdf, "-Latitude",  "South  (e.g. -33.8688 S)")
    _kv(pdf, "+Longitude", "East   (e.g. 151.2093 E)")
    _kv(pdf, "-Longitude", "West   (e.g. -80.6000 W)")
    _kv(pdf, "Datum",      "WGS-84 decimal degrees throughout")
    pdf.ln(4)

    _section_heading(pdf, "Distance Computation")
    _kv(pdf, "Formula",        "Haversine great-circle distance")
    _kv(pdf, "Earth radius",   "3440.065 nautical miles (mean spherical)")
    _kv(pdf, "Route type",     "Great-circle (shortest surface path)")
    _kv(pdf, "Waypoint method","Intermediate-point interpolation at fixed time intervals")
    pdf.ln(6)

    disclaimer = (
        "This report is for mission planning purposes only. All cost estimates "
        "are approximations based on user-supplied rate inputs and do not "
        "constitute a binding quotation from any service provider. Leg distances "
        "are great-circle and take no account of landmasses, traffic separation "
        "schemes, or canal routing, so actual sailing distances -- and therefore "
        "transit days and charter hire -- may be materially longer. Port "
        "availability, depth, fuel supply, and other facilities should be "
        "verified with port authorities before operational commitment. This "
        "document does not replace professional maritime, launch, or safety "
        "planning."
    )
    _disclaimer_box(pdf, disclaimer, box_h=36)


# ---- Public entry point -----------------------------------------------------

def generate_voyage_report(
    schedule: VoyageSchedule,
    all_port_costs: list[VoyageCostBreakdown],
    analysis_result: Optional[AnalysisResult],
    output_path: str,
    project=None,  # Optional[Project]
) -> str:
    """
    Generate a 5-page voyage & mission planning PDF.

    Parameters
    ----------
    schedule        : VoyageSchedule with site, port, cost, and waypoints set
    all_port_costs  : VoyageCostBreakdown list for all candidate ports (sorted
                      cheapest-first); builds the comparison table on page 3
    analysis_result : Optional AnalysisResult; if provided, adds launch analysis
                      section to page 1
    output_path     : Full .pdf path (legacy) OR output directory — when a
                      directory is given, the filename is generated via naming.py
    project         : Optional Project dataclass; drives filename generation

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
        info = build_report_filename("voyage", schedule.site, project)
        filename = info["filename"]
        sequence_number = info["sequence_number"]
        out = out / filename
    out.parent.mkdir(parents=True, exist_ok=True)

    site_label = schedule.site.name or schedule.site.coord_str
    port_label = schedule.port.port_name

    pdf = _GatewayPDF(title="Voyage & Mission Planning Report")
    pdf.set_author("Seagate Space Corporation -- Gateway Launch Operations")
    pdf.set_title("Voyage & Mission Planning Report")
    pdf.set_subject(f"{site_label} / {port_label}")

    _page1(pdf, schedule, analysis_result)
    _page_route(pdf, schedule)
    _page_breakdown(pdf, schedule)
    _page2(pdf, schedule, all_port_costs)
    _page3(pdf, schedule)
    _page4(pdf, schedule)

    pdf.output(str(out))

    from modules.m5_reports.naming import record_report
    record_report(
        "voyage", filename, str(out.resolve()),
        sequence_number, schedule.site.id,
        project.id if project else None,
    )

    return str(out.resolve())

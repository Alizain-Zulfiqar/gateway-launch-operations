"""
main.py — Gateway Launch Operations application entry point.

Phase 1: CLI mode — run analyses from command line, print results.
Phase 1b: PyQt6 desktop UI (launched when no CLI arguments are given).

Usage:
    python main.py                                    # Launch desktop UI
    python main.py --init                             # Initialize database only
    python main.py --test                             # Run probability engine test
    python main.py --site 28.5,-80.6                 # Quick site analysis (lat,lon)
    python main.py --profile 28.5,-80.6              # 12-month profile table
    python main.py --compare 34.2,-66.5 22.4,-69.1   # Side-by-side site comparison
    python main.py --report 28.5,-80.6               # Generate PDF report (current month)
    python main.py --ports 28.5,-80.6                # 5 nearest qualifying ports
    python main.py --voyage 28.5,-80.6               # Voyage cost comparison
    python main.py --voyage-report 28.5,-80.6 PORT_ID # Generate voyage PDF
    python main.py --compare-report 34.2,-66.5 22.4,-69.1 # Multi-site comparison PDF
"""
import argparse
import sys

# Ensure UTF-8 output on Windows (Unicode box-drawing and verdict symbols)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from core.runtime_paths import bootstrap_runtime

bootstrap_runtime()

from core.database import init_db
from core.models import Site, Vehicle, Platform
from core.utils import format_coord, lat_to_band, band_label, fmt_prob
from modules.m3_probability.engine import (
    compute_probability, compute_annual_profile,
    best_launch_months, annual_go_fraction, summary_text
)
from config import GATEWAY_PLATFORMS

# ── Shared constants ──────────────────────────────────────────────────────────

MO = ["Jan","Feb","Mar","Apr","May","Jun",
      "Jul","Aug","Sep","Oct","Nov","Dec"]

VERDICT_SYM = {"GO": "✓", "MARGINAL": "~", "NO-GO": "✗"}


def _default_vehicle() -> Vehicle:
    return Vehicle(
        name="Firefly Alpha",
        vehicle_class="slv_orb",
        recovery_mode="expendable",
        max_wind_kts=18.0,
        max_gust_kts=25.0,
        max_hs_m=1.5,
        max_swell_ht_m=2.0,
        max_swell_period_s=12.0,
        max_wind_dir_tolerance_deg=30.0,
        max_sea_dir_tolerance_deg=60.0,
        max_swell_dir_tolerance_deg=60.0,
    )


def _default_platform() -> Platform:
    return Platform(name="Gateway X", hull_type="semisub", hull_motion_factor=0.78)


def _parse_latlon(s: str) -> tuple[float, float]:
    """Parse 'LAT,LON' string into (float, float). Raises ValueError on bad input."""
    parts = s.split(",")
    if len(parts) != 2:
        raise ValueError(f"Expected LAT,LON, got {repr(s)}")
    return float(parts[0]), float(parts[1])


# ── Banner ────────────────────────────────────────────────────────────────────

def print_banner():
    print("=" * 60)
    print("  GATEWAY LAUNCH OPERATIONS")
    print("  Site Analysis & Mission Planning")
    print("  Seagate Space Corporation")
    print("=" * 60)
    print()


# ── --site (existing quick analysis) ─────────────────────────────────────────

def quick_analysis(lat: float, lon: float):
    """Run a quick annual profile for a site with default vehicle/platform."""
    site     = Site(lat=lat, lon=lon, name=f"Quick analysis {format_coord(lat, lon)}")
    vehicle  = _default_vehicle()
    platform = _default_platform()

    print(f"\nSite:     {site.coord_str}")
    print(f"Band:     {band_label(lat_to_band(lat))}")
    print(f"Vehicle:  {vehicle.name} ({vehicle.vehicle_class})")
    print(f"Platform: {platform.name} ({platform.hull_type}, "
          f"motion factor {platform.hull_motion_factor})")
    print(f"Era:      1960–2024 (ICOADS modern era)")
    print()

    profile = compute_annual_profile(site, vehicle, platform)

    print(f"{'Month':<6} {'Prob':>6} {'Verdict':<10} {'Limiting':<12}")
    print("-" * 40)
    for month, result in profile.items():
        sym = VERDICT_SYM[result.verdict]
        print(f"{MO[month-1]:<6} {result.pct:>5}%  "
              f"{sym} {result.verdict:<9} {result.limiting_param}")

    go_frac = annual_go_fraction(profile)
    best    = best_launch_months(profile)
    print()
    print(f"Annual GO fraction:  {round(go_frac * 100)}% of months ≥70% probability")
    if best:
        best_mo, best_prob = best[0]
        print(f"Best launch month:   {MO[best_mo-1]} ({round(best_prob*100)}%)")
    else:
        print("Best launch month:   None meet 70% GO threshold")


# ── --profile ─────────────────────────────────────────────────────────────────

def run_profile(lat: float, lon: float):
    """
    Print a formatted 12-month profile table with verdict symbols,
    best launch months, and annual GO fraction.
    """
    site     = Site(lat=lat, lon=lon, name=format_coord(lat, lon))
    vehicle  = _default_vehicle()
    platform = _default_platform()

    print(f"\n{'─'*55}")
    print(f"  ANNUAL LAUNCH WINDOW PROFILE")
    print(f"  Site     : {site.coord_str}  [{band_label(lat_to_band(lat))}]")
    print(f"  Vehicle  : {vehicle.name}  ({vehicle.vehicle_class})")
    print(f"  Platform : {platform.name}  (hull factor {platform.hull_motion_factor})")
    print(f"  Era      : 1960–2024")
    print(f"{'─'*55}")

    profile = compute_annual_profile(site, vehicle, platform)

    # Table header
    print(f"\n  {'Month':<5} {'Prob':>5}  {'':2} {'Verdict':<9} {'Limiting param'}")
    print(f"  {'─'*5} {'─'*5}  {'─'*2} {'─'*9} {'─'*14}")

    for month, result in profile.items():
        sym = VERDICT_SYM[result.verdict]
        # Colour-code verdict: simple prefix indicators in plain text
        bar = "▓" * (result.pct // 10)
        print(f"  {MO[month-1]:<5} {result.pct:>4}%  {sym}  {result.verdict:<9} {result.limiting_param}")

    # Summary
    go_frac = annual_go_fraction(profile)
    best    = best_launch_months(profile)

    print(f"\n  Annual GO fraction  : {round(go_frac * 100)}%  "
          f"({sum(1 for r in profile.values() if r.verdict=='GO')}/12 months ≥70%)")

    if best:
        print(f"\n  Best launch months (≥70% GO threshold):")
        for rank, (m, prob) in enumerate(best, 1):
            print(f"    {rank}. {MO[m-1]:<5} — {round(prob*100)}%  {VERDICT_SYM['GO']}")
    else:
        print(f"\n  No months meet the 70% GO threshold at this site.")

    print()


# ── --compare ─────────────────────────────────────────────────────────────────

def run_compare(coords: list[tuple[float, float]]):
    """
    Side-by-side monthly comparison for up to 7 sites.
    Marks the best site per month with *.
    Ranks sites by annual GO fraction in summary.
    """
    if len(coords) > 7:
        print("Warning: --compare accepts up to 7 sites. Ignoring extras.")
        coords = coords[:7]

    vehicle  = _default_vehicle()
    platform = _default_platform()

    sites    = [Site(lat=lat, lon=lon, name=format_coord(lat, lon))
                for lat, lon in coords]
    profiles = [compute_annual_profile(s, vehicle, platform) for s in sites]
    n        = len(sites)

    # ── Header ────────────────────────────────────────────────────────────────
    col_w = 8   # width per site column
    label_w = 6

    print(f"\n{'─'*70}")
    print(f"  SITE COMPARISON  —  {vehicle.name} on {platform.name}")
    print(f"{'─'*70}")
    print()

    # Site index legend
    for i, site in enumerate(sites):
        go_frac = annual_go_fraction(profiles[i])
        band    = band_label(lat_to_band(site.lat))
        print(f"  S{i+1}  {site.coord_str:<26}  [{band}]")
    print()

    # ── Monthly table ──────────────────────────────────────────────────────────
    # Header row
    hdr = f"  {'Month':<{label_w}}"
    for i in range(n):
        hdr += f"{'S'+str(i+1):>{col_w}}"
    print(hdr)
    print("  " + "─" * (label_w + col_w * n))

    for month in range(1, 13):
        probs   = [profiles[i][month].overall_prob for i in range(n)]
        best_i  = probs.index(max(probs))
        row     = f"  {MO[month-1]:<{label_w}}"
        for i, prob in enumerate(probs):
            pct_str = f"{round(prob*100)}%"
            if i == best_i:
                pct_str += "*"
            row += f"{pct_str:>{col_w}}"
        print(row)

    # ── Summary: rank by GO fraction ──────────────────────────────────────────
    go_fracs = [(i, annual_go_fraction(profiles[i])) for i in range(n)]
    go_fracs.sort(key=lambda x: x[1], reverse=True)

    print()
    print(f"  {'─'*55}")
    print(f"  RANKING by annual GO fraction (months ≥70%)")
    print(f"  {'─'*55}")
    print(f"  {'Rank':<5} {'Site':<6} {'Coord':<28} {'GO%':>5}  {'GO months':>10}")
    print(f"  {'─'*5} {'─'*5} {'─'*27} {'─'*5}  {'─'*10}")

    for rank, (i, gf) in enumerate(go_fracs, 1):
        site     = sites[i]
        go_months = sum(1 for r in profiles[i].values() if r.verdict == "GO")
        print(f"  {rank:<5} S{i+1:<5} {site.coord_str:<28} "
              f"{round(gf*100):>4}%  {go_months}/12 months")

    # Best overall
    best_rank_i, best_gf = go_fracs[0]
    print()
    print(f"  Best site overall: S{best_rank_i+1}  {sites[best_rank_i].coord_str}"
          f"  ({round(best_gf*100)}% annual GO)")
    print()


# ── --compare-report ─────────────────────────────────────────────────────────

def run_compare_report(coords: list[tuple[float, float]]):
    """Generate a multi-site comparison PDF for up to 7 sites."""
    from datetime import datetime, timezone
    from pathlib import Path
    from modules.m5_reports.comparison_pdf import generate_comparison_report

    if len(coords) > 7:
        print("Warning: --compare-report accepts up to 7 sites. Ignoring extras.")
        coords = coords[:7]

    vehicle  = _default_vehicle()
    platform = _default_platform()

    sites    = [Site(lat=lat, lon=lon, name=format_coord(lat, lon))
                for lat, lon in coords]

    print(f"\nRunning 12-month profile for {len(sites)} sites...")
    profiles = []
    for site in sites:
        print(f"  {site.coord_str}...")
        profiles.append(compute_annual_profile(site, vehicle, platform))

    site_results = list(zip(sites, profiles))

    reports_dir = Path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = str(reports_dir / f"comparison_{len(sites)}sites_{ts}.pdf")

    saved = generate_comparison_report(site_results, vehicle, platform, out_path)
    print(f"Comparison report saved: {saved}")


# ── --ports ──────────────────────────────────────────────────────────────────

def run_ports(lat: float, lon: float):
    """Print the 5 nearest qualifying ports to a site."""
    from modules.m4_ports.proximity import nearest_ports

    site  = Site(lat=lat, lon=lon, name=format_coord(lat, lon))
    ports = nearest_ports(site, n=5, min_depth_m=10.0, require_fuel=True)

    if not ports:
        print("\nNo qualifying ports found in database.")
        print("Run: python scripts/import_wpi.py  (after saving data/wpi.csv)")
        return

    print(f"\nNearest qualifying ports to {site.coord_str}")
    print(f"  Filter: depth_anch >= 10 m, fuel oil available")
    print()

    hdr = f"  {'#':<3} {'Port name':<30} {'Country':<16} {'Dist (NM)':>9}  {'Bearing':>7}  {'Size':<5}  {'Depth':>7}  {'Fuel':<5}"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    for i, p in enumerate(ports, 1):
        depth_str = f"{p.depth_anch_m:.1f} m" if p.depth_anch_m else "  --  "
        fuel_str  = "Y" if p.fuel_oil else "N"
        size_str  = p.harbor_size or "-"
        print(f"  {i:<3} {p.port_name[:29]:<30} {p.country[:15]:<16} "
              f"{p.distance_nm:>8.1f}  {p.bearing_deg:>6.1f}°  {size_str:<5}  "
              f"{depth_str:>7}  {fuel_str}")
    print()


# ── --voyage ─────────────────────────────────────────────────────────────────

def run_voyage(lat: float, lon: float):
    """Find 5 nearest ports and print a voyage cost comparison table."""
    from modules.m4_ports.proximity import nearest_ports
    from modules.m4_ports.voyage import compare_port_options, load_params

    site  = Site(lat=lat, lon=lon, name=format_coord(lat, lon))
    ports = nearest_ports(site, n=5, min_depth_m=10.0, require_fuel=True)

    if not ports:
        print("\nNo qualifying ports found. Run: python scripts/import_wpi.py")
        return

    params = load_params()
    costs  = compare_port_options(site, ports, params=params)

    W = 82
    print(f"\n  PORT VOYAGE ECONOMICS  --  {site.coord_str}")
    print("  " + "=" * W)
    print(f"  {'Rank':<5} {'Port':<26} {'Country':<14} {'Dist':>8}  "
          f"{'Voyage':>9}  {'Total':>12}  {'Per launch':>12}")
    print("  " + "-" * W)
    for rank, vc in enumerate(costs, 1):
        print(
            f"  {rank:<5} {vc.port.port_name[:25]:<26} {vc.port.country[:13]:<14} "
            f"{vc.total_distance_nm:>5,.0f} NM  "
            f"{vc.voyage_days:>6.2f} d  "
            f"${vc.total_usd:>11,.0f}  ${vc.cost_per_launch():>11,.0f}"
        )
    print("  " + "=" * W)
    print(f"  Total = charter hire + port fees + fuel.  "
          f"Speed: {params.speed_kts:g} kts.  Launches: {params.launches}.")
    print("  Adjust every rate on the Ports page (Voyage Cost Settings).")
    print()


# ── --voyage-report ──────────────────────────────────────────────────────────

def run_voyage_report(lat: float, lon: float, port_id: int):
    """Generate a voyage PDF report for a site + port combination."""
    from datetime import datetime, timezone
    from pathlib import Path
    from core.database import get_connection
    from core.models import Port as PortModel, VoyageSchedule
    from modules.m4_ports.proximity import nearest_ports
    from modules.m4_ports.voyage import (
        calculate_voyage_cost, generate_waypoints, compare_port_options,
        load_params,
    )
    from modules.m5_reports.voyage_pdf import generate_voyage_report

    # Load selected port from DB
    conn = get_connection()
    row = conn.execute(
        "SELECT id, wpi_number, port_name, country, lat, lon, "
        "harbor_size, max_vessel_size, depth_anch_m, fuel_oil, diesel "
        "FROM ports WHERE id = ?", (port_id,)
    ).fetchone()
    conn.close()

    if row is None:
        print(f"ERROR: No port found with id={port_id}. "
              f"Run --ports {lat},{lon} to list valid port IDs.")
        sys.exit(1)

    selected_port = PortModel(
        id           = row["id"],
        wpi_number   = row["wpi_number"] or "",
        port_name    = row["port_name"],
        country      = row["country"] or "",
        lat          = row["lat"],
        lon          = row["lon"],
        harbor_size  = row["harbor_size"] or "",
        max_vessel_size = row["max_vessel_size"] or "",
        depth_anch_m = row["depth_anch_m"],
        fuel_oil     = bool(row["fuel_oil"]),
        diesel       = bool(row["diesel"]),
    )

    site = Site(lat=lat, lon=lon, name=format_coord(lat, lon))

    params = load_params()

    # Comparison table: 5 nearest qualifying ports
    nearby = nearest_ports(site, n=5, min_depth_m=10.0, require_fuel=True)
    all_costs = compare_port_options(site, nearby, params=params)

    # Ensure selected port is in comparison list (add if not nearest 5)
    if not any(vc.port.id == port_id for vc in all_costs):
        extra = calculate_voyage_cost(site, selected_port, params=params)
        all_costs.append(extra)
        all_costs.sort(key=lambda vc: vc.total_usd)

    # Build schedule for selected port
    cost = calculate_voyage_cost(site, selected_port, params=params)
    waypoints = generate_waypoints(site, selected_port,
                                   platform_speed_kts=params.speed_kts)
    schedule = VoyageSchedule(
        site=site, port=selected_port, cost=cost, waypoints=waypoints
    )

    # Output path
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    site_slug = f"{abs(lat):.1f}{'N' if lat >= 0 else 'S'}_{abs(lon):.1f}{'E' if lon >= 0 else 'W'}"
    out_path = Path("reports") / f"voyage_{site_slug}_port{port_id}_{ts}.pdf"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    saved = generate_voyage_report(
        schedule      = schedule,
        all_port_costs= all_costs,
        analysis_result= None,   # no analysis; use --report separately
        output_path   = str(out_path),
    )
    print(f"Voyage report saved: {saved}")


# ── --report ─────────────────────────────────────────────────────────────────

def run_report(lat: float, lon: float):
    """
    Run a probability analysis for the current calendar month and write a PDF
    report to ./reports/gateway_report_<timestamp>.pdf.
    """
    from datetime import datetime, timezone
    from pathlib import Path
    from modules.m5_reports.pdf_report import generate_analysis_report

    site     = Site(lat=lat, lon=lon, name=f"Site {format_coord(lat, lon)}")
    vehicle  = _default_vehicle()
    platform = _default_platform()
    month    = datetime.now(timezone.utc).month

    print(f"\nGenerating report for {site.coord_str}  (month={MO[month-1]}) ...")
    result = compute_probability(site, vehicle, platform, month=month)

    reports_dir = Path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = str(reports_dir / f"gateway_report_{ts}.pdf")

    saved = generate_analysis_report(result, output_path)
    print(f"Report saved: {saved}")
    print(f"Overall:  {result.pct}%  {result.verdict}  (limiting: {result.limiting_param})")


# ── --test ────────────────────────────────────────────────────────────────────

def run_test():
    print("Running probability engine test...\n")
    site = Site(lat=28.5, lon=-80.6, name="Test — Cape Canaveral area")
    v = Vehicle(name="Firefly Alpha", vehicle_class="slv_orb",
                recovery_mode="expendable",
                max_wind_kts=18, max_gust_kts=25, max_hs_m=1.5,
                max_swell_ht_m=2.0, max_swell_period_s=12)
    p = Platform("Gateway X", "semisub", 0.78)
    r = compute_probability(site, v, p, month=6)
    print(summary_text(r))
    print(f"\nParam probs: {
        {k: f'{round(pv*100)}%' for k, pv in r.param_probs.items()}
    }")


# ── Interactive CLI ───────────────────────────────────────────────────────────

def interactive_cli():
    print("Enter site coordinates (+lat=N, -lat=S, +lon=E, -lon=W)")
    try:
        lat = float(input("  Latitude (decimal degrees): ").strip())
        lon = float(input("  Longitude (decimal degrees): ").strip())
        quick_analysis(lat, lon)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nExiting.")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Gateway Launch Operations — Site Analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --profile 28.5,-80.6
  python main.py --compare 34.2,-66.5 22.4,-69.1 32.6,-61.1
        """,
    )
    parser.add_argument("--init",    action="store_true",
                        help="Initialize database only")
    parser.add_argument("--test",    action="store_true",
                        help="Run probability engine test")
    parser.add_argument("--site",    type=str, metavar="LAT,LON",
                        help="Quick site analysis (e.g. 28.5,-80.6)")
    parser.add_argument("--profile", type=str, metavar="LAT,LON",
                        help="12-month launch window profile")
    parser.add_argument("--compare", type=str, nargs="+", metavar="LAT,LON",
                        help="Compare up to 7 sites side-by-side")
    parser.add_argument("--report", type=str, metavar="LAT,LON",
                        help="Generate PDF report for site (current month)")
    parser.add_argument("--ports", type=str, metavar="LAT,LON",
                        help="5 nearest qualifying ports (fuel + depth >= 10 m)")
    parser.add_argument("--voyage", type=str, metavar="LAT,LON",
                        help="Voyage cost comparison to 5 nearest ports")
    parser.add_argument("--voyage-report", type=str, nargs=2,
                        metavar=("LAT,LON", "PORT_ID"),
                        help="Generate voyage PDF for site + port DB id")
    parser.add_argument("--compare-report", type=str, nargs="+", metavar="LAT,LON",
                        help="Multi-site comparison PDF (2-7 sites)")
    args = parser.parse_args()

    print_banner()
    init_db()

    if args.init:
        print("Database initialized.")
        return

    if args.test:
        run_test()
        return

    if args.site:
        try:
            lat, lon = _parse_latlon(args.site)
            quick_analysis(lat, lon)
        except (ValueError, IndexError) as e:
            print(f"Error parsing --site: {e}")
            print("Format: --site LAT,LON  (e.g. --site 28.5,-80.6)")
            sys.exit(1)
        return

    if args.profile:
        try:
            lat, lon = _parse_latlon(args.profile)
            run_profile(lat, lon)
        except ValueError as e:
            print(f"Error parsing --profile: {e}")
            print("Format: --profile LAT,LON  (e.g. --profile 28.5,-80.6)")
            sys.exit(1)
        return

    if args.compare:
        try:
            coords = [_parse_latlon(s) for s in args.compare]
        except ValueError as e:
            print(f"Error parsing --compare: {e}")
            print("Format: --compare LAT1,LON1 LAT2,LON2 ...")
            sys.exit(1)
        if len(coords) < 2:
            print("Error: --compare requires at least 2 sites.")
            sys.exit(1)
        run_compare(coords)
        return

    if args.voyage:
        try:
            lat, lon = _parse_latlon(args.voyage)
            run_voyage(lat, lon)
        except ValueError as e:
            print(f"Error parsing --voyage: {e}")
            sys.exit(1)
        return

    if args.ports:
        try:
            lat, lon = _parse_latlon(args.ports)
            run_ports(lat, lon)
        except ValueError as e:
            print(f"Error parsing --ports: {e}")
            sys.exit(1)
        return

    if args.voyage_report:
        try:
            lat, lon = _parse_latlon(args.voyage_report[0])
            port_id  = int(args.voyage_report[1])
        except (ValueError, IndexError) as e:
            print(f"Error: {e}")
            print("Format: --voyage-report LAT,LON PORT_ID")
            sys.exit(1)
        run_voyage_report(lat, lon, port_id)
        return

    if args.report:
        try:
            lat, lon = _parse_latlon(args.report)
            run_report(lat, lon)
        except ValueError as e:
            print(f"Error parsing --report: {e}")
            print("Format: --report LAT,LON  (e.g. --report 28.5,-80.6)")
            sys.exit(1)
        return

    if args.compare_report:
        try:
            coords = [_parse_latlon(s) for s in args.compare_report]
        except ValueError as e:
            print(f"Error parsing --compare-report: {e}")
            print("Format: --compare-report LAT1,LON1 LAT2,LON2 ...")
            sys.exit(1)
        if len(coords) < 2:
            print("Error: --compare-report requires at least 2 sites.")
            sys.exit(1)
        run_compare_report(coords)
        return

    # Default: launch desktop UI
    from ui.main_window import launch_ui
    launch_ui()


if __name__ == "__main__":
    main()

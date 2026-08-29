"""
modules/m5_reports/analysis_chart_pages.py — Per-chart PNGs + conclusions for PDF.

Renders each Analysis decision chart (1–12) as its own Agg figure (not a
screenshot of the on-screen stack) and attaches a short 2–3 sentence
conclusion from the same profile / climatology / operability data.

Intentionally does NOT import ui.widgets.analysis_charts (that module forces
QtAgg and breaks headless PDF export).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.colors
import matplotlib.pyplot as plt  # noqa: F401 — registers Agg
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from config import DEFAULT_THRESHOLDS

# Palette / thresholds mirrored from ui/widgets/analysis_charts.py
_BG = "#1a2233"
_PANEL = "#0f1923"
_GRID = "#374151"
_TEXT = "#e2e8f0"
_MUTED = "#94a3b8"
_ACCENT = "#2563eb"
_GO = "#22c55e"
_MARG = "#f59e0b"
_NOGO = "#ef4444"
_REF_COLOR = "#38bdf8"


def _go_pct() -> float:
    from core.verdict_thresholds import go_pct_threshold
    return go_pct_threshold()


def _marg_pct() -> float:
    from core.verdict_thresholds import marginal_pct_threshold
    return marginal_pct_threshold()


_REF_WIND_KTS = float(DEFAULT_THRESHOLDS["ws"])
_REF_HS_M = float(DEFAULT_THRESHOLDS["sh"])
_M_TO_FT = 3.28084
_OPER_PCT_VMIN = 30.0
_OPER_PCT_VMAX = 100.0

_MO = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_PARAM_LABEL = {
    "ws": "Wind speed", "wg": "Wind gust", "sh": "Sea Hs",
    "swh": "Swell height", "swp": "Swell period",
    "wdV": "Wind dir", "sdV": "Sea dir", "swdV": "Swell dir",
}
_SS_BINS = [
    ("SS2", 0.0, 0.5, "#bfdbfe"),
    ("SS3", 0.5, 1.25, "#60a5fa"),
    ("SS4", 1.25, 2.5, "#3b82f6"),
    ("SS5+", 2.5, float("inf"), "#1e3a8a"),
]
_SS_CV = 0.5
_PROB_CMAP = matplotlib.colors.LinearSegmentedColormap.from_list(
    "gateway_prob", ["#7f1d1d", "#b45309", "#a16207", "#4d7c0f", "#15803d"]
)
_OPER_CMAP = matplotlib.colors.LinearSegmentedColormap.from_list(
    "gateway_oper", ["#fef9c3", "#bef264", "#16a34a", "#14532d"]
)


@dataclass
class ChartPage:
    number: int
    title: str
    path: str
    conclusion: str


def _style_ax(ax) -> None:
    ax.set_facecolor(_BG)
    for spine in ax.spines.values():
        spine.set_color(_GRID)
    ax.tick_params(colors=_MUTED, labelsize=8)
    ax.title.set_color(_TEXT)
    ax.xaxis.label.set_color(_MUTED)
    ax.yaxis.label.set_color(_MUTED)


def _verdict_color(prob: float) -> str:
    from core.verdict_thresholds import get_go_threshold, get_marginal_threshold
    if prob >= get_go_threshold():
        return _GO
    if prob >= get_marginal_threshold():
        return _MARG
    return _NOGO


def combined_hs(sh: float, swh: float) -> float:
    return (float(sh) ** 2 + float(swh) ** 2) ** 0.5


def _sea_state_composition(hs_mean: float) -> list[float]:
    if hs_mean <= 0:
        return [0.0 for _ in _SS_BINS]
    sigma = math.sqrt(math.log(1.0 + _SS_CV ** 2))
    mu = math.log(hs_mean) - 0.5 * sigma ** 2

    def cdf(x: float) -> float:
        if x == float("inf"):
            return 1.0
        if x <= 0:
            return 0.0
        return 0.5 * (1.0 + math.erf((math.log(x) - mu) / (sigma * math.sqrt(2.0))))

    return [(cdf(hi) - cdf(lo)) * 100.0 for _, lo, hi, _c in _SS_BINS]


def _active_params(profile: dict) -> list[str]:
    first = next(iter(profile.values()))
    active = getattr(first, "active_params", None) or set()
    mag = ["ws", "wg", "sh", "swh", "swp"]
    return [p for p in mag if p in active] or mag


def _means(profile: dict, param: str) -> list[float]:
    out = []
    for m in range(1, 13):
        em = getattr(profile[m], "effective_means", {}) or {}
        out.append(float(em.get(param) or 0.0))
    return out


def _thr(profile: dict, param: str) -> Optional[float]:
    first = next(iter(profile.values()))
    th = getattr(first, "thresholds", {}) or {}
    v = th.get(param)
    return float(v) if v else None


def _best_worst(values: Sequence[float]) -> tuple[int, int]:
    arr = np.asarray(values, dtype=float)
    return int(np.nanargmax(arr)), int(np.nanargmin(arr))


def _month_list(indices: Sequence[int]) -> str:
    names = [_MO[i] for i in indices]
    if not names:
        return "none"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def _new_fig(width: float = 8.2, height: float = 4.4):
    fig = Figure(figsize=(width, height), facecolor=_PANEL)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    fig.subplots_adjust(left=0.10, right=0.96, top=0.88, bottom=0.14)
    _style_ax(ax)
    return fig, ax


def _save(fig, path: Path, dpi: int = 150) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        path, dpi=dpi, facecolor=fig.get_facecolor(),
        edgecolor="none", bbox_inches="tight", pad_inches=0.2,
    )
    plt.close(fig)
    return str(path.resolve())


def _draw_operability_heatmap(ax, matrix, years, *, fmt, vmin, vmax, cbar_label, classify_fn):
    from modules.m2_weather.operability import classify_pct

    if classify_fn is None:
        classify_fn = classify_pct
    data = np.array(matrix, dtype=float)
    masked = np.ma.masked_invalid(data)
    im = ax.imshow(masked, aspect="auto", cmap=_OPER_CMAP, vmin=vmin, vmax=vmax,
                   origin="upper")
    ax.set_xticks(range(len(years)))
    ax.set_xticklabels([str(y) for y in years], rotation=45, ha="right", fontsize=7)
    ax.set_yticks(range(12))
    ax.set_yticklabels(_MO)
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            v = data[i, j]
            if np.isnan(v):
                continue
            ax.text(j, i, format(v, fmt), ha="center", va="center", fontsize=6,
                    color="#0f172a")
    cbar = ax.figure.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label(cbar_label, color=_MUTED, fontsize=8)
    cbar.ax.tick_params(colors=_MUTED, labelsize=7)


# ── Conclusions ──────────────────────────────────────────────────────────────

def _conclude_operating(overall: list[float]) -> str:
    go_line = _go_pct()
    marg_line = _marg_pct()
    best_i, worst_i = _best_worst(overall)
    go = [i for i, v in enumerate(overall) if v >= go_line]
    marg = [i for i, v in enumerate(overall) if marg_line <= v < go_line]
    denied = [i for i, v in enumerate(overall) if v < marg_line]
    return (
        f"{_month_list(go) if go else 'No months'} reach GO (≥{go_line:.0f}% of days meeting all "
        f"optimal criteria). {_month_list(marg) if marg else 'No months'} fall in the "
        f"marginal band ({marg_line:.0f}–{go_line:.0f}%), and "
        f"{_month_list(denied) if denied else 'no months'} are denied (<{marg_line:.0f}%). "
        f"{_MO[best_i]} is the strongest month at {overall[best_i]:.0f}%, while "
        f"{_MO[worst_i]} is weakest at {overall[worst_i]:.0f}% — prioritise launch "
        f"planning around the higher-scoring months under the current optimal limits."
    )


def _conclude_hs(hs_ft: list[float], limit_ft: float) -> str:
    calm_i, rough_i = int(np.nanargmin(hs_ft)), int(np.nanargmax(hs_ft))
    over = [i for i, v in enumerate(hs_ft) if v > limit_ft]
    over_txt = (
        f"Months above the {limit_ft:.1f} ft reference: {_month_list(over)}."
        if over else
        f"No month's mean exceeds the {limit_ft:.1f} ft reference line."
    )
    return (
        f"Mean combined significant wave height is lowest in {_MO[calm_i]} "
        f"({hs_ft[calm_i]:.1f} ft) and highest in {_MO[rough_i]} ({hs_ft[rough_i]:.1f} ft). "
        f"{over_txt} "
        f"Calmer months reduce sea-state risk for deck and launch operations; "
        f"rougher months need more schedule contingency."
    )


def _conclude_wind(ws: list[float], limit: float) -> str:
    calm_i, windy_i = int(np.nanargmin(ws)), int(np.nanargmax(ws))
    over = [i for i, v in enumerate(ws) if v > limit]
    over_txt = (
        f"Mean wind exceeds the {limit:.0f} kt reference in {_month_list(over)}."
        if over else
        f"No month's mean wind exceeds the {limit:.0f} kt reference."
    )
    return (
        f"Average 10 m wind is lightest in {_MO[calm_i]} ({ws[calm_i]:.1f} kt) and "
        f"strongest in {_MO[windy_i]} ({ws[windy_i]:.1f} kt). "
        f"{over_txt} "
        f"Windier months raise handling and hold-down risk even when seas are moderate."
    )


def _conclude_sea_state(hs: list[float]) -> str:
    ss = [_sea_state_composition(h) for h in hs]
    ss5 = [row[3] for row in ss]
    ss2 = [row[0] for row in ss]
    rough_i = int(np.nanargmax(ss5))
    calm_i = int(np.nanargmax(ss2))
    return (
        f"Modelled sea-state composition shows the largest SS5+ share in "
        f"{_MO[rough_i]} (~{ss5[rough_i]:.0f}% of time) and the most SS2 time in "
        f"{_MO[calm_i]} (~{ss2[calm_i]:.0f}%). "
        f"Months dominated by SS4-SS5+ imply a harsher operating envelope for "
        f"hull motion and deck work. "
        f"Prefer months with a larger SS2-SS3 fraction when scheduling sensitive evolutions."
    )


def _conclude_gust(ratio: list[float]) -> str:
    peak_i = int(np.nanargmax(ratio))
    turb = [i for i, r in enumerate(ratio) if r >= 1.5]
    turb_txt = (
        f"Turbulent months (≥1.5): {_month_list(turb)}."
        if turb else
        "No month exceeds the 1.5 turbulence threshold on the monthly-mean ratio."
    )
    return (
        f"Gust-to-wind ratio peaks in {_MO[peak_i]} at {ratio[peak_i]:.2f}. "
        f"{turb_txt} "
        f"Elevated gust ratios increase structural-load and crane/hold-down risk "
        f"beyond what mean wind alone indicates."
    )


def _conclude_dir(sdV: list[float], swdV: list[float], tol: Optional[float]) -> str:
    sea_peak = int(np.nanargmax(sdV))
    swell_peak = int(np.nanargmax(swdV))
    tol_txt = f" against a {tol:.0f}° tolerance" if tol else ""
    return (
        f"Sea-direction spread is widest in {_MO[sea_peak]} ({sdV[sea_peak]:.0f}°) and "
        f"swell-direction spread in {_MO[swell_peak]} ({swdV[swell_peak]:.0f}°){tol_txt}. "
        f"Large directional spreads reduce heading consistency for weather-vaning and "
        f"azimuth-sensitive launch windows. "
        f"Months with tighter spreads are preferable when direction limits are active."
    )


def _conclude_swell_scatter(swp, swh, thr_p, thr_h) -> str:
    risk = []
    for i, (p, h) in enumerate(zip(swp, swh)):
        if (thr_p is not None and p > thr_p) or (thr_h is not None and h > thr_h):
            risk.append(i)
    long_i = int(np.nanargmax(swp))
    high_i = int(np.nanargmax(swh))
    risk_txt = (
        f"Months outside swell limits: {_month_list(risk)}."
        if risk else
        "All months stay inside the swell period/height limit lines where shown."
    )
    return (
        f"Longest mean swell period is in {_MO[long_i]} ({swp[long_i]:.1f} s); "
        f"highest mean swell height is in {_MO[high_i]} ({swh[high_i]:.2f} m). "
        f"{risk_txt} "
        f"Long-period, high swell combinations raise resonance and vessel-motion risk "
        f"for floating platforms."
    )


def _conclude_steepness(steep: list[float]) -> str:
    peak_i = int(np.nanargmax(steep))
    steep_m = [i for i, v in enumerate(steep) if v >= 0.04]
    steep_txt = (
        f"Steep months (≥0.04): {_month_list(steep_m)}."
        if steep_m else
        "No month exceeds the 0.04 steepness threshold on monthly means."
    )
    return (
        f"Swell steepness (H/L) is greatest in {_MO[peak_i]} ({steep[peak_i]:.3f}). "
        f"{steep_txt} "
        f"Steeper swell increases breaking-seas and slamming risk during transit and "
        f"on-station evolutions."
    )


def _conclude_dual(joint: list[float], rank_str: str) -> str:
    best_i, worst_i = _best_worst(joint)
    go = [i for i, v in enumerate(joint) if v >= _go_pct()]
    return (
        f"Under the standard wind/Hs dual check, {_MO[best_i]} scores highest "
        f"({joint[best_i]:.0f}%) and {_MO[worst_i]} lowest ({joint[worst_i]:.0f}%). "
        f"Top months: {rank_str}. "
        f"{len(go)} month(s) clear the {_go_pct():.0f}% dual-criteria band — use this as a "
        f"reference operability view alongside the full multi-parameter Chart 1 verdict."
    )


def _conclude_param_heatmap(
    profile: dict,
    params: list[str],
    param_fractions: dict | None = None,
) -> str:
    if param_fractions:
        means = {}
        for p in params:
            vals = [
                float(param_fractions.get(m, {}).get(p, 0.0))
                for m in range(1, 13)
                if param_fractions.get(m, {}).get(p) is not None
            ]
            means[p] = float(np.mean(vals)) if vals else 0.0
        metric = "estimated marginal criterion-met %"
    else:
        means = {
            p: float(np.mean([profile[m].param_probs.get(p, 0.0) for m in range(1, 13)]))
            for p in params
        }
        metric = "weighted engine probability"
    weak = min(means, key=means.get)
    strong = max(means, key=means.get)
    overall = [profile[m].overall_prob * 100 for m in range(1, 13)]
    best_i, worst_i = _best_worst(overall)
    return (
        f"Across the year, {_PARAM_LABEL.get(weak, weak)} is the weakest "
        f"marginal contributor on average ({means[weak]:.0f}% {metric}), while "
        f"{_PARAM_LABEL.get(strong, strong)} is strongest ({means[strong]:.0f}%). "
        f"{_MO[best_i]} shows the highest joint operability (Chart 1); "
        f"{_MO[worst_i]} the lowest. "
        f"Chart 1 combines all active rows via independence — a high single-parameter "
        f"row does not guarantee a high joint month."
    )


def _conclude_oper_pct(operability) -> str:
    if not operability or not operability.years or operability.months_cached <= 0:
        return (
            "Operability heatmap data were not available for this run. "
            "Re-run Historical analysis after the last-10-year ERA5 cache is complete "
            "to interpret inter-annual variability."
        )
    month_avgs = []
    for row in operability.pct_both:
        vals = [v for v in row if v is not None]
        month_avgs.append(float(np.mean(vals)) if vals else float("nan"))
    if np.all(np.isnan(month_avgs)):
        return (
            "Insufficient cached months to summarise inter-annual operability. "
            "Download or re-fetch ERA5 for the last 10 years and export again."
        )
    best_i = int(np.nanargmax(month_avgs))
    worst_i = int(np.nanargmin(month_avgs))
    yrs = f"{operability.years[0]}-{operability.years[-1]}"
    return (
        f"Over {yrs}, the highest average share of days meeting all optimal criteria "
        f"is in {_MO[best_i]} (~{month_avgs[best_i]:.0f}%), and the lowest in "
        f"{_MO[worst_i]} (~{month_avgs[worst_i]:.0f}%). "
        f"Year-to-year colour variation shows climate volatility — a green month in "
        f"one year can still be marginal in another. "
        f"Use multi-year green bands for primary windows and keep backup months ready."
    )


def _conclude_oper_days(operability) -> str:
    if not operability or not operability.years or operability.months_cached <= 0:
        return (
            "Estimated operable-day counts were not available for this run. "
            "Complete the last-10-year ERA5 cache and re-export to quantify "
            "how many days per month typically clear all criteria."
        )
    month_avgs = []
    for row in operability.operable_days:
        vals = [v for v in row if v is not None]
        month_avgs.append(float(np.mean(vals)) if vals else float("nan"))
    if np.all(np.isnan(month_avgs)):
        return (
            "No operable-day estimates could be computed from the cache. "
            "Ensure ERA5 monthly marine fields are present for the last 10 years."
        )
    best_i = int(np.nanargmax(month_avgs))
    worst_i = int(np.nanargmin(month_avgs))
    return (
        f"Estimated operable days (from monthly means) average highest in "
        f"{_MO[best_i]} (~{month_avgs[best_i]:.0f} days) and lowest in "
        f"{_MO[worst_i]} (~{month_avgs[worst_i]:.0f} days). "
        f"Months averaging ≥25 operable days are strong candidates for campaign "
        f"scheduling; months near or below 15 days need wider weather contingency. "
        f"These are model estimates from monthly ERA5 means, not hourly observations."
    )


# ── Public builder ───────────────────────────────────────────────────────────

def build_analysis_chart_pages(
    directory,
    profile: dict,
    *,
    climatology=None,
    operability=None,
    thresholds: dict | None = None,
    active_criteria: list | None = None,
    day_fractions: dict | None = None,
    param_fractions: dict | None = None,
    dpi: int = 150,
) -> List[ChartPage]:
    """Render charts 1–12 as individual PNGs with conclusions."""
    if not profile:
        return []

    out_dir = Path(directory)
    out_dir.mkdir(parents=True, exist_ok=True)
    from modules.m3_probability.multipliers import exceedance

    thr = dict(thresholds or DEFAULT_THRESHOLDS)
    ref_wind = float(thr.get("ws", DEFAULT_THRESHOLDS["ws"]))
    ref_hs = float(thr.get("sh", DEFAULT_THRESHOLDS["sh"]))

    months = list(range(1, 13))
    x = np.arange(1, 13)
    overall = [profile[m].overall_prob * 100 for m in months]
    ws = _means(profile, "ws")
    wg = _means(profile, "wg")
    sh = _means(profile, "sh")
    swh = _means(profile, "swh")
    swp = _means(profile, "swp")
    sdV = _means(profile, "sdV")
    swdV = _means(profile, "swdV")
    hs = [combined_hs(a, b) for a, b in zip(sh, swh)]
    hs_ft = [h * _M_TO_FT for h in hs]
    era_suffix = ""
    if climatology and getattr(climatology, "era5_coverage", (0, 0))[0] > 0:
        era_suffix = f" (ERA5 {climatology.window_label} pooled)"

    pages: List[ChartPage] = []

    # 1
    fig, ax = _new_fig(8.2, 4.6)
    ax.plot(x, overall, color=_ACCENT, linewidth=2.2, zorder=2)
    for m, val in zip(x, overall):
        ax.scatter(m, val, color=_verdict_color(val / 100), s=50, zorder=3,
                   edgecolors=_PANEL, linewidths=0.8)
    go_line = _go_pct()
    marg_line = _marg_pct()
    ax.axhline(go_line, color=_GO, linestyle="--", linewidth=1.1,
               alpha=0.8, label=f"GO ({go_line:.0f}%)")
    ax.axhline(marg_line, color=_MARG, linestyle="--", linewidth=1.1,
               alpha=0.8, label=f"Marginal ({marg_line:.0f}%)")
    ax.set_ylim(0, 100); ax.set_xlim(0.5, 12.5)
    ax.set_xticks(x); ax.set_xticklabels(_MO)
    ax.set_ylabel("% days all criteria met")
    title1 = "1. Operating window — % of days meeting all optimal criteria"
    ax.set_title(title1, fontsize=11, fontweight="bold")
    ax.grid(True, color=_GRID, linestyle=":", alpha=0.5)
    ax.legend(loc="lower center", ncol=2, fontsize=8, facecolor=_BG,
              edgecolor=_GRID, labelcolor=_MUTED)
    pages.append(ChartPage(1, title1, _save(fig, out_dir / "chart_01.png", dpi),
                           _conclude_operating(overall)))

    # 2
    fig, ax = _new_fig()
    ax.bar(x, hs_ft, color=_ACCENT, edgecolor=_GRID, linewidth=0.4)
    lim_ft = ref_hs * _M_TO_FT
    ax.axhline(lim_ft, color=_REF_COLOR, linestyle=":", linewidth=1.5,
               label=f"Limit {ref_hs:.2f} m / {lim_ft:.1f} ft")
    ax.set_xticks(x); ax.set_xticklabels(_MO); ax.set_ylabel("Hs (ft)")
    title2 = "2. Monthly Average Significant Wave Height" + era_suffix
    ax.set_title(title2, fontsize=11, fontweight="bold")
    ax.grid(True, axis="y", color=_GRID, linestyle=":", alpha=0.4)
    ax.legend(loc="upper right", fontsize=8, facecolor=_BG,
              edgecolor=_GRID, labelcolor=_MUTED)
    pages.append(ChartPage(2, title2, _save(fig, out_dir / "chart_02.png", dpi),
                           _conclude_hs(hs_ft, lim_ft)))

    # 3
    fig, ax = _new_fig()
    ax.bar(x, ws, color="#0ea5e9", edgecolor=_GRID, linewidth=0.4)
    ax.axhline(ref_wind, color=_REF_COLOR, linestyle=":", linewidth=1.5,
               label=f"Limit {ref_wind:.0f} kt")
    ax.set_xticks(x); ax.set_xticklabels(_MO); ax.set_ylabel("Wind (kt)")
    title3 = "3. Monthly Average 10 m Wind Speed" + era_suffix
    ax.set_title(title3, fontsize=11, fontweight="bold")
    ax.grid(True, axis="y", color=_GRID, linestyle=":", alpha=0.4)
    ax.legend(loc="upper right", fontsize=8, facecolor=_BG,
              edgecolor=_GRID, labelcolor=_MUTED)
    pages.append(ChartPage(3, title3, _save(fig, out_dir / "chart_03.png", dpi),
                           _conclude_wind(ws, ref_wind)))

    # 4
    fig, ax = _new_fig(8.2, 4.8)
    ss_matrix = [_sea_state_composition(h) for h in hs]
    bottom = np.zeros(12)
    for i, (label, _lo, _hi, color) in enumerate(_SS_BINS):
        vals = np.array([row[i] for row in ss_matrix])
        ax.bar(x, vals, bottom=bottom, color=color, edgecolor=_GRID,
               linewidth=0.3, label=label, width=0.7)
        bottom += vals
    ax.set_ylim(0, 100); ax.set_xlim(0.5, 12.5)
    ax.set_xticks(x); ax.set_xticklabels(_MO); ax.set_ylabel("% of time")
    title4 = "4. Exclusive Sea-State Composition (WMO Douglas)"
    ax.set_title(title4, fontsize=11, fontweight="bold")
    ax.grid(True, axis="y", color=_GRID, linestyle=":", alpha=0.4)
    ax.legend(loc="upper right", ncol=4, fontsize=8, facecolor=_BG,
              edgecolor=_GRID, labelcolor=_MUTED)
    pages.append(ChartPage(4, title4, _save(fig, out_dir / "chart_04.png", dpi),
                           _conclude_sea_state(hs)))

    # 5
    fig, ax = _new_fig()
    ratio = [(g / s) if s > 0 else 0.0 for g, s in zip(wg, ws)]
    ax.plot(x, ratio, color=_MARG, linewidth=2, marker="o", markersize=5)
    for m, r in zip(x, ratio):
        if r >= 1.5:
            ax.scatter(m, r, color=_NOGO, s=45, zorder=3)
    ax.axhline(1.5, color=_NOGO, linestyle="--", linewidth=1.1, label="Turbulent > 1.5")
    ax.set_xticks(x); ax.set_xticklabels(_MO); ax.set_ylabel("Gust / wind")
    title5 = "5. Gust ratio (structural-load / turbulence risk)"
    ax.set_title(title5, fontsize=11, fontweight="bold")
    ax.grid(True, axis="y", color=_GRID, linestyle=":", alpha=0.4)
    ax.legend(loc="upper right", fontsize=8, facecolor=_BG,
              edgecolor=_GRID, labelcolor=_MUTED)
    pages.append(ChartPage(5, title5, _save(fig, out_dir / "chart_05.png", dpi),
                           _conclude_gust(ratio)))

    # 6
    fig, ax = _new_fig()
    bw = 0.4
    ax.bar(x - bw / 2, sdV, width=bw, color="#06b6d4", edgecolor=_GRID,
           linewidth=0.4, label="Sea dir spread")
    ax.bar(x + bw / 2, swdV, width=bw, color="#ec4899", edgecolor=_GRID,
           linewidth=0.4, label="Swell dir spread")
    thr_s = _thr(profile, "sdV")
    if thr_s:
        ax.axhline(thr_s, color=_MUTED, linestyle="--", linewidth=1.1,
                   label=f"Tol {thr_s:.0f} deg")
    ax.set_xticks(x); ax.set_xticklabels(_MO); ax.set_ylabel("Spread (deg)")
    title6 = "6. Directional variability (heading consistency)"
    ax.set_title(title6, fontsize=11, fontweight="bold")
    ax.grid(True, axis="y", color=_GRID, linestyle=":", alpha=0.4)
    ax.legend(loc="upper right", fontsize=8, facecolor=_BG,
              edgecolor=_GRID, labelcolor=_MUTED)
    pages.append(ChartPage(6, title6, _save(fig, out_dir / "chart_06.png", dpi),
                           _conclude_dir(sdV, swdV, thr_s)))

    # 7
    fig, ax = _new_fig()
    sc = ax.scatter(swp, swh, c=months, cmap="viridis", s=70,
                    edgecolors=_PANEL, linewidths=0.6, zorder=3)
    thr_p = _thr(profile, "swp")
    thr_h = _thr(profile, "swh")
    if thr_p:
        ax.axvline(thr_p, color=_NOGO, linestyle="--", linewidth=1.1, label="Period limit")
    if thr_h:
        ax.axhline(thr_h, color=_NOGO, linestyle="--", linewidth=1.1, label="Height limit")
    for i, (p, h) in enumerate(zip(swp, swh)):
        ax.annotate(_MO[i], (p, h), textcoords="offset points", xytext=(4, 4),
                    fontsize=7, color=_MUTED)
    ax.set_xlabel("Swell period (s)"); ax.set_ylabel("Swell height (m)")
    title7 = "7. Swell period vs height (resonance risk)"
    ax.set_title(title7, fontsize=11, fontweight="bold")
    ax.grid(True, color=_GRID, linestyle=":", alpha=0.4)
    cbar = fig.colorbar(sc, ax=ax, fraction=0.045, pad=0.02, ticks=[1, 4, 7, 10])
    cbar.ax.set_yticklabels(["Jan", "Apr", "Jul", "Oct"])
    cbar.ax.tick_params(colors=_MUTED, labelsize=7)
    if thr_p or thr_h:
        ax.legend(loc="upper right", fontsize=8, facecolor=_BG,
                  edgecolor=_GRID, labelcolor=_MUTED)
    pages.append(ChartPage(7, title7, _save(fig, out_dir / "chart_07.png", dpi),
                           _conclude_swell_scatter(swp, swh, thr_p, thr_h)))

    # 8
    fig, ax = _new_fig()
    steep = [(h / (1.56 * p * p)) if p > 0 else 0.0 for h, p in zip(swh, swp)]
    ax.bar(x, steep, color=[_NOGO if v >= 0.04 else _ACCENT for v in steep],
           edgecolor=_GRID, linewidth=0.4)
    ax.axhline(0.04, color=_NOGO, linestyle="--", linewidth=1.1, label="Steep > 0.04")
    ax.set_xticks(x); ax.set_xticklabels(_MO); ax.set_ylabel("H / L")
    title8 = "8. Swell steepness (breaking-seas risk)"
    ax.set_title(title8, fontsize=11, fontweight="bold")
    ax.grid(True, axis="y", color=_GRID, linestyle=":", alpha=0.4)
    ax.legend(loc="upper right", fontsize=8, facecolor=_BG,
              edgecolor=_GRID, labelcolor=_MUTED)
    pages.append(ChartPage(8, title8, _save(fig, out_dir / "chart_08.png", dpi),
                           _conclude_steepness(steep)))

    # 9
    fig, ax = _new_fig(8.2, 4.8)
    bw = 0.4
    use_ncei = (
        climatology is not None
        and any(climatology.pct_both_by_month.get(m) is not None for m in months)
    )
    if use_ncei:
        joint = [float(climatology.pct_both_by_month.get(m) or 0.0) for m in months]
        ax.bar(x, joint, width=0.7, color=_ACCENT, edgecolor=_GRID, linewidth=0.4)
        rank_idx = sorted(range(12), key=lambda i: joint[i], reverse=True)[:3]
        rank_str = " · ".join(f"{_MO[i]} {joint[i]:.0f}%" for i in rank_idx)
        title_extra = f"NCEI {climatology.window_label}"
    else:
        ws_ref = [exceedance(_REF_WIND_KTS / max(0.01, v)) * 100 for v in ws]
        hs_ref = [exceedance(_REF_HS_M / max(0.01, v)) * 100 for v in hs]
        joint = [(a / 100.0) * (b / 100.0) * 100.0 for a, b in zip(ws_ref, hs_ref)]
        ax.bar(x - bw / 2, ws_ref, width=bw, color=_ACCENT, edgecolor=_GRID,
               linewidth=0.4, label=f"Wind <= {_REF_WIND_KTS:.0f} kt %")
        ax.bar(x + bw / 2, hs_ref, width=bw, color="#0ea5e9", edgecolor=_GRID,
               linewidth=0.4, label=f"Hs <= {_REF_HS_M:.2f} m %")
        rank_idx = sorted(range(12), key=lambda i: joint[i], reverse=True)[:3]
        rank_str = " · ".join(f"{_MO[i]} {joint[i]:.0f}%" for i in rank_idx)
        title_extra = "exceedance model"
        ax.legend(loc="lower right", fontsize=8, facecolor=_BG,
                  edgecolor=_GRID, labelcolor=_MUTED)
    ax.axhline(_go_pct(), color=_GO, linestyle="--", linewidth=1.0, alpha=0.7)
    ax.set_ylim(0, 100)
    ax.set_xticks(x); ax.set_xticklabels(_MO); ax.set_ylabel("Operable (%)")
    title9 = (
        f"9. Standard operability — Hs <= {_REF_HS_M:.2f} m & "
        f"wind <= {_REF_WIND_KTS:.0f} kt ({title_extra})"
    )
    ax.set_title(title9, fontsize=11, fontweight="bold")
    ax.grid(True, axis="y", color=_GRID, linestyle=":", alpha=0.4)
    pages.append(ChartPage(9, title9, _save(fig, out_dir / "chart_09.png", dpi),
                           _conclude_dual(joint, rank_str)))

    # 10
    params = list(active_criteria) if active_criteria else _active_params(profile)
    go_line = _go_pct()

    def _chart10_cell(month: int, param: str) -> float:
        if param_fractions and param_fractions.get(month, {}).get(param) is not None:
            return float(param_fractions[month][param])
        return float(profile[month].param_probs.get(param, 0.0) * 100)

    matrix = np.array([
        [_chart10_cell(m, p) for m in months] for p in params
    ])
    fig, ax = _new_fig(8.2, max(3.8, 0.55 * len(params) + 2.2))
    im = ax.imshow(matrix, aspect="auto", cmap=_PROB_CMAP, vmin=0, vmax=100,
                   origin="upper")
    ax.set_xticks(range(12)); ax.set_xticklabels(_MO)
    ax.set_yticks(range(len(params)))
    ax.set_yticklabels([_PARAM_LABEL.get(p, p) for p in params])
    title10 = (
        "10. Per-parameter criterion met — estimated % of days/month "
        "(marginal; Chart 1 uses joint product)"
    )
    ax.set_title(title10, fontsize=11, fontweight="bold")
    for i in range(len(params)):
        for j in range(12):
            val = matrix[i, j]
            ax.text(j, i, f"{val:.0f}", ha="center", va="center",
                    color="#0f1923" if val >= go_line else "#f8fafc", fontsize=8)
    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.ax.tick_params(colors=_MUTED, labelsize=7)
    pages.append(ChartPage(10, title10, _save(fig, out_dir / "chart_10.png", dpi),
                           _conclude_param_heatmap(profile, params, param_fractions)))

    # 11–12
    title11 = "11. Inter-annual % days meeting all optimal criteria (last 10 years)"
    title12 = "12. Estimated operable days per month (last 10 years)"
    if operability and operability.years and operability.months_cached > 0:
        fig, ax = _new_fig(8.2, 5.2)
        _draw_operability_heatmap(
            ax, operability.pct_both, operability.years,
            fmt=".0f", vmin=_OPER_PCT_VMIN, vmax=_OPER_PCT_VMAX,
            cbar_label="% criteria met", classify_fn=None,
        )
        ax.set_title(title11, fontsize=11, fontweight="bold")
        pages.append(ChartPage(11, title11, _save(fig, out_dir / "chart_11.png", dpi),
                               _conclude_oper_pct(operability)))

        from modules.m2_weather.operability import classify_days
        fig, ax = _new_fig(8.2, 5.2)
        days_max = max(
            (v for row in operability.operable_days for v in row if v is not None),
            default=31,
        )
        _draw_operability_heatmap(
            ax, operability.operable_days, operability.years,
            fmt=".0f", vmin=0, vmax=max(31, days_max),
            cbar_label="Est. operable days", classify_fn=classify_days,
        )
        ax.set_title(title12, fontsize=11, fontweight="bold")
        pages.append(ChartPage(12, title12, _save(fig, out_dir / "chart_12.png", dpi),
                               _conclude_oper_days(operability)))
    else:
        for num, title, name, conclude in (
            (11, title11, "chart_11.png", _conclude_oper_pct),
            (12, title12, "chart_12.png", _conclude_oper_days),
        ):
            fig, ax = _new_fig(8.2, 3.5)
            ax.axis("off")
            ax.text(0.5, 0.5, "Operability data not available for this run.",
                    ha="center", va="center", color=_MUTED, fontsize=11,
                    transform=ax.transAxes)
            ax.set_title(title, fontsize=11, fontweight="bold", color=_TEXT)
            pages.append(ChartPage(num, title, _save(fig, out_dir / name, dpi),
                                   conclude(operability)))

    return pages

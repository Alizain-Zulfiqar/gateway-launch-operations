"""
ui/widgets/analysis_charts.py — Matplotlib decision-support charts.

Shared between the Analysis / Quick Analysis tabs (single-site view) and the
Comparison tab (multi-site view). All charts are computed from the Gateway
probability engine's output — a `dict[int, AnalysisResult]` keyed by month
(1–12) — not from any parallel data pipeline, so they stay analytically
consistent with the rest of the app.

Visual inspiration: the reference notebook's operating-window line chart and
location × month heatmap, adapted to Gateway's eight-parameter probability
model (seaborn is intentionally not required — pure matplotlib only).
"""
from __future__ import annotations

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.patches import Rectangle

from PyQt6.QtWidgets import QWidget, QVBoxLayout

from config import DEFAULT_THRESHOLDS

# ── Palette (matches the app dark theme) ──────────────────────────────────────
_BG      = "#1a2233"
_PANEL   = "#0f1923"
_GRID    = "#374151"
_TEXT    = "#e2e8f0"
_MUTED   = "#94a3b8"
_ACCENT  = "#2563eb"
_GO      = "#22c55e"
_MARG    = "#f59e0b"
_NOGO    = "#ef4444"

_MO = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

_MAG_PARAMS = ["ws", "wg", "sh", "swh", "swp"]
_DIR_PARAMS = ["wdV", "sdV", "swdV"]
_PARAM_LABEL = {
    "ws": "Wind speed", "wg": "Wind gust", "sh": "Sea Hs",
    "swh": "Swell height", "swp": "Swell period",
    "wdV": "Wind dir", "sdV": "Sea dir", "swdV": "Swell dir",
}

# GO/MARGINAL display bands — read from Settings at render time (see
# core.verdict_thresholds). Do not hardcode 0.70 / 0.50 here.


def _go_pct() -> float:
    from core.verdict_thresholds import go_pct_threshold
    return go_pct_threshold()


def _marg_pct() -> float:
    from core.verdict_thresholds import marginal_pct_threshold
    return marginal_pct_threshold()


# Reference dual-criteria benchmark for Chart 9 (aligned with DEFAULT_THRESHOLDS).
_REF_WIND_KTS = float(DEFAULT_THRESHOLDS["ws"])
_REF_HS_M = float(DEFAULT_THRESHOLDS["sh"])
_REF_COLOR = "#38bdf8"

# Green-amber-red colormap for the probability heatmaps (0 → red, 1 → green).
_PROB_CMAP = matplotlib.colors.LinearSegmentedColormap.from_list(
    "gateway_prob", ["#7f1d1d", "#b45309", "#a16207", "#4d7c0f", "#15803d"]
)

# YlGn-style operability heatmap (matches main.html notebook charts 5–6).
_OPER_CMAP = matplotlib.colors.LinearSegmentedColormap.from_list(
    "gateway_oper", ["#fef9c3", "#bef264", "#16a34a", "#14532d"]
)
_OPER_PCT_VMIN = 30.0
_OPER_PCT_VMAX = 100.0
_OPER_ANN_OPTIMAL = "#14532d"
_OPER_ANN_MARGINAL = "#854d0e"
_OPER_ANN_SUBOPT = "#7f1d1d"

SITE_COLORS = [
    "#3b82f6", "#22c55e", "#ef4444", "#f59e0b",
    "#a855f7", "#06b6d4", "#ec4899",
]

# Exclusive WMO Douglas sea-state bands by significant wave height (m) —
# matches main.html (SS2 / SS3 / SS4 / SS5+). Calm SS0–1 (<0.1 m) is folded
# into the SS2 stack segment so each month still totals ~100%.
# Colours: light→dark blue like the notebook's sns "Blues" palette.
_SS_BINS = [
    ("SS2",  0.0,  0.5,            "#bfdbfe"),  # includes calm <0.1 m
    ("SS3",  0.5,  1.25,           "#60a5fa"),
    ("SS4",  1.25, 2.5,            "#3b82f6"),
    ("SS5+", 2.5,  float("inf"),   "#1e3a8a"),
]
_SS_CV = 0.5   # assumed coefficient of variation of hourly Hs within a month
_M_TO_FT = 3.28084


def combined_hs(sh: float, swh: float) -> float:
    """True significant wave height from independent wind-sea + swell components
    (energy sum, √(sh²+swh²)) — the physically correct combined Hs, rather than
    the wind-sea component alone."""
    return (float(sh) ** 2 + float(swh) ** 2) ** 0.5


def _sea_state_composition(hs_mean: float) -> list[float]:
    """Estimate the % of time spent in each Douglas sea-state band for a month,
    from the monthly mean significant wave height, assuming a lognormal
    distribution of hourly Hs (CV = _SS_CV). Returns percentages aligned with
    _SS_BINS (they sum to ~100). This is a model-based estimate — the engine
    only carries monthly means, not an hourly distribution."""
    import math
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


def _verdict_color(prob: float) -> str:
    from core.verdict_thresholds import get_go_threshold, get_marginal_threshold
    if prob >= get_go_threshold():
        return _GO
    if prob >= get_marginal_threshold():
        return _MARG
    return _NOGO


def _style_ax(ax) -> None:
    ax.set_facecolor(_BG)
    for spine in ax.spines.values():
        spine.set_color(_GRID)
    ax.tick_params(colors=_MUTED, labelsize=7)
    ax.title.set_color(_TEXT)
    ax.xaxis.label.set_color(_MUTED)
    ax.yaxis.label.set_color(_MUTED)


def _draw_operability_heatmap(
    ax,
    matrix,
    years: list,
    *,
    fmt: str,
    vmin: float,
    vmax: float,
    cbar_label: str,
    classify_fn,
) -> None:
    """Render a month × year operability grid with tier-coloured annotations."""
    import numpy as np
    from modules.m2_weather.operability import classify_pct, classify_days

    if classify_fn is None:
        classify_fn = classify_pct

    data = np.array(matrix, dtype=float)
    masked = np.ma.masked_invalid(data)
    im = ax.imshow(
        masked, aspect="auto", cmap=_OPER_CMAP, vmin=vmin, vmax=vmax,
        origin="upper",
    )
    ax.set_xticks(range(len(years)))
    ax.set_xticklabels([str(y) for y in years], fontsize=7)
    ax.set_yticks(range(12))
    ax.set_yticklabels(_MO, fontsize=7)
    ax.set_xlabel("Year")
    ax.set_ylabel("Month")

    for row in range(12):
        for col in range(len(years)):
            val = matrix[row][col]
            if val is None:
                ax.text(col, row, "—", ha="center", va="center",
                        color=_MUTED, fontsize=6)
                continue
            tier = classify_fn(val)
            if tier == "optimal":
                tcolor = _OPER_ANN_OPTIMAL
            elif tier == "marginal":
                tcolor = _OPER_ANN_MARGINAL
            else:
                tcolor = _OPER_ANN_SUBOPT
            if fmt == ".0f":
                label = f"{int(round(val))}"
            else:
                label = f"{val:.0f}"
            ax.text(col, row, label, ha="center", va="center",
                    color=tcolor, fontsize=6, fontweight="bold")

    cbar = ax.figure.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
    cbar.set_label(cbar_label, color=_MUTED, fontsize=7)
    cbar.ax.tick_params(colors=_MUTED, labelsize=6)
    cbar.outline.set_edgecolor(_GRID)


def _active_params(profile: dict) -> list[str]:
    """Magnitude params (always) + any directional param that actually counted
    toward the overall probability in this run."""
    active = _MAG_PARAMS.copy()
    if profile:
        first = next(iter(profile.values()))
        counted = getattr(first, "active_params", None) or set()
        for p in _DIR_PARAMS:
            if p in counted:
                active.append(p)
    return active


class _BaseChartCanvas(QWidget):
    """A QWidget wrapping a single matplotlib Figure/canvas."""

    def __init__(
        self,
        parent=None,
        min_height: int = 460,
        *,
        fig_inches: tuple[float, float] | None = None,
        constrained_layout: bool = True,
    ):
        super().__init__(parent)
        from PyQt6.QtWidgets import QSizePolicy

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._use_constrained = constrained_layout
        kw = {"facecolor": _PANEL}
        if constrained_layout:
            kw["constrained_layout"] = True
        self.fig = Figure(**kw)
        if fig_inches is not None:
            self.fig.set_size_inches(fig_inches[0], fig_inches[1], forward=True)
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.canvas.setMinimumHeight(min_height)
        self.setMinimumHeight(min_height)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        layout.addWidget(self.canvas)

    def _placeholder(self, msg: str) -> None:
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        ax.set_facecolor(_PANEL)
        ax.axis("off")
        ax.text(0.5, 0.5, msg, color=_MUTED, ha="center", va="center",
                fontsize=10, transform=ax.transAxes)
        self.canvas.draw_idle()


class AnalysisChartsWidget(_BaseChartCanvas):
    """Single-site decision charts (scrollable stack):

      1. Operating window — monthly GO probability.
      2. Monthly Average Significant Wave Height (combined Hs, m & ft) —
         matches main.html; 1.8 m / 6 ft reference line.
      3. Monthly Average 10 m Wind Speed — matches main.html; 25 kt reference.
      4. Exclusive Sea-State Composition — stacked SS2/SS3/SS4/SS5+ by month
         (WMO Douglas; estimated from monthly mean Hs via lognormal model).
      5. Gust ratio — mean gust ÷ sustained wind.
      6. Directional variability — sea/swell direction spread.
      7. Swell period vs height — resonance risk scatter.
      8. Swell steepness — H/L breaking-seas risk.
      9. Dual-criteria operability — wind ≤ 25 kt AND combined Hs ≤ 1.8 m,
         with most-favorable-months ranking.
     10. Per-parameter probability heatmap.
     11. Inter-annual variability — % meeting both wind + Hs criteria (month × year).
     12. Fully operable days per month (all reports that day met both criteria).

    The old "wind vs limit" / "Hs vs limit" bar charts were removed in favour
    of the main.html monthly-average panels (#2–#4).
    """

    def __init__(self, parent=None, *, spacious: bool = False):
        # spacious=True (Comparison per-site stacks): taller figure + extra
        # subplot gaps so 12 panels are readable instead of packed.
        if spacious:
            super().__init__(
                parent,
                min_height=5200,
                fig_inches=(11.5, 58.0),
                constrained_layout=False,
            )
        else:
            super().__init__(parent, min_height=2900)
        self._spacious = spacious
        self._profile: dict = {}
        self._operability = None
        self._operability_progress: tuple[int, int] | None = None
        self._climatology = None
        self._gs = None
        self._ax11 = None
        self._ax12 = None
        self._operability_pending = False
        self._thresholds: dict = dict(DEFAULT_THRESHOLDS)
        self._active_criteria: list[str] = list(_MAG_PARAMS)
        self._day_fractions: dict | None = None
        self._param_fractions: dict | None = None
        self._placeholder("Run an analysis to see charts.")

    @staticmethod
    def _means(profile: dict, param: str, months) -> list[float]:
        out = []
        for m in months:
            em = getattr(profile[m], "effective_means", {}) or {}
            out.append(float(em.get(param) or 0.0))
        return out

    @staticmethod
    def _thr(profile: dict, param: str):
        first = next(iter(profile.values()))
        th = getattr(first, "thresholds", {}) or {}
        v = th.get(param)
        return float(v) if v else None

    def set_profile(
        self,
        profile: dict,
        operability=None,
        operability_progress: tuple[int, int] | None = None,
        climatology=None,
        *,
        thresholds: dict | None = None,
        active_criteria: list | None = None,
        day_fractions: dict | None = None,
        param_fractions: dict | None = None,
    ) -> None:
        """Full render (charts 1–12). Used by Quick Analysis and legacy callers."""
        if not profile:
            self._profile = {}
            self._operability = None
            self._operability_progress = None
            self._climatology = None
            self._operability_pending = False
            self._day_fractions = None
            self._param_fractions = None
            self._placeholder("Run an analysis to see charts.")
            return

        self.set_profile_charts_1_10(
            profile,
            climatology=climatology,
            thresholds=thresholds,
            active_criteria=active_criteria,
            day_fractions=day_fractions,
            param_fractions=param_fractions,
        )
        self._operability = operability
        self._operability_progress = operability_progress
        self._operability_pending = False
        self._render_operability_panels()
        self.canvas.draw_idle()

    def set_profile_charts_1_10(
        self,
        profile: dict,
        climatology=None,
        *,
        thresholds: dict | None = None,
        active_criteria: list | None = None,
        day_fractions: dict | None = None,
        param_fractions: dict | None = None,
    ) -> None:
        """Render decision charts 1–10; charts 11–12 show a loading placeholder."""
        if not profile:
            self.set_profile({})
            return

        self._profile = profile
        self._climatology = climatology
        if thresholds is not None:
            self._thresholds = dict(thresholds)
        if active_criteria is not None:
            self._active_criteria = list(active_criteria)
        if day_fractions is not None:
            self._day_fractions = day_fractions
        if param_fractions is not None:
            self._param_fractions = param_fractions
        self._operability = None
        self._operability_progress = None
        self._operability_pending = True

        import numpy as np
        from modules.m3_probability.multipliers import exceedance

        self.fig.clear()
        self._ax11 = None
        self._ax12 = None
        gs_kw = dict(
            height_ratios=[1.0, 1.0, 1.15, 0.95, 0.95, 1.0, 1.05, 1.1, 1.1],
        )
        if self._spacious:
            gs_kw["hspace"] = 0.55
            gs_kw["wspace"] = 0.30
        gs = self.fig.add_gridspec(9, 2, **gs_kw)
        self._gs = gs
        if self._spacious:
            self.fig.subplots_adjust(
                left=0.07, right=0.97, top=0.985, bottom=0.015,
            )
        months = list(range(1, 13))
        x = np.arange(1, 13)

        era_suffix = ""
        if climatology and climatology.era5_coverage[0] > 0:
            era_suffix = f" (ERA5 {climatology.window_label} pooled)"

        overall = [profile[m].overall_prob * 100 for m in months]
        ws = self._means(profile, "ws", months)
        wg = self._means(profile, "wg", months)
        sh = self._means(profile, "sh", months)
        swh = self._means(profile, "swh", months)
        swp = self._means(profile, "swp", months)
        sdV = self._means(profile, "sdV", months)
        swdV = self._means(profile, "swdV", months)
        hs = [combined_hs(a, b) for a, b in zip(sh, swh)]
        hs_ft = [h * _M_TO_FT for h in hs]

        self._draw_charts_1_10_body(
            gs, x, months, profile, climatology, era_suffix, exceedance,
            overall, ws, wg, sh, swh, swp, sdV, swdV, hs, hs_ft,
            thresholds=self._thresholds,
            day_fractions=self._day_fractions,
            active_criteria=self._active_criteria,
            param_fractions=self._param_fractions,
        )
        self._render_operability_panels()
        self.canvas.draw_idle()

    def _draw_charts_1_10_body(
        self, gs, x, months, profile, climatology, era_suffix, exceedance,
        overall, ws, wg, sh, swh, swp, sdV, swdV, hs, hs_ft,
        *,
        thresholds: dict | None = None,
        day_fractions: dict | None = None,
        active_criteria: list | None = None,
        param_fractions: dict | None = None,
    ) -> None:
        import numpy as np
        thr = dict(thresholds or self._thresholds or DEFAULT_THRESHOLDS)
        ref_wind = float(thr.get("ws", _REF_WIND_KTS))
        ref_hs = float(thr.get("sh", _REF_HS_M))
        # ── 1. Operating window (full width) ─────────────────────────────────
        ax = self.fig.add_subplot(gs[0, :])
        _style_ax(ax)
        ax.plot(x, overall, color=_ACCENT, linewidth=2, zorder=2)
        for m, val in zip(x, overall):
            ax.scatter(m, val, color=_verdict_color(val / 100),
                       s=44, zorder=3, edgecolors=_PANEL, linewidths=0.8)
        go_line = _go_pct()
        marg_line = _marg_pct()
        ax.axhline(go_line, color=_GO, linestyle="--", linewidth=1,
                   alpha=0.7, label=f"GO ({go_line:.0f}%)")
        ax.axhline(marg_line, color=_MARG, linestyle="--", linewidth=1,
                   alpha=0.7, label=f"Marginal ({marg_line:.0f}%)")
        best_len, best_start = 0, None
        run_len, run_start = 0, None
        for i, val in enumerate(overall):
            if val >= _go_pct():
                if run_len == 0:
                    run_start = i
                run_len += 1
                if run_len > best_len:
                    best_len, best_start = run_len, run_start
            else:
                run_len = 0
        if best_len > 0:
            ax.axvspan(best_start + 1 - 0.5, best_start + best_len + 0.5,
                       color=_GO, alpha=0.12, zorder=1)
            ax.text(best_start + 1 + (best_len - 1) / 2, 6,
                    f"Longest GO run: {best_len} mo",
                    ha="center", color=_GO, fontsize=6)
        ax.set_ylim(0, 100)
        ax.set_xlim(0.5, 12.5)
        ax.set_xticks(x)
        ax.set_xticklabels(_MO)
        ax.set_ylabel("% days all criteria met")
        ax.set_title(
            "Operating window — avg % of days/month where all optimal criteria are met",
            fontsize=9, fontweight="bold",
        )
        ax.grid(True, color=_GRID, linestyle=":", linewidth=0.5, alpha=0.5)
        leg = ax.legend(loc="lower center", ncol=2, fontsize=6,
                        facecolor=_BG, edgecolor=_GRID, labelcolor=_MUTED)
        leg.get_frame().set_alpha(0.9)

        # ── 2. Monthly Average Significant Wave Height (main.html style) ─────
        ax = self.fig.add_subplot(gs[1, 0])
        _style_ax(ax)
        ax.bar(x, hs_ft, color=_ACCENT, edgecolor=_GRID, linewidth=0.4, zorder=2)
        ax.axhline(ref_hs * _M_TO_FT, color=_REF_COLOR, linestyle=":",
                   linewidth=1.4, label=f"Limit {ref_hs:.1f} m / {ref_hs * _M_TO_FT:.0f} ft")
        ax.set_xticks(x); ax.set_xticklabels(_MO)
        ax.set_ylabel("Hs (ft)")
        ax.set_title("Monthly Average Significant Wave Height" + era_suffix,
                     fontsize=8, fontweight="bold")
        ax.grid(True, axis="y", color=_GRID, linestyle=":", linewidth=0.5, alpha=0.4)
        ax.legend(loc="upper right", fontsize=6, facecolor=_BG,
                  edgecolor=_GRID, labelcolor=_MUTED)
        # Secondary axis in metres for readability.
        ax2 = ax.twinx()
        ax2.set_ylim(ax.get_ylim()[0] / _M_TO_FT, ax.get_ylim()[1] / _M_TO_FT)
        ax2.set_ylabel("Hs (m)", color=_MUTED, fontsize=7)
        ax2.tick_params(colors=_MUTED, labelsize=6)
        for spine in ax2.spines.values():
            spine.set_color(_GRID)

        # ── 3. Monthly Average 10 m Wind Speed (main.html style) ─────────────
        ax = self.fig.add_subplot(gs[1, 1])
        _style_ax(ax)
        ax.bar(x, ws, color="#0ea5e9", edgecolor=_GRID, linewidth=0.4, zorder=2)
        ax.axhline(ref_wind, color=_REF_COLOR, linestyle=":",
                   linewidth=1.4, label=f"Limit {ref_wind:.0f} kt")
        ax.set_xticks(x); ax.set_xticklabels(_MO)
        ax.set_ylabel("Wind (kt)")
        ax.set_title("Monthly Average 10 m Wind Speed" + era_suffix,
                     fontsize=8, fontweight="bold")
        ax.grid(True, axis="y", color=_GRID, linestyle=":", linewidth=0.5, alpha=0.4)
        ax.legend(loc="upper right", fontsize=6, facecolor=_BG,
                  edgecolor=_GRID, labelcolor=_MUTED)

        # ── 4. Exclusive Sea-State Composition (main.html stacked bars) ──────
        ax = self.fig.add_subplot(gs[2, :])
        _style_ax(ax)
        ss_matrix = [_sea_state_composition(h) for h in hs]  # 12 × 4
        bottom = np.zeros(12)
        for i, (label, _lo, _hi, color) in enumerate(_SS_BINS):
            vals = np.array([row[i] for row in ss_matrix])
            ax.bar(x, vals, bottom=bottom, color=color, edgecolor=_GRID,
                   linewidth=0.3, label=label, width=0.7)
            bottom += vals
        ax.set_ylim(0, 100)
        ax.set_xlim(0.5, 12.5)
        ax.set_xticks(x); ax.set_xticklabels(_MO)
        ax.set_ylabel("% of time")
        ax.set_title(
            "Exclusive Sea-State Composition (WMO Douglas — from monthly mean Hs)",
            fontsize=9, fontweight="bold")
        ax.grid(True, axis="y", color=_GRID, linestyle=":", linewidth=0.5, alpha=0.4)
        ax.legend(loc="upper right", ncol=4, fontsize=6, facecolor=_BG,
                  edgecolor=_GRID, labelcolor=_MUTED)

        # ── 5. Gust ratio ────────────────────────────────────────────────────
        ax = self.fig.add_subplot(gs[3, 0])
        _style_ax(ax)
        ratio = [(g / s) if s > 0 else 0.0 for g, s in zip(wg, ws)]
        ax.plot(x, ratio, color=_MARG, linewidth=1.8, marker="o", markersize=4,
                zorder=2)
        for m, r in zip(x, ratio):
            if r >= 1.5:
                ax.scatter(m, r, color=_NOGO, s=40, zorder=3,
                           edgecolors=_PANEL, linewidths=0.6)
        ax.axhline(1.5, color=_NOGO, linestyle="--", linewidth=1, alpha=0.7,
                   label="Turbulent > 1.5")
        ax.set_xticks(x); ax.set_xticklabels(_MO)
        ax.set_ylabel("Gust ÷ wind")
        ax.set_title("Gust ratio (structural-load / turbulence risk)",
                     fontsize=8, fontweight="bold")
        ax.grid(True, axis="y", color=_GRID, linestyle=":", linewidth=0.5, alpha=0.4)
        ax.legend(loc="upper right", fontsize=6, facecolor=_BG,
                  edgecolor=_GRID, labelcolor=_MUTED)

        # ── 6. Directional variability ───────────────────────────────────────
        ax = self.fig.add_subplot(gs[3, 1])
        _style_ax(ax)
        bw = 0.4
        ax.bar(x - bw / 2, sdV, width=bw, color="#06b6d4", edgecolor=_GRID,
               linewidth=0.4, label="Sea dir spread")
        ax.bar(x + bw / 2, swdV, width=bw, color="#ec4899", edgecolor=_GRID,
               linewidth=0.4, label="Swell dir spread")
        thr_s = self._thr(profile, "sdV")
        if thr_s:
            ax.axhline(thr_s, color=_MUTED, linestyle="--", linewidth=1,
                       alpha=0.7, label=f"Tol {thr_s:.0f}°")
        ax.set_xticks(x); ax.set_xticklabels(_MO)
        ax.set_ylabel("Spread (°)")
        ax.set_title("Directional variability (heading consistency)",
                     fontsize=8, fontweight="bold")
        ax.grid(True, axis="y", color=_GRID, linestyle=":", linewidth=0.5, alpha=0.4)
        ax.legend(loc="upper right", fontsize=6, facecolor=_BG,
                  edgecolor=_GRID, labelcolor=_MUTED)

        # ── 7. Swell period vs height scatter ────────────────────────────────
        ax = self.fig.add_subplot(gs[4, 0])
        _style_ax(ax)
        sc = ax.scatter(swp, swh, c=months, cmap="viridis", s=55,
                        edgecolors=_PANEL, linewidths=0.6, zorder=3)
        thr_p = self._thr(profile, "swp")
        thr_h = self._thr(profile, "swh")
        if thr_p:
            ax.axvline(thr_p, color=_NOGO, linestyle="--", linewidth=1, alpha=0.7)
        if thr_h:
            ax.axhline(thr_h, color=_NOGO, linestyle="--", linewidth=1, alpha=0.7)
        ax.set_xlabel("Swell period (s)")
        ax.set_ylabel("Swell height (m)")
        ax.set_title("Swell period vs height (resonance risk)",
                     fontsize=8, fontweight="bold")
        ax.grid(True, color=_GRID, linestyle=":", linewidth=0.5, alpha=0.4)
        cbar = self.fig.colorbar(sc, ax=ax, fraction=0.045, pad=0.02,
                                 ticks=[1, 4, 7, 10])
        cbar.ax.set_yticklabels(["Jan", "Apr", "Jul", "Oct"])
        cbar.ax.tick_params(colors=_MUTED, labelsize=6)
        cbar.outline.set_edgecolor(_GRID)

        # ── 8. Swell steepness ───────────────────────────────────────────────
        ax = self.fig.add_subplot(gs[4, 1])
        _style_ax(ax)
        steep = [(h / (1.56 * p * p)) if p > 0 else 0.0
                 for h, p in zip(swh, swp)]
        ax.bar(x, steep, color=[_NOGO if v >= 0.04 else _ACCENT for v in steep],
               edgecolor=_GRID, linewidth=0.4)
        ax.axhline(0.04, color=_NOGO, linestyle="--", linewidth=1, alpha=0.7,
                   label="Steep > 0.04")
        ax.set_xticks(x); ax.set_xticklabels(_MO)
        ax.set_ylabel("H / L")
        ax.set_title("Swell steepness (breaking-seas risk)",
                     fontsize=8, fontweight="bold")
        ax.grid(True, axis="y", color=_GRID, linestyle=":", linewidth=0.5, alpha=0.4)
        ax.legend(loc="upper right", fontsize=6, facecolor=_BG,
                  edgecolor=_GRID, labelcolor=_MUTED)

        # ── 9. Dual-criteria (combined Hs + wind standard) ───────────────────
        ax = self.fig.add_subplot(gs[5, :])
        _style_ax(ax)
        bw = 0.4
        use_ncei_joint = (
            climatology is not None
            and any(climatology.pct_both_by_month.get(m) is not None for m in months)
        )
        if use_ncei_joint:
            joint = [
                float(climatology.pct_both_by_month.get(m) or 0.0) for m in months
            ]
            rank_idx = sorted(range(12), key=lambda i: joint[i], reverse=True)[:3]
            rank_str = "  ·  ".join(f"{_MO[i]} {joint[i]:.0f}%" for i in rank_idx)
            ax.bar(x, joint, width=0.7, color=_ACCENT, edgecolor=_GRID,
                   linewidth=0.4, label="% both criteria (NCEI obs)")
            for m, val in zip(x, joint):
                if val >= _go_pct():
                    ax.scatter(m, val, marker="*", color=_GO, s=60, zorder=4)
            title_extra = f"NCEI {climatology.window_label} pooled"
        else:
            ws_ref = [exceedance(_REF_WIND_KTS / max(0.01, v)) * 100 for v in ws]
            hs_ref = [exceedance(_REF_HS_M / max(0.01, v)) * 100 for v in hs]
            joint = [(a / 100.0) * (b / 100.0) * 100.0 for a, b in zip(ws_ref, hs_ref)]
            rank_idx = sorted(range(12), key=lambda i: joint[i], reverse=True)[:3]
            rank_str = "  ·  ".join(f"{_MO[i]} {joint[i]:.0f}%" for i in rank_idx)
            ax.bar(x - bw / 2, ws_ref, width=bw, color=_ACCENT, edgecolor=_GRID,
                   linewidth=0.4, label=f"Wind ≤ {_REF_WIND_KTS:.0f} kt %")
            ax.bar(x + bw / 2, hs_ref, width=bw, color="#0ea5e9", edgecolor=_GRID,
                   linewidth=0.4, label=f"Hs ≤ {_REF_HS_M:.2f} m %")
            for m, a, b in zip(x, ws_ref, hs_ref):
                if a >= _go_pct() and b >= _go_pct():
                    ax.scatter(m, 96, marker="*", color=_GO, s=60, zorder=4)
            title_extra = "exceedance model"
            ax.legend(loc="lower right", fontsize=6, facecolor=_BG,
                      edgecolor=_GRID, labelcolor=_MUTED)
        if rank_idx:
            best = rank_idx[0]
            ax.axvspan(best + 1 - 0.5, best + 1 + 0.5, color=_GO, alpha=0.12,
                       zorder=0)
        ax.axhline(_go_pct(), color=_GO, linestyle="--", linewidth=1, alpha=0.6)
        ax.set_ylim(0, 100)
        ax.set_xticks(x); ax.set_xticklabels(_MO)
        ax.set_ylabel("Operable (%)")
        ax.set_title(
            f"Standard operability — Hs ≤ {_REF_HS_M:.2f} m & "
            f"wind ≤ {_REF_WIND_KTS:.0f} kt (★ both met)\n"
            f"Most favorable months:  {rank_str}  ·  {title_extra}",
            fontsize=8, fontweight="bold")
        ax.grid(True, axis="y", color=_GRID, linestyle=":", linewidth=0.5, alpha=0.4)

        # ── 10. Per-parameter criterion-met heatmap (full width) ─────────────
        params = list(active_criteria) if active_criteria else _active_params(profile)
        pf = param_fractions if param_fractions is not None else self._param_fractions
        go_pct = _go_pct()

        def _cell_pct(month: int, param: str) -> float:
            if pf and pf.get(month, {}).get(param) is not None:
                return float(pf[month][param])
            return float(profile[month].param_probs.get(param, 0.0) * 100)

        matrix = np.array([
            [_cell_pct(m, p) for m in months]
            for p in params
        ])
        ax = self.fig.add_subplot(gs[6, :])
        _style_ax(ax)
        im = ax.imshow(matrix, aspect="auto", cmap=_PROB_CMAP,
                       vmin=0, vmax=100, origin="upper")
        ax.set_xticks(range(12)); ax.set_xticklabels(_MO)
        ax.set_yticks(range(len(params)))
        ax.set_yticklabels([_PARAM_LABEL.get(p, p) for p in params])
        ax.set_title(
            "Per-parameter criterion met — estimated % of days/month "
            "(marginal; Chart 1 uses joint product of these)",
            fontsize=9, fontweight="bold",
        )
        for i in range(len(params)):
            for j in range(12):
                val = matrix[i, j]
                ax.text(j, i, f"{val:.0f}", ha="center", va="center",
                        color="#0f1923" if val >= go_pct else "#f8fafc", fontsize=6)
        cbar = self.fig.colorbar(im, ax=ax, fraction=0.02, pad=0.01)
        cbar.ax.tick_params(colors=_MUTED, labelsize=6)
        cbar.outline.set_edgecolor(_GRID)

    @staticmethod
    def _draw_fetch_progress(ax, done: int, total: int, title: str) -> None:
        ax.axis("off")
        pct = int(100 * done / total) if total else 0
        ax.text(
            0.5, 0.62,
            title,
            color=_TEXT, ha="center", va="center", fontsize=9,
            transform=ax.transAxes,
        )
        ax.text(
            0.5, 0.48,
            f"{done} / {total} months ({pct}%)",
            color=_MUTED, ha="center", va="center", fontsize=8,
            transform=ax.transAxes,
        )
        bar_left, bar_width, bar_y, bar_h = 0.15, 0.7, 0.32, 0.08
        ax.add_patch(
            Rectangle(
                (bar_left, bar_y), bar_width, bar_h,
                transform=ax.transAxes, facecolor=_PANEL, edgecolor=_GRID,
            )
        )
        fill = bar_width * (done / total) if total else 0
        if fill > 0:
            ax.add_patch(
                Rectangle(
                    (bar_left, bar_y), fill, bar_h,
                    transform=ax.transAxes, facecolor=_ACCENT, edgecolor=_ACCENT,
                )
            )

    def export_chart_images(
        self,
        directory,
        *,
        dpi: int = 140,
        max_pages: int = 6,
    ) -> list[str]:
        """
        Export the current decision-chart figure as PNG slices sized for A4 PDF.

        Returns a list of absolute file paths (empty if no profile is loaded).
        Does not alter the on-screen figure size.
        """
        import math
        from io import BytesIO
        from pathlib import Path

        import matplotlib.pyplot as plt
        import numpy as np

        out_dir = Path(directory)
        out_dir.mkdir(parents=True, exist_ok=True)
        if not self._profile:
            return []

        # Ensure artists are fully laid out before rasterising.
        self.canvas.draw()
        buf = BytesIO()
        self.fig.savefig(
            buf,
            format="png",
            dpi=dpi,
            facecolor=self.fig.get_facecolor(),
            edgecolor="none",
            bbox_inches="tight",
            pad_inches=0.15,
        )
        buf.seek(0)
        img = plt.imread(buf)
        if img.ndim < 2 or img.shape[0] < 10 or img.shape[1] < 10:
            return []

        # Fit strips to ~A4 content box (190 mm × 245 mm).
        page_aspect = 190.0 / 245.0
        strip_h = max(1, int(round(img.shape[1] / page_aspect)))
        n_pages = min(max_pages, max(1, math.ceil(img.shape[0] / strip_h)))
        # Rebalance strip height so pages share the figure evenly.
        strip_h = max(1, math.ceil(img.shape[0] / n_pages))

        paths: list[str] = []
        for i in range(n_pages):
            y0 = i * strip_h
            y1 = min(img.shape[0], (i + 1) * strip_h)
            if y0 >= img.shape[0]:
                break
            strip = img[y0:y1]
            # Pad short final strip so PDF scaling stays consistent.
            if strip.shape[0] < strip_h:
                pad = np.full(
                    (strip_h - strip.shape[0], strip.shape[1], strip.shape[2]),
                    strip[0, 0] if strip.size else 1.0,
                    dtype=strip.dtype,
                )
                # Use panel background-ish dark if possible
                pad[:] = (15 / 255, 25 / 255, 35 / 255, 1.0)[: strip.shape[2]]
                strip = np.vstack([strip, pad])
            path = out_dir / f"decision_charts_{i + 1:02d}.png"
            plt.imsave(path, strip)
            paths.append(str(path.resolve()))
        return paths

    def _render_operability_panels(self) -> None:
        from modules.m2_weather.operability import classify_days

        if self._gs is None:
            return

        if self._ax11 is None or self._ax11 not in self.fig.axes:
            self._ax11 = self.fig.add_subplot(self._gs[7, :])
        else:
            self._ax11.clear()
        if self._ax12 is None or self._ax12 not in self.fig.axes:
            self._ax12 = self.fig.add_subplot(self._gs[8, :])
        else:
            self._ax12.clear()
        ax11, ax12 = self._ax11, self._ax12
        _style_ax(ax11)
        _style_ax(ax12)

        operability = self._operability
        progress = self._operability_progress
        loading = progress is not None and progress[0] < progress[1]
        is_era5 = operability is not None and operability.source == "era5_reanalysis"

        if self._operability_pending and operability is None and not loading:
            wait_msg = "Building operability heatmaps (charts 11–12)…"
            ax11.axis("off")
            ax11.text(0.5, 0.5, wait_msg, color=_MUTED, ha="center", va="center",
                      fontsize=9, transform=ax11.transAxes)
            ax12.axis("off")
            ax12.text(0.5, 0.5, wait_msg, color=_MUTED, ha="center", va="center",
                      fontsize=9, transform=ax12.transAxes)
            return

        if loading:
            msg = "Fetching operability data for charts 11–12…"
            self._draw_fetch_progress(ax11, progress[0], progress[1], msg)
            self._draw_fetch_progress(ax12, progress[0], progress[1], msg)
            return

        if operability and operability.years and operability.months_cached > 0:
            _draw_operability_heatmap(
                ax11, operability.pct_both, operability.years,
                fmt=".0f", vmin=_OPER_PCT_VMIN, vmax=_OPER_PCT_VMAX,
                cbar_label="% both criteria met",
                classify_fn=None,
            )
            src_label = "ERA5 monthly means" if is_era5 else "NCEI observations"
            cache_label = (
                f"ERA5 cache {operability.coverage_pct:.0f}% of months"
                if is_era5
                else f"NCEI cache {operability.coverage_pct:.0f}% of months"
            )
            if is_era5 and operability.thresholds:
                lim_bits = []
                _lbl = {
                    "ws": "wind", "wg": "gust", "sh": "Hs",
                    "swh": "swell Ht", "swp": "swell T",
                }
                _unit = {
                    "ws": "kt", "wg": "kt", "sh": "m",
                    "swh": "m", "swp": "s",
                }
                for p in operability.active_params or operability.thresholds:
                    v = operability.thresholds.get(p)
                    if v is None:
                        continue
                    lim_bits.append(
                        f"{_lbl.get(p, p)}≤{v:.2g}{_unit.get(p, '')}"
                    )
                lim_note = (
                    f"Limits: {', '.join(lim_bits)}  ·  "
                    f"{src_label}  ·  {cache_label}  ·  "
                    f"Optimal ≥{_go_pct():.0f}%  ·  Marginal ≥{_marg_pct():.0f}%"
                )
                title_pct = (
                    "Inter-Annual Variability — % Days All Optimal Criteria Met "
                    "(ERA5, last 10 y)\n"
                )
            else:
                lim_note = (
                    f"Limits: wind ≤ {operability.wind_limit_kts:.0f} kt, "
                    f"combined Hs ≤ {operability.hs_limit_m:.1f} m  ·  "
                    f"{src_label}  ·  {cache_label}  ·  "
                    f"Optimal ≥{_go_pct():.0f}%  ·  Marginal ≥{_marg_pct():.0f}%"
                )
                title_pct = (
                    "Inter-Annual Variability — % Observations Meeting Both Criteria\n"
                )
            ax11.set_title(title_pct + lim_note, fontsize=8, fontweight="bold")
            days_max = max(
                (v for row in operability.operable_days for v in row if v is not None),
                default=31,
            )
            _draw_operability_heatmap(
                ax12, operability.operable_days, operability.years,
                fmt=".0f", vmin=0, vmax=max(31, days_max),
                cbar_label="Est. operable days" if is_era5 else "Fully operable days",
                classify_fn=classify_days,
            )
            if is_era5:
                ax12.set_title(
                    "Estimated Operable Days per Month (from ERA5 monthly means)\n"
                    "Not hourly observations  ·  Optimal ≥25 days  ·  "
                    "Marginal ≥15 days  ·  Sub-optimal below",
                    fontsize=8, fontweight="bold",
                )
            else:
                ax12.set_title(
                    "Fully Operable Days per Month "
                    "(every report that day met both criteria)\n"
                    "Optimal ≥25 days  ·  Marginal ≥15 days  ·  Sub-optimal below",
                    fontsize=8, fontweight="bold",
                )
            return

        if progress is not None and progress[0] >= progress[1]:
            empty_msg = (
                "No operability data available for this site and year range."
            )
            ax11.axis("off")
            ax11.text(0.5, 0.5, empty_msg, color=_MUTED, ha="center", va="center",
                      fontsize=9, transform=ax11.transAxes)
            ax12.axis("off")
            ax12.text(0.5, 0.5, empty_msg, color=_MUTED, ha="center", va="center",
                      fontsize=9, transform=ax12.transAxes)
            return

        wait_msg = "Operability heatmaps appear after charts 1–10 complete."
        ax11.axis("off")
        ax11.text(0.5, 0.5, wait_msg, color=_MUTED, ha="center", va="center",
                  fontsize=9, transform=ax11.transAxes)
        ax12.axis("off")
        ax12.text(0.5, 0.5, wait_msg, color=_MUTED, ha="center", va="center",
                  fontsize=9, transform=ax12.transAxes)

    @staticmethod
    def _draw_fetch_progress(ax, done: int, total: int, title: str) -> None:
        self._operability_progress = (done, total)
        if self._profile:
            self._render_operability_panels()
            self.canvas.draw_idle()

    def update_operability_progress(self, done: int, total: int) -> None:
        self._operability_progress = (done, total)
        if self._profile:
            self._render_operability_panels()
            self.canvas.draw_idle()

    def set_operability(self, operability, climatology=None) -> None:
        self._operability = operability
        self._operability_progress = None
        self._operability_pending = False
        if climatology is not None:
            self._climatology = climatology
        if self._profile:
            self._render_operability_panels()
            self.canvas.draw_idle()

    def refresh_profile(self, profile: dict, climatology=None) -> None:
        """Re-render charts 1–10 after ERA5 cache fill (main Analysis tab)."""
        operability = self._operability
        progress = self._operability_progress
        self.set_profile(
            profile,
            operability=operability,
            operability_progress=progress,
            climatology=climatology,
            thresholds=self._thresholds,
            active_criteria=self._active_criteria,
            day_fractions=self._day_fractions,
            param_fractions=self._param_fractions,
        )


class ComparisonChartsWidget(_BaseChartCanvas):
    """Multi-site decision charts:

    1. Overlaid 12-month GO probability lines (one per site).
    2. Site × month overall GO% heatmap.
    3. Annual-mean GO% ranking bar.
    """

    def __init__(self, parent=None):
        super().__init__(parent, min_height=720, fig_inches=(10.5, 7.2))
        self._placeholder("Run a comparison to see charts.")

    def set_results(self, results: list) -> None:
        """results: list of (Site, dict[int, AnalysisResult])."""
        if not results:
            self._placeholder("Run a comparison to see charts.")
            return

        import numpy as np

        self.fig.clear()
        gs = self.fig.add_gridspec(2, 2, height_ratios=[1.0, 1.0])
        months = list(range(1, 13))

        labels = [s.name or s.coord_str for s, _ in results]
        colors = [SITE_COLORS[i % len(SITE_COLORS)] for i in range(len(results))]

        # ── Chart 1: overlaid GO lines ────────────────────────────────────────
        ax1 = self.fig.add_subplot(gs[0, :])
        _style_ax(ax1)
        for (site, profile), color, label in zip(results, colors, labels):
            vals = [profile[m].overall_prob * 100 for m in months]
            ax1.plot(months, vals, color=color, linewidth=1.8, marker="o",
                     markersize=3, label=label)
        ax1.axhline(_go_pct(), color=_GO, linestyle="--", linewidth=1, alpha=0.6)
        ax1.set_ylim(0, 100)
        ax1.set_xlim(0.5, 12.5)
        ax1.set_xticks(months)
        ax1.set_xticklabels(_MO)
        ax1.set_ylabel("GO probability (%)")
        ax1.set_title(
            "Monthly GO probability by site (ERA5 day-fraction)",
            fontsize=9, fontweight="bold",
        )
        ax1.grid(True, color=_GRID, linestyle=":", linewidth=0.5, alpha=0.5)
        leg = ax1.legend(loc="lower center", ncol=min(len(results), 4), fontsize=6,
                         facecolor=_BG, edgecolor=_GRID, labelcolor=_MUTED)
        leg.get_frame().set_alpha(0.9)

        # ── Chart 2: site × month GO% heatmap ─────────────────────────────────
        matrix = np.array([
            [profile[m].overall_prob * 100 for m in months]
            for _, profile in results
        ])
        ax2 = self.fig.add_subplot(gs[1, 0])
        _style_ax(ax2)
        im = ax2.imshow(matrix, aspect="auto", cmap=_PROB_CMAP,
                        vmin=0, vmax=100, origin="upper")
        ax2.set_xticks(range(12))
        ax2.set_xticklabels(_MO, fontsize=6)
        ax2.set_yticks(range(len(labels)))
        ax2.set_yticklabels(labels, fontsize=6)
        ax2.set_title("GO% by site and month", fontsize=9, fontweight="bold")
        for i in range(len(labels)):
            for j in range(12):
                val = matrix[i, j]
                ax2.text(j, i, f"{val:.0f}", ha="center", va="center",
                         color="#0f1923" if val >= 50 else "#f8fafc", fontsize=5)

        # ── Chart 3: annual-mean GO% ranking ──────────────────────────────────
        annual_mean = [
            sum(profile[m].overall_prob for m in months) / 12 * 100
            for _, profile in results
        ]
        order = sorted(range(len(results)), key=lambda i: annual_mean[i])
        ax3 = self.fig.add_subplot(gs[1, 1])
        _style_ax(ax3)
        y_pos = range(len(order))
        ax3.barh([i for i in y_pos],
                 [annual_mean[i] for i in order],
                 color=[colors[i] for i in order])
        ax3.set_yticks([i for i in y_pos])
        ax3.set_yticklabels([labels[i] for i in order], fontsize=6)
        ax3.set_xlim(0, 100)
        ax3.axvline(_go_pct(), color=_GO, linestyle="--", linewidth=1, alpha=0.6)
        ax3.set_title("Annual mean GO%", fontsize=9, fontweight="bold")
        for idx, i in enumerate(order):
            ax3.text(min(annual_mean[i] + 2, 92), idx, f"{annual_mean[i]:.0f}%",
                     va="center", color=_TEXT, fontsize=6)

        self.canvas.draw_idle()

"""
modules/m2_weather/operability.py — Inter-annual operability heatmaps (charts 11–12)
and monthly all-criteria day-fraction estimates (Chart 1 Historical verdict).

Historical path uses ERA5 monthly means from era5_monthly_cache. Joint % is the
product of per-parameter exceedance probabilities for every active magnitude
parameter that has a mean and a threshold (ws/wg/sh/swh/swp). Operable days are
estimated as pct/100 × days_in_month (not true hourly observations).

Charts 11–12 always use the last OPERABILITY_YEARS calendar years, independent
of the Analysis year-range spinboxes. Chart 1 day-fractions use the selected
analysis year range.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from config import DEFAULT_THRESHOLDS
from core.models import Site
from core.utils import ncei_bbox_str
from modules.m2_weather.era5_cache import get_cached_era5_month
from modules.m2_weather.ncei import get_cached_month
from modules.m3_probability.multipliers import exceedance

# Defaults aligned with config.DEFAULT_THRESHOLDS (20 kt / 6 ft Hs).
REF_WIND_KTS = float(DEFAULT_THRESHOLDS["ws"])
REF_HS_M = float(DEFAULT_THRESHOLDS["sh"])

# Charts 11–12 always cover this many recent calendar years.
OPERABILITY_YEARS = 10

# Classification bands (mirror AnalysisResult.verdict: GO ≥70%, MARGINAL ≥50%).
OPTIMAL_PCT = 70.0
MARGINAL_PCT = 50.0
OPTIMAL_DAYS = 25
MARGINAL_DAYS = 15

_MONTHS = list(range(1, 13))

# Magnitude params available from ERA5 monthly marine cache.
ERA5_CRITERIA_PARAMS: tuple[str, ...] = ("ws", "wg", "sh", "swh", "swp")
DIRECTION_CRITERIA_PARAMS: tuple[str, ...] = ("wdV", "sdV", "swdV")
ALL_CRITERIA_PARAMS: tuple[str, ...] = ERA5_CRITERIA_PARAMS + DIRECTION_CRITERIA_PARAMS

_DIRECTIONAL = frozenset({"wdV", "sdV", "swdV"})

_CACHE_MEAN_KEYS = {
    "ws": "ws_mean_kts",
    "wg": "wg_mean_kts",
    "sh": "sh_mean_m",
    "swh": "swh_mean_m",
    "swp": "swp_mean_s",
}


@dataclass
class OperabilityHeatmaps:
    """Month (1–12) × year operability grids for chart rendering."""
    years: List[int] = field(default_factory=list)
    pct_both: List[List[Optional[float]]] = field(default_factory=list)       # 12 × n_years
    operable_days: List[List[Optional[int]]] = field(default_factory=list)    # 12 × n_years
    wind_limit_kts: float = REF_WIND_KTS
    hs_limit_m: float = REF_HS_M
    months_cached: int = 0
    months_total: int = 0
    source: str = "ncei_global_marine"
    thresholds: Dict[str, float] = field(default_factory=dict)
    active_params: List[str] = field(default_factory=list)

    @property
    def coverage_pct(self) -> float:
        if self.months_total <= 0:
            return 0.0
        return round(100.0 * self.months_cached / self.months_total, 1)


def era5_operability_year_range(as_of: date | None = None) -> tuple[int, int]:
    """Last OPERABILITY_YEARS calendar years ending at as_of.year (default today)."""
    ye = (as_of or date.today()).year
    return ye - (OPERABILITY_YEARS - 1), ye


def resolve_active_criteria_params(
    thresholds: Optional[Dict[str, float]] = None,
    active_params: Optional[Iterable[str]] = None,
) -> List[str]:
    """Params that participate in all-criteria operability checks (magnitude + optional direction)."""
    thr = thresholds or DEFAULT_THRESHOLDS
    if active_params is None:
        candidates = list(ERA5_CRITERIA_PARAMS)
    else:
        ap = set(active_params)
        candidates = [p for p in ALL_CRITERIA_PARAMS if p in ap]
        if not candidates:
            candidates = [p for p in ERA5_CRITERIA_PARAMS if p in ap]
        if not candidates:
            candidates = list(ERA5_CRITERIA_PARAMS)
    return [p for p in candidates if thr.get(p) is not None and float(thr[p]) > 0]


def criteria_params_from_weights(weights: dict) -> List[str]:
    """All parameters with non-zero weight (direction included when opted in)."""
    active = [
        p for p in ALL_CRITERIA_PARAMS
        if float(weights.get(p, 0.0) or 0.0) > 0.0
    ]
    return active or list(ERA5_CRITERIA_PARAMS)


def means_from_era5_row(row: dict) -> Dict[str, float]:
    """Extract param → mean from an era5_monthly_cache row."""
    out: Dict[str, float] = {}
    for param, col in _CACHE_MEAN_KEYS.items():
        val = row.get(col)
        if val is not None:
            out[param] = float(val)
    return out


def param_criterion_prob(
    means: Dict[str, float],
    thresholds: Dict[str, float],
    param: str,
) -> Optional[float]:
    """Single-parameter probability (0.0–1.0) that criterion is met."""
    from modules.m3_probability.multipliers import directional_prob

    mean = means.get(param)
    thr = thresholds.get(param)
    if mean is None or thr is None or mean <= 0 or thr <= 0:
        return None
    if param in _DIRECTIONAL:
        return float(directional_prob(float(thr), float(mean)))
    return float(exceedance(float(thr) / float(mean)))


def param_criterion_pct(
    means: Dict[str, float],
    thresholds: Dict[str, float],
    param: str,
) -> Optional[float]:
    """Single-parameter marginal % (0–100) that criterion is met."""
    p = param_criterion_prob(means, thresholds, param)
    if p is None:
        return None
    return round(min(100.0, max(0.0, p * 100.0)), 1)


def joint_pct_all_criteria(
    means: Dict[str, float],
    thresholds: Dict[str, float],
    active_params: Sequence[str],
) -> Optional[float]:
    """
    Joint % of time all active criteria are met (independence × per-param probability).

    Magnitude params use exceedance(threshold / mean). Direction params use
    directional_prob(tolerance, variance).
    """
    probs: List[float] = []
    for param in active_params:
        p = param_criterion_prob(means, thresholds, param)
        if p is not None:
            probs.append(p)
    if not probs:
        return None
    joint = 1.0
    for p in probs:
        joint *= p
    return round(min(100.0, max(0.0, joint * 100.0)), 1)


def limiting_param_all_criteria(
    means: Dict[str, float],
    thresholds: Dict[str, float],
    active_params: Sequence[str],
) -> str:
    """Lowest per-parameter OK probability among active criteria (limiting constraint)."""
    param_probs: Dict[str, float] = {}
    for param in active_params:
        p = param_criterion_prob(means, thresholds, param)
        if p is not None:
            param_probs[param] = p
    if not param_probs:
        return ""
    return min(param_probs, key=param_probs.get)


def direction_supplemental_means(
    profile: Dict[int, object],
    active_params: Iterable[str],
) -> Optional[Dict[int, Dict[str, float]]]:
    """Effective means for direction params (not in ERA5 monthly cache)."""
    dir_params = [p for p in DIRECTION_CRITERIA_PARAMS if p in set(active_params)]
    if not dir_params:
        return None
    out: Dict[int, Dict[str, float]] = {}
    for mo, result in profile.items():
        eff = getattr(result, "effective_means", None) or {}
        chunk = {p: float(eff[p]) for p in dir_params if eff.get(p) is not None}
        if chunk:
            out[mo] = chunk
    return out or None


def monthly_all_criteria_day_fractions(
    site: Site,
    year_start: int,
    year_end: int,
    thresholds: Optional[Dict[str, float]] = None,
    active_params: Optional[Iterable[str]] = None,
    supplemental_means_by_month: Optional[Dict[int, Dict[str, float]]] = None,
) -> Dict[int, Dict[str, float]]:
    """
    Per calendar month, average across years the estimated fraction of days
    where every active criterion is met simultaneously.

    supplemental_means_by_month: optional {month: {param: mean}} merged into
    ERA5 row means (used for direction params not stored in era5_monthly_cache).

    Returns {month: {"pct": 0–100, "avg_days": float}}.
    """
    thr = dict(thresholds or DEFAULT_THRESHOLDS)
    params = resolve_active_criteria_params(thr, active_params)
    out: Dict[int, Dict[str, float]] = {}

    for mo in _MONTHS:
        pcts: List[float] = []
        days_est: List[float] = []
        for yr in range(int(year_start), int(year_end) + 1):
            row = get_cached_era5_month(site.lat, site.lon, f"{yr}-{mo:02d}-01")
            if row is None:
                continue
            means = means_from_era5_row(row)
            if supplemental_means_by_month and mo in supplemental_means_by_month:
                for pk, pv in supplemental_means_by_month[mo].items():
                    if pv is not None and pk in params:
                        means[pk] = float(pv)
            pct = joint_pct_all_criteria(means, thr, params)
            if pct is None:
                continue
            ndays = calendar.monthrange(yr, mo)[1]
            pcts.append(pct)
            days_est.append(pct / 100.0 * ndays)
        if pcts:
            out[mo] = {
                "pct": round(float(np.mean(pcts)), 1),
                "avg_days": round(float(np.mean(days_est)), 1),
            }
    return out


def monthly_per_param_criterion_fractions(
    site: Site,
    year_start: int,
    year_end: int,
    thresholds: Optional[Dict[str, float]] = None,
    active_params: Optional[Iterable[str]] = None,
    supplemental_means_by_month: Optional[Dict[int, Dict[str, float]]] = None,
) -> Dict[int, Dict[str, float]]:
    """
    Per calendar month, average across years the marginal estimated % of days
    each active criterion is met (Chart 10).

    Returns {month: {param: pct}} where pct is 0–100.
    """
    thr = dict(thresholds or DEFAULT_THRESHOLDS)
    params = resolve_active_criteria_params(thr, active_params)
    out: Dict[int, Dict[str, float]] = {}

    for mo in _MONTHS:
        by_param: Dict[str, List[float]] = {p: [] for p in params}
        for yr in range(int(year_start), int(year_end) + 1):
            row = get_cached_era5_month(site.lat, site.lon, f"{yr}-{mo:02d}-01")
            if row is None:
                continue
            means = means_from_era5_row(row)
            if supplemental_means_by_month and mo in supplemental_means_by_month:
                for pk, pv in supplemental_means_by_month[mo].items():
                    if pv is not None and pk in params:
                        means[pk] = float(pv)
            for param in params:
                pct = param_criterion_pct(means, thr, param)
                if pct is not None:
                    by_param[param].append(pct)
        chunk = {
            p: round(float(np.mean(vals)), 1)
            for p, vals in by_param.items()
            if vals
        }
        if chunk:
            out[mo] = chunk
    return out


def per_param_criterion_fractions_from_profile(
    profile: Dict[int, object],
    thresholds: Optional[Dict[str, float]] = None,
    active_params: Optional[Iterable[str]] = None,
) -> Dict[int, Dict[str, float]]:
    """45-Day / no-ERA5 fallback: marginal % from each month's effective_means."""
    thr = dict(thresholds or DEFAULT_THRESHOLDS)
    params = resolve_active_criteria_params(thr, active_params)
    out: Dict[int, Dict[str, float]] = {}
    for mo, result in profile.items():
        eff = getattr(result, "effective_means", None) or {}
        chunk: Dict[str, float] = {}
        for param in params:
            pct = param_criterion_pct(eff, thr, param)
            if pct is not None:
                chunk[param] = pct
        if chunk:
            out[int(mo)] = chunk
    return out


def apply_day_fraction_verdicts(
    profile: Dict[int, object],
    day_fractions: Dict[int, Dict[str, float]],
    *,
    thresholds: Optional[Dict[str, float]] = None,
    active_params: Optional[Iterable[str]] = None,
) -> None:
    """Overwrite AnalysisResult.overall_prob and limiting_param from day fractions."""
    thr = dict(thresholds or DEFAULT_THRESHOLDS)
    params = resolve_active_criteria_params(thr, active_params) if active_params else None
    for mo, result in profile.items():
        frac = day_fractions.get(mo)
        if frac is None:
            continue
        result.overall_prob = max(0.0, min(1.0, float(frac["pct"]) / 100.0))
        if params:
            eff = getattr(result, "effective_means", None) or {}
            limiting = limiting_param_all_criteria(eff, thr, params)
            if limiting:
                result.limiting_param = limiting


def compute_operability_from_df(
    df,
    wind_limit_kts: float = REF_WIND_KTS,
    hs_limit_m: float = REF_HS_M,
) -> Tuple[Optional[float], Optional[int]]:
    """Return (pct_both_criteria, n_fully_operable_days) from a parsed NCEI frame."""
    if df is None or len(df) == 0:
        return None, None

    work = df.copy()
    wave = work["wave_hgt_m"].astype(float)
    swell = work["swell_hgt_m"].astype(float)
    hs = np.sqrt(wave.fillna(0.0) ** 2 + swell.fillna(0.0) ** 2)
    has_wave = wave.notna() | swell.notna()
    has_wind = work["wind_speed_kts"].notna()
    both_ok = (
        has_wave & has_wind
        & (work["wind_speed_kts"] <= wind_limit_kts)
        & (hs <= hs_limit_m)
    )
    work["both_ok"] = both_ok
    if not both_ok.any():
        return None, None

    pct = round(float(both_ok.mean() * 100.0), 1)

    work["date"] = work["timestamp"].dt.date
    daily = work.groupby("date").agg(
        day_pct=("both_ok", lambda s: float(s.mean() * 100.0)),
        n_obs=("both_ok", "count"),
    )
    n_days = int(((daily["day_pct"] == 100.0) & (daily["n_obs"] >= 4)).sum())
    return pct, n_days


def _scale_pct_for_limits(
    pct_ref: float,
    ws_mean: Optional[float],
    hs_mean: Optional[float],
    wind_limit: float,
    hs_limit: float,
) -> float:
    """Adjust a reference-limit pct using monthly-mean exceedance ratios."""
    if pct_ref is None:
        return None
    if abs(wind_limit - REF_WIND_KTS) < 0.01 and abs(hs_limit - REF_HS_M) < 0.01:
        return pct_ref

    ws = float(ws_mean) if ws_mean and ws_mean > 0 else None
    wave = float(hs_mean) if hs_mean and hs_mean > 0 else None
    if ws is None or wave is None:
        return pct_ref

    p_ws_ref = exceedance(REF_WIND_KTS / ws)
    p_ws_lim = exceedance(wind_limit / ws)
    p_hs_ref = exceedance(REF_HS_M / wave)
    p_hs_lim = exceedance(hs_limit / wave)
    joint_ref = max(p_ws_ref * p_hs_ref, 1e-9)
    joint_lim = p_ws_lim * p_hs_lim
    return round(min(100.0, max(0.0, pct_ref * (joint_lim / joint_ref))), 1)


def _scale_days_for_limits(pct_ref: float, pct_adj: float, days_ref: int) -> int:
    if days_ref is None or pct_ref is None or pct_adj is None or pct_ref <= 0:
        return days_ref
    return int(round(days_ref * (pct_adj / pct_ref)))


def classify_pct(pct: Optional[float]) -> str:
    if pct is None:
        return "no_data"
    from core.verdict_thresholds import go_pct_threshold, marginal_pct_threshold
    if pct >= go_pct_threshold():
        return "optimal"
    if pct >= marginal_pct_threshold():
        return "marginal"
    return "suboptimal"


def classify_days(days: Optional[int]) -> str:
    if days is None:
        return "no_data"
    if days >= OPTIMAL_DAYS:
        return "optimal"
    if days >= MARGINAL_DAYS:
        return "marginal"
    return "suboptimal"


def build_operability_heatmaps(
    site: Site,
    year_start: int,
    year_end: int,
    wind_limit_kts: float = REF_WIND_KTS,
    hs_limit_m: float = REF_HS_M,
) -> OperabilityHeatmaps:
    """Assemble month × year grids from the NCEI monthly cache (cache-only)."""
    bbox = ncei_bbox_str(site.lat, site.lon, site.bbox_nm)
    years = list(range(int(year_start), int(year_end) + 1))
    n_years = len(years)

    pct_grid: List[List[Optional[float]]] = [[None] * n_years for _ in _MONTHS]
    days_grid: List[List[Optional[int]]] = [[None] * n_years for _ in _MONTHS]
    cached = 0
    total = 0

    for yr in years:
        y_idx = yr - years[0]
        for mo in _MONTHS:
            total += 1
            month_start = f"{yr}-{mo:02d}-01"
            row = get_cached_month(bbox, month_start)
            if row is None:
                continue

            pct_ref = row.get("pct_both_criteria")
            days_ref = row.get("n_fully_operable_days")
            if pct_ref is None and days_ref is None:
                continue

            cached += 1
            ws_mean = row.get("ws_mean_kts")
            wave_m = row.get("wave_hgt_mean_m")
            swell_m = row.get("swell_hgt_mean_m")
            if wave_m is not None or swell_m is not None:
                hs_mean = float(np.sqrt((float(wave_m or 0) ** 2 + float(swell_m or 0) ** 2)))
            else:
                hs_mean = None

            pct_adj = _scale_pct_for_limits(
                float(pct_ref) if pct_ref is not None else None,
                ws_mean, hs_mean, wind_limit_kts, hs_limit_m,
            )
            days_adj = _scale_days_for_limits(
                float(pct_ref) if pct_ref is not None else None,
                pct_adj,
                int(days_ref) if days_ref is not None else None,
            )
            pct_grid[mo - 1][y_idx] = pct_adj
            days_grid[mo - 1][y_idx] = days_adj

    return OperabilityHeatmaps(
        years=years,
        pct_both=pct_grid,
        operable_days=days_grid,
        wind_limit_kts=wind_limit_kts,
        hs_limit_m=hs_limit_m,
        months_cached=cached,
        months_total=total,
        thresholds={"ws": wind_limit_kts, "sh": hs_limit_m},
        active_params=["ws", "sh"],
    )


def build_operability_heatmaps_for_site(
    site: Site,
    wind_limit_kts: float = REF_WIND_KTS,
    hs_limit_m: float = REF_HS_M,
) -> OperabilityHeatmaps:
    """Fixed rolling OPERABILITY_YEARS window for the active site (NCEI)."""
    ys, ye = era5_operability_year_range()
    return build_operability_heatmaps(site, ys, ye, wind_limit_kts, hs_limit_m)


def _joint_pct_from_monthly_means(
    ws_mean: Optional[float],
    hs_mean: Optional[float],
    wind_limit_kts: float,
    hs_limit_m: float,
) -> Optional[float]:
    """Legacy dual-criteria helper (wind + combined Hs)."""
    return joint_pct_all_criteria(
        {"ws": ws_mean, "sh": hs_mean} if ws_mean and hs_mean else {},
        {"ws": wind_limit_kts, "sh": hs_limit_m},
        ["ws", "sh"],
    )


def build_era5_operability_heatmaps(
    site: Site,
    year_start: int,
    year_end: int,
    wind_limit_kts: float = REF_WIND_KTS,
    hs_limit_m: float = REF_HS_M,
    *,
    thresholds: Optional[Dict[str, float]] = None,
    active_params: Optional[Iterable[str]] = None,
    on_progress=None,
) -> OperabilityHeatmaps:
    """
    Month × year operability grids from era5_monthly_cache.

    Uses all active magnitude parameters (default ws/wg/sh/swh/swp) with the
    supplied optimal thresholds. pct_both is joint exceedance; operable_days is
    pct/100 × days_in_month.
    """
    thr = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        thr.update({k: float(v) for k, v in thresholds.items() if v is not None})
    # Backward-compat kwargs override ws/sh when explicit thresholds omitted.
    if thresholds is None:
        thr["ws"] = wind_limit_kts
        thr["sh"] = hs_limit_m

    params = resolve_active_criteria_params(thr, active_params)
    years = list(range(int(year_start), int(year_end) + 1))
    n_years = len(years)
    pct_grid: List[List[Optional[float]]] = [[None] * n_years for _ in _MONTHS]
    days_grid: List[List[Optional[int]]] = [[None] * n_years for _ in _MONTHS]
    cached = 0
    total = n_years * len(_MONTHS)
    done = 0

    for yr in years:
        y_idx = yr - years[0]
        for mo in _MONTHS:
            done += 1
            if on_progress:
                on_progress(done, total, "Building operability heatmaps…")

            month_start = f"{yr}-{mo:02d}-01"
            row = get_cached_era5_month(site.lat, site.lon, month_start)
            if row is None:
                continue

            means = means_from_era5_row(row)
            if not means:
                continue

            cached += 1
            pct = joint_pct_all_criteria(means, thr, params)
            pct_grid[mo - 1][y_idx] = pct
            if pct is not None:
                ndays = calendar.monthrange(yr, mo)[1]
                days_grid[mo - 1][y_idx] = int(round(pct / 100.0 * ndays))

    return OperabilityHeatmaps(
        years=years,
        pct_both=pct_grid,
        operable_days=days_grid,
        wind_limit_kts=float(thr.get("ws", REF_WIND_KTS)),
        hs_limit_m=float(thr.get("sh", REF_HS_M)),
        months_cached=cached,
        months_total=total,
        source="era5_reanalysis",
        thresholds={p: float(thr[p]) for p in params},
        active_params=list(params),
    )

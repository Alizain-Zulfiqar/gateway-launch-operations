"""
modules/m3_probability/compare_sites.py — ERA5-backed multi-site comparison.

Mirrors Main Analysis Historical for each site:

  Phase A (charts 1–10 / ranking):
    ensure_era5_cache → build_monthly_climatology → compute_annual_profile
    → monthly_all_criteria_day_fractions → apply_day_fraction_verdicts

  Phase B (charts 11–12):
    ensure_era5_cache for last OPERABILITY_YEARS → build_era5_operability_heatmaps
"""
from __future__ import annotations

from typing import Callable, Optional

from config import DEFAULT_THRESHOLDS, DEFAULT_WEIGHTS
from core.models import Platform, Site, Vehicle
from modules.m2_weather.climatology import MonthlyClimatology, build_monthly_climatology
from modules.m2_weather.era5_ensure import ensure_era5_cache
from modules.m2_weather.operability import (
    apply_day_fraction_verdicts,
    build_era5_operability_heatmaps,
    criteria_params_from_weights,
    direction_supplemental_means,
    era5_operability_year_range,
    monthly_all_criteria_day_fractions,
    monthly_per_param_criterion_fractions,
)
from modules.m3_probability.engine import compute_annual_profile

ProgressCallback = Callable[[int, int, str], None]


def compare_site_era5(
    site: Site,
    vehicle: Vehicle,
    platform: Platform,
    year_start: int,
    year_end: int,
    *,
    thresholds: Optional[dict] = None,
    weights: Optional[dict] = None,
    on_progress: ProgressCallback | None = None,
) -> tuple[dict, MonthlyClimatology, object, dict, dict]:
    """
    Run one site through the same ERA5 Historical path as Main Analysis.

    Returns (profile, MonthlyClimatology, OperabilityHeatmaps, day_fractions,
    param_fractions).
    Raises RuntimeError if Phase A ERA5 cache cannot be completed.
    Phase B cache failure still returns heatmaps from whatever is cached.
    """
    thr = dict(thresholds or DEFAULT_THRESHOLDS)
    wts = dict(weights or DEFAULT_WEIGHTS)
    wind_kts = float(thr.get("ws", DEFAULT_THRESHOLDS["ws"]))
    hs_m = float(thr.get("sh", DEFAULT_THRESHOLDS["sh"]))
    criteria = criteria_params_from_weights(wts)
    label = site.name or site.coord_str

    # ── Phase A: charts 1–10 ──────────────────────────────────────────────────
    if on_progress:
        on_progress(-1, 0, f"{label}: ensuring ERA5 for charts 1–10…")

    ok, err = ensure_era5_cache(
        site.lat, site.lon, year_start, year_end, on_progress=on_progress,
    )
    if not ok:
        raise RuntimeError(
            err or f"ERA5 fetch failed for {label}."
        )

    if on_progress:
        on_progress(-1, 0, f"{label}: analyzing 12-month profile…")

    climatology = build_monthly_climatology(
        site, year_start, year_end, wind_kts, hs_m,
    )
    profile = compute_annual_profile(
        site,
        vehicle,
        platform,
        year_start=year_start,
        year_end=year_end,
        weights=wts,
        mode="historical",
        observed_means_by_month=climatology.by_month,
        thresholds_override=thr,
    )
    supplemental = direction_supplemental_means(profile, criteria)
    day_frac = monthly_all_criteria_day_fractions(
        site,
        year_start,
        year_end,
        thresholds=thr,
        active_params=criteria,
        supplemental_means_by_month=supplemental,
    )
    param_frac = monthly_per_param_criterion_fractions(
        site,
        year_start,
        year_end,
        thresholds=thr,
        active_params=criteria,
        supplemental_means_by_month=supplemental,
    )
    apply_day_fraction_verdicts(
        profile, day_frac, thresholds=thr, active_params=criteria,
    )

    # ── Phase B: charts 11–12 (last 10 calendar years) ────────────────────────
    op_ys, op_ye = era5_operability_year_range()

    def _op_progress(done: int, total: int, detail: str) -> None:
        if on_progress:
            on_progress(done, total, f"{label}: {detail}")

    if on_progress:
        on_progress(
            -1, 0,
            f"{label}: ensuring ERA5 for charts 11–12 ({op_ys}–{op_ye})…",
        )

    ok_op, err_op = ensure_era5_cache(
        site.lat, site.lon, op_ys, op_ye, on_progress=_op_progress,
    )
    if not ok_op and on_progress:
        on_progress(
            -1, 0,
            f"{label}: charts 11–12 cache incomplete — "
            f"{err_op or 'using whatever months are cached'}",
        )

    if on_progress:
        on_progress(-1, 0, f"{label}: building operability heatmaps (charts 11–12)…")

    operability = build_era5_operability_heatmaps(
        site,
        op_ys,
        op_ye,
        wind_kts,
        hs_m,
        thresholds=thr,
        active_params=criteria,
        on_progress=_op_progress,
    )
    return profile, climatology, operability, day_frac, param_frac

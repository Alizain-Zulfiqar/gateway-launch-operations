"""
modules/m3_probability/engine.py

Core launch window probability computation engine.
Pure functions — no DB access, no UI calls.

Entry point: compute_probability()
"""
from typing import Dict, Optional
from config import DEFAULT_WEIGHTS, era_weight as calc_era_weight
from core.models import AnalysisResult, Site, Vehicle, Platform
from core.utils import lat_to_band, band_label, fmt_prob
from modules.m3_probability.multipliers import (
    PARAM_NAMES, effective_mean, exceedance, directional_prob
)

DIRECTIONAL_PARAMS = {"wdV", "sdV", "swdV"}


def normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    """Normalize weights dict so values sum to 1.0."""
    total = sum(weights.values())
    if total <= 0:
        return {k: 1.0 / len(weights) for k in weights}
    return {k: v / total for k, v in weights.items()}


def compute_probability(
    site: Site,
    vehicle: Vehicle,
    platform: Platform,
    month: int,                              # 1-indexed
    year_start: Optional[int] = 1960,
    year_end:   Optional[int] = 2024,
    weights: Optional[Dict[str, float]] = None,
    mode: str = "historical",
    observed_means: Optional[Dict[str, dict]] = None,
    observed_means_by_month: Optional[Dict[int, Dict[str, dict]]] = None,
    platform_contract: Optional["PlatformContract"] = None,
    thresholds_override: Optional[Dict[str, float]] = None,
) -> AnalysisResult:
    """
    Compute launch window probability for a site/vehicle/platform/month combination.

    Parameters
    ----------
    site           : Site dataclass with lat, lon, bbox_nm
    vehicle        : Vehicle dataclass with thresholds and vehicle_class
    platform       : Platform dataclass with hull_type and hull_motion_factor
    month          : Analysis month (1=Jan … 12=Dec)
    year_start     : Start year for historical analysis (ignored in 45day mode)
    year_end       : End year for historical analysis
    weights        : Parameter weights dict. Defaults to config.DEFAULT_WEIGHTS
    mode           : '45day' or 'historical'
    observed_means : Optional dict keyed by parameter shortname, as returned by
                     data_manager.get_site_weather_summary(). Each value is a dict
                     with keys 'mean', 'p90', 'source', 'station_id'. When a
                     parameter entry has a non-None 'mean', that observed value
                     replaces the ICOADS climatological base for the effective-mean
                     calculation. Hull/vehicle/recovery multipliers still apply.

    Returns
    -------
    AnalysisResult dataclass with all computed values
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS.copy()

    if observed_means is None:
        observed_means = {}

    if observed_means_by_month is None:
        observed_means_by_month = {}

    nw = normalize_weights(weights)
    thresholds = vehicle.thresholds()
    if thresholds_override:
        # User-supplied "optimal values" override the vehicle defaults on a
        # per-parameter basis; any parameter left as None falls back to the
        # vehicle's own threshold (the system default).
        thresholds = {
            **thresholds,
            **{k: v for k, v in thresholds_override.items() if v is not None},
        }
    era_wt = calc_era_weight(year_start or 1960, year_end or 2024)
    era_var = 1 + (1 - era_wt) * 0.20   # effective variability inflation

    param_probs: Dict[str, float] = {}
    eff_means:   Dict[str, float] = {}
    data_sources: Dict[str, str]  = {}

    for param in PARAM_NAMES:
        thresh = thresholds.get(param, 0.0)
        month_obs = observed_means_by_month.get(month) or {}
        obs = month_obs.get(param) if param in month_obs else observed_means.get(param, {})
        obs_mean = obs.get("mean") if obs else None

        if obs_mean is not None:
            # Observed data available: use it as the base, then apply the
            # same hull / vehicle-class / recovery multipliers as the model
            # path so platform and vehicle constraints are still reflected.
            from modules.m3_probability.multipliers import (
                hull_factor, vehicle_class_mod, recovery_mod
            )
            hf = hull_factor(platform.hull_type, param)
            vc = vehicle_class_mod(vehicle.vehicle_class, param)
            rm = recovery_mod(vehicle.recovery_mode, param)
            eff = obs_mean * hf * vc * rm
            data_sources[param] = obs.get("source", "ndbc_realtime")
        else:
            eff = effective_mean(
                lat               = site.lat,
                lon               = site.lon,
                month             = month,
                param             = param,
                hull_type         = platform.hull_type,
                vehicle_class     = vehicle.vehicle_class,
                recovery_mode_val = vehicle.recovery_mode,
                era_wt            = era_wt,
            )
            data_sources[param] = "icoads_model"

        eff_means[param] = eff

        if param in DIRECTIONAL_PARAMS:
            p = directional_prob(thresh, eff)
        else:
            ratio = thresh / max(0.01, eff)
            p = exceedance(ratio)

        param_probs[param] = p

    # Weighted sum
    overall = sum(param_probs[p] * nw.get(p, 0.0) for p in PARAM_NAMES)
    overall = min(0.97, max(0.04, overall))

    # Parameters that actually contributed to the result (non-zero weight).
    active_params = {p for p in PARAM_NAMES if nw.get(p, 0.0) > 0.0}

    # Limiting parameter = lowest-probability CONTRIBUTING parameter. Excluded
    # (zero-weight) direction params must not surface as the limiting parameter
    # even when their raw probability is naturally low.
    if active_params:
        limiting = min(active_params, key=lambda p: param_probs[p])
    else:
        # Defensive fallback: should never happen with valid weights, but
        # prevents a crash if every weight is somehow zero.
        limiting = min(param_probs, key=param_probs.get)

    # Confidence rating
    if era_wt >= 0.95:
        confidence = "high"
    elif era_wt >= 0.85:
        confidence = "moderate"
    elif era_wt >= 0.72:
        confidence = "low"
    else:
        confidence = "model"

    # Vessel pre-check gate (Pre-28B-1) — only runs when a contract is linked.
    vessel_verdict = None
    vessel_limiting_param = None
    vessel_param_probs: Dict[str, float] = {}
    vessel_contract_code = None
    warranted_verified = False
    if platform_contract is not None:
        from modules.m1_site.contracts import (
            resolve_warranted_envelope, apply_vessel_gate,
        )
        warranted, vessel_contract_code = resolve_warranted_envelope(
            platform_contract.id
        )
        vessel_param_probs, vessel_verdict, vessel_limiting_param = apply_vessel_gate(
            warranted, thresholds, param_probs, active_params, eff_means=eff_means,
        )
        warranted_verified = bool(
            getattr(platform_contract, "warranted_verified", False)
        )

    return AnalysisResult(
        site             = site,
        vehicle          = vehicle,
        platform         = platform,
        mode             = mode,
        overall_prob     = overall,
        param_probs      = param_probs,
        limiting_param   = limiting,
        data_sources     = data_sources,
        effective_means  = eff_means,
        thresholds       = thresholds,
        weights          = nw,
        active_params    = active_params,
        era_weight       = era_wt,
        confidence_rating= confidence,
        year_start       = year_start,
        year_end         = year_end,
        month_filter     = month,
        vessel_verdict        = vessel_verdict,
        vessel_limiting_param = vessel_limiting_param,
        vessel_param_probs    = vessel_param_probs,
        vessel_contract_code  = vessel_contract_code,
        warranted_verified    = warranted_verified,
    )


def compute_annual_profile(
    site: Site,
    vehicle: Vehicle,
    platform: Platform,
    year_start: Optional[int] = 1960,
    year_end:   Optional[int] = 2024,
    weights: Optional[Dict[str, float]] = None,
    platform_contract: Optional["PlatformContract"] = None,
    mode: str = "historical",
    observed_means: Optional[Dict[str, dict]] = None,
    observed_means_by_month: Optional[Dict[int, Dict[str, dict]]] = None,
    thresholds_override: Optional[Dict[str, float]] = None,
) -> Dict[int, AnalysisResult]:
    """
    Compute probability for all 12 months. Returns dict keyed by month (1–12).

    mode/observed_means pass straight through to compute_probability() for
    every month (Set 34, item 14) — '45day' mode uses one live NDBC/near-term
    snapshot (observed_means, typically from
    data_manager.get_site_weather_summary(site, mode='45day')) applied
    uniformly across all 12 months, since it represents current conditions
    rather than a month-specific climatology; year_start/year_end are ignored
    by compute_probability() in that mode, same as for a single-month run.
    """
    return {
        month: compute_probability(
            site       = site,
            vehicle    = vehicle,
            platform   = platform,
            month      = month,
            year_start = year_start,
            year_end   = year_end,
            weights    = weights,
            platform_contract = platform_contract,
            mode           = mode,
            observed_means = observed_means,
            observed_means_by_month = observed_means_by_month,
            thresholds_override = thresholds_override,
        )
        for month in range(1, 13)
    }


def best_launch_months(
    annual_profile: Dict[int, AnalysisResult],
    go_threshold: float = 0.70,
) -> list:
    """
    Return list of (month, probability) tuples sorted by probability descending,
    filtered to months at or above go_threshold.
    """
    results = [
        (month, r.overall_prob)
        for month, r in annual_profile.items()
        if r.overall_prob >= go_threshold
    ]
    return sorted(results, key=lambda x: x[1], reverse=True)


def annual_go_fraction(
    annual_profile: Dict[int, AnalysisResult],
    go_threshold: float = 0.70,
) -> float:
    """Return the fraction of months (0.0–1.0) that meet or exceed go_threshold."""
    go_months = sum(
        1 for r in annual_profile.values()
        if r.overall_prob >= go_threshold
    )
    return go_months / 12.0


def compute_probability_from_observed(
    vehicle: Vehicle,
    platform: Platform,
    observed_means: Dict[str, Optional[float]],
    fallback_result: AnalysisResult,
) -> AnalysisResult:
    """
    Compute probability using raw observed NDBC means where available.

    observed_means: mapping from engine param shortname to raw float value or None.
        {"ws": 10.0, "wg": 14.0, "sh": 1.2, "swh": 0.8, "swp": 8.0}
    Directional params (wdV, sdV, swdV) always fall back to climate.
    Missing params fall back to climate model via fallback_result site/month.

    Hull motion and vehicle-class/recovery modifiers are applied to every
    observed value by the existing compute_probability() engine path.
    """
    obs_dict: Dict[str, dict] = {
        param: {"mean": val, "source": "ndbc_realtime"}
        for param, val in observed_means.items()
        if val is not None and param not in DIRECTIONAL_PARAMS
    }
    return compute_probability(
        site           = fallback_result.site,
        vehicle        = vehicle,
        platform       = platform,
        month          = fallback_result.month_filter or 1,
        year_start     = fallback_result.year_start,
        year_end       = fallback_result.year_end,
        weights        = fallback_result.weights,
        mode           = "observed",
        observed_means = obs_dict,
    )


def summary_text(result: AnalysisResult) -> str:
    """Return a plain-text one-paragraph summary of an analysis result."""
    from core.utils import month_name, band_label, lat_to_band
    mo = month_name(result.month_filter or 0)
    band = band_label(lat_to_band(result.site.lat))
    return (
        f"Analysis for {result.site.name or result.site.coord_str} — "
        f"{result.vehicle.name} on {result.platform.name}. "
        f"Month: {mo}. Latitude band: {band}. "
        f"Overall launch window probability: {result.pct}% ({result.verdict}). "
        f"Limiting parameter: {result.limiting_param} "
        f"({round(result.param_probs[result.limiting_param]*100)}%). "
        f"ERA weight: {result.era_weight:.2f} ({result.confidence_rating} confidence). "
        f"Data basis: NOAA ICOADS C00606 climatological model."
    )

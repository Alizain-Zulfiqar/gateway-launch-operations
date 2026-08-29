"""
modules/m3_probability/multipliers.py

All multiplier functions for the probability engine.
Each function is pure — no side effects, no DB access.

Multiplier chain:
  Eff_Mean[i] = Base[i] × Season_Mod[i] × Era_Var × Hull_Factor × VC_Mod[i] × Rec_Mod
  Param_Prob[i] = exceedance(Threshold[i] / Eff_Mean[i])
  Window_Prob = sum(Param_Prob[i] × NormWeight[i])
"""
from config import (
    CLIMATE_BASE, SEASONAL_MOD, PARAM_INDICES,
    HULL_MOTION_FACTOR, VEHICLE_CLASS_MOD, RECOVERY_MOD,
    SEA_STATE_PARAMS, WIND_PARAMS, EXCEEDANCE_TABLE,
    APPLY_VEHICLE_MODIFIERS,
)
from core.utils import lat_to_band
from typing import Dict


PARAM_NAMES = ["ws","wg","sh","swh","swp","wdV","sdV","swdV"]


def climate_base(lat: float) -> Dict[str, float]:
    """Return ICOADS climatological base values for the latitude band."""
    return CLIMATE_BASE[lat_to_band(lat)]


def seasonal_mod(month: int) -> list:
    """
    Return seasonal modifier list for month (1-indexed).
    Index matches PARAM_INDICES order: ws, wg, sh, swh, swp, wdV, sdV, swdV
    """
    if not 1 <= month <= 12:
        raise ValueError(f"Month must be 1–12, got {month}")
    return SEASONAL_MOD[month - 1]


def era_variability(era_wt: float) -> float:
    """
    Sparser data eras increase effective variability.
    era_wt = 1.0 → no variability inflation.
    era_wt = 0.72 → 5.6% inflation of effective mean.
    """
    return 1 + (1 - era_wt) * 0.20


def hull_factor(hull_type: str, param: str) -> float:
    """
    Return hull motion factor. Applied ONLY to wave HEIGHT params (sh, swh).

    Swell period (swp) is excluded — hull motion changes the vessel's response
    to a given sea state, not the wave period itself. Wind parameters always
    return 1.0.
    """
    if param in ("sh", "swh"):
        return HULL_MOTION_FACTOR.get(hull_type, 1.00)
    return 1.0


def vehicle_class_mod(vehicle_class: str, param: str) -> float:
    """
    Return vehicle class modifier for a given parameter.
    Only defined for ws, wg, sh, swh — other params return 1.0.

    Returns 1.0 unconditionally when config.APPLY_VEHICLE_MODIFIERS is False,
    so the vehicle's class does not influence the analysis (the run then
    depends purely on the parameter threshold values + location climatology).
    """
    if not APPLY_VEHICLE_MODIFIERS:
        return 1.0
    mods = VEHICLE_CLASS_MOD.get(vehicle_class, {})
    return mods.get(param, 1.0)


def recovery_mod(recovery_mode: str, param: str) -> float:
    """
    Return recovery mode modifier. Applied ONLY to wind params (ws, wg).
    All other parameters return 1.0.

    Returns 1.0 unconditionally when config.APPLY_VEHICLE_MODIFIERS is False
    (see vehicle_class_mod).
    """
    if not APPLY_VEHICLE_MODIFIERS:
        return 1.0
    if param in WIND_PARAMS:
        return RECOVERY_MOD.get(recovery_mode, 1.0)
    return 1.0


def lon_basin_mod(lon: float, param: str) -> float:
    """
    Ocean basin modifier. Pacific is ~10% calmer than Atlantic at same latitude.
    Applied to wind and wave parameters (not direction tolerances).
    """
    if param in ("wdV", "sdV", "swdV"):
        return 1.0
    # Normalize lon to -180..180
    l = ((lon % 360) + 540) % 360 - 180
    if l >= 120 or (l <= -90 and l >= -180):
        basin = "pacific"
    elif 20 <= l < 120:
        basin = "indian"
    else:
        basin = "atlantic"
    if basin == "pacific":
        return 0.90
    if basin == "indian":
        return 0.95
    return 1.00


def effective_mean(
    lat: float,
    lon: float,
    month: int,          # 1-indexed
    param: str,
    hull_type: str,
    vehicle_class: str,
    recovery_mode_val: str,
    era_wt: float = 1.0,
) -> float:
    """
    Compute effective climatological mean for a single parameter.

    Formula:
        Eff_Mean = Base × Season_Mod × Era_Var × Hull_Factor × VC_Mod × Rec_Mod × Basin_Mod
    """
    base = climate_base(lat)
    sm   = seasonal_mod(month)
    idx  = PARAM_INDICES.get(param)
    if idx is None:
        raise ValueError(f"Unknown parameter: {param}")

    b    = base[param]
    s    = sm[idx]
    ev   = era_variability(era_wt)
    hf   = hull_factor(hull_type, param)
    vc   = vehicle_class_mod(vehicle_class, param)
    rm   = recovery_mod(recovery_mode_val, param)
    bm   = lon_basin_mod(lon, param)

    return b * s * ev * hf * vc * rm * bm


def exceedance(ratio: float) -> float:
    """
    Map threshold/mean ratio to exceedance probability.
    Uses the lookup table from config.EXCEEDANCE_TABLE.
    """
    for threshold_ratio, prob in EXCEEDANCE_TABLE:
        if ratio >= threshold_ratio:
            return prob
    return 0.08


def directional_prob(tolerance_deg: float, variance_deg: float) -> float:
    """
    Probability that prevailing direction falls within ±tolerance_deg.
    variance_deg = climatological directional spread for that parameter.
    """
    if variance_deg <= 0:
        return 1.0
    p = (tolerance_deg / 2.0) / max(1.0, variance_deg)
    return min(0.97, max(0.05, p))

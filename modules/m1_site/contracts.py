"""
modules/m1_site/contracts.py — Platform contract hierarchy traversal and the
Option 2 vessel pre-check gate (Pre-28B-1).

Single source of truth for resolving which warranted operating envelope governs
a specific mission, and for comparing that envelope against vehicle thresholds.
"""
from __future__ import annotations

import logging
from typing import Optional

from core.database import get_connection
from core.models import PlatformContract

logger = logging.getLogger(__name__)

# Verdict thresholds (per-parameter), matching AnalysisResult.verdict.
_GO_MIN       = 0.70
_MARGINAL_MIN = 0.45


def get_contract(contract_id: int) -> Optional[PlatformContract]:
    """Fetch a single PlatformContract by id. Returns None if not found."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM platform_contracts WHERE id = ?", (contract_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    d = dict(row)
    return PlatformContract(
        id=d["id"],
        platform_id=d["platform_id"],
        vessel_code=d["vessel_code"],
        contract_code=d["contract_code"],
        customer_name=d["customer_name"],
        contract_tier=d.get("contract_tier", "master"),
        parent_contract_id=d.get("parent_contract_id"),
        contract_start=d["contract_start"],
        contract_end=d["contract_end"],
        status=d.get("status", "active"),
        warranted_max_wind_kts=d.get("warranted_max_wind_kts"),
        warranted_max_gust_kts=d.get("warranted_max_gust_kts"),
        warranted_max_hs_m=d.get("warranted_max_hs_m"),
        warranted_max_swell_ht_m=d.get("warranted_max_swell_ht_m"),
        warranted_max_swell_period_s=d.get("warranted_max_swell_period_s"),
        warranted_verified=bool(d.get("warranted_verified", 0)),
        warranted_verified_by=d.get("warranted_verified_by"),
        warranted_verified_date=d.get("warranted_verified_date"),
        warranted_source_doc=d.get("warranted_source_doc"),
        document_url=d.get("document_url"),
        document_unc_path=d.get("document_unc_path"),
        notes=d.get("notes"),
        created_at=d.get("created_at"),
        updated_at=d.get("updated_at"),
        is_archived=bool(d.get("is_archived", 0)),
    )


def resolve_warranted_envelope(contract_id: int) -> tuple[dict, str]:
    """
    Walk the contract hierarchy upward from *contract_id* toward the master
    contract, returning (envelope, contract_code).

    Most-specific-wins: for each parameter, the value from the most specific
    contract in the chain that specifies a non-NULL limit is used. Parameters
    that no contract specifies are absent (engine falls back to the vehicle
    threshold for those). Cycles are detected and terminate the walk.
    """
    resolved: dict = {}
    visited: set = set()
    current_id = contract_id
    contract_code = ""

    while current_id is not None:
        if current_id in visited:
            logger.warning(
                "Cycle detected in contract hierarchy at id=%s. "
                "Stopping traversal.", current_id
            )
            break
        visited.add(current_id)

        contract = get_contract(current_id)
        if contract is None:
            break

        if not contract_code:
            contract_code = contract.contract_code

        # Most specific contract wins → only fill params not yet resolved.
        for param, val in contract.warranted_envelope().items():
            if param not in resolved:
                resolved[param] = val

        current_id = contract.parent_contract_id

    return resolved, contract_code


def _verdict_from(probs: dict, active_params: set) -> tuple[Optional[str], Optional[str]]:
    """Return (verdict, limiting_param) from per-parameter probabilities,
    restricted to active_params (same filter as the Pre-28B-3 vehicle fix)."""
    considered = [p for p in active_params if p in probs]
    if not considered:
        return None, None
    limiting = min(considered, key=lambda p: probs[p])
    lowest = probs[limiting]
    if all(probs[p] >= _GO_MIN for p in considered):
        verdict = "GO"
    elif lowest >= _MARGINAL_MIN:
        verdict = "MARGINAL"
    else:
        verdict = "NO-GO"
    return verdict, limiting


def apply_vessel_gate(
    warranted_envelope: dict,
    vehicle_thresholds: dict,
    param_probs: dict,
    active_params: set,
    eff_means: Optional[dict] = None,
) -> tuple[dict, Optional[str], Optional[str]]:
    """
    Option 2 vessel pre-check gate. For each active parameter the governing
    limit is the MORE CONSERVATIVE of the vessel warranted limit and the vehicle
    threshold (this safety rule is vessel↔vehicle only, not master↔subcontract).

    Returns (vessel_param_probs, vessel_verdict, vessel_limiting_param).

    When *eff_means* is supplied (engine path) a tightened magnitude limit is
    re-scored exactly via the exceedance table; otherwise a monotonic proxy
    (probability scaled by governing/threshold) is used. Direction parameters are
    never warranted at vessel level, so they pass through unchanged.

    If *warranted_envelope* is empty, the vehicle probabilities pass through
    unchanged and the verdict/limiting reflect those.
    """
    from modules.m3_probability.multipliers import exceedance

    vessel_param_probs: dict = {}
    for param in active_params:
        base = param_probs.get(param, 0.0)
        v_thr = vehicle_thresholds.get(param)
        w_lim = warranted_envelope.get(param)

        # No vessel limit for this param, or vehicle already at/under it → unchanged.
        if w_lim is None or v_thr is None or w_lim >= v_thr:
            vessel_param_probs[param] = base
            continue

        # Vessel is tighter → re-score against the vessel limit.
        if eff_means and eff_means.get(param):
            ratio = w_lim / max(0.01, eff_means[param])
            vessel_param_probs[param] = exceedance(ratio)
        else:
            vessel_param_probs[param] = max(0.0, min(1.0, base * (w_lim / v_thr)))

    verdict, limiting = _verdict_from(vessel_param_probs, active_params)
    return vessel_param_probs, verdict, limiting

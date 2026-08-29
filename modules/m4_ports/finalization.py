"""
modules/m4_ports/finalization.py — voyage estimate finalization and actuals tracking.

One row per (project_id, site_id).  Finalize snapshots VoyageCostParams + the
computed breakdown; actuals use the same JSON shape for estimate-vs-actual compare.
"""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.database import get_connection
from core.models import FEE_CATEGORIES, Site
from modules.m4_ports.voyage import VoyageCostBreakdown, VoyageCostParams, serialize_breakdown


class FinalizationError(Exception):
    """Raised when finalize/save preconditions fail."""


@dataclass
class VoyageFinalization:
    id: int
    project_id: int
    site_id: int
    load_port_id: int
    finalized_at: str
    notes: str
    estimate_params: dict
    estimate_breakdown: dict
    actual_breakdown: Optional[dict]
    actual_entered_at: Optional[str]
    load_port_name: str = ""
    site_name: str = ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def _row_to_finalization(row) -> VoyageFinalization:
    return VoyageFinalization(
        id=row["id"],
        project_id=row["project_id"],
        site_id=row["site_id"],
        load_port_id=row["load_port_id"],
        finalized_at=row["finalized_at"] or "",
        notes=row["notes"] or "",
        estimate_params=json.loads(row["estimate_params_json"]),
        estimate_breakdown=json.loads(row["estimate_breakdown_json"]),
        actual_breakdown=(
            json.loads(row["actual_breakdown_json"])
            if row["actual_breakdown_json"]
            else None
        ),
        actual_entered_at=row["actual_entered_at"],
        load_port_name=row["load_port_name"] or "",
        site_name=row["site_name"] or "",
    )


def recompute_breakdown_totals(data: dict) -> dict:
    """Recompute charter/fuel/total fields from editable inputs in a breakdown dict."""
    out = deepcopy(data)
    transit = float(out.get("total_transit_days") or 0.0)
    onsite = float(out.get("total_onsite_days") or 0.0)
    launches = int(out.get("launches") or 1)
    if launches < 1:
        launches = 1

    charter_total = 0.0
    fuel_total = 0.0
    underway_gal = 0.0
    onsite_gal = 0.0

    vessels = out.get("vessels") or []
    for v in vessels:
        deployed = bool(v.get("deployed"))
        if not deployed:
            v["charter_usd"] = 0.0
            v["underway_gal"] = 0.0
            v["onsite_gal"] = 0.0
            v["total_gal"] = 0.0
            v["fuel_usd"] = 0.0
            continue

        charter_days = float(v.get("charter_days") or 0.0)
        charter_rate = float(v.get("charter_rate_usd_day") or 0.0)
        at_sea = float(v.get("at_sea_gal_day") or 0.0)
        in_port = float(v.get("in_port_gal_day") or 0.0)
        fuel_rate = float(v.get("fuel_usd_gal") or 0.0)

        v_charter = round(charter_days * charter_rate, 2)
        v_underway = round(transit * at_sea, 2)
        v_onsite = round(onsite * in_port, 2)
        v_gal = round(v_underway + v_onsite, 2)
        v_fuel = round(v_gal * fuel_rate, 2)

        v["charter_usd"] = v_charter
        v["underway_gal"] = v_underway
        v["onsite_gal"] = v_onsite
        v["total_gal"] = v_gal
        v["fuel_usd"] = v_fuel

        charter_total += v_charter
        fuel_total += v_fuel
        underway_gal += v_underway
        onsite_gal += v_onsite

    port_fees_total = 0.0
    for pf in out.get("port_fees") or []:
        total = 0.0
        for cat in FEE_CATEGORIES:
            total += float(pf.get(f"{cat}_usd") or 0.0)
        pf["total_usd"] = round(total, 2)
        port_fees_total += pf["total_usd"]

    charter_total = round(charter_total, 2)
    port_fees_total = round(port_fees_total, 2)
    fuel_total = round(fuel_total, 2)
    fuel_total_gal = round(underway_gal + onsite_gal, 2)
    total_usd = round(charter_total + port_fees_total + fuel_total, 2)
    voyage_days = round(transit + onsite, 4)
    cost_per_launch = round(total_usd / launches, 2)

    out["charter_total_usd"] = charter_total
    out["port_fees_total_usd"] = port_fees_total
    out["fuel_total_usd"] = fuel_total
    out["underway_gal"] = round(underway_gal, 2)
    out["onsite_gal"] = round(onsite_gal, 2)
    out["fuel_total_gal"] = fuel_total_gal
    out["total_usd"] = total_usd
    out["voyage_days"] = voyage_days
    out["launches"] = launches
    out["cost_per_launch_usd"] = cost_per_launch
    out["vessels"] = vessels
    return out


def copy_estimate_for_actuals(estimate: dict, params: Optional[dict] = None) -> dict:
    """Deep copy estimate breakdown as starting point for actual entry."""
    out = deepcopy(estimate)
    if params:
        param_vessels = {v.get("key"): v for v in (params.get("vessels") or [])}
        for v in out.get("vessels") or []:
            pv = param_vessels.get(v.get("key"), {})
            v.setdefault("at_sea_gal_day", float(pv.get("at_sea_gal_day") or 0.0))
            v.setdefault("in_port_gal_day", float(pv.get("in_port_gal_day") or 0.0))
    return recompute_breakdown_totals(out)


def finalize_voyage(
    project_id: int,
    site: Site,
    port_id: int,
    params: VoyageCostParams,
    breakdown: VoyageCostBreakdown,
    notes: str = "",
) -> VoyageFinalization:
    if not project_id:
        raise FinalizationError("An active project is required to finalize a port.")
    if not site or site.id is None:
        raise FinalizationError("A saved site is required to finalize a port.")
    if not port_id:
        raise FinalizationError("A load port must be selected.")

    params_json = json.dumps(params.to_dict())
    breakdown_json = json.dumps(serialize_breakdown(breakdown))
    now = _utc_now()

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO voyage_finalizations (
                project_id, site_id, load_port_id, finalized_at, notes,
                estimate_params_json, estimate_breakdown_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, site_id) DO UPDATE SET
                load_port_id = excluded.load_port_id,
                finalized_at = excluded.finalized_at,
                notes = excluded.notes,
                estimate_params_json = excluded.estimate_params_json,
                estimate_breakdown_json = excluded.estimate_breakdown_json,
                actual_breakdown_json = NULL,
                actual_entered_at = NULL
            """,
            (
                project_id,
                site.id,
                port_id,
                now,
                notes or "",
                params_json,
                breakdown_json,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    row = get_finalization(project_id, site.id)
    if row is None:
        raise FinalizationError("Failed to persist voyage finalization.")
    return row


def get_finalization(project_id: int, site_id: int) -> Optional[VoyageFinalization]:
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT vf.*,
                   p.port_name AS load_port_name,
                   s.name AS site_name
            FROM voyage_finalizations vf
            LEFT JOIN ports p ON p.id = vf.load_port_id
            LEFT JOIN sites s ON s.id = vf.site_id
            WHERE vf.project_id = ? AND vf.site_id = ?
            """,
            (project_id, site_id),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return _row_to_finalization(row)


def list_finalizations(project_id: int) -> List[VoyageFinalization]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT vf.*,
                   p.port_name AS load_port_name,
                   s.name AS site_name
            FROM voyage_finalizations vf
            LEFT JOIN ports p ON p.id = vf.load_port_id
            LEFT JOIN sites s ON s.id = vf.site_id
            WHERE vf.project_id = ?
            ORDER BY vf.finalized_at DESC
            """,
            (project_id,),
        ).fetchall()
    finally:
        conn.close()
    return [_row_to_finalization(r) for r in rows]


def save_actuals(finalization_id: int, actual_breakdown_dict: dict) -> VoyageFinalization:
    actual = recompute_breakdown_totals(actual_breakdown_dict)
    now = _utc_now()
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            UPDATE voyage_finalizations
            SET actual_breakdown_json = ?, actual_entered_at = ?
            WHERE id = ?
            """,
            (json.dumps(actual), now, finalization_id),
        )
        if cur.rowcount == 0:
            raise FinalizationError(f"Finalization id {finalization_id} not found.")
        row = conn.execute(
            "SELECT project_id, site_id FROM voyage_finalizations WHERE id = ?",
            (finalization_id,),
        ).fetchone()
        conn.commit()
    finally:
        conn.close()
    if row is None:
        raise FinalizationError(f"Finalization id {finalization_id} not found.")
    fin = get_finalization(row["project_id"], row["site_id"])
    if fin is None:
        raise FinalizationError("Failed to reload finalization after save.")
    return fin


def clear_actuals(finalization_id: int) -> VoyageFinalization:
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            UPDATE voyage_finalizations
            SET actual_breakdown_json = NULL, actual_entered_at = NULL
            WHERE id = ?
            """,
            (finalization_id,),
        )
        if cur.rowcount == 0:
            raise FinalizationError(f"Finalization id {finalization_id} not found.")
        row = conn.execute(
            "SELECT project_id, site_id FROM voyage_finalizations WHERE id = ?",
            (finalization_id,),
        ).fetchone()
        conn.commit()
    finally:
        conn.close()
    if row is None:
        raise FinalizationError(f"Finalization id {finalization_id} not found.")
    fin = get_finalization(row["project_id"], row["site_id"])
    if fin is None:
        raise FinalizationError("Failed to reload finalization after clear.")
    return fin


def _money(val: Any) -> float:
    try:
        return float(val or 0.0)
    except (TypeError, ValueError):
        return 0.0


def compare_estimate_actual(
    estimate: dict,
    actual: dict,
) -> List[Dict[str, Any]]:
    """Return variance rows: label, estimate, actual, delta, delta_pct."""
    rows: List[Dict[str, Any]] = []

    def add_row(label: str, est: float, act: float, *, is_currency: bool = True) -> None:
        delta = round(act - est, 2)
        if est != 0:
            delta_pct = round((delta / est) * 100.0, 1)
        elif act != 0:
            delta_pct = None
        else:
            delta_pct = 0.0
        rows.append({
            "label": label,
            "estimate": est,
            "actual": act,
            "delta": delta,
            "delta_pct": delta_pct,
            "is_currency": is_currency,
        })

    est_vessels = {v.get("key"): v for v in (estimate.get("vessels") or [])}
    act_vessels = {v.get("key"): v for v in (actual.get("vessels") or [])}
    all_keys = list(dict.fromkeys(list(est_vessels.keys()) + list(act_vessels.keys())))

    for key in all_keys:
        ev = est_vessels.get(key, {})
        av = act_vessels.get(key, {})
        name = av.get("name") or ev.get("name") or key
        add_row(f"{name} — Charter", _money(ev.get("charter_usd")), _money(av.get("charter_usd")))
        add_row(f"{name} — Fuel", _money(ev.get("fuel_usd")), _money(av.get("fuel_usd")))

    add_row(
        "Charter — Total",
        _money(estimate.get("charter_total_usd")),
        _money(actual.get("charter_total_usd")),
    )

    est_fees = {pf.get("role"): pf for pf in (estimate.get("port_fees") or [])}
    act_fees = {pf.get("role"): pf for pf in (actual.get("port_fees") or [])}
    for role in list(dict.fromkeys(list(est_fees.keys()) + list(act_fees.keys()))):
        add_row(
            f"Port fees — {role.replace('_', ' ').title()}",
            _money(est_fees.get(role, {}).get("total_usd")),
            _money(act_fees.get(role, {}).get("total_usd")),
        )

    add_row(
        "Port fees — Total",
        _money(estimate.get("port_fees_total_usd")),
        _money(actual.get("port_fees_total_usd")),
    )
    add_row(
        "Fuel — Gallons",
        _money(estimate.get("fuel_total_gal")),
        _money(actual.get("fuel_total_gal")),
        is_currency=False,
    )
    add_row(
        "Fuel — Total",
        _money(estimate.get("fuel_total_usd")),
        _money(actual.get("fuel_total_usd")),
    )
    add_row(
        "Voyage days",
        _money(estimate.get("voyage_days")),
        _money(actual.get("voyage_days")),
        is_currency=False,
    )
    add_row(
        "Total USD",
        _money(estimate.get("total_usd")),
        _money(actual.get("total_usd")),
    )
    add_row(
        "Cost / Launch",
        _money(estimate.get("cost_per_launch_usd")),
        _money(actual.get("cost_per_launch_usd")),
    )
    return rows

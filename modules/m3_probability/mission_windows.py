"""
modules/m3_probability/mission_windows.py — Consecutive GO-day windows for Mission Timing.
"""
from __future__ import annotations

import calendar
import statistics
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Dict, Iterable, List, Optional

from config import DEFAULT_THRESHOLDS, DEFAULT_WEIGHTS
from core.models import Site
from modules.m2_weather.era5_daily import (
    ensure_era5_daily_duration,
    load_daily_month_series,
    mission_timing_year_range,
)
from modules.m2_weather.operability import ERA5_CRITERIA_PARAMS, resolve_active_criteria_params

ProgressCallback = Callable[[int, int, str], None]

_DAILY_FIELD = {
    "ws": "ws_mean_kts",
    "wg": "wg_max_kts",
    "sh": "sh_mean_m",
    "swh": "swh_mean_m",
    "swp": "swp_mean_s",
}

_MO = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


@dataclass
class GoStreak:
    start_day: int
    end_day: int
    length: int


@dataclass
class YearMissionStats:
    year: int
    go_days: int
    total_days: int
    streaks: List[GoStreak] = field(default_factory=list)
    max_streak: int = 0
    longest_window: str = ""
    num_streaks: int = 0


@dataclass
class MissionWindowAnalysis:
    calendar_month: int
    month_label: str
    duration_years: int
    year_start: int
    year_end: int
    years: List[YearMissionStats] = field(default_factory=list)
    avg_max_streak: float = 0.0
    avg_streak_length: float = 0.0
    max_streak_ever: int = 0
    avg_go_days: float = 0.0
    avg_go_pct: float = 0.0
    avg_streaks_per_year: float = 0.0
    typical_start_day: Optional[int] = None
    typical_start_label: str = ""
    suggested_start_day: Optional[int] = None
    planning_hint: str = ""
    active_params: List[str] = field(default_factory=list)
    thresholds: Dict[str, float] = field(default_factory=dict)


def _active_criteria_params(weights: dict) -> list[str]:
    active = [
        p for p in ERA5_CRITERIA_PARAMS
        if float(weights.get(p, 0.0) or 0.0) > 0.0
    ]
    return active or list(ERA5_CRITERIA_PARAMS)


def day_meets_criteria(
    daily_row: dict,
    thresholds: dict,
    active_params: Iterable[str],
) -> bool:
    """Hard threshold check on daily aggregates."""
    for param in active_params:
        col = _DAILY_FIELD.get(param)
        thr = thresholds.get(param)
        val = daily_row.get(col) if col else None
        if thr is None or val is None:
            return False
        if float(val) > float(thr):
            return False
    return True


def find_go_streaks(go_mask: List[bool]) -> List[GoStreak]:
    """Return consecutive True streaks as (start_dom, end_dom, length) 1-indexed."""
    streaks: List[GoStreak] = []
    start: Optional[int] = None
    for i, ok in enumerate(go_mask):
        dom = i + 1
        if ok:
            if start is None:
                start = dom
        elif start is not None:
            streaks.append(GoStreak(start, dom - 1, dom - start))
            start = None
    if start is not None:
        streaks.append(GoStreak(start, len(go_mask), len(go_mask) - start + 1))
    return streaks


def _format_window(year: int, month: int, streak: GoStreak) -> str:
    mo = _MO[month - 1]
    if streak.start_day == streak.end_day:
        return f"{mo} {streak.start_day}, {year}"
    return f"{mo} {streak.start_day}–{streak.end_day}, {year}"


def _median_int(values: List[int]) -> Optional[int]:
    if not values:
        return None
    return int(round(statistics.median(values)))


def analyze_mission_windows(
    site: Site,
    calendar_month: int,
    duration_years: int,
    *,
    thresholds: Optional[dict] = None,
    weights: Optional[dict] = None,
    on_progress: ProgressCallback | None = None,
) -> MissionWindowAnalysis:
    """
    Ensure ERA5 daily cache and compute consecutive GO-day statistics.

    Raises RuntimeError if daily cache cannot be completed.
    """
    thr = dict(thresholds or DEFAULT_THRESHOLDS)
    wts = dict(weights or DEFAULT_WEIGHTS)
    params = resolve_active_criteria_params(thr, _active_criteria_params(wts))
    ys, ye = mission_timing_year_range(duration_years)

    ok, err = ensure_era5_daily_duration(
        site.lat,
        site.lon,
        calendar_month,
        duration_years,
        on_progress=on_progress,
    )
    if not ok:
        raise RuntimeError(err or "ERA5 daily data could not be retrieved.")

    year_stats: List[YearMissionStats] = []
    all_streak_lengths: List[int] = []
    max_streaks: List[int] = []
    longest_starts: List[int] = []
    streak_counts: List[int] = []
    go_day_counts: List[int] = []
    go_pcts: List[float] = []

    for yr in range(ys, ye + 1):
        series = load_daily_month_series(site.lat, site.lon, yr, calendar_month)
        ndays = calendar.monthrange(yr, calendar_month)[1]
        go_mask = [False] * ndays
        for row in series:
            dom = row["day"]
            if 1 <= dom <= ndays:
                go_mask[dom - 1] = day_meets_criteria(row, thr, params)

        streaks = find_go_streaks(go_mask)
        go_days = sum(go_mask)
        max_str = max((s.length for s in streaks), default=0)
        best = max(streaks, key=lambda s: s.length) if streaks else None
        window = _format_window(yr, calendar_month, best) if best and best.length > 0 else "—"

        ys_row = YearMissionStats(
            year=yr,
            go_days=go_days,
            total_days=ndays,
            streaks=streaks,
            max_streak=max_str,
            longest_window=window,
            num_streaks=len(streaks),
        )
        year_stats.append(ys_row)

        go_day_counts.append(go_days)
        go_pcts.append(100.0 * go_days / ndays if ndays else 0.0)
        max_streaks.append(max_str)
        streak_counts.append(len(streaks))
        if best and best.length > 0:
            longest_starts.append(best.start_day)
        for s in streaks:
            all_streak_lengths.append(s.length)

    avg_max = float(statistics.mean(max_streaks)) if max_streaks else 0.0
    avg_streak = float(statistics.mean(all_streak_lengths)) if all_streak_lengths else 0.0
    max_ever = max(max_streaks) if max_streaks else 0
    avg_go = float(statistics.mean(go_day_counts)) if go_day_counts else 0.0
    avg_pct = float(statistics.mean(go_pcts)) if go_pcts else 0.0
    avg_num_streaks = float(statistics.mean(streak_counts)) if streak_counts else 0.0
    med_start = _median_int(longest_starts)
    mo_label = _MO[calendar_month - 1]

    if med_start is not None:
        typical_label = f"~{mo_label} {med_start} (median start of longest streak)"
    else:
        typical_label = "No consistent longest-window start"

    if max_ever >= 5:
        hint = (
            f"Longest observed run: {max_ever} consecutive GO days in {mo_label}. "
            f"Typical longest streak averages {avg_max:.1f} days/year. "
            f"Consider starting around {mo_label} {med_start or 'mid-month'}."
        )
    elif max_ever > 0:
        hint = (
            f"GO windows are fragmented — max {max_ever} consecutive days in {mo_label}. "
            f"Average {avg_go:.1f} GO days/month ({avg_pct:.0f}%). "
            "Plan for intermittent weather holds rather than one long block."
        )
    else:
        hint = (
            f"No full-day GO windows found in {mo_label} over {duration_years} years "
            "at the current thresholds."
        )

    return MissionWindowAnalysis(
        calendar_month=calendar_month,
        month_label=mo_label,
        duration_years=duration_years,
        year_start=ys,
        year_end=ye,
        years=year_stats,
        avg_max_streak=round(avg_max, 1),
        avg_streak_length=round(avg_streak, 1),
        max_streak_ever=max_ever,
        avg_go_days=round(avg_go, 1),
        avg_go_pct=round(avg_pct, 1),
        avg_streaks_per_year=round(avg_num_streaks, 1),
        typical_start_day=med_start,
        typical_start_label=typical_label,
        suggested_start_day=med_start,
        planning_hint=hint,
        active_params=list(params),
        thresholds={p: float(thr[p]) for p in params if p in thr},
    )

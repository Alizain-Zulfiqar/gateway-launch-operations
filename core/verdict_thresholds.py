"""
core/verdict_thresholds.py — GO / MARGINAL / NO-GO display bands from settings.

Bands (probability 0.0–1.0):
  GO       ≥ go_threshold      (default 0.70)
  MARGINAL ≥ marginal_threshold and < go_threshold  (default 0.50)
  NO-GO    < marginal_threshold
"""
from __future__ import annotations


def get_go_threshold() -> float:
    try:
        from core.settings import get_float
        return float(get_float("go_threshold", 0.70))
    except Exception:
        return 0.70


def get_marginal_threshold() -> float:
    try:
        from core.settings import get_float
        return float(get_float("marginal_threshold", 0.50))
    except Exception:
        return 0.50


def classify_verdict(prob: float) -> str:
    """Return 'GO', 'MARGINAL', or 'NO-GO' for a probability in [0, 1]."""
    go = get_go_threshold()
    marg = min(get_marginal_threshold(), go)
    if prob >= go:
        return "GO"
    if prob >= marg:
        return "MARGINAL"
    return "NO-GO"


def go_pct_threshold() -> float:
    return get_go_threshold() * 100.0


def marginal_pct_threshold() -> float:
    return get_marginal_threshold() * 100.0

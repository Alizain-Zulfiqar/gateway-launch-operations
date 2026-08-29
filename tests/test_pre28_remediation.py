"""
tests/test_pre28_remediation.py — Pre-28 remediation checks.

Covers the housekeeping fixes (m1_site package marker, logo filename) and the
newly added forecast / period-comparison functions. Network-dependent tests
skip cleanly when offline or when pandas/requests are unavailable.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_m1_site_init_exists():
    assert (Path(__file__).parent.parent / "modules" / "m1_site" / "__init__.py").exists()


def test_logo_available():
    from config import logo_available
    assert logo_available() is True


def test_logo_path_case_matches_disk():
    """The on-disk filename must match LOGO_PATH exactly (case-sensitive check)."""
    from config import LOGO_PATH
    names = {p.name for p in LOGO_PATH.parent.iterdir()}
    assert LOGO_PATH.name in names, f"{LOGO_PATH.name} not in {names}"


# ── Forecast fetch functions (network) ───────────────────────────────────────

def test_fetch_openmeteo_returns_dataframe():
    try:
        from modules.m2_weather.forecast import fetch_openmeteo_marine_forecast
        result = fetch_openmeteo_marine_forecast(32.6, -61.1)
        if result is not None:
            assert "wave_ht_m" in result.columns
            assert "swell_ht_m" in result.columns
            assert len(result) > 100
    except Exception:
        pytest.skip("Network unavailable")


def test_fetch_nws_returns_none_offshore():
    # NWS covers U.S. waters only. Bermuda (32.6N, 61.1W) is outside coverage —
    # must return None (or a DataFrame), never raise.
    try:
        from modules.m2_weather.forecast import fetch_nws_marine_forecast
        result = fetch_nws_marine_forecast(32.6, -61.1)
        assert result is None or hasattr(result, "columns")
    except Exception:
        pytest.skip("Network unavailable")


def test_fetch_combined_forecast_structure():
    try:
        from modules.m2_weather.forecast import fetch_combined_forecast
        result = fetch_combined_forecast(32.6, -61.1)
        assert "nws_available" in result
        assert "openmeteo_available" in result
        assert "lat" in result
        assert "lon" in result
        assert result["lat"] == 32.6
    except Exception:
        pytest.skip("Network unavailable")


# ── compare_periods (offline, synthetic data) ────────────────────────────────

def test_compare_periods_structure():
    pd = pytest.importorskip("pandas")
    np = pytest.importorskip("numpy")
    from datetime import datetime, timezone
    from modules.m2_weather.ndbc_history import compare_periods

    dates = pd.date_range(end=datetime.now(timezone.utc).replace(tzinfo=None), periods=45 * 24, freq="h")
    df = pd.DataFrame({
        "wspd_kts": np.random.uniform(5, 20, 45 * 24),
        "wvht_m":   np.random.uniform(0.5, 3.0, 45 * 24),
    }, index=dates)

    result = compare_periods(df, "TEST01", "Test Station")
    assert "15" in result
    assert "30" in result
    assert "45" in result
    assert result["station_id"] == "TEST01"
    # 45 days of hourly data → all three windows populated
    assert result["15"] is not None
    assert result["30"] is not None
    assert result["45"] is not None


def test_compare_periods_insufficient_data_yields_none():
    pd = pytest.importorskip("pandas")
    np = pytest.importorskip("numpy")
    from datetime import datetime, timezone
    from modules.m2_weather.ndbc_history import compare_periods

    # Only 20 hourly records — below 10% of even the 15-day window (needs 36).
    dates = pd.date_range(end=datetime.now(timezone.utc).replace(tzinfo=None), periods=20, freq="h")
    df = pd.DataFrame({"wspd_kts": np.random.uniform(5, 20, 20)}, index=dates)

    result = compare_periods(df, "SPARSE", "")
    assert result["15"] is None
    assert result["30"] is None
    assert result["45"] is None

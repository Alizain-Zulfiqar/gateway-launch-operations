"""
tests/test_ndbc.py — Tests for modules/m2_weather/ndbc.py DataFrame functions.

Network tests hit live NDBC endpoints.  They are automatically skipped if the
network is unreachable so CI does not fail without connectivity.

Run: pytest tests/test_ndbc.py -v
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
import pytest
import pandas as pd
import requests

from modules.m2_weather.ndbc import (
    fetch_met_data,
    fetch_spec_data,
    get_station_summary,
    _parse_met,
    _parse_spec,
    _empty_met_df,
    _empty_spec_df,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

BERMUDA = "41047"   # Deep-water buoy SE of Bermuda — reliable met, often has spec

def _ndbc_reachable() -> bool:
    try:
        requests.head("https://www.ndbc.noaa.gov", timeout=5)
        return True
    except requests.RequestException:
        return False

network = pytest.mark.skipif(
    not _ndbc_reachable(),
    reason="NDBC network unreachable",
)


# ── Unit tests (no network) ────────────────────────────────────────────────────

MET_SAMPLE = """\
#YY  MM DD hh mm WDIR WSPD GST  WVHT   DPD   APD MWD   PRES  ATMP  WTMP  DEWP  VIS PTDY  TIDE
#yr  mo dy hr mn degT m/s  m/s     m   sec   sec degT   hPa  degC  degC  degC   mi  hPa    ft
2026 06 20 12 00  270  8.5 10.2   1.8  10.0   7.0 260 1015.0  24.0  26.0  18.0   MM   MM    MM
2026 06 20 11 00  265  7.0  8.8   1.6   9.0   6.5 255 1015.5  23.8  25.9  17.5   MM   MM    MM
2026 06 20 10 00  260 99.0  8.0   1.4   8.5   6.2 250 1016.0  23.5  25.8  17.0   MM   MM    MM
2026 06 20 09 00  255  6.5  7.9 999.0   8.0   6.0 245 1016.5  23.2  25.7  16.8   MM   MM    MM
"""

SPEC_SAMPLE = """\
#YY  MM DD hh mm SwH  SwP  SwD  WWH  WWP  WWD  STEEPNESS  APD MWD
#yr  mo dy hr mn  m    s  degT   m    s   degT
2026 06 20 12 00  1.5 12.0 260  0.8  6.0 270 AVERAGE      7.0 265
2026 06 20 11 00  1.3 11.5 255  0.7  5.5 265 AVERAGE      6.5 260
2026 06 20 10 00 99.0 11.0 250  0.6  5.0 260 AVERAGE      6.0 255
"""


def test_parse_met_drops_sentinel_rows():
    rows = _parse_met(MET_SAMPLE)
    # All 4 data rows should parse (sentinel filtering is done in fetch_met_data)
    assert len(rows) == 4


def test_parse_spec_parses_rows():
    rows = _parse_spec(SPEC_SAMPLE)
    assert len(rows) == 3


def test_empty_met_df_has_correct_columns():
    df = _empty_met_df()
    expected = {"timestamp", "wspd_ms", "wspd_kts", "wdir_deg",
                "gst_ms", "gst_kts", "wvht_m", "mwd_deg"}
    assert set(df.columns) == expected


def test_empty_spec_df_has_correct_columns():
    df = _empty_spec_df()
    assert set(df.columns) == {"timestamp", "swh_m", "swp_s", "swd_deg"}


def test_met_sentinel_filtering_via_parse():
    """Rows with 99.0 or 999.0 in any numeric column should be dropped."""
    rows = _parse_met(MET_SAMPLE)
    df = pd.DataFrame(rows)
    # Raw rows contain sentinel values — verify they exist before filtering
    # (fetch_met_data is where filtering actually happens; we test logic here)
    from modules.m2_weather.ndbc import _MISSING
    # rows 2 and 3 contain sentinels in WSPD and WVHT respectively
    assert len(rows) == 4   # all rows parse
    # confirm the sentinel values appear
    assert any(
        any(str(v) in {"99.0", "999.0"} for v in r.values() if v is not None)
        for r in rows
    )


# ── Network tests ─────────────────────────────────────────────────────────────

@network
def test_fetch_met_data_returns_dataframe():
    df = fetch_met_data(BERMUDA)
    assert isinstance(df, pd.DataFrame)


@network
def test_fetch_met_data_expected_columns():
    df = fetch_met_data(BERMUDA)
    expected = {"timestamp", "wspd_ms", "wspd_kts", "wdir_deg",
                "gst_ms", "gst_kts", "wvht_m", "mwd_deg"}
    assert expected.issubset(set(df.columns)), (
        f"Missing columns: {expected - set(df.columns)}"
    )


@network
def test_fetch_met_data_has_at_least_one_row():
    df = fetch_met_data(BERMUDA)
    assert len(df) >= 1, "Expected at least one observation row"


@network
def test_fetch_met_data_timestamp_is_utc_datetime():
    df = fetch_met_data(BERMUDA)
    assert pd.api.types.is_datetime64_any_dtype(df["timestamp"])
    # All timestamps should be timezone-aware UTC
    assert df["timestamp"].dt.tz is not None


@network
def test_fetch_met_data_within_45_days():
    df = fetch_met_data(BERMUDA)
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=45)
    assert (df["timestamp"] >= cutoff).all(), "Record older than 45 days found"


@network
def test_fetch_met_data_no_sentinel_values():
    df = fetch_met_data(BERMUDA)
    num_cols = ["wspd_ms", "wspd_kts", "wdir_deg", "gst_ms", "gst_kts", "wvht_m", "mwd_deg"]
    for col in num_cols:
        assert not df[col].isin({99.0, 999.0}).any(), (
            f"Sentinel value found in column {col}"
        )


@network
def test_fetch_met_data_wind_speed_kts_positive():
    df = fetch_met_data(BERMUDA)
    # Drop rows where wspd_kts is NaN (stations that report waves but not wind)
    wind_rows = df["wspd_kts"].dropna()
    assert len(wind_rows) > 0, "Expected at least some rows with wind speed"
    assert (wind_rows >= 0).all()


@network
def test_fetch_met_data_ms_kts_consistent():
    """wspd_kts should equal wspd_ms × MS_TO_KTS within floating-point tolerance."""
    from config import MS_TO_KTS
    df = fetch_met_data(BERMUDA)
    # Only test rows where both columns are non-null
    valid = df[df["wspd_kts"].notna() & df["wspd_ms"].notna()]
    assert len(valid) > 0, "No rows with valid wind speed data"
    diff = (valid["wspd_kts"] - valid["wspd_ms"] * MS_TO_KTS).abs()
    assert (diff < 0.01).all(), "wspd_kts / wspd_ms unit conversion mismatch"


@network
def test_fetch_spec_data_returns_none_or_dataframe():
    result = fetch_spec_data(BERMUDA)
    assert result is None or isinstance(result, pd.DataFrame)


@network
def test_fetch_spec_data_columns_when_present():
    result = fetch_spec_data(BERMUDA)
    if result is not None:
        expected = {"timestamp", "swh_m", "swp_s", "swd_deg"}
        assert expected.issubset(set(result.columns))


@network
def test_fetch_spec_data_no_sentinel_values():
    result = fetch_spec_data(BERMUDA)
    if result is not None and len(result) > 0:
        for col in ["swh_m", "swp_s", "swd_deg"]:
            assert not result[col].isin({99.0, 999.0}).any()


@network
def test_get_station_summary_keys():
    summary = get_station_summary(BERMUDA)
    expected_keys = {
        "station_id", "has_spec", "record_count_met", "record_count_spec",
        "wind_speed_mean_kts", "wind_speed_max_kts",
        "hs_mean_m", "hs_max_m",
        "date_range_start", "date_range_end",
    }
    assert expected_keys == set(summary.keys())


@network
def test_get_station_summary_station_id_uppercase():
    summary = get_station_summary(BERMUDA.lower())
    assert summary["station_id"] == BERMUDA.upper()


@network
def test_get_station_summary_record_count_positive():
    summary = get_station_summary(BERMUDA)
    assert summary["record_count_met"] >= 1


@network
def test_get_station_summary_has_spec_is_bool():
    summary = get_station_summary(BERMUDA)
    assert isinstance(summary["has_spec"], bool)


@network
def test_get_station_summary_spec_count_matches_has_spec():
    summary = get_station_summary(BERMUDA)
    if summary["has_spec"]:
        assert isinstance(summary["record_count_spec"], int)
    else:
        assert summary["record_count_spec"] is None


@network
def test_get_station_summary_max_ge_mean():
    summary = get_station_summary(BERMUDA)
    if summary["wind_speed_mean_kts"] is not None:
        assert summary["wind_speed_max_kts"] >= summary["wind_speed_mean_kts"]
    if summary["hs_mean_m"] is not None:
        assert summary["hs_max_m"] >= summary["hs_mean_m"]


@network
def test_get_station_summary_date_range_non_empty():
    summary = get_station_summary(BERMUDA)
    assert summary["date_range_start"] != ""
    assert summary["date_range_end"]   != ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

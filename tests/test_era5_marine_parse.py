"""Tests for ERA5 marine NetCDF parsing (CDS zip stream merge)."""
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.m2_weather.era5 import (
    _collapse_cds_monthly_times,
    _merge_marine_month_dicts,
    _parse_era5_marine_nc,
)


def _write_stream(path: Path, vars_data: dict, time: str) -> None:
    data_vars = {
        name: (["valid_time", "latitude", "longitude"], [[[val]]])
        for name, val in vars_data.items()
    }
    ds = xr.Dataset(
        data_vars,
        coords={
            "valid_time": [np.datetime64(time)],
            "latitude": [28.5],
            "longitude": [-80.5],
        },
    )
    ds.to_netcdf(path, engine="netcdf4")


def _write_marine_zip(path: Path) -> None:
    """CDS-like zip: wind/wave at 00:00, gust at 06:00, same calendar month."""
    wind = path.parent / "wind.nc"
    gust = path.parent / "gust.nc"
    _write_stream(
        wind,
        {"si10": 6.5, "swh": 0.84, "shts": 0.61, "mpts": 6.54},
        "2024-01-01T00:00:00",
    )
    _write_stream(gust, {"i10fg": 9.24}, "2024-01-01T06:00:00")
    with zipfile.ZipFile(path, "w") as zf:
        zf.write(wind, arcname="data_stream-moda_stepType-avgua.nc")
        zf.write(gust, arcname="data_stream-moda_stepType-avgid.nc")


def _write_merged_nc(path: Path) -> None:
    """Legacy single-file merge with duplicate month timestamps."""
    wind = xr.Dataset(
        {
            "si10": (["valid_time", "latitude", "longitude"], [[[6.5]]]),
            "swh": (["valid_time", "latitude", "longitude"], [[[0.84]]]),
            "shts": (["valid_time", "latitude", "longitude"], [[[0.61]]]),
            "mpts": (["valid_time", "latitude", "longitude"], [[[6.54]]]),
        },
        coords={
            "valid_time": [np.datetime64("2024-01-01T00:00:00")],
            "latitude": [28.5],
            "longitude": [-80.5],
        },
    )
    gust = xr.Dataset(
        {
            "i10fg": (["valid_time", "latitude", "longitude"], [[[9.24]]]),
        },
        coords={
            "valid_time": [np.datetime64("2024-01-01T06:00:00")],
            "latitude": [28.5],
            "longitude": [-80.5],
        },
    )
    xr.merge([wind, gust], compat="override", join="outer").to_netcdf(
        path, engine="netcdf4"
    )


class TestCollapseCdsMonthlyTimes:
    def test_collapses_duplicate_month_timestamps(self, tmp_path):
        nc = tmp_path / "marine.nc"
        _write_merged_nc(nc)
        ds = xr.open_dataset(nc, engine="netcdf4").load()
        assert ds.sizes["valid_time"] == 2
        collapsed = _collapse_cds_monthly_times(ds)
        assert collapsed.sizes["valid_time"] == 1
        pt = collapsed.sel(latitude=28.5, longitude=-80.5, method="nearest")
        assert float(np.asarray(pt["si10"].values).flat[0]) == pytest.approx(6.5)
        assert float(np.asarray(pt["i10fg"].values).flat[0]) == pytest.approx(9.24)

    def test_collapses_with_expver_coord_on_time(self):
        times = np.array(
            ["2024-01-01T00:00:00", "2024-01-01T06:00:00"],
            dtype="datetime64[ns]",
        )
        ds = xr.Dataset(
            {
                "si10": (["valid_time", "latitude", "longitude"], [[[6.5]], [[np.nan]]]),
                "i10fg": (["valid_time", "latitude", "longitude"], [[[np.nan]], [[9.24]]]),
            },
            coords={
                "valid_time": times,
                "latitude": [28.5],
                "longitude": [-80.5],
                "expver": ("valid_time", ["0001", "0001"]),
            },
        )
        collapsed = _collapse_cds_monthly_times(ds)
        assert collapsed.sizes["valid_time"] == 1
        assert "expver" not in collapsed.coords


class TestParseEra5MarineNc:
    def test_parses_all_core_fields_from_merged_streams(self, tmp_path):
        nc = tmp_path / "marine.nc"
        _write_merged_nc(nc)
        result = _parse_era5_marine_nc(str(nc), 28.5, -80.5, 2024, 2024)
        assert result is not None
        row = result["2024-01-01"]
        assert row["ws_mean_kts"] == pytest.approx(12.63, abs=0.05)
        assert row["sh_mean_m"] == pytest.approx(0.84, abs=0.01)
        assert row["swh_mean_m"] == pytest.approx(0.61, abs=0.01)
        assert row["swp_mean_s"] == pytest.approx(6.54, abs=0.01)
        assert row["wg_mean_kts"] == pytest.approx(17.96, abs=0.05)

    def test_parses_cds_zip_without_xr_merge(self, tmp_path):
        zpath = tmp_path / "era5.zip"
        _write_marine_zip(zpath)
        result = _parse_era5_marine_nc(str(zpath), 28.5, -80.5, 2024, 2024)
        assert result is not None
        row = result["2024-01-01"]
        assert row["ws_mean_kts"] == pytest.approx(12.63, abs=0.05)
        assert row["wg_mean_kts"] == pytest.approx(17.96, abs=0.05)
        assert row["sh_mean_m"] == pytest.approx(0.84, abs=0.01)

    def test_merge_month_dicts_fills_fields(self):
        a = {"2024-01-01": {"record_count": 1, "ws_mean_kts": 12.0}}
        b = {"2024-01-01": {"record_count": 1, "wg_mean_kts": 18.0}}
        m = _merge_marine_month_dicts(a, b)
        assert m["2024-01-01"]["ws_mean_kts"] == 12.0
        assert m["2024-01-01"]["wg_mean_kts"] == 18.0

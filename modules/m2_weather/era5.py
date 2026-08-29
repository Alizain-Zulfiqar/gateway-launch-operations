"""
modules/m2_weather/era5.py -- ERA5 reanalysis and WaveWatch III swell retrieval.

Two public functions:

  fetch_swell_climatology()   -- ERA5 monthly mean swell via CDS API (historical mode)
  fetch_swell_realtime_ww3()  -- WW3 last-45-day swell via NOAA ERDDAP (45-day mode)

Both return None on any failure so callers can fall back to icoads_model without
special handling.  Never raise — log a warning and return None.

Authentication:
  cdsapi reads credentials from ~/.cdsapirc automatically.
  No API key is stored in .env or config.py.
  Register and download .cdsapirc from https://cds.climate.copernicus.eu
"""
import logging
import os
import sys
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

log = logging.getLogger(__name__)

# ── ERA5 CDS constants ────────────────────────────────────────────────────────

# cdsapi reads ~/.cdsapirc automatically — no explicit url/key needed.

_ERA5_DATASET = "reanalysis-era5-single-levels-monthly-means"

# Set 42: previously requested "significant_height_of_combined_wind_waves_
# and_swell" (ERA5 shortname swh) to populate this app's swh (swell height)
# parameter — but that ERA5 variable is the COMBINED wind-sea + swell
# height, not swell alone (confirmed against ECMWF's own parameter
# documentation). The correct swell-only variables are used below.
_ERA5_VARS    = [
    "significant_height_of_total_swell",
    "mean_period_of_total_swell",
    "mean_direction_of_total_swell",
]
# Wind gust: ECMWF's docs mark gust fields "forecast only", so availability
# in the monthly-AVERAGED REANALYSIS product this app uses was uncertain —
# confirmed live (2026-07-13, once CDS auth was unblocked) that it IS
# present: a real retrieve() for this variable against
# reanalysis-era5-single-levels-monthly-means succeeded and returned netCDF
# shortname "i10fg" (instantaneous 10m wind gust), same valid_time
# coordinate as the swell variables. See fetch_gust_climatology() below.
_ERA5_GUST_VAR = "instantaneous_10m_wind_gust"
_NC_I10FG      = "i10fg"  # instantaneous 10m wind gust, m/s

# netCDF variable short-names as stored in ERA5 downloaded files
_NC_SHTS = "shts"  # significant height of total swell
_NC_MPTS = "mpts"  # mean period of total swell
_NC_MDTS = "mdts"  # mean direction of total swell

# ── WaveWatch III ERDDAP constants ────────────────────────────────────────────

_WW3_ERDDAP  = "https://coastwatch.pfeg.noaa.gov/erddap"
_WW3_DATASET = "NWW3_Global_Best"

# Candidate variable names — ERDDAP schema varies by dataset and server version.
# Set 42 follow-up fix: live-queried info/NWW3_Global_Best/index.json
# (2026-07-12) and found the actual live variable names are short codes
# (shgt/sdir/sper/Thgt/Tdir/Tper/whgt/wdir/wper), none of which matched any
# prior candidate. Confirmed via each variable's long_name/standard_name/units
# that "shgt"/"sdir"/"sper" are the genuinely swell-only fields
# (standard_name sea_surface_swell_wave_*) — "Thgt"/"Tdir"/"Tper" are the
# combined/total wave fields (same wrong-variable mistake class as the old
# ERA5 swh bug) and "whgt"/"wdir"/"wper" are wind-sea-only, neither of which
# is what this app's swell (swh/swdV/swp) parameters need. The confirmed
# swell-only codes are listed first; older long-name candidates kept as
# fallbacks in case a different ERDDAP server/dataset version exposes those
# instead.
_WW3_SWH_CANDIDATES = [
    "shgt",
    "Significant_height_of_combined_wind_waves_and_swell_surface",
    "Significant_height_of_wind_waves_and_swell",
    "hs", "swh",
]
_WW3_MWD_CANDIDATES = [
    "sdir",
    "Primary_wave_mean_direction_surface",
    "Primary_wave_direction_surface",
    "Mean_direction_of_wind_waves",
    "dp", "mwd",
]
_WW3_MWP_CANDIDATES = [
    "sper",
    "Primary_wave_mean_period_surface",
    "Primary_wave_mean_period",
    "Mean_period_of_wind_waves",
    "tp", "mwp",
]

# Live WW3 ERDDAP griddap queries against this dataset measured ~13 minutes
# server-side (NOAA-side aggregation across the ForecastModelRunCollection,
# not fixable client-side — see CLAUDE.md). Cached results are reused for up
# to this many hours before a fresh live fetch is attempted; this represents
# a rolling 45-day "current conditions" window (unlike NCEI's unbounded
# climatological cache), so it must expire rather than persist forever.
_WW3_CACHE_MAX_AGE_HOURS = 24
_WW3_CACHE_COLUMNS = ["swh_mean_m", "swh_p90_m", "swd_mean_deg", "swp_mean_s", "record_count"]


# ── Utility ───────────────────────────────────────────────────────────────────

def _circular_mean_deg(angles_deg: np.ndarray) -> float:
    """Circular (unit-vector) mean of bearings in degrees."""
    rad      = np.deg2rad(angles_deg)
    mean_sin = np.mean(np.sin(rad))
    mean_cos = np.mean(np.cos(rad))
    return float(np.degrees(np.arctan2(mean_sin, mean_cos)) % 360)


# ── ERA5 swell climatology ────────────────────────────────────────────────────

def fetch_swell_climatology(
    lat: float,
    lon: float,
    year_start: int,
    year_end: int,
    months: list[int] | None = None,
) -> dict | None:
    """
    Fetch ERA5 monthly mean swell climatology from the Copernicus CDS API.

    Parameters
    ----------
    lat, lon    : Site coordinates (WGS-84, +N/+E convention).
    year_start  : First year of the historical range (inclusive).
    year_end    : Last year of the historical range (inclusive).
    months      : 1-indexed month list to fetch; None = all 12 months.

    Returns
    -------
    Dict keyed by month (int 1–12), each value a dict with:
        swh_mean_m   : float  — monthly mean significant swell height (m)
        swh_p90_m    : float  — 90th-percentile significant swell height (m)
        swp_mean_s   : float or None  — monthly mean swell period (s)
        swd_mean_deg : float or None  — circular mean swell direction (°)
        source       : 'era5_reanalysis'
        year_start   : int
        year_end     : int
        record_count : int
    Returns None on any failure (.cdsapirc missing, invalid key, network error).
    """
    try:
        import cdsapi          # noqa: F401 — check import only
    except ImportError:
        log.warning("cdsapi not installed — skipping ERA5 swell fetch")
        return None

    try:
        return _do_fetch_era5(lat, lon, year_start, year_end, months)
    except Exception as exc:
        _log_auth_warning(exc)
        return None


def _get_cds_client(**kwargs):
    """
    Return a CDS API client with a working retrieve() implementation.

    Set 42: plain cdsapi.Client() builds retrieve() URLs using an old path
    scheme (/api/resources/{dataset}) that Copernicus has retired —
    confirmed via direct live testing (404 Not Found), unrelated to what
    variables are requested. ecmwf.datastores.legacy_client.LegacyClient is
    a drop-in replacement (identical retrieve(name, request, target)
    signature) that uses the correct current path
    (/api/retrieve/v1/processes/{dataset}/execution) — confirmed working
    up through authentication. Falls back to plain cdsapi.Client only if
    ecmwf-datastores-client somehow isn't installed (it's already a
    dependency of cdsapi itself, so this should be rare).
    """
    try:
        from ecmwf.datastores.legacy_client import LegacyClient
        return LegacyClient(quiet=True, progress=False)
    except ImportError:
        import cdsapi
        try:
            return cdsapi.Client(quiet=True, progress=False, wait_until_complete=True)
        except TypeError:
            return cdsapi.Client(quiet=True, progress=False)


_AUX_COORDS = ("expver", "number")


def _strip_auxiliary_coords(ds):
    """Remove ERA5 expver/number coords that break time collapsing."""
    import xarray as xr

    for dim in _AUX_COORDS:
        if dim in ds.dims:
            ds = ds.mean(dim, skipna=True)
    drop = [c for c in _AUX_COORDS if c in ds.coords]
    if drop:
        ds = ds.drop_vars(drop, errors="ignore")
    return ds


def _collapse_cds_monthly_times(ds):
    """
    Collapse duplicate valid_time rows that belong to the same calendar month.

    CDS zip merges can produce two timestamps per month (e.g. wind/wave at
    00:00 and gust at 06:00 from separate NetCDF streams). Downstream parsers
    that iterate time indices and overwrite by month would keep only the last
    stream — typically gust-only rows.
    """
    import pandas as pd
    import xarray as xr

    ds = _strip_auxiliary_coords(ds)

    time_key = _first_nc_key(ds, ["valid_time", "time"])
    if time_key is None or time_key not in ds.dims:
        return ds

    times = pd.to_datetime(ds[time_key].values)
    month_periods = times.to_period("M")
    if len(set(month_periods)) == len(times):
        return ds

    from collections import defaultdict

    groups: dict = defaultdict(list)
    for i, period in enumerate(month_periods):
        groups[period].append(i)

    new_times = [period.to_timestamp() for period in sorted(groups.keys())]
    new_data: dict = {}
    for var in ds.data_vars:
        da = ds[var]
        if time_key not in da.dims:
            new_data[var] = da
            continue
        pieces = []
        for period in sorted(groups.keys()):
            idxs = groups[period]
            piece = da.isel({time_key: idxs}).mean(dim=time_key, skipna=True)
            pieces.append(piece)
        new_data[var] = xr.concat(
            pieces,
            dim=xr.DataArray(new_times, dims=[time_key], name=time_key),
        )

    # Spatial coords only — omit time-linked aux coords (expver, number).
    coords = {
        k: ds.coords[k]
        for k in ds.coords
        if k != time_key and time_key not in ds.coords[k].dims
    }
    coords[time_key] = new_times
    return xr.Dataset(new_data, coords=coords, attrs=ds.attrs)


def _list_cds_netcdf_paths(path: str, tmpdir: str) -> list[Path]:
    """Return NetCDF file paths for a CDS download (plain .nc or unzipped)."""
    raw = Path(path).read_bytes()[:2]
    if raw != b"PK":
        return [Path(path)]
    with zipfile.ZipFile(path) as zf:
        names = [n for n in zf.namelist() if n.endswith(".nc")]
        if not names:
            raise ValueError("CDS zip archive contains no NetCDF files")
        zf.extractall(tmpdir)
        return [Path(tmpdir) / name for name in names]


def _open_cds_netcdf(path: str):
    """
    Open a CDS download as an xarray Dataset.

    Copernicus now often returns a ZIP archive containing one or more
    NetCDF streams even when format=netcdf is requested — opening the path
    directly with netCDF4 fails with "Unknown file format".

    Prefer stream-by-stream parsing for marine climatology
    (_parse_era5_marine_nc); this helper remains for swell/gust parsers.
    """
    import xarray as xr

    with tempfile.TemporaryDirectory() as tmpdir:
        paths = _list_cds_netcdf_paths(path, tmpdir)
        datasets = [
            _strip_auxiliary_coords(xr.open_dataset(p, engine="netcdf4").load())
            for p in paths
        ]
        if len(datasets) == 1:
            return _collapse_cds_monthly_times(datasets[0])
        # Align only on shared dims after stripping aux coords that conflict
        # when wind/wave (00:00) and gust (06:00) share a calendar month.
        merged = xr.merge(datasets, compat="override", join="outer")
        return _collapse_cds_monthly_times(merged)


def _do_fetch_era5(
    lat: float,
    lon: float,
    year_start: int,
    year_end: int,
    months: list[int] | None,
) -> dict | None:
    target_months = months if months else list(range(1, 13))

    # Bounding box: one ERA5 cell (0.25°) around the point, N/W/S/E
    area = [
        min(90.0,   lat + 0.25),
        max(-180.0, lon - 0.25),
        max(-90.0,  lat - 0.25),
        min(180.0,  lon + 0.25),
    ]
    years   = [str(y) for y in range(year_start, year_end + 1)]
    mo_strs = [f"{m:02d}" for m in target_months]

    client = _get_cds_client()

    with tempfile.NamedTemporaryFile(suffix=".nc", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        client.retrieve(
            _ERA5_DATASET,
            {
                "product_type": "monthly_averaged_reanalysis",
                "variable":     _ERA5_VARS,
                "year":         years,
                "month":        mo_strs,
                "time":         "00:00",
                "area":         area,
                "format":       "netcdf",
            },
            tmp_path,
        )
        return _parse_era5_nc(tmp_path, lat, lon, year_start, year_end, target_months)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _parse_era5_nc(
    nc_path: str,
    lat: float,
    lon: float,
    year_start: int,
    year_end: int,
    target_months: list[int],
) -> dict | None:
    import xarray as xr

    ds = _open_cds_netcdf(nc_path)
    try:
        # Snap to the nearest grid point
        sel_kwargs: dict = {}
        if "latitude" in ds.dims:
            sel_kwargs["latitude"] = lat
        if "longitude" in ds.dims:
            sel_kwargs["longitude"] = lon
        ds_pt = ds.sel(**sel_kwargs, method="nearest") if sel_kwargs else ds

        result: dict = {}

        # Set 42 follow-up fix: the time coordinate in current CDS output
        # is named "valid_time", not the classic "time" — confirmed via a
        # live download whose variable list was ['shts', 'mpts', 'mdts',
        # 'number', 'valid_time', 'latitude', 'longitude', 'expver'], no
        # 'time' at all. Try both so this keeps working if Copernicus
        # reverts or varies this across dataset versions.
        time_key = _first_nc_key(ds_pt, ["valid_time", "time"])
        if time_key is None:
            log.warning("ERA5 netCDF has no recognised time coordinate (checked "
                        "valid_time, time) — variables present: %s", list(ds_pt.variables))
            return None

        for mo in target_months:
            mo_mask = ds_pt[time_key].dt.month == mo
            ds_mo   = ds_pt.sel(**{time_key: mo_mask})

            # SHTS — significant height of TOTAL SWELL (swell-only; Set 42
            # fix, was previously the combined wind-sea+swell variable)
            swh_key = _first_nc_key(ds_mo, [_NC_SHTS, "shts", "significant_height_of_total_swell"])
            if swh_key is None:
                continue
            swh_vals = ds_mo[swh_key].values.flatten()
            swh_vals = swh_vals[~np.isnan(swh_vals)]
            if len(swh_vals) == 0:
                continue

            # MPTS — mean period of total swell (swell-only)
            mwp_key  = _first_nc_key(ds_mo, [_NC_MPTS, "mpts", "mean_period_of_total_swell"])
            mwp_mean = None
            if mwp_key:
                mwp_v = ds_mo[mwp_key].values.flatten()
                mwp_v = mwp_v[~np.isnan(mwp_v)]
                if len(mwp_v) > 0:
                    mwp_mean = round(float(np.mean(mwp_v)), 3)

            # MDTS — mean direction of total swell (swell-only)
            mwd_key      = _first_nc_key(ds_mo, [_NC_MDTS, "mdts", "mean_direction_of_total_swell"])
            swd_mean_deg = None
            if mwd_key:
                mwd_v = ds_mo[mwd_key].values.flatten()
                mwd_v = mwd_v[~np.isnan(mwd_v)]
                if len(mwd_v) > 0:
                    swd_mean_deg = round(_circular_mean_deg(mwd_v), 1)

            result[mo] = {
                "swh_mean_m":   round(float(np.mean(swh_vals)), 3),
                "swh_p90_m":    round(float(np.percentile(swh_vals, 90)), 3),
                "swp_mean_s":   mwp_mean,
                "swd_mean_deg": swd_mean_deg,
                "source":       "era5_reanalysis",
                "year_start":   year_start,
                "year_end":     year_end,
                "record_count": int(len(swh_vals)),
            }

        return result if result else None

    finally:
        ds.close()


def _first_nc_key(ds, candidates: list[str]) -> str | None:
    """Return the first candidate variable name present in the xarray dataset."""
    for c in candidates:
        if c in ds:
            return c
    return None


# ── ERA5 wind gust climatology ────────────────────────────────────────────────

def fetch_gust_climatology(
    lat: float,
    lon: float,
    year_start: int,
    year_end: int,
    months: list[int] | None = None,
) -> dict | None:
    """
    Fetch ERA5 monthly mean 10m wind gust climatology from the Copernicus CDS
    API. Deferred until Set 42's CDS auth fix landed (previously untestable —
    every live request failed at authentication); confirmed live 2026-07-13
    that "instantaneous_10m_wind_gust" IS present in the monthly-averaged
    REANALYSIS product despite ECMWF's docs marking gust "forecast only".

    NCEI Global Marine (this app's other historical wind source) does not
    carry gust at all (see data_manager.py's module docstring) — ERA5 is the
    first live historical source for wg.

    Parameters
    ----------
    lat, lon    : Site coordinates (WGS-84, +N/+E convention).
    year_start  : First year of the historical range (inclusive).
    year_end    : Last year of the historical range (inclusive).
    months      : 1-indexed month list to fetch; None = all 12 months.

    Returns
    -------
    Dict keyed by month (int 1-12), each value a dict with:
        wg_mean_kts  : float  — monthly mean instantaneous 10m wind gust (kts)
        wg_p90_kts   : float  — 90th-percentile wind gust (kts)
        source       : 'era5_reanalysis'
        year_start   : int
        year_end     : int
        record_count : int
    Returns None on any failure (.cdsapirc missing, invalid key, network error).
    """
    try:
        import cdsapi          # noqa: F401 — check import only
    except ImportError:
        log.warning("cdsapi not installed — skipping ERA5 gust fetch")
        return None

    try:
        return _do_fetch_era5_gust(lat, lon, year_start, year_end, months)
    except Exception as exc:
        _log_auth_warning(exc)
        return None


def _do_fetch_era5_gust(
    lat: float,
    lon: float,
    year_start: int,
    year_end: int,
    months: list[int] | None,
) -> dict | None:
    target_months = months if months else list(range(1, 13))

    area = [
        min(90.0,   lat + 0.25),
        max(-180.0, lon - 0.25),
        max(-90.0,  lat - 0.25),
        min(180.0,  lon + 0.25),
    ]
    years   = [str(y) for y in range(year_start, year_end + 1)]
    mo_strs = [f"{m:02d}" for m in target_months]

    client = _get_cds_client()

    with tempfile.NamedTemporaryFile(suffix=".nc", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        client.retrieve(
            _ERA5_DATASET,
            {
                "product_type": "monthly_averaged_reanalysis",
                "variable":     [_ERA5_GUST_VAR],
                "year":         years,
                "month":        mo_strs,
                "time":         "00:00",
                "area":         area,
                "format":       "netcdf",
            },
            tmp_path,
        )
        return _parse_era5_gust_nc(tmp_path, lat, lon, year_start, year_end, target_months)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _parse_era5_gust_nc(
    nc_path: str,
    lat: float,
    lon: float,
    year_start: int,
    year_end: int,
    target_months: list[int],
) -> dict | None:
    import xarray as xr
    from config import MS_TO_KTS

    ds = _open_cds_netcdf(nc_path)
    try:
        sel_kwargs: dict = {}
        if "latitude" in ds.dims:
            sel_kwargs["latitude"] = lat
        if "longitude" in ds.dims:
            sel_kwargs["longitude"] = lon
        ds_pt = ds.sel(**sel_kwargs, method="nearest") if sel_kwargs else ds

        result: dict = {}

        # Same valid_time/time flexibility as _parse_era5_nc() (Set 42
        # follow-up) — current CDS output names the coordinate valid_time.
        time_key = _first_nc_key(ds_pt, ["valid_time", "time"])
        if time_key is None:
            log.warning("ERA5 gust netCDF has no recognised time coordinate "
                        "(checked valid_time, time) — variables present: %s",
                        list(ds_pt.variables))
            return None

        gust_key = _first_nc_key(ds_pt, [_NC_I10FG, "i10fg", "instantaneous_10m_wind_gust"])
        if gust_key is None:
            log.warning("ERA5 gust netCDF has no recognised gust variable "
                        "(checked i10fg) — variables present: %s", list(ds_pt.variables))
            return None

        for mo in target_months:
            mo_mask  = ds_pt[time_key].dt.month == mo
            gust_vals = ds_pt[gust_key].sel(**{time_key: mo_mask}).values.flatten()
            gust_vals = gust_vals[~np.isnan(gust_vals)]
            if len(gust_vals) == 0:
                continue

            gust_kts = gust_vals * MS_TO_KTS
            result[mo] = {
                "wg_mean_kts":  round(float(np.mean(gust_kts)), 2),
                "wg_p90_kts":   round(float(np.percentile(gust_kts, 90)), 2),
                "source":       "era5_reanalysis",
                "year_start":   year_start,
                "year_end":     year_end,
                "record_count": int(len(gust_vals)),
            }

        return result if result else None

    finally:
        ds.close()


# ── ERA5 combined marine climatology (hybrid Analysis tab) ───────────────────

_ERA5_MARINE_VARS = [
    "10m_wind_speed",
    "significant_height_of_combined_wind_waves_and_swell",
    "significant_height_of_total_swell",
    "mean_period_of_total_swell",
    "instantaneous_10m_wind_gust",
]
_NC_WS = ["si10", "10m_wind_speed", "u10"]
_NC_SH = ["swh", "significant_height_of_combined_wind_waves_and_swell"]
_NC_SHTS_MARINE = ["shts", "significant_height_of_total_swell"]
_NC_MPTS_MARINE = ["mpts", "mean_period_of_total_swell"]


def fetch_marine_climatology(
    lat: float,
    lon: float,
    year_start: int,
    year_end: int,
) -> dict[str, dict] | None:
    """
    Fetch ERA5 monthly marine fields for cache storage.

    Returns dict keyed by month_start ('YYYY-MM-01') with ws/sh/swh/swp/wg means.
    Raises on CDS/network/parse failures so callers can surface the real error;
    returns None only when cdsapi is not installed.
    """
    try:
        import cdsapi  # noqa: F401 — presence check
    except ImportError:
        log.warning("cdsapi not installed — skipping ERA5 marine fetch")
        return None
    try:
        return _do_fetch_marine_climatology(lat, lon, year_start, year_end)
    except Exception as exc:
        _log_auth_warning(exc)
        raise


def _do_fetch_marine_climatology(
    lat: float,
    lon: float,
    year_start: int,
    year_end: int,
) -> dict[str, dict] | None:
    area = [
        min(90.0, lat + 0.25),
        max(-180.0, lon - 0.25),
        max(-90.0, lat - 0.25),
        min(180.0, lon + 0.25),
    ]
    years = [str(y) for y in range(year_start, year_end + 1)]
    mo_strs = [f"{m:02d}" for m in range(1, 13)]
    client = _get_cds_client()

    with tempfile.NamedTemporaryFile(suffix=".nc", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        client.retrieve(
            _ERA5_DATASET,
            {
                "product_type": "monthly_averaged_reanalysis",
                "variable": _ERA5_MARINE_VARS,
                "year": years,
                "month": mo_strs,
                "time": "00:00",
                "area": area,
                "format": "netcdf",
            },
            tmp_path,
        )
        return _parse_era5_marine_nc(tmp_path, lat, lon, year_start, year_end)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _scalar_at_point(da, lat: float, lon: float) -> float | None:
    """Nearest-point scalar from a DataArray; None if missing/NaN."""
    sel = {}
    if "latitude" in da.dims:
        sel["latitude"] = lat
    if "longitude" in da.dims:
        sel["longitude"] = lon
    if sel:
        da = da.sel(**sel, method="nearest")
    try:
        v = float(np.asarray(da.values).reshape(-1)[0])
    except (TypeError, ValueError, IndexError):
        return None
    if np.isnan(v):
        return None
    return v


def _parse_era5_marine_stream(
    ds,
    lat: float,
    lon: float,
    year_start: int,
    year_end: int,
) -> dict[str, dict]:
    """Parse one CDS NetCDF stream into month_start → partial field dict."""
    import pandas as pd
    from config import MS_TO_KTS

    ds = _strip_auxiliary_coords(ds)
    time_key = _first_nc_key(ds, ["valid_time", "time"])
    if time_key is None:
        return {}

    field_specs = [
        (_first_nc_key(ds, _NC_WS), "ws_mean_kts", MS_TO_KTS),
        (_first_nc_key(ds, _NC_SH), "sh_mean_m", 1.0),
        (_first_nc_key(ds, _NC_SHTS_MARINE), "swh_mean_m", 1.0),
        (_first_nc_key(ds, _NC_MPTS_MARINE), "swp_mean_s", 1.0),
        (
            _first_nc_key(ds, [_NC_I10FG, "i10fg", "instantaneous_10m_wind_gust"]),
            "wg_mean_kts",
            MS_TO_KTS,
        ),
    ]
    field_specs = [(k, name, scale) for k, name, scale in field_specs if k is not None]
    if not field_specs:
        return {}

    times = pd.to_datetime(ds[time_key].values)
    from collections import defaultdict

    # Accumulate raw values per month/field (handles duplicate month stamps).
    buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for i, ts in enumerate(times):
        ts = pd.Timestamp(ts)
        if ts.year < year_start or ts.year > year_end:
            continue
        month_start = f"{ts.year}-{ts.month:02d}-01"
        for var_key, field, scale in field_specs:
            v = _scalar_at_point(ds[var_key].isel({time_key: i}), lat, lon)
            if v is not None:
                buckets[month_start][field].append(v * scale)

    result: dict[str, dict] = {}
    for month_start, fields in buckets.items():
        entry: dict = {"record_count": 1}
        for field, vals in fields.items():
            if not vals:
                continue
            mean_v = float(np.mean(vals))
            entry[field] = round(mean_v, 2 if field.endswith("_kts") else 3)
        if len(entry) > 1:
            result[month_start] = entry
    return result


def _merge_marine_month_dicts(*partials: dict[str, dict]) -> dict[str, dict]:
    """Merge per-stream month dicts; later streams fill missing fields."""
    merged: dict[str, dict] = {}
    for part in partials:
        for month_start, entry in part.items():
            dest = merged.setdefault(month_start, {"record_count": 0})
            dest["record_count"] = max(
                int(dest.get("record_count") or 0),
                int(entry.get("record_count") or 0),
            )
            for key, val in entry.items():
                if key == "record_count":
                    continue
                if dest.get(key) is None and val is not None:
                    dest[key] = val
    return merged


def _parse_era5_marine_nc(
    nc_path: str,
    lat: float,
    lon: float,
    year_start: int,
    year_end: int,
) -> dict[str, dict] | None:
    """
    Parse CDS marine download into month_start → field dicts.

    Opens each NetCDF stream in a CDS zip independently and merges field
    dicts by calendar month — avoids xr.merge valid_time/expver conflicts
    when wind/wave (00:00) and gust (06:00) share a month.
    """
    import xarray as xr

    with tempfile.TemporaryDirectory() as tmpdir:
        paths = _list_cds_netcdf_paths(nc_path, tmpdir)
        partials = []
        for p in paths:
            ds = xr.open_dataset(p, engine="netcdf4")
            try:
                partials.append(
                    _parse_era5_marine_stream(
                        ds.load(), lat, lon, year_start, year_end
                    )
                )
            finally:
                ds.close()

    result = _merge_marine_month_dicts(*partials)
    return result if result else None


def _log_auth_warning(exc: Exception) -> None:
    rc_path = Path.home() / ".cdsapirc"
    log.warning(
        "ERA5 fetch or NetCDF parse failed (credentials OK if Settings test "
        "passes). Confirm .cdsapirc at %s — %s",
        rc_path, exc,
    )


def check_era5_auth() -> tuple[bool, str]:
    """
    Test ERA5 authentication with a real, lightweight API call.

    Returns (ok: bool, message: str).
    Called by the Settings tab [Test Connection] button.

    Set 42 fix: this previously only instantiated cdsapi.Client(), which
    just parses .cdsapirc — it never made a network call, so it reported
    "Connected" even when live requests were failing (confirmed live: a
    real retrieve() call failed with 401 Unauthorized even after this
    "check" reported success). Now calls check_authentication(), a real,
    lightweight account-verification request that doesn't submit a data
    job. Live testing (2026-07-12) found this specific endpoint
    (/profiles/v1/account/verification/pat — PAT = Personal Access Token)
    fails with 401 even with a correctly-formatted .cdsapirc, suggesting
    the new CDS backend expects a genuinely different token type than the
    old-format API key, not just the old key with its <UID>: prefix
    stripped — the error message below reflects that.
    """
    username = os.environ.get("USERNAME") or os.environ.get("USER") or "username"
    rc_path  = Path.home() / ".cdsapirc"

    if not rc_path.exists():
        return False, (
            f".cdsapirc not found at {rc_path}.  "
            "Download it from https://cds.climate.copernicus.eu"
        )

    try:
        from ecmwf.datastores.legacy_client import LegacyClient
    except ImportError:
        return False, (
            "ecmwf-datastores-client package not installed.  "
            "Run: pip install ecmwf-datastores-client"
        )

    try:
        client = LegacyClient(quiet=True, progress=False)
        client.client.check_authentication()
        return True, "Connected — ERA5 CDS authenticated"
    except Exception as exc:
        return False, (
            f"ERA5 authentication failed ({exc}).  "
            f".cdsapirc at C:\\Users\\{username}\\.cdsapirc is correctly "
            "formatted, but the API key itself may need to be regenerated "
            "as a current Personal Access Token from your CDS profile page "
            "(https://cds.climate.copernicus.eu/profile) — the new backend "
            "may not accept an old-format key even with the deprecated "
            "<UID>: prefix removed."
        )


# ── WaveWatch III realtime swell (ERDDAP) ────────────────────────────────────

def _ww3_bucket(lat: float, lon: float) -> tuple[float, float]:
    """Round to the nearest whole degree — matches the +-0.5 deg query window
    used in _do_fetch_ww3(), so nearby sites naturally share a cache row."""
    return (round(lat), round(lon))


def get_cached_ww3(lat: float, lon: float) -> dict | None:
    """Return the cached WW3 summary for this lat/lon bucket if it exists and
    is younger than _WW3_CACHE_MAX_AGE_HOURS, else None (cache miss/stale)."""
    lat_b, lon_b = _ww3_bucket(lat, lon)
    from core.database import get_connection
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT *, "
            "(julianday('now') - julianday(fetched_at)) * 24.0 AS age_hours "
            "FROM ww3_realtime_cache WHERE lat_bucket=? AND lon_bucket=?",
            (lat_b, lon_b),
        ).fetchone()
    finally:
        conn.close()
    if row is None or row["age_hours"] > _WW3_CACHE_MAX_AGE_HOURS:
        return None
    result = {col: row[col] for col in _WW3_CACHE_COLUMNS}
    result["source"] = "ww3_erddap"
    return result


def save_cached_ww3(lat: float, lon: float, summary: dict) -> None:
    """Insert or overwrite the cached WW3 summary for this lat/lon bucket."""
    lat_b, lon_b = _ww3_bucket(lat, lon)
    from core.database import get_connection
    conn = get_connection()
    try:
        conn.execute(
            f"""
            INSERT INTO ww3_realtime_cache
                (lat_bucket, lon_bucket, {", ".join(_WW3_CACHE_COLUMNS)}, fetched_at)
            VALUES (?, ?, {", ".join("?" for _ in _WW3_CACHE_COLUMNS)}, CURRENT_TIMESTAMP)
            ON CONFLICT(lat_bucket, lon_bucket) DO UPDATE SET
                {", ".join(f"{c}=excluded.{c}" for c in _WW3_CACHE_COLUMNS)},
                fetched_at = excluded.fetched_at
            """,
            (lat_b, lon_b, *(summary.get(c) for c in _WW3_CACHE_COLUMNS)),
        )
        conn.commit()
    finally:
        conn.close()


def fetch_swell_realtime_ww3(
    lat: float,
    lon: float,
) -> dict | None:
    """
    Retrieve the last 45 days of WaveWatch III swell data from NOAA ERDDAP.
    Checks the local ww3_realtime_cache first (see get_cached_ww3()) since a
    live ERDDAP query for this dataset measures ~13 minutes server-side —
    a cache hit (any fetch for this lat/lon bucket within the last
    _WW3_CACHE_MAX_AGE_HOURS) returns instantly instead.

    Returns a dict with:
        swh_mean_m   : float
        swh_p90_m    : float
        swd_mean_deg : float or None
        swp_mean_s   : float or None
        source       : 'ww3_erddap'
        record_count : int
    Returns None on any failure (network, dataset unavailable, no data).
    """
    try:
        cached = get_cached_ww3(lat, lon)
        if cached is not None:
            log.info("WW3 ERDDAP: serving cached result for (%.4f, %.4f)", lat, lon)
            return cached
    except Exception as exc:
        log.warning("WW3 cache lookup failed for (%.4f, %.4f): %s", lat, lon, exc)
        # non-fatal — fall through to a live fetch

    try:
        result = _do_fetch_ww3(lat, lon)
    except Exception as exc:
        log.warning("WW3 ERDDAP fetch failed for (%.4f, %.4f): %s", lat, lon, exc)
        return None

    if result is not None:
        try:
            save_cached_ww3(lat, lon, result)
        except Exception as exc:
            log.warning("WW3 cache write failed for (%.4f, %.4f): %s", lat, lon, exc)
            # non-fatal — the live result is still returned below

    return result


def _do_fetch_ww3(lat: float, lon: float) -> dict | None:
    try:
        from erddapy import ERDDAP
    except ImportError:
        log.warning("erddapy not installed — skipping WW3 swell fetch")
        return None

    now   = datetime.now(timezone.utc)
    start = now - timedelta(days=45)

    e = ERDDAP(server=_WW3_ERDDAP, protocol="griddap")
    e.dataset_id = _WW3_DATASET

    # Discover which variable names exist in this dataset (best-effort)
    available: set[str] = set()
    try:
        info_url = e.get_info_url(dataset_id=_WW3_DATASET, response="csv")
        import pandas as pd
        info_df  = pd.read_csv(info_url)
        available = set(info_df["Variable Name"].dropna().tolist())
    except Exception:
        pass   # proceed with candidate list; failures caught later

    swh_var = _first_available(_WW3_SWH_CANDIDATES, available)
    mwd_var = _first_available(_WW3_MWD_CANDIDATES, available)
    mwp_var = _first_available(_WW3_MWP_CANDIDATES, available)

    if swh_var is None:
        log.warning("WW3 ERDDAP: no recognised SWH variable found in %s", _WW3_DATASET)
        return None

    vars_to_fetch = [v for v in [swh_var, mwd_var, mwp_var] if v is not None]

    # Set 42 follow-up fix: live .das inspection of NWW3_Global_Best (2026-07-13)
    # found two more bugs beyond the variable-name mismatch, both previously
    # masked by the "no recognised SWH variable" early return:
    #   1. This grid has FOUR dims — time, depth, latitude, longitude — not
    #      three, and erddapy's griddap_initialize() (auto-run when
    #      e.dataset_id was set above) already populated e.constraints with a
    #      key for every dim PLUS a "{dim}_step" key each. Wholesale-replacing
    #      e.constraints with a new dict — even one that lists depth — still
    #      fails erddapy's key-equality check (_griddap_check_constraints)
    #      because it drops the "_step" keys, raising "keys in e.constraints
    #      have changed. Re-run e.griddap_initialize". Fix: mutate the
    #      existing dict in place so all originally-generated keys survive.
    #      depth's actual_range is 0.0, 0.0 (surface-only), so a fixed 0/0
    #      window is always correct.
    #   2. The dataset's longitude uses 0-360°E (actual_range 0.0, 359.5), not
    #      this app's -180..180 (+E/-W) convention (see CLAUDE.md coordinate
    #      convention) — convert at this API boundary only, app-wide storage
    #      stays -180..180.
    lon_360 = lon % 360
    e.variables = vars_to_fetch
    e.constraints.update({
        "time>=":      start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "time<=":      now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "depth>=":     0,
        "depth<=":     0,
        "latitude>=":  lat - 0.5,
        "latitude<=":  lat + 0.5,
        "longitude>=": lon_360 - 0.5,
        "longitude<=": lon_360 + 0.5,
    })

    df = None
    try:
        import pandas as pd
        df = e.to_pandas(index_col="time (UTC)", parse_dates=True)
    except Exception:
        try:
            ds = e.to_xarray()
            df = ds.to_dataframe().reset_index()
        except Exception as exc2:
            log.warning("WW3 ERDDAP: pandas + xarray both failed: %s", exc2)
            return None

    if df is None or len(df) == 0:
        return None

    swh_col = _find_col(df, swh_var)
    if swh_col is None:
        return None

    swh_vals = df[swh_col].dropna().values.astype(float)
    if len(swh_vals) == 0:
        return None

    out: dict = {
        "swh_mean_m":   round(float(np.mean(swh_vals)), 3),
        "swh_p90_m":    round(float(np.percentile(swh_vals, 90)), 3),
        "swd_mean_deg": None,
        "swp_mean_s":   None,
        "source":       "ww3_erddap",
        "record_count": int(len(swh_vals)),
    }

    if mwd_var:
        mwd_col = _find_col(df, mwd_var)
        if mwd_col:
            mwd_vals = df[mwd_col].dropna().values.astype(float)
            if len(mwd_vals) > 0:
                out["swd_mean_deg"] = round(_circular_mean_deg(mwd_vals), 1)

    if mwp_var:
        mwp_col = _find_col(df, mwp_var)
        if mwp_col:
            mwp_vals = df[mwp_col].dropna().values.astype(float)
            if len(mwp_vals) > 0:
                out["swp_mean_s"] = round(float(np.mean(mwp_vals)), 3)

    return out


# ── ERA5 hourly → daily (Mission Timing tab) ─────────────────────────────────

_ERA5_HOURLY_DATASET = "reanalysis-era5-single-levels"
_ERA5_HOURLY_TIMES = [f"{h:02d}:00" for h in range(24)]
# Hourly single-levels has no 10m_wind_speed (MARS ambiguous); use u/v components.
_ERA5_HOURLY_VARS = [
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "significant_height_of_combined_wind_waves_and_swell",
    "significant_height_of_total_swell",
    "mean_period_of_total_swell",
    "instantaneous_10m_wind_gust",
]
_NC_U10 = ["u10", "10m_u_component_of_wind", "u"]
_NC_V10 = ["v10", "10m_v_component_of_wind", "v"]


def fetch_marine_hourly_month(
    lat: float,
    lon: float,
    year: int,
    month: int,
) -> dict[str, dict] | None:
    """
    Fetch ERA5 hourly marine fields for one calendar month.

    Returns dict keyed by date ('YYYY-MM-DD') with daily aggregates.
    Raises on CDS/network/parse failures; returns None if cdsapi missing.
    """
    try:
        import cdsapi  # noqa: F401
    except ImportError:
        log.warning("cdsapi not installed — skipping ERA5 hourly fetch")
        return None
    try:
        return _do_fetch_marine_hourly_month(lat, lon, year, month)
    except Exception as exc:
        _log_auth_warning(exc)
        raise


def _do_fetch_marine_hourly_month(
    lat: float,
    lon: float,
    year: int,
    month: int,
) -> dict[str, dict] | None:
    import calendar

    ndays = calendar.monthrange(year, month)[1]
    area = [
        min(90.0, lat + 0.25),
        max(-180.0, lon - 0.25),
        max(-90.0, lat - 0.25),
        min(180.0, lon + 0.25),
    ]
    client = _get_cds_client()
    with tempfile.NamedTemporaryFile(suffix=".nc", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        client.retrieve(
            _ERA5_HOURLY_DATASET,
            {
                "product_type": "reanalysis",
                "variable": _ERA5_HOURLY_VARS,
                "year": str(year),
                "month": f"{month:02d}",
                "day": [f"{d:02d}" for d in range(1, ndays + 1)],
                "time": _ERA5_HOURLY_TIMES,
                "area": area,
                "data_format": "netcdf",
            },
            tmp_path,
        )
        return _parse_era5_hourly_nc(tmp_path, lat, lon, year, month)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _parse_era5_hourly_stream(
    ds,
    lat: float,
    lon: float,
    year: int,
    month: int,
) -> dict[str, dict]:
    """Parse one CDS NetCDF stream into date → daily aggregate dict."""
    import pandas as pd
    from collections import defaultdict
    from config import MS_TO_KTS

    ds = _strip_auxiliary_coords(ds)
    time_key = _first_nc_key(ds, ["valid_time", "time"])
    if time_key is None:
        return {}

    u_key = _first_nc_key(ds, _NC_U10)
    v_key = _first_nc_key(ds, _NC_V10)
    scalar_specs = [
        (_first_nc_key(ds, _NC_SH), "sh_mean_m", 1.0, "mean"),
        (_first_nc_key(ds, _NC_SHTS_MARINE), "swh_mean_m", 1.0, "mean"),
        (_first_nc_key(ds, _NC_MPTS_MARINE), "swp_mean_s", 1.0, "mean"),
        (
            _first_nc_key(ds, [_NC_I10FG, "i10fg", "instantaneous_10m_wind_gust"]),
            "wg_max_kts",
            MS_TO_KTS,
            "max",
        ),
    ]
    scalar_specs = [(k, name, scale, agg) for k, name, scale, agg in scalar_specs if k is not None]
    if not u_key and not v_key and not scalar_specs:
        return {}

    times = pd.to_datetime(ds[time_key].values)
    buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for i, ts in enumerate(times):
        ts = pd.Timestamp(ts)
        if ts.year != year or ts.month != month:
            continue
        date_str = ts.strftime("%Y-%m-%d")

        if u_key and v_key:
            u = _scalar_at_point(ds[u_key].isel({time_key: i}), lat, lon)
            v = _scalar_at_point(ds[v_key].isel({time_key: i}), lat, lon)
            if u is not None and v is not None:
                ws_ms = float(np.hypot(u, v))
                buckets[date_str]["ws_mean_kts"].append(ws_ms * MS_TO_KTS)

        for var_key, field, scale, _agg in scalar_specs:
            val = _scalar_at_point(ds[var_key].isel({time_key: i}), lat, lon)
            if val is not None:
                buckets[date_str][field].append(val * scale)

    result: dict[str, dict] = {}
    for date_str, fields in buckets.items():
        entry: dict = {"n_hours": 0}
        hour_counts = [len(v) for v in fields.values() if v]
        if hour_counts:
            entry["n_hours"] = max(hour_counts)
        for field, vals in fields.items():
            if not vals:
                continue
            spec = next((s for s in scalar_specs if s[1] == field), None)
            agg = spec[3] if spec else "mean"
            if field == "ws_mean_kts" or agg == "mean":
                entry[field] = round(float(np.mean(vals)), 2 if field.endswith("_kts") else 3)
            else:
                entry[field] = round(float(max(vals)), 2 if field.endswith("_kts") else 3)
        if entry.get("n_hours", 0) > 0:
            result[date_str] = entry
    return result


def _merge_daily_dicts(*partials: dict[str, dict]) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for part in partials:
        for date_str, entry in part.items():
            dest = merged.setdefault(date_str, {"n_hours": 0})
            dest["n_hours"] = max(int(dest.get("n_hours") or 0), int(entry.get("n_hours") or 0))
            for key, val in entry.items():
                if key == "n_hours":
                    continue
                if key.startswith("wg_") and dest.get(key) is not None and val is not None:
                    dest[key] = max(float(dest[key]), float(val))
                elif dest.get(key) is None and val is not None:
                    dest[key] = val
    return merged


def _parse_era5_hourly_nc(
    nc_path: str,
    lat: float,
    lon: float,
    year: int,
    month: int,
) -> dict[str, dict] | None:
    import xarray as xr

    with tempfile.TemporaryDirectory() as tmpdir:
        paths = _list_cds_netcdf_paths(nc_path, tmpdir)
        partials = []
        for p in paths:
            ds = xr.open_dataset(p, engine="netcdf4")
            try:
                partials.append(
                    _parse_era5_hourly_stream(ds.load(), lat, lon, year, month)
                )
            finally:
                ds.close()
    result = _merge_daily_dicts(*partials)
    return result if result else None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _first_available(candidates: list[str], available: set[str]) -> str | None:
    """Return the first candidate present in available, or first candidate if set is empty."""
    if not available:
        return candidates[0]   # no discovery info — try the first name
    for c in candidates:
        if c in available:
            return c
    return None


def _find_col(df, var_name: str) -> str | None:
    """Find a DataFrame column whose name equals or starts with var_name."""
    if var_name in df.columns:
        return var_name
    for col in df.columns:
        if col.startswith(var_name):
            return col
    return None

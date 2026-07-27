#!/usr/bin/env python3
"""ERA5 Reanalysis Downloader - Download ERA5 single-level data from Planetary Computer.

Downloads ERA5 single-level reanalysis data from Microsoft Planetary Computer
STAC endpoint (https://planetarycomputer.microsoft.com/api/stac/v1/) and saves
as NetCDF files. No API key required.

Usage:
    python era5-download.py download --variable temperature_2m --start-date 2024-01 --end-date 2024-03
    python era5-download.py search --variable precipitation --start-date 2024-01
    python era5-download.py variables
"""

import argparse
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    print("Error: requests library required. Install with: pip install requests", file=sys.stderr)
    sys.exit(1)

try:
    import xarray as xr
except ImportError:
    xr = None

try:
    import zarr  # noqa: F401  — required by xr.open_zarr
    _HAVE_ZARR = True
except ImportError:
    _HAVE_ZARR = False

try:
    import planetary_computer
except ImportError:
    planetary_computer = None

__version__ = "0.1.0"

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "era5-pds"
USER_AGENT = f"era5-download/{__version__} (+https://clawhub.ai/skills/era5-download)"

ERA5_VARIABLES = {
    "temperature_2m": {
        "description": "Air temperature at 2 meters above surface (analysis)",
        "units": "K",
        "asset_key": "air_temperature_at_2_metres",
    },
    "precipitation": {
        "description": "Total precipitation (forecast 1-hour accumulation)",
        "units": "m",
        "asset_key": "precipitation_amount_1hour_Accumulation",
    },
    "wind_u_10m": {
        "description": "U-component of wind at 10 meters",
        "units": "m/s",
        "asset_key": "eastward_wind_at_10_metres",
    },
    "wind_v_10m": {
        "description": "V-component of wind at 10 meters",
        "units": "m/s",
        "asset_key": "northward_wind_at_10_metres",
    },
    "wind_u_100m": {
        "description": "U-component of wind at 100 meters",
        "units": "m/s",
        "asset_key": "eastward_wind_at_100_metres",
    },
    "wind_v_100m": {
        "description": "V-component of wind at 100 meters",
        "units": "m/s",
        "asset_key": "northward_wind_at_100_metres",
    },
    "dewpoint_2m": {
        "description": "Dewpoint temperature at 2 meters",
        "units": "K",
        "asset_key": "dew_point_temperature_at_2_metres",
    },
    "surface_pressure": {
        "description": "Surface pressure",
        "units": "Pa",
        "asset_key": "surface_air_pressure",
    },
    "sea_level_pressure": {
        "description": "Mean sea level pressure",
        "units": "Pa",
        "asset_key": "air_pressure_at_mean_sea_level",
    },
    "sea_surface_temperature": {
        "description": "Sea surface temperature",
        "units": "K",
        "asset_key": "sea_surface_temperature",
    },
    "solar_radiation": {
        "description": "Surface solar radiation downwards (1-hour accumulation)",
        "units": "J m**-2",
        "asset_key": "integral_wrt_time_of_surface_direct_downwelling_shortwave_flux_in_air_1hour_Accumulation",
    },
}


def get_variable_info(name):
    """Get ERA5 variable metadata."""
    if name not in ERA5_VARIABLES:
        raise ValueError(
            f"Unknown variable: {name}. Available: {', '.join(sorted(ERA5_VARIABLES.keys()))}"
        )
    return ERA5_VARIABLES[name]


def create_session():
    """Create a requests session with retry and user-agent."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    session.trust_env = False
    adapter = requests.adapters.HTTPAdapter(max_retries=3)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def search_era5(variable, start_date, end_date=None, limit=12):
    """Search for ERA5 data items on Planetary Computer.

    Args:
        variable: ERA5 variable name (e.g. 'temperature_2m').
        start_date: Start date string (YYYY or YYYY-MM).
        end_date: End date string (YYYY or YYYY-MM). Defaults to start_date.
        limit: Maximum number of items to return.

    Returns:
        List of dicts with keys: id, datetime, variable, asset_url.
    """
    var_info = get_variable_info(variable)
    asset_key = var_info["asset_key"]

    start_dt = _parse_date(start_date)
    end_dt = _parse_date(end_date) if end_date else start_dt

    session = create_session()
    url = f"{STAC_URL}/collections/{COLLECTION}/items"
    # Build STAC datetime range filter so the server only returns items
    # within the requested window. Required for accurate YYYY-MM matching.
    dt_range = None
    if start_dt and end_dt:
        from datetime import datetime as _dt
        end_inclusive = _dt(end_dt.year, end_dt.month, 28)  # 28 covers all months safely
        if end_dt.month == 12:
            end_inclusive = _dt(end_dt.year, 12, 31)
        dt_range = f"{start_dt.strftime('%Y-%m-%dT00:00:00Z')}/{end_inclusive.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    params = {"limit": limit}
    if dt_range:
        params["datetime"] = dt_range
    resp = session.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    results = []
    for item in data.get("features", []):
        item_id = item.get("id", "")
        item_assets = item.get("assets", {})

        # Match the variable by asset key OR by asset title/href hints.
        # The era5-pds collection sometimes has the variable in `air` etc.
        matched_asset = None
        if asset_key in item_assets:
            matched_asset = asset_key
        else:
            for ak, av in item_assets.items():
                title = (av.get("title") or "").lower()
                desc = (av.get("description") or "").lower()
                href = (av.get("href") or "").lower()
                if variable.replace("_", " ") in title or variable in href or asset_key in href:
                    matched_asset = ak
                    break
        if matched_asset is None:
            continue

        item_date = _parse_item_date(item_id, item.get("properties", {}).get("datetime"))
        if item_date is None:
            continue

        if start_dt and item_date < start_dt:
            continue
        if end_dt and item_date > end_dt:
            continue

        href = item_assets[matched_asset].get("href", "")
        results.append({
            "id": item_id,
            "datetime": item_date.isoformat(),
            "variable": variable,
            "asset_url": href,
        })

    return results


def download_era5(
    variable,
    start_date,
    end_date=None,
    output=None,
    bbox=None,
    skip_existing=False,
    quiet=False,
    fmt=None,
):
    """Download ERA5 data and save in the requested format.

    Args:
        variable: ERA5 variable name.
        start_date: Start date (YYYY or YYYY-MM).
        end_date: End date (YYYY or YYYY-MM). Defaults to start_date.
        output: Output file path. Auto-generated if None.
        bbox: Bounding box [west, south, east, north].
        skip_existing: Skip download if output file exists.
        quiet: Suppress progress output.
        fmt: Output format — 'netcdf' (default), 'csv', or 'json'.

    Returns:
        Path to downloaded file.
    """
    var_info = get_variable_info(variable)
    asset_key = var_info["asset_key"]

    start_dt = _parse_date(start_date)
    end_dt = _parse_date(end_date) if end_date else start_dt

    fmt = (fmt or "netcdf").lower()
    if fmt not in ("netcdf", "csv", "json"):
        raise ValueError(f"Unknown --format: {fmt!r}. Choose from: netcdf, csv, json.")

    if output is None:
        sd_label = start_date if isinstance(start_date, str) else start_dt.strftime("%Y-%m")
        ed_label = (end_date if isinstance(end_date, str) else end_dt.strftime("%Y-%m")) if end_date else sd_label
        ext = {"netcdf": ".nc", "csv": ".csv", "json": ".json"}[fmt]
        output = f"era5_{variable}_{sd_label}_to_{ed_label}{ext}"

    output_path = Path(output)
    if skip_existing and output_path.exists():
        if not quiet:
            print(f"Skipping (exists): {output_path}")
        return str(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    session = create_session()

    if not quiet:
        print(f"Searching for {variable} data...")

    url = f"{STAC_URL}/collections/{COLLECTION}/items"
    params = {"limit": 12}
    resp = session.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    items_to_download = []
    for item in data.get("features", []):
        item_id = item.get("id", "")
        item_assets = item.get("assets", {})

        if asset_key not in item_assets:
            continue

        item_date = _parse_item_date(item_id, item.get("properties", {}).get("datetime"))
        if item_date is None:
            continue
        if start_dt and item_date < start_dt:
            continue
        if end_dt and item_date > end_dt:
            continue

        href = item_assets[asset_key].get("href", "")
        items_to_download.append({"id": item_id, "href": href, "date": item_date})

    if not items_to_download:
        raise RuntimeError(
            f"No {variable} data found for {start_date} to {end_date or start_date}"
        )

    if not quiet:
        print(f"Found {len(items_to_download)} item(s) to download.")

    if xr is not None and _HAVE_ZARR:
        datasets = []
        total = len(items_to_download)
        for idx, item in enumerate(items_to_download, 1):
            if not quiet:
                print(f"  [{idx}/{total}] Downloading {item['id']}...")

            store_url = _sign_url(item["href"])
            ds = xr.open_zarr(store_url, consolidated=True)

            if start_dt:
                ds = ds.sel(time=slice(start_dt, end_dt))
            if bbox:
                west, south, east, north = bbox
                ds = ds.sel(
                    latitude=slice(north, south),
                    longitude=slice(west, east),
                )

            datasets.append(ds)

        if not quiet:
            print("Merging datasets...")
        combined = xr.concat(datasets, dim="time")
        combined = combined.sortby("time")

        part_path = output_path.with_suffix(output_path.suffix + ".part")
        if not quiet:
            print(f"Writing NetCDF to {output_path}...")

        try:
            combined.to_netcdf(part_path)
            part_path.rename(output_path)
            final_path = output_path
        except Exception as nc_err:
            # NetCDF engine (h5netcdf/scipy) missing. Try engine="scipy" or
            # fall back to a copy of the first zarr (no NetCDF, requires zarr).
            if part_path.exists():
                part_path.unlink()
            try:
                combined.to_netcdf(part_path, engine="scipy")
                part_path.rename(output_path)
                final_path = output_path
            except Exception as scipy_err:
                raise RuntimeError(
                    f"NetCDF write failed. Install h5netcdf (`pip install h5netcdf`) "
                    f"or scipy (`pip install scipy`) and retry. "
                    f"Original error: {nc_err}"
                ) from scipy_err

        if not quiet:
            print(f"Done: {final_path}")

        for ds in datasets:
            ds.close()

        # Non-NetCDF formats: emit alongside the .nc file or override the output path.
        if fmt in ("csv", "json"):
            ts = _centroid_point_timeseries(combined)
            csv_path = Path(str(final_path)).with_suffix(".csv")
            json_path = Path(str(final_path)).with_suffix(".json")
            if fmt == "csv":
                write_csv_timeseries(ts, str(csv_path))
                if not quiet:
                    print(f"  CSV summary: {csv_path}")
                return str(csv_path)
            else:
                summary = {
                    "skill": "era5-download",
                    "version": __version__,
                    "variable": variable,
                    "asset_key": asset_key,
                    "units": var_info.get("units"),
                    "start_date": str(start_date),
                    "end_date": str(end_date or start_date),
                    "bbox": list(bbox) if bbox else None,
                    "n_items": len(items_to_download),
                    "n_timesteps": len(ts),
                    "netcdf_path": str(final_path),
                    "timeseries": ts,
                }
                write_json_summary(summary, str(json_path))
                if not quiet:
                    print(f"  JSON summary: {json_path}")
                return str(json_path)

        return str(final_path)
    elif xr is not None and not _HAVE_ZARR:
        # xarray installed but zarr missing — we cannot open the planetary-computer
        # zarr stores at all. Print a helpful hint.
        raise RuntimeError(
            "era5-download needs the `zarr` package to open planetary-computer "
            "zarr stores. Install it with: pip install zarr  "
            "(then re-run the download)."
        )
    else:
        if not quiet:
            print("xarray not installed. Downloading raw zarr data...")

        _download_raw_zarr(session, items_to_download, output_path, quiet=quiet)
        return str(output_path)


def _download_raw_zarr(session, items_to_download, output_path, quiet=False):
    """Download raw zarr stream for the first item to the given path.

    Used as a fallback when xarray/NetCDF backends are unavailable.
    """
    item = items_to_download[0]
    # abfs:// URLs need a Planetary Computer SAS token to be fetchable via
    # plain HTTPS. Sign the URL first.
    store_url = _sign_url(item["href"])
    part_path = output_path.with_suffix(output_path.suffix + ".part")

    resp = session.get(store_url, stream=True, timeout=60)
    resp.raise_for_status()

    try:
        total = int(resp.headers.get("content-length", 0))
    except (ValueError, TypeError):
        total = 0

    downloaded = 0
    block_size = 8192

    with open(part_path, "wb") as f:
        for chunk in resp.iter_content(block_size):
            f.write(chunk)
            downloaded += len(chunk)
            if not quiet and total > 0:
                pct = downloaded * 100 // total
                bar = "=" * (pct // 2) + " " * (50 - pct // 2)
                print(f"\r  [{bar}] {pct}% ({downloaded}/{total})", end="", flush=True)

    if not quiet:
        print()

    part_path.rename(output_path)
    if not quiet:
        print(f"Done: {output_path}")
        return str(output_path)


def _sign_url(url):
    """Sign a Planetary Computer asset URL for access."""
    if planetary_computer is not None:
        return planetary_computer.sign(url)
    return url


def _parse_date(date_str):
    """Parse date string to datetime."""
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Invalid date format: {date_str}. Use YYYY, YYYY-MM, or YYYY-MM-DD.")


def _parse_item_date(item_id, dt_prop):
    """Extract datetime from STAC item id or properties."""
    if dt_prop:
        try:
            return datetime.fromisoformat(str(dt_prop).replace("Z", "+00:00")).replace(tzinfo=None)
        except (ValueError, AttributeError):
            pass

    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(item_id, fmt)
        except ValueError:
            continue

    for sep in ("_", "-", "."):
        for part in item_id.split(sep):
            if len(part) >= 4 and part[:4].isdigit():
                try:
                    return _parse_date(part[:7] if len(part) >= 7 else part[:4])
                except ValueError:
                    continue
    return None


def _centroid_point_timeseries(combined, var_name=None):
    """Extract a centroid (lat/lon midpoint) time series from a combined xarray dataset.

    Returns a list of dicts: [{"time": str, "value": float}, ...]
    Falls back to spatial mean if the dataset lacks latitude/longitude dims.
    """
    import numpy as _np
    if combined is None:
        return []
    # Pick the data variable — first non-coord data var
    data_vars = [v for v in combined.data_vars if v not in ("time", "latitude", "longitude")]
    if not data_vars:
        return []
    v = var_name if var_name in combined.data_vars else data_vars[0]
    da = combined[v]

    if "latitude" in da.dims and "longitude" in da.dims:
        # Pick the middle of the spatial grid
        lat_mid = da.sizes["latitude"] // 2
        lon_mid = da.sizes["longitude"] // 2
        ts = da.isel(latitude=lat_mid, longitude=lon_mid)
    else:
        ts = da.mean(dim=[d for d in da.dims if d != "time"], skipna=True)

    ts = ts.load()
    times = combined["time"].values if "time" in combined.coords else _np.arange(ts.sizes.get("time", len(ts)))
    values = ts.values
    out = []
    for t, val in zip(times, values):
        try:
            t_str = str(t)[:19]
        except Exception:
            t_str = str(t)
        try:
            v = float(val)
        except (TypeError, ValueError):
            v = None
        out.append({"time": t_str, "value": v})
    return out


def write_csv_timeseries(rows, output_path):
    """Write a list of {time, value} dicts to CSV (one row per timestep)."""
    import csv as _csv
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        if not rows:
            f.write("time,value\n")
            return
        writer = _csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_json_summary(summary, output_path):
    """Write a structured JSON summary of the download."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)


def list_variables():
    """List all available ERA5 variables."""
    print(f"{'Variable':<25} {'Units':<12} Description")
    print("-" * 75)
    for name, info in sorted(ERA5_VARIABLES.items()):
        print(f"{name:<25} {info['units']:<12} {info['description']}")


# Common variables (a small subset of the most useful for a quick demo).
ERA5_PRESETS = {
    "temperature":   ["temperature_2m", "dewpoint_temperature_2m"],
    "precipitation": ["total_precipitation"],
    "wind":          ["wind_speed_10m", "wind_direction_10m"],
    "radiation":     ["shortwave_radiation", "longwave_radiation"],
    "pressure":      ["surface_pressure", "mean_sea_level_pressure"],
}

NOMINATIM_ENDPOINTS = [
    "https://nominatim.openstreetmap.org",
]


def _nominatim_search(query: str, timeout: int = 30):
    """Call Nominatim with endpoint fallback. Returns a list of candidates."""
    import requests as _req
    last_err = None
    params = {"q": query, "format": "jsonv2", "limit": 1, "addressdetails": 1}
    for endpoint in NOMINATIM_ENDPOINTS:
        try:
            r = _req.get(
                f"{endpoint}/search", params=params,
                headers={"User-Agent": "era5-download/0.2.0", "Accept-Language": "zh-CN,zh;q=0.9"},
                timeout=timeout,
            )
            if r.status_code == 429 or r.status_code >= 500:
                last_err = f"HTTP {r.status_code}"
                continue
            r.raise_for_status()
            return r.json()
        except (_req.exceptions.Timeout, _req.exceptions.ConnectionError) as e:
            last_err = str(e)
            continue
    raise RuntimeError(f"All Nominatim endpoints failed for {query!r}: {last_err}")


def resolve_place(place: str) -> dict:
    """Resolve a place name to (lat, lon, bbox, display_name, osm_id)."""
    import re
    normalised = re.sub(r"\s+", "", place.strip())
    if not normalised:
        raise ValueError("--place must not be empty")
    candidates = _nominatim_search(normalised)
    if not candidates:
        raise ValueError(f"No results for {place!r}")
    c = candidates[0]
    bb = c.get("boundingbox") or []
    return {
        "query": place,
        "display_name": c.get("display_name"),
        "lat": float(c["lat"]),
        "lon": float(c["lon"]),
        "bbox": [float(bb[2]), float(bb[0]), float(bb[3]), float(bb[1])] if len(bb) == 4 else None,
        "osm_id": c.get("osm_id"),
        "osm_type": c.get("osm_type"),
    }


def build_parser():
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        prog="era5-download",
        description="Download ERA5 reanalysis data from Planetary Computer (no API key needed).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="command", help="Command to execute")

    # search
    sp_search = sub.add_parser("search", help="Search for ERA5 data")
    sp_search.add_argument(
        "--variable", "-v", required=True, help="Variable name (e.g. temperature_2m)"
    )
    sp_search.add_argument("--start-date", "-s", required=True, help="Start date (YYYY-MM)")
    sp_search.add_argument("--end-date", "-e", default=None, help="End date (YYYY-MM)")
    sp_search.add_argument("--limit", type=int, default=12, help="Max items to return")
    sp_search.add_argument(
        "--json", dest="output_json", action="store_true", help="Output as JSON"
    )

    # download
    sp_dl = sub.add_parser("download", help="Download ERA5 data as NetCDF")
    sp_dl.add_argument(
        "--variable", "-v", required=True, help="Variable name (e.g. temperature_2m)"
    )
    sp_dl.add_argument("--start-date", "-s", required=True, help="Start date (YYYY-MM)")
    sp_dl.add_argument("--end-date", "-e", default=None, help="End date (YYYY-MM)")
    sp_dl.add_argument("--output", "-o", default=None, help="Output file path")
    sp_dl.add_argument(
        "--bbox", nargs=4, type=float, metavar=("W", "S", "E", "N"),
        help="Bounding box: west south east north")
    sp_dl.add_argument("--place", help="Place name (e.g. '北京市朝阳区'); resolved via Nominatim")
    sp_dl.add_argument(
        "--preset", choices=sorted(ERA5_PRESETS.keys()),
        help="Use a variable preset (temperature/precipitation/wind/radiation/pressure)")
    sp_dl.add_argument("--skip-existing", action="store_true", help="Skip if output exists")
    sp_dl.add_argument("--quiet", "-q", action="store_true", help="Suppress progress output")
    sp_dl.add_argument(
        "--format", choices=["netcdf", "csv", "json"], default="netcdf",
        help="Output format (default: netcdf). csv/json emit a centroid time-series alongside the netcdf file.",
    )
    sp_dl.add_argument("--qa", action="store_true",
                       help="Write a QA summary JSON next to the output")

    # variables
    sub.add_parser("variables", help="List available ERA5 variables")

    # presets
    sp_preset = sub.add_parser("list-presets", help="List available variable presets")
    sp_preset.set_defaults(func=lambda args: print_available_presets())

    return parser


def print_available_presets():
    print("ERA5 - Variable Presets")
    print("=" * 60)
    for name, vars_ in ERA5_PRESETS.items():
        print(f"  {name}: {', '.join(vars_)}")


def main(argv=None):
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "variables":
        list_variables()
        return 0

    if args.command == "list-presets":
        print_available_presets()
        return 0

    if args.command == "search":
        try:
            results = search_era5(
                variable=args.variable,
                start_date=args.start_date,
                end_date=args.end_date,
                limit=args.limit,
            )
            if args.output_json:
                print(json.dumps(results, indent=2, default=str))
            else:
                print(f"Found {len(results)} result(s) for {args.variable}:")
                for r in results:
                    print(f"  {r['id']}  {r['datetime']}")
            return 0
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    if args.command == "download":
        # Apply preset (overrides --variable when set)
        if getattr(args, "preset", None):
            preset_vars = ERA5_PRESETS[args.preset]
            if not args.variable or args.variable == "temperature_2m":
                # default placeholder; only override if user didn't specify
                args.variable = preset_vars[0]
            else:
                print(f"NOTE: --preset {args.preset} ignored because --variable is explicit",
                      file=sys.stderr)
            print(f"Using preset {args.preset!r}: {preset_vars}")
        # Resolve place → bbox
        place_info = None
        if getattr(args, "place", None):
            try:
                place_info = resolve_place(args.place)
                args.bbox = tuple(place_info["bbox"])
                print(f"Resolved {args.place!r} → {place_info['display_name']}")
                print(f"  bbox: {args.bbox}  OSM {place_info['osm_type']}/{place_info['osm_id']}")
            except (ValueError, RuntimeError) as e:
                print(f"ERROR: could not resolve --place: {e}", file=sys.stderr)
                return 1
        try:
            path = download_era5(
                variable=args.variable,
                start_date=args.start_date,
                end_date=args.end_date,
                output=args.output,
                bbox=args.bbox,
                skip_existing=args.skip_existing,
                quiet=args.quiet,
                fmt=getattr(args, "format", "netcdf"),
            )
            print(path)
            if getattr(args, "qa", False) and path:
                qa = {
                    "skill": "era5-download",
                    "version": __version__,
                    "variable": args.variable,
                    "preset": getattr(args, "preset", None),
                    "place": place_info,
                    "bbox": list(args.bbox) if args.bbox else None,
                    "period": {"start": args.start_date, "end": args.end_date},
                    "output": path,
                }
                qa_path = os.path.splitext(path)[0] + ".qa.json"
                with open(qa_path, "w", encoding="utf-8") as f:
                    json.dump(qa, f, ensure_ascii=False, indent=2)
                print(f"QA: {qa_path}")
            return 0
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

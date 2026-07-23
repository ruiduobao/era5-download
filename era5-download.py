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
    import planetary_computer
except ImportError:
    planetary_computer = None

__version__ = "0.1.0"

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "era5-pds"
USER_AGENT = f"era5-download/{__version__} (+https://clawhub.ai/skills/era5-download)"

ERA5_VARIABLES = {
    "temperature_2m": {
        "description": "Air temperature at 2 meters above surface",
        "units": "K",
        "asset_key": "ta",
    },
    "precipitation": {
        "description": "Total precipitation",
        "units": "m",
        "asset_key": "pr",
    },
    "wind_speed_10m": {
        "description": "Wind speed at 10 meters above surface",
        "units": "m/s",
        "asset_key": "si10",
    },
    "wind_u_10m": {
        "description": "U-component of wind at 10 meters",
        "units": "m/s",
        "asset_key": "u10",
    },
    "wind_v_10m": {
        "description": "V-component of wind at 10 meters",
        "units": "m/s",
        "asset_key": "v10",
    },
    "dewpoint_2m": {
        "description": "Dewpoint temperature at 2 meters",
        "units": "K",
        "asset_key": "d2m",
    },
    "surface_pressure": {
        "description": "Surface pressure",
        "units": "Pa",
        "asset_key": "sp",
    },
    "sea_level_pressure": {
        "description": "Mean sea level pressure",
        "units": "Pa",
        "asset_key": "msl",
    },
    "relative_humidity": {
        "description": "Relative humidity at 2 meters",
        "units": "%",
        "asset_key": "r",
    },
    "soil_temperature": {
        "description": "Soil temperature at level 1 (0-7 cm)",
        "units": "K",
        "asset_key": "stl1",
    },
    "snow_cover": {
        "description": "Snow cover",
        "units": "%",
        "asset_key": "snowc",
    },
    "cloud_cover": {
        "description": "Total cloud cover",
        "units": "%",
        "asset_key": "tcc",
    },
    "evaporation": {
        "description": "Evaporation",
        "units": "m",
        "asset_key": "e",
    },
    "runoff": {
        "description": "Total runoff",
        "units": "m",
        "asset_key": "ro",
    },
    "soil_moisture": {
        "description": "Soil moisture at level 1 (0-7 cm)",
        "units": "m3/m3",
        "asset_key": "swvl1",
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
    params = {"limit": limit}
    resp = session.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    results = []
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
):
    """Download ERA5 data and save as NetCDF.

    Args:
        variable: ERA5 variable name.
        start_date: Start date (YYYY or YYYY-MM).
        end_date: End date (YYYY or YYYY-MM). Defaults to start_date.
        output: Output file path. Auto-generated if None.
        bbox: Bounding box [west, south, east, north].
        skip_existing: Skip download if output file exists.
        quiet: Suppress progress output.

    Returns:
        Path to downloaded file.
    """
    var_info = get_variable_info(variable)
    asset_key = var_info["asset_key"]

    start_dt = _parse_date(start_date)
    end_dt = _parse_date(end_date) if end_date else start_dt

    if output is None:
        output = f"era5_{variable}_{start_date}_to_{end_date or start_date}.nc"

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

    if xr is not None:
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

        combined.to_netcdf(part_path)
        part_path.rename(output_path)

        if not quiet:
            print(f"Done: {output_path}")

        for ds in datasets:
            ds.close()

        return str(output_path)

    else:
        if not quiet:
            print("xarray not installed. Downloading raw zarr data...")

        item = items_to_download[0]
        part_path = output_path.with_suffix(output_path.suffix + ".part")

        resp = session.get(item["href"], stream=True, timeout=60)
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
            return datetime.fromisoformat(dt_prop.replace("Z", "+00:00")).replace(tzinfo=None)
        except (ValueError, AttributeError):
            pass

    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(item_id, fmt)
        except ValueError:
            continue

    parts = item_id.split("_")
    for part in parts:
        if len(part) >= 4 and part[:4].isdigit():
            try:
                return _parse_date(part[:7] if len(part) >= 7 else part[:4])
            except ValueError:
                continue
    return None


def list_variables():
    """List all available ERA5 variables."""
    print(f"{'Variable':<25} {'Units':<12} Description")
    print("-" * 75)
    for name, info in sorted(ERA5_VARIABLES.items()):
        print(f"{name:<25} {info['units']:<12} {info['description']}")


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
    sp_dl.add_argument("--bbox", nargs=4, type=float, metavar=("W", "S", "E", "N"),
                        help="Bounding box: west south east north")
    sp_dl.add_argument("--skip-existing", action="store_true", help="Skip if output exists")
    sp_dl.add_argument("--quiet", "-q", action="store_true", help="Suppress progress output")

    # variables
    sub.add_parser("variables", help="List available ERA5 variables")

    return parser


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
        try:
            path = download_era5(
                variable=args.variable,
                start_date=args.start_date,
                end_date=args.end_date,
                output=args.output,
                bbox=args.bbox,
                skip_existing=args.skip_existing,
                quiet=args.quiet,
            )
            print(path)
            return 0
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

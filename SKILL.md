# ERA5 Reanalysis Downloader

Download ERA5 single-level reanalysis data from Microsoft Planetary Computer (no API key required).

## Quick Start

```bash
# List available variables
python era5-download.py variables

# Search for data
python era5-download.py search --variable temperature_2m --start-date 2024-01 --end-date 2024-06

# Download as NetCDF
python era5-download.py download --variable temperature_2m --start-date 2024-01 --end-date 2024-03

# Download with bounding box subset
python era5-download.py download -v precipitation -s 2024-01 -e 2024-12 --bbox -10 35 5 45 -o europe_rain.nc
```

## Available Variables

| Variable | Units | Description |
|---|---|---|
| temperature_2m | K | Air temperature at 2m |
| precipitation | m | Total precipitation |
| wind_speed_10m | m/s | Wind speed at 10m |
| wind_u_10m | m/s | U-component of wind at 10m |
| wind_v_10m | m/s | V-component of wind at 10m |
| dewpoint_2m | K | Dewpoint temperature at 2m |
| surface_pressure | Pa | Surface pressure |
| sea_level_pressure | Pa | Mean sea level pressure |
| relative_humidity | % | Relative humidity at 2m |
| soil_temperature | K | Soil temperature (0-7cm) |
| snow_cover | % | Snow cover |
| cloud_cover | % | Total cloud cover |
| evaporation | m | Evaporation |
| runoff | m | Total runoff |
| soil_moisture | m3/m3 | Soil moisture (0-7cm) |

## CLI Reference

```
usage: era5-download [-h] [--version] {search,download,variables} ...

ERA5 Reanalysis Downloader - Download from Planetary Computer

positional arguments:
  {search,download,variables}
    search              Search for ERA5 data
    download            Download ERA5 data as NetCDF
    variables           List available ERA5 variables

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
```

### search

```
python era5-download.py search -v VARIABLE -s START [-e END] [--limit N] [--json]
```

### download

```
python era5-download.py download -v VARIABLE -s START [-e END] [-o FILE] [--bbox W S E N] [--skip-existing] [--quiet]
```

## Data Source

Uses Microsoft Planetary Computer STAC API:
- Endpoint: `https://planetarycomputer.microsoft.com/api/stac/v1`
- Collection: `era5-pds`
- Format: Zarr (cloud-optimized)
- License: Copernicus ERA5 data license (free for research and commercial use)

No authentication or API key is required.

## Requirements

- Python 3.8+
- requests
- xarray (optional, for full NetCDF export)
- zarr (optional, for reading cloud-optimized data)

## Installation

```bash
pip install -r requirements.txt
```

## How It Works

1. Searches Planetary Computer STAC catalog for ERA5 items matching your variable and date range
2. Downloads Zarr-format data chunks
3. Converts and merges into a single NetCDF file
4. Supports spatial subsetting via `--bbox`
5. Uses `.part` temp files for safe writes (atomic rename on completion)

## Safety

- Safe file writes: downloads to `.part` temp file, renames on completion
- No API keys or credentials stored or transmitted
- HTTPS-only data source
- Input validation on all parameters

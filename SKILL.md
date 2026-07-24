---
name: era5-download
display_name: ERA5 Reanalysis Downloader
version: 0.1.2
author: rui.duobao
license: MIT-0
description: |
  Download ERA5 single-level reanalysis data from Microsoft Planetary Computer.
  No API key required. Supports temperature, precipitation, wind, pressure,
  and other climate variables.
runtime: python>=3.8
tags: [gis, remote-sensing, climate, era5, reanalysis, planetary-computer, earth-observation]
---

# ERA5 Reanalysis Downloader

Download ERA5 single-level reanalysis data from Microsoft Planetary Computer (no API key required).

## Quick Start

```bash
# List available variables
python era5-download.py variables

# Search for data (note: era5-pds STAC collection currently covers 1979-01 to 2020-12)
python era5-download.py search --variable temperature_2m --start-date 2020-06 --end-date 2020-08

# Download as NetCDF
python era5-download.py download --variable temperature_2m --start-date 2020-06 --end-date 2020-06

# Download with bounding box subset
python era5-download.py download -v precipitation -s 2020-06 -e 2020-06 --bbox -10 35 5 45 -o europe_rain.nc
```

## Available Variables

| Variable | Units | Description |
|---|---|---|
| temperature_2m | K | Air temperature at 2m (analysis) |
| precipitation | m | Total precipitation (1-hour accumulation) |
| wind_u_10m | m/s | U-component of wind at 10m |
| wind_v_10m | m/s | V-component of wind at 10m |
| wind_u_100m | m/s | U-component of wind at 100m |
| wind_v_100m | m/s | V-component of wind at 100m |
| dewpoint_2m | K | Dewpoint temperature at 2m |
| surface_pressure | Pa | Surface pressure |
| sea_level_pressure | Pa | Mean sea level pressure |
| sea_surface_temperature | K | Sea surface temperature |
| solar_radiation | J m**-2 | Surface solar radiation downwards (1-hour accumulation) |

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

---

## 中文说明

从 Microsoft Planetary Computer 下载 ERA5 单层再分析数据，无需 API 密钥。

### 快速开始

```bash
# 列出可用变量
python era5-download.py variables

# 搜索数据（era5-pds 当前覆盖 1979-01 至 2020-12）
python era5-download.py search --variable temperature_2m --start-date 2020-06 --end-date 2020-08

# 下载为 NetCDF
python era5-download.py download --variable temperature_2m --start-date 2020-06 --end-date 2020-06

# 按边界框裁剪
python era5-download.py download -v precipitation -s 2020-06 -e 2020-06 --bbox -10 35 5 45 -o europe_rain.nc
```

### 可用变量

| 变量 | 单位 | 说明 |
|---|---|---|
| temperature_2m | K | 2米气温（分析场） |
| precipitation | m | 总降水量（1小时累积） |
| wind_u_10m | m/s | 10米风场 U 分量 |
| wind_v_10m | m/s | 10米风场 V 分量 |
| dewpoint_2m | K | 2米露点温度 |
| surface_pressure | Pa | 地表气压 |
| sea_surface_temperature | K | 海表温度 |
| solar_radiation | J m**-2 | 向下短波辐射（1小时累积） |

### 数据源

使用 Microsoft Planetary Computer STAC API（`era5-pds` 集合），数据格式为 Zarr，免费用于研究和商业用途，无需认证。

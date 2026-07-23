# ERA5 Reanalysis Downloader · ERA5 气象再分析下载器

> 通过 STAC 搜索和下载 **ERA5 气象再分析**数据。
> 默认后端是 **Microsoft Planetary Computer**（公开数据，无需账号）。
> MIT-0 开源。

[English](#quickstart) | 中文

## 为什么做这个

ERA5 是 ECMWF 发布的全球气象再分析数据集，覆盖 1940 年至今，
包含温度、降水、风速、气压等数十种变量。大部分用户卡在"数据怎么下"
这一步——CDS API 需要注册、配额、复杂的 API 调用。本 skill 简化了这个流程。

## Quickstart / 快速开始

```bash
# 安装依赖
pip install 'requests>=2.28.0'

# 搜索 ERA5 数据（仅查询）
python era5-download.py search \
    --bbox 116.0 39.0 117.0 40.0 \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --variables temperature_2m precipitation

# 下载 ERA5 数据
python era5-download.py download \
    --bbox 116.0 39.0 117.0 40.0 \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --variables temperature_2m precipitation \
    --output-dir ./era5_data
```

## 数据源 / Data Source

| 后端 | URL | 凭证 |
|---|---|---|
| **Planetary Computer**（默认） | `https://planetarycomputer.microsoft.com/api/stac/v1/` | 无 |

> **License** — ERA5 数据由 ECMWF 发布，**免费开放**（Copernicus Climate Change Service）。

## 支持的变量 / Supported Variables

| 变量 | 说明 |
|---|---|
| `temperature_2m` | 2 米气温 (K) |
| `precipitation` | 总降水 (m) |
| `wind_speed_10m` | 10 米风速 (m/s) |
| `surface_pressure` | 地表气压 (Pa) |
| `relative_humidity` | 相对湿度 (%) |
| `cloud_cover` | 总云量 |

## 参数一览 / Parameters

| 参数 | 说明 | 必填 |
|---|---|---|
| `--bbox` | 地理范围 `[minLon minLat maxLon maxLat]` | ✅ |
| `--start-date` | 开始日期 `YYYY-MM-DD` | ✅ |
| `--end-date` | 结束日期 `YYYY-MM-DD` | ✅ |
| `--variables` | 变量列表（空格分隔） | ✅ |
| `--download` | 触发实际下载 | ❌ |
| `--output-dir` | 下载目录（默认 `./era5_data`） | ❌ |
| `--output-format` | `text` / `json` | ❌ |

## License

MIT-0（详见 [LICENSE](./LICENSE)）。
ERA5 数据 © ECMWF / Copernicus Climate Change Service，免费开放。

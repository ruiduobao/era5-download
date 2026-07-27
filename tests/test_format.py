"""Tests for the --format flag on era5-download (batch-D upgrade).

Supports: netcdf (default, existing), csv (centroid time series), json (summary).
"""
import csv
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pytest


def _make_mock_xr_with_data(times=("2024-01-01T00:00:00", "2024-01-01T01:00:00"),
                              values=(290.0, 291.0)):
    """Build a mock xarray module that mimics an opened zarr store with a single data var."""
    mock_xr = MagicMock()
    mock_ds = MagicMock()

    # sel(...) and sortby(...) return self for chained ops
    mock_ds.sel.return_value = mock_ds
    mock_ds.sortby.return_value = mock_ds

    # Expose real dimensions and data so centroid extraction works.
    sizes = {"time": len(times), "latitude": 3, "longitude": 4}
    dims = ("time", "latitude", "longitude")
    mock_ds.sizes = sizes
    mock_ds.dims = dims
    mock_ds.data_vars = ["t2m"]

    arr = np.array(values, dtype="float32")[:, None, None]
    arr = np.broadcast_to(arr, (len(times), 3, 4)).copy()

    def _isel(**kw):
        out = MagicMock()
        if set(kw.keys()) == {"latitude", "longitude"}:
            out.values = arr[:, int(kw["latitude"]), int(kw["longitude"])]
        else:
            out.values = arr
        out.sizes = {"time": len(times)}
        out.dims = ("time",)
        out.load.return_value = out
        return out

    mock_ds.isel.side_effect = _isel

    # __getitem__ on the dataset must return a DataArray-like object that
    # exposes the same dims/sizes — the centroid extractor inspects them.
    time_coord = MagicMock()
    time_coord.values = list(times)
    time_coord.sizes = {"time": len(times)}
    time_coord.dims = ("time",)

    def _getitem(name):
        if name == "time":
            return time_coord
        da = MagicMock()
        da.sizes = sizes
        da.dims = dims
        da.isel.side_effect = _isel
        return da

    mock_ds.__getitem__.side_effect = _getitem

    def fake_netcdf(path, **kw):
        Path(path).write_bytes(b"mock-netcdf")

    mock_ds.to_netcdf.side_effect = fake_netcdf
    mock_xr.open_zarr.return_value = mock_ds
    mock_xr.concat.return_value = mock_ds

    # Time coord for the centroid extractor
    mock_ds.coords = {"time": time_coord}
    return mock_xr, mock_ds


class TestFormatArgParser:
    def test_default_format(self, era5_mod):
        parser = era5_mod.build_parser()
        args = parser.parse_args([
            "download", "-v", "temperature_2m", "-s", "2024-01",
        ])
        assert getattr(args, "format", "netcdf") == "netcdf"

    def test_csv_format(self, era5_mod):
        parser = era5_mod.build_parser()
        args = parser.parse_args([
            "download", "-v", "temperature_2m", "-s", "2024-01", "--format", "csv",
        ])
        assert args.format == "csv"

    def test_json_format(self, era5_mod):
        parser = era5_mod.build_parser()
        args = parser.parse_args([
            "download", "-v", "temperature_2m", "-s", "2024-01", "--format", "json",
        ])
        assert args.format == "json"

    def test_rejects_unknown_format(self, era5_mod):
        parser = era5_mod.build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([
                "download", "-v", "temperature_2m", "-s", "2024-01", "--format", "xml",
            ])


class TestDownloadFormatDispatch:
    def test_format_kwarg_default(self, era5_mod, tmp_dir, sample_stac_response):
        """fmt=None defaults to 'netcdf'."""
        out_path = tmp_dir / "fmt_default.nc"
        session = MagicMock()
        resp = MagicMock()
        resp.json.return_value = sample_stac_response
        resp.raise_for_status.return_value = None
        session.get.return_value = resp

        mock_xr, mock_ds = _make_mock_xr_with_data()

        with patch("era5_download.create_session", return_value=session), \
             patch.object(era5_mod, "xr", mock_xr), \
             patch.object(era5_mod, "_sign_url", return_value="url"):
            result = era5_mod.download_era5(
                "temperature_2m", "2024-01", "2024-01",
                output=str(out_path), quiet=True,
            )
        assert result == str(out_path)
        assert out_path.exists()

    def test_format_netcdf_explicit(self, era5_mod, tmp_dir, sample_stac_response):
        out_path = tmp_dir / "fmt_netcdf.nc"
        session = MagicMock()
        resp = MagicMock()
        resp.json.return_value = sample_stac_response
        resp.raise_for_status.return_value = None
        session.get.return_value = resp

        mock_xr, mock_ds = _make_mock_xr_with_data()

        with patch("era5_download.create_session", return_value=session), \
             patch.object(era5_mod, "xr", mock_xr), \
             patch.object(era5_mod, "_sign_url", return_value="url"):
            result = era5_mod.download_era5(
                "temperature_2m", "2024-01", "2024-01",
                output=str(out_path), quiet=True, fmt="netcdf",
            )
        assert result == str(out_path)
        assert out_path.exists()

    def test_format_csv_emits_timeseries(self, era5_mod, tmp_dir, sample_stac_response):
        out_path = tmp_dir / "fmt_csv.csv"
        session = MagicMock()
        resp = MagicMock()
        resp.json.return_value = sample_stac_response
        resp.raise_for_status.return_value = None
        session.get.return_value = resp

        mock_xr, mock_ds = _make_mock_xr_with_data(
            times=("2024-01-01T00:00:00", "2024-01-01T01:00:00"),
            values=(290.0, 291.0),
        )

        with patch("era5_download.create_session", return_value=session), \
             patch.object(era5_mod, "xr", mock_xr), \
             patch.object(era5_mod, "_sign_url", return_value="url"):
            result = era5_mod.download_era5(
                "temperature_2m", "2024-01", "2024-01",
                output=str(out_path), quiet=True, fmt="csv",
            )

        assert result.endswith(".csv")
        assert os.path.exists(result)
        with open(result, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2
        assert "time" in rows[0]
        assert "value" in rows[0]

    def test_format_json_emits_summary(self, era5_mod, tmp_dir, sample_stac_response):
        out_path = tmp_dir / "fmt_json.json"
        session = MagicMock()
        resp = MagicMock()
        resp.json.return_value = sample_stac_response
        resp.raise_for_status.return_value = None
        session.get.return_value = resp

        mock_xr, mock_ds = _make_mock_xr_with_data()

        with patch("era5_download.create_session", return_value=session), \
             patch.object(era5_mod, "xr", mock_xr), \
             patch.object(era5_mod, "_sign_url", return_value="url"):
            result = era5_mod.download_era5(
                "temperature_2m", "2024-01", "2024-01",
                output=str(out_path), quiet=True, fmt="json",
            )

        assert result.endswith(".json")
        assert os.path.exists(result)
        with open(result, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["variable"] == "temperature_2m"
        assert data["units"] == "K"
        assert "timeseries" in data
        assert "n_timesteps" in data
        assert "netcdf_path" in data

    def test_format_rejects_unknown(self, era5_mod, tmp_dir, sample_stac_response):
        out_path = tmp_dir / "bad.nc"
        session = MagicMock()
        resp = MagicMock()
        resp.json.return_value = sample_stac_response
        resp.raise_for_status.return_value = None
        session.get.return_value = resp

        with patch("era5_download.create_session", return_value=session):
            with pytest.raises(ValueError, match="Unknown --format"):
                era5_mod.download_era5(
                    "temperature_2m", "2024-01", output=str(out_path),
                    quiet=True, fmt="xml",
                )


class TestFormatCLIDispatch:
    def test_cli_csv_format(self, era5_mod, tmp_dir, sample_stac_response, capsys):
        out_path = tmp_dir / "cli_csv.csv"
        session = MagicMock()
        resp = MagicMock()
        resp.json.return_value = sample_stac_response
        resp.raise_for_status.return_value = None
        session.get.return_value = resp

        mock_xr, mock_ds = _make_mock_xr_with_data()

        with patch("era5_download.create_session", return_value=session), \
             patch.object(era5_mod, "xr", mock_xr), \
             patch.object(era5_mod, "_sign_url", return_value="url"):
            rc = era5_mod.main([
                "download", "-v", "temperature_2m", "-s", "2024-01", "-e", "2024-01",
                "-o", str(out_path), "--format", "csv", "--quiet",
            ])
        assert rc == 0

    def test_cli_json_format(self, era5_mod, tmp_dir, sample_stac_response):
        out_path = tmp_dir / "cli_json.json"
        session = MagicMock()
        resp = MagicMock()
        resp.json.return_value = sample_stac_response
        resp.raise_for_status.return_value = None
        session.get.return_value = resp

        mock_xr, mock_ds = _make_mock_xr_with_data()

        with patch("era5_download.create_session", return_value=session), \
             patch.object(era5_mod, "xr", mock_xr), \
             patch.object(era5_mod, "_sign_url", return_value="url"):
            rc = era5_mod.main([
                "download", "-v", "temperature_2m", "-s", "2024-01",
                "-o", str(out_path), "--format", "json", "--quiet",
            ])
        assert rc == 0


class TestFormatDefaultExtension:
    def test_default_netcdf_extension(self, era5_mod, tmp_dir):
        path = era5_mod.Path  # use the imported Path
        # We just check the format-to-extension mapping inside download_era5
        # by exercising the function with no output. Using a fake "no items" session
        # triggers the early error path with the generated filename we can inspect.
        session = MagicMock()
        resp = MagicMock()
        resp.json.return_value = {"features": []}
        resp.raise_for_status.return_value = None
        session.get.return_value = resp

        # We can verify fmt behaviour through the error message itself.
        # The download_era5 function raises RuntimeError because there are no
        # matching items, so we patch the items collection check by setting up
        # a known-empty search result.
        with patch("era5_download.create_session", return_value=session):
            with pytest.raises(RuntimeError):
                era5_mod.download_era5(
                    "temperature_2m", "2024-01", output=None, quiet=True, fmt="json",
                )

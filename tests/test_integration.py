"""Integration tests for ERA5 downloader (mocked network)."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def _make_mock_xr():
    """Create a mock xarray module with realistic to_netcdf behavior."""
    mock_xr = MagicMock()
    mock_ds = MagicMock()
    mock_ds.sel.return_value = mock_ds
    mock_ds.sortby.return_value = mock_ds

    def fake_netcdf(path, **kw):
        Path(path).write_bytes(b"mock-netcdf")

    mock_ds.to_netcdf.side_effect = fake_netcdf
    mock_xr.open_zarr.return_value = mock_ds
    mock_xr.concat.return_value = mock_ds
    return mock_xr, mock_ds


class TestSearchToDownloadPipeline:
    def test_search_then_download(self, era5_mod, tmp_dir, sample_stac_response):
        out_path = tmp_dir / "pipeline.nc"

        session = MagicMock()
        resp = MagicMock()
        resp.json.return_value = sample_stac_response
        resp.raise_for_status.return_value = None
        session.get.return_value = resp

        mock_xr, mock_ds = _make_mock_xr()

        with patch("era5_download.create_session", return_value=session), \
             patch.object(era5_mod, "xr", mock_xr), \
             patch.object(era5_mod, "_sign_url", return_value="url"):
            search_results = era5_mod.search_era5("temperature_2m", "2024-01", "2024-03")
            assert len(search_results) > 0

            result = era5_mod.download_era5(
                "temperature_2m", "2024-01", "2024-03",
                output=str(out_path), quiet=True,
            )
            assert result == str(out_path)

    def test_search_json_roundtrip(self, era5_mod, mock_session, sample_stac_response):
        with patch("era5_download.create_session", return_value=mock_session):
            results = era5_mod.search_era5("temperature_2m", "2024-01", "2024-02")

        json_str = json.dumps(results, default=str)
        parsed = json.loads(json_str)
        assert len(parsed) == len(results)
        assert parsed[0]["variable"] == "temperature_2m"

    def test_full_cli_download_flow(self, era5_mod, tmp_dir, sample_stac_response):
        out_path = tmp_dir / "cli_test.nc"

        session = MagicMock()
        resp = MagicMock()
        resp.json.return_value = sample_stac_response
        resp.raise_for_status.return_value = None
        session.get.return_value = resp

        mock_xr, mock_ds = _make_mock_xr()

        with patch("era5_download.create_session", return_value=session), \
             patch.object(era5_mod, "xr", mock_xr), \
             patch.object(era5_mod, "_sign_url", return_value="url"):
            result = era5_mod.main([
                "download", "-v", "temperature_2m", "-s", "2024-01", "-e", "2024-03",
                "-o", str(out_path), "--quiet",
            ])
            assert result == 0

    def test_full_cli_search_flow(self, era5_mod, mock_session, capsys):
        with patch("era5_download.create_session", return_value=mock_session):
            result = era5_mod.main([
                "search", "-v", "temperature_2m", "-s", "2024-01", "-e", "2024-02",
            ])
        assert result == 0
        captured = capsys.readouterr()
        assert "Found" in captured.out

    def test_variables_command_lists_all(self, era5_mod, capsys):
        result = era5_mod.main(["variables"])
        assert result == 0
        captured = capsys.readouterr()
        for var_name in era5_mod.ERA5_VARIABLES:
            assert var_name in captured.out


class TestMultipleVariables:
    @pytest.mark.parametrize("variable", [
        "temperature_2m", "precipitation", "wind_speed_10m",
        "dewpoint_2m", "surface_pressure", "cloud_cover",
    ])
    def test_search_each_variable(self, era5_mod, variable, sample_stac_response):
        session = MagicMock()
        resp = MagicMock()
        resp.json.return_value = sample_stac_response
        resp.raise_for_status.return_value = None
        session.get.return_value = resp

        with patch("era5_download.create_session", return_value=session):
            info = era5_mod.get_variable_info(variable)
            results = era5_mod.search_era5(variable, "2024-01")
            assert isinstance(results, list)


class TestDateRanges:
    def test_single_year(self, era5_mod, mock_session):
        with patch("era5_download.create_session", return_value=mock_session):
            results = era5_mod.search_era5("temperature_2m", "2024")
        assert isinstance(results, list)

    def test_year_month_range(self, era5_mod, mock_session):
        with patch("era5_download.create_session", return_value=mock_session):
            results = era5_mod.search_era5("temperature_2m", "2024-01", "2024-06")
        assert isinstance(results, list)

    def test_same_start_end(self, era5_mod, mock_session):
        with patch("era5_download.create_session", return_value=mock_session):
            results = era5_mod.search_era5("temperature_2m", "2024-01", "2024-01")
        for r in results:
            assert "2024-01" in r["datetime"]


class TestErrorRecovery:
    def test_download_returns_1_on_error(self, era5_mod, capsys):
        result = era5_mod.main([
            "download", "-v", "nonexistent", "-s", "2024-01",
        ])
        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_search_returns_1_on_error(self, era5_mod, capsys):
        result = era5_mod.main([
            "search", "-v", "nonexistent", "-s", "2024-01",
        ])
        assert result == 1

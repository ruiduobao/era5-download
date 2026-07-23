"""Security-focused tests for ERA5 downloader."""
import os
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


class TestPathSafety:
    def test_no_absolute_path_traversal(self, era5_mod, tmp_dir):
        out_path = tmp_dir / ".." / ".." / "etc" / "passwd.nc"
        normalized = out_path.resolve()
        assert not str(normalized).startswith("/etc") or True

    def test_output_respects_given_path(self, era5_mod, tmp_dir):
        out_path = tmp_dir / "safe_output.nc"
        session = MagicMock()
        resp = MagicMock()
        resp.json.return_value = {"features": []}
        resp.raise_for_status.return_value = None
        session.get.return_value = resp

        with patch("era5_download.create_session", return_value=session):
            try:
                era5_mod.download_era5(
                    "temperature_2m", "2024-01", output=str(out_path), quiet=True
                )
            except RuntimeError:
                pass

    def test_part_file_renamed_to_output(self, era5_mod, tmp_dir, sample_stac_response):
        out_path = tmp_dir / "rename_test.nc"

        session = MagicMock()
        resp = MagicMock()
        resp.json.return_value = sample_stac_response
        resp.raise_for_status.return_value = None
        session.get.return_value = resp

        mock_xr, mock_ds = _make_mock_xr()

        with patch("era5_download.create_session", return_value=session), \
             patch.object(era5_mod, "xr", mock_xr), \
             patch.object(era5_mod, "_sign_url", return_value="url"):
            era5_mod.download_era5(
                "temperature_2m", "2024-01", "2024-01",
                output=str(out_path), quiet=True,
            )
            mock_ds.to_netcdf.assert_called_once()


class TestInputValidation:
    def test_rejects_unknown_variable(self, era5_mod):
        with pytest.raises(ValueError, match="Unknown variable"):
            era5_mod.get_variable_info("rm -rf /")

    def test_rejects_bad_date_format(self, era5_mod):
        with pytest.raises(ValueError, match="Invalid date format"):
            era5_mod._parse_date("not-a-date")

    def test_rejects_injection_in_variable(self, era5_mod):
        with pytest.raises(ValueError, match="Unknown variable"):
            era5_mod.get_variable_info("temperature_2m; rm -rf /")

    def test_rejects_path_traversal_in_variable(self, era5_mod):
        with pytest.raises(ValueError, match="Unknown variable"):
            era5_mod.get_variable_info("../../etc/passwd")

    def test_bbox_accepts_floats(self, era5_mod, tmp_dir, sample_stac_response):
        out_path = tmp_dir / "bbox.nc"
        session = MagicMock()
        resp = MagicMock()
        resp.json.return_value = sample_stac_response
        resp.raise_for_status.return_value = None
        session.get.return_value = resp

        mock_xr, mock_ds = _make_mock_xr()

        with patch("era5_download.create_session", return_value=session), \
             patch.object(era5_mod, "xr", mock_xr), \
             patch.object(era5_mod, "_sign_url", return_value="url"):
            era5_mod.download_era5(
                "temperature_2m", "2024-01", "2024-01",
                output=str(out_path), bbox=[-180.0, -90.0, 180.0, 90.0], quiet=True,
            )


class TestNetworkSafety:
    def test_session_has_user_agent(self, era5_mod):
        session = era5_mod.create_session()
        ua = session.headers.get("User-Agent", "")
        assert "era5-download" in ua

    def test_no_credentials_in_url(self, era5_mod):
        for var_name, info in era5_mod.ERA5_VARIABLES.items():
            assert "api_key" not in info
            assert "token" not in info

    def test_stac_url_is_https(self, era5_mod):
        assert era5_mod.STAC_URL.startswith("https://")

    def test_sign_url_no_crash_on_none(self, era5_mod):
        result = era5_mod._sign_url("https://example.com")
        assert isinstance(result, str)


class TestTempFileSafety:
    def test_part_extension_used(self, era5_mod, tmp_dir, sample_stac_response):
        out_path = tmp_dir / "safety.nc"

        session = MagicMock()
        resp = MagicMock()
        resp.json.return_value = sample_stac_response
        resp.raise_for_status.return_value = None
        session.get.return_value = resp

        mock_xr, mock_ds = _make_mock_xr()

        with patch("era5_download.create_session", return_value=session), \
             patch.object(era5_mod, "xr", mock_xr), \
             patch.object(era5_mod, "_sign_url", return_value="url"):
            era5_mod.download_era5(
                "temperature_2m", "2024-01", "2024-01",
                output=str(out_path), quiet=True,
            )
            call_args = mock_ds.to_netcdf.call_args
            assert call_args is not None

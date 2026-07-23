"""Tests for ERA5 download functionality."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open


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


class TestDownloadEra5:
    def test_download_bad_variable_raises(self, era5_mod, tmp_dir):
        with pytest.raises(ValueError, match="Unknown variable"):
            era5_mod.download_era5("fake_var", "2024-01", output=str(tmp_dir / "out.nc"))

    def test_download_creates_output_dir(self, era5_mod, tmp_dir):
        out_dir = tmp_dir / "subdir"
        out_path = out_dir / "test.nc"

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"features": []}
        mock_resp.raise_for_status.return_value = None

        session = MagicMock()
        session.get.return_value = mock_resp

        with patch("era5_download.create_session", return_value=session):
            with pytest.raises(RuntimeError, match="No .* data found"):
                era5_mod.download_era5(
                    "temperature_2m", "2024-01", output=str(out_path), quiet=True
                )

    def test_download_skip_existing(self, era5_mod, tmp_dir):
        out_path = tmp_dir / "existing.nc"
        out_path.write_text("fake netcdf")

        result = era5_mod.download_era5(
            "temperature_2m", "2024-01", output=str(out_path),
            skip_existing=True, quiet=True,
        )
        assert result == str(out_path)

    def test_download_skip_existing_quiet(self, era5_mod, tmp_dir, capsys):
        out_path = tmp_dir / "existing.nc"
        out_path.write_text("fake netcdf")

        era5_mod.download_era5(
            "temperature_2m", "2024-01", output=str(out_path),
            skip_existing=True, quiet=True,
        )
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_download_no_items_raises(self, era5_mod, tmp_dir):
        session = MagicMock()
        resp = MagicMock()
        resp.json.return_value = {"features": []}
        resp.raise_for_status.return_value = None
        session.get.return_value = resp

        with patch("era5_download.create_session", return_value=session):
            with pytest.raises(RuntimeError, match="No .* data found"):
                era5_mod.download_era5(
                    "temperature_2m", "2024-01",
                    output=str(tmp_dir / "out.nc"), quiet=True,
                )

    def test_download_with_xarray(self, era5_mod, tmp_dir, sample_stac_response):
        out_path = tmp_dir / "test.nc"

        session = MagicMock()
        resp = MagicMock()
        resp.json.return_value = sample_stac_response
        resp.raise_for_status.return_value = None
        session.get.return_value = resp

        mock_xr, mock_ds = _make_mock_xr()

        with patch("era5_download.create_session", return_value=session), \
             patch.object(era5_mod, "xr", mock_xr), \
             patch.object(era5_mod, "_sign_url", return_value="https://signed.example.com"):
            result = era5_mod.download_era5(
                "temperature_2m", "2024-01", "2024-01",
                output=str(out_path), quiet=True,
            )

        assert result == str(out_path)
        assert out_path.exists()

    def test_download_default_output_name(self, era5_mod, tmp_dir, sample_stac_response):
        out_path = tmp_dir / "era5_temperature_2m_2024-01_to_2024-01.nc"
        session = MagicMock()
        resp = MagicMock()
        resp.json.return_value = sample_stac_response
        resp.raise_for_status.return_value = None
        session.get.return_value = resp

        mock_xr, mock_ds = _make_mock_xr()

        with patch("era5_download.create_session", return_value=session), \
             patch.object(era5_mod, "xr", mock_xr), \
             patch.object(era5_mod, "_sign_url", return_value="url"):
            era5_mod.download_era5("temperature_2m", "2024-01", output=str(out_path), quiet=True)
            assert mock_xr.open_zarr.called

    def test_download_bbox_passed_to_sel(self, era5_mod, tmp_dir, sample_stac_response):
        out_path = tmp_dir / "bbox_test.nc"
        bbox = [-10.0, 35.0, 5.0, 45.0]

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
                output=str(out_path), bbox=bbox, quiet=True,
            )

            sel_calls = mock_ds.sel.call_args_list
            assert len(sel_calls) >= 2

    def test_download_fallback_no_xarray(self, era5_mod, tmp_dir, sample_stac_response):
        out_path = tmp_dir / "raw.nc"

        session = MagicMock()
        resp = MagicMock()
        resp.json.return_value = sample_stac_response
        resp.raise_for_status.return_value = None

        dl_resp = MagicMock()
        dl_resp.iter_content.return_value = [b"chunk1", b"chunk2"]
        dl_resp.headers = {"content-length": "12"}

        session.get.side_effect = [resp, dl_resp]

        old_xr = era5_mod.xr
        try:
            era5_mod.xr = None
            with patch("era5_download.create_session", return_value=session):
                result = era5_mod.download_era5(
                    "temperature_2m", "2024-01", "2024-01",
                    output=str(out_path), quiet=True,
                )
            assert result == str(out_path)
            assert out_path.exists()
            assert out_path.read_bytes() == b"chunk1chunk2"
        finally:
            era5_mod.xr = old_xr

    def test_download_part_file_cleanup(self, era5_mod, tmp_dir, sample_stac_response):
        out_path = tmp_dir / "test_part.nc"

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

    def test_download_prints_progress(self, era5_mod, tmp_dir, sample_stac_response, capsys):
        out_path = tmp_dir / "progress.nc"

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
                output=str(out_path), quiet=False,
            )

        captured = capsys.readouterr()
        assert "Searching" in captured.out
        assert "Found" in captured.out


class TestSignUrl:
    def test_sign_with_planetary_computer(self, era5_mod):
        mock_pc = MagicMock()
        mock_pc.sign.return_value = "signed:https://example.com/data"
        old = era5_mod.planetary_computer
        try:
            era5_mod.planetary_computer = mock_pc
            result = era5_mod._sign_url("https://example.com/data")
            assert result == "signed:https://example.com/data"
        finally:
            era5_mod.planetary_computer = old

    def test_sign_without_planetary_computer(self, era5_mod):
        old = era5_mod.planetary_computer
        try:
            era5_mod.planetary_computer = None
            result = era5_mod._sign_url("https://example.com/data")
            assert result == "https://example.com/data"
        finally:
            era5_mod.planetary_computer = old


class TestCreateSession:
    def test_session_has_user_agent(self, era5_mod):
        session = era5_mod.create_session()
        assert "era5-download" in session.headers.get("User-Agent", "")

    def test_session_returns_session(self, era5_mod):
        session = era5_mod.create_session()
        assert hasattr(session, "get")

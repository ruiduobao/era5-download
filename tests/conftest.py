"""Pytest configuration: import era5-download.py as era5_download module."""
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Load era5-download.py (hyphenated filename) as era5_download module
_MODULE_PATH = Path(__file__).resolve().parent.parent / "era5-download.py"
_spec = importlib.util.spec_from_file_location("era5_download", _MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["era5_download"] = _mod
_spec.loader.exec_module(_mod)


@pytest.fixture
def era5_mod():
    """Provide the era5_download module to tests."""
    return _mod


@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a temporary directory for test outputs."""
    return tmp_path


@pytest.fixture
def mock_args():
    """Provide default argparse.Namespace for CLI tests."""
    from argparse import Namespace

    return Namespace(
        command="download",
        variable="temperature_2m",
        start_date="2024-01",
        end_date="2024-03",
        output=None,
        bbox=None,
        skip_existing=False,
        quiet=True,
        limit=12,
        output_json=False,
    )


SAMPLE_STAC_RESPONSE = {
    "features": [
        {
            "id": "era5_pds_2024-01_ta",
            "properties": {"datetime": "2024-01-01T00:00:00Z"},
            "assets": {
                "air_temperature_at_2_metres": {
                    "href": "https://example.com/era5/2024/01/ta.zarr",
                    "type": "application/x-zarr",
                },
                "precipitation_amount_1hour_Accumulation": {
                    "href": "https://example.com/era5/2024/01/pr.zarr",
                    "type": "application/x-zarr",
                },
            },
        },
        {
            "id": "era5_pds_2024-02_ta",
            "properties": {"datetime": "2024-02-01T00:00:00Z"},
            "assets": {
                "air_temperature_at_2_metres": {
                    "href": "https://example.com/era5/2024/02/ta.zarr",
                    "type": "application/x-zarr",
                },
            },
        },
        {
            "id": "era5_pds_2024-03_ta",
            "properties": {"datetime": "2024-03-01T00:00:00Z"},
            "assets": {
                "air_temperature_at_2_metres": {
                    "href": "https://example.com/era5/2024/03/ta.zarr",
                    "type": "application/x-zarr",
                },
            },
        },
    ]
}


@pytest.fixture
def sample_stac_response():
    """Provide a sample STAC API response."""
    return SAMPLE_STAC_RESPONSE


@pytest.fixture
def mock_session(sample_stac_response):
    """Create a mock requests session that returns sample STAC data."""
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = sample_stac_response
    resp.raise_for_status.return_value = None
    session.get.return_value = resp
    session.headers = {}
    return session

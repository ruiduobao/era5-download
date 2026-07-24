"""Tests for ERA5 search functionality."""
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock


class TestGetVariableInfo:
    def test_valid_variable(self, era5_mod):
        info = era5_mod.get_variable_info("temperature_2m")
        assert info["asset_key"] == "air_temperature_at_2_metres"
        assert info["units"] == "K"

    def test_precipitation(self, era5_mod):
        info = era5_mod.get_variable_info("precipitation")
        assert info["asset_key"] == "precipitation_amount_1hour_Accumulation"
        assert info["units"] == "m"

    def test_wind_u_10m(self, era5_mod):
        info = era5_mod.get_variable_info("wind_u_10m")
        assert info["asset_key"] == "eastward_wind_at_10_metres"

    def test_invalid_variable_raises(self, era5_mod):
        with pytest.raises(ValueError, match="Unknown variable"):
            era5_mod.get_variable_info("not_a_real_var")

    def test_all_variables_have_required_keys(self, era5_mod):
        for name, info in era5_mod.ERA5_VARIABLES.items():
            assert "description" in info, f"{name} missing description"
            assert "units" in info, f"{name} missing units"
            assert "asset_key" in info, f"{name} missing asset_key"

    def test_variable_count(self, era5_mod):
        assert len(era5_mod.ERA5_VARIABLES) >= 9


class TestParseDate:
    def test_parse_year(self, era5_mod):
        dt = era5_mod._parse_date("2024")
        assert dt == datetime(2024, 1, 1)

    def test_parse_year_month(self, era5_mod):
        dt = era5_mod._parse_date("2024-03")
        assert dt == datetime(2024, 3, 1)

    def test_parse_full_date(self, era5_mod):
        dt = era5_mod._parse_date("2024-06-15")
        assert dt == datetime(2024, 6, 15)

    def test_parse_none(self, era5_mod):
        assert era5_mod._parse_date(None) is None

    def test_parse_empty(self, era5_mod):
        assert era5_mod._parse_date("") is None

    def test_parse_invalid_raises(self, era5_mod):
        with pytest.raises(ValueError, match="Invalid date format"):
            era5_mod._parse_date("not-a-date")


class TestParseItemDate:
    def test_from_datetime_property(self, era5_mod):
        dt = era5_mod._parse_item_date("some_id", "2024-01-15T12:00:00Z")
        assert dt == datetime(2024, 1, 15, 12, 0, 0)

    def test_from_id_full_date(self, era5_mod):
        dt = era5_mod._parse_item_date("2024-01-15", None)
        assert dt == datetime(2024, 1, 15)

    def test_from_id_year_month(self, era5_mod):
        dt = era5_mod._parse_item_date("2024-03", None)
        assert dt == datetime(2024, 3, 1)

    def test_from_id_year(self, era5_mod):
        dt = era5_mod._parse_item_date("2024", None)
        assert dt == datetime(2024, 1, 1)

    def test_prefers_datetime_property(self, era5_mod):
        dt = era5_mod._parse_item_date("2024-01-01", "2024-06-15T00:00:00Z")
        assert dt == datetime(2024, 6, 15, 0, 0, 0)

    def test_returns_none_for_unknown(self, era5_mod):
        dt = era5_mod._parse_item_date("unknown_format_xyz", None)
        assert dt is None


class TestSearchEra5:
    def test_search_returns_list(self, era5_mod, mock_session):
        with patch("era5_download.create_session", return_value=mock_session):
            results = era5_mod.search_era5("temperature_2m", "2024-01", "2024-03")
        assert isinstance(results, list)

    def test_search_filters_by_date(self, era5_mod, mock_session):
        with patch("era5_download.create_session", return_value=mock_session):
            results = era5_mod.search_era5("temperature_2m", "2024-01", "2024-02")
        dates = [r["datetime"] for r in results]
        for d in dates:
            assert "2024-01" in d or "2024-02" in d

    def test_search_result_structure(self, era5_mod, mock_session):
        with patch("era5_download.create_session", return_value=mock_session):
            results = era5_mod.search_era5("temperature_2m", "2024-01")
        assert len(results) > 0
        r = results[0]
        assert "id" in r
        assert "datetime" in r
        assert "variable" in r
        assert "asset_url" in r

    def test_search_variable_in_results(self, era5_mod, mock_session):
        with patch("era5_download.create_session", return_value=mock_session):
            results = era5_mod.search_era5("temperature_2m", "2024-01")
        for r in results:
            assert r["variable"] == "temperature_2m"

    def test_search_bad_variable_raises(self, era5_mod):
        with pytest.raises(ValueError, match="Unknown variable"):
            era5_mod.search_era5("fake_var", "2024-01")

    def test_search_single_month(self, era5_mod, mock_session):
        with patch("era5_download.create_session", return_value=mock_session):
            results = era5_mod.search_era5("temperature_2m", "2024-01")
        for r in results:
            assert "2024-01" in r["datetime"]

    def test_search_api_error_propagates(self, era5_mod):
        session = MagicMock()
        resp = MagicMock()
        resp.raise_for_status.side_effect = Exception("API Error")
        session.get.return_value = resp
        with patch("era5_download.create_session", return_value=session):
            with pytest.raises(Exception, match="API Error"):
                era5_mod.search_era5("temperature_2m", "2024-01")

    def test_search_empty_response(self, era5_mod):
        session = MagicMock()
        resp = MagicMock()
        resp.json.return_value = {"features": []}
        resp.raise_for_status.return_value = None
        session.get.return_value = resp
        with patch("era5_download.create_session", return_value=session):
            results = era5_mod.search_era5("temperature_2m", "2024-01")
        assert results == []

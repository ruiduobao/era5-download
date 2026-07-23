"""Tests for CLI argument parsing."""
import pytest


class TestBuildParser:
    def test_parser_creates_subcommands(self, era5_mod):
        parser = era5_mod.build_parser()
        args = parser.parse_args(["variables"])
        assert args.command == "variables"

    def test_parser_search_minimal(self, era5_mod):
        parser = era5_mod.build_parser()
        args = parser.parse_args(["search", "--variable", "temperature_2m", "--start-date", "2024-01"])
        assert args.command == "search"
        assert args.variable == "temperature_2m"
        assert args.start_date == "2024-01"
        assert args.end_date is None

    def test_parser_search_full(self, era5_mod):
        parser = era5_mod.build_parser()
        args = parser.parse_args([
            "search", "-v", "precipitation", "-s", "2024-01", "-e", "2024-06",
            "--limit", "5", "--json",
        ])
        assert args.variable == "precipitation"
        assert args.start_date == "2024-01"
        assert args.end_date == "2024-06"
        assert args.limit == 5
        assert args.output_json is True

    def test_parser_download_minimal(self, era5_mod):
        parser = era5_mod.build_parser()
        args = parser.parse_args(["download", "-v", "temperature_2m", "-s", "2024-01"])
        assert args.command == "download"
        assert args.output is None
        assert args.bbox is None
        assert args.skip_existing is False

    def test_parser_download_full(self, era5_mod):
        parser = era5_mod.build_parser()
        args = parser.parse_args([
            "download", "--variable", "wind_speed_10m", "--start-date", "2023-06",
            "--end-date", "2023-12", "--output", "wind.nc",
            "--bbox", "-10", "35", "5", "45", "--skip-existing", "--quiet",
        ])
        assert args.variable == "wind_speed_10m"
        assert args.output == "wind.nc"
        assert args.bbox == [-10.0, 35.0, 5.0, 45.0]
        assert args.skip_existing is True
        assert args.quiet is True

    def test_parser_no_command(self, era5_mod):
        parser = era5_mod.build_parser()
        args = parser.parse_args([])
        assert args.command is None

    def test_parser_search_requires_variable(self, era5_mod):
        parser = era5_mod.build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["search", "--start-date", "2024-01"])

    def test_parser_search_requires_start_date(self, era5_mod):
        parser = era5_mod.build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["search", "--variable", "temperature_2m"])


class TestMainCLI:
    def test_main_no_command(self, era5_mod):
        result = era5_mod.main([])
        assert result == 0

    def test_main_variables(self, era5_mod, capsys):
        result = era5_mod.main(["variables"])
        assert result == 0
        captured = capsys.readouterr()
        assert "temperature_2m" in captured.out
        assert "precipitation" in captured.out

    def test_main_version(self, era5_mod):
        with pytest.raises(SystemExit) as exc:
            era5_mod.main(["--version"])
        assert exc.value.code == 0

    def test_main_search_bad_variable(self, era5_mod, capsys):
        result = era5_mod.main([
            "search", "--variable", "nonexistent_var", "--start-date", "2024-01",
        ])
        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_main_search_success(self, era5_mod, mock_session, sample_stac_response, capsys):
        with patch("era5_download.create_session", return_value=mock_session):
            result = era5_mod.main([
                "search", "-v", "temperature_2m", "-s", "2024-01", "-e", "2024-02",
            ])
        assert result == 0
        captured = capsys.readouterr()
        assert "Found" in captured.out

    def test_main_search_json(self, era5_mod, mock_session, sample_stac_response, capsys):
        with patch("era5_download.create_session", return_value=mock_session):
            result = era5_mod.main([
                "search", "-v", "temperature_2m", "-s", "2024-01", "--json",
            ])
        assert result == 0
        captured = capsys.readouterr()
        assert "[" in captured.out


from unittest.mock import patch

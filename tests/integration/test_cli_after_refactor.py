"""CLI integration tests using Typer CliRunner."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from getit import __version__
from getit.cli import app

runner = CliRunner()


@pytest.mark.integration
class TestCLISupportedCommand:
    def test_supported_exits_zero(self):
        result = runner.invoke(app, ["supported"])

        assert result.exit_code == 0

    def test_supported_contains_gofile(self):
        result = runner.invoke(app, ["supported"])

        assert "GoFile" in result.stdout

    def test_supported_contains_pixeldrain(self):
        result = runner.invoke(app, ["supported"])

        assert "PixelDrain" in result.stdout

    def test_supported_contains_mediafire(self):
        result = runner.invoke(app, ["supported"])

        assert "MediaFire" in result.stdout

    def test_supported_contains_1fichier(self):
        result = runner.invoke(app, ["supported"])

        assert "1Fichier" in result.stdout

    def test_supported_contains_mega(self):
        result = runner.invoke(app, ["supported"])

        assert "Mega" in result.stdout

    def test_supported_shows_table_format(self):
        result = runner.invoke(app, ["supported"])

        assert "Host" in result.stdout
        assert "Domains" in result.stdout
        assert "Features" in result.stdout


@pytest.mark.integration
class TestCLIVersionFlag:
    def test_version_flag_exits_zero(self):
        result = runner.invoke(app, ["--version"])

        assert result.exit_code == 0

    def test_version_short_flag_exits_zero(self):
        result = runner.invoke(app, ["-V"])

        assert result.exit_code == 0

    def test_version_contains_version_string(self):
        result = runner.invoke(app, ["--version"])

        assert __version__ in result.stdout

    def test_version_contains_getit_name(self):
        result = runner.invoke(app, ["--version"])

        assert "getit" in result.stdout


@pytest.mark.integration
class TestCLIConfigCommand:
    def test_config_show_exits_zero(self):
        result = runner.invoke(app, ["config", "--show"])

        assert result.exit_code == 0

    def test_config_default_exits_zero(self):
        result = runner.invoke(app, ["config"])

        assert result.exit_code == 0

    def test_config_shows_settings(self):
        result = runner.invoke(app, ["config"])

        assert "Download Directory" in result.stdout
        assert "Max Concurrent Downloads" in result.stdout


@pytest.mark.integration
class TestCLIHelpOutput:
    def test_help_exits_zero(self):
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0

    def test_help_shows_available_commands(self):
        result = runner.invoke(app, ["--help"])

        assert "download" in result.stdout
        assert "info" in result.stdout
        assert "supported" in result.stdout
        assert "config" in result.stdout

    def test_download_help_exits_zero(self):
        result = runner.invoke(app, ["download", "--help"])

        assert result.exit_code == 0

    def test_download_help_shows_options(self):
        result = runner.invoke(app, ["download", "--help"])

        assert "--output" in result.stdout or "-o" in result.stdout
        assert "--concurrent" in result.stdout or "-c" in result.stdout
        assert "--password" in result.stdout or "-p" in result.stdout


@pytest.mark.integration
class TestCLIErrorHandling:
    def test_download_no_urls_fails(self):
        result = runner.invoke(app, ["download"])

        assert result.exit_code != 0

    def test_download_nonexistent_file_fails(self):
        result = runner.invoke(app, ["download", "-f", "/nonexistent/urls.txt"])

        assert result.exit_code != 0
        assert "not found" in result.stdout.lower() or result.exit_code == 1

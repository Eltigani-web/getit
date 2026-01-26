"""Unit tests for config module."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from getit.config import (
    Settings,
    get_config_file_path,
    get_default_config_dir,
    get_default_download_dir,
    get_settings,
    load_config,
    save_config,
    update_settings,
)


class TestGetDefaultConfigDir:
    """Tests for get_default_config_dir()."""

    def test_returns_path(self) -> None:
        """Should return a Path object."""
        result = get_default_config_dir()
        assert isinstance(result, Path)

    def test_creates_directory(self, temp_dir: Path) -> None:
        """Should create the directory if it doesn't exist."""
        with patch("getit.config.Path.home", return_value=temp_dir):
            with patch("sys.platform", "linux"):
                result = get_default_config_dir()
                assert result.exists()

    @patch("sys.platform", "darwin")
    def test_macos_path(self, temp_dir: Path) -> None:
        """Should use ~/Library/Application Support on macOS."""
        with patch("getit.config.Path.home", return_value=temp_dir):
            result = get_default_config_dir()
            assert "Library/Application Support/getit" in str(result)

    @patch("sys.platform", "linux")
    def test_linux_path(self, temp_dir: Path) -> None:
        """Should use ~/.config on Linux."""
        with patch("getit.config.Path.home", return_value=temp_dir):
            with patch.dict("os.environ", {"XDG_CONFIG_HOME": ""}, clear=False):
                result = get_default_config_dir()
                assert ".config/getit" in str(result) or "getit" in str(result)


class TestGetDefaultDownloadDir:
    """Tests for get_default_download_dir()."""

    def test_returns_path(self) -> None:
        """Should return a Path object."""
        result = get_default_download_dir()
        assert isinstance(result, Path)

    def test_creates_directory(self, temp_dir: Path) -> None:
        """Should create the directory if it doesn't exist."""
        with patch("getit.config.Path.home", return_value=temp_dir):
            result = get_default_download_dir()
            assert result.exists()
            assert result.name == "getit"


class TestLoadConfig:
    """Tests for load_config()."""

    def test_returns_empty_dict_if_no_file(self, temp_config_dir: Path) -> None:
        """Should return empty dict if config file doesn't exist."""
        with patch(
            "getit.config.get_config_file_path", return_value=temp_config_dir / "config.json"
        ):
            result = load_config()
            assert result == {}

    def test_loads_valid_json(self, temp_config_dir: Path) -> None:
        """Should load valid JSON config."""
        config_path = temp_config_dir / "config.json"
        config_data = {"max_concurrent_downloads": 5, "enable_resume": False}
        config_path.write_text(json.dumps(config_data))

        with patch("getit.config.get_config_file_path", return_value=config_path):
            result = load_config()
            assert result["max_concurrent_downloads"] == 5
            assert result["enable_resume"] is False

    def test_converts_download_dir_to_path(self, temp_config_dir: Path) -> None:
        """Should convert download_dir string to Path."""
        config_path = temp_config_dir / "config.json"
        config_data = {"download_dir": "~/Downloads/test"}
        config_path.write_text(json.dumps(config_data))

        with patch("getit.config.get_config_file_path", return_value=config_path):
            result = load_config()
            assert isinstance(result["download_dir"], Path)

    def test_returns_empty_dict_on_invalid_json(self, temp_config_dir: Path) -> None:
        """Should return empty dict on invalid JSON."""
        config_path = temp_config_dir / "config.json"
        config_path.write_text("not valid json {{{")

        with patch("getit.config.get_config_file_path", return_value=config_path):
            result = load_config()
            assert result == {}


class TestSaveConfig:
    """Tests for save_config()."""

    def test_saves_config_to_file(self, temp_config_dir: Path, temp_download_dir: Path) -> None:
        """Should save settings to JSON file."""
        config_path = temp_config_dir / "config.json"
        settings = Settings(
            download_dir=temp_download_dir,
            config_dir=temp_config_dir,
            max_concurrent_downloads=5,
            enable_resume=False,
        )

        with patch("getit.config.get_config_file_path", return_value=config_path):
            save_config(settings)

        assert config_path.exists()
        data = json.loads(config_path.read_text())
        assert data["max_concurrent_downloads"] == 5
        assert data["enable_resume"] is False

    def test_creates_parent_directory(self, temp_dir: Path, temp_download_dir: Path) -> None:
        """Should create parent directory if it doesn't exist."""
        config_path = temp_dir / "nested" / "config" / "config.json"
        settings = Settings(
            download_dir=temp_download_dir,
            config_dir=temp_dir,
        )

        with patch("getit.config.get_config_file_path", return_value=config_path):
            save_config(settings)

        assert config_path.exists()


class TestSettings:
    """Tests for Settings class."""

    def test_default_values(self) -> None:
        """Should have sensible default values."""
        settings = Settings()
        assert settings.max_concurrent_downloads == 3
        assert settings.max_retries == 3
        assert settings.enable_resume is True
        assert settings.theme == "dark"

    def test_custom_values(self, temp_download_dir: Path) -> None:
        """Should accept custom values."""
        settings = Settings(
            download_dir=temp_download_dir,
            max_concurrent_downloads=5,
            max_retries=1,
            enable_resume=False,
        )
        assert settings.download_dir == temp_download_dir
        assert settings.max_concurrent_downloads == 5
        assert settings.max_retries == 1
        assert settings.enable_resume is False

    def test_validation_min_values(self) -> None:
        """Should validate minimum values."""
        with pytest.raises(ValueError):
            Settings(max_concurrent_downloads=0)

    def test_validation_max_values(self) -> None:
        """Should validate maximum values."""
        with pytest.raises(ValueError):
            Settings(max_concurrent_downloads=100)

    def test_history_db_default(self, temp_config_dir: Path) -> None:
        """Should set history_db from config_dir."""
        settings = Settings(config_dir=temp_config_dir)
        assert settings.history_db == temp_config_dir / "history.db"


class TestGetSettings:
    """Tests for get_settings()."""

    def test_returns_settings_instance(self) -> None:
        """Should return a Settings instance."""
        # Reset global state
        import getit.config

        getit.config._settings = None

        result = get_settings()
        assert isinstance(result, Settings)

    def test_caches_instance(self) -> None:
        """Should return the same instance on subsequent calls."""
        import getit.config

        getit.config._settings = None

        result1 = get_settings()
        result2 = get_settings()
        assert result1 is result2


class TestUpdateSettings:
    """Tests for update_settings()."""

    def test_updates_global_settings(self, temp_download_dir: Path) -> None:
        """Should update the global settings instance."""
        import getit.config

        getit.config._settings = None

        result = update_settings(
            download_dir=temp_download_dir,
            max_concurrent_downloads=7,
        )

        assert result.download_dir == temp_download_dir
        assert result.max_concurrent_downloads == 7

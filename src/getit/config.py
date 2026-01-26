"""Configuration management using Pydantic Settings."""

import json
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_default_config_dir() -> Path:
    """Get the default configuration directory."""
    import os
    import sys

    if sys.platform == "darwin":
        config_dir = Path.home() / "Library" / "Application Support" / "getit"
    elif sys.platform == "win32":
        config_dir = Path(os.environ.get("APPDATA", Path.home())) / "getit"
    else:
        config_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "getit"

    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_default_download_dir() -> Path:
    """Get the default download directory."""
    download_dir = Path.home() / "Downloads" / "getit"
    download_dir.mkdir(parents=True, exist_ok=True)
    return download_dir


def get_config_file_path() -> Path:
    """Get the path to the JSON config file."""
    return get_default_config_dir() / "config.json"


def load_config() -> dict:
    """Load settings from JSON config file."""
    config_path = get_config_file_path()
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Convert path strings back to Path objects
                if "download_dir" in data and isinstance(data["download_dir"], str):
                    data["download_dir"] = Path(data["download_dir"]).expanduser()
                return data
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_prefix="GETIT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Download settings
    download_dir: Path = Field(default_factory=get_default_download_dir)
    max_concurrent_downloads: int = Field(default=3, ge=1, le=10)
    max_concurrent_chunks: int = Field(default=4, ge=1, le=16)
    chunk_size: int = Field(default=1024 * 1024, ge=1024)  # 1MB default
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_delay: float = Field(default=1.0, ge=0.0)
    timeout: float = Field(default=30.0, ge=5.0)
    speed_limit: Optional[int] = Field(default=None)  # bytes/sec, None = unlimited

    # Resume settings
    enable_resume: bool = Field(default=True)

    # API settings
    gofile_token: Optional[str] = Field(default=None)
    pixeldrain_api_key: Optional[str] = Field(default=None)
    mega_email: Optional[str] = Field(default=None)
    mega_password: Optional[str] = Field(default=None)

    # TUI settings
    show_speed: bool = Field(default=True)
    show_eta: bool = Field(default=True)
    theme: str = Field(default="dark")

    # Rate limiting
    requests_per_second: float = Field(default=10.0, ge=1.0)

    # Paths
    config_dir: Path = Field(default_factory=get_default_config_dir)
    history_db: Optional[Path] = Field(default=None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.history_db is None:
            self.history_db = self.config_dir / "history.db"


def save_config(settings: Settings) -> None:
    """Save user-facing settings to JSON config file."""
    config_path = get_config_file_path()
    config_data = {
        "download_dir": str(settings.download_dir),
        "max_concurrent_downloads": settings.max_concurrent_downloads,
        "speed_limit": settings.speed_limit,
        "enable_resume": settings.enable_resume,
        "max_retries": settings.max_retries,
        "show_speed": settings.show_speed,
        "show_eta": settings.show_eta,
        "theme": settings.theme,
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the global settings instance, loading from config file if available."""
    global _settings
    if _settings is None:
        saved_config = load_config()
        _settings = Settings(**saved_config)
    return _settings


def update_settings(**kwargs) -> Settings:
    """Update the global settings instance."""
    global _settings
    _settings = Settings(**kwargs)
    return _settings

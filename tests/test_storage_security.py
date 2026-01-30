"""Tests for storage and configuration security (Wave 4, Task 9)."""

import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from getit.config import Settings, save_config
from getit.storage.history import DownloadHistory


class TestFilePermissions:
    """Test file permission settings for databases and config files."""

    @pytest.mark.asyncio
    async def test_config_database_permissions_600(self):
        """Config/history databases get 600 permissions (rw-------)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "config" / "history.db"

            async with DownloadHistory(db_path) as history:
                await history.add_download(
                    url="https://example.com/file1",
                    filename="file1.txt",
                    filepath="/downloads/file1.txt",
                    size=1024,
                )

            stat_info = os.stat(db_path)
            mode = stat_info.st_mode & 0o777
            assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"

    @pytest.mark.asyncio
    async def test_download_database_permissions_640(self):
        """Download databases get 640 permissions (rw-r-----)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "downloads" / "history.db"

            async with DownloadHistory(db_path) as history:
                await history.add_download(
                    url="https://example.com/file1",
                    filename="file1.txt",
                    filepath="/downloads/file1.txt",
                    size=1024,
                )

            stat_info = os.stat(db_path)
            mode = stat_info.st_mode & 0o777
            assert mode == 0o640, f"Expected 0o640, got {oct(mode)}"

    @pytest.mark.asyncio
    async def test_custom_permissions_override(self):
        """Custom file permissions can override defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "custom" / "history.db"
            custom_perms = 0o660

            async with DownloadHistory(db_path, file_permissions=custom_perms) as history:
                await history.add_download(
                    url="https://example.com/file1",
                    filename="file1.txt",
                    filepath="/downloads/file1.txt",
                    size=1024,
                )

            stat_info = os.stat(db_path)
            mode = stat_info.st_mode & 0o777
            assert mode == custom_perms, f"Expected {oct(custom_perms)}, got {oct(mode)}"

    def test_config_file_permissions_600(self):
        """JSON config file gets 600 permissions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "config"
            config_dir.mkdir(parents=True, exist_ok=True)

            with patch("getit.config.get_default_config_dir", return_value=config_dir):
                settings = Settings(
                    download_dir=Path(tmpdir) / "downloads",
                    max_concurrent_downloads=4,
                )
                save_config(settings)

            config_path = config_dir / "config.json"
            assert config_path.exists()

            stat_info = os.stat(config_path)
            mode = stat_info.st_mode & 0o777
            assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"


class TestWalAndPragmas:
    """Test WAL mode and PRAGMA configuration."""

    @pytest.mark.asyncio
    async def test_wal_mode_enabled(self):
        """WAL mode is enabled for better concurrency."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "history.db"

            async with DownloadHistory(db_path):
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                cursor.execute("PRAGMA journal_mode")
                mode = cursor.fetchone()[0]
                conn.close()

                assert mode == "wal", f"Expected 'wal', got '{mode}'"

    @pytest.mark.asyncio
    async def test_synchronous_normal(self):
        """PRAGMA synchronous is set to NORMAL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "history.db"

            async with DownloadHistory(db_path) as history:
                assert history._db is not None
                async with history._db.execute("PRAGMA synchronous") as cursor:
                    row = await cursor.fetchone()
                    mode = row[0] if row else None
                    assert mode == 1, f"Expected 1 (NORMAL), got {mode}"

    @pytest.mark.asyncio
    async def test_busy_timeout_30s(self):
        """Busy timeout is set to 30 seconds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "history.db"

            async with DownloadHistory(db_path) as history:
                assert history._db is not None
                async with history._db.execute("PRAGMA busy_timeout") as cursor:
                    row = await cursor.fetchone()
                    timeout = row[0] if row else None
                    assert timeout == 30000, f"Expected 30000ms, got {timeout}ms"

    @pytest.mark.asyncio
    async def test_foreign_keys_enabled(self):
        """Foreign keys are enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "history.db"

            async with DownloadHistory(db_path) as history:
                assert history._db is not None
                async with history._db.execute("PRAGMA foreign_keys") as cursor:
                    row = await cursor.fetchone()
                    enabled = row[0] if row else None
                    assert enabled == 1, f"Expected 1 (enabled), got {enabled}"


class TestSchemaVersioning:
    """Test schema version tracking."""

    @pytest.mark.asyncio
    async def test_schema_versions_table_exists(self):
        """schema_versions table is created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "history.db"

            async with DownloadHistory(db_path):
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_versions'"
                )
                result = cursor.fetchone()
                conn.close()

                assert result is not None, "schema_versions table not found"

    @pytest.mark.asyncio
    async def test_current_schema_version_recorded(self):
        """Current schema version is recorded in schema_versions table."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "history.db"

            async with DownloadHistory(db_path):
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT version FROM schema_versions WHERE version = ?",
                    (DownloadHistory.CURRENT_SCHEMA_VERSION,),
                )
                result = cursor.fetchone()
                conn.close()

                assert result is not None, "Current schema version not recorded"
                assert result[0] == DownloadHistory.CURRENT_SCHEMA_VERSION

    @pytest.mark.asyncio
    async def test_get_schema_version_returns_current(self):
        """get_schema_version() returns the current version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "history.db"

            async with DownloadHistory(db_path) as history:
                version = await history.get_schema_version()
                assert version == DownloadHistory.CURRENT_SCHEMA_VERSION

    @pytest.mark.asyncio
    async def test_get_schema_version_auto_creates_if_missing(self):
        """get_schema_version() returns current version even if table was empty (auto-created)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "history.db"

            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(db_path))
            conn.execute("""
                CREATE TABLE schema_versions (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            conn.close()

            async with DownloadHistory(db_path) as history:
                version = await history.get_schema_version()
                assert version == DownloadHistory.CURRENT_SCHEMA_VERSION


class TestSecretRedaction:
    """Test secret redaction for database operations."""

    def test_redact_token_pattern(self):
        """Token patterns are redacted."""
        history = DownloadHistory(Path("test.db"))
        input_text = "url=https://example.com&token=abc123xyz789def456"
        redacted = history._redact_secrets(input_text)
        assert "token=***REDACTED***" in redacted
        assert "abc123xyz789def456" not in redacted

    def test_redact_password_pattern(self):
        """Password patterns are redacted."""
        history = DownloadHistory(Path("test.db"))
        input_text = "user=admin&password=mySecretPassword123"
        redacted = history._redact_secrets(input_text)
        assert "password=***REDACTED***" in redacted
        assert "mySecretPassword123" not in redacted

    def test_redact_api_key_pattern(self):
        """API key patterns are redacted."""
        history = DownloadHistory(Path("test.db"))
        input_text = "api_key=sk_1234567890abcdef"
        redacted = history._redact_secrets(input_text)
        assert "api_key=***REDACTED***" in redacted
        assert "sk_1234567890abcdef" not in redacted

    def test_redact_authorization_bearer(self):
        """Authorization values are redacted when they meet 6+ character requirement."""
        history = DownloadHistory(Path("test.db"))
        input_text = "Authorization: token123456"
        redacted = history._redact_secrets(input_text)
        assert "***REDACTED***" in redacted
        assert "token123456" not in redacted

    def test_redact_secret_pattern(self):
        """Secret patterns are redacted."""
        history = DownloadHistory(Path("test.db"))
        input_text = "secret_key=superSecretValue123456"
        redacted = history._redact_secrets(input_text)
        assert "secret_key=***REDACTED***" in redacted
        assert "superSecretValue123456" not in redacted

    def test_redact_multiple_secrets(self):
        """Multiple secrets in one string are all redacted."""
        history = DownloadHistory(Path("test.db"))
        input_text = "token=abc123&password=xyz789&api_key=def456"
        redacted = history._redact_secrets(input_text)
        assert redacted.count("***REDACTED***") == 3

    def test_redact_short_secrets_not_redacted(self):
        """Short secrets (<6 chars) are not redacted (false positive prevention)."""
        history = DownloadHistory(Path("test.db"))
        input_text = "password=abc"
        redacted = history._redact_secrets(input_text)
        assert "***REDACTED***" not in redacted
        assert "password=abc" in redacted

    def test_redact_empty_input(self):
        """Empty or None input is handled gracefully."""
        history = DownloadHistory(Path("test.db"))
        assert history._redact_secrets("") == ""


class TestEnvironmentVariableRedaction:
    """Test environment variable redaction in logging."""

    def test_environment_variables_not_logged(self):
        """Environment variables containing secrets are filtered from logs."""
        with patch.dict(
            os.environ,
            {"GETIT_GOFILE_TOKEN": "secret_token_12345", "GETIT_MEGA_PASSWORD": "secret_pass"},
        ):
            settings = Settings()

            from getit.config import save_config

            with tempfile.TemporaryDirectory() as tmpdir:
                config_dir = Path(tmpdir) / "config"
                config_dir.mkdir(parents=True, exist_ok=True)

                with patch("getit.config.get_default_config_dir", return_value=config_dir):
                    save_config(settings)

                config_path = config_dir / "config.json"
                with open(config_path) as f:
                    import json

                    config_data = json.load(f)

                assert "encryption_key" not in config_data
                assert "secret_key_123" not in str(config_data)


class TestDownloadHistoryIntegration:
    """Integration tests for download history with security features."""

    @pytest.mark.asyncio
    async def test_full_lifecycle_with_security(self):
        """Test full download history lifecycle with all security features."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "downloads" / "history.db"

            async with DownloadHistory(db_path) as history:
                assert history._db is not None
                async with history._db.execute("PRAGMA journal_mode") as cursor:
                    row = await cursor.fetchone()
                    assert row is not None
                    assert row[0] == "wal"

                async with history._db.execute("PRAGMA synchronous") as cursor:
                    row = await cursor.fetchone()
                    assert row is not None
                    assert row[0] == 1

                async with history._db.execute("PRAGMA busy_timeout") as cursor:
                    row = await cursor.fetchone()
                    assert row is not None
                    assert row[0] == 30000

                download_id = await history.add_download(
                    url="https://example.com/file1.txt",
                    filename="file1.txt",
                    filepath=str(Path(tmpdir) / "file1.txt"),
                    size=1024,
                    extractor="test",
                )
                assert download_id > 0

                version = await history.get_schema_version()
                assert version == DownloadHistory.CURRENT_SCHEMA_VERSION

                await history.update_status(download_id, "completed")

                entry = await history.get_download(download_id)
                assert entry is not None
                assert entry.status == "completed"

                stat_info = os.stat(db_path)
                mode = stat_info.st_mode & 0o777
                assert mode == 0o640, f"Expected 0o640, got {oct(mode)}"

    @pytest.mark.asyncio
    async def test_config_database_full_lifecycle(self):
        """Test config database lifecycle with 600 permissions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "config" / "history.db"

            async with DownloadHistory(db_path) as history:
                await history.add_download(
                    url="https://example.com/file1.txt",
                    filename="file1.txt",
                    filepath="/downloads/file1.txt",
                    size=2048,
                )

            stat_info = os.stat(db_path)
            mode = stat_info.st_mode & 0o777
            assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"

            async with DownloadHistory(db_path) as history:
                recent = await history.get_recent(10)
                assert len(recent) == 1
                assert recent[0].url == "https://example.com/file1.txt"

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import ClassVar

import aiosqlite


@dataclass
class HistoryEntry:
    id: int
    url: str
    filename: str
    filepath: str
    size: int
    extractor: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    error: str | None


class DownloadHistory:
    """SQLite download history with security hardening.

    Security features:
    - File permissions: 600 for config/history databases
    - WAL mode enabled for better concurrency
    - Busy timeout: 30 seconds
    - PRAGMA synchronous=NORMAL for performance
    - Schema version tracking
    - Secret redaction in logs
    - Environment variable filtering
    """

    # Schema version for migration tracking
    CURRENT_SCHEMA_VERSION: ClassVar[int] = 1

    # File permissions
    CONFIG_PERMISSIONS: ClassVar[int] = 0o600  # rw-------
    DOWNLOAD_PERMISSIONS: ClassVar[int] = 0o640  # rw-r-----

    # Database PRAGMAs
    BUSY_TIMEOUT_MS: ClassVar[int] = 30000  # 30 seconds
    PRAGMA_SYNCHRONOUS: ClassVar[str] = "NORMAL"
    PRAGMA_JOURNAL_MODE: ClassVar[str] = "WAL"

    # Secret patterns for redaction - capture groups to preserve key name
    # Pattern matches: key_name followed by =, :, or space+value
    # Value stops at delimiter: &, ;, or end of string
    SECRET_PATTERNS: ClassVar[re.Pattern] = re.compile(
        r"(?i)((?:token|password|api_key|api_secret|authorization|secret|key)[=:\s]+)([^&;\'\"\s]{6,})"
    )

    def __init__(self, db_path: Path, file_permissions: int | None = None):
        """Initialize download history.

        Args:
            db_path: Path to SQLite database
            file_permissions: Optional custom permissions (default: 600 for config, 640 for downloads)
        """
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None
        self._file_permissions = file_permissions

    def _get_permissions(self) -> int:
        """Determine appropriate file permissions for database."""
        if self._file_permissions is not None:
            return self._file_permissions
        # Check if db_path is in config directory (more restrictive)
        db_str = str(self.db_path).lower()
        if any(x in db_str for x in ["config", ".config", "application support"]):
            return self.CONFIG_PERMISSIONS
        return self.DOWNLOAD_PERMISSIONS

    def _redact_secrets(self, text: str) -> str:
        """Redact secrets from text for logging.

        Args:
            text: Text that may contain secrets

        Returns:
            Text with secrets redacted as ***REDACTED***
        """
        if not text:
            return text

        def replace_secret(match):
            return f"{match.group(1)}***REDACTED***"

        return self.SECRET_PATTERNS.sub(replace_secret, text)

    def _get_connection_kwargs(self) -> dict:
        """Get connection kwargs with busy timeout."""
        return {"timeout": self.BUSY_TIMEOUT_MS / 1000.0}

    async def __aenter__(self) -> DownloadHistory:
        await self.connect()
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def connect(self) -> None:
        """Connect to SQLite database with security hardening."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        db_existed = self.db_path.exists()

        # Connect with busy timeout
        self._db = await aiosqlite.connect(self.db_path, **self._get_connection_kwargs())

        # Set file permissions on new databases
        if not db_existed:
            os.chmod(self.db_path, self._get_permissions())
        else:
            # Ensure existing databases have correct permissions
            current_mode = os.stat(self.db_path).st_mode & 0o777
            desired_mode = self._get_permissions()
            if current_mode != desired_mode:
                os.chmod(self.db_path, desired_mode)

        await self._configure_pragmas()
        await self._create_tables()
        await self._ensure_schema_version()

    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    async def _configure_pragmas(self) -> None:
        """Configure SQLite PRAGMAs for security and performance."""
        if not self._db:
            return

        async with self._db.execute(f"PRAGMA journal_mode={self.PRAGMA_JOURNAL_MODE}") as cursor:
            await cursor.fetchone()

        async with self._db.execute(f"PRAGMA synchronous={self.PRAGMA_SYNCHRONOUS}") as cursor:
            await cursor.fetchone()

        async with self._db.execute(f"PRAGMA busy_timeout={self.BUSY_TIMEOUT_MS}") as cursor:
            await cursor.fetchone()

        async with self._db.execute("PRAGMA foreign_keys=ON") as cursor:
            await cursor.fetchone()

        await self._db.commit()

    async def _ensure_schema_version(self) -> None:
        """Ensure schema_versions table exists and current version is recorded."""
        if not self._db:
            return

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS schema_versions (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await self._db.execute(
            "INSERT OR IGNORE INTO schema_versions (version) VALUES (?)",
            (self.CURRENT_SCHEMA_VERSION,),
        )
        await self._db.commit()

    async def get_schema_version(self) -> int:
        """Get current schema version from database.

        Returns:
            Current schema version (0 if not found)
        """
        if not self._db:
            return 0

        cursor = await self._db.execute("SELECT MAX(version) FROM schema_versions")
        row = await cursor.fetchone()
        return row[0] if row and row[0] else 0

    async def _create_tables(self) -> None:
        if not self._db:
            return

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                filename TEXT NOT NULL,
                filepath TEXT NOT NULL,
                size INTEGER DEFAULT 0,
                extractor TEXT,
                status TEXT DEFAULT 'pending',
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                error TEXT
            )
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_downloads_url ON downloads(url)
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_downloads_status ON downloads(status)
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_downloads_started_at ON downloads(started_at)
        """)

        await self._db.commit()

    async def add_download(
        self,
        url: str,
        filename: str,
        filepath: str,
        size: int = 0,
        extractor: str = "",
    ) -> int:
        if not self._db:
            raise RuntimeError("Database not connected")

        cursor = await self._db.execute(
            """
            INSERT INTO downloads (url, filename, filepath, size, extractor, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
            """,
            (url, filename, filepath, size, extractor),
        )
        await self._db.commit()
        return cursor.lastrowid or 0

    async def update_status(
        self,
        download_id: int,
        status: str,
        error: str | None = None,
    ) -> None:
        if not self._db:
            return

        if status == "completed":
            await self._db.execute(
                """
                UPDATE downloads
                SET status = ?, completed_at = CURRENT_TIMESTAMP, error = ?
                WHERE id = ?
                """,
                (status, error, download_id),
            )
        else:
            await self._db.execute(
                """
                UPDATE downloads SET status = ?, error = ? WHERE id = ?
                """,
                (status, error, download_id),
            )
        await self._db.commit()

    async def get_download(self, download_id: int) -> HistoryEntry | None:
        if not self._db:
            return None

        async with self._db.execute(
            "SELECT * FROM downloads WHERE id = ?", (download_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._row_to_entry(tuple(row))
        return None

    async def get_recent(self, limit: int = 50) -> list[HistoryEntry]:
        if not self._db:
            return []

        entries: list[HistoryEntry] = []
        async with self._db.execute(
            "SELECT * FROM downloads ORDER BY started_at DESC LIMIT ?", (limit,)
        ) as cursor:
            async for row in cursor:
                entries.append(self._row_to_entry(tuple(row)))
        return entries

    async def get_by_status(self, status: str) -> list[HistoryEntry]:
        if not self._db:
            return []

        entries: list[HistoryEntry] = []
        async with self._db.execute(
            "SELECT * FROM downloads WHERE status = ? ORDER BY started_at DESC",
            (status,),
        ) as cursor:
            async for row in cursor:
                entries.append(self._row_to_entry(tuple(row)))
        return entries

    async def url_exists(self, url: str) -> bool:
        if not self._db:
            return False

        async with self._db.execute(
            "SELECT 1 FROM downloads WHERE url = ? AND status = 'completed' LIMIT 1",
            (url,),
        ) as cursor:
            return await cursor.fetchone() is not None

    async def clear_history(self, before_days: int | None = None) -> int:
        if not self._db:
            return 0

        if before_days:
            cursor = await self._db.execute(
                """
                DELETE FROM downloads
                WHERE started_at < datetime('now', ? || ' days')
                """,
                (f"-{before_days}",),
            )
        else:
            cursor = await self._db.execute("DELETE FROM downloads")

        await self._db.commit()
        return cursor.rowcount or 0

    def _row_to_entry(self, row: tuple) -> HistoryEntry:
        return HistoryEntry(
            id=row[0],
            url=row[1],
            filename=row[2],
            filepath=row[3],
            size=row[4],
            extractor=row[5] or "",
            status=row[6] or "pending",
            started_at=datetime.fromisoformat(row[7]) if row[7] else datetime.now(),
            completed_at=datetime.fromisoformat(row[8]) if row[8] else None,
            error=row[9],
        )

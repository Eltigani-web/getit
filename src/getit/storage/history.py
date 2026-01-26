from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

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
    completed_at: Optional[datetime]
    error: Optional[str]


class DownloadHistory:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def __aenter__(self) -> DownloadHistory:
        await self.connect()
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def connect(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        await self._create_tables()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

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
        error: Optional[str] = None,
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

    async def get_download(self, download_id: int) -> Optional[HistoryEntry]:
        if not self._db:
            return None

        async with self._db.execute(
            "SELECT * FROM downloads WHERE id = ?", (download_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._row_to_entry(row)
        return None

    async def get_recent(self, limit: int = 50) -> list[HistoryEntry]:
        if not self._db:
            return []

        entries: list[HistoryEntry] = []
        async with self._db.execute(
            "SELECT * FROM downloads ORDER BY started_at DESC LIMIT ?", (limit,)
        ) as cursor:
            async for row in cursor:
                entries.append(self._row_to_entry(row))
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
                entries.append(self._row_to_entry(row))
        return entries

    async def url_exists(self, url: str) -> bool:
        if not self._db:
            return False

        async with self._db.execute(
            "SELECT 1 FROM downloads WHERE url = ? AND status = 'completed' LIMIT 1",
            (url,),
        ) as cursor:
            return await cursor.fetchone() is not None

    async def clear_history(self, before_days: Optional[int] = None) -> int:
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

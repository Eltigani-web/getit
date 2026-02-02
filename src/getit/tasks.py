"""Task registry with SQLite persistence for managing download tasks."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

import aiosqlite

from getit.config import get_default_config_dir

_UNSET = object()


class TaskStatus(Enum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskInfo:
    task_id: str
    url: str
    output_dir: Path
    status: TaskStatus
    progress: dict[str, float] = field(default_factory=dict)
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


class TaskRegistry:
    BUSY_TIMEOUT_MS: int = 30000
    PRAGMA_SYNCHRONOUS: str = "NORMAL"
    PRAGMA_JOURNAL_MODE: str = "WAL"
    CONFIG_PERMISSIONS: int = 0o600

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or (get_default_config_dir() / "tasks.db")
        self._db: aiosqlite.Connection | None = None

    async def __aenter__(self) -> TaskRegistry:
        await self.connect()
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def connect(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        db_existed = self.db_path.exists()

        self._db = await aiosqlite.connect(self.db_path, timeout=self.BUSY_TIMEOUT_MS / 1000.0)

        if not db_existed:
            os.chmod(self.db_path, self.CONFIG_PERMISSIONS)
        else:
            current_mode = os.stat(self.db_path).st_mode & 0o777
            if current_mode != self.CONFIG_PERMISSIONS:
                os.chmod(self.db_path, self.CONFIG_PERMISSIONS)

        await self._configure_pragmas()
        await self._create_tables()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def _configure_pragmas(self) -> None:
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

    async def _create_tables(self) -> None:
        if not self._db:
            return

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                output_dir TEXT NOT NULL,
                status TEXT NOT NULL,
                progress TEXT,
                error TEXT,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at)
        """)

        await self._db.commit()

    async def create_task(self, url: str, output_dir: Path) -> str:
        if not self._db:
            raise RuntimeError("Database not connected")

        task_id = str(uuid.uuid4())
        now = datetime.now()

        await self._db.execute(
            """
            INSERT INTO tasks (task_id, url, output_dir, status, progress, error, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                url,
                str(output_dir),
                TaskStatus.PENDING.value,
                json.dumps({}),
                None,
                now.isoformat(),
                now.isoformat(),
            ),
        )
        await self._db.commit()
        return task_id

    async def get_task(self, task_id: str) -> TaskInfo | None:
        if not self._db:
            return None

        async with self._db.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._row_to_task(tuple(row))
        return None

    async def update_task(
        self,
        task_id: str,
        status: TaskStatus | None = None,
        progress: dict[str, float] | None = None,
        error: str | None | object = _UNSET,
    ) -> None:
        if not self._db:
            return

        updates = []
        values = []

        if status is not None:
            updates.append("status = ?")
            values.append(status.value)

        if progress is not None:
            updates.append("progress = ?")
            values.append(json.dumps(progress))

        if error is not _UNSET:
            updates.append("error = ?")
            values.append(error)

        updates.append("updated_at = ?")
        values.append(datetime.now().isoformat())

        values.append(task_id)

        await self._db.execute(
            f"UPDATE tasks SET {', '.join(updates)} WHERE task_id = ?",
            tuple(values),
        )
        await self._db.commit()

    async def list_active(self) -> list[TaskInfo]:
        if not self._db:
            return []

        tasks: list[TaskInfo] = []
        async with self._db.execute(
            """
            SELECT * FROM tasks
            WHERE status NOT IN (?, ?, ?)
            ORDER BY created_at ASC
            """,
            (
                TaskStatus.COMPLETED.value,
                TaskStatus.FAILED.value,
                TaskStatus.CANCELLED.value,
            ),
        ) as cursor:
            async for row in cursor:
                tasks.append(self._row_to_task(tuple(row)))
        return tasks

    async def delete_task(self, task_id: str) -> None:
        if not self._db:
            return

        await self._db.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
        await self._db.commit()

    def _row_to_task(self, row: tuple) -> TaskInfo:
        progress_data = row[4]
        progress: dict[str, float] = {}
        if progress_data:
            progress = json.loads(progress_data)
        return TaskInfo(
            task_id=row[0],
            url=row[1],
            output_dir=Path(row[2]),
            status=TaskStatus(row[3]),
            progress=progress,
            error=row[5],
            created_at=datetime.fromisoformat(row[6]),
            updated_at=datetime.fromisoformat(row[7]),
        )

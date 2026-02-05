"""Unit tests for TaskRegistry."""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncGenerator, Generator
from datetime import datetime
from pathlib import Path

import pytest

from getit.tasks import TaskInfo, TaskRegistry, TaskStatus


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_status_values_exist(self) -> None:
        """Should have all required status values."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.EXTRACTING.value == "extracting"
        assert TaskStatus.DOWNLOADING.value == "downloading"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"


class TestTaskInfo:
    """Tests for TaskInfo dataclass."""

    def test_task_info_creation(self) -> None:
        """Should create TaskInfo with all fields."""
        task_id = "test-uuid-123"
        url = "https://example.com/file"
        output_dir = Path("/tmp/downloads")
        status = TaskStatus.PENDING
        created_at = datetime.now()
        updated_at = datetime.now()

        task = TaskInfo(
            task_id=task_id,
            url=url,
            output_dir=output_dir,
            status=status,
            progress={},
            error=None,
            created_at=created_at,
            updated_at=updated_at,
        )

        assert task.task_id == task_id
        assert task.url == url
        assert task.output_dir == output_dir
        assert task.status == status
        assert task.progress == {}
        assert task.error is None
        assert task.created_at == created_at
        assert task.updated_at == updated_at

    def test_task_info_with_error(self) -> None:
        """Should store error message."""
        task = TaskInfo(
            task_id="test",
            url="https://example.com",
            output_dir=Path("/tmp"),
            status=TaskStatus.FAILED,
            progress={"percentage": 50.0},
            error="Download failed",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert task.error == "Download failed"

    def test_task_info_with_progress(self) -> None:
        """Should store progress value."""
        task = TaskInfo(
            task_id="test",
            url="https://example.com",
            output_dir=Path("/tmp"),
            status=TaskStatus.DOWNLOADING,
            progress={"percentage": 75.5},
            error=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert task.progress == {"percentage": 75.5}


@pytest.mark.asyncio
class TestTaskRegistry:
    """Tests for TaskRegistry class."""

    @pytest.fixture
    def temp_db_path(self) -> Generator[Path, None, None]:
        """Provide a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "tasks.db"

    @pytest.fixture
    async def registry(self, temp_db_path: Path) -> AsyncGenerator[TaskRegistry, None]:
        """Provide a connected TaskRegistry instance."""
        reg = TaskRegistry(temp_db_path)
        await reg.connect()
        yield reg
        await reg.close()

    async def test_connect_creates_database(self, temp_db_path: Path) -> None:
        """Should create database file on connect."""
        assert not temp_db_path.exists()
        reg = TaskRegistry(temp_db_path)
        await reg.connect()
        assert temp_db_path.exists()
        await reg.close()

    async def test_connect_sets_permissions(self, temp_db_path: Path) -> None:
        """Should set restrictive permissions on database file."""
        import sys

        if sys.platform.startswith("win"):
            pytest.skip("Windows does not support POSIX file permissions")
        reg = TaskRegistry(temp_db_path)
        await reg.connect()
        await reg.close()

        mode = os.stat(temp_db_path).st_mode & 0o777
        assert mode == 0o600

    async def test_create_task_generates_uuid(self, registry: TaskRegistry) -> None:
        """Should generate UUID4 task_id automatically."""
        task_id = await registry.create_task(
            url="https://example.com/file",
            output_dir=Path("/tmp/downloads"),
        )
        # UUID4 format: 8-4-4-4-12 hex characters
        assert isinstance(task_id, str)
        assert len(task_id) == 36
        assert task_id.count("-") == 4

    async def test_create_task_stores_in_database(self, registry: TaskRegistry) -> None:
        """Should persist task to database."""
        url = "https://example.com/file"
        output_dir = Path("/tmp/downloads")

        task_id = await registry.create_task(url=url, output_dir=output_dir)
        task = await registry.get_task(task_id)

        assert task is not None
        assert task.task_id == task_id
        assert task.url == url
        assert task.output_dir == output_dir
        assert task.status == TaskStatus.PENDING
        assert task.progress == {}
        assert task.error is None

    async def test_create_task_sets_timestamps(self, registry: TaskRegistry) -> None:
        """Should set created_at and updated_at on creation."""
        before = datetime.now()
        task_id = await registry.create_task(
            url="https://example.com",
            output_dir=Path("/tmp"),
        )
        after = datetime.now()

        task = await registry.get_task(task_id)
        assert task is not None
        assert before <= task.created_at <= after
        assert before <= task.updated_at <= after
        assert task.created_at == task.updated_at

    async def test_get_task_returns_none_for_nonexistent(self, registry: TaskRegistry) -> None:
        """Should return None for nonexistent task_id."""
        task = await registry.get_task("nonexistent-uuid")
        assert task is None

    async def test_update_task_changes_status(self, registry: TaskRegistry) -> None:
        """Should update task status."""
        task_id = await registry.create_task(
            url="https://example.com",
            output_dir=Path("/tmp"),
        )

        await registry.update_task(task_id, status=TaskStatus.DOWNLOADING)
        task = await registry.get_task(task_id)

        assert task is not None
        assert task.status == TaskStatus.DOWNLOADING

    async def test_update_task_changes_progress(self, registry: TaskRegistry) -> None:
        """Should update task progress."""
        task_id = await registry.create_task(
            url="https://example.com",
            output_dir=Path("/tmp"),
        )

        await registry.update_task(task_id, progress={"percentage": 45.5})
        task = await registry.get_task(task_id)

        assert task is not None
        assert task.progress == {"percentage": 45.5}

    async def test_update_task_sets_error(self, registry: TaskRegistry) -> None:
        """Should update task error message."""
        task_id = await registry.create_task(
            url="https://example.com",
            output_dir=Path("/tmp"),
        )

        error_msg = "Network timeout"
        await registry.update_task(task_id, status=TaskStatus.FAILED, error=error_msg)
        task = await registry.get_task(task_id)

        assert task is not None
        assert task.status == TaskStatus.FAILED
        assert task.error == error_msg

    async def test_update_task_updates_timestamp(self, registry: TaskRegistry) -> None:
        """Should update updated_at timestamp."""
        task_id = await registry.create_task(
            url="https://example.com",
            output_dir=Path("/tmp"),
        )
        original_task = await registry.get_task(task_id)
        assert original_task is not None

        # Small delay to ensure timestamp difference
        import asyncio

        await asyncio.sleep(0.01)

        await registry.update_task(task_id, progress={"percentage": 50.0})
        updated_task = await registry.get_task(task_id)

        assert updated_task is not None
        assert updated_task.updated_at > original_task.updated_at

    async def test_list_active_excludes_completed(self, registry: TaskRegistry) -> None:
        """Should exclude COMPLETED tasks from active list."""
        task1_id = await registry.create_task(url="https://example.com/1", output_dir=Path("/tmp"))
        task2_id = await registry.create_task(url="https://example.com/2", output_dir=Path("/tmp"))

        await registry.update_task(task1_id, status=TaskStatus.COMPLETED)

        active = await registry.list_active()
        assert len(active) == 1
        assert active[0].task_id == task2_id

    async def test_list_active_excludes_failed(self, registry: TaskRegistry) -> None:
        """Should exclude FAILED tasks from active list."""
        task1_id = await registry.create_task(url="https://example.com/1", output_dir=Path("/tmp"))
        task2_id = await registry.create_task(url="https://example.com/2", output_dir=Path("/tmp"))

        await registry.update_task(task1_id, status=TaskStatus.FAILED)

        active = await registry.list_active()
        assert len(active) == 1
        assert active[0].task_id == task2_id

    async def test_list_active_excludes_cancelled(self, registry: TaskRegistry) -> None:
        """Should exclude CANCELLED tasks from active list."""
        task1_id = await registry.create_task(url="https://example.com/1", output_dir=Path("/tmp"))
        task2_id = await registry.create_task(url="https://example.com/2", output_dir=Path("/tmp"))

        await registry.update_task(task1_id, status=TaskStatus.CANCELLED)

        active = await registry.list_active()
        assert len(active) == 1
        assert active[0].task_id == task2_id

    async def test_list_active_includes_pending(self, registry: TaskRegistry) -> None:
        """Should include PENDING tasks in active list."""
        task_id = await registry.create_task(url="https://example.com", output_dir=Path("/tmp"))

        active = await registry.list_active()
        assert len(active) == 1
        assert active[0].task_id == task_id
        assert active[0].status == TaskStatus.PENDING

    async def test_list_active_includes_extracting(self, registry: TaskRegistry) -> None:
        """Should include EXTRACTING tasks in active list."""
        task_id = await registry.create_task(url="https://example.com", output_dir=Path("/tmp"))
        await registry.update_task(task_id, status=TaskStatus.EXTRACTING)

        active = await registry.list_active()
        assert len(active) == 1
        assert active[0].status == TaskStatus.EXTRACTING

    async def test_list_active_includes_downloading(self, registry: TaskRegistry) -> None:
        """Should include DOWNLOADING tasks in active list."""
        task_id = await registry.create_task(url="https://example.com", output_dir=Path("/tmp"))
        await registry.update_task(task_id, status=TaskStatus.DOWNLOADING)

        active = await registry.list_active()
        assert len(active) == 1
        assert active[0].status == TaskStatus.DOWNLOADING

    async def test_list_active_returns_empty_when_no_tasks(self, registry: TaskRegistry) -> None:
        """Should return empty list when no tasks exist."""
        active = await registry.list_active()
        assert active == []

    async def test_delete_task_removes_from_database(self, registry: TaskRegistry) -> None:
        """Should remove task from database."""
        task_id = await registry.create_task(url="https://example.com", output_dir=Path("/tmp"))

        await registry.delete_task(task_id)
        task = await registry.get_task(task_id)

        assert task is None

    async def test_delete_task_nonexistent_does_not_error(self, registry: TaskRegistry) -> None:
        """Should not raise error when deleting nonexistent task."""
        await registry.delete_task("nonexistent-uuid")  # Should not raise

    async def test_delete_task_multiple_preserves_others(self, registry: TaskRegistry) -> None:
        """Should only delete specified task, not others."""
        task1_id = await registry.create_task(url="https://example.com/1", output_dir=Path("/tmp"))
        task2_id = await registry.create_task(url="https://example.com/2", output_dir=Path("/tmp"))

        await registry.delete_task(task1_id)

        task1 = await registry.get_task(task1_id)
        task2 = await registry.get_task(task2_id)

        assert task1 is None
        assert task2 is not None

    async def test_context_manager_async_with(self, temp_db_path: Path) -> None:
        """Should work as async context manager."""
        async with TaskRegistry(temp_db_path) as reg:
            task_id = await reg.create_task(url="https://example.com", output_dir=Path("/tmp"))
            task = await reg.get_task(task_id)
            assert task is not None

    async def test_persistence_across_connections(self, temp_db_path: Path) -> None:
        """Should persist data across connection cycles."""
        # Create task in first connection
        async with TaskRegistry(temp_db_path) as reg1:
            task_id = await reg1.create_task(url="https://example.com", output_dir=Path("/tmp"))

        # Verify task exists in second connection
        async with TaskRegistry(temp_db_path) as reg2:
            task = await reg2.get_task(task_id)
            assert task is not None
            assert task.url == "https://example.com"

    async def test_progress_persists_as_float(self, registry: TaskRegistry) -> None:
        """Should store and retrieve progress as dict."""
        task_id = await registry.create_task(url="https://example.com", output_dir=Path("/tmp"))

        await registry.update_task(task_id, progress={"percentage": 33.333})
        task = await registry.get_task(task_id)

        assert task is not None
        assert abs(task.progress["percentage"] - 33.333) < 0.001

    async def test_output_dir_persists_as_path(self, registry: TaskRegistry) -> None:
        """Should store and retrieve output_dir as Path."""
        output_dir = Path("/tmp/downloads/subdir")
        task_id = await registry.create_task(url="https://example.com", output_dir=output_dir)

        task = await registry.get_task(task_id)
        assert task is not None
        assert task.output_dir == output_dir
        assert isinstance(task.output_dir, Path)

    async def test_list_active_ordered_by_created_at(self, registry: TaskRegistry) -> None:
        """Should return active tasks ordered by creation time."""
        import asyncio

        task1_id = await registry.create_task(url="https://example.com/1", output_dir=Path("/tmp"))
        await asyncio.sleep(0.01)
        task2_id = await registry.create_task(url="https://example.com/2", output_dir=Path("/tmp"))
        await asyncio.sleep(0.01)
        task3_id = await registry.create_task(url="https://example.com/3", output_dir=Path("/tmp"))

        active = await registry.list_active()
        assert len(active) == 3
        # Should be ordered oldest to newest
        assert active[0].task_id == task1_id
        assert active[1].task_id == task2_id
        assert active[2].task_id == task3_id

    async def test_error_can_be_cleared(self, registry: TaskRegistry) -> None:
        """Should allow clearing error by setting to None."""
        task_id = await registry.create_task(url="https://example.com", output_dir=Path("/tmp"))

        await registry.update_task(task_id, error="Some error")
        task = await registry.get_task(task_id)
        assert task is not None
        assert task.error == "Some error"

        await registry.update_task(task_id, error=None)
        task = await registry.get_task(task_id)
        assert task is not None
        assert task.error is None

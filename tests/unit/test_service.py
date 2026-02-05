"""Unit tests for DownloadService facade."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from getit.config import Settings
from getit.core.downloader import DownloadStatus, DownloadTask
from getit.core.manager import DownloadResult
from getit.events import DOWNLOAD_COMPLETE, DOWNLOAD_ERROR, DOWNLOAD_PROGRESS, EventBus
from getit.extractors.base import FileInfo
from getit.registry import ExtractorRegistry
from getit.service import DownloadService
from getit.tasks import TaskRegistry, TaskStatus


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def registry():
    return ExtractorRegistry()


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
async def task_registry(temp_dir):
    db_path = temp_dir / "test_tasks.db"
    reg = TaskRegistry(db_path=db_path)
    await reg.connect()
    yield reg
    await reg.close()


@pytest.fixture
def settings(temp_dir):
    return Settings(download_dir=temp_dir)


@pytest.fixture
async def service(registry, event_bus, task_registry, settings):
    svc = DownloadService(
        registry=registry, event_bus=event_bus, task_registry=task_registry, settings=settings
    )
    await svc.start()
    yield svc
    await svc.close()


class TestDownloadServiceInit:
    """Tests for DownloadService initialization."""

    def test_init_with_required_params(self, registry, event_bus, task_registry):
        """Should initialize with required parameters."""
        svc = DownloadService(registry=registry, event_bus=event_bus, task_registry=task_registry)
        assert svc._registry == registry
        assert svc._event_bus == event_bus
        assert svc._task_registry == task_registry

    def test_init_with_settings(self, registry, event_bus, task_registry, settings):
        """Should accept optional settings."""
        svc = DownloadService(
            registry=registry,
            event_bus=event_bus,
            task_registry=task_registry,
            settings=settings,
        )
        assert svc._settings == settings


class TestDownloadServiceDownload:
    """Tests for DownloadService.download()."""

    @pytest.mark.asyncio
    async def test_download_creates_task(self, service, event_bus, task_registry, temp_dir):
        """Should create task before extraction."""
        url = "https://example.com/file"
        output_dir = temp_dir / "downloads"

        with patch.object(
            service._manager, "download_url", new_callable=AsyncMock
        ) as mock_download:
            mock_download.return_value = [
                DownloadResult.succeeded(
                    DownloadTask(
                        file_info=FileInfo(url=url, filename="test.txt"),
                        output_path=output_dir / "test.txt",
                    )
                )
            ]

            task_id = await service.download(url, output_dir)

            assert task_id is not None
            task = await task_registry.get_task(task_id)
            assert task is not None
            assert task.url == url

    @pytest.mark.asyncio
    async def test_download_updates_status_extracting(self, service, task_registry, temp_dir):
        """Should update task status to EXTRACTING during extraction."""
        url = "https://example.com/file"
        output_dir = temp_dir / "downloads"

        with patch.object(
            service._manager, "download_url", new_callable=AsyncMock
        ) as mock_download:
            mock_download.return_value = []

            task_id = await service.download(url, output_dir)
            task = await task_registry.get_task(task_id)

            # After extraction, should be at least past EXTRACTING
            assert task.status != TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_download_with_password(self, service):
        """Should pass password to extract_files."""
        url = "https://example.com/file"
        output_dir = Path("/tmp/downloads")
        password = "secret"

        with patch.object(
            service._manager, "download_url", new_callable=AsyncMock
        ) as mock_download:
            mock_download.return_value = []

            await service.download(url, output_dir, password=password)
            mock_download.assert_called_once()
            args, _ = mock_download.call_args
            assert args[0] == url
            assert args[1] == password

    @pytest.mark.asyncio
    async def test_download_emits_progress_events(self, service, event_bus):
        """Should emit DOWNLOAD_PROGRESS events via progress callback."""
        url = "https://example.com/file"
        output_dir = Path("/tmp/downloads")
        progress_events = []

        def capture_progress(data):
            progress_events.append(data)

        event_bus.subscribe(DOWNLOAD_PROGRESS, capture_progress)

        with patch.object(
            service._manager, "download_url", new_callable=AsyncMock
        ) as mock_download:
            # Simulate progress callback being called
            def side_effect(url, password, output_dir, on_progress):
                if on_progress:
                    task = DownloadTask(
                        file_info=FileInfo(url=url, filename="test.txt"),
                        output_path=Path("/tmp/test.txt"),
                    )
                    task.progress.status = DownloadStatus.DOWNLOADING
                    task.progress.downloaded = 50
                    task.progress.total = 100
                    on_progress(task)
                return [DownloadResult.succeeded(task)]

            mock_download.side_effect = side_effect

            await service.download(url, output_dir)

            assert len(progress_events) > 0

    @pytest.mark.asyncio
    async def test_download_emits_complete_event(self, service, event_bus):
        """Should emit DOWNLOAD_COMPLETE on success."""
        url = "https://example.com/file"
        output_dir = Path("/tmp/downloads")
        complete_events = []

        def capture_complete(data):
            complete_events.append(data)

        event_bus.subscribe(DOWNLOAD_COMPLETE, capture_complete)

        with patch.object(
            service._manager, "download_url", new_callable=AsyncMock
        ) as mock_download:
            file_info = FileInfo(url=url, filename="test.txt", size=100)

            task = DownloadTask(file_info=file_info, output_path=output_dir / "test.txt")
            task.progress.status = DownloadStatus.COMPLETED
            mock_download.return_value = [DownloadResult.succeeded(task)]

            await service.download(url, output_dir)

            assert len(complete_events) > 0

    @pytest.mark.asyncio
    async def test_download_emits_error_event(self, service, event_bus):
        """Should emit DOWNLOAD_ERROR on failure."""
        url = "https://example.com/file"
        output_dir = Path("/tmp/downloads")
        error_events = []

        def capture_error(data):
            error_events.append(data)

        event_bus.subscribe(DOWNLOAD_ERROR, capture_error)

        with patch.object(
            service._manager, "download_url", new_callable=AsyncMock
        ) as mock_download:
            file_info = FileInfo(url=url, filename="test.txt", size=100)

            task = DownloadTask(file_info=file_info, output_path=output_dir / "test.txt")
            task.progress.status = DownloadStatus.FAILED
            task.progress.error = "Download failed"
            mock_download.return_value = [DownloadResult.failed(task, "Download failed")]

            await service.download(url, output_dir)

            assert len(error_events) > 0


class TestDownloadServiceListFiles:
    """Tests for DownloadService.list_files()."""

    @pytest.mark.asyncio
    async def test_list_files_returns_file_info(self, service):
        """Should return list of FileInfo from extractor."""
        url = "https://example.com/file"
        expected_files = [
            FileInfo(url=url, filename="test1.txt", size=100),
            FileInfo(url=url, filename="test2.txt", size=200),
        ]

        with patch.object(
            service._manager, "extract_files", new_callable=AsyncMock
        ) as mock_extract:
            mock_extract.return_value = expected_files

            files = await service.list_files(url)

            assert len(files) == 2
            assert files[0].filename == "test1.txt"
            assert files[1].filename == "test2.txt"

    @pytest.mark.asyncio
    async def test_list_files_with_password(self, service):
        """Should pass password to extract_files."""
        url = "https://example.com/file"
        password = "secret"

        with patch.object(
            service._manager, "extract_files", new_callable=AsyncMock
        ) as mock_extract:
            mock_extract.return_value = []

            await service.list_files(url, password=password)
            mock_extract.assert_called_once_with(url, password)


class TestDownloadServiceGetStatus:
    """Tests for DownloadService.get_status()."""

    @pytest.mark.asyncio
    async def test_get_status_returns_task_info(self, service, task_registry):
        """Should return TaskInfo for existing task."""
        task_id = await task_registry.create_task("https://example.com", Path("/tmp"))

        status = await service.get_status(task_id)

        assert status is not None
        assert status.task_id == task_id

    @pytest.mark.asyncio
    async def test_get_status_returns_none_for_missing_task(self, service):
        """Should return None for non-existent task."""
        status = await service.get_status("nonexistent-uuid")
        assert status is None


class TestDownloadServiceListActive:
    """Tests for DownloadService.list_active()."""

    @pytest.mark.asyncio
    async def test_list_active_returns_pending_tasks(self, service, task_registry):
        """Should return tasks that are not completed/failed/cancelled."""
        task1_id = await task_registry.create_task("https://example.com/1", Path("/tmp"))
        task2_id = await task_registry.create_task("https://example.com/2", Path("/tmp"))
        await task_registry.update_task(task1_id, status=TaskStatus.DOWNLOADING)
        await task_registry.update_task(task2_id, status=TaskStatus.COMPLETED)

        active = await service.list_active()

        assert len(active) == 1
        assert active[0].task_id == task1_id


class TestDownloadServiceCancel:
    """Tests for DownloadService.cancel()."""

    @pytest.mark.asyncio
    async def test_cancel_updates_task_status(self, service, task_registry):
        """Should update task status to CANCELLED."""
        task_id = await task_registry.create_task("https://example.com", Path("/tmp"))

        result = await service.cancel(task_id)

        assert result is True
        task = await task_registry.get_task(task_id)
        assert task.status == TaskStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_returns_false_for_missing_task(self, service):
        """Should return False for non-existent task."""
        result = await service.cancel("nonexistent-uuid")
        assert result is False

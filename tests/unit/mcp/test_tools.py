from __future__ import annotations

import contextlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from getit.extractors.base import FileInfo
from getit.mcp.server import ServerContext
from getit.mcp.tools import cancel_download, download, get_download_status, list_files
from getit.tasks import TaskInfo, TaskRegistry, TaskStatus


@pytest.fixture
def mock_context():
    ctx = ServerContext()
    ctx.download_service = AsyncMock()
    ctx.download_service._manager = MagicMock()
    ctx.task_registry = AsyncMock(spec=TaskRegistry)
    ctx.task_registry._db = MagicMock()
    return ctx


@pytest.fixture(autouse=True)
def setup_context(mock_context):
    with patch("getit.mcp.tools.get_context", return_value=mock_context):
        yield mock_context


class TestDownload:
    @pytest.mark.asyncio
    async def test_returns_task_id(self, mock_context):
        mock_context.download_service.download.return_value = "test-task-123"

        result = await download("https://gofile.io/d/abc123")

        assert result == {"task_id": "test-task-123"}
        mock_context.download_service.download.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_default_output_dir(self, mock_context):
        mock_context.download_service.download.return_value = "task-id"

        await download("https://gofile.io/d/abc123")

        call_args = mock_context.download_service.download.call_args
        assert call_args[0][1] == Path.cwd() / "downloads"

    @pytest.mark.asyncio
    async def test_uses_custom_output_dir(self, mock_context):
        mock_context.download_service.download.return_value = "task-id"

        await download("https://gofile.io/d/abc123", output_dir="/custom/path")

        call_args = mock_context.download_service.download.call_args
        assert call_args[0][1] == Path("/custom/path")

    @pytest.mark.asyncio
    async def test_passes_password(self, mock_context):
        mock_context.download_service.download.return_value = "task-id"

        await download("https://gofile.io/d/abc123", password="secret")

        call_args = mock_context.download_service.download.call_args
        assert call_args[0][2] == "secret"

    @pytest.mark.asyncio
    async def test_connects_task_registry_if_needed(self, mock_context):
        mock_context.task_registry._db = None
        mock_context.task_registry.connect = AsyncMock()
        mock_context.download_service.download.return_value = "task-id"

        await download("https://gofile.io/d/abc123")

        mock_context.task_registry.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_starts_download_service_if_needed(self, mock_context):
        mock_context.download_service._manager = None
        mock_context.download_service.start = AsyncMock()
        mock_context.download_service.download.return_value = "task-id"

        await download("https://gofile.io/d/abc123")

        mock_context.download_service.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_if_download_service_not_initialized(self, mock_context):
        mock_context.download_service = None

        with pytest.raises(RuntimeError, match="DownloadService not initialized"):
            await download("https://gofile.io/d/abc123")


class TestListFiles:
    @pytest.mark.asyncio
    async def test_returns_file_list(self, mock_context):
        file_info = FileInfo(
            url="https://gofile.io/d/abc123",
            filename="test.txt",
            size=1024,
            direct_url="https://direct.url",
            password_protected=False,
            checksum="abc123",
            checksum_type="md5",
            parent_folder="folder",
            extractor_name="gofile",
            encrypted=False,
        )
        mock_context.download_service.list_files.return_value = [file_info]

        result = await list_files("https://gofile.io/d/abc123")

        assert "files" in result
        assert len(result["files"]) == 1
        assert result["files"][0]["filename"] == "test.txt"
        assert result["files"][0]["size"] == 1024

    @pytest.mark.asyncio
    async def test_converts_all_file_info_fields(self, mock_context):
        file_info = FileInfo(
            url="https://gofile.io/d/abc123",
            filename="test.txt",
            size=2048,
            direct_url="https://direct.url",
            password_protected=True,
            checksum="def456",
            checksum_type="sha256",
            parent_folder="parent",
            extractor_name="pixeldrain",
            encrypted=True,
        )
        mock_context.download_service.list_files.return_value = [file_info]

        result = await list_files("https://gofile.io/d/abc123")

        file_dict = result["files"][0]
        assert file_dict["url"] == "https://gofile.io/d/abc123"
        assert file_dict["filename"] == "test.txt"
        assert file_dict["size"] == 2048
        assert file_dict["direct_url"] == "https://direct.url"
        assert file_dict["password_protected"] is True
        assert file_dict["checksum"] == "def456"
        assert file_dict["checksum_type"] == "sha256"
        assert file_dict["parent_folder"] == "parent"
        assert file_dict["extractor_name"] == "pixeldrain"
        assert file_dict["encrypted"] is True

    @pytest.mark.asyncio
    async def test_passes_password(self, mock_context):
        mock_context.download_service.list_files.return_value = []

        await list_files("https://gofile.io/d/abc123", password="secret")

        mock_context.download_service.list_files.assert_called_once_with(
            "https://gofile.io/d/abc123", "secret"
        )

    @pytest.mark.asyncio
    async def test_handles_empty_file_list(self, mock_context):
        mock_context.download_service.list_files.return_value = []

        result = await list_files("https://gofile.io/d/abc123")

        assert result == {"files": []}

    @pytest.mark.asyncio
    async def test_connects_task_registry_if_needed(self, mock_context):
        mock_context.task_registry._db = None
        mock_context.task_registry.connect = AsyncMock()
        mock_context.download_service.list_files.return_value = []

        await list_files("https://gofile.io/d/abc123")

        mock_context.task_registry.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_starts_download_service_if_needed(self, mock_context):
        mock_context.download_service._manager = None
        mock_context.download_service.start = AsyncMock()
        mock_context.download_service.list_files.return_value = []

        await list_files("https://gofile.io/d/abc123")

        mock_context.download_service.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_if_download_service_not_initialized(self, mock_context):
        mock_context.download_service = None

        with pytest.raises(RuntimeError, match="DownloadService not initialized"):
            await list_files("https://gofile.io/d/abc123")


class TestGetDownloadStatus:
    @pytest.mark.asyncio
    async def test_returns_task_status(self, mock_context):
        task_info = TaskInfo(
            task_id="test-task-123",
            url="https://gofile.io/d/abc123",
            output_dir=Path("/downloads"),
            status=TaskStatus.DOWNLOADING,
            progress={"percentage": 50.0, "downloaded": 500.0, "total": 1000.0},
        )
        mock_context.task_registry.get_task.return_value = task_info

        result = await get_download_status("test-task-123")

        assert result["task_id"] == "test-task-123"
        assert result["url"] == "https://gofile.io/d/abc123"
        assert result["status"] == "downloading"
        assert result["progress"]["percentage"] == 50.0
        assert result["output_dir"] == "/downloads"

    @pytest.mark.asyncio
    async def test_converts_datetime_to_isoformat(self, mock_context):
        task_info = TaskInfo(
            task_id="test-task-123",
            url="https://gofile.io/d/abc123",
            output_dir=Path("/downloads"),
            status=TaskStatus.PENDING,
        )
        mock_context.task_registry.get_task.return_value = task_info

        result = await get_download_status("test-task-123")

        assert "created_at" in result
        assert "updated_at" in result
        assert isinstance(result["created_at"], str)
        assert isinstance(result["updated_at"], str)

    @pytest.mark.asyncio
    async def test_includes_error_if_present(self, mock_context):
        task_info = TaskInfo(
            task_id="test-task-123",
            url="https://gofile.io/d/abc123",
            output_dir=Path("/downloads"),
            status=TaskStatus.FAILED,
            error="Connection timeout",
        )
        mock_context.task_registry.get_task.return_value = task_info

        result = await get_download_status("test-task-123")

        assert result["error"] == "Connection timeout"

    @pytest.mark.asyncio
    async def test_raises_value_error_if_task_not_found(self, mock_context):
        mock_context.task_registry.get_task.return_value = None

        with pytest.raises(ValueError, match="Task test-task-123 not found"):
            await get_download_status("test-task-123")

    @pytest.mark.asyncio
    async def test_connects_task_registry_if_needed(self, mock_context):
        mock_context.task_registry._db = None
        mock_context.task_registry.connect = AsyncMock()
        mock_context.task_registry.get_task.return_value = None

        with contextlib.suppress(ValueError):
            await get_download_status("test-task-123")

        mock_context.task_registry.connect.assert_called_once()


class TestCancelDownload:
    @pytest.mark.asyncio
    async def test_returns_success_true_when_cancelled(self, mock_context):
        mock_context.download_service.cancel.return_value = True

        result = await cancel_download("test-task-123")

        assert result == {"success": True}

    @pytest.mark.asyncio
    async def test_returns_success_false_when_not_found(self, mock_context):
        mock_context.download_service.cancel.return_value = False

        result = await cancel_download("test-task-123")

        assert result == {"success": False}

    @pytest.mark.asyncio
    async def test_calls_download_service_cancel(self, mock_context):
        mock_context.download_service.cancel.return_value = True

        await cancel_download("test-task-123")

        mock_context.download_service.cancel.assert_called_once_with("test-task-123")

    @pytest.mark.asyncio
    async def test_connects_task_registry_if_needed(self, mock_context):
        mock_context.task_registry._db = None
        mock_context.task_registry.connect = AsyncMock()
        mock_context.download_service.cancel.return_value = True

        await cancel_download("test-task-123")

        mock_context.task_registry.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_starts_download_service_if_needed(self, mock_context):
        mock_context.download_service._manager = None
        mock_context.download_service.start = AsyncMock()
        mock_context.download_service.cancel.return_value = True

        await cancel_download("test-task-123")

        mock_context.download_service.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_if_download_service_not_initialized(self, mock_context):
        mock_context.download_service = None

        with pytest.raises(RuntimeError, match="DownloadService not initialized"):
            await cancel_download("test-task-123")


class TestMCPRegistration:
    @pytest.mark.asyncio
    async def test_download_tool_registered(self):
        from getit.mcp.server import mcp

        tools = [t.name for t in await mcp.list_tools()]
        assert "download" in tools

    @pytest.mark.asyncio
    async def test_list_files_tool_registered(self):
        from getit.mcp.server import mcp

        tools = [t.name for t in await mcp.list_tools()]
        assert "list_files" in tools

    @pytest.mark.asyncio
    async def test_get_download_status_tool_registered(self):
        from getit.mcp.server import mcp

        tools = [t.name for t in await mcp.list_tools()]
        assert "get_download_status" in tools

    @pytest.mark.asyncio
    async def test_cancel_download_tool_registered(self):
        from getit.mcp.server import mcp

        tools = [t.name for t in await mcp.list_tools()]
        assert "cancel_download" in tools

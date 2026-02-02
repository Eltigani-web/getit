"""End-to-end integration tests for MCP server with FakeDownloadService."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

from getit.extractors.base import FileInfo
from getit.mcp.server import ServerContext, mcp
from getit.tasks import TaskRegistry, TaskStatus

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class FakeDownloadService:
    """Fake download service that creates dummy files without network calls."""

    def __init__(self, task_registry: TaskRegistry, download_dir: Path):
        self._task_registry = task_registry
        self._download_dir = download_dir
        self._manager = object()

    async def start(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def download(self, url: str, output_dir: Path, password: str | None = None) -> str:
        task_id = await self._task_registry.create_task(url, output_dir)
        await self._task_registry.update_task(task_id, status=TaskStatus.DOWNLOADING)

        output_dir.mkdir(parents=True, exist_ok=True)
        dummy_file = output_dir / "fake_download.txt"
        dummy_file.write_text(f"Fake download content for {url}")

        await self._task_registry.update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            progress={"percentage": 100.0, "downloaded": 1024.0, "total": 1024.0},
        )
        return task_id

    async def list_files(self, url: str, password: str | None = None) -> list[FileInfo]:
        return [
            FileInfo(
                url=url,
                filename="fake_file.txt",
                size=1024,
                direct_url=f"{url}/direct",
                password_protected=password is not None,
                checksum="abc123",
                checksum_type="md5",
                parent_folder=None,
                extractor_name="fake",
                encrypted=False,
            )
        ]

    async def get_status(self, task_id: str):
        return await self._task_registry.get_task(task_id)

    async def list_active(self):
        return await self._task_registry.list_active()

    async def cancel(self, task_id: str) -> bool:
        task = await self._task_registry.get_task(task_id)
        if not task:
            return False
        await self._task_registry.update_task(task_id, status=TaskStatus.CANCELLED)
        return True


@pytest.fixture
def temp_dirs():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        db_dir = tmp_path / "db"
        db_dir.mkdir()
        download_dir = tmp_path / "downloads"
        download_dir.mkdir()
        yield {"db": db_dir, "download": download_dir}


@pytest_asyncio.fixture
async def mcp_context(temp_dirs) -> AsyncGenerator[ServerContext, None]:
    import getit.mcp.server as server_module

    task_registry = TaskRegistry(db_path=temp_dirs["db"] / "tasks.db")
    await task_registry.connect()

    fake_service = FakeDownloadService(task_registry, temp_dirs["download"])

    ctx = ServerContext()
    ctx.task_registry = task_registry
    ctx.download_service = fake_service

    original_context = server_module._context
    server_module._context = ctx

    import getit.mcp.prompts  # noqa: F401
    import getit.mcp.resources  # noqa: F401
    import getit.mcp.tools  # noqa: F401

    yield ctx

    await task_registry.close()
    server_module._context = original_context


def get_tool_result(result):
    """Extract dict result from mcp.call_tool return value (tuple of content_list, result_dict)."""
    if isinstance(result, tuple) and len(result) == 2:
        return result[1]
    return result


def get_tool_text(result):
    """Extract text from mcp.call_tool return value."""
    if isinstance(result, tuple) and len(result) == 2:
        content_list = result[0]
        if content_list and hasattr(content_list[0], "text"):
            return content_list[0].text
    return str(result)


@pytest.mark.integration
class TestMCPToolsE2E:
    @pytest.mark.asyncio
    async def test_download_creates_file_on_disk(self, mcp_context, temp_dirs):
        result = await mcp.call_tool(
            "download",
            {"url": "https://example.com/test.zip", "output_dir": str(temp_dirs["download"])},
        )

        result_dict = get_tool_result(result)
        assert "task_id" in result_dict

        dummy_file = temp_dirs["download"] / "fake_download.txt"
        assert dummy_file.exists()
        assert "Fake download content" in dummy_file.read_text()

    @pytest.mark.asyncio
    async def test_download_with_password(self, mcp_context, temp_dirs):
        result = await mcp.call_tool(
            "download",
            {
                "url": "https://example.com/protected.zip",
                "output_dir": str(temp_dirs["download"]),
                "password": "secret123",
            },
        )

        result_dict = get_tool_result(result)
        assert "task_id" in result_dict

    @pytest.mark.asyncio
    async def test_list_files_returns_file_info(self, mcp_context):
        result = await mcp.call_tool(
            "list_files",
            {"url": "https://example.com/folder"},
        )

        result_dict = get_tool_result(result)
        assert "files" in result_dict
        assert len(result_dict["files"]) == 1
        assert result_dict["files"][0]["filename"] == "fake_file.txt"
        assert result_dict["files"][0]["size"] == 1024

    @pytest.mark.asyncio
    async def test_list_files_with_password(self, mcp_context):
        result = await mcp.call_tool(
            "list_files",
            {"url": "https://example.com/protected", "password": "secret"},
        )

        result_dict = get_tool_result(result)
        assert result_dict["files"][0]["password_protected"] is True

    @pytest.mark.asyncio
    async def test_get_download_status_after_download(self, mcp_context, temp_dirs):
        download_result = await mcp.call_tool(
            "download",
            {"url": "https://example.com/test.zip", "output_dir": str(temp_dirs["download"])},
        )

        task_id = get_tool_result(download_result)["task_id"]

        status_result = await mcp.call_tool(
            "get_download_status",
            {"task_id": task_id},
        )

        status_dict = get_tool_result(status_result)
        assert status_dict["task_id"] == task_id
        assert status_dict["status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_download_status_not_found(self, mcp_context):
        with pytest.raises(Exception) as exc_info:
            await mcp.call_tool(
                "get_download_status",
                {"task_id": "nonexistent-task-id"},
            )

        assert "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_cancel_download_success(self, mcp_context, temp_dirs):
        download_result = await mcp.call_tool(
            "download",
            {"url": "https://example.com/test.zip", "output_dir": str(temp_dirs["download"])},
        )

        task_id = get_tool_result(download_result)["task_id"]

        cancel_result = await mcp.call_tool(
            "cancel_download",
            {"task_id": task_id},
        )

        cancel_dict = get_tool_result(cancel_result)
        assert cancel_dict["success"] is True

    @pytest.mark.asyncio
    async def test_cancel_download_not_found(self, mcp_context):
        result = await mcp.call_tool(
            "cancel_download",
            {"task_id": "nonexistent-task-id"},
        )

        result_dict = get_tool_result(result)
        assert result_dict["success"] is False


@pytest.mark.integration
class TestMCPRegistration:
    @pytest.mark.asyncio
    async def test_all_tools_registered(self, mcp_context):
        tools = await mcp.list_tools()
        tool_names = [t.name for t in tools]

        assert "download" in tool_names
        assert "list_files" in tool_names
        assert "get_download_status" in tool_names
        assert "cancel_download" in tool_names

    @pytest.mark.asyncio
    async def test_resources_registered(self, mcp_context):
        resources = await mcp.list_resources()
        resource_uris = [str(r.uri) for r in resources]

        assert "active-downloads://list" in resource_uris

    @pytest.mark.asyncio
    async def test_prompts_registered(self, mcp_context):
        prompts = await mcp.list_prompts()
        prompt_names = [p.name for p in prompts]

        assert "download_workflow" in prompt_names


@pytest.mark.integration
class TestTaskRegistryPersistence:
    @pytest.mark.asyncio
    async def test_task_persisted_to_sqlite(self, mcp_context, temp_dirs):
        await mcp.call_tool(
            "download",
            {"url": "https://example.com/test.zip", "output_dir": str(temp_dirs["download"])},
        )

        db_file = temp_dirs["db"] / "tasks.db"
        assert db_file.exists()

    @pytest.mark.asyncio
    async def test_multiple_downloads_tracked(self, mcp_context, temp_dirs):
        task_ids = []
        for i in range(3):
            result = await mcp.call_tool(
                "download",
                {
                    "url": f"https://example.com/file{i}.zip",
                    "output_dir": str(temp_dirs["download"]),
                },
            )
            result_dict = get_tool_result(result)
            task_ids.append(result_dict["task_id"])

        for task_id in task_ids:
            task = await mcp_context.task_registry.get_task(task_id)
            assert task is not None
            assert task.status == TaskStatus.COMPLETED

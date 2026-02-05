from __future__ import annotations

import pytest
from mcp.server.fastmcp import FastMCP

from getit.events import EventBus
from getit.mcp.server import ServerContext, create_server, get_context, mcp
from getit.registry import ExtractorRegistry
from getit.service import DownloadService
from getit.tasks import TaskRegistry


@pytest.fixture(autouse=True)
def reset_mcp_state():
    import getit.mcp.server as server_module

    original_context = server_module._context
    original_extractors = ExtractorRegistry._extractors.copy()

    server_module._context = None

    yield

    server_module._context = original_context
    ExtractorRegistry._extractors.clear()
    ExtractorRegistry._extractors.update(original_extractors)


class TestCreateServer:
    def test_returns_fastmcp_and_context(self) -> None:
        server, ctx = create_server()
        assert isinstance(server, FastMCP)
        assert isinstance(ctx, ServerContext)

    def test_server_is_module_mcp_instance(self) -> None:
        server, _ = create_server()
        assert server is mcp

    def test_context_has_event_bus(self) -> None:
        _, ctx = create_server()
        assert isinstance(ctx.event_bus, EventBus)

    def test_context_has_task_registry(self) -> None:
        _, ctx = create_server()
        assert isinstance(ctx.task_registry, TaskRegistry)

    def test_context_has_extractor_registry(self) -> None:
        _, ctx = create_server()
        assert ctx.extractor_registry is ExtractorRegistry

    def test_context_has_download_service(self) -> None:
        _, ctx = create_server()
        assert isinstance(ctx.download_service, DownloadService)


class TestGetContext:
    def test_returns_context_after_create(self) -> None:
        _, expected_ctx = create_server()
        ctx = get_context()
        assert ctx is expected_ctx

    def test_raises_before_create(self) -> None:
        import getit.mcp.server as server_module

        server_module._context = None
        with pytest.raises(RuntimeError, match="not initialized"):
            get_context()
        create_server()


class TestServerContext:
    def test_default_construction(self) -> None:
        ctx = ServerContext()
        assert isinstance(ctx.event_bus, EventBus)
        assert isinstance(ctx.task_registry, TaskRegistry)
        assert ctx.extractor_registry is ExtractorRegistry
        assert ctx.download_service is None


class TestMCPInstance:
    def test_mcp_is_fastmcp(self) -> None:
        assert isinstance(mcp, FastMCP)

    def test_mcp_has_name_getit(self) -> None:
        assert mcp.name == "getit"

    def test_tool_decorator_accessible(self) -> None:
        assert callable(mcp.tool)

    def test_resource_decorator_accessible(self) -> None:
        assert callable(mcp.resource)

    def test_prompt_decorator_accessible(self) -> None:
        assert callable(mcp.prompt)


class TestExtractorRegistration:
    def test_gofile_extractor_registered(self) -> None:
        create_server()
        assert ExtractorRegistry.get("gofile") is not None

    def test_pixeldrain_extractor_registered(self) -> None:
        create_server()
        assert ExtractorRegistry.get("pixeldrain") is not None

    def test_mediafire_extractor_registered(self) -> None:
        create_server()
        assert ExtractorRegistry.get("mediafire") is not None

    def test_onefichier_extractor_registered(self) -> None:
        create_server()
        assert ExtractorRegistry.get("1fichier") is not None

    def test_mega_extractor_registered(self) -> None:
        create_server()
        assert ExtractorRegistry.get("mega") is not None

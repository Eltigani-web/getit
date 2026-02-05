"""MCP server for getit file downloader.

Provides MCP tools, resources, and prompts for download management via stdio transport.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mcp.server.fastmcp import FastMCP

import getit.extractors.gofile  # noqa: F401
import getit.extractors.mediafire  # noqa: F401
import getit.extractors.mega  # noqa: F401
import getit.extractors.onefichier  # noqa: F401
import getit.extractors.pixeldrain  # noqa: F401
from getit.config import get_settings
from getit.events import EventBus
from getit.registry import ExtractorRegistry
from getit.service import DownloadService
from getit.tasks import TaskRegistry


@dataclass
class ServerContext:
    """Holds shared state for MCP server components."""

    event_bus: EventBus = field(default_factory=EventBus)
    task_registry: TaskRegistry = field(default_factory=TaskRegistry)
    extractor_registry: type[ExtractorRegistry] = field(default=ExtractorRegistry)
    download_service: DownloadService | None = None


mcp = FastMCP("getit")

_context: ServerContext | None = None


def get_context() -> ServerContext:
    """Get the current server context. Raises if not initialized."""
    if _context is None:
        raise RuntimeError("Server context not initialized. Call create_server() first.")
    return _context


def create_server() -> tuple[FastMCP, ServerContext]:
    """Create and configure the MCP server with all required registries.

    Returns:
        Tuple of (FastMCP instance, ServerContext with registries)
    """
    global _context

    _context = ServerContext()
    _context.download_service = DownloadService(
        registry=_context.extractor_registry,
        event_bus=_context.event_bus,
        task_registry=_context.task_registry,
        settings=get_settings(),
    )

    return mcp, _context


def main() -> None:
    """Entry point for running the MCP server with stdio transport."""
    create_server()

    import getit.mcp.prompts  # noqa: F401
    import getit.mcp.resources  # noqa: F401

    # Import modules with MCP decorators to register tools, resources, and prompts
    import getit.mcp.tools  # noqa: F401

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

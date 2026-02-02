"""MCP resources for streaming download status updates.

Provides the active_downloads resource that streams real-time updates to subscribed
MCP clients when download progress, completion, or errors occur.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from mcp.server.session import ServerSession

from getit.events import DOWNLOAD_COMPLETE, DOWNLOAD_ERROR, DOWNLOAD_PROGRESS
from getit.mcp.server import get_context, mcp
from getit.mcp.tools import _ensure_services_ready

logger = logging.getLogger(__name__)

ACTIVE_DOWNLOADS_URI = "active-downloads://list"

# Track subscribed sessions
_subscribed_sessions: set[ServerSession] = set()
_event_handlers_registered = False
_registration_lock = asyncio.Lock()


async def _register_event_handlers() -> None:
    """Register EventBus handlers for download events (lazy initialization)."""
    global _event_handlers_registered

    async with _registration_lock:
        if _event_handlers_registered:
            return

        ctx = get_context()

        # Register handlers for all download events
        ctx.event_bus.subscribe(DOWNLOAD_PROGRESS, _on_download_event)
        ctx.event_bus.subscribe(DOWNLOAD_COMPLETE, _on_download_event)
        ctx.event_bus.subscribe(DOWNLOAD_ERROR, _on_download_event)

        _event_handlers_registered = True
        logger.info("EventBus handlers registered for active_downloads resource")


async def _on_download_event(data: Any) -> None:
    """Notify all subscribed sessions when a download event occurs."""
    if not _subscribed_sessions:
        return

    # Notify all subscribed sessions
    for session in list(_subscribed_sessions):
        try:
            await session.send_resource_updated(ACTIVE_DOWNLOADS_URI)
        except Exception:
            logger.exception(
                "Failed to notify session of resource update",
                extra={"uri": ACTIVE_DOWNLOADS_URI},
            )
            _subscribed_sessions.discard(session)


@mcp.resource(ACTIVE_DOWNLOADS_URI)
async def active_downloads() -> list[dict[str, Any]]:
    """Resource that returns current active download tasks.

    Returns a list of all active download tasks with their current status,
    progress, and metadata.
    """
    await _ensure_services_ready()

    ctx = get_context()
    active_tasks = await ctx.task_registry.list_active()

    # Convert TaskInfo objects to dicts for JSON serialization
    tasks_data = []
    for task in active_tasks:
        tasks_data.append(
            {
                "task_id": task.task_id,
                "url": task.url,
                "status": task.status.value,
                "progress": task.progress,
                "output_dir": str(task.output_dir),
                "created_at": task.created_at.isoformat(),
                "updated_at": task.updated_at.isoformat(),
                "error": task.error,
            }
        )

    return tasks_data


# Register subscription handlers using FastMCP's internal MCP server
@mcp._mcp_server.subscribe_resource()
async def handle_subscribe(uri: str) -> None:
    """Handle resource subscription requests.

    Args:
        uri: The resource URI being subscribed to
    """
    if uri != ACTIVE_DOWNLOADS_URI:
        return

    await _ensure_services_ready()
    await _register_event_handlers()

    session = mcp._mcp_server.request_context.session
    _subscribed_sessions.add(session)

    logger.info(
        "Client subscribed to resource",
        extra={"uri": uri, "session_count": len(_subscribed_sessions)},
    )


@mcp._mcp_server.unsubscribe_resource()
async def handle_unsubscribe(uri: str) -> None:
    """Handle resource unsubscription requests.

    Args:
        uri: The resource URI being unsubscribed from
    """
    if uri != ACTIVE_DOWNLOADS_URI:
        return

    session = mcp._mcp_server.request_context.session
    _subscribed_sessions.discard(session)

    logger.info(
        "Client unsubscribed from resource",
        extra={"uri": uri, "session_count": len(_subscribed_sessions)},
    )

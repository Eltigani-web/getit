"""Event bus for publish-subscribe communication.

Provides a lightweight EventBus for streaming progress and status updates
to CLI/TUI/MCP clients. Supports both sync and async callbacks.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

DOWNLOAD_PROGRESS = "download_progress"
DOWNLOAD_COMPLETE = "download_complete"
DOWNLOAD_ERROR = "download_error"


class EventBus:
    """Minimal pub-sub event bus for application events.

    Supports:
    - Subscribe/unsubscribe callbacks to named events
    - Emit events with optional data
    - Sync and async callbacks
    - Exception handling (logs and continues)
    """

    def __init__(self) -> None:
        """Initialize the event bus."""
        self._subscribers: dict[str, list[Callable[[Any], Any]]] = defaultdict(list)

    def subscribe(self, event: str, callback: Callable[[Any], Any]) -> None:
        """Subscribe a callback to an event.

        Args:
            event: Event name (e.g., DOWNLOAD_PROGRESS)
            callback: Callable that receives event data
        """
        self._subscribers[event].append(callback)

    def unsubscribe(self, event: str, callback: Callable[[Any], Any]) -> None:
        """Unsubscribe a callback from an event.

        Args:
            event: Event name
            callback: Callback to remove
        """
        if event in self._subscribers:
            with contextlib.suppress(ValueError):
                self._subscribers[event].remove(callback)

    def emit(self, event: str, data: Any = None) -> None:
        """Emit an event to all subscribers.

        Handles both sync and async callbacks. Async callbacks are scheduled
        as background tasks and exceptions are logged.

        Args:
            event: Event name
            data: Optional data to pass to callbacks
        """
        callbacks = self._subscribers.get(event, [])
        for callback in callbacks:
            try:
                if inspect.iscoroutinefunction(callback):
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        logger.warning(
                            "No running event loop; skipping async callback",
                            extra={"event": event},
                        )
                        continue
                    task = loop.create_task(callback(data))
                    task.add_done_callback(self._log_task_exception)
                else:
                    callback(data)
            except Exception:
                logger.exception(
                    f"Exception in callback for event {event}",
                    extra={"event": event},
                )

    @staticmethod
    def _log_task_exception(task: asyncio.Task) -> None:
        """Log exceptions raised by async callbacks."""
        with contextlib.suppress(asyncio.CancelledError):
            exception = task.exception()
            if exception:
                logger.exception("Exception in async callback", exc_info=exception)

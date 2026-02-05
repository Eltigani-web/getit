"""Unit tests for EventBus module."""

from __future__ import annotations

import asyncio
from unittest.mock import Mock, patch

import pytest

from getit.events import (
    DOWNLOAD_COMPLETE,
    DOWNLOAD_ERROR,
    DOWNLOAD_PROGRESS,
    EventBus,
)


class TestEventBusSubscribe:
    """Tests for EventBus.subscribe()."""

    def test_subscribe_callback(self) -> None:
        """Should allow subscribing a callback to an event."""
        bus = EventBus()
        callback = Mock()
        bus.subscribe(DOWNLOAD_PROGRESS, callback)
        assert len(bus._subscribers[DOWNLOAD_PROGRESS]) == 1
        assert bus._subscribers[DOWNLOAD_PROGRESS][0] == callback

    def test_subscribe_multiple_callbacks(self) -> None:
        """Should allow multiple callbacks for the same event."""
        bus = EventBus()
        callback1 = Mock()
        callback2 = Mock()
        bus.subscribe(DOWNLOAD_PROGRESS, callback1)
        bus.subscribe(DOWNLOAD_PROGRESS, callback2)
        assert len(bus._subscribers[DOWNLOAD_PROGRESS]) == 2

    def test_subscribe_different_events(self) -> None:
        """Should maintain separate subscriber lists for different events."""
        bus = EventBus()
        callback1 = Mock()
        callback2 = Mock()
        bus.subscribe(DOWNLOAD_PROGRESS, callback1)
        bus.subscribe(DOWNLOAD_COMPLETE, callback2)
        assert len(bus._subscribers[DOWNLOAD_PROGRESS]) == 1
        assert len(bus._subscribers[DOWNLOAD_COMPLETE]) == 1


class TestEventBusUnsubscribe:
    """Tests for EventBus.unsubscribe()."""

    def test_unsubscribe_callback(self) -> None:
        """Should remove a callback from an event."""
        bus = EventBus()
        callback = Mock()
        bus.subscribe(DOWNLOAD_PROGRESS, callback)
        bus.unsubscribe(DOWNLOAD_PROGRESS, callback)
        assert len(bus._subscribers[DOWNLOAD_PROGRESS]) == 0

    def test_unsubscribe_specific_callback(self) -> None:
        """Should only remove the specified callback."""
        bus = EventBus()
        callback1 = Mock()
        callback2 = Mock()
        bus.subscribe(DOWNLOAD_PROGRESS, callback1)
        bus.subscribe(DOWNLOAD_PROGRESS, callback2)
        bus.unsubscribe(DOWNLOAD_PROGRESS, callback1)
        assert len(bus._subscribers[DOWNLOAD_PROGRESS]) == 1
        assert bus._subscribers[DOWNLOAD_PROGRESS][0] == callback2

    def test_unsubscribe_nonexistent_callback(self) -> None:
        """Should not raise when unsubscribing nonexistent callback."""
        bus = EventBus()
        callback = Mock()
        bus.unsubscribe(DOWNLOAD_PROGRESS, callback)
        # Should not raise

    def test_unsubscribe_nonexistent_event(self) -> None:
        """Should not raise when unsubscribing from nonexistent event."""
        bus = EventBus()
        callback = Mock()
        bus.unsubscribe("nonexistent_event", callback)
        # Should not raise


class TestEventBusEmit:
    """Tests for EventBus.emit()."""

    def test_emit_calls_callback(self) -> None:
        """Should call registered callbacks when event is emitted."""
        bus = EventBus()
        callback = Mock()
        bus.subscribe(DOWNLOAD_PROGRESS, callback)
        bus.emit(DOWNLOAD_PROGRESS, {"progress": 50})
        callback.assert_called_once_with({"progress": 50})

    def test_emit_calls_multiple_callbacks(self) -> None:
        """Should call all registered callbacks."""
        bus = EventBus()
        callback1 = Mock()
        callback2 = Mock()
        bus.subscribe(DOWNLOAD_PROGRESS, callback1)
        bus.subscribe(DOWNLOAD_PROGRESS, callback2)
        bus.emit(DOWNLOAD_PROGRESS, {"progress": 50})
        callback1.assert_called_once_with({"progress": 50})
        callback2.assert_called_once_with({"progress": 50})

    def test_emit_different_events_independently(self) -> None:
        """Should only call callbacks for the emitted event."""
        bus = EventBus()
        progress_callback = Mock()
        complete_callback = Mock()
        bus.subscribe(DOWNLOAD_PROGRESS, progress_callback)
        bus.subscribe(DOWNLOAD_COMPLETE, complete_callback)
        bus.emit(DOWNLOAD_PROGRESS, {"progress": 50})
        progress_callback.assert_called_once()
        complete_callback.assert_not_called()

    def test_emit_no_callbacks(self) -> None:
        """Should not raise when emitting event with no callbacks."""
        bus = EventBus()
        bus.emit(DOWNLOAD_PROGRESS, {"progress": 50})
        # Should not raise

    def test_emit_with_dict_data(self) -> None:
        """Should pass dict data to callbacks."""
        bus = EventBus()
        callback = Mock()
        bus.subscribe(DOWNLOAD_PROGRESS, callback)
        data = {"progress": 75, "speed": "2MB/s"}
        bus.emit(DOWNLOAD_PROGRESS, data)
        callback.assert_called_once_with(data)

    def test_emit_with_none_data(self) -> None:
        """Should handle None data."""
        bus = EventBus()
        callback = Mock()
        bus.subscribe(DOWNLOAD_COMPLETE, callback)
        bus.emit(DOWNLOAD_COMPLETE, None)
        callback.assert_called_once_with(None)


class TestEventBusCallbackExceptions:
    """Tests for handling exceptions in callbacks."""

    def test_exception_in_callback_logged(self) -> None:
        """Should log exception when callback raises."""
        bus = EventBus()

        def failing_callback(data: dict | None) -> None:
            raise ValueError("Test error")

        bus.subscribe(DOWNLOAD_PROGRESS, failing_callback)

        with patch("getit.events.logger") as mock_logger:
            bus.emit(DOWNLOAD_PROGRESS, {"progress": 50})
            mock_logger.exception.assert_called_once()

    def test_exception_in_callback_continues(self) -> None:
        """Should continue calling remaining callbacks after one fails."""
        bus = EventBus()
        callback1 = Mock(side_effect=ValueError("Test error"))
        callback2 = Mock()

        bus.subscribe(DOWNLOAD_PROGRESS, callback1)
        bus.subscribe(DOWNLOAD_PROGRESS, callback2)

        with patch("getit.events.logger"):
            bus.emit(DOWNLOAD_PROGRESS, {"progress": 50})

        callback2.assert_called_once()

    @pytest.mark.asyncio
    async def test_exception_in_async_callback_logged(self) -> None:
        """Should log exception when async callback raises."""
        bus = EventBus()

        async def failing_async_callback(data: dict | None) -> None:
            raise ValueError("Async test error")

        bus.subscribe(DOWNLOAD_PROGRESS, failing_async_callback)

        with patch("getit.events.logger") as mock_logger:
            bus.emit(DOWNLOAD_PROGRESS, {"progress": 50})
            await asyncio.sleep(0.01)
            mock_logger.exception.assert_called_once()


class TestEventBusAsyncCallbacks:
    """Tests for async callback support."""

    @pytest.mark.asyncio
    async def test_async_callback_executed(self) -> None:
        """Should execute async callbacks."""
        bus = EventBus()
        callback_executed = False

        async def async_callback(data: dict | None) -> None:
            nonlocal callback_executed
            await asyncio.sleep(0.01)
            callback_executed = True

        bus.subscribe(DOWNLOAD_PROGRESS, async_callback)
        bus.emit(DOWNLOAD_PROGRESS, {"progress": 50})

        # Give time for async task to execute
        await asyncio.sleep(0.05)
        assert callback_executed

    @pytest.mark.asyncio
    async def test_sync_and_async_callbacks_together(self) -> None:
        """Should execute both sync and async callbacks."""
        bus = EventBus()
        sync_callback = Mock()

        async def async_callback(data: dict | None) -> None:
            await asyncio.sleep(0.01)

        bus.subscribe(DOWNLOAD_PROGRESS, sync_callback)
        bus.subscribe(DOWNLOAD_PROGRESS, async_callback)
        bus.emit(DOWNLOAD_PROGRESS, {"progress": 50})

        sync_callback.assert_called_once()
        # Give time for async task
        await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_emit_returns_immediately_for_async(self) -> None:
        """Should return immediately when emitting (async runs in background)."""
        bus = EventBus()

        async def slow_callback(data: dict | None) -> None:
            await asyncio.sleep(1)

        bus.subscribe(DOWNLOAD_PROGRESS, slow_callback)

        # Should return immediately, not wait for async
        import time

        start = time.time()
        bus.emit(DOWNLOAD_PROGRESS, {"progress": 50})
        elapsed = time.time() - start
        assert elapsed < 0.1  # Should be almost instant
        await asyncio.sleep(0.01)


class TestEventConstants:
    """Tests for event constants."""

    def test_event_constants_defined(self) -> None:
        """Should have all required event constants."""
        assert DOWNLOAD_PROGRESS == "download_progress"
        assert DOWNLOAD_COMPLETE == "download_complete"
        assert DOWNLOAD_ERROR == "download_error"

    def test_event_constants_are_strings(self) -> None:
        """Event constants should be strings."""
        assert isinstance(DOWNLOAD_PROGRESS, str)
        assert isinstance(DOWNLOAD_COMPLETE, str)
        assert isinstance(DOWNLOAD_ERROR, str)


class TestEventBusIntegration:
    """Integration tests for EventBus."""

    def test_workflow_subscribe_emit_unsubscribe(self) -> None:
        """Should handle complete subscription workflow."""
        bus = EventBus()
        callback = Mock()

        # Subscribe
        bus.subscribe(DOWNLOAD_PROGRESS, callback)
        bus.emit(DOWNLOAD_PROGRESS, {"progress": 50})
        assert callback.call_count == 1

        # Unsubscribe
        bus.unsubscribe(DOWNLOAD_PROGRESS, callback)
        bus.emit(DOWNLOAD_PROGRESS, {"progress": 75})
        assert callback.call_count == 1  # No additional call

    def test_multiple_events_workflow(self) -> None:
        """Should handle events in workflow sequence."""
        bus = EventBus()
        progress_callback = Mock()
        complete_callback = Mock()
        error_callback = Mock()

        bus.subscribe(DOWNLOAD_PROGRESS, progress_callback)
        bus.subscribe(DOWNLOAD_COMPLETE, complete_callback)
        bus.subscribe(DOWNLOAD_ERROR, error_callback)

        # Emit sequence
        bus.emit(DOWNLOAD_PROGRESS, {"progress": 25})
        bus.emit(DOWNLOAD_PROGRESS, {"progress": 50})
        bus.emit(DOWNLOAD_COMPLETE, None)

        assert progress_callback.call_count == 2
        complete_callback.assert_called_once()
        error_callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_progress_tracking_with_async(self) -> None:
        """Should track progress with async callbacks."""
        bus = EventBus()
        updates = []

        async def track_progress(data: dict | None) -> None:
            await asyncio.sleep(0.001)
            if data:
                updates.append(data["progress"])

        bus.subscribe(DOWNLOAD_PROGRESS, track_progress)

        # Emit multiple progress updates
        for progress in [25, 50, 75, 100]:
            bus.emit(DOWNLOAD_PROGRESS, {"progress": progress})

        # Wait for all async tasks
        await asyncio.sleep(0.1)
        assert len(updates) >= 1  # At least one should complete

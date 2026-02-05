from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from getit.events import DOWNLOAD_COMPLETE, DOWNLOAD_ERROR, DOWNLOAD_PROGRESS
from getit.mcp.resources import (
    ACTIVE_DOWNLOADS_URI,
    _on_download_event,
    _register_event_handlers,
    _subscribed_sessions,
    active_downloads,
    handle_subscribe,
    handle_unsubscribe,
)
from getit.mcp.server import ServerContext
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
    with (
        patch("getit.mcp.resources.get_context", return_value=mock_context),
        patch("getit.mcp.tools.get_context", return_value=mock_context),
    ):
        mock_context.event_bus.subscribe = MagicMock()
        yield mock_context


@pytest.fixture(autouse=True)
def reset_module_state():
    import getit.mcp.resources

    getit.mcp.resources._subscribed_sessions.clear()
    getit.mcp.resources._event_handlers_registered = False
    yield
    getit.mcp.resources._subscribed_sessions.clear()
    getit.mcp.resources._event_handlers_registered = False


class TestActiveDownloadsResource:
    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_active_tasks(self, mock_context):
        mock_context.task_registry.list_active.return_value = []

        result = await active_downloads()

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_list_of_active_tasks(self, mock_context):
        task1 = TaskInfo(
            task_id="task-1",
            url="https://gofile.io/d/abc123",
            output_dir=Path("/downloads"),
            status=TaskStatus.DOWNLOADING,
            progress={"percentage": 50.0, "downloaded": 500.0, "total": 1000.0},
        )
        task2 = TaskInfo(
            task_id="task-2",
            url="https://pixeldrain.com/u/xyz789",
            output_dir=Path("/downloads"),
            status=TaskStatus.PENDING,
            progress={},
        )
        mock_context.task_registry.list_active.return_value = [task1, task2]

        result = await active_downloads()

        assert len(result) == 2
        assert result[0]["task_id"] == "task-1"
        assert result[0]["status"] == "downloading"
        assert result[0]["progress"]["percentage"] == 50.0
        assert result[1]["task_id"] == "task-2"
        assert result[1]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_converts_all_task_fields_to_dict(self, mock_context):
        task = TaskInfo(
            task_id="task-123",
            url="https://test.com/file",
            output_dir=Path("/custom/output"),
            status=TaskStatus.EXTRACTING,
            progress={"current": 10, "total": 100},
            error="Test error",
        )
        mock_context.task_registry.list_active.return_value = [task]

        result = await active_downloads()

        assert len(result) == 1
        task_dict = result[0]
        assert task_dict["task_id"] == "task-123"
        assert task_dict["url"] == "https://test.com/file"
        assert task_dict["status"] == "extracting"
        assert task_dict["progress"] == {"current": 10, "total": 100}
        assert task_dict["output_dir"] == "/custom/output"
        assert task_dict["error"] == "Test error"
        assert "created_at" in task_dict
        assert "updated_at" in task_dict

    @pytest.mark.asyncio
    async def test_formats_datetimes_as_isoformat(self, mock_context):
        task = TaskInfo(
            task_id="task-123",
            url="https://test.com/file",
            output_dir=Path("/downloads"),
            status=TaskStatus.DOWNLOADING,
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            updated_at=datetime(2024, 1, 1, 12, 30, 0),
        )
        mock_context.task_registry.list_active.return_value = [task]

        result = await active_downloads()

        assert result[0]["created_at"] == "2024-01-01T12:00:00"
        assert result[0]["updated_at"] == "2024-01-01T12:30:00"

    @pytest.mark.asyncio
    async def test_ensures_services_ready_before_listing(self, mock_context):
        mock_context.task_registry._db = None
        mock_context.task_registry.connect = AsyncMock()
        mock_context.download_service._manager = None
        mock_context.download_service.start = AsyncMock()
        mock_context.task_registry.list_active.return_value = []

        await active_downloads()

        mock_context.task_registry.connect.assert_called_once()
        mock_context.download_service.start.assert_called_once()


class TestEventHandlerRegistration:
    @pytest.mark.asyncio
    async def test_registers_event_handlers_once(self, mock_context):
        await _register_event_handlers()
        await _register_event_handlers()

        assert mock_context.event_bus.subscribe.call_count == 3

        calls = [c[0][0] for c in mock_context.event_bus.subscribe.call_args_list]
        assert DOWNLOAD_PROGRESS in calls
        assert DOWNLOAD_COMPLETE in calls
        assert DOWNLOAD_ERROR in calls

    @pytest.mark.asyncio
    async def test_registers_same_callback_for_all_events(self, mock_context):
        await _register_event_handlers()

        callbacks = [c[0][1] for c in mock_context.event_bus.subscribe.call_args_list]
        assert all(cb == _on_download_event for cb in callbacks)


class TestDownloadEventNotification:
    @pytest.mark.asyncio
    async def test_does_nothing_when_no_subscribed_sessions(self):
        await _on_download_event({"task_id": "test"})

    @pytest.mark.asyncio
    async def test_notifies_all_subscribed_sessions(self):
        session1 = AsyncMock()
        session2 = AsyncMock()
        _subscribed_sessions.add(session1)
        _subscribed_sessions.add(session2)

        await _on_download_event({"task_id": "test"})

        session1.send_resource_updated.assert_called_once()
        session2.send_resource_updated.assert_called_once()

    @pytest.mark.asyncio
    async def test_continues_on_notification_error(self):
        session1 = AsyncMock()
        session2 = AsyncMock()
        session1.send_resource_updated.side_effect = Exception("Connection lost")
        _subscribed_sessions.add(session1)
        _subscribed_sessions.add(session2)

        await _on_download_event({"task_id": "test"})

        session2.send_resource_updated.assert_called_once()
        assert session1 not in _subscribed_sessions


class TestSubscribeHandler:
    @pytest.mark.asyncio
    async def test_ignores_non_matching_uri(self, mock_context):
        from getit.mcp.server import mcp

        mock_session = AsyncMock()
        mock_request_context = MagicMock()
        mock_request_context.session = mock_session

        with patch.object(
            type(mcp._mcp_server),
            "request_context",
            new_callable=PropertyMock,
            return_value=mock_request_context,
        ):
            await handle_subscribe("other://uri")

        assert mock_session not in _subscribed_sessions

    @pytest.mark.asyncio
    async def test_adds_session_to_subscribers(self, mock_context):
        from getit.mcp.server import mcp

        mock_session = AsyncMock()
        mock_request_context = MagicMock()
        mock_request_context.session = mock_session

        with patch.object(
            type(mcp._mcp_server),
            "request_context",
            new_callable=PropertyMock,
            return_value=mock_request_context,
        ):
            await handle_subscribe(ACTIVE_DOWNLOADS_URI)

        assert mock_session in _subscribed_sessions

    @pytest.mark.asyncio
    async def test_ensures_services_ready_before_subscribing(self, mock_context):
        from getit.mcp.server import mcp

        mock_context.task_registry._db = None
        mock_context.task_registry.connect = AsyncMock()
        mock_context.download_service._manager = None
        mock_context.download_service.start = AsyncMock()

        mock_session = AsyncMock()
        mock_request_context = MagicMock()
        mock_request_context.session = mock_session

        with patch.object(
            type(mcp._mcp_server),
            "request_context",
            new_callable=PropertyMock,
            return_value=mock_request_context,
        ):
            await handle_subscribe(ACTIVE_DOWNLOADS_URI)

        mock_context.task_registry.connect.assert_called_once()
        mock_context.download_service.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_registers_event_handlers_on_first_subscription(self, mock_context):
        from getit.mcp.server import mcp

        mock_session = AsyncMock()
        mock_request_context = MagicMock()
        mock_request_context.session = mock_session

        with patch.object(
            type(mcp._mcp_server),
            "request_context",
            new_callable=PropertyMock,
            return_value=mock_request_context,
        ):
            await handle_subscribe(ACTIVE_DOWNLOADS_URI)

        assert mock_context.event_bus.subscribe.call_count == 3

    @pytest.mark.asyncio
    async def test_multiple_sessions_can_subscribe(self, mock_context):
        from getit.mcp.server import mcp

        session1 = AsyncMock()
        session2 = AsyncMock()

        mock_request_context1 = MagicMock()
        mock_request_context1.session = session1
        mock_request_context2 = MagicMock()
        mock_request_context2.session = session2

        with patch.object(
            type(mcp._mcp_server),
            "request_context",
            new_callable=PropertyMock,
            return_value=mock_request_context1,
        ):
            await handle_subscribe(ACTIVE_DOWNLOADS_URI)

        with patch.object(
            type(mcp._mcp_server),
            "request_context",
            new_callable=PropertyMock,
            return_value=mock_request_context2,
        ):
            await handle_subscribe(ACTIVE_DOWNLOADS_URI)

        assert session1 in _subscribed_sessions
        assert session2 in _subscribed_sessions
        assert len(_subscribed_sessions) == 2


class TestUnsubscribeHandler:
    @pytest.mark.asyncio
    async def test_ignores_non_matching_uri(self):
        from getit.mcp.server import mcp

        mock_session = AsyncMock()
        _subscribed_sessions.add(mock_session)

        mock_request_context = MagicMock()
        mock_request_context.session = mock_session

        with patch.object(
            type(mcp._mcp_server),
            "request_context",
            new_callable=PropertyMock,
            return_value=mock_request_context,
        ):
            await handle_unsubscribe("other://uri")

        assert mock_session in _subscribed_sessions

    @pytest.mark.asyncio
    async def test_removes_session_from_subscribers(self):
        from getit.mcp.server import mcp

        mock_session = AsyncMock()
        _subscribed_sessions.add(mock_session)

        mock_request_context = MagicMock()
        mock_request_context.session = mock_session

        with patch.object(
            type(mcp._mcp_server),
            "request_context",
            new_callable=PropertyMock,
            return_value=mock_request_context,
        ):
            await handle_unsubscribe(ACTIVE_DOWNLOADS_URI)

        assert mock_session not in _subscribed_sessions

    @pytest.mark.asyncio
    async def test_safe_to_unsubscribe_when_not_subscribed(self):
        from getit.mcp.server import mcp

        mock_session = AsyncMock()
        mock_request_context = MagicMock()
        mock_request_context.session = mock_session

        with patch.object(
            type(mcp._mcp_server),
            "request_context",
            new_callable=PropertyMock,
            return_value=mock_request_context,
        ):
            await handle_unsubscribe(ACTIVE_DOWNLOADS_URI)

        assert mock_session not in _subscribed_sessions

    @pytest.mark.asyncio
    async def test_only_removes_requesting_session(self):
        from getit.mcp.server import mcp

        session1 = AsyncMock()
        session2 = AsyncMock()
        _subscribed_sessions.add(session1)
        _subscribed_sessions.add(session2)

        mock_request_context = MagicMock()
        mock_request_context.session = session1

        with patch.object(
            type(mcp._mcp_server),
            "request_context",
            new_callable=PropertyMock,
            return_value=mock_request_context,
        ):
            await handle_unsubscribe(ACTIVE_DOWNLOADS_URI)

        assert session1 not in _subscribed_sessions
        assert session2 in _subscribed_sessions


class TestMCPResourceRegistration:
    @pytest.mark.asyncio
    async def test_active_downloads_resource_registered(self):
        from getit.mcp.server import mcp

        resources = [str(r.uri) for r in await mcp.list_resources()]
        assert ACTIVE_DOWNLOADS_URI in resources

    @pytest.mark.asyncio
    async def test_resource_returns_list(self, mock_context):
        mock_context.task_registry.list_active.return_value = []

        result = await active_downloads()
        assert result == []


class TestSubscriptionLifecycle:
    @pytest.mark.asyncio
    async def test_full_subscribe_event_unsubscribe_flow(self, mock_context):
        from getit.mcp.server import mcp

        mock_session = AsyncMock()
        mock_request_context = MagicMock()
        mock_request_context.session = mock_session

        with patch.object(
            type(mcp._mcp_server),
            "request_context",
            new_callable=PropertyMock,
            return_value=mock_request_context,
        ):
            await handle_subscribe(ACTIVE_DOWNLOADS_URI)
            assert mock_session in _subscribed_sessions

            await _on_download_event({"task_id": "test"})
            mock_session.send_resource_updated.assert_called_once()

            await handle_unsubscribe(ACTIVE_DOWNLOADS_URI)
            assert mock_session not in _subscribed_sessions

            mock_session.send_resource_updated.reset_mock()
            await _on_download_event({"task_id": "test"})
            mock_session.send_resource_updated.assert_not_called()

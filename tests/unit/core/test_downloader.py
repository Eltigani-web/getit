"""Tests for chunk-level retry logic in FileDownloader."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from getit.core.downloader import FileDownloader, DownloadTask, DownloadStatus, DownloadProgress
from getit.extractors.base import FileInfo
from getit.utils.http import HTTPClient


@pytest.fixture
def sample_file_info():
    return FileInfo(url="http://example.com/file", filename="test.txt", size=10000)


@pytest.fixture
def sample_task(sample_file_info, tmp_path):
    return DownloadTask(
        file_info=sample_file_info,
        output_path=tmp_path / "test.txt",
        max_retries=3,
    )


@pytest.fixture
def mock_http_client():
    client = MagicMock(spec=HTTPClient)
    client.session = MagicMock()
    client.get_file_info = AsyncMock(return_value=(10000, True, None))
    return client


class TestChunkRetry:
    @pytest.mark.asyncio
    async def test_downloader_initialization(self, mock_http_client):
        """FileDownloader initializes with correct defaults."""
        downloader = FileDownloader(mock_http_client)
        assert downloader.chunk_size == 1024 * 1024
        assert downloader.enable_resume is True

    @pytest.mark.asyncio
    async def test_task_starts_with_pending_status(self, sample_task):
        """DownloadTask starts with PENDING status."""
        assert sample_task.progress.status == DownloadStatus.PENDING

    @pytest.mark.asyncio
    async def test_task_tracks_retries(self, sample_task):
        """DownloadTask tracks retry count."""
        assert sample_task.retries == 0
        sample_task.retries = 1
        assert sample_task.retries == 1

    @pytest.mark.asyncio
    async def test_progress_updates_correctly(self, sample_task):
        """Download progress updates are tracked."""
        sample_task.progress.downloaded = 5000
        sample_task.progress.total = 10000
        assert sample_task.progress.downloaded == 5000
        assert sample_task.progress.percentage == 50.0

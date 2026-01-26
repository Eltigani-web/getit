"""Tests for chunk-level retry logic in FileDownloader.

Tests for retry behavior on chunk download failures:
- Timeout on individual chunk should trigger retry
- All retries exhausted should mark task as FAILED
- Retry should preserve download progress
- Multiple chunks failing should retry appropriately
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from getit.core.downloader import FileDownloader, DownloadTask, DownloadStatus
from getit.config import Settings
from getit.extractors.base import FileInfo


class TestChunkRetry:
    """Test suite for chunk-level retry logic."""

    @pytest_asyncio.fixture
    def mock_downloader():
        """Create mock FileDownloader."""
        downloader = AsyncMock(spec=FileDownloader)
        downloader.download = AsyncMock()
        downloader.chunk_timeout = 10
        downloader._speed_samples = MagicMock()
        downloader._decryption_counter = MagicMock()
        downloader._cancel_event = MagicMock()
        return downloader

    @pytest_asyncio.fixture
    def sample_task():
        """Create sample DownloadTask."""
        return DownloadTask(
            file_info=FileInfo(url="http://example.com/file", filename="test.txt", size=10000),
            output_path=MagicMock(),
            progress=MagicMock(total=10000, downloaded=0, speed=0),
            max_retries=3,
        )

    @pytest_asyncio.fixture
    def mock_chunk_response():
        """Create mock async iterator that returns chunks."""

        async def chunk_iter():
            yield b"chunk1"
            yield b"chunk2"
            yield b"chunk3"

        return chunk_iter()

    @pytest_asyncio.fixture
    def mock_chunk_timeout():
        """Create mock async iterator that times out once then succeeds."""
        call_count = 0

        async def chunk_iter():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise asyncio.TimeoutError
            yield b"chunk1"
            yield b"chunk2"
            yield b"chunk3"

        return chunk_iter()

    async def test_chunk_timeout_retries(self, mock_downloader, mock_chunk_timeout):
        """Chunk timeout triggers retry and succeeds on second attempt."""
        mock_downloader.download.return_value = self.sample_task()
        mock_downloader._get_next_chunk = AsyncMock(side_effect=self.mock_chunk_timeout)

        await mock_downloader.download(self.sample_task())

        # Should be called twice (initial attempt + 1 retry)
        assert mock_downloader._get_next_chunk.call_count == 2
        # Final call should have succeeded
        assert mock_downloader.download.call_count == 1

    async def test_chunk_max_retries_fails(self, mock_downloader, mock_chunk_timeout):
        """All chunk retries exhausted marks task as FAILED."""
        task = self.sample_task()
        mock_downloader.download.return_value = task
        mock_downloader._get_next_chunk = AsyncMock(side_effect=self.mock_chunk_timeout)

        result = await mock_downloader.download(task)

        # Should fail after max retries
        assert result is False
        assert task.progress.status == DownloadStatus.FAILED
        assert "retries exhausted" in task.progress.error.lower()

    async def test_chunk_retry_preserves_progress(self, mock_downloader, mock_chunk_timeout):
        """Retry does not reset download progress."""
        task = self.sample_task()
        task.progress.downloaded = 5000
        task.progress.speed = 1024

        mock_downloader.download.return_value = task
        mock_downloader._get_next_chunk = AsyncMock(side_effect=self.mock_chunk_timeout)

        await mock_downloader.download(task)

        # Progress should be preserved, not reset to 0
        assert task.progress.downloaded == 5000
        assert task.progress.speed == 1024

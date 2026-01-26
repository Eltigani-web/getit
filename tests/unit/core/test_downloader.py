"""Unit tests for core/downloader module."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from getit.core.downloader import (
    ChecksumMismatchError,
    DownloadProgress,
    DownloadStatus,
    DownloadTask,
    FileDownloader,
)
from getit.extractors.base import FileInfo


class TestDownloadStatus:
    """Tests for DownloadStatus enum."""

    def test_all_statuses_exist(self) -> None:
        """Should have all required status values."""
        assert DownloadStatus.PENDING
        assert DownloadStatus.DOWNLOADING
        assert DownloadStatus.PAUSED
        assert DownloadStatus.COMPLETED
        assert DownloadStatus.FAILED
        assert DownloadStatus.CANCELLED
        assert DownloadStatus.VERIFYING


class TestDownloadProgress:
    """Tests for DownloadProgress dataclass."""

    def test_default_values(self) -> None:
        """Should have sensible defaults."""
        progress = DownloadProgress()
        assert progress.downloaded == 0
        assert progress.total == 0
        assert progress.speed == 0.0
        assert progress.eta == 0.0
        assert progress.status == DownloadStatus.PENDING
        assert progress.error is None

    def test_percentage_zero_total(self) -> None:
        """Should return 0% when total is 0."""
        progress = DownloadProgress(downloaded=100, total=0)
        assert progress.percentage == 0.0

    def test_percentage_calculation(self) -> None:
        """Should calculate percentage correctly."""
        progress = DownloadProgress(downloaded=50, total=100)
        assert progress.percentage == 50.0

    def test_percentage_caps_at_100(self) -> None:
        """Should cap percentage at 100%."""
        progress = DownloadProgress(downloaded=150, total=100)
        assert progress.percentage == 100.0


class TestDownloadTask:
    """Tests for DownloadTask dataclass."""

    def test_generates_task_id(self, sample_file_info: FileInfo, temp_download_dir: Path) -> None:
        """Should generate a task_id if not provided."""
        task = DownloadTask(
            file_info=sample_file_info,
            output_path=temp_download_dir / "test.zip",
        )
        assert task.task_id
        assert len(task.task_id) == 8

    def test_uses_provided_task_id(
        self, sample_file_info: FileInfo, temp_download_dir: Path
    ) -> None:
        """Should use provided task_id."""
        task = DownloadTask(
            file_info=sample_file_info,
            output_path=temp_download_dir / "test.zip",
            task_id="custom01",
        )
        assert task.task_id == "custom01"

    def test_default_retries(self, sample_file_info: FileInfo, temp_download_dir: Path) -> None:
        """Should have default retry values."""
        task = DownloadTask(
            file_info=sample_file_info,
            output_path=temp_download_dir / "test.zip",
        )
        assert task.retries == 0
        assert task.max_retries == 3


class TestChecksumMismatchError:
    """Tests for ChecksumMismatchError."""

    def test_error_message(self) -> None:
        """Should format error message correctly."""
        error = ChecksumMismatchError("expected123", "actual456", "md5")
        assert "MD5" in str(error)
        assert "expected123" in str(error)
        assert "actual456" in str(error)

    def test_error_attributes(self) -> None:
        """Should store error attributes."""
        error = ChecksumMismatchError("expected", "actual", "sha256")
        assert error.expected == "expected"
        assert error.actual == "actual"
        assert error.checksum_type == "sha256"


class TestFileDownloader:
    """Tests for FileDownloader class."""

    def test_init_defaults(self, mock_http_client: MagicMock) -> None:
        """Should have sensible defaults."""
        downloader = FileDownloader(mock_http_client)
        assert downloader.chunk_size == 1024 * 1024
        assert downloader.enable_resume is True
        assert downloader.speed_limit is None
        assert downloader.verify_checksum is True

    def test_init_custom_values(self, mock_http_client: MagicMock) -> None:
        """Should accept custom values."""
        downloader = FileDownloader(
            mock_http_client,
            chunk_size=512 * 1024,
            enable_resume=False,
            speed_limit=1024 * 1024,
            verify_checksum=False,
        )
        assert downloader.chunk_size == 512 * 1024
        assert downloader.enable_resume is False
        assert downloader.speed_limit == 1024 * 1024
        assert downloader.verify_checksum is False

    def test_hash_algorithms_available(self, mock_http_client: MagicMock) -> None:
        """Should have standard hash algorithms."""
        downloader = FileDownloader(mock_http_client)
        assert "md5" in downloader.HASH_ALGORITHMS
        assert "sha1" in downloader.HASH_ALGORITHMS
        assert "sha256" in downloader.HASH_ALGORITHMS
        assert "sha512" in downloader.HASH_ALGORITHMS

    def test_cancel_event_initialized(self, mock_http_client: MagicMock) -> None:
        downloader = FileDownloader(mock_http_client)
        assert downloader._cancel_event is not None
        assert not downloader._cancel_event.is_set()

    def test_cancel_sets_event(self, mock_http_client: MagicMock) -> None:
        downloader = FileDownloader(mock_http_client)
        downloader.cancel()
        assert downloader._cancel_event.is_set()


class TestFileDownloaderDiskSpace:
    """Tests for disk space checking."""

    def test_check_disk_space_zero_bytes(self, mock_http_client: MagicMock, temp_dir: Path) -> None:
        """Should skip check for zero bytes."""
        downloader = FileDownloader(mock_http_client)
        # Should not raise
        downloader._check_disk_space(temp_dir, 0)

    def test_check_disk_space_negative_bytes(
        self, mock_http_client: MagicMock, temp_dir: Path
    ) -> None:
        """Should skip check for negative bytes."""
        downloader = FileDownloader(mock_http_client)
        # Should not raise
        downloader._check_disk_space(temp_dir, -100)

    def test_check_disk_space_raises_on_insufficient(
        self, mock_http_client: MagicMock, temp_dir: Path
    ) -> None:
        """Should raise OSError when disk space is insufficient."""
        downloader = FileDownloader(mock_http_client)
        # Request absurdly large amount
        with pytest.raises(OSError, match="Insufficient disk space"):
            downloader._check_disk_space(temp_dir, 10**18)  # 1 Exabyte


class TestFileDownloaderSpeedSmoothing:
    """Tests for speed calculation smoothing."""

    def test_update_speed_zero_time_diff(
        self,
        mock_http_client: MagicMock,
        sample_download_task: DownloadTask,
    ) -> None:
        """Should not update speed when time_diff is zero."""
        downloader = FileDownloader(mock_http_client)
        sample_download_task.progress.speed = 100.0

        downloader._update_speed_smoothed(sample_download_task, 1024, 0)

        assert sample_download_task.progress.speed == 100.0

    def test_update_speed_first_sample(
        self,
        mock_http_client: MagicMock,
        sample_download_task: DownloadTask,
    ) -> None:
        """Should set initial speed directly."""
        downloader = FileDownloader(mock_http_client)

        downloader._update_speed_smoothed(sample_download_task, 1024, 1.0)

        assert sample_download_task.progress.speed == 1024.0
        assert sample_download_task.progress._last_speed == 1024.0

    def test_update_speed_smoothing(
        self,
        mock_http_client: MagicMock,
        sample_download_task: DownloadTask,
    ) -> None:
        """Should apply exponential smoothing."""
        downloader = FileDownloader(mock_http_client)
        sample_download_task.progress.total = 10000

        # First sample
        downloader._update_speed_smoothed(sample_download_task, 1000, 1.0)
        first_speed = sample_download_task.progress.speed

        # Second sample with different speed
        downloader._update_speed_smoothed(sample_download_task, 500, 1.0)
        second_speed = sample_download_task.progress.speed

        # Speed should be smoothed between 1000 and 500
        assert 500 < second_speed < 1000

    def test_update_speed_calculates_eta(
        self,
        mock_http_client: MagicMock,
        sample_download_task: DownloadTask,
    ) -> None:
        """Should calculate ETA based on remaining bytes and speed."""
        downloader = FileDownloader(mock_http_client)
        sample_download_task.progress.total = 2000
        sample_download_task.progress.downloaded = 1000

        downloader._update_speed_smoothed(sample_download_task, 500, 1.0)

        # ETA = remaining / speed = 1000 / 500 = 2 seconds
        assert sample_download_task.progress.eta == pytest.approx(2.0, rel=0.1)


class TestFileDownloaderMegaDecryption:
    """Tests for Mega.nz decryption support."""

    def test_create_mega_decryptor(self, mock_http_client: MagicMock) -> None:
        """Should create AES-CTR decryptor."""
        downloader = FileDownloader(mock_http_client)
        key = b"\x00" * 16
        iv = b"\x00" * 16

        decryptor = downloader._create_mega_decryptor(key, iv)

        assert decryptor is not None
        # Verify it can decrypt
        test_data = b"test data here"
        encrypted = decryptor.encrypt(test_data)
        assert encrypted != test_data

    def test_create_mega_decryptor_with_counter(self, mock_http_client: MagicMock) -> None:
        """Should support initial counter offset."""
        downloader = FileDownloader(mock_http_client)
        key = b"\x00" * 16
        iv = b"\x00" * 16

        decryptor = downloader._create_mega_decryptor(key, iv, initial_counter=100)
        assert decryptor is not None


class TestFileDownloaderVerifyChecksum:
    """Tests for checksum verification."""

    @pytest.mark.asyncio
    async def test_verify_unknown_algorithm_returns_true(
        self,
        mock_http_client: MagicMock,
        temp_dir: Path,
    ) -> None:
        """Should return True for unknown checksum types."""
        downloader = FileDownloader(mock_http_client)
        test_file = temp_dir / "test.txt"
        test_file.write_text("test content")

        result = await downloader._verify_file_checksum(test_file, "abc123", "unknown_algo")

        assert result is True

    @pytest.mark.asyncio
    async def test_verify_md5_success(
        self,
        mock_http_client: MagicMock,
        temp_dir: Path,
    ) -> None:
        """Should verify correct MD5 checksum."""
        downloader = FileDownloader(mock_http_client)
        test_file = temp_dir / "test.txt"
        test_file.write_bytes(b"")  # Empty file

        # MD5 of empty file
        result = await downloader._verify_file_checksum(
            test_file, "d41d8cd98f00b204e9800998ecf8427e", "md5"
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_verify_md5_failure(
        self,
        mock_http_client: MagicMock,
        temp_dir: Path,
    ) -> None:
        """Should raise ChecksumMismatchError on mismatch."""
        downloader = FileDownloader(mock_http_client)
        test_file = temp_dir / "test.txt"
        test_file.write_bytes(b"some content")

        with pytest.raises(ChecksumMismatchError) as exc_info:
            await downloader._verify_file_checksum(test_file, "wrong_checksum", "md5")

        assert exc_info.value.expected == "wrong_checksum"
        assert exc_info.value.checksum_type == "md5"

    @pytest.mark.asyncio
    async def test_verify_sha256_success(
        self,
        mock_http_client: MagicMock,
        temp_dir: Path,
    ) -> None:
        """Should verify correct SHA256 checksum."""
        downloader = FileDownloader(mock_http_client)
        test_file = temp_dir / "test.txt"
        test_file.write_bytes(b"")  # Empty file

        # SHA256 of empty file
        result = await downloader._verify_file_checksum(
            test_file,
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "sha256",
        )

        assert result is True

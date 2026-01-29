from __future__ import annotations

import asyncio
import hashlib
import shutil
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import aiofiles
import aiohttp
from Cryptodome.Cipher import AES
from Cryptodome.Util import Counter

from getit.utils.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from getit.extractors.base import FileInfo
    from getit.utils.http import HTTPClient


class DownloadStatus(Enum):
    """Status states for a download task."""

    PENDING = auto()
    DOWNLOADING = auto()
    PAUSED = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()
    VERIFYING = auto()


class ChecksumMismatchError(Exception):
    """Raised when file checksum doesn't match expected value."""

    def __init__(self, expected: str, actual: str, checksum_type: str):
        self.expected = expected
        self.actual = actual
        self.checksum_type = checksum_type
        super().__init__(f"{checksum_type.upper()} mismatch: expected {expected}, got {actual}")


@dataclass
class DownloadProgress:
    """Tracks download progress including speed and ETA."""

    downloaded: int = 0
    total: int = 0
    speed: float = 0.0
    eta: float = 0.0
    status: DownloadStatus = DownloadStatus.PENDING
    error: str | None = None
    _speed_samples: deque = field(default_factory=lambda: deque(maxlen=10))
    _last_speed: float = 0.0

    @property
    def percentage(self) -> float:
        """Calculate download completion percentage."""
        if self.total <= 0:
            return 0.0
        return min(100.0, (self.downloaded / self.total) * 100)


@dataclass
class DownloadTask:
    """Represents a single file download task."""

    file_info: FileInfo
    output_path: Path
    progress: DownloadProgress = field(default_factory=DownloadProgress)
    task_id: str = ""
    retries: int = 0
    max_retries: int = 3

    def __post_init__(self) -> None:
        if not self.task_id:
            import uuid

            self.task_id = str(uuid.uuid4())[:8]


ProgressCallback = Callable[[DownloadTask], None]


class FileDownloader:
    """Download files with resume support, encryption, and progress tracking.

    Features:
        - Resume interrupted downloads (if server supports Range requests)
        - Mega.nz AES-CTR decryption
        - Speed limiting
        - Checksum verification (MD5, SHA1, SHA256, SHA512)
        - Progress callbacks
    """

    HASH_ALGORITHMS = {
        "md5": hashlib.md5,
        "sha1": hashlib.sha1,
        "sha256": hashlib.sha256,
        "sha512": hashlib.sha512,
    }

    def __init__(
        self,
        http_client: HTTPClient,
        chunk_size: int = 1024 * 1024,
        enable_resume: bool = True,
        speed_limit: int | None = None,
        verify_checksum: bool = True,
        chunk_timeout: float = 60.0,
    ):
        """Initialize the file downloader.

        Args:
            http_client: HTTP client for making requests
            chunk_size: Size of download chunks in bytes
            enable_resume: Whether to attempt resuming partial downloads
            speed_limit: Maximum download speed in bytes/second (None for unlimited)
            verify_checksum: Whether to verify file checksums after download
            chunk_timeout: Timeout for individual chunk downloads in seconds
        """
        self.http = http_client
        self.chunk_size = chunk_size
        self.enable_resume = enable_resume
        self.speed_limit = speed_limit
        self.verify_checksum = verify_checksum
        self.chunk_timeout = chunk_timeout
        self._cancel_event: asyncio.Event = asyncio.Event()

    def _prepare_request_context(
        self, file_info: FileInfo
    ) -> tuple[dict[str, str], dict[str, str], str]:
        """Prepare headers, cookies, and download URL from file info."""
        headers = dict(file_info.headers) if file_info.headers else {}
        cookies = dict(file_info.cookies) if file_info.cookies else {}
        download_url = file_info.direct_url or file_info.url
        return headers, cookies, download_url

    def _prepare_decryptor(self, file_info: FileInfo) -> tuple[Any | None, bool]:
        """Create decryptor if file is encrypted with Mega encryption."""
        is_encrypted = getattr(file_info, "encrypted", False)
        if is_encrypted and file_info.encryption_key and file_info.encryption_iv:
            decryptor = self._create_mega_decryptor(
                file_info.encryption_key, file_info.encryption_iv
            )
            return decryptor, True
        return None, is_encrypted

    def _calculate_resume_position(
        self,
        temp_path: Path,
        total_size: int,
        supports_resume: bool,
        is_encrypted: bool,
        headers: dict[str, str],
    ) -> int:
        """Calculate resume position and update headers if resuming."""
        if is_encrypted and temp_path.exists():
            temp_path.unlink()
            return 0

        if not (self.enable_resume and temp_path.exists()):
            return 0

        resume_pos = temp_path.stat().st_size

        if total_size > 0 and resume_pos >= total_size:
            temp_path.unlink()
            return 0

        if resume_pos > 0 and supports_resume:
            headers["Range"] = f"bytes={resume_pos}-"
            return resume_pos

        return 0

    def _is_cancelled(self, task: DownloadTask) -> bool:
        """Check if download should be cancelled."""
        return self._cancel_event.is_set() or task.progress.status == DownloadStatus.CANCELLED

    async def _handle_pause(self, task: DownloadTask) -> bool:
        """Handle pause state. Returns False if cancelled during pause."""
        while task.progress.status == DownloadStatus.PAUSED:
            await asyncio.sleep(0.1)
            if task.progress.status != DownloadStatus.PAUSED:
                return task.progress.status != DownloadStatus.CANCELLED
        return True

    async def _apply_speed_limit(self, chunk_len: int, current_speed: float) -> None:
        """Apply speed limiting delay if configured."""
        if not self.speed_limit or current_speed <= self.speed_limit:
            return

        target_time = chunk_len / self.speed_limit
        actual_time = chunk_len / current_speed if current_speed > 0 else 0
        delay = target_time - actual_time

        if delay > 0:
            await asyncio.sleep(delay)

    async def _get_next_chunk(
        self,
        task: DownloadTask,
        chunk_iter: Any,
    ) -> bytes | None:
        """Get next chunk with retry logic.

        Wraps chunk iteration with retry to handle transient network failures.
        """
        for attempt in range(task.max_retries + 1):
            try:
                return await chunk_iter.__anext__()
            except StopAsyncIteration:
                return None
            except (TimeoutError, aiohttp.ClientError) as e:
                if attempt < task.max_retries:
                    backoff = 2**attempt
                    await asyncio.sleep(backoff)
                    continue
                task.progress.status = DownloadStatus.FAILED
                task.progress.error = (
                    f"Chunk download timed out after {task.max_retries} retries: {e}"
                )
                return None
        return None

    def _update_speed_smoothed(
        self, task: DownloadTask, bytes_downloaded: int, time_diff: float
    ) -> None:
        """Update download speed using exponential moving average."""
        if time_diff <= 0:
            return

        instant_speed = bytes_downloaded / time_diff
        task.progress._speed_samples.append(instant_speed)

        alpha = 0.3
        if task.progress._last_speed == 0:
            task.progress._last_speed = instant_speed
        else:
            task.progress._last_speed = (
                alpha * instant_speed + (1 - alpha) * task.progress._last_speed
            )

        task.progress.speed = task.progress._last_speed

        if task.progress.speed > 0 and task.progress.total > 0:
            remaining = task.progress.total - task.progress.downloaded
            task.progress.eta = remaining / task.progress.speed

    async def _verify_file_checksum(
        self,
        file_path: Path,
        expected_checksum: str,
        checksum_type: str,
    ) -> bool:
        """Verify file checksum matches expected value."""
        logger.debug("Verifying checksum for %s", file_path)
        checksum_type = checksum_type.lower()
        if checksum_type not in self.HASH_ALGORITHMS:
            return True

        hasher = self.HASH_ALGORITHMS[checksum_type]()

        async with aiofiles.open(file_path, "rb") as f:
            while chunk := await f.read(self.chunk_size):
                hasher.update(chunk)

        actual = hasher.hexdigest()
        logger.debug("Checksum verification - expected=%s, actual=%s", expected_checksum, actual)
        if actual.lower() != expected_checksum.lower():
            raise ChecksumMismatchError(expected_checksum, actual, checksum_type)

        return True

    def _check_disk_space(self, target_dir: Path, required_bytes: int) -> None:
        """Check if sufficient disk space is available."""
        if required_bytes <= 0:
            return
        try:
            stat = shutil.disk_usage(target_dir)
            required_with_buffer = int(required_bytes * 1.1)
            if stat.free < required_with_buffer:
                free_gb = stat.free / (1024**3)
                required_gb = required_bytes / (1024**3)
                raise OSError(
                    f"Insufficient disk space: need {required_gb:.2f}GB, "
                    f"have {free_gb:.2f}GB available"
                )
        except OSError:
            raise
        except Exception:
            pass

    def _create_mega_decryptor(self, key: bytes, iv: bytes, initial_counter: int = 0) -> Any:
        """Create AES-CTR decryptor for Mega.nz encrypted files."""
        iv_int = int.from_bytes(iv[:8], "big")
        ctr = Counter.new(128, initial_value=(iv_int << 64) + initial_counter)
        return AES.new(key, AES.MODE_CTR, counter=ctr)

    async def _cleanup_on_error(
        self, task: DownloadTask, temp_path: Path, error_msg: str | None = None
    ) -> None:
        """Clean up temporary partial file on error.

        Deletes the .part file and sets task to FAILED.
        Called from both disk full errors and cancellation handling.
        """
        # Remove partial file if it exists
        if temp_path.exists():
            temp_path.unlink()

        # Mark task as failed with error details
        task.progress.status = DownloadStatus.FAILED
        if error_msg:
            task.progress.error = error_msg
        elif task.progress.error:
            task.progress.error = f"Failed to clean up: {task.progress.error}"
        else:
            task.progress.error = "Download failed during cleanup"

    async def _download_chunks(
        self,
        task: DownloadTask,
        response: Any,
        file_handle: Any,
        decryptor: Any | None,
        on_progress: ProgressCallback | None,
    ) -> bool:
        """Download file chunks with progress tracking."""
        last_update_time = asyncio.get_event_loop().time()
        bytes_since_update = 0
        chunk_iter = response.content.iter_chunked(self.chunk_size)

        while True:
            if task.progress.status == DownloadStatus.FAILED:
                return False

            chunk = await self._get_next_chunk(task, chunk_iter)
            if chunk is None:
                if task.progress.status == DownloadStatus.FAILED:  # type: ignore[comparison-overlap]
                    return False
                break

            if self._is_cancelled(task):
                task.progress.status = DownloadStatus.CANCELLED
                return False

            if not await self._handle_pause(task):
                return False

            if decryptor:
                chunk = decryptor.decrypt(chunk)

            try:
                await file_handle.write(chunk)
            except OSError as e:
                await self._cleanup_on_error(task, task.output_path, f"Disk write failed: {e}")
                if e.errno == 28:
                    task.progress.error = "Disk full: No space left on device"
                return False

            chunk_len = len(chunk)
            task.progress.downloaded += chunk_len
            bytes_since_update += chunk_len

            current_time = asyncio.get_event_loop().time()
            time_diff = current_time - last_update_time

            if time_diff >= 0.5:
                self._update_speed_smoothed(task, bytes_since_update, time_diff)
                bytes_since_update = 0
                last_update_time = current_time

                if on_progress:
                    on_progress(task)

            await self._apply_speed_limit(chunk_len, task.progress.speed)

        return True

    async def _perform_download(
        self,
        task: DownloadTask,
        temp_path: Path,
        download_url: str,
        headers: dict[str, str],
        cookies: dict[str, str],
        resume_pos: int,
        decryptor: Any | None,
        on_progress: ProgressCallback | None,
    ) -> bool:
        """Perform actual file download."""
        logger.debug("Downloading task=%s to %s", task.task_id, task.output_path)
        mode: Literal["ab", "wb"] = "ab" if resume_pos > 0 else "wb"

        async with (
            aiofiles.open(temp_path, mode) as f,
            await self.http.session.get(
                download_url,
                headers=headers,
                cookies=cookies,
            ) as resp,
        ):
            if resp.status == 416 and temp_path.exists():
                return True

            resp.raise_for_status()

            if task.progress.total == 0:
                content_length = resp.headers.get("content-length")
                if content_length:
                    task.progress.total = int(content_length) + resume_pos

            return await self._download_chunks(task, resp, f, decryptor, on_progress)

    async def _finalize_download(
        self,
        task: DownloadTask,
        file_info: FileInfo,
        output_path: Path,
        temp_path: Path,
        on_progress: ProgressCallback | None,
    ) -> bool:
        """Finalize download by renaming temp file and verifying checksum."""
        logger.debug("Finalizing download: temp=%s -> output=%s", temp_path, output_path)
        temp_path.rename(output_path)
        output_path.chmod(0o644)

        if self.verify_checksum and file_info.checksum and file_info.checksum_type:
            task.progress.status = DownloadStatus.VERIFYING
            if on_progress:
                on_progress(task)
            await self._verify_file_checksum(
                output_path, file_info.checksum, file_info.checksum_type
            )

        task.progress.status = DownloadStatus.COMPLETED
        task.progress.speed = 0
        task.progress.eta = 0

        if on_progress:
            on_progress(task)

        return True

    def _handle_cancellation(self, task: DownloadTask, temp_path: Path) -> bool:
        """Handle download cancellation."""
        task.progress.status = DownloadStatus.CANCELLED
        if temp_path.exists() and not self.enable_resume:
            temp_path.unlink()
        return False

    def _handle_checksum_error(
        self, task: DownloadTask, error: ChecksumMismatchError, output_path: Path
    ) -> bool:
        """Handle checksum mismatch error."""
        task.progress.status = DownloadStatus.FAILED
        task.progress.error = str(error)
        if output_path.exists():
            output_path.unlink()
        return False

    def _handle_download_error(self, task: DownloadTask, error: Exception) -> bool:
        """Handle general download error."""
        task.progress.status = DownloadStatus.FAILED
        task.progress.error = str(error)
        return False

    async def download(
        self,
        task: DownloadTask,
        on_progress: ProgressCallback | None = None,
    ) -> bool:
        """Download a file with resume support and progress tracking.

        Args:
            task: Download task containing file info and output path
            on_progress: Optional callback invoked periodically with progress

        Returns:
            True if download completed successfully, False otherwise
        """
        self._cancel_event.clear()
        file_info = task.file_info
        output_path = task.output_path

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Use the output_path directly - manager already created unique file via mkstemp
        temp_path = output_path

        try:
            task.progress.status = DownloadStatus.DOWNLOADING

            headers, cookies, download_url = self._prepare_request_context(file_info)

            file_size, supports_resume, _ = await self.http.get_file_info(
                download_url, headers=file_info.headers
            )
            if file_size > 0:
                task.progress.total = file_size

            self._check_disk_space(output_path.parent, task.progress.total)

            decryptor, is_encrypted = self._prepare_decryptor(file_info)

            resume_pos = self._calculate_resume_position(
                temp_path, task.progress.total, supports_resume, is_encrypted, headers
            )
            task.progress.downloaded = resume_pos

            success = await self._perform_download(
                task,
                temp_path,
                download_url,
                headers,
                cookies,
                resume_pos,
                decryptor,
                on_progress,
            )

            if not success:
                return False

            return await self._finalize_download(
                task, file_info, output_path, temp_path, on_progress
            )

        except asyncio.CancelledError:
            return self._handle_cancellation(task, temp_path)

        except ChecksumMismatchError as e:
            return self._handle_checksum_error(task, e, output_path)

        except Exception as e:
            return self._handle_download_error(task, e)

    def cancel(self) -> None:
        """Cancel the current download."""
        self._cancel_event.set()

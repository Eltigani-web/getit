"""Download orchestration and concurrent download management."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

    from getit.utils.sanitize import sanitize_filename
from getit.core.downloader import (
    DownloadProgress,
    DownloadStatus,
    DownloadTask,
    FileDownloader,
    ProgressCallback,
)
)
from getit.extractors.base import BaseExtractor, FileInfo
from getit.extractors.gofile import GoFileExtractor
from getit.extractors.mediafire import MediaFireExtractor
from getit.extractors.mega import MegaExtractor
from getit.extractors.onefichier import OneFichierExtractor
from getit.extractors.pixeldrain import PixelDrainExtractor
from getit.utils.http import HTTPClient

if TYPE_CHECKING:
    pass


@dataclass
class DownloadResult:
    """Result of a download operation with success/failure status."""

    task: DownloadTask
    success: bool
    error: Optional[str] = None

    @classmethod
    def succeeded(cls, task: DownloadTask) -> DownloadResult:
        return cls(task=task, success=True)

    @classmethod
    def failed(cls, task: DownloadTask, error: str) -> DownloadResult:
        return cls(task=task, success=False, error=error)

    @classmethod
    def cancelled(cls, task: DownloadTask) -> DownloadResult:
        return cls(task=task, success=False, error="Download cancelled")


class DownloadManager:
    EXTRACTORS: list[type[BaseExtractor]] = [
        GoFileExtractor,
        PixelDrainExtractor,
        MediaFireExtractor,
        OneFichierExtractor,
        MegaExtractor,
    ]

    def __init__(
        self,
        output_dir: Path,
        max_concurrent: int = 3,
        chunk_size: int = 1024 * 1024,
        enable_resume: bool = True,
        speed_limit: Optional[int] = None,
        max_retries: int = 3,
        requests_per_second: float = 10.0,
    ):
        self.output_dir = Path(output_dir)
        self.max_concurrent = max_concurrent
        self.chunk_size = chunk_size
        self.enable_resume = enable_resume
        self.speed_limit = speed_limit
        self.max_retries = max_retries
        self.requests_per_second = requests_per_second

        self._http: Optional[HTTPClient] = None
        self._tasks: list[DownloadTask] = []
        self._active_downloads: dict[str, asyncio.Task] = {}
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._extractors: dict[str, BaseExtractor] = {}

    async def __aenter__(self) -> DownloadManager:
        await self.start()
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def start(self) -> None:
        self._http = HTTPClient(
            requests_per_second=self.requests_per_second,
        )
        await self._http.start()
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        self._init_extractors()

    async def close(self) -> None:
        for task in self._active_downloads.values():
            task.cancel()
        if self._http:
            await self._http.close()

    def _init_extractors(self) -> None:
        if not self._http:
            return
        for extractor_cls in self.EXTRACTORS:
            extractor = extractor_cls(self._http)
            self._extractors[extractor_cls.EXTRACTOR_NAME] = extractor

    def get_extractor(self, url: str) -> Optional[BaseExtractor]:
        for extractor in self._extractors.values():
            if extractor.can_handle(url):
                return extractor
        return None

    async def extract_files(self, url: str, password: Optional[str] = None) -> list[FileInfo]:
        extractor = self.get_extractor(url)
        if not extractor:
            raise ValueError(f"No extractor found for URL: {url}")
        return await extractor.extract(url, password)

    def create_task(
        self,
        file_info: FileInfo,
        output_dir: Optional[Path] = None,
    ) -> DownloadTask:
        target_dir = output_dir or self.output_dir

        if file_info.parent_folder:
            target_dir = target_dir / file_info.parent_folder

        output_path = target_dir / sanitize_filename(file_info.filename)

        counter = 1
        original_stem = output_path.stem
        original_suffix = output_path.suffix
        while output_path.exists():
            output_path = target_dir / f"{original_stem}_{counter}{original_suffix}"
            counter += 1

        task = DownloadTask(
            file_info=file_info,
            output_path=output_path,
            max_retries=self.max_retries,
        )
        task.progress.total = file_info.size

        self._tasks.append(task)
        return task

    async def download_task(
        self,
        task: DownloadTask,
        on_progress: Optional[ProgressCallback] = None,
    ) -> DownloadResult:
        if not self._http or not self._semaphore:
            raise RuntimeError("DownloadManager not started")

        async with self._semaphore:
            downloader = FileDownloader(
                self._http,
                chunk_size=self.chunk_size,
                enable_resume=self.enable_resume,
                speed_limit=self.speed_limit,
            )

            for attempt in range(task.max_retries + 1):
                task.retries = attempt
                success = await downloader.download(task, on_progress)

                if success:
                    return DownloadResult.succeeded(task)

                if task.progress.status == DownloadStatus.CANCELLED:
                    return DownloadResult.cancelled(task)

                if attempt < task.max_retries:
                    await asyncio.sleep(2**attempt)
                    task.progress.status = DownloadStatus.PENDING
                    task.progress.error = None

            return DownloadResult.failed(task, task.progress.error or "Max retries exceeded")

    async def download_url(
        self,
        url: str,
        password: Optional[str] = None,
        output_dir: Optional[Path] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> list[DownloadResult]:
        files = await self.extract_files(url, password)
        results: list[DownloadResult] = []

        tasks = [self.create_task(f, output_dir) for f in files]

        download_coros = [self.download_task(task, on_progress) for task in tasks]

        results = await asyncio.gather(*download_coros)
        return list(results)

    async def download_urls(
        self,
        urls: list[str],
        password: Optional[str] = None,
        output_dir: Optional[Path] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> list[DownloadResult]:
        all_results: list[DownloadResult] = []

        for url in urls:
            try:
                results = await self.download_url(url, password, output_dir, on_progress)
                all_results.extend(results)
            except Exception as e:
                dummy_task = DownloadTask(
                    file_info=FileInfo(url=url, filename="error"),
                    output_path=Path("error"),
                )
                dummy_task.progress.status = DownloadStatus.FAILED
                dummy_task.progress.error = str(e)
                all_results.append(DownloadResult.failed(dummy_task, str(e)))

        return all_results

    @property
    def tasks(self) -> list[DownloadTask]:
        return self._tasks.copy()

    def get_task(self, task_id: str) -> Optional[DownloadTask]:
        for task in self._tasks:
            if task.task_id == task_id:
                return task
        return None

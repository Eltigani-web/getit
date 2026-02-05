"""DownloadService facade for coordinating downloads with events and persistence."""

from __future__ import annotations

import asyncio
from pathlib import Path

from getit.config import Settings
from getit.core.downloader import DownloadStatus, DownloadTask
from getit.core.manager import DownloadManager, DownloadResult
from getit.events import DOWNLOAD_COMPLETE, DOWNLOAD_ERROR, DOWNLOAD_PROGRESS, EventBus
from getit.extractors.base import FileInfo
from getit.registry import ExtractorRegistry
from getit.tasks import TaskInfo, TaskRegistry, TaskStatus
from getit.utils.logging import get_logger

logger = get_logger(__name__)


class DownloadService:
    def __init__(
        self,
        registry: ExtractorRegistry | type[ExtractorRegistry],
        event_bus: EventBus,
        task_registry: TaskRegistry,
        settings: Settings | None = None,
    ):
        if isinstance(registry, type):
            self._registry = registry()
        else:
            self._registry = registry
        self._event_bus = event_bus
        self._task_registry = task_registry
        self._settings = settings
        self._manager: DownloadManager | None = None

    async def start(self) -> None:
        if self._settings:
            self._manager = DownloadManager(
                output_dir=self._settings.download_dir,
                max_concurrent=self._settings.max_concurrent_downloads,
                enable_resume=self._settings.enable_resume,
                speed_limit=self._settings.speed_limit,
                registry=self._registry,
            )
        else:
            self._manager = DownloadManager(
                output_dir=Path.cwd() / "downloads",
                registry=self._registry,
            )
        await self._manager.start()

    async def close(self) -> None:
        if self._manager:
            await self._manager.close()

    async def download(self, url: str, output_dir: Path, password: str | None = None) -> str:
        self._ensure_started()
        task_id = await self._task_registry.create_task(url, output_dir)
        await self._task_registry.update_task(task_id, status=TaskStatus.EXTRACTING)
        await self._run_download(task_id, url, output_dir, password)
        return task_id

    async def _run_download(
        self,
        task_id: str,
        url: str,
        output_dir: Path,
        password: str | None,
    ) -> None:
        try:
            manager = self._require_manager()
            results = await manager.download_url(
                url, password, output_dir, lambda t: self._handle_progress(task_id, t)
            )
            await self._finalize_download(task_id, results)
        except Exception as e:
            await self._task_registry.update_task(task_id, status=TaskStatus.FAILED, error=str(e))
            self._event_bus.emit(DOWNLOAD_ERROR, {"task_id": task_id, "error": str(e)})
            raise

    async def _finalize_download(self, task_id: str, results: list[DownloadResult]) -> None:
        failed = [r for r in results if not r.success]
        if failed:
            error_msg = "; ".join(r.error or "Unknown" for r in failed)
            await self._task_registry.update_task(
                task_id, status=TaskStatus.FAILED, error=error_msg
            )
        else:
            await self._task_registry.update_task(task_id, status=TaskStatus.COMPLETED)

        for result in results:
            payload = {
                "task_id": task_id,
                "file_task_id": result.task.task_id,
                "filename": result.task.file_info.filename,
            }
            if result.success:
                self._event_bus.emit(DOWNLOAD_COMPLETE, payload)
            else:
                self._event_bus.emit(
                    DOWNLOAD_ERROR,
                    {**payload, "error": result.error or "Download failed"},
                )

    def _handle_progress(self, task_id: str, dl_task: DownloadTask) -> None:
        progress_data = {
            "percentage": dl_task.progress.percentage,
            "downloaded": float(dl_task.progress.downloaded),
            "total": float(dl_task.progress.total),
            "speed": dl_task.progress.speed,
            "eta": dl_task.progress.eta,
            "file_task_id": dl_task.task_id,
            "filename": dl_task.file_info.filename,
            "url": dl_task.file_info.url,
            "status": dl_task.progress.status,
            "error": dl_task.progress.error,
        }

        status = None
        if dl_task.progress.status == DownloadStatus.DOWNLOADING:
            status = TaskStatus.DOWNLOADING

        async def _safe_update() -> None:
            try:
                await self._task_registry.update_task(
                    task_id, status=status, progress=progress_data
                )
            except Exception:
                logger.exception("Failed to update task %s progress", task_id)

        asyncio.create_task(_safe_update())

        if dl_task.progress.status == DownloadStatus.DOWNLOADING:
            self._event_bus.emit(DOWNLOAD_PROGRESS, {"task_id": task_id, "progress": progress_data})

    async def list_files(self, url: str, password: str | None = None) -> list[FileInfo]:
        self._ensure_started()
        manager = self._require_manager()
        return await manager.extract_files(url, password)

    async def get_status(self, task_id: str) -> TaskInfo | None:
        return await self._task_registry.get_task(task_id)

    async def list_active(self) -> list[TaskInfo]:
        return await self._task_registry.list_active()

    async def cancel(self, task_id: str) -> bool:
        """Cancel a download task.

        Note: This marks the task as cancelled in the registry but does not
        immediately stop in-flight HTTP transfers. The download will stop
        at the next progress callback check or chunk boundary.
        """
        task = await self._task_registry.get_task(task_id)
        if not task:
            return False
        await self._task_registry.update_task(task_id, status=TaskStatus.CANCELLED)
        self._event_bus.emit(DOWNLOAD_ERROR, {"task_id": task_id, "error": "Cancelled"})
        return True

    def _ensure_started(self) -> None:
        if not self._manager:
            raise RuntimeError("Service not started")

    def _require_manager(self) -> DownloadManager:
        self._ensure_started()
        assert self._manager is not None
        return self._manager

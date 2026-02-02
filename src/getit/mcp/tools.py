"""MCP tools for managing downloads via getit."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from getit.mcp.server import get_context, mcp


async def _ensure_services_ready() -> None:
    """Ensure TaskRegistry is connected and DownloadService is started."""
    ctx = get_context()

    # Connect TaskRegistry if not already connected
    if ctx.task_registry._db is None:
        await ctx.task_registry.connect()

    # Start DownloadService if not already started
    if ctx.download_service and ctx.download_service._manager is None:
        await ctx.download_service.start()


def _default_output_dir(download_service: object) -> Path:
    settings = getattr(download_service, "_settings", None)
    download_dir = getattr(settings, "download_dir", None) if settings else None
    if isinstance(download_dir, Path):
        return download_dir
    return Path.cwd() / "downloads"


@mcp.tool()
async def download(
    url: str, output_dir: str | None = None, password: str | None = None
) -> dict[str, str]:
    """Start a download task for the given URL.

    Args:
        url: The URL to download from (GoFile, PixelDrain, MediaFire, 1Fichier, Mega.nz)
        output_dir: Optional output directory (defaults to ./downloads)
        password: Optional password for protected content

    Returns:
        Dictionary with task_id of the created download task
    """
    await _ensure_services_ready()

    ctx = get_context()
    if not ctx.download_service:
        raise RuntimeError("DownloadService not initialized")

    output_path = Path(output_dir) if output_dir else _default_output_dir(ctx.download_service)
    task_id = await ctx.download_service.download(url, output_path, password)

    return {"task_id": task_id}


@mcp.tool()
async def list_files(url: str, password: str | None = None) -> dict[str, list[dict[str, Any]]]:
    """List files available at the given URL without downloading.

    Args:
        url: The URL to extract file information from
        password: Optional password for protected content

    Returns:
        Dictionary with "files" key containing list of file information dicts
    """
    await _ensure_services_ready()

    ctx = get_context()
    if not ctx.download_service:
        raise RuntimeError("DownloadService not initialized")

    file_infos = await ctx.download_service.list_files(url, password)

    # Convert FileInfo dataclasses to dicts
    files = []
    for file_info in file_infos:
        files.append(
            {
                "url": file_info.url,
                "filename": file_info.filename,
                "size": file_info.size,
                "direct_url": file_info.direct_url,
                "password_protected": file_info.password_protected,
                "checksum": file_info.checksum,
                "checksum_type": file_info.checksum_type,
                "parent_folder": file_info.parent_folder,
                "extractor_name": file_info.extractor_name,
                "encrypted": file_info.encrypted,
            }
        )

    return {"files": files}


@mcp.tool()
async def get_download_status(task_id: str) -> dict[str, Any]:
    """Get the status of a download task.

    Args:
        task_id: The ID of the task to check

    Returns:
        Dictionary with task status information including status, progress, output_dir,
        created_at, updated_at, and optionally error

    Raises:
        ValueError: If task_id is not found
    """
    await _ensure_services_ready()

    ctx = get_context()
    task_info = await ctx.task_registry.get_task(task_id)

    if task_info is None:
        raise ValueError(f"Task {task_id} not found")

    return {
        "task_id": task_info.task_id,
        "url": task_info.url,
        "status": task_info.status.value,
        "progress": task_info.progress,
        "output_dir": str(task_info.output_dir),
        "created_at": task_info.created_at.isoformat(),
        "updated_at": task_info.updated_at.isoformat(),
        "error": task_info.error,
    }


@mcp.tool()
async def cancel_download(task_id: str) -> dict[str, bool]:
    """Cancel a running download task.

    Args:
        task_id: The ID of the task to cancel

    Returns:
        Dictionary with "success" key indicating if cancellation was successful
    """
    await _ensure_services_ready()

    ctx = get_context()
    if not ctx.download_service:
        raise RuntimeError("DownloadService not initialized")

    success = await ctx.download_service.cancel(task_id)

    return {"success": success}

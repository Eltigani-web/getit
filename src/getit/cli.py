from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table

import getit.extractors  # noqa: F401
from getit import __version__
from getit.config import get_settings
from getit.events import DOWNLOAD_COMPLETE, DOWNLOAD_ERROR, DOWNLOAD_PROGRESS, EventBus
from getit.registry import ExtractorRegistry
from getit.service import DownloadService
from getit.tasks import TaskRegistry
from getit.utils.logging import (
    get_logger,
    set_download_id,
    set_run_id,
    setup_logging,
)

logger = get_logger(__name__)

app = typer.Typer(
    name="getit",
    help="Universal file hosting downloader - supports GoFile, PixelDrain, MediaFire, 1Fichier, Mega.nz",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

console = Console()


def version_callback(value: bool) -> None:
    if value:
        console.print(f"[bold blue]getit[/bold blue] version [green]{__version__}[/green]")
        raise typer.Exit()


def format_size(size_bytes: int) -> str:
    size: float = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def create_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.fields[filename]}", justify="right"),
        BarColumn(bar_width=40),
        "[progress.percentage]{task.percentage:>3.1f}%",
        "•",
        DownloadColumn(),
        "•",
        TransferSpeedColumn(),
        "•",
        TimeRemainingColumn(),
        console=console,
        transient=False,
    )


class ProgressTracker:
    def __init__(self, progress: Progress):
        self.progress = progress
        self.task_ids: dict[str, TaskID] = {}

    def add_task(self, filename: str, total: int, file_task_id: str) -> TaskID:
        task_id = self.progress.add_task(
            "download",
            filename=filename[:40],
            total=total,
            start=True,
        )
        self.task_ids[file_task_id] = task_id
        return task_id

    def update_from_event(self, progress_data: dict) -> None:
        file_task_id = progress_data.get("file_task_id")
        if not file_task_id:
            return

        if file_task_id not in self.task_ids:
            filename = progress_data.get("filename", "unknown")
            total = int(progress_data.get("total", 0))
            self.add_task(filename, total, file_task_id)

        progress_task_id = self.task_ids[file_task_id]

        total = int(progress_data.get("total", 0))
        if total > 0:
            self.progress.update(
                progress_task_id,
                completed=int(progress_data.get("downloaded", 0)),
                total=total,
            )
        else:
            self.progress.update(
                progress_task_id,
                advance=0,
            )


@app.command()
def download(
    urls: Annotated[
        list[str] | None,
        typer.Argument(
            help="URLs to download (supports GoFile, PixelDrain, MediaFire, 1Fichier, Mega.nz)"
        ),
    ] = None,
    file: Annotated[
        Path | None,
        typer.Option("-f", "--file", help="File containing URLs (one per line)"),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("-o", "--output", help="Output directory"),
    ] = None,
    concurrent: Annotated[
        int,
        typer.Option("-c", "--concurrent", help="Max concurrent downloads"),
    ] = 3,
    password: Annotated[
        str | None,
        typer.Option("-p", "--password", help="Password for protected files"),
    ] = None,
    no_resume: Annotated[
        bool,
        typer.Option("--no-resume", help="Disable resume for partial downloads"),
    ] = False,
    limit: Annotated[
        str | None,
        typer.Option("--limit", help="Speed limit (e.g., 1M, 500K)"),
    ] = None,
) -> None:
    all_urls: list[str] = []

    if file:
        if not file.exists():
            console.print(f"[red]File not found:[/red] {file}")
            raise typer.Exit(1)
        with open(file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    url_part = line.split()[0] if line.split() else ""
                    if url_part:
                        all_urls.append(url_part)

    if urls:
        all_urls.extend(urls)

    if not all_urls:
        console.print("[red]No URLs provided. Use positional arguments or -f/--file[/red]")
        raise typer.Exit(1)

    async def run_downloads() -> None:
        with set_run_id():
            logger.info("Starting download session", extra={"url_count": len(all_urls)})

            base_settings = get_settings()
            output_dir_resolved = output or base_settings.download_dir

            speed_limit_bytes = None
            if limit:
                match = re.match(r"(\d+(?:\.\d+)?)\s*([KMG])?", limit, re.I)
                if match:
                    value = float(match.group(1))
                    unit = (match.group(2) or "").upper()
                    multipliers = {"K": 1024, "M": 1024**2, "G": 1024**3, "": 1}
                    speed_limit_bytes = int(value * multipliers.get(unit, 1))

            settings = base_settings.model_copy(deep=True)
            settings.max_concurrent_downloads = concurrent
            settings.enable_resume = not no_resume
            if speed_limit_bytes is not None:
                settings.speed_limit = speed_limit_bytes

            event_bus = EventBus()
            task_registry = TaskRegistry()
            registry = ExtractorRegistry
            service = DownloadService(
                registry=registry,
                event_bus=event_bus,
                task_registry=task_registry,
                settings=settings,
            )

            await task_registry.connect()
            await service.start()

            try:
                extraction_semaphore = asyncio.Semaphore(10)

                async def extract_url(url: str) -> tuple[str, list]:
                    async with extraction_semaphore:
                        extractor_cls = ExtractorRegistry.get_for_url(url)
                        if not extractor_cls:
                            console.print(f"[red]No extractor found for:[/red] {url}")
                            return (url, [])
                        try:
                            files = await service.list_files(url, password)
                            return (url, files)
                        except Exception as e:
                            console.print(f"[red]Error extracting {url}:[/red] {e}")
                            return (url, [])

                with console.status(
                    f"[bold green]Extracting {len(all_urls)} URL(s) in parallel..."
                ):
                    extraction_results = await asyncio.gather(
                        *[extract_url(url) for url in all_urls]
                    )

                file_count = 0
                for _, files in extraction_results:
                    for file_info in files:
                        file_count += 1
                        console.print(
                            f"  [green]✓[/green] {file_info.filename} "
                            f"[dim]({format_size(file_info.size)})[/dim]"
                        )

                if file_count == 0:
                    console.print("[yellow]No files to download[/yellow]")
                    return

                console.print(f"\n[bold]Starting download of {file_count} file(s)...[/bold]\n")

                progress = create_progress()
                tracker = ProgressTracker(progress)

                completed_files: set[str] = set()
                failed_files: set[str] = set()

                def on_progress(data: dict) -> None:
                    progress_data = data.get("progress", {})
                    if progress_data:
                        tracker.update_from_event(progress_data)

                event_bus.subscribe(DOWNLOAD_PROGRESS, on_progress)

                def on_complete(data: dict) -> None:
                    file_task_id = data.get("file_task_id")
                    if file_task_id and file_task_id not in failed_files:
                        completed_files.add(file_task_id)

                def on_error(data: dict) -> None:
                    file_task_id = data.get("file_task_id")
                    if file_task_id and file_task_id not in completed_files:
                        failed_files.add(file_task_id)

                event_bus.subscribe(DOWNLOAD_COMPLETE, on_complete)
                event_bus.subscribe(DOWNLOAD_ERROR, on_error)

                with progress:
                    download_tasks = []
                    for url, files in extraction_results:
                        if files:

                            async def download_with_logging(url: str) -> str:
                                with set_download_id(url[:50]):
                                    logger.info("Starting download: %s", url)
                                    return await service.download(
                                        url, output_dir_resolved, password
                                    )

                            download_tasks.append(download_with_logging(url))

                    results = await asyncio.gather(*download_tasks, return_exceptions=True)

                exception_failures = sum(1 for r in results if isinstance(r, Exception))
                success_count = len(completed_files)
                fail_count = len(failed_files) + exception_failures

                logger.info(
                    "Download session completed: %d succeeded, %d failed", success_count, fail_count
                )
            finally:
                await service.close()
                await task_registry.close()

    asyncio.run(run_downloads())


@app.command()
def info(
    url: Annotated[str, typer.Argument(help="URL to get information about")],
    password: Annotated[
        str | None,
        typer.Option("-p", "--password", help="Password for protected files"),
    ] = None,
) -> None:
    async def get_info() -> None:
        settings = get_settings()
        event_bus = EventBus()
        task_registry = TaskRegistry()
        registry = ExtractorRegistry
        service = DownloadService(
            registry=registry,
            event_bus=event_bus,
            task_registry=task_registry,
            settings=settings,
        )

        await task_registry.connect()
        await service.start()

        try:
            extractor_cls = ExtractorRegistry.get_for_url(url)
            if not extractor_cls:
                console.print(f"[red]No extractor found for:[/red] {url}")
                return

            console.print(f"[bold]Extractor:[/bold] {extractor_cls.EXTRACTOR_NAME}")

            try:
                files = await service.list_files(url, password)

                table = Table(title=f"Files ({len(files)})")
                table.add_column("Filename", style="cyan")
                table.add_column("Size", justify="right", style="green")
                table.add_column("Folder", style="dim")

                total_size = 0
                for f in files:
                    table.add_row(
                        f.filename,
                        format_size(f.size),
                        f.parent_folder or "-",
                    )
                    total_size += f.size

                console.print(table)
                console.print(f"\n[bold]Total:[/bold] {format_size(total_size)}")

            except Exception as e:
                console.print(f"[red]Error:[/red] {e}")
        finally:
            await service.close()
            await task_registry.close()

    asyncio.run(get_info())


@app.command()
def tui() -> None:
    try:
        from getit.tui.app import GetItApp

        app = GetItApp()
        app.run()
    except ImportError as e:
        console.print(f"[red]TUI dependencies not available:[/red] {e}")
        console.print("Install with: pip install getit[tui]")
        raise typer.Exit(1) from None


@app.command()
def config(
    show: Annotated[
        bool,
        typer.Option("--show", help="Show current configuration"),
    ] = False,
    reset: Annotated[
        bool,
        typer.Option("--reset", help="Reset to default configuration"),
    ] = False,
) -> None:
    settings = get_settings()

    if show or (not show and not reset):
        table = Table(title="Current Configuration")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Download Directory", str(settings.download_dir))
        table.add_row("Max Concurrent Downloads", str(settings.max_concurrent_downloads))
        table.add_row("Chunk Size", format_size(settings.chunk_size))
        table.add_row("Max Retries", str(settings.max_retries))
        table.add_row("Resume Enabled", str(settings.enable_resume))
        table.add_row(
            "Speed Limit",
            format_size(settings.speed_limit) if settings.speed_limit else "Unlimited",
        )
        table.add_row("Config Directory", str(settings.config_dir))

        console.print(table)


@app.command()
def supported() -> None:
    table = Table(title="Supported File Hosts")
    table.add_column("Host", style="cyan")
    table.add_column("Domains", style="green")
    table.add_column("Features", style="dim")

    table.add_row(
        "GoFile",
        "gofile.io",
        "Folders, Password Protection",
    )
    table.add_row(
        "PixelDrain",
        "pixeldrain.com, pixeldrain.net",
        "Files, Lists, API Key",
    )
    table.add_row(
        "MediaFire",
        "mediafire.com",
        "Files, Folders",
    )
    table.add_row(
        "1Fichier",
        "1fichier.com + 8 mirrors",
        "Password Protection, Wait Times",
    )
    table.add_row(
        "Mega.nz",
        "mega.nz, mega.co.nz, mega.io",
        "Files, Folders, Encryption",
    )

    console.print(table)


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", "-V", callback=version_callback, is_eager=True),
    ] = None,
) -> None:
    setup_logging()


if __name__ == "__main__":
    app()

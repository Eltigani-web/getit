from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
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
from rich.text import Text

from getit import __version__
from getit.config import Settings, get_settings
from getit.core.downloader import DownloadStatus, DownloadTask
from getit.core.manager import DownloadManager

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


def format_size(size: int) -> str:
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

    def add_task(self, task: DownloadTask) -> TaskID:
        task_id = self.progress.add_task(
            "download",
            filename=task.file_info.filename[:40],
            total=task.progress.total or 0,
            start=True,
        )
        self.task_ids[task.task_id] = task_id
        return task_id

    def update(self, task: DownloadTask) -> None:
        if task.task_id not in self.task_ids:
            self.add_task(task)

        progress_task_id = self.task_ids[task.task_id]

        if task.progress.total > 0:
            self.progress.update(
                progress_task_id,
                completed=task.progress.downloaded,
                total=task.progress.total,
            )
        else:
            self.progress.update(
                progress_task_id,
                advance=0,
            )


@app.command()
def download(
    urls: Annotated[
        list[str],
        typer.Argument(
            help="URLs to download (supports GoFile, PixelDrain, MediaFire, 1Fichier, Mega.nz)"
        ),
    ],
    output: Annotated[
        Optional[Path],
        typer.Option("-o", "--output", help="Output directory"),
    ] = None,
    concurrent: Annotated[
        int,
        typer.Option("-c", "--concurrent", help="Max concurrent downloads"),
    ] = 3,
    password: Annotated[
        Optional[str],
        typer.Option("-p", "--password", help="Password for protected files"),
    ] = None,
    no_resume: Annotated[
        bool,
        typer.Option("--no-resume", help="Disable resume for partial downloads"),
    ] = False,
    limit: Annotated[
        Optional[str],
        typer.Option("--limit", help="Speed limit (e.g., 1M, 500K)"),
    ] = None,
) -> None:
    settings = get_settings()
    output_dir = output or settings.download_dir

    speed_limit = None
    if limit:
        match = re.match(r"(\d+(?:\.\d+)?)\s*([KMG])?", limit, re.I)
        if match:
            value = float(match.group(1))
            unit = (match.group(2) or "").upper()
            multipliers = {"K": 1024, "M": 1024**2, "G": 1024**3, "": 1}
            speed_limit = int(value * multipliers.get(unit, 1))

    async def run_downloads() -> None:
        async with DownloadManager(
            output_dir=output_dir,
            max_concurrent=concurrent,
            enable_resume=not no_resume,
            speed_limit=speed_limit,
        ) as manager:
            all_tasks: list[DownloadTask] = []

            with console.status("[bold green]Extracting file information...") as status:
                for url in urls:
                    try:
                        extractor = manager.get_extractor(url)
                        if not extractor:
                            console.print(f"[red]No extractor found for:[/red] {url}")
                            continue

                        status.update(f"[bold green]Extracting from {extractor.EXTRACTOR_NAME}...")
                        files = await manager.extract_files(url, password)

                        for file_info in files:
                            task = manager.create_task(file_info)
                            all_tasks.append(task)
                            console.print(
                                f"  [green]✓[/green] {file_info.filename} "
                                f"[dim]({format_size(file_info.size)})[/dim]"
                            )

                    except Exception as e:
                        console.print(f"[red]Error extracting {url}:[/red] {e}")

            if not all_tasks:
                console.print("[yellow]No files to download[/yellow]")
                return

            console.print(f"\n[bold]Starting download of {len(all_tasks)} file(s)...[/bold]\n")

            progress = create_progress()
            tracker = ProgressTracker(progress)

            for task in all_tasks:
                tracker.add_task(task)

            with progress:
                download_coros = [
                    manager.download_task(task, on_progress=tracker.update) for task in all_tasks
                ]

                results = await asyncio.gather(*download_coros)

            console.print()

            success_count = sum(1 for r in results if r.success)
            fail_count = len(results) - success_count

            if success_count > 0:
                console.print(f"[green]✓ {success_count} file(s) downloaded successfully[/green]")

            if fail_count > 0:
                console.print(f"[red]✗ {fail_count} file(s) failed[/red]")
                for result in results:
                    if not result.success:
                        console.print(
                            f"  [red]•[/red] {result.task.file_info.filename}: {result.error}"
                        )

    asyncio.run(run_downloads())


@app.command()
def info(
    url: Annotated[str, typer.Argument(help="URL to get information about")],
    password: Annotated[
        Optional[str],
        typer.Option("-p", "--password", help="Password for protected files"),
    ] = None,
) -> None:
    async def get_info() -> None:
        async with DownloadManager(
            output_dir=Path.cwd(),
        ) as manager:
            extractor = manager.get_extractor(url)
            if not extractor:
                console.print(f"[red]No extractor found for:[/red] {url}")
                return

            console.print(f"[bold]Extractor:[/bold] {extractor.EXTRACTOR_NAME}")

            try:
                files = await manager.extract_files(url, password)

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
        raise typer.Exit(1)


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
        Optional[bool],
        typer.Option("--version", "-V", callback=version_callback, is_eager=True),
    ] = None,
) -> None:
    pass


if __name__ == "__main__":
    app()

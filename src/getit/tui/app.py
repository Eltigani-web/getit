from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Static,
    Switch,
    TextArea,
)

from getit.config import get_settings, save_config
from getit.core.downloader import DownloadStatus, DownloadTask
from getit.core.manager import DownloadManager


def _count_tasks_by_status(tasks: dict[str, DownloadTask]) -> tuple[int, int, int, int, float]:
    total = len(tasks)
    active = 0
    completed = 0
    failed = 0
    total_speed = 0.0

    for task in tasks.values():
        status = task.progress.status
        if status == DownloadStatus.DOWNLOADING:
            active += 1
        elif status == DownloadStatus.COMPLETED:
            completed += 1
        elif status == DownloadStatus.FAILED:
            failed += 1
        total_speed += task.progress.speed

    return total, active, completed, failed, total_speed


def _supports_unicode() -> bool:
    if os.environ.get("GETIT_ASCII_ONLY", "").lower() in ("1", "true", "yes"):
        return False

    term = os.environ.get("TERM", "").lower()
    if term in ("dumb", "unknown", ""):
        return False

    lang = os.environ.get("LANG", "").lower()
    lc_all = os.environ.get("LC_ALL", "").lower()
    if "utf" in lang or "utf" in lc_all:
        return True

    if sys.platform == "darwin":
        return True

    if "xterm" in term or "256color" in term or "kitty" in term or "alacritty" in term:
        return True

    try:
        "█".encode(sys.stdout.encoding or "utf-8")
        return True
    except (UnicodeEncodeError, LookupError):
        return False


UNICODE_SUPPORT = _supports_unicode()

PROGRESS_FILLED = "█" if UNICODE_SUPPORT else "#"
PROGRESS_EMPTY = "░" if UNICODE_SUPPORT else "-"

MODAL_BASE_CSS = """
    align: center middle;

    .modal-dialog {
        width: auto;
        height: auto;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }

    .modal-dialog Label {
        margin-bottom: 1;
    }

    .modal-dialog Input {
        margin-bottom: 1;
    }

    .modal-buttons {
        width: 100%;
        height: auto;
        margin-top: 1;
    }

    .modal-buttons Button {
        margin-right: 1;
    }
"""


def format_size(size_bytes: int) -> str:
    size: float = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def format_speed(speed: float) -> str:
    return f"{format_size(int(speed))}/s"


def format_eta(seconds: float) -> str:
    if seconds <= 0:
        return "--:--"
    if seconds >= 3600:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"


class BatchFileScreen(ModalScreen[tuple[str, str | None, str | None] | None]):
    CSS = """
    BatchFileScreen {
        align: center middle;
    }

    #batch-dialog {
        width: 70;
        height: auto;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }

    #batch-dialog Label {
        margin-bottom: 1;
    }

    #batch-dialog Input {
        margin-bottom: 1;
    }

    #batch-dialog Static {
        margin-bottom: 1;
        color: $text-muted;
    }

    .folder-row {
        height: auto;
        margin-bottom: 1;
        align: left middle;
    }

    .folder-row Label {
        margin-left: 1;
        margin-bottom: 0;
    }

    #batch-buttons {
        width: 100%;
        height: auto;
        margin-top: 1;
    }

    #batch-buttons Button {
        margin-right: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="batch-dialog"):
            yield Label("Import URLs from File")
            yield Static("Enter path to a text file with one URL per line:")
            yield Input(
                placeholder="e.g., ~/Downloads/urls.txt",
                id="file-path-input",
            )
            yield Input(
                placeholder="Password for all files (optional)",
                id="batch-password-input",
                password=True,
            )
            with Horizontal(classes="folder-row"):
                yield Switch(value=False, id="custom-folder-switch")
                yield Label("Create custom folder for batch")
            yield Input(
                placeholder="Folder name (e.g., 'my-downloads')",
                id="custom-folder-input",
                disabled=True,
            )
            with Horizontal(id="batch-buttons"):
                yield Button("Import", variant="primary", id="import-btn")
                yield Button("Cancel", id="batch-cancel-btn")

    @on(Switch.Changed, "#custom-folder-switch")
    def on_switch_changed(self, event: Switch.Changed) -> None:
        folder_input = self.query_one("#custom-folder-input", Input)
        folder_input.disabled = not event.value
        if not event.value:
            folder_input.value = ""

    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#batch-cancel-btn")
    def on_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#import-btn")
    def on_import(self) -> None:
        file_input = self.query_one("#file-path-input", Input)
        password_input = self.query_one("#batch-password-input", Input)
        file_path = file_input.value.strip()
        password = password_input.value.strip() or None

        custom_folder: str | None = None
        switch = self.query_one("#custom-folder-switch", Switch)
        if switch.value:
            folder_input = self.query_one("#custom-folder-input", Input)
            folder_name = folder_input.value.strip()
            if folder_name:
                custom_folder = folder_name

        if file_path:
            expanded_path = Path(file_path).expanduser().resolve()
            self.dismiss((str(expanded_path), password, custom_folder))
        else:
            self.dismiss(None)

    @on(Input.Submitted, "#file-path-input")
    def on_path_submitted(self) -> None:
        self.on_import()


class AddUrlScreen(ModalScreen[tuple[list[str], str | None, str | None] | None]):
    """Screen for adding one or more URLs with optional folder grouping."""

    CSS = """
    AddUrlScreen {
        align: center middle;
    }

    #dialog {
        width: 70;
        height: auto;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }

    #dialog Label {
        margin-bottom: 1;
    }

    #dialog Input {
        margin-bottom: 1;
    }

    #url-area {
        height: 8;
        margin-bottom: 1;
    }

    #buttons {
        width: 100%;
        height: auto;
        margin-top: 1;
    }

    #buttons Button {
        margin-right: 1;
    }

    .hint {
        color: $text-muted;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="dialog"):
            yield Label("Add Download URLs")
            yield Static("Enter URLs (one per line)", classes="hint")
            yield TextArea(id="url-area")
            yield Input(
                placeholder="Password (optional, applies to all)",
                id="password_input",
                password=True,
            )
            yield Input(placeholder="Folder name (optional, groups downloads)", id="folder_input")
            with Horizontal(id="buttons"):
                yield Button("Add", variant="primary", id="add_btn")
                yield Button("Cancel", id="cancel_btn")

    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#cancel_btn")
    def on_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#add_btn")
    def on_add(self) -> None:
        url_area = self.query_one("#url-area", TextArea)
        password_input = self.query_one("#password_input", Input)
        folder_input = self.query_one("#folder_input", Input)

        text = url_area.text.strip()
        password = password_input.value.strip() or None
        folder = folder_input.value.strip() or None

        urls = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#") and line.strip().startswith("http")
        ]

        if urls:
            self.dismiss((urls, password, folder))
        else:
            self.app.notify("No valid URLs entered", severity="warning")


class ErrorDetailsScreen(ModalScreen[None]):
    CSS = """
    ErrorDetailsScreen {
        align: center middle;
    }

    #error-dialog {
        width: 70;
        height: auto;
        max-height: 20;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }

    #error-dialog Label {
        margin-bottom: 1;
    }

    #error-message {
        margin-bottom: 1;
        color: $error;
    }

    #error-buttons {
        width: 100%;
        height: auto;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
    ]

    def __init__(self, download_task: DownloadTask):
        super().__init__()
        self.download_task = download_task

    def compose(self) -> ComposeResult:
        with Container(id="error-dialog"):
            yield Label(f"Error Details: {self.download_task.file_info.filename[:40]}")
            yield Static(
                self.download_task.progress.error or "Unknown error",
                id="error-message",
            )
            yield Static(f"Retries: {self.download_task.retries}/{self.download_task.max_retries}")
            with Horizontal(id="error-buttons"):
                yield Button("Retry", variant="primary", id="retry-btn")
                yield Button("Close", id="close-btn")

    def action_close(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#close-btn")
    def on_close(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#retry-btn")
    def on_retry(self) -> None:
        self.download_task.progress.status = DownloadStatus.PENDING
        self.download_task.progress.error = None
        self.download_task.retries = 0
        self.app.call_later(self._trigger_retry)
        self.dismiss(None)

    def _trigger_retry(self) -> None:
        if hasattr(self.app, "_start_download"):
            self.app._start_download(self.download_task)


class SettingsScreen(ModalScreen[None]):
    CSS = """
    SettingsScreen {
        align: center middle;
    }

    #settings-dialog {
        width: 65;
        height: auto;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }

    #settings-dialog Label {
        margin-bottom: 1;
    }

    #settings-dialog Input {
        margin-bottom: 1;
    }

    .setting-row {
        height: auto;
        margin-bottom: 1;
    }

    .setting-label {
        width: 25;
    }

    #settings-buttons {
        width: 100%;
        height: auto;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
    ]

    def __init__(self, settings):
        super().__init__()
        self.settings = settings

    def compose(self) -> ComposeResult:
        with Container(id="settings-dialog"):
            yield Label("Settings", id="settings-title")

            with Horizontal(classes="setting-row"):
                yield Label("Download Directory:", classes="setting-label")
                yield Input(
                    value=str(self.settings.download_dir),
                    id="download-dir-input",
                )

            with Horizontal(classes="setting-row"):
                yield Label("Max Concurrent:", classes="setting-label")
                yield Input(
                    value=str(self.settings.max_concurrent_downloads),
                    id="max-concurrent-input",
                )

            with Horizontal(classes="setting-row"):
                yield Label("Speed Limit (0=unlimited):", classes="setting-label")
                yield Input(
                    value=str(self.settings.speed_limit or 0),
                    id="speed-limit-input",
                )

            with Horizontal(id="settings-buttons"):
                yield Button("Save", variant="primary", id="save-btn")
                yield Button("Cancel", id="cancel-settings-btn")

    def action_close(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#cancel-settings-btn")
    def on_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#save-btn")
    def on_save(self) -> None:
        try:
            download_dir_str = self.query_one("#download-dir-input", Input).value.strip()
            max_concurrent = int(self.query_one("#max-concurrent-input", Input).value)
            speed_limit = int(self.query_one("#speed-limit-input", Input).value)

            download_path = Path(download_dir_str).expanduser().resolve()
            try:
                download_path.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                self.app.notify(f"Invalid directory: {e}", severity="error")
                return

            self.settings.download_dir = download_path
            self.settings.max_concurrent_downloads = max(1, min(10, max_concurrent))
            self.settings.speed_limit = speed_limit if speed_limit > 0 else None

            save_config(self.settings)

            self.app.notify("Settings saved", severity="information")
            self.dismiss(None)
        except ValueError:
            self.app.notify("Invalid input values", severity="error")


class StatusBar(Static):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.total_downloads = 0
        self.active_downloads = 0
        self.completed_downloads = 0
        self.failed_downloads = 0
        self.total_speed = 0.0

    def update_status(
        self,
        total: int = 0,
        active: int = 0,
        completed: int = 0,
        failed: int = 0,
        speed: float = 0.0,
    ) -> None:
        self.total_downloads = total
        self.active_downloads = active
        self.completed_downloads = completed
        self.failed_downloads = failed
        self.total_speed = speed
        self.refresh()

    def render(self) -> Text:
        text = Text()
        text.append(f" Downloads: {self.total_downloads} ", style="bold")
        text.append("| ", style="dim")
        text.append(f"Active: {self.active_downloads} ", style="cyan")
        text.append("| ", style="dim")
        text.append(f"Completed: {self.completed_downloads} ", style="green")
        if self.failed_downloads > 0:
            text.append("| ", style="dim")
            text.append(f"Failed: {self.failed_downloads} ", style="red")
        text.append("| ", style="dim")
        text.append(f"Speed: {format_speed(self.total_speed)}", style="yellow")
        return text


class GetItApp(App):
    CSS = """
    Screen {
        background: $surface;
    }

    #main-container {
        height: 100%;
        padding: 1;
    }

    #controls {
        dock: top;
        height: 3;
        padding: 0 1;
        background: $panel;
    }

    #controls Button {
        margin-right: 1;
    }

    #downloads-table {
        height: 1fr;
        border: solid $primary;
    }

    #status-bar {
        dock: bottom;
        height: 1;
        background: $panel;
        padding: 0 1;
    }

    .progress-cell {
        width: 100%;
    }
    """

    TITLE = "getit - Universal File Downloader"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("a", "add_url", "Add URL"),
        Binding("b", "batch_import", "Batch Import"),
        Binding("r", "refresh", "Refresh"),
        Binding("c", "cancel_selected", "Cancel"),
        Binding("p", "pause_resume_selected", "Pause/Resume"),
        Binding("e", "view_error", "View Error"),
        Binding("space", "retry_selected", "Retry"),
        Binding("s", "open_settings", "Settings"),
    ]

    STATUS_STYLES: dict[DownloadStatus, tuple[str, str]] = {
        DownloadStatus.PENDING: ("dim", "Pending"),
        DownloadStatus.DOWNLOADING: ("cyan", "Downloading"),
        DownloadStatus.PAUSED: ("yellow", "Paused"),
        DownloadStatus.COMPLETED: ("green", "Completed"),
        DownloadStatus.FAILED: ("red", "Failed"),
        DownloadStatus.CANCELLED: ("red", "Cancelled"),
        DownloadStatus.VERIFYING: ("magenta", "Verifying"),
    }

    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self.manager: DownloadManager | None = None
        self.tasks: dict[str, DownloadTask] = {}
        self._update_timer: asyncio.Task | None = None
        self._term_width: int = 100
        self._datatable_column_keys: dict[str, object] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main-container"):
            with Horizontal(id="controls"):
                yield Button("Add URL", id="add-btn", variant="primary")
                yield Button("Batch Import", id="batch-btn", variant="primary")
                yield Button("Start All", id="start-btn", variant="success")
                yield Button("Cancel All", id="cancel-btn", variant="error")
                yield Button("Clear Completed", id="clear-btn")
            yield DataTable(id="downloads-table")
        yield StatusBar(id="status-bar")
        yield Footer()

    async def on_mount(self) -> None:
        table = self.query_one("#downloads-table", DataTable)

        term_size = shutil.get_terminal_size(fallback=(100, 24))
        self._term_width = term_size.columns
        term_height = term_size.lines

        if self._term_width < 80 or term_height < 20:
            self.notify(
                f"Terminal size {self._term_width}x{term_height} is small. Recommended: 100x24+",
                severity="warning",
                timeout=5,
            )

        if self._term_width >= 120:
            self._datatable_column_keys["Filename"] = table.add_column("Filename", width=40)
            self._datatable_column_keys["Size"] = table.add_column("Size", width=12)
            self._datatable_column_keys["Progress"] = table.add_column("Progress", width=22)
            self._datatable_column_keys["Speed"] = table.add_column("Speed", width=12)
            self._datatable_column_keys["ETA"] = table.add_column("ETA", width=10)
            self._datatable_column_keys["Status"] = table.add_column("Status", width=12)
        elif self._term_width >= 100:
            self._datatable_column_keys["Filename"] = table.add_column("Filename", width=35)
            self._datatable_column_keys["Size"] = table.add_column("Size", width=12)
            self._datatable_column_keys["Progress"] = table.add_column("Progress", width=20)
            self._datatable_column_keys["Speed"] = table.add_column("Speed", width=12)
            self._datatable_column_keys["ETA"] = table.add_column("ETA", width=10)
            self._datatable_column_keys["Status"] = table.add_column("Status", width=12)
        elif self._term_width >= 80:
            self._datatable_column_keys["Filename"] = table.add_column("Filename", width=25)
            self._datatable_column_keys["Size"] = table.add_column("Size", width=10)
            self._datatable_column_keys["Progress"] = table.add_column("Progress", width=18)
            self._datatable_column_keys["Speed"] = table.add_column("Speed", width=10)
            self._datatable_column_keys["Status"] = table.add_column("Status", width=10)
        else:
            self._datatable_column_keys["File"] = table.add_column("File", width=20)
            self._datatable_column_keys["Progress"] = table.add_column("Progress", width=15)
            self._datatable_column_keys["Status"] = table.add_column("Status", width=10)

        table.cursor_type = "row"

        self.manager = DownloadManager(
            output_dir=self.settings.download_dir,
            max_concurrent=self.settings.max_concurrent_downloads,
            enable_resume=self.settings.enable_resume,
        )
        await self.manager.start()

        self._start_status_updates()

    async def on_unmount(self) -> None:
        if self._update_timer:
            self._update_timer.cancel()
        self.workers.cancel_all()
        if self.manager:
            await self.manager.close()

    def _start_status_updates(self) -> None:
        self._update_timer = asyncio.create_task(self._update_loop())

    async def _update_loop(self) -> None:
        while True:
            await asyncio.sleep(0.5)
            self._update_table()
            self._update_status_bar()

    def _update_table(self) -> None:
        table = self.query_one("#downloads-table", DataTable)

        for task_id, task in self.tasks.items():
            progress = task.progress

            progress_pct = f"{progress.percentage:5.1f}%"
            progress_bar = self._create_progress_bar(progress.percentage)

            speed = format_speed(progress.speed) if progress.speed > 0 else "-"
            eta = format_eta(progress.eta) if progress.eta > 0 else "-"

            style, status_text = self.STATUS_STYLES.get(progress.status, ("dim", "Unknown"))

            try:
                progress_key = self._datatable_column_keys.get("Progress")
                status_key = self._datatable_column_keys.get("Status")
                speed_key = self._datatable_column_keys.get("Speed")
                eta_key = self._datatable_column_keys.get("ETA")

                if progress_key:
                    table.update_cell(task_id, progress_key, f"{progress_bar} {progress_pct}")  # type: ignore[arg-type]  # Textual DataTable stubs incomplete
                if status_key:
                    table.update_cell(task_id, status_key, Text(status_text, style=style))  # type: ignore[arg-type]  # Textual DataTable stubs incomplete
                if self._term_width >= 80 and speed_key:
                    table.update_cell(task_id, speed_key, speed)  # type: ignore[arg-type]  # Textual DataTable stubs incomplete
                if self._term_width >= 100 and eta_key:
                    table.update_cell(task_id, eta_key, eta)  # type: ignore[arg-type]  # Textual DataTable stubs incomplete
            except Exception:
                pass

    def _create_progress_bar(self, percentage: float) -> str:
        width = 10
        filled = int(width * percentage / 100)
        empty = width - filled
        return f"[{PROGRESS_FILLED * filled}{PROGRESS_EMPTY * empty}]"

    def _update_status_bar(self) -> None:
        status_bar = self.query_one("#status-bar", StatusBar)
        total, active, completed, failed, total_speed = _count_tasks_by_status(self.tasks)
        status_bar.update_status(total, active, completed, failed, total_speed)

    def action_refresh(self) -> None:
        self._update_table()
        self._update_status_bar()
        self.notify("Refreshed", timeout=1)

    @work
    async def action_add_url(self) -> None:
        result = await self.push_screen_wait(AddUrlScreen())
        if result:
            urls, password, custom_folder = result
            await self._add_urls(urls, password, custom_folder)

    @work(exclusive=False)
    async def _add_urls(
        self,
        urls: list[str],
        password: str | None = None,
        custom_folder: str | None = None,
    ) -> None:
        batch_output_dir = self._create_batch_folder(custom_folder)
        if custom_folder and batch_output_dir is None:
            return

        if len(urls) > 1:
            self.notify(f"Adding {len(urls)} URL(s)...")

        success_count = 0
        for url in urls:
            try:
                await self._add_download(url, password, batch_output_dir)  # type: ignore[misc]
                success_count += 1
            except Exception:
                pass

        if len(urls) > 1:
            self.notify(
                f"Added {success_count}/{len(urls)} URL(s)",
                severity="information" if success_count > 0 else "warning",
            )

    @on(Button.Pressed, "#add-btn")
    async def on_add_button(self) -> None:
        self.action_add_url()

    @on(Button.Pressed, "#batch-btn")
    async def on_batch_button(self) -> None:
        self.action_batch_import()

    @work
    async def action_batch_import(self) -> None:
        result = await self.push_screen_wait(BatchFileScreen())
        if result:
            file_path, password, custom_folder = result
            self._import_from_file(file_path, password, custom_folder)

    def _get_unique_folder(self, base_folder: Path) -> Path:
        if not base_folder.exists():
            return base_folder

        counter = 1
        while True:
            candidate = base_folder.parent / f"{base_folder.name}_{counter}"
            if not candidate.exists():
                return candidate
            counter += 1

    @work(exclusive=False)
    async def _import_from_file(
        self,
        file_path: str,
        password: str | None = None,
        custom_folder: str | None = None,
    ) -> None:
        try:
            urls = self._parse_url_file(file_path)
            if urls is None:
                return

            batch_output_dir = self._create_batch_folder(custom_folder)
            if custom_folder and batch_output_dir is None:
                return

            self.notify(f"Importing {len(urls)} URL(s)...")

            success_count = 0
            for url in urls:
                try:
                    await self._add_download(  # type: ignore[misc]  # Textual Worker
                        url, password, batch_output_dir
                    )
                    success_count += 1
                except Exception:
                    pass

            self.notify(
                f"Imported {success_count}/{len(urls)} URL(s)",
                severity="information" if success_count > 0 else "warning",
            )

        except Exception as e:
            self.notify(f"Error reading file: {e}", severity="error")

    def _parse_url_file(self, file_path: str) -> list[str] | None:
        path = Path(file_path)
        if not path.exists():
            self.notify(f"File not found: {file_path}", severity="error")
            return None

        if not path.is_file():
            self.notify(f"Not a file: {file_path}", severity="error")
            return None

        with open(path, encoding="utf-8") as f:
            lines = f.readlines()

        urls = [
            line.strip()
            for line in lines
            if line.strip() and not line.strip().startswith("#") and line.strip().startswith("http")
        ]

        if not urls:
            self.notify("No valid URLs found in file", severity="warning")
            return None

        return urls

    def _create_batch_folder(self, custom_folder: str | None) -> Path | None:
        if not custom_folder:
            return None

        base_folder = self.settings.download_dir / custom_folder
        batch_output_dir = self._get_unique_folder(base_folder)
        try:
            batch_output_dir.mkdir(parents=True, exist_ok=True)
            self.notify(f"Saving to: {batch_output_dir.name}")
            return batch_output_dir
        except OSError as e:
            self.notify(f"Failed to create folder: {e}", severity="error")
            return None

    @on(Button.Pressed, "#start-btn")
    async def on_start_all(self) -> None:
        pending_tasks = [
            t for t in self.tasks.values() if t.progress.status == DownloadStatus.PENDING
        ]
        if pending_tasks:
            for task in pending_tasks:
                self._start_download(task)
            self.notify(f"Started {len(pending_tasks)} download(s)")
        else:
            self.notify("No pending downloads to start", severity="warning")

    @on(Button.Pressed, "#cancel-btn")
    async def on_cancel_all(self) -> None:
        cancellable_statuses = (
            DownloadStatus.DOWNLOADING,
            DownloadStatus.PENDING,
            DownloadStatus.PAUSED,
        )
        cancelled_count = 0
        for task in self.tasks.values():
            if task.progress.status in cancellable_statuses:
                task.progress.status = DownloadStatus.CANCELLED
                cancelled_count += 1
        if cancelled_count > 0:
            self.notify(f"Cancelled {cancelled_count} download(s)")
        else:
            self.notify("No active downloads to cancel", severity="warning")

    @on(Button.Pressed, "#clear-btn")
    def on_clear_completed(self) -> None:
        table = self.query_one("#downloads-table", DataTable)
        completed_ids = [
            tid
            for tid, t in self.tasks.items()
            if t.progress.status
            in (DownloadStatus.COMPLETED, DownloadStatus.CANCELLED, DownloadStatus.FAILED)
        ]
        for tid in completed_ids:
            try:
                table.remove_row(tid)
                del self.tasks[tid]
            except Exception:
                pass

    @work(exclusive=False)
    async def _add_download(
        self,
        url: str,
        password: str | None = None,
        output_dir: Path | None = None,
    ) -> None:
        if not self.manager:
            return

        try:
            extractor = self.manager.get_extractor(url)
            if not extractor:
                self.notify(f"No extractor for: {url}", severity="error")
                return

            self.notify(f"Extracting from {extractor.EXTRACTOR_NAME}...")
            files = await self.manager.extract_files(url, password)

            table = self.query_one("#downloads-table", DataTable)

            for file_info in files:
                task = self.manager.create_task(file_info, output_dir)
                self.tasks[task.task_id] = task

                initial_bar = f"[{PROGRESS_EMPTY * 10}]   0.0%"
                row_data, row_key = self._get_table_row_for_task(task, initial_bar)
                table.add_row(*row_data, key=row_key)

                self._start_download(task)

            self.notify(f"Added {len(files)} file(s)", severity="information")

        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    @work(exclusive=False)
    async def _start_download(self, task: DownloadTask) -> None:
        if not self.manager:
            return

        def on_progress(t: DownloadTask) -> None:
            pass

        result = await self.manager.download_task(task, on_progress)

        if result.success:
            self.notify(f"Completed: {task.file_info.filename}", severity="information")
        else:
            self.notify(f"Failed: {task.file_info.filename}", severity="error")

    def _get_selected_task(self) -> DownloadTask | None:
        table = self.query_one("#downloads-table", DataTable)
        if table.cursor_row is None:
            return None
        try:
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
            task_id = str(row_key.value)
            return self.tasks.get(task_id)
        except Exception:
            return None

    def _get_table_row_for_task(self, task: DownloadTask, initial_bar: str) -> tuple[tuple, str]:
        filename_width = 32 if self._term_width >= 100 else 20
        truncated_name = task.file_info.filename[:filename_width]
        if len(task.file_info.filename) > filename_width:
            truncated_name += "..."

        pending_status = Text("Pending", style="dim")

        if self._term_width >= 100:
            return (
                (
                    truncated_name,
                    format_size(task.file_info.size),
                    initial_bar,
                    "-",
                    "-",
                    pending_status,
                ),
                task.task_id,
            )
        elif self._term_width >= 80:
            return (
                (
                    truncated_name,
                    format_size(task.file_info.size),
                    initial_bar,
                    "-",
                    pending_status,
                ),
                task.task_id,
            )
        else:
            return (
                (truncated_name, initial_bar, pending_status),
                task.task_id,
            )

    def action_cancel_selected(self) -> None:
        task = self._get_selected_task()
        if task and task.progress.status in (
            DownloadStatus.DOWNLOADING,
            DownloadStatus.PENDING,
            DownloadStatus.PAUSED,
        ):
            task.progress.status = DownloadStatus.CANCELLED
            self.notify(f"Cancelled: {task.file_info.filename[:30]}")

    def action_pause_resume_selected(self) -> None:
        task = self._get_selected_task()
        if not task:
            return

        if task.progress.status == DownloadStatus.DOWNLOADING:
            task.progress.status = DownloadStatus.PAUSED
            self.notify(f"Paused: {task.file_info.filename[:30]}")
        elif task.progress.status == DownloadStatus.PAUSED:
            task.progress.status = DownloadStatus.DOWNLOADING
            self.notify(f"Resumed: {task.file_info.filename[:30]}")

    async def action_view_error(self) -> None:
        task = self._get_selected_task()
        if not task:
            return

        if task.progress.status == DownloadStatus.FAILED:
            await self.push_screen(ErrorDetailsScreen(task))
        else:
            self.notify("No error for this download", severity="warning")

    def action_retry_selected(self) -> None:
        task = self._get_selected_task()
        if not task:
            return

        if task.progress.status in (DownloadStatus.FAILED, DownloadStatus.CANCELLED):
            task.progress.status = DownloadStatus.PENDING
            task.progress.error = None
            task.retries = 0
            self._start_download(task)
            self.notify(f"Retrying: {task.file_info.filename[:30]}")

    async def action_open_settings(self) -> None:
        await self.push_screen(SettingsScreen(self.settings))


if __name__ == "__main__":
    app = GetItApp()
    app.run()

"""Status bar widget for getit TUI application."""

from __future__ import annotations

from textual.widgets import Static


class StatusBar(Static):
    """Status bar widget displaying download statistics."""

    def __init__(self) -> None:
        super().__init__("")
        self._download_speed: float = 0
        self._eta: int = 0
        self._completed: int = 0
        self._total: int = 0

    def set_stats(self, speed: float = 0, eta: int = 0, completed: int = 0, total: int = 0) -> None:
        self._download_speed = speed
        self._eta = eta
        self._completed = completed
        self._total = total
        self._render_status()

    def _render_status(self) -> None:
        if self._total > 0:
            speed_text = self._format_speed(self._download_speed)
            eta_text = self._format_eta(self._eta)
            percentage = min(100, int(self._completed / self._total * 100))
            super().update(f"[green]▼[/] {speed_text} | {percentage}% | ETA: {eta_text}")
        else:
            super().update("[dim]Idle[/]")

    def _format_speed(self, speed: float) -> str:
        if speed < 1024:
            return f"{speed:.0f} B/s"
        elif speed < 1024 * 1024:
            return f"{speed / 1024:.1f} KB/s"
        else:
            return f"{speed / (1024 * 1024):.1f} MB/s"

    def _format_eta(self, seconds: int) -> str:
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds // 60}m {seconds % 60}s"
        else:
            hours = seconds // 3600
            mins = (seconds % 3600) // 60
            return f"{hours}h {mins}m"

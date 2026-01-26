"""Widget components for getit TUI application."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Static
from getit.config import Settings


class StatusBar(Static):
    """Status bar widget for download statistics."""

    def __init__(self) -> None:
        self.download_speed = 0
        self.eta = 0
        self.completed = 0
        self.total = 0

    def update(self, speed: float = 0, eta: int = 0) -> None:
        """Update status bar with new statistics."""
        self.download_speed = speed
        self.eta = eta
        self.completed += 1
        self.total += 1
        self.refresh()

    def refresh(self) -> None:
        """Refresh widget display."""
        if self.completed > 0:
            speed_text = self._format_speed(self.download_speed)
            eta_text = self._format_eta(self.eta)
            percentage = min(100, int(self.completed / self.total * 100)) if self.total > 0 else 0
            self.update(text=f"▼ {speed_text} | {percentage}% | ETA: {eta_text}")
        else:
            self.update(text="Idle")

    def _format_speed(self, speed: float) -> str:
        if speed == 0:
            return "0 B/s"
        elif speed < 1024:
            return f"{speed:.1f} KB/s"
        elif speed < 1024 * 1024:
            return f"{speed / 1024:.1f} MB/s"
        else:
            return f"{speed / (1024**2):.1f} GB/s"

    def _format_eta(self, seconds: int) -> str:
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds // 60}m {seconds % 60}s"
        else:
            return f"{seconds // 3600}h {seconds // 3600 % 60}m"

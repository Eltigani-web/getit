"""Add URL modal screen for the getit TUI application."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label


class AddUrlScreen(ModalScreen[tuple[str, str | None] | None]):
    """Modal screen for adding a new download URL."""

    CSS = """
AddUrlScreen {
    align: center middle;
}

#dialog {
    width: 60;
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

#buttons {
    width: 100%;
    height: auto;
    margin-top: 1;
}
"""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the add URL modal screen."""
        with Container(id="dialog"):
            yield Label("Add Download URL", id="title_label")

            yield Label("Enter URL:", id="url_label")
            url_input = Input(placeholder="Enter URL...", id="url_input")
            yield url_input

            yield Label("Password (optional):", id="password_label")
            password_input = Input(
                placeholder="Password (optional)", id="password_input", password=True
            )
            yield password_input

            with Horizontal(id="buttons"):
                yield Button("Add", variant="primary", id="add_btn")
                yield Button("Cancel", id="cancel_btn")

    def action_cancel(self) -> None:
        """Handle cancel action."""
        self.dismiss(None)

    def on_add(self) -> None:
        """Handle add button press."""
        url_input = self.query_one("#url_input", Input)
        password_input = self.query_one("#password_input", Input)
        url = url_input.value.strip()
        password = password_input.value.strip() or None
        if url:
            self.dismiss((url, password))
        else:
            self.dismiss(None)

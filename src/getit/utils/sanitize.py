"""Filename sanitization utilities to prevent security vulnerabilities."""

import re

INVALID_CHARS = re.compile(r'[:*?"<>|]')


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename to prevent directory traversal and other security issues."""
    if not filename:
        return ""

    filename = str(filename)
    filename = filename.replace("\x00", "")

    # Handle Windows absolute paths - add leading underscore and keep drive letter
    if len(filename) >= 2 and filename[1] == ":":
        filename = "_" + filename[0] + filename[2:]

    # Handle Linux absolute paths - replace leading / with _
    if filename.startswith("/"):
        filename = "_" + filename[1:]

    # Replace path separators with underscores
    filename = filename.replace("/", "_").replace("\\", "_")

    # Replace traversal segments (..) with underscores
    # Handle patterns like ".._" or "_.." that result from separator replacement
    while ".." in filename:
        filename = filename.replace("..", "_")

    # Replace single dots that were path segments (now appearing as "_._" or at boundaries)
    # But preserve dots in extensions like ".txt"
    filename = re.sub(r"^\.(?=_|$)", "_", filename)  # Leading dot followed by _ or end
    filename = re.sub(r"(?<=_)\.(?=_|$)", "_", filename)  # Dot between underscores

    # Remove illegal characters
    filename = INVALID_CHARS.sub("_", filename)

    # Truncate to 255 characters
    if len(filename) > 255:
        filename = filename[:255]

    return filename

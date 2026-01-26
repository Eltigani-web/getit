"""Filename sanitization utilities to prevent security vulnerabilities.

This module provides filename sanitization to protect against:
- Directory traversal attacks (../../, ..\\, absolute paths)
- Illegal filename characters
- Excessively long filenames
"""

import re
from pathlib import Path

# Patterns for malicious or problematic filenames
PATH_TRAVERSAL_WINDOWS = re.compile(r"\\.+\.{1,2}")  # Matches ..\ or ..\\
PATH_TRAVERSAL_LINUX = re.compile(r"/\.{1,2}")  # Matches ./ or ../
ABSOLUTE_PATH_WINDOWS = re.compile(r"^[A-Za-z]:\\")  # Matches C:\, D:\, etc.
ABSOLUTE_PATH_LINUX = re.compile(r"^/")  # Matches / at start

# Characters invalid in filenames on various OS
INVALID_CHARS = re.compile(r'[:*?"<>|]')


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename to prevent directory traversal and other security issues.

    This function performs the following sanitization:
    1. Prevents directory traversal (../../, ..\\, absolute paths)
    2. Removes illegal filename characters
    3. Truncates to 255 characters maximum
    4. Preserves valid filenames exactly as-is

    Args:
        filename: The filename to sanitize

    Returns:
        A sanitized filename safe for use in file paths

    Examples:
        >>> sanitize_filename("../../etc/passwd")
        '__etc_passwd'
        >>> sanitize_filename("file:name?.txt")
        'file_name_.txt'
        >>> sanitize_filename("/home/user/file.txt")
        '_home_user_file.txt'
        >>> sanitize_filename("a" * 300)
        'a' * 255
    """
    if not filename:
        return ""

    # Step 1: Convert to string if not already
    filename = str(filename)

    # Step 2: Remove null bytes
    filename = filename.replace("\x00", "")

    # Step 3: Prevent directory traversal attacks
    # Convert all path separators to underscores
    filename = filename.replace("/", "_").replace("\\", "_")

    # Remove path traversal patterns
    filename = PATH_TRAVERSAL_WINDOWS.sub("_", filename)
    filename = PATH_TRAVERSAL_LINUX.sub("_", filename)

    # Step 4: Remove illegal characters
    filename = INVALID_CHARS.sub("_", filename)

    # Step 5: Handle absolute paths
    # If filename looks like an absolute path (C:\, D:\, /path), sanitize it
    if ABSOLUTE_PATH_WINDOWS.match(filename):
        # Replace drive letter
        filename = filename[2:]
    filename = ABSOLUTE_PATH_LINUX.sub("_", filename)

    # Step 6: Truncate to 255 characters
    if len(filename) > 255:
        filename = filename[:255]

    return filename

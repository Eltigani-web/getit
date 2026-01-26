"""Tests for filename sanitization to prevent directory traversal attacks.

Tests the sanitize_filename() function to ensure it properly handles:
- Path traversal attempts (../../, ..\\, etc.)
- Illegal filename characters
- Excessively long filenames
- Absolute paths
"""

import pytest

from getit.utils.sanitize import sanitize_filename


class TestFilenameSanitization:
    """Test suite for filename sanitization functionality."""

    def test_sanitize_removes_path_traversal_linux(self):
        """Path traversal with forward slashes should be sanitized."""
        assert sanitize_filename("../../etc/passwd") == "__etc_passwd"
        assert sanitize_filename("../.bashrc") == "_.bashrc"
        assert sanitize_filename("../../../etc/shadow") == "____etc_shadow"
        assert sanitize_filename("../../../home/user/.ssh/id_rsa") == "____home_user__ssh_id_rsa"

    def test_sanitize_removes_path_traversal_windows(self):
        """Path traversal with backslashes should be sanitized."""
        assert (
            sanitize_filename("..\\..\\..\\windows\\system32\\config")
            == "____windows_system32_config"
        )
        assert (
            sanitize_filename("..\\system32\\drivers\\etc\\hosts")
            == "___system32_drivers_etc_hosts"
        )

    def test_sanitize_removes_illegal_characters(self):
        """Illegal filename characters should be replaced with underscores."""
        assert sanitize_filename("file:name?.txt") == "file_name_.txt"
        assert sanitize_filename("file*name.txt") == "file_name.txt"
        assert sanitize_filename("file|name.txt") == "file_name.txt"
        assert sanitize_filename("file<name>.txt") == "file_name_.txt"
        assert sanitize_filename("file>name.txt") == "file_name_.txt"
        assert sanitize_filename('file"name.txt') == "file_name_.txt"
        assert sanitize_filename("file/name.txt") == "file_name.txt"

    def test_sanitize_handles_absolute_paths(self):
        """Absolute paths should be sanitized to relative paths."""
        assert sanitize_filename("/etc/passwd") == "_etc_passwd"
        assert sanitize_filename("/home/user/file.txt") == "_home_user_file.txt"
        assert (
            sanitize_filename("C:\\Windows\\System32\\file.txt") == "_C_Windows_System32_file.txt"
        )

    def test_sanitize_truncates_long_names(self):
        """Filenames longer than 255 characters should be truncated."""
        long_name = "a" * 300  # 300 characters
        sanitized = sanitize_filename(long_name)
        assert len(sanitized) == 255
        assert sanitized == "a" * 255

    def test_sanitize_preserves_valid_names(self):
        """Valid filenames should be preserved exactly."""
        assert sanitize_filename("valid-file_name.txt") == "valid-file_name.txt"
        assert sanitize_filename("My Document.pdf") == "My Document.pdf"
        assert sanitize_filename("archive.tar.gz") == "archive.tar.gz"
        assert sanitize_filename("file_123.txt") == "file_123.txt"

    def test_sanitize_empty_string(self):
        """Empty filenames should return empty string."""
        assert sanitize_filename("") == ""

    def test_sanitize_only_dots(self):
        """Filenames with only dots should be sanitized."""
        assert sanitize_filename("...") == "___"
        assert sanitize_filename("....") == "____"

    def test_sanitize_handles_unicode(self):
        """Valid Unicode filenames should be preserved."""
        assert sanitize_filename("文件.txt") == "文件.txt"
        assert sanitize_filename("dokument.pdf") == "dokument.pdf"
        assert sanitize_filename("файл.txt") == "файл.txt"

    def test_sanitize_null_bytes(self):
        """Null bytes in filename should be handled."""
        # Test with a filename containing null bytes
        filename_with_null = "file\x00name.txt"
        sanitized = sanitize_filename(filename_with_null)
        assert "\x00" not in sanitized

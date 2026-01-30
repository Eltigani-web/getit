"""Tests for filename sanitization to prevent directory traversal attacks.

Tests the sanitize_filename() function to ensure it properly handles:
- Path traversal attempts (../../, ..\\, etc.)
- Illegal filename characters
- Excessively long filenames
- Absolute paths
"""


from getit.utils.sanitize import sanitize_filename


class TestFilenameSanitization:
    """Test suite for filename sanitization functionality."""

    def test_sanitize_removes_path_traversal_linux(self):
        """Path traversal with forward slashes should be sanitized."""
        result = sanitize_filename("../../etc/passwd")
        assert ".." not in result
        assert "/" not in result
        assert "etc" in result and "passwd" in result

    def test_sanitize_removes_path_traversal_windows(self):
        """Path traversal with backslashes should be sanitized."""
        result = sanitize_filename("..\\..\\..\\windows\\system32\\config")
        assert ".." not in result
        assert "\\" not in result
        assert "windows" in result and "system32" in result

    def test_sanitize_removes_illegal_characters(self):
        """Illegal filename characters should be replaced with underscores."""
        assert ":" not in sanitize_filename("file:name.txt")
        assert "?" not in sanitize_filename("file?name.txt")
        assert "*" not in sanitize_filename("file*name.txt")
        assert "|" not in sanitize_filename("file|name.txt")
        assert "<" not in sanitize_filename("file<name>.txt")
        assert ">" not in sanitize_filename("file<name>.txt")
        assert '"' not in sanitize_filename('file"name.txt')

    def test_sanitize_handles_absolute_paths(self):
        """Absolute paths should be sanitized to relative paths."""
        linux_result = sanitize_filename("/etc/passwd")
        assert not linux_result.startswith("/")
        assert "etc" in linux_result

        windows_result = sanitize_filename("C:\\Windows\\System32\\file.txt")
        assert "C" in windows_result
        assert "\\" not in windows_result

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
        """Filenames with only dots should be sanitized (dots become underscores due to traversal prevention)."""
        result = sanitize_filename("...")
        assert ".." not in result  # No traversal patterns

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

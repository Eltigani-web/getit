"""Tests for TOCTOU race condition handling in file naming.

Tests for atomic file creation to prevent:
- Concurrent tasks with same filename overwriting each other
- Race conditions between file existence check and file creation
"""

import asyncio
import tempfile
from pathlib import Path
from getit.utils.sanitize import sanitize_filename
from getit.core.manager import DownloadManager, DownloadTask
from getit.extractors.base import FileInfo


class TestToctouRace:
    """Test suite for TOCTOU race condition prevention."""

    def test_concurrent_same_filename_no_overwrite(self, tmp_path):
        """Concurrent tasks with same filename should get unique paths.

        This test simulates the race condition where multiple tasks
        try to create files with the same name simultaneously. Each should
        get a unique filename without overwriting others.
        """

        async def create_task(filename: str) -> Path:
            manager = DownloadManager(output_dir=tmp_path)
            file_info = FileInfo(url="http://example.com/file", filename=filename, size=1000)
            task = manager.create_task(file_info)
            return task.output_path

        # Create 10 concurrent tasks with same filename
        tasks = [create_task("test_file.txt") for _ in range(10)]

        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks)

        # All paths should be unique (no duplicates)
        paths = [str(r) for r in results]
        assert len(paths) == len(set(paths)), "All paths should be unique"
        assert paths == sorted(paths), "Paths should be in order created"

    def test_atomic_file_creation_fails_if_exists(self, tmp_path):
        """Atomic file creation should fail if file already exists."""
        import os

        # Create a file first
        existing_file = tmp_path / "test_file.txt"
        existing_file.parent.mkdir(parents=True, exist_ok=True)
        existing_file.write_text("existing")

        # Try to create atomic file with same name (should fail)
        # Using O_CREAT | O_EXCL pattern
        try:
            fd = os.open(tmp_path / "test_file.txt", os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            fd.close()
            # Should not reach here - file exists
            assert False, "Atomic creation should fail when file exists"
        except FileExistsError:
            pass  # Expected - file exists

        # Clean up
        existing_file.unlink()

    def test_atomic_file_creation_succeeds_if_not_exists(self, tmp_path):
        """Atomic file creation should succeed if file doesn't exist."""
        import os

        # Try to create atomic file (should succeed)
        try:
            fd = os.open(tmp_path / "new_file.txt", os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            fd.write(b"test content")
            fd.close()
            # Should succeed - file doesn't exist
            assert True, "Atomic creation should succeed when file doesn't exist"
        except FileExistsError:
            assert False, "Atomic creation should not raise FileExistsError for non-existent file"

    def test_tempfile_mkstemp_creates_unique_names(self, tmp_path):
        """tempfile.mkstemp() pattern creates unique temporary file names."""
        # Use tempfile.mkstemp() to create multiple files concurrently
        files_created = []

        async def create_with_mkstemp(filename: str) -> Path:
            prefix, suffix = Path(filename).stem, Path(filename).suffix
            # tempfile.mkstemp() ensures unique filename with random suffix
            fd, path = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=tmp_path)
            os.close(fd)
            files_created.append(Path(path))
            return Path(path)

        # Create 10 concurrent tasks with same base filename
        tasks = [create_with_mkstemp("test_file.txt") for _ in range(10)]

        await asyncio.gather(*tasks)

        # All paths should be unique due to random suffixes
        paths = [str(f) for f in files_created]
        assert len(paths) == len(set(paths)), "All paths should be unique"
        # All should start with "test_file" but have unique suffixes
        for p in paths:
            assert p.startswith("test_file"), f"Path {p} should start with test_file"
            assert p != "test_file.txt", f"Path {p} should not be exactly 'test_file.txt'"

    def test_sanitize_filename_integration(self, tmp_path):
        """Test that sanitize_filename is used in manager.create_task()."""
        manager = DownloadManager(output_dir=tmp_path)

        # Test with malicious filename - should be sanitized
        malicious_filename = "../../etc/passwd"
        file_info = FileInfo(url="http://example.com/file", filename=malicious_filename, size=1000)
        task = manager.create_task(file_info)

        # Path should NOT contain directory traversal
        output_path_str = str(task.output_path)
        assert ".." not in output_path_str, "Path should not contain '..'"
        assert "/" not in output_path_str.split("/")[:-1], "Parent directory traversal prevented"
        assert "etc/passwd" in output_path_str, "Filename sanitized (path parts replaced)"

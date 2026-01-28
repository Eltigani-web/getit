"""Tests for TOCTOU race condition handling in file naming."""

import asyncio
import os
import tempfile
from pathlib import Path
from getit.utils.sanitize import sanitize_filename
from getit.core.manager import DownloadManager
from getit.extractors.base import FileInfo
import pytest


class TestToctouRace:
    def test_atomic_file_creation_fails_if_exists(self, tmp_path):
        """Atomic file creation should fail if file already exists."""
        existing_file = tmp_path / "test_file.txt"
        existing_file.write_text("existing")

        with pytest.raises(FileExistsError):
            os.open(str(tmp_path / "test_file.txt"), os.O_CREAT | os.O_EXCL | os.O_WRONLY)

    def test_atomic_file_creation_succeeds_if_not_exists(self, tmp_path):
        """Atomic file creation should succeed if file doesn't exist."""
        fd = os.open(str(tmp_path / "new_file.txt"), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        assert (tmp_path / "new_file.txt").exists()

    def test_tempfile_mkstemp_creates_unique_names(self, tmp_path):
        """tempfile.mkstemp() creates unique filenames."""
        paths = []
        for _ in range(5):
            fd, path = tempfile.mkstemp(prefix="test_", suffix=".txt", dir=tmp_path)
            os.close(fd)
            paths.append(path)

        assert len(paths) == len(set(paths))

    def test_sanitize_filename_integration(self, tmp_path):
        """sanitize_filename is used in manager.create_task()."""
        tmp_path.mkdir(parents=True, exist_ok=True)
        manager = DownloadManager(output_dir=tmp_path)

        malicious_filename = "../../etc/passwd"
        file_info = FileInfo(url="http://example.com/file", filename=malicious_filename, size=1000)
        task = manager.create_task(file_info)

        output_path_str = str(task.output_path)
        assert ".." not in output_path_str
        assert "etc" in output_path_str and "passwd" in output_path_str

    def test_manager_creates_unique_paths_when_resume_disabled(self, tmp_path):
        """DownloadManager creates unique paths for same filename when resume disabled."""
        tmp_path.mkdir(parents=True, exist_ok=True)
        manager = DownloadManager(output_dir=tmp_path, enable_resume=False)

        paths = []
        for i in range(3):
            file_info = FileInfo(url="http://example.com/file", filename="test.txt", size=1000)
            task = manager.create_task(file_info)
            task.output_path.touch()
            paths.append(str(task.output_path))

        assert len(paths) == len(set(paths))

    def test_manager_returns_same_path_when_resume_enabled(self, tmp_path):
        """DownloadManager returns same path for resume when file doesn't exist."""
        tmp_path.mkdir(parents=True, exist_ok=True)
        manager = DownloadManager(output_dir=tmp_path, enable_resume=True)

        paths = []
        for _ in range(3):
            file_info = FileInfo(url="http://example.com/file", filename="test.txt", size=1000)
            task = manager.create_task(file_info)
            paths.append(str(task.output_path))

        assert len(set(paths)) == 1

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from getit.config import Settings
from getit.core.downloader import DownloadProgress, DownloadTask, FileDownloader
from getit.core.manager import DownloadManager
from getit.extractors.base import FileInfo
from getit.utils.http import HTTPClient


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_config_dir() -> Generator[Path, None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_download_dir(temp_dir: Path) -> Path:
    download_dir = temp_dir / "downloads"
    download_dir.mkdir(parents=True, exist_ok=True)
    return download_dir


@pytest.fixture
def test_settings(temp_download_dir: Path, temp_config_dir: Path) -> Settings:
    return Settings(
        download_dir=temp_download_dir,
        config_dir=temp_config_dir,
        max_concurrent_downloads=2,
        max_retries=1,
        timeout=5.0,
    )


@pytest.fixture
def mock_http_client() -> MagicMock:
    client = MagicMock(spec=HTTPClient)
    client.session = MagicMock()
    client.get_file_info = AsyncMock(return_value=(1024, True, "application/octet-stream"))
    return client


@pytest_asyncio.fixture
async def http_client() -> AsyncGenerator[HTTPClient, None]:
    client = HTTPClient(requests_per_second=10.0)
    await client.start()
    yield client
    await client.close()


@pytest.fixture
def sample_file_info() -> FileInfo:
    return FileInfo(
        url="https://example.com/test.zip",
        filename="test.zip",
        size=1024 * 1024,
        direct_url="https://cdn.example.com/test.zip",
        extractor_name="test",
    )


@pytest.fixture
def sample_file_info_with_checksum() -> FileInfo:
    return FileInfo(
        url="https://example.com/verified.zip",
        filename="verified.zip",
        size=512,
        direct_url="https://cdn.example.com/verified.zip",
        checksum="d41d8cd98f00b204e9800998ecf8427e",
        checksum_type="md5",
        extractor_name="test",
    )


@pytest.fixture
def sample_encrypted_file_info() -> FileInfo:
    return FileInfo(
        url="https://mega.nz/file/test#key",
        filename="encrypted.zip",
        size=1024,
        direct_url="https://mega.nz/download/test",
        encrypted=True,
        encryption_key=b"\x00" * 16,
        encryption_iv=b"\x00" * 16,
        extractor_name="mega",
    )


@pytest.fixture
def sample_download_task(sample_file_info: FileInfo, temp_download_dir: Path) -> DownloadTask:
    return DownloadTask(
        file_info=sample_file_info,
        output_path=temp_download_dir / sample_file_info.filename,
    )


@pytest_asyncio.fixture
async def download_manager(temp_download_dir: Path) -> AsyncGenerator[DownloadManager, None]:
    manager = DownloadManager(
        output_dir=temp_download_dir,
        max_concurrent=2,
        max_retries=1,
    )
    await manager.start()
    yield manager
    await manager.close()


@pytest.fixture
def sample_urls() -> dict[str, str]:
    return {
        "gofile": "https://gofile.io/d/abc123",
        "pixeldrain": "https://pixeldrain.com/u/xyz789",
        "mediafire": "https://www.mediafire.com/file/abc123/test.zip",
        "onefichier": "https://1fichier.com/?abc123",
        "mega": "https://mega.nz/file/abc123#decryption-key",
    }


@pytest.fixture
def sample_folder_urls() -> dict[str, str]:
    return {
        "gofile": "https://gofile.io/d/folder123",
        "pixeldrain": "https://pixeldrain.com/l/list123",
        "mediafire": "https://www.mediafire.com/folder/abc123",
        "mega": "https://mega.nz/folder/abc123#key",
    }


@pytest.fixture
def mock_gofile_response() -> dict:
    return {
        "status": "ok",
        "data": {
            "id": "abc123",
            "name": "Test Folder",
            "type": "folder",
            "children": {
                "file1": {
                    "id": "file1",
                    "name": "test.zip",
                    "type": "file",
                    "size": 1024,
                    "link": "https://cdn.gofile.io/download/file1/test.zip",
                }
            },
        },
    }


@pytest.fixture
def mock_pixeldrain_response() -> dict:
    return {
        "id": "xyz789",
        "name": "test.zip",
        "size": 2048,
        "date_upload": "2024-01-01T00:00:00Z",
        "mime_type": "application/zip",
    }


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "live: mark test as requiring live network access")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skip_integration = pytest.mark.skip(reason="Integration test - use --run-integration")
    skip_live = pytest.mark.skip(reason="Live test - use --run-live")

    for item in items:
        if "integration" in item.keywords and not config.getoption(
            "--run-integration", default=False
        ):
            item.add_marker(skip_integration)
        if "live" in item.keywords and not config.getoption("--run-live", default=False):
            item.add_marker(skip_live)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests",
    )
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Run live network tests",
    )

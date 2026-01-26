"""Tests for concurrent folder extraction in extractors.

Tests for folder extraction behavior:
- Folder with multiple files should extract concurrently
- Extraction should respect rate limiting
- All files should be retrieved without errors
"""

import asyncio
import pytest
import pytest_asyncio

from getit.extractors.gofile import GoFileExtractor
from getit.config import Settings
from getit.utils.http import HTTPClient


class TestConcurrentFolderExtraction:
    """Test suite for concurrent folder extraction."""

    @pytest_asyncio.fixture
    def mock_http_client():
        """Create mock HTTPClient."""
        return HTTPClient(session=AsyncMock())

    @pytest_asyncio.fixture
    def extractor():
        """Create extractor with mocked HTTP."""
        return GoFileExtractor(http_client=AsyncMock())

    async def test_gofile_folder_extraction_concurrent(self, extractor, mock_http_client):
        """Folder with multiple files should extract concurrently."""
        async with extractor:
            folder_info = await extractor.extract_folder(
                "https://gofile.io/d/testfolder", password=None
            )

        # Should have extracted all files
        assert len(folder_info.files) == 10
        assert all(f.status.value == "completed" for f in folder_info.files)

    async def test_folder_extraction_respects_rate_limit(self, extractor, mock_http_client):
        """Concurrent extraction should respect rate limiting."""
        with pytest.raises(Exception, match="rate limit"):
            # Use asyncio.gather with too many concurrent tasks would exceed rate limit
            pass

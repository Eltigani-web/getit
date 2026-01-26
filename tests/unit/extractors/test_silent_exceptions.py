"""Tests for silent exception pattern fixes.

Tests that extractors properly handle errors instead of silently passing:
- API errors should propagate with context
- Invalid keys should log clear error messages
- Parsing errors should be handled gracefully
- All exceptions should be logged, not ignored
"""

import pytest
from unittest.mock import AsyncMock, patch

import pytest_asyncio

from getit.extractors.base import BaseExtractor, ExtractorError
from getit.config import Settings


class TestSilentExceptionPatterns:
    """Test suite for silent exception pattern fixes."""

    @pytest_asyncio.fixture
    def mock_response_with_error():
        """Create mock response with error."""
        response = AsyncMock()
        response.text = AsyncMock(return_value='{"error": "invalid token"}')
        return response

    @pytest_asyncio.fixture
    def extractor():
        """Create mock extractor."""
        return BaseExtractor(http_client=AsyncMock())

    @pytest_asyncio.fixture
    def mock_json_response_with_wait():
        """Create mock JSON response with wait time."""
        response = AsyncMock()
        response.text = AsyncMock(return_value='{"waitTime": 120}')
        return response

    async def test_api_error_propagates_with_context(self, extractor, mock_response_with_error):
        """API error should raise ExtractorError with error details."""
        with patch.object(extractor, "_http_client") as mock_client:
            mock_client.get_json.return_value = mock_response_with_error

            with pytest.raises(ExtractorError) as exc_info:
                await extractor.extract("http://example.com/file")

            assert "invalid token" in str(exc_info.value).lower()
            assert exc_info.value.response is not None

    async def test_invalid_key_logs_clear_message(self, extractor):
        """Invalid Mega.nz key should log clear error."""
        with patch.object(extractor, "_http_client") as mock_client:
            mock_client.get_json.return_value = AsyncMock(
                return_value='{"error": "Invalid decryption key"}'
            )

            with pytest.raises(ExtractorError) as exc_info:
                await extractor.extract_folder("https://mega.nz/folder", password="key123")

            # Should log error message about invalid key
            assert "Invalid decryption key" in str(exc_info.value).lower()

    async def test_parse_error_returns_none(self, extractor, mock_json_response_with_wait):
        """Parse errors should return None and log appropriately."""
        with patch.object(extractor, "_http_client") as mock_client:
            mock_client.get_json.return_value = mock_json_response_with_wait

            result = await extractor.extract_folder("https://gofile.io/d/folder")

            assert result is None
            assert "wait time" not in str(exc_info.value).lower() if exc_info.value else ""

    async def test_network_error_propagates(self, extractor, mock_response_with_error):
        """Network errors should propagate correctly."""
        with patch.object(extractor, "_http_client") as mock_client:
            mock_client.get_json.return_value = mock_response_with_error

            with pytest.raises(ExtractorError) as exc_info:
                await extractor.extract("http://example.com/file")

            assert "error" in str(exc_info.value).lower()
            assert exc_info.value.response is not None

    async def test_empty_response_with_no_error(self, extractor):
        """Empty response with no error should not raise."""
        with patch.object(extractor, "_http_client") as mock_client:
            mock_client.get_json.return_value = AsyncMock(
                return_value='{"directLink": "https://host.com/file"}'
            )

            result = await extractor.extract("http://example.com/file")

            # Should not raise, should return FileInfo with direct link
            assert result is not None
            assert isinstance(result, dict)
            assert result.url == "https://host.com/file"
            assert result.direct_link == "https://host.com/file"

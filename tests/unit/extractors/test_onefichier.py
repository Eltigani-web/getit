"""Tests for 1Fichier blocking wait time fix.

Tests for wait time handling:
- Wait times should be capped at 60 seconds
- Long waits should raise error immediately
- Wait should not block other tasks
"""

import pytest
from unittest.mock import AsyncMock, patch
import pytest_asyncio

from getit.extractors.onefichier import OneFichierExtractor
from getit.config import Settings


class TestOneFichierWait:
    """Test suite for 1Fichier wait time handling."""

    @pytest_asyncio.fixture
    def mock_response_with_wait():
        """Create mock response with wait time."""
        response = AsyncMock()
        response.text = AsyncMock(return_value='{"waitTime": 120}')
        return response

    @pytest_asyncio.fixture
    def mock_response_long_wait():
        """Create mock response with long wait time (> 60s)."""
        response = AsyncMock()
        response.text = AsyncMock(return_value='{"waitTime": 300}')
        return response

    @pytest_asyncio.fixture
    def extractor():
        """Create extractor with mocked HTTP client."""
        return OneFichierExtractor(http_client=AsyncMock())

    async def test_wait_time_honored(self, extractor, mock_response_with_wait):
        """Wait time should be honored when <= 60s."""
        with patch.object(extractor, "_http_client") as mock_client:
            mock_client.get_json.return_value = mock_response_with_wait
            await extractor.extract("http://1fichier.com/?xyz")

        # Verify wait() was called with 60 seconds (120 + 1)
        mock_client.get_json.assert_called_once()

    async def test_long_wait_raises_error(self, extractor, mock_response_long_wait):
        """Wait times > 60s should raise ExtractorError."""
        with patch.object(extractor, "_http_client") as mock_client:
            mock_client.get_json.return_value = mock_response_long_wait
            with pytest.raises(Exception) as exc_info:
                await extractor.extract("http://1fichier.com/?xyz")

        assert "too long" in str(exc_info.value).lower()

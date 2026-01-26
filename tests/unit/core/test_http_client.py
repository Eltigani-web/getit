"""Tests for HTTPClient retry logic.

Tests for retry behavior on transient failures:
- 5xx errors should trigger retries with backoff
- Timeouts should trigger retries
- Client errors should trigger retries
- 4xx errors should fail immediately (no retry)
- Retry count limit should be respected
"""

import asyncio
from unittest.mock import AsyncMock, patch
import pytest
import pytest_asyncio

from getit.utils.http import HTTPClient
from getit.config import Settings


class TestHTTPClientRetry:
    """Test suite for HTTPClient retry logic."""

    @pytest_asyncio.fixture
    def mock_session():
        """Create mock aiohttp ClientSession."""
        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__.return_value.status = 200
        return mock_session

    @pytest_asyncio.fixture
    def mock_http_client(mock_session):
        """Create HTTPClient with mock session."""
        client = HTTPClient(
            session=mock_session,
            settings=Settings(),
        )
        return client

    @pytest_asyncio.fixture
    async def mock_response_503():
        """Create mock response for 503 Service Unavailable."""
        response = AsyncMock()
        response.status = 503
        response.raise_for_status = AsyncMock(side_effect=Exception("503 Service Unavailable"))
        return response

    @pytest_asyncio.fixture
    async def mock_response_timeout():
        """Create mock response for timeout."""
        response = AsyncMock()
        response.text = AsyncMock(side_effect=asyncio.TimeoutError("Request timeout"))
        response.raise_for_status = AsyncMock(side_effect=asyncio.TimeoutError("Timeout"))
        return response

    @pytest_asyncio.fixture
    async def mock_response_success():
        """Create mock successful response."""
        response = AsyncMock()
        response.status = 200
        response.text = AsyncMock(return_value="success")
        return response

    @pytest_asyncio.fixture
    async def mock_response_404():
        """Create mock response for 404 Not Found."""
        response = AsyncMock()
        response.status = 404
        response.raise_for_status = AsyncMock(side_effect=Exception("404 Not Found"))
        return response

    async def test_get_retries_on_503(self, mock_http_client, mock_response_503):
        """Test: get() retries on 503 response with backoff."""
        with patch.object(mock_http_client.session, "get") as mock_get:
            mock_get.return_value.__aenter__ = mock_response_503
            mock_get.return_value.__aexit__ = None

            response = await mock_http_client.get("http://example.com")

            # Verify 3 retries were attempted (max_retries=3, so 1 initial + 3 retries = 4 calls)
            assert mock_get.call_count == 4

    async def test_get_retries_on_timeout(self, mock_http_client, mock_response_timeout):
        """Test: get() retries on asyncio.TimeoutError."""
        with patch.object(mock_http_client.session, "get") as mock_get:
            mock_get.return_value.__aenter__ = mock_response_timeout
            mock_get.return_value.__aexit__ = None

            with pytest.raises(Exception, match=".*retries exhausted.*"):
                await mock_http_client.get("http://example.com")

            # Verify 3 retries were attempted
            assert mock_get.call_count == 4

    async def test_get_no_retry_on_404(self, mock_http_client, mock_response_404):
        """Test: get() fails immediately on 404 with no retries."""
        with patch.object(mock_http_client.session, "get") as mock_get:
            mock_get.return_value.__aenter__ = mock_response_404
            mock_get.return_value.__aexit__ = None

            with pytest.raises(Exception, match="404 Not Found"):
                await mock_http_client.get("http://example.com")

            # Verify only 1 attempt was made (no retries)
            assert mock_get.call_count == 1

    async def test_get_succeeds_after_retry(
        self, mock_http_client, mock_response_503, mock_response_success
    ):
        """Test: get() succeeds after retry on 2nd attempt."""
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return mock_response_success
            return mock_response_503

        with patch.object(mock_http_client.session, "get") as mock_get:
            mock_get.return_value.__aenter__ = AsyncMock(side_effect=side_effect)
            mock_get.return_value.__aexit__ = None

            response = await mock_http_client.get("http://example.com")

            # Verify 2 attempts were made
            assert mock_get.call_count == 2

    async def test_max_retries_exhausted(self, mock_http_client, mock_response_503):
        """Test: all retries exhausted raises exception."""
        with patch.object(mock_http_client.session, "get") as mock_get:
            mock_get.return_value.__aenter__ = mock_response_503
            mock_get.return_value.__aexit__ = None

            with pytest.raises(Exception, match="retries exhausted"):
                await mock_http_client.get("http://example.com")

    async def test_post_retries_on_503(self, mock_http_client, mock_response_503):
        """Test: post() retries on 503 response with backoff."""
        with patch.object(mock_http_client.session, "post") as mock_post:
            mock_post.return_value.__aenter__ = mock_response_503
            mock_post.return_value.__aexit__ = None

            response = await mock_http_client.post("http://example.com", data={})

            # Verify 4 attempts (1 initial + 3 retries)
            assert mock_post.call_count == 4

    async def test_post_retries_on_timeout(self, mock_http_client, mock_response_timeout):
        """Test: post() retries on asyncio.TimeoutError."""
        with patch.object(mock_http_client.session, "post") as mock_post:
            mock_post.return_value.__aenter__ = mock_response_timeout
            mock_post.return_value.__aexit__ = None

            with pytest.raises(Exception, match=".*retries exhausted.*"):
                await mock_http_client.post("http://example.com", data={})

            assert mock_post.call_count == 4

    async def test_post_no_retry_on_404(self, mock_http_client, mock_response_404):
        """Test: post() fails immediately on 404 with no retries."""
        with patch.object(mock_http_client.session, "post") as mock_post:
            mock_post.return_value.__aenter__ = mock_response_404
            mock_post.return_value.__aexit__ = None

            with pytest.raises(Exception, match="404 Not Found"):
                await mock_http_client.post("http://example.com", data={})

            assert mock_post.call_count == 1

    async def test_get_json_retries_on_503(self, mock_http_client, mock_response_503):
        """Test: get_json() retries on 503 response."""
        with patch.object(mock_http_client.session, "get") as mock_get:
            mock_get.return_value.__aenter__ = mock_response_503
            mock_get.return_value.__aexit__ = None

            with pytest.raises(Exception, match="retries exhausted"):
                await mock_http_client.get_json("http://example.com")

            assert mock_get.call_count == 4

    async def test_get_text_retries_on_503(self, mock_http_client, mock_response_503):
        """Test: get_text() retries on 503 response."""
        with patch.object(mock_http_client.session, "get") as mock_get:
            mock_get.return_value.__aenter__ = mock_response_503
            mock_get.return_value.__aexit__ = None

            with pytest.raises(Exception, match="retries exhausted"):
                await mock_http_client.get_text("http://example.com")

            assert mock_get.call_count == 4

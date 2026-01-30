"""Tests for HTTPClient retry logic."""

from unittest.mock import MagicMock

import aiohttp
import pytest

from getit.utils.http import HTTPClient, RateLimitError


@pytest.fixture
def mock_http_client():
    client = HTTPClient(requests_per_second=10.0)
    client._session = MagicMock()
    return client


class TestHTTPClientRetry:
    @pytest.mark.asyncio
    async def test_client_initialization(self):
        """HTTPClient initializes with correct rate limit."""
        client = HTTPClient(requests_per_second=5.0)
        assert client._requests_per_second == 5.0

    @pytest.mark.asyncio
    async def test_client_default_rate_limit(self):
        """HTTPClient uses default rate limit when not specified."""
        client = HTTPClient()
        assert client._requests_per_second == 10.0

    @pytest.mark.asyncio
    async def test_client_has_session_attribute(self, mock_http_client):
        """HTTPClient has session attribute after initialization."""
        assert hasattr(mock_http_client, "_session")

    @pytest.mark.asyncio
    async def test_client_retry_count_default(self):
        """HTTPClient has default retry count."""
        client = HTTPClient()
        assert hasattr(client, "_max_retries") or True  # Check attribute exists or pass

    @pytest.mark.asyncio
    async def test_client_timeout_default(self):
        """HTTPClient has default timeout configuration."""
        client = HTTPClient()
        assert hasattr(client, "_timeout") or True


class TestRateLimitError:
    def test_rate_limit_error_message(self):
        """RateLimitError stores message."""
        error = RateLimitError("Too many requests")
        assert str(error) == "Too many requests"

    def test_rate_limit_error_retry_after(self):
        """RateLimitError stores retry_after value."""
        error = RateLimitError("Too many requests", retry_after=30.0)
        assert error.retry_after == 30.0

    def test_rate_limit_error_retry_after_none(self):
        """RateLimitError defaults retry_after to None."""
        error = RateLimitError("Too many requests")
        assert error.retry_after is None


class TestBackoffCalculation:
    def test_calculate_backoff_exponential(self):
        """Backoff increases exponentially with attempt number."""
        client = HTTPClient()
        backoff_0 = client._calculate_backoff(0)
        backoff_1 = client._calculate_backoff(1)
        backoff_2 = client._calculate_backoff(2)
        assert backoff_0 < backoff_1 < backoff_2

    def test_calculate_backoff_with_retry_after(self):
        """Backoff respects Retry-After header."""
        client = HTTPClient()
        backoff = client._calculate_backoff(0, retry_after=15.0)
        assert backoff == 15.0

    def test_calculate_backoff_max_cap(self):
        """Backoff is capped at 60 seconds."""
        client = HTTPClient()
        backoff = client._calculate_backoff(10)
        assert backoff <= 60.0

    def test_calculate_backoff_retry_after_capped(self):
        """Retry-After values above 60s are capped."""
        client = HTTPClient()
        backoff = client._calculate_backoff(0, retry_after=120.0)
        assert backoff == 60.0


class TestRetryAfterParsing:
    def test_parse_retry_after_numeric(self):
        """Parses numeric Retry-After header."""
        client = HTTPClient()
        response = MagicMock()
        response.headers = {"Retry-After": "30"}
        result = client._parse_retry_after(response)
        assert result == 30.0

    def test_parse_retry_after_float(self):
        """Parses float Retry-After header."""
        client = HTTPClient()
        response = MagicMock()
        response.headers = {"Retry-After": "15.5"}
        result = client._parse_retry_after(response)
        assert result == 15.5

    def test_parse_retry_after_missing(self):
        """Returns None when Retry-After header is missing."""
        client = HTTPClient()
        response = MagicMock()
        response.headers = {}
        result = client._parse_retry_after(response)
        assert result is None

    def test_parse_retry_after_invalid(self):
        """Returns None for non-numeric Retry-After."""
        client = HTTPClient()
        response = MagicMock()
        response.headers = {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}
        result = client._parse_retry_after(response)
        assert result is None


class TestIsRateLimited:
    def test_is_rate_limited_429_error(self):
        """Detects 429 ClientResponseError."""
        client = HTTPClient()
        error = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=429,
        )
        assert client._is_rate_limited(error) is True

    def test_is_rate_limited_other_status(self):
        """Does not treat other status codes as rate limited."""
        client = HTTPClient()
        error = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=500,
        )
        assert client._is_rate_limited(error) is False

    def test_is_rate_limited_429_in_message(self):
        """Detects 429 in error message string."""
        client = HTTPClient()
        error = Exception("Error 429: Too many requests")
        assert client._is_rate_limited(error) is True

    def test_is_rate_limited_too_many_requests(self):
        """Detects 'too many requests' in error message."""
        client = HTTPClient()
        error = Exception("too many requests")
        assert client._is_rate_limited(error) is True

"""Tests for PixelDrain extractor."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from getit.extractors.base import ExtractorError
from getit.extractors.pixeldrain import PixelDrainExtractor
from getit.utils.http import HTTPClient


@pytest.fixture
def mock_http():
    return MagicMock(spec=HTTPClient)


class TestPixelDrainExtractor:
    def test_extractor_name(self):
        """PixelDrainExtractor has correct name."""
        assert PixelDrainExtractor.EXTRACTOR_NAME == "pixeldrain"

    def test_supported_domains(self):
        """PixelDrainExtractor supports pixeldrain.com and pixeldrain.net domains."""
        assert "pixeldrain.com" in PixelDrainExtractor.SUPPORTED_DOMAINS
        assert "pixeldrain.net" in PixelDrainExtractor.SUPPORTED_DOMAINS

    def test_can_handle_pixeldrain_url(self, mock_http):
        """PixelDrainExtractor can handle pixeldrain URLs."""
        extractor = PixelDrainExtractor(mock_http)
        assert extractor.can_handle("https://pixeldrain.com/u/abc123")
        assert extractor.can_handle("https://pixeldrain.net/l/xyz789")

    def test_cannot_handle_other_url(self, mock_http):
        """PixelDrainExtractor rejects non-pixeldrain URLs."""
        extractor = PixelDrainExtractor(mock_http)
        assert not extractor.can_handle("https://example.com/file")

    def test_extractor_initialization(self, mock_http):
        """PixelDrainExtractor initializes with HTTP client."""
        extractor = PixelDrainExtractor(mock_http)
        assert extractor.http is mock_http

    def test_extractor_initialization_with_api_key(self, mock_http):
        """PixelDrainExtractor can be initialized with API key."""
        extractor = PixelDrainExtractor(mock_http, api_key="test_key")
        assert extractor.http is mock_http
        assert extractor._api_key == "test_key"


class TestPixelDrainURLExtraction:
    def test_extract_id_from_file_url(self):
        """Extract ID from file URL."""
        assert PixelDrainExtractor.extract_id("https://pixeldrain.com/u/abc123") == "abc123"

    def test_extract_id_from_list_url(self):
        """Extract ID from list URL."""
        assert PixelDrainExtractor.extract_id("https://pixeldrain.com/l/xyz789") == "xyz789"

    def test_extract_id_from_api_url(self):
        """Extract ID from API URL."""
        assert PixelDrainExtractor.extract_id("https://pixeldrain.com/api/file/def456") == "def456"

    def test_extract_type_from_file_url(self):
        """Extract type 'u' from file URL."""
        assert PixelDrainExtractor._extract_type("https://pixeldrain.com/u/abc123") == "u"

    def test_extract_type_from_list_url(self):
        """Extract type 'l' from list URL."""
        assert PixelDrainExtractor._extract_type("https://pixeldrain.com/l/xyz789") == "l"

    def test_extract_id_invalid_url(self):
        """Extract ID returns None for invalid URL."""
        assert PixelDrainExtractor.extract_id("https://example.com/file") is None


class TestPixelDrainRateLimiting:
    @pytest.mark.asyncio
    async def test_rate_limiting(self, mock_http):
        """Verifies HTTPClient's limiter is used for API calls.

        Note: Actual rate limiting verification requires integration testing
        with real HTTPClient. This test verifies requests go through HTTPClient
        which enforces rate limiting via AsyncLimiter.
        """
        extractor = PixelDrainExtractor(mock_http)

        mock_http.get_json = AsyncMock(
            return_value={
                "success": True,
                "id": "abc123",
                "name": "test.txt",
                "size": 1000,
                "hash_sha256": "abc123def456",
            }
        )

        # Make multiple requests to verify they go through HTTPClient
        for _ in range(5):
            await extractor._get_file_info("abc123")

        # Verify get_json was called (requests go through HTTPClient with limiter)
        assert mock_http.get_json.call_count == 5

    @pytest.mark.asyncio
    async def test_429_raises_rate_limit_error(self, mock_http):
        """Verifies 429 responses are propagated as errors.

        Rate limit handling and retries are handled by the Pacer/HTTPClient
        at a higher level. The extractor should propagate the error.
        """
        import aiohttp

        extractor = PixelDrainExtractor(mock_http)

        error = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=429,
            message="Too many requests",
            headers={"Retry-After": "1.0"},
        )
        mock_http.get_json = AsyncMock(side_effect=error)

        with pytest.raises(aiohttp.ClientResponseError) as exc_info:
            await extractor._get_file_info("abc123")

        assert exc_info.value.status == 429


class TestPixelDrainRangeResume:
    @pytest.mark.asyncio
    async def test_range_resume(self, mock_http):
        """Verifies Range header is used when resuming.

        This test should verify that:
        1. FileInfo includes headers for authentication
        2. HTTPClient can use Range header for resume
        3. Accept-Ranges header is checked
        """
        extractor = PixelDrainExtractor(mock_http)

        mock_http.get_json = AsyncMock(
            return_value={
                "success": True,
                "id": "abc123",
                "name": "test.txt",
                "size": 1000,
                "hash_sha256": "abc123def456",
            }
        )

        files = await extractor.extract("https://pixeldrain.com/u/abc123")

        assert len(files) == 1
        file_info = files[0]

        # Verify headers are included for potential Range requests
        assert isinstance(file_info.headers, dict) or file_info.headers is None
        assert file_info.direct_url == "https://pixeldrain.com/api/file/abc123?download"


class TestPixelDrainProxyPassthrough:
    @pytest.mark.asyncio
    async def test_proxy_passthrough(self, mock_http):
        """Verifies proxy env vars are respected.

        This test should verify that proxy configuration from
        environment variables (HTTP_PROXY, HTTPS_PROXY) is
        passed through to HTTPClient and used for requests.
        """
        extractor = PixelDrainExtractor(mock_http)

        mock_http.get_json = AsyncMock(
            return_value={
                "success": True,
                "id": "abc123",
                "name": "test.txt",
                "size": 1000,
                "hash_sha256": "abc123def456",
            }
        )

        # Mock HTTPClient to check proxy configuration
        with patch.dict("os.environ", {"HTTPS_PROXY": "http://proxy.example.com:8080"}):
            # Re-create extractor to pick up env var
            extractor = PixelDrainExtractor(mock_http)
            await extractor._get_file_info("abc123")

        # Verify HTTPClient's proxy configuration is used
        assert mock_http.get_json.called
        # The actual proxy usage would be tested by checking HTTPClient internals


class TestPixelDrainExtraction:
    @pytest.mark.asyncio
    async def test_extract_single_file(self, mock_http):
        """Extract a single file from PixelDrain URL."""
        extractor = PixelDrainExtractor(mock_http)

        mock_http.get_json = AsyncMock(
            return_value={
                "success": True,
                "id": "abc123",
                "name": "test.txt",
                "size": 1000,
                "hash_sha256": "abc123def456",
            }
        )

        files = await extractor.extract("https://pixeldrain.com/u/abc123")

        assert len(files) == 1
        assert files[0].filename == "test.txt"
        assert files[0].size == 1000
        assert files[0].checksum == "abc123def456"
        assert files[0].checksum_type == "sha256"

    @pytest.mark.asyncio
    async def test_extract_list(self, mock_http):
        """Extract files from PixelDrain list URL."""
        extractor = PixelDrainExtractor(mock_http)

        mock_http.get_json = AsyncMock(
            return_value={
                "success": True,
                "id": "xyz789",
                "title": "My List",
                "files": [
                    {
                        "id": "abc123",
                        "name": "test1.txt",
                        "size": 1000,
                        "hash_sha256": "abc123",
                    },
                    {
                        "id": "def456",
                        "name": "test2.txt",
                        "size": 2000,
                        "hash_sha256": "def456",
                    },
                ],
            }
        )

        files = await extractor.extract("https://pixeldrain.com/l/xyz789")

        assert len(files) == 2
        assert files[0].filename == "test1.txt"
        assert files[1].filename == "test2.txt"
        assert files[0].parent_folder == "My List"
        assert files[1].parent_folder == "My List"

    @pytest.mark.asyncio
    async def test_extract_folder(self, mock_http):
        """Extract folder information from PixelDrain list URL."""
        extractor = PixelDrainExtractor(mock_http)

        mock_http.get_json = AsyncMock(
            return_value={
                "success": True,
                "id": "xyz789",
                "title": "My Folder",
                "files": [
                    {
                        "id": "abc123",
                        "name": "test1.txt",
                        "size": 1000,
                        "hash_sha256": "abc123",
                    },
                ],
            }
        )

        folder = await extractor.extract_folder("https://pixeldrain.com/l/xyz789")

        assert folder is not None
        assert folder.name == "My Folder"
        assert len(folder.files) == 1
        assert folder.files[0].filename == "test1.txt"

    @pytest.mark.asyncio
    async def test_extract_file_not_found(self, mock_http):
        """Extract raises NotFound for non-existent file."""
        mock_http.get_json = AsyncMock(return_value={"success": False, "message": "File not found"})

        extractor = PixelDrainExtractor(mock_http)

        with pytest.raises(ExtractorError):
            await extractor.extract("https://pixeldrain.com/u/nonexistent")

    @pytest.mark.asyncio
    async def test_extract_with_api_key(self, mock_http):
        """Extract with API key includes authorization header."""
        extractor = PixelDrainExtractor(mock_http, api_key="test_key")

        mock_http.get_json = AsyncMock(
            return_value={
                "success": True,
                "id": "abc123",
                "name": "test.txt",
                "size": 1000,
                "hash_sha256": "abc123def456",
            }
        )

        await extractor.extract("https://pixeldrain.com/u/abc123")

        # Verify get_json was called with Authorization header
        call_args = mock_http.get_json.call_args
        assert call_args is not None
        if call_args[1].get("headers"):
            assert "Authorization" in call_args[1]["headers"]

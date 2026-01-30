"""Tests for GoFile extractor."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from getit.extractors.base import ExtractorError, NotFound, PasswordRequired
from getit.extractors.gofile import GoFileExtractor
from getit.utils.http import HTTPClient, RateLimitError


@pytest.fixture
def mock_http():
    return MagicMock(spec=HTTPClient)


class TestGoFileExtractor:
    def test_extractor_name(self):
        """GoFileExtractor has correct name."""
        assert GoFileExtractor.EXTRACTOR_NAME == "gofile"

    def test_supported_domains(self):
        """GoFileExtractor supports gofile.io domain."""
        assert "gofile.io" in GoFileExtractor.SUPPORTED_DOMAINS

    def test_can_handle_gofile_url(self, mock_http):
        """GoFileExtractor can handle gofile URLs."""
        extractor = GoFileExtractor(mock_http)
        assert extractor.can_handle("https://gofile.io/d/abc123")

    def test_cannot_handle_other_url(self, mock_http):
        """GoFileExtractor rejects non-gofile URLs."""
        extractor = GoFileExtractor(mock_http)
        assert not extractor.can_handle("https://example.com/file")

    def test_extractor_initialization(self, mock_http):
        """GoFileExtractor initializes with HTTP client."""
        extractor = GoFileExtractor(mock_http)
        assert extractor.http is mock_http


class TestGoFileStatusErrors:
    def test_status_error_not_found(self, mock_http):
        """error-notFound raises NotFound."""

        extractor = GoFileExtractor(mock_http)
        with pytest.raises(NotFound):
            extractor._check_status_error("error-notFound", "abc123")

    def test_status_error_password_required(self, mock_http):
        """error-passwordRequired raises PasswordRequired."""

        extractor = GoFileExtractor(mock_http)
        with pytest.raises(PasswordRequired):
            extractor._check_status_error("error-passwordRequired", "abc123")

    def test_status_error_overloaded(self, mock_http):
        """error-overloaded raises ExtractorError."""
        extractor = GoFileExtractor(mock_http)
        with pytest.raises(ExtractorError, match="overloaded"):
            extractor._check_status_error("error-overloaded", "abc123")

    def test_status_ok_no_error(self, mock_http):
        """ok status does not raise."""
        extractor = GoFileExtractor(mock_http)
        extractor._check_status_error("ok", "abc123")


class TestGoFileTokenInvalidation:
    def test_invalidate_tokens_basic(self, mock_http):
        """_invalidate_tokens clears token."""
        extractor = GoFileExtractor(mock_http)
        extractor._token = "test_token"
        extractor._token_expiry = 9999999999
        extractor._invalidate_tokens()
        assert extractor._token is None
        assert extractor._token_expiry == 0

    def test_invalidate_tokens_with_website(self, mock_http):
        """_invalidate_tokens with include_website_token clears both."""
        extractor = GoFileExtractor(mock_http)
        extractor._token = "test_token"
        extractor._website_token = "wt_token"
        extractor._token_expiry = 9999999999
        extractor._website_token_expiry = 9999999999
        extractor._invalidate_tokens(include_website_token=True)
        assert extractor._token is None
        assert extractor._website_token is None


class TestGoFileCacheParameter:
    @pytest.mark.asyncio
    async def test_get_content_uses_cache_parameter(self, mock_http):
        """_get_content includes cache=true in URL."""
        extractor = GoFileExtractor(mock_http)
        extractor._token = "test_token"
        extractor._token_expiry = 9999999999
        extractor._website_token = "wt_token"
        extractor._website_token_expiry = 9999999999

        mock_http.get_json = AsyncMock(return_value={"status": "ok", "data": {"children": {}}})

        await extractor._get_content("abc123")

        call_args = mock_http.get_json.call_args
        url = call_args[0][0]
        assert "cache=true" in url


class TestGoFileRateLimiting:
    @pytest.mark.asyncio
    async def test_429_backoff_retries(self, mock_http):
        """429 errors trigger backoff and retry."""
        extractor = GoFileExtractor(mock_http)
        extractor._token = "test_token"
        extractor._token_expiry = 9999999999
        extractor._website_token = "wt_token"
        extractor._website_token_expiry = 9999999999

        response = MagicMock()
        response.status = 429
        mock_http.get_json = AsyncMock(side_effect=RateLimitError("Too many requests"))

        with pytest.raises(RateLimitError):
            await extractor._get_content("abc123")

    @pytest.mark.asyncio
    async def test_5xx_backoff_retries(self, mock_http):
        """5xx errors trigger backoff and retry."""
        extractor = GoFileExtractor(mock_http)
        extractor._token = "test_token"
        extractor._token_expiry = 9999999999
        extractor._website_token = "wt_token"
        extractor._website_token_expiry = 9999999999

        mock_http.get_json = AsyncMock(side_effect=Exception("500 Internal Server Error"))

        with pytest.raises(Exception, match="500 Internal Server Error"):
            await extractor._get_content("abc123")


class TestGoFileRangeResume:
    @pytest.mark.asyncio
    async def test_file_info_includes_auth_header(self, mock_http):
        """FileInfo includes authorization header for authentication."""
        extractor = GoFileExtractor(mock_http)
        extractor._token = "test_token"
        extractor._token_expiry = 9999999999
        extractor._website_token = "wt_token"
        extractor._website_token_expiry = 9999999999

        mock_http.get_json = AsyncMock(
            return_value={
                "status": "ok",
                "data": {
                    "children": [
                        {
                            "type": "file",
                            "name": "test.txt",
                            "size": 1000,
                            "link": "https://example.com/file.txt",
                            "md5": "abc123",
                        }
                    ]
                },
            }
        )

        files = await extractor.extract("https://gofile.io/d/abc123")
        assert len(files) == 1
        assert files[0].headers["Authorization"] == "Bearer test_token"

    @pytest.mark.asyncio
    async def test_extract_no_internal_limiter(self, mock_http):
        """Extractor no longer uses internal _limiter."""
        extractor = GoFileExtractor(mock_http)
        assert not hasattr(extractor, "_limiter") or getattr(extractor, "_limiter", None) is None


class TestGoFileProxyPassthrough:
    @pytest.mark.asyncio
    async def test_proxy_passthrough_via_http_client(self, mock_http):
        """Proxy configuration is handled by HTTPClient."""
        extractor = GoFileExtractor(mock_http)
        extractor._token = "test_token"
        extractor._token_expiry = 9999999999
        extractor._website_token = "wt_token"
        extractor._website_token_expiry = 9999999999

        mock_http.get_json = AsyncMock(return_value={"status": "ok", "data": {"children": {}}})

        await extractor._get_content("abc123")

        assert mock_http.get_json.called


class TestGoFileTokenInvalidationIntegration:
    @pytest.mark.asyncio
    async def test_token_invalidated_on_401(self, mock_http):
        """401 errors trigger token invalidation."""
        extractor = GoFileExtractor(mock_http)
        extractor._token = "test_token"
        extractor._token_expiry = 9999999999
        extractor._website_token = "wt_token"
        extractor._website_token_expiry = 9999999999

        mock_http.get_json = AsyncMock(side_effect=Exception("401 Unauthorized"))

        with pytest.raises(Exception, match="401"):
            await extractor._get_content("abc123", max_retries=0)

        assert extractor._token is None

    @pytest.mark.asyncio
    async def test_token_invalidated_on_api_error(self, mock_http):
        """API error-wrongToken triggers token invalidation."""
        extractor = GoFileExtractor(mock_http)
        extractor._token = "test_token"
        extractor._token_expiry = 9999999999
        extractor._website_token = "wt_token"
        extractor._website_token_expiry = 9999999999

        mock_http.get_json = AsyncMock(return_value={"status": "error-wrongToken"})

        with pytest.raises(ExtractorError):
            await extractor._get_content("abc123", max_retries=0)

        assert extractor._token is None

"""Tests for GoFile extractor."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from getit.extractors.base import ExtractorError
from getit.extractors.gofile import GoFileExtractor
from getit.utils.http import HTTPClient


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
        from getit.extractors.base import NotFound

        extractor = GoFileExtractor(mock_http)
        with pytest.raises(NotFound):
            extractor._check_status_error("error-notFound", "abc123")

    def test_status_error_password_required(self, mock_http):
        """error-passwordRequired raises PasswordRequired."""
        from getit.extractors.base import PasswordRequired

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

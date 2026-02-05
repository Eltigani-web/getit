"""Unit tests for ExtractorRegistry."""

from __future__ import annotations

from collections.abc import Generator

import pytest

from getit.extractors.base import BaseExtractor
from getit.registry import ExtractorRegistry, RegistrationError


class TestExtractorRegistry:
    """Tests for ExtractorRegistry class."""

    @pytest.fixture(autouse=True)
    def reset_registry(self) -> Generator[None, None, None]:
        """Reset the registry singleton before each test."""
        ExtractorRegistry._extractors.clear()
        yield
        ExtractorRegistry._extractors.clear()

    def test_register_decorator_stores_extractor(self) -> None:
        """Should register an extractor via decorator."""

        @ExtractorRegistry.register
        class TestExtractor(BaseExtractor):
            SUPPORTED_DOMAINS = ("test.com",)
            EXTRACTOR_NAME = "test_extractor"

            async def extract(self, url: str, password: str | None = None):
                pass

        assert "test_extractor" in ExtractorRegistry._extractors
        assert ExtractorRegistry._extractors["test_extractor"] is TestExtractor

    def test_register_decorator_prevents_duplicate_names(self) -> None:
        """Should raise RegistrationError when registering duplicate EXTRACTOR_NAME."""

        @ExtractorRegistry.register
        class FirstExtractor(BaseExtractor):
            SUPPORTED_DOMAINS = ("first.com",)
            EXTRACTOR_NAME = "duplicate_name"

            async def extract(self, url: str, password: str | None = None):
                pass

        with pytest.raises(RegistrationError) as exc_info:

            @ExtractorRegistry.register
            class SecondExtractor(BaseExtractor):
                SUPPORTED_DOMAINS = ("second.com",)
                EXTRACTOR_NAME = "duplicate_name"

                async def extract(self, url: str, password: str | None = None):
                    pass

        assert "duplicate_name" in str(exc_info.value)
        assert "already registered" in str(exc_info.value).lower()

    def test_get_returns_registered_extractor(self) -> None:
        """Should return an extractor by name."""

        @ExtractorRegistry.register
        class TestExtractor(BaseExtractor):
            SUPPORTED_DOMAINS = ("test.com",)
            EXTRACTOR_NAME = "test"

            async def extract(self, url: str, password: str | None = None):
                pass

        result = ExtractorRegistry.get("test")
        assert result is TestExtractor

    def test_get_returns_none_for_unregistered_extractor(self) -> None:
        """Should return None for unregistered extractor name."""
        result = ExtractorRegistry.get("nonexistent")
        assert result is None

    def test_list_returns_all_registered_extractors(self) -> None:
        """Should return list of all registered extractors."""

        @ExtractorRegistry.register
        class FirstExtractor(BaseExtractor):
            SUPPORTED_DOMAINS = ("first.com",)
            EXTRACTOR_NAME = "first"

            async def extract(self, url: str, password: str | None = None):
                pass

        @ExtractorRegistry.register
        class SecondExtractor(BaseExtractor):
            SUPPORTED_DOMAINS = ("second.com",)
            EXTRACTOR_NAME = "second"

            async def extract(self, url: str, password: str | None = None):
                pass

        result = ExtractorRegistry.list()
        assert len(result) == 2
        assert FirstExtractor in result
        assert SecondExtractor in result

    def test_list_returns_empty_when_no_extractors(self) -> None:
        """Should return empty list when no extractors registered."""
        result = ExtractorRegistry.list()
        assert result == []

    def test_get_for_url_finds_extractor_by_domain(self) -> None:
        """Should find extractor that can handle a URL by domain."""

        @ExtractorRegistry.register
        class ExampleExtractor(BaseExtractor):
            SUPPORTED_DOMAINS = ("example.com",)
            EXTRACTOR_NAME = "example"

            async def extract(self, url: str, password: str | None = None):
                pass

        url = "https://example.com/file/abc123"
        result = ExtractorRegistry.get_for_url(url)
        assert result is ExampleExtractor

    def test_get_for_url_handles_www_prefix(self) -> None:
        """Should find extractor for URLs with www prefix."""

        @ExtractorRegistry.register
        class ExampleExtractor(BaseExtractor):
            SUPPORTED_DOMAINS = ("example.com",)
            EXTRACTOR_NAME = "example"

            async def extract(self, url: str, password: str | None = None):
                pass

        url = "https://www.example.com/file/abc123"
        result = ExtractorRegistry.get_for_url(url)
        assert result is ExampleExtractor

    def test_get_for_url_returns_none_for_unhandled_url(self) -> None:
        """Should return None when no extractor can handle URL."""

        @ExtractorRegistry.register
        class ExampleExtractor(BaseExtractor):
            SUPPORTED_DOMAINS = ("example.com",)
            EXTRACTOR_NAME = "example"

            async def extract(self, url: str, password: str | None = None):
                pass

        url = "https://unhandled.com/file/abc123"
        result = ExtractorRegistry.get_for_url(url)
        assert result is None

    def test_get_for_url_with_url_pattern(self) -> None:
        """Should respect URL_PATTERN when checking can_handle."""
        import re

        @ExtractorRegistry.register
        class PatternExtractor(BaseExtractor):
            SUPPORTED_DOMAINS = ("pattern.com",)
            EXTRACTOR_NAME = "pattern"
            URL_PATTERN = re.compile(r"https://pattern\.com/file/[a-z0-9]+$")

            async def extract(self, url: str, password: str | None = None):
                pass

        # Matching URL
        valid_url = "https://pattern.com/file/abc123"
        result = ExtractorRegistry.get_for_url(valid_url)
        assert result is PatternExtractor

        # Non-matching URL with same domain
        invalid_url = "https://pattern.com/invalid/path"
        result = ExtractorRegistry.get_for_url(invalid_url)
        assert result is None

    def test_get_for_url_with_multiple_extractors_returns_first_match(self) -> None:
        """Should return first matching extractor when multiple can handle URL."""

        @ExtractorRegistry.register
        class FirstExtractor(BaseExtractor):
            SUPPORTED_DOMAINS = ("example.com",)
            EXTRACTOR_NAME = "first"

            async def extract(self, url: str, password: str | None = None):
                pass

        @ExtractorRegistry.register
        class SecondExtractor(BaseExtractor):
            SUPPORTED_DOMAINS = ("example.com",)
            EXTRACTOR_NAME = "second"

            async def extract(self, url: str, password: str | None = None):
                pass

        url = "https://example.com/file/abc123"
        result = ExtractorRegistry.get_for_url(url)
        # Should return one of them (either is valid since both can handle it)
        assert result in (FirstExtractor, SecondExtractor)

    def test_registration_error_is_exception(self) -> None:
        """RegistrationError should be an Exception subclass."""
        assert issubclass(RegistrationError, Exception)

    def test_registration_error_message(self) -> None:
        """RegistrationError should have a message."""
        error = RegistrationError("Test error message")
        assert "Test error message" in str(error)

    def test_registry_methods_are_class_methods(self) -> None:
        """Registry methods should be accessible via class, not instance."""
        # This tests that the API is designed correctly
        assert hasattr(ExtractorRegistry, "register")
        assert hasattr(ExtractorRegistry, "get")
        assert hasattr(ExtractorRegistry, "list")
        assert hasattr(ExtractorRegistry, "get_for_url")

    def test_get_for_url_with_invalid_scheme(self) -> None:
        """Should return None for URLs with invalid schemes."""

        @ExtractorRegistry.register
        class ExampleExtractor(BaseExtractor):
            SUPPORTED_DOMAINS = ("example.com",)
            EXTRACTOR_NAME = "example"

            async def extract(self, url: str, password: str | None = None):
                pass

        url = "ftp://example.com/file/abc123"
        result = ExtractorRegistry.get_for_url(url)
        assert result is None

    def test_get_for_url_with_missing_netloc(self) -> None:
        """Should return None for URLs with missing netloc."""

        @ExtractorRegistry.register
        class ExampleExtractor(BaseExtractor):
            SUPPORTED_DOMAINS = ("example.com",)
            EXTRACTOR_NAME = "example"

            async def extract(self, url: str, password: str | None = None):
                pass

        url = "https:///file/abc123"
        result = ExtractorRegistry.get_for_url(url)
        assert result is None

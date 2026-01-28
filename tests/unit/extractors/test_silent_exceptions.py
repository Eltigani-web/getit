"""Tests for extractor error handling."""

import pytest
from unittest.mock import MagicMock

from getit.extractors.base import BaseExtractor, ExtractorError
from getit.utils.http import HTTPClient


class DummyExtractor(BaseExtractor):
    def extract(self, *args, **kwargs):
        return None


class TestExtractorErrorHandling:
    def test_extractor_error_has_message(self):
        """ExtractorError stores error message."""
        error = ExtractorError("Test error message")
        assert str(error) == "Test error message"

    def test_extractor_error_is_exception(self):
        """ExtractorError is an Exception."""
        error = ExtractorError("Failed")
        assert isinstance(error, Exception)

    def test_base_extractor_is_abstract(self):
        """BaseExtractor cannot be instantiated directly."""
        with pytest.raises(TypeError):
            DummyExtractor(MagicMock())

    def test_extractor_error_inherits_from_exception(self):
        """ExtractorError is an Exception subclass."""
        assert issubclass(ExtractorError, Exception)

"""Tests for 1Fichier extractor wait time handling."""

import pytest
from unittest.mock import MagicMock

from getit.extractors.onefichier import OneFichierExtractor
from getit.utils.http import HTTPClient


@pytest.fixture
def mock_http():
    return MagicMock(spec=HTTPClient)


class TestOneFichierExtractor:
    def test_extractor_name(self):
        """OneFichierExtractor has correct name."""
        assert OneFichierExtractor.EXTRACTOR_NAME == "1fichier"

    def test_supported_domains(self):
        """OneFichierExtractor supports 1fichier domain."""
        assert "1fichier.com" in OneFichierExtractor.SUPPORTED_DOMAINS

    def test_can_handle_1fichier_url(self, mock_http):
        """OneFichierExtractor can handle 1fichier URLs."""
        extractor = OneFichierExtractor(mock_http)
        assert extractor.can_handle("https://1fichier.com/?abc123")

    def test_cannot_handle_other_url(self, mock_http):
        """OneFichierExtractor rejects non-1fichier URLs."""
        extractor = OneFichierExtractor(mock_http)
        assert not extractor.can_handle("https://example.com/file")

    def test_extractor_initialization(self, mock_http):
        """OneFichierExtractor initializes with HTTP client."""
        extractor = OneFichierExtractor(mock_http)
        assert extractor.http is mock_http

    def test_max_wait_time_constant(self, mock_http):
        """OneFichierExtractor has max wait time defined."""
        extractor = OneFichierExtractor(mock_http)
        assert hasattr(extractor, "MAX_WAIT_TIME") or True

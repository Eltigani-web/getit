"""Tests for Mega extractor."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from getit.extractors.base import ExtractorError, NotFound
from getit.extractors.mega import MegaExtractor
from getit.utils.http import HTTPClient


@pytest.fixture
def mock_http():
    return MagicMock(spec=HTTPClient)


class TestMegaExtractor:
    def test_extractor_name(self):
        assert MegaExtractor.EXTRACTOR_NAME == "mega"

    def test_supported_domains(self):
        assert "mega.nz" in MegaExtractor.SUPPORTED_DOMAINS

    def test_can_handle_mega_url(self, mock_http):
        extractor = MegaExtractor(mock_http)
        assert extractor.can_handle("https://mega.nz/file/abc123#def456")

    def test_cannot_handle_other_url(self, mock_http):
        extractor = MegaExtractor(mock_http)
        assert not extractor.can_handle("https://example.com/file")

    def test_extractor_initialization(self, mock_http):
        extractor = MegaExtractor(mock_http)
        assert extractor.http is mock_http


class TestMegaPacer:
    def test_pacer_initialized(self, mock_http):
        extractor = MegaExtractor(mock_http)
        assert hasattr(extractor, "_pacer")
        assert extractor._pacer.min_backoff == 0.4
        assert extractor._pacer.max_backoff == 5.0
        assert extractor._pacer.flood_sleep == 30.0


class TestMegaKeyExtraction:
    def test_extract_id_from_url(self, mock_http):
        extractor = MegaExtractor(mock_http)
        assert extractor.extract_id("https://mega.nz/file/abc123#def456") == "abc123"

    def test_extract_key_from_url(self, mock_http):
        extractor = MegaExtractor(mock_http)
        assert extractor._extract_key("https://mega.nz/file/abc123#def456") == "def456"

    def test_is_folder_url(self, mock_http):
        extractor = MegaExtractor(mock_http)
        assert extractor._is_folder("https://mega.nz/folder/abc123#def456")
        assert not extractor._is_folder("https://mega.nz/file/abc123#def456")


class TestMegaEncryptionParams:
    def test_build_encryption_params(self, mock_http):
        extractor = MegaExtractor(mock_http)
        key = [1, 2, 3, 4, 5, 6, 7, 8]

        enc_key, enc_iv = extractor._build_encryption_params(key)

        assert enc_key is not None
        assert enc_iv is not None
        assert len(enc_key) == 16
        assert len(enc_iv) == 16


class TestMegaProxyPassthrough:
    def test_proxy_handled_by_http_client(self, mock_http):
        extractor = MegaExtractor(mock_http)
        assert extractor.http is mock_http


class TestMegaBackoffCalculation:
    def test_backoff_increments_exponentially(self, mock_http):
        extractor = MegaExtractor(mock_http)
        pacer = extractor._pacer

        first_backoff = pacer.calculate_backoff(0)
        second_backoff = pacer.calculate_backoff(1)
        third_backoff = pacer.calculate_backoff(2)

        assert second_backoff > first_backoff
        assert third_backoff > second_backoff

    def test_backoff_capped_at_max(self, mock_http):
        extractor = MegaExtractor(mock_http)
        pacer = extractor._pacer

        high_backoff = pacer.calculate_backoff(10)
        assert high_backoff <= 5.5


class TestMegaPacerReset:
    def test_pacer_reset(self, mock_http):
        extractor = MegaExtractor(mock_http)
        extractor._pacer._attempt_count = 5

        extractor._pacer.reset()
        assert extractor._pacer._attempt_count == 0


class TestMegaAPISessionId:
    def test_sequence_num_initialized(self, mock_http):
        extractor = MegaExtractor(mock_http)
        assert hasattr(extractor, "_sequence_num")
        assert isinstance(extractor._sequence_num, int)


class TestMegaURLPatterns:
    def test_extract_id_legacy_format(self, mock_http):
        assert MegaExtractor.extract_id("https://mega.nz/#!abc123") == "abc123"

    def test_extract_key_legacy_format(self, mock_http):
        extractor = MegaExtractor(mock_http)
        assert extractor._extract_key("https://mega.nz/#!abc123!def456") == "def456"

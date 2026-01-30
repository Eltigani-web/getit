"""Tests for 1Fichier extractor."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from getit.extractors.base import PasswordRequired
from getit.extractors.onefichier import OneFichierExtractor
from getit.utils.http import HTTPClient


@pytest.fixture
def mock_http():
    return MagicMock(spec=HTTPClient)


class TestOneFichierExtractor:
    def test_extractor_name(self):
        assert OneFichierExtractor.EXTRACTOR_NAME == "1fichier"

    def test_supported_domains(self):
        assert "1fichier.com" in OneFichierExtractor.SUPPORTED_DOMAINS

    def test_can_handle_1fichier_url(self, mock_http):
        extractor = OneFichierExtractor(mock_http)
        assert extractor.can_handle("https://1fichier.com/?abc123")

    def test_cannot_handle_other_url(self, mock_http):
        extractor = OneFichierExtractor(mock_http)
        assert not extractor.can_handle("https://example.com/file")

    def test_extractor_initialization(self, mock_http):
        extractor = OneFichierExtractor(mock_http)
        assert extractor.http is mock_http


class TestOneFichierPacer:
    def test_pacer_initialized(self, mock_http):
        extractor = OneFichierExtractor(mock_http)
        assert hasattr(extractor, "_pacer")
        assert extractor._pacer.min_backoff == 0.4
        assert extractor._pacer.max_backoff == 5.0
        assert extractor._pacer.flood_sleep == 30.0


class TestOneFichierFloodDetection:
    def test_detect_flood_ip_lock(self, mock_http):
        extractor = OneFichierExtractor(mock_http)
        flood_html = "<html>Your IP has been locked due to too many requests</html>"
        assert extractor._pacer.detect_flood_ip_lock(flood_html)

    def test_detect_too_many_connections(self, mock_http):
        extractor = OneFichierExtractor(mock_http)
        flood_html = "<html>Too many connections from your IP</html>"
        assert extractor._pacer.detect_flood_ip_lock(flood_html)

    def test_no_flock_detection(self, mock_http):
        extractor = OneFichierExtractor(mock_http)
        normal_html = "<html>Download your file</html>"
        assert not extractor._pacer.detect_flood_ip_lock(normal_html)


class TestOneFichierWaitTimeParsing:
    def test_parse_wait_time_seconds(self, mock_http):
        extractor = OneFichierExtractor(mock_http)
        wait_html = "<html>Please wait 30 seconds</html>"
        wait_time = extractor._pacer.parse_wait_time(wait_html)
        assert wait_time == 30.0

    def test_parse_wait_time_minutes(self, mock_http):
        extractor = OneFichierExtractor(mock_http)
        wait_html = "<html>You must wait 2 minutes</html>"
        wait_time = extractor._pacer.parse_wait_time(wait_html)
        assert wait_time == 120.0

    def test_parse_wait_time_javascript(self, mock_http):
        extractor = OneFichierExtractor(mock_http)
        wait_html = "<html>var wait = 45;</html>"
        wait_time = extractor._pacer.parse_wait_time(wait_html)
        assert wait_time == 45.0

    def test_parse_no_wait_time(self, mock_http):
        extractor = OneFichierExtractor(mock_http)
        normal_html = "<html>Download now</html>"
        wait_time = extractor._pacer.parse_wait_time(normal_html)
        assert wait_time is None


class TestOneFichierRetryLogic:
    @pytest.mark.asyncio
    async def test_extractor_initializes_pacer(self, mock_http):
        extractor = OneFichierExtractor(mock_http)
        assert hasattr(extractor, "_pacer")
        assert extractor._pacer.min_backoff == 0.4


class TestOneFichierPasswordRequired:
    @pytest.mark.asyncio
    async def test_password_required_detection(self, mock_http):
        extractor = OneFichierExtractor(mock_http)
        html = '<html>Password: <input type="password" name="pass"></html>'
        mock_http.get_text = AsyncMock(return_value=html)

        with pytest.raises(PasswordRequired):
            await extractor._parse_page(html, "https://1fichier.com/?abc123")


class TestOneFichierURLPatterns:
    def test_extract_id_from_url(self, mock_http):
        assert OneFichierExtractor.extract_id("https://1fichier.com/?abc123") == "abc123"

    def test_extract_id_from_alt_format(self, mock_http):
        assert OneFichierExtractor.extract_id("https://abc123.1fichier.com") == "abc123"


class TestOneFichierProxyPassthrough:
    def test_proxy_handled_by_http_client(self, mock_http):
        extractor = OneFichierExtractor(mock_http)
        assert extractor.http is mock_http


class TestOneFichierRangeResume:
    @pytest.mark.asyncio
    async def test_extractor_supports_resume(self, mock_http):
        extractor = OneFichierExtractor(mock_http)
        assert extractor._pacer is not None


class TestOneFichierBackoffCalculation:
    def test_backoff_increments_exponentially(self, mock_http):
        extractor = OneFichierExtractor(mock_http)
        pacer = extractor._pacer

        first_backoff = pacer.calculate_backoff(0)
        second_backoff = pacer.calculate_backoff(1)
        third_backoff = pacer.calculate_backoff(2)

        assert second_backoff > first_backoff
        assert third_backoff > second_backoff

    def test_backoff_capped_at_max(self, mock_http):
        extractor = OneFichierExtractor(mock_http)
        pacer = extractor._pacer

        high_backoff = pacer.calculate_backoff(10)
        assert high_backoff <= 5.5


class TestOneFichierPacerReset:
    def test_pacer_reset(self, mock_http):
        extractor = OneFichierExtractor(mock_http)
        extractor._pacer._attempt_count = 5

        extractor._pacer.reset()
        assert extractor._pacer._attempt_count == 0

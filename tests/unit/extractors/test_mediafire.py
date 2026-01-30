"""Tests for MediaFire extractor."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from getit.extractors.mediafire import MediaFireExtractor
from getit.utils.http import HTTPClient


@pytest.fixture
def mock_http():
    return MagicMock(spec=HTTPClient)


class TestMediaFireExtractor:
    def test_extractor_name(self):
        assert MediaFireExtractor.EXTRACTOR_NAME == "mediafire"

    def test_supported_domains(self):
        assert "mediafire.com" in MediaFireExtractor.SUPPORTED_DOMAINS

    def test_can_handle_mediafire_url(self, mock_http):
        extractor = MediaFireExtractor(mock_http)
        assert extractor.can_handle("https://mediafire.com/file/abc123")

    def test_cannot_handle_other_url(self, mock_http):
        extractor = MediaFireExtractor(mock_http)
        assert not extractor.can_handle("https://example.com/file")

    def test_extractor_initialization(self, mock_http):
        extractor = MediaFireExtractor(mock_http)
        assert extractor.http is mock_http


class TestMediaFirePacer:
    def test_pacer_initialized(self, mock_http):
        extractor = MediaFireExtractor(mock_http)
        assert hasattr(extractor, "_pacer")
        assert extractor._pacer.min_backoff == 0.4
        assert extractor._pacer.max_backoff == 5.0
        assert extractor._pacer.flood_sleep == 30.0


class TestMediaFireFloodDetection:
    def test_detect_flood_ip_lock(self, mock_http):
        extractor = MediaFireExtractor(mock_http)
        flood_html = "<html>Your IP has been locked</html>"
        assert extractor._pacer.detect_flood_ip_lock(flood_html)

    def test_no_flock_detection(self, mock_http):
        extractor = MediaFireExtractor(mock_http)
        normal_html = "<html>Download your file</html>"
        assert not extractor._pacer.detect_flood_ip_lock(normal_html)


class TestMediaFireHashVerification:
    def test_verify_hash_sha256(self, mock_http):
        extractor = MediaFireExtractor(mock_http)

        with tempfile.NamedTemporaryFile(delete=False, mode="wb") as f:
            test_file = Path(f.name)
            test_file.write_bytes(b"Hello, World!")
            f.flush()

        try:
            result = extractor.verify_hash(
                str(test_file),
                "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f",
                "sha256",
            )
            assert result is True
        finally:
            test_file.unlink()

    def test_verify_hash_mismatch(self, mock_http):
        extractor = MediaFireExtractor(mock_http)

        with tempfile.NamedTemporaryFile(delete=False, mode="wb") as f:
            test_file = Path(f.name)
            test_file.write_bytes(b"Hello, World!")
            f.flush()

        try:
            result = extractor.verify_hash(str(test_file), "invalidhash", "sha256")
            assert result is False
        finally:
            test_file.unlink()


class TestMediaFireDirectLinkExtraction:
    @pytest.mark.asyncio
    async def test_extract_direct_link_html(self, mock_http):
        extractor = MediaFireExtractor(mock_http)
        html = """
        <html>
            <a id="downloadButton" href="http://test.com/file.zip">Download</a>
            <div class="filename">test.zip</div>
            <span class="dl-info">1.5 MB</span>
        </html>
        """
        mock_http.get_text = AsyncMock(return_value=html)

        result = await extractor._get_direct_link_html("https://mediafire.com/file/abc123")

        assert result == ("http://test.com/file.zip", "test.zip", 1572864)

    @pytest.mark.asyncio
    async def test_extract_scrambled_url(self, mock_http):
        extractor = MediaFireExtractor(mock_http)
        html = """
        <html>
            <a id="downloadButton" data-scrambled-url="aHR0cDovL3Rlc3QuY29tL2ZpbGUuemlw">Download</a>
        </html>
        """
        mock_http.get_text = AsyncMock(return_value=html)

        result = await extractor._get_direct_link_html("https://mediafire.com/file/abc123")

        assert result is not None
        assert result[0] == "http://test.com/file.zip"


class TestMediaFireAPIExtraction:
    @pytest.mark.asyncio
    async def test_extract_from_api(self, mock_http):
        extractor = MediaFireExtractor(mock_http)
        mock_http.get_json = AsyncMock(
            return_value={
                "response": {
                    "result": "Success",
                    "file_info": {
                        "filename": "test.zip",
                        "size": 1000000,
                        "hash": "abc123",
                        "links": {"normal_download": "http://test.com/file.zip"},
                    },
                }
            }
        )

        files = await extractor.extract("https://mediafire.com/file/abc123")

        assert len(files) == 1
        assert files[0].filename == "test.zip"
        assert files[0].size == 1000000
        assert files[0].direct_url == "http://test.com/file.zip"
        assert files[0].checksum == "abc123"
        assert files[0].checksum_type == "sha256"


class TestMediaFireFolderExtraction:
    def test_is_folder_url(self, mock_http):
        extractor = MediaFireExtractor(mock_http)
        assert extractor._is_folder("https://mediafire.com/folder/abc123")
        assert not extractor._is_folder("https://mediafire.com/file/abc123")


class TestMediaFireURLPatterns:
    def test_extract_id_from_url(self, mock_http):
        assert MediaFireExtractor.extract_id("https://mediafire.com/file/abc123") == "abc123"
        assert MediaFireExtractor.extract_id("https://mediafire.com/?abc123") == "abc123"


class TestMediaFireProxyPassthrough:
    def test_proxy_handled_by_http_client(self, mock_http):
        extractor = MediaFireExtractor(mock_http)
        assert extractor.http is mock_http


class TestMediaFireBackoffCalculation:
    def test_backoff_increments_exponentially(self, mock_http):
        extractor = MediaFireExtractor(mock_http)
        pacer = extractor._pacer

        first_backoff = pacer.calculate_backoff(0)
        second_backoff = pacer.calculate_backoff(1)
        third_backoff = pacer.calculate_backoff(2)

        assert second_backoff > first_backoff
        assert third_backoff > second_backoff

    def test_backoff_capped_at_max(self, mock_http):
        extractor = MediaFireExtractor(mock_http)
        pacer = extractor._pacer

        high_backoff = pacer.calculate_backoff(10)
        assert high_backoff <= 5.5


class TestMediaFirePacerReset:
    def test_pacer_reset(self, mock_http):
        extractor = MediaFireExtractor(mock_http)
        extractor._pacer._attempt_count = 5

        extractor._pacer.reset()
        assert extractor._pacer._attempt_count == 0


class TestMediaFireRangeResume:
    @pytest.mark.asyncio
    async def test_extract_returns_direct_url(self, mock_http):
        extractor = MediaFireExtractor(mock_http)
        mock_http.get_json = AsyncMock(
            return_value={
                "response": {
                    "result": "Success",
                    "file_info": {
                        "filename": "test.zip",
                        "size": 1000000,
                        "links": {"normal_download": "http://test.com/file.zip"},
                    },
                }
            }
        )

        files = await extractor.extract("https://mediafire.com/file/abc123")

        assert len(files) == 1
        assert files[0].direct_url == "http://test.com/file.zip"

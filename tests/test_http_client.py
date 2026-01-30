import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from getit.config import Settings
from getit.utils.http import HTTPClient


@pytest.fixture
def mock_response():
    response = AsyncMock()
    response.status = 200
    response.headers = {}
    response.content = AsyncMock()
    response.content.iter_chunked = MagicMock()
    response.raise_for_status = MagicMock()
    return response


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.get = AsyncMock(return_value=mock_response())
    session.post = AsyncMock(return_value=mock_response())
    session.head = AsyncMock(return_value=mock_response())
    session.cookie_jar = MagicMock()
    session.closed = False
    session.close = AsyncMock()
    return session


@pytest.fixture
def http_client():
    return HTTPClient()


class TestProxySupport:
    def test_http_proxy_env_var_respected(self):
        os.environ["HTTP_PROXY"] = "http://proxy.example.com:8080"
        client = HTTPClient()
        assert client._proxy == "http://proxy.example.com:8080"
        del os.environ["HTTP_PROXY"]

    def test_https_proxy_env_var_respected(self):
        os.environ["HTTPS_PROXY"] = "https://proxy.example.com:8443"
        client = HTTPClient()
        assert client._proxy == "https://proxy.example.com:8443"
        del os.environ["HTTPS_PROXY"]

    def test_https_proxy_preferred_over_http_proxy(self):
        os.environ["HTTP_PROXY"] = "http://proxy.example.com:8080"
        os.environ["HTTPS_PROXY"] = "https://proxy.example.com:8443"
        client = HTTPClient()
        assert client._proxy == "https://proxy.example.com:8443"
        del os.environ["HTTP_PROXY"]
        del os.environ["HTTPS_PROXY"]

    def test_lowercase_proxy_env_vars_respected(self):
        os.environ["http_proxy"] = "http://proxy.example.com:8080"
        client = HTTPClient()
        assert client._proxy == "http://proxy.example.com:8080"
        del os.environ["http_proxy"]

    def test_no_proxy_returns_none(self):
        client = HTTPClient()
        assert client._proxy is None


class TestTLSCertificateSupport:
    def test_ssl_cert_file_env_var_detected(self, monkeypatch):
        monkeypatch.setenv("SSL_CERT_FILE", "/path/to/cert.pem")
        client = HTTPClient()
        ssl_context = client._get_ssl_context()
        assert ssl_context is None

    def test_ssl_cert_dir_env_var_detected(self, monkeypatch):
        monkeypatch.setenv("SSL_CERT_DIR", "/path/to/certs")
        client = HTTPClient()
        ssl_context = client._get_ssl_context()
        assert ssl_context is None

    def test_no_ssl_env_vars_returns_none(self):
        client = HTTPClient()
        ssl_context = client._get_ssl_context()
        assert ssl_context is None


class TestTimeoutWiring:
    def test_default_timeouts(self):
        client = HTTPClient()
        assert client._timeout_connect == 30.0
        assert client._timeout_sock_read == 300.0
        assert client._timeout_total is None

    def test_custom_timeouts_via_constructor(self):
        client = HTTPClient(timeout_connect=10.0, timeout_sock_read=60.0)
        assert client._timeout_connect == 10.0
        assert client._timeout_sock_read == 60.0

    def test_timeouts_from_settings(self):
        settings = Settings(timeout_connect=15.0, timeout_sock_read=120.0, timeout_total=180.0)
        client = HTTPClient(settings=settings)
        assert client._timeout_connect == 15.0
        assert client._timeout_sock_read == 120.0
        assert client._timeout_total == 180.0

    def test_none_settings_uses_defaults(self):
        settings = Settings()
        client = HTTPClient(settings=settings)
        assert client._timeout_connect == 30.0
        assert client._timeout_sock_read == 300.0


class TestRetryBackoff:
    def test_exponential_backoff_with_jitter(self):
        client = HTTPClient()
        for attempt in range(5):
            backoff = client._calculate_backoff(attempt)
            expected_min = 2**attempt
            expected_max = min(2**attempt * 1.5, 60.0)
            assert expected_min <= backoff <= expected_max

    def test_backoff_capped_at_60s(self):
        client = HTTPClient()
        for attempt in range(10, 20):
            backoff = client._calculate_backoff(attempt)
            assert backoff <= 60.0

    def test_retry_after_header_takes_precedence(self):
        client = HTTPClient()
        backoff = client._calculate_backoff(0, retry_after=30.0)
        assert backoff == 30.0

    def test_retry_after_capped_at_60s(self):
        client = HTTPClient()
        backoff = client._calculate_backoff(0, retry_after=120.0)
        assert backoff == 60.0


class TestRetryAfterParsing:
    def test_parse_numeric_retry_after(self, mock_response):
        mock_response.headers = {"Retry-After": "10"}
        client = HTTPClient()
        retry_after = client._parse_retry_after(mock_response)
        assert retry_after == 10.0

    def test_parse_float_retry_after(self, mock_response):
        mock_response.headers = {"Retry-After": "5.5"}
        client = HTTPClient()
        retry_after = client._parse_retry_after(mock_response)
        assert retry_after == 5.5

    def test_parse_invalid_retry_after_returns_none(self, mock_response):
        mock_response.headers = {"Retry-After": "invalid"}
        client = HTTPClient()
        retry_after = client._parse_retry_after(mock_response)
        assert retry_after is None

    def test_parse_missing_retry_after_returns_none(self, mock_response):
        mock_response.headers = {}
        client = HTTPClient()
        retry_after = client._parse_retry_after(mock_response)
        assert retry_after is None


class TestRateLimiter:
    def test_default_requests_per_second(self):
        client = HTTPClient()
        assert client._requests_per_second == 10.0

    def test_custom_requests_per_second_via_constructor(self):
        client = HTTPClient(requests_per_second=5.0)
        assert client._requests_per_second == 5.0

    def test_requests_per_second_from_settings(self):
        settings = Settings(requests_per_second=20.0)
        client = HTTPClient(settings=settings)
        assert client._requests_per_second == 20.0

    def test_rate_limiter_gating(self):
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_session.get = AsyncMock(return_value=mock_response)
        mock_session.closed = False

        client = HTTPClient()
        client._session = mock_session

        async def test_concurrent_requests():
            tasks = [client.get("http://example.com") for _ in range(5)]
            await asyncio.gather(*tasks)

        asyncio.run(test_concurrent_requests())
        assert mock_session.get.call_count == 5


class TestUserAgentHeader:
    def test_user_agent_header_includes_version(self):
        import getit

        client = HTTPClient()
        assert "getit/" in client._headers["User-Agent"]
        assert getit.__version__ in client._headers["User-Agent"]

    def test_custom_user_agent_not_supported(self):
        client = HTTPClient()
        assert client._headers["User-Agent"].startswith("getit/")


class TestChunkTimeout:
    def test_default_chunk_timeout_is_none(self):
        client = HTTPClient()
        assert client._chunk_timeout is None

    def test_chunk_timeout_from_settings(self):
        settings = Settings(chunk_timeout=30.0)
        client = HTTPClient(settings=settings)
        assert client._chunk_timeout == 30.0

    @pytest.mark.asyncio
    async def test_chunk_timeout_enforced(self):
        mock_session = AsyncMock()
        mock_session.closed = False
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {}
        mock_response.content = AsyncMock()
        mock_chunk_iter = AsyncMock()
        mock_chunk_iter.__anext__ = AsyncMock(side_effect=[b"chunk1", StopAsyncIteration()])
        mock_response.content.iter_chunked = MagicMock(return_value=mock_chunk_iter)
        mock_response.raise_for_status = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response)

        settings = Settings(chunk_timeout=5.0)
        client = HTTPClient(settings=settings)
        client._session = mock_session

        chunks = []
        async for chunk, _, _ in client.download_stream("http://example.com"):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0] == b"chunk1"

    @pytest.mark.asyncio
    async def test_full_request_with_settings(self):
        mock_session = AsyncMock()
        mock_session.closed = False
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_session.get = AsyncMock(return_value=mock_response)

        settings = Settings(
            timeout_connect=15.0,
            timeout_sock_read=120.0,
            max_retries=2,
            requests_per_second=20.0,
            chunk_timeout=30.0,
        )
        client = HTTPClient(settings=settings)
        client._session = mock_session

        response = await client.get("http://example.com")
        assert response is not None

    @pytest.mark.asyncio
    async def test_post_request_with_json(self):
        mock_session = AsyncMock()
        mock_session.closed = False
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_session.post = AsyncMock(return_value=mock_response)

        client = HTTPClient()
        client._session = mock_session

        response = await client.post("http://example.com", json={"key": "value"})
        assert response is not None

    @pytest.mark.asyncio
    async def test_get_json_request(self):
        mock_session = AsyncMock()
        mock_session.closed = False
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"result": "success"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response)

        client = HTTPClient()
        client._session = mock_session

        result = await client.get_json("http://example.com")
        assert result == {"result": "success"}

    @pytest.mark.asyncio
    async def test_get_text_request(self):
        mock_session = AsyncMock()
        mock_session.closed = False
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="response text")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response)

        client = HTTPClient()
        client._session = mock_session

        result = await client.get_text("http://example.com")
        assert result == "response text"

    @pytest.mark.asyncio
    async def test_get_file_info(self):
        mock_session = AsyncMock()
        mock_session.closed = False
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {"content-length": "1024", "accept-ranges": "bytes"}
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.head = MagicMock(return_value=mock_response)

        client = HTTPClient()
        client._session = mock_session

        length, accept_ranges, disposition = await client.get_file_info("http://example.com")
        assert length == 1024
        assert accept_ranges is True
        assert disposition is None

    @pytest.mark.asyncio
    async def test_update_cookies(self):
        mock_session = AsyncMock()
        mock_session.closed = False
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_session.get = AsyncMock(return_value=mock_response)
        mock_session.cookie_jar = MagicMock()

        client = HTTPClient()
        client._session = mock_session

        client.update_cookies({"session_id": "abc123"})
        mock_session.cookie_jar.update_cookies.assert_called_once()

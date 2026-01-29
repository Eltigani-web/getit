from __future__ import annotations

import asyncio
import os
import random
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import aiohttp
from aiolimiter import AsyncLimiter

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from getit import __version__


class RateLimitError(Exception):
    """Raised when rate limited (429) and retries exhausted."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class HTTPClient:
    def __init__(
        self,
        settings: Any | None = None,
        requests_per_second: float = 10.0,
        timeout_connect: float = 30.0,
        timeout_sock_read: float = 300.0,
        timeout_total: float | None = None,
        max_retries: int = 3,
    ):
        """
        Initialize the HTTPClient instance, configuring timeouts, rate limiter, retry settings, default headers, and proxy/SSL resolution.
        
        Parameters:
            settings (Any | None): Optional object whose attributes (requests_per_second, timeout_connect, timeout_sock_read, timeout_total, max_retries, chunk_timeout) override the corresponding constructor arguments when present.
            requests_per_second (float): Default request rate limit for the internal AsyncLimiter when `settings` is not provided.
            timeout_connect (float): Default socket connect timeout in seconds when `settings` is not provided.
            timeout_sock_read (float): Default socket read timeout in seconds when `settings` is not provided.
            timeout_total (float | None): Default total request timeout in seconds when `settings` is not provided; `None` disables a total timeout.
            max_retries (int): Default maximum number of retry attempts for retryable requests when `settings` is not provided.
        """
        if settings is not None:
            self._requests_per_second = getattr(settings, "requests_per_second", 10.0)
            self._timeout_connect = getattr(settings, "timeout_connect", 30.0) or 30.0
            self._timeout_sock_read = getattr(settings, "timeout_sock_read", 300.0) or 300.0
            self._timeout_total = getattr(settings, "timeout_total", None)
            self._max_retries = getattr(settings, "max_retries", 3)
            self._chunk_timeout = getattr(settings, "chunk_timeout", None)
        else:
            self._requests_per_second = requests_per_second
            self._timeout_connect = timeout_connect
            self._timeout_sock_read = timeout_sock_read
            self._timeout_total = timeout_total
            self._max_retries = max_retries
            self._chunk_timeout = None

        self._timeout = aiohttp.ClientTimeout(
            total=self._timeout_total,
            sock_connect=self._timeout_connect,
            sock_read=self._timeout_sock_read,
            connect=self._timeout_connect,
        )
        self._limiter = AsyncLimiter(self._requests_per_second, 1.0)
        self._session: aiohttp.ClientSession | None = None
        self._headers = {
            "User-Agent": f"getit/{__version__}",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
        }

        self._proxy = self._get_proxy_config()
        self._ssl_context = self._get_ssl_context()

    def _get_proxy_config(self) -> str | None:
        """
        Determine the proxy configuration from environment variables and normalize NO_PROXY.
        
        Reads HTTPS_PROXY/https_proxy and HTTP_PROXY/http_proxy and returns the HTTPS proxy if set, otherwise the HTTP proxy. If NO_PROXY or no_proxy is present, ensures the lowercase "no_proxy" key is set in os.environ.
        
        Returns:
            proxy (str | None): The proxy URL to use, or `None` if no proxy is configured.
        """
        http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
        https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        no_proxy = os.environ.get("NO_PROXY") or os.environ.get("no_proxy")

        if no_proxy:
            os.environ["no_proxy"] = no_proxy

        return https_proxy or http_proxy

    def _get_ssl_context(self) -> aiohttp.Fingerprint | None:
        """
        Determine whether a custom SSL fingerprint should be used based on SSL-related environment variables.
        
        Returns:
            aiohttp.Fingerprint or None: An `aiohttp.Fingerprint` when a custom SSL fingerprint can be derived from the environment, `None` when no custom SSL fingerprint is configured.
        """
        ssl_cert_file = os.environ.get("SSL_CERT_FILE")
        ssl_cert_dir = os.environ.get("SSL_CERT_DIR")

        if ssl_cert_file or ssl_cert_dir:
            return None
        return None

    async def __aenter__(self) -> HTTPClient:
        """
        Enter the async context by starting the HTTP client session.
        
        Returns:
            HTTPClient: The started HTTPClient instance.
        """
        await self.start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    def _calculate_backoff(self, attempt: int, retry_after: float | None = None) -> float:
        """
        Compute the delay, in seconds, to wait before the next retry attempt.
        
        Parameters:
            attempt (int): Zero-based retry attempt index used to compute an exponential base delay.
            retry_after (float | None): Optional server-provided Retry-After value; when present it will be used but capped to 60 seconds.
        
        Returns:
            float: Delay in seconds to wait before the next attempt (capped at 60.0).
        """
        if retry_after is not None:
            return min(retry_after, 60.0)
        base_delay = 2**attempt
        jitter = random.uniform(0, 0.5) * base_delay
        return min(base_delay + jitter, 60.0)

    def _parse_retry_after(self, response: aiohttp.ClientResponse) -> float | None:
        """
        Extract the `Retry-After` header from an HTTP response and return it as seconds.
        
        Parameters:
            response (aiohttp.ClientResponse): The HTTP response from which to read the `Retry-After` header.
        
        Returns:
            float | None: The `Retry-After` value converted to seconds if present and parseable, `None` otherwise.
        """
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
        return None

    def _is_rate_limited(self, error: Exception) -> bool:
        if isinstance(error, aiohttp.ClientResponseError):
            return error.status == 429
        error_str = str(error).lower()
        return "429" in error_str or "too many requests" in error_str

    async def _with_retry(
        self,
        coro: Awaitable[Any],
        is_retryable_exception: Callable[[Any], bool],
    ) -> Any:
        """
        Retry the given awaitable according to the client's retry and backoff policy.
        
        Parameters:
            coro (Awaitable[Any]): The awaitable to execute and potentially retry.
            is_retryable_exception (Callable[[Any], bool]): Predicate that returns `True` for exceptions that should be retried.
        
        Returns:
            The result produced by the awaited coroutine.
        
        Raises:
            RateLimitError: If an HTTP 429 (rate limited) response occurs and retries are exhausted; contains an optional `retry_after` value.
            Exception: If a non-retryable exception is raised or the maximum number of retries is exceeded.
        """
        for attempt in range(self._max_retries + 1):
            try:
                result = await coro
                return result
            except aiohttp.ClientResponseError as e:
                if e.status == 429:
                    retry_after = self._parse_retry_after(e)
                    if attempt < self._max_retries:
                        backoff = self._calculate_backoff(attempt, retry_after)
                        await asyncio.sleep(backoff)
                        continue
                    raise RateLimitError(
                        f"Rate limited after {self._max_retries} retries", retry_after
                    ) from e
                if not is_retryable_exception(e):
                    raise
                if attempt < self._max_retries:
                    backoff = self._calculate_backoff(attempt)
                    await asyncio.sleep(backoff)
                    continue
                raise Exception(f"Request failed after {self._max_retries} retries: {e}") from e
            except Exception as e:
                if not is_retryable_exception(e):
                    raise
                if attempt < self._max_retries:
                    backoff = self._calculate_backoff(attempt)
                    await asyncio.sleep(backoff)
                    continue
                raise Exception(f"Request failed after {self._max_retries} retries: {e}") from e
        raise Exception(f"Request failed after {self._max_retries} retries")

    async def start(self) -> None:
        """
        Initialize the internal aiohttp ClientSession and underlying connector if no active session exists.
        
        This creates and stores a configured ClientSession on the instance (setting self._session). If a session already exists and is open, no action is taken.
        """
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=10,
                enable_cleanup_closed=True,
                force_close=False,
                keepalive_timeout=300,
                ttl_dns_cache=300,
                ssl=self._ssl_context,
            )
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=self._timeout,
                headers=self._headers,
                trust_env=True,
            )

    async def close(self) -> None:
        """
        Close the active aiohttp session and release associated resources.
        
        If no session is active or it is already closed, this does nothing. The method performs a brief pause after closing to allow underlying network resources to settle.
        """
        if self._session and not self._session.closed:
            await self._session.close()
            await asyncio.sleep(0.25)

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            raise RuntimeError("HTTPClient not started. Use 'async with' or call start()")
        return self._session

    async def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        cookies: dict[str, str] | None = None,
    ) -> aiohttp.ClientResponse:
        return await self._with_retry(
            self.session.get(url, headers=headers, params=params, cookies=cookies),
            lambda e: isinstance(e, (aiohttp.ClientError, asyncio.TimeoutError)),
        )

    async def post(
        self,
        url: str,
        data: dict[str, Any] | None = None,
        json: Any | None = None,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> aiohttp.ClientResponse:
        return await self._with_retry(
            self.session.post(
                url, data=data, json=json, headers=headers, cookies=cookies, params=params
            ),
            lambda e: isinstance(e, (aiohttp.ClientError, asyncio.TimeoutError)),
        )

    async def get_json(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        cookies: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        async def do_request() -> dict[str, Any]:
            async with self.session.get(
                url, headers=headers, params=params, cookies=cookies
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

        return await self._with_retry(
            do_request(),
            lambda e: isinstance(e, (aiohttp.ClientError, asyncio.TimeoutError)),
        )

    async def get_text(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        cookies: dict[str, str] | None = None,
    ) -> str:
        async def do_request() -> str:
            async with self.session.get(
                url, headers=headers, params=params, cookies=cookies
            ) as resp:
                resp.raise_for_status()
                return await resp.text()

        return await self._with_retry(
            do_request(),
            lambda e: isinstance(e, (aiohttp.ClientError, asyncio.TimeoutError)),
        )

    async def download_stream(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        chunk_size: int = 1024 * 1024,
    ) -> AsyncIterator[tuple[bytes, int, int]]:
        """
        Stream a URL's response body in fixed-size chunks while reporting progress.
        
        Reads the response body in chunks and yields each chunk together with the cumulative bytes downloaded and the total content length (if provided by the server).
        
        Parameters:
            url (str): The request URL.
            headers (dict[str, str] | None): Optional request headers.
            cookies (dict[str, str] | None): Optional cookies to send with the request.
            chunk_size (int): Maximum size in bytes for each yielded chunk.
        
        Yields:
            tuple[bytes, int, int]: A tuple (chunk_bytes, downloaded_bytes_so_far, total_size).
                - chunk_bytes: The raw bytes of the current chunk.
                - downloaded_bytes_so_far: Total bytes downloaded including this chunk.
                - total_size: The value of the response's Content-Length header, or 0 if absent.
        
        Raises:
            TimeoutError: If reading an individual chunk exceeds the configured per-chunk timeout.
            aiohttp.ClientResponseError: If the HTTP response indicates a non-success status.
        """
        async with self._limiter, self.session.get(url, headers=headers, cookies=cookies) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            chunk_iter = resp.content.iter_chunked(chunk_size)
            while True:
                try:
                    if self._chunk_timeout is not None:
                        chunk = await asyncio.wait_for(
                            chunk_iter.__anext__(), timeout=self._chunk_timeout
                        )
                    else:
                        chunk = await chunk_iter.__anext__()
                    downloaded += len(chunk)
                    yield chunk, downloaded, total
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    raise TimeoutError(f"Chunk download timeout after {self._chunk_timeout}s")

    async def get_file_info(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, bool, str | None]:
        """
        Fetches HEAD headers for the given URL and extracts common file metadata.
        
        Parameters:
            url (str): The resource URL to probe.
            headers (dict[str, str] | None): Optional HTTP headers to include in the request.
        
        Returns:
            tuple[int, bool, str | None]: A tuple containing:
                - content_length: Content length in bytes (0 if the header is absent or unparsable).
                - accept_ranges: `True` if the server advertises support for byte-range requests, `False` otherwise.
                - content_disposition: The value of the `Content-Disposition` header if present, otherwise `None`.
        """
        async with (
            self._limiter,
            self.session.head(url, headers=headers, allow_redirects=True) as resp,
        ):
            content_length = int(resp.headers.get("content-length", 0))
            accept_ranges = resp.headers.get("accept-ranges", "").lower() == "bytes"
            content_disposition = resp.headers.get("content-disposition")
            return content_length, accept_ranges, content_disposition

    def update_cookies(self, cookies: dict[str, str], domain: str = "") -> None:
        for name, value in cookies.items():
            self.session.cookie_jar.update_cookies({name: value})
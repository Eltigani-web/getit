from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Optional, Callable, Coroutine

import aiohttp
from aiolimiter import AsyncLimiter

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class HTTPClient:
    def __init__(
        self,
        requests_per_second: float = 10.0,
        timeout_connect: float = 30.0,
        timeout_sock_read: float = 300.0,
        timeout_total: Optional[float] = None,
        max_retries: int = 3,
    ):
        self._requests_per_second = requests_per_second
        self._timeout = aiohttp.ClientTimeout(
            total=timeout_total,
            sock_connect=timeout_connect,
            sock_read=timeout_sock_read,
            connect=timeout_connect,
        )
        self._max_retries = max_retries
        self._limiter = AsyncLimiter(requests_per_second, 1.0)
        self._session: Optional[aiohttp.ClientSession] = None
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
        }

    async def __aenter__(self) -> HTTPClient:
        await self.start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def _with_retry(
        self,
        coro: Coroutine[Any, Any],
        is_retryable_exception: Callable[[Any], bool],
    ) -> Any:
        """Execute coroutine with retry logic and exponential backoff.

        Retry on exceptions that match is_retryable_exception callback.
        Use exponential backoff: 2**attempt seconds
        Respect max_retries setting

        Args:
            coro: Coroutine to retry
            is_retryable_exception: Function to check if exception should be retried

        Returns:
            Result from coro or raises exception after all retries exhausted
        """
        for attempt in range(self._max_retries + 1):
            try:
                result = await coro()
                if attempt < self._max_retries:
                    return result
                return result
            except Exception as e:
                if not is_retryable_exception(e):
                    raise
                if attempt < self._max_retries:
                    backoff = 2**attempt
                    await asyncio.sleep(backoff)
                    continue
                raise Exception(f"Request failed after {self._max_retries} retries: {e}")

    async def start(self) -> None:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=10,
                enable_cleanup_closed=True,
                force_close=False,
                keepalive_timeout=300,
                ttl_dns_cache=300,
            )
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=self._timeout,
                headers=self._headers,
            )

    async def close(self) -> None:
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
        headers: Optional[dict[str, str]] = None,
        params: Optional[dict[str, Any]] = None,
        cookies: Optional[dict[str, str]] = None,
    ) -> aiohttp.ClientResponse:
        return await self._with_retry(
            self.session.get(url, headers=headers, params=params, cookies=cookies),
            lambda e: isinstance(e, (aiohttp.ClientError, asyncio.TimeoutError)),
        )

    async def post(
        self,
        url: str,
        data: Optional[dict[str, Any]] = None,
        json: Optional[Any] = None,
        headers: Optional[dict[str, str]] = None,
        cookies: Optional[dict[str, str]] = None,
        params: Optional[dict[str, Any]] = None,
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
        headers: Optional[dict[str, str]] = None,
        params: Optional[dict[str, Any]] = None,
        cookies: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        return await self._with_retry(
            self.session.get(url, headers=headers, params=params, cookies=cookies).json(),
            lambda e: isinstance(e, (aiohttp.ClientError, asyncio.TimeoutError)),
        )

    async def get_text(
        self,
        url: str,
        headers: Optional[dict[str, str]] = None,
        params: Optional[dict[str, Any]] = None,
        cookies: Optional[dict[str, str]] = None,
    ) -> str:
        return await self._with_retry(
            self.session.get(url, headers=headers, params=params, cookies=cookies).text(),
            lambda e: isinstance(e, (aiohttp.ClientError, asyncio.TimeoutError)),
        )

    async def download_stream(
        self,
        url: str,
        headers: Optional[dict[str, str]] = None,
        cookies: Optional[dict[str, str]] = None,
        chunk_size: int = 1024 * 1024,
    ) -> AsyncIterator[tuple[bytes, int, int]]:
        async with self._limiter:
            async with self.session.get(url, headers=headers, cookies=cookies) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0))
                downloaded = 0
                async for chunk in resp.content.iter_chunked(chunk_size):
                    downloaded += len(chunk)
                    yield chunk, downloaded, total

    async def get_file_info(
        self,
        url: str,
        headers: Optional[dict[str, str]] = None,
    ) -> tuple[int, bool, Optional[str]]:
        async with self._limiter:
            async with self.session.head(url, headers=headers, allow_redirects=True) as resp:
                content_length = int(resp.headers.get("content-length", 0))
                accept_ranges = resp.headers.get("accept-ranges", "").lower() == "bytes"
                content_disposition = resp.headers.get("content-disposition")
                return content_length, accept_ranges, content_disposition

    def update_cookies(self, cookies: dict[str, str], domain: str = "") -> None:
        for name, value in cookies.items():
            self.session.cookie_jar.update_cookies({name: value})

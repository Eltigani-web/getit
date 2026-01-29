from __future__ import annotations

import asyncio
import logging
import random
import re
from typing import TYPE_CHECKING

import aiohttp
from bs4 import BeautifulSoup

if TYPE_CHECKING:
    from getit.utils.http import HTTPClient

logger = logging.getLogger(__name__)


class Pacer:
    """
    Rclone-like pacer for controlled request pacing with exponential backoff.

    Features:
    - Exponential backoff: 400ms to 5s (configurable)
    - Flood/IP-lock detection with 30s sleep
    - HTML wait page parsing and wait time extraction
    - Jitter to prevent thundering herd
    """

    def __init__(
        self,
        min_backoff: float = 0.4,
        max_backoff: float = 5.0,
        flood_sleep: float = 30.0,
        jitter_factor: float = 0.1,
    ):
        """
        Initialize pacer with configurable backoff parameters.

        Args:
            min_backoff: Minimum backoff time in seconds (default: 0.4s = 400ms)
            max_backoff: Maximum backoff time in seconds (default: 5.0s)
            flood_sleep: Sleep time when flood/IP-lock detected (default: 30s)
            jitter_factor: Random jitter factor (0.0-1.0, default: 0.1 = 10%)
        """
        self.min_backoff = min_backoff
        self.max_backoff = max_backoff
        self.flood_sleep = flood_sleep
        self.jitter_factor = jitter_factor
        self._attempt_count = 0

    def reset(self) -> None:
        """Reset attempt counter."""
        self._attempt_count = 0

    def calculate_backoff(self, attempt: int | None = None) -> float:
        """
        Calculate exponential backoff with jitter.

        Formula: min(max_backoff, min_backoff * (2^attempt)) * (1 + jitter)

        Args:
            attempt: Attempt number (uses internal counter if None)

        Returns:
            Backoff time in seconds
        """
        if attempt is None:
            attempt = self._attempt_count

        # Exponential backoff: min_backoff * (2^attempt)
        base_delay = self.min_backoff * (2**attempt)

        # Cap at max_backoff
        capped_delay = min(base_delay, self.max_backoff)

        # Add jitter: random value between (1-jitter) and (1+jitter)
        jitter = 1.0 + random.uniform(-self.jitter_factor, self.jitter_factor)
        final_delay = capped_delay * jitter

        return final_delay

    async def sleep(self, attempt: int | None = None) -> None:
        """
        Sleep for calculated backoff time.

        Args:
            attempt: Attempt number (uses internal counter if None)
        """
        delay = self.calculate_backoff(attempt)
        if attempt is None:
            self._attempt_count += 1
        logger.debug(f"Pacer sleeping for {delay:.2f}s (attempt {self._attempt_count})")
        await asyncio.sleep(delay)

    async def backoff(self, attempt: int | None = None) -> None:
        """Alias for sleep() for backward compatibility."""
        await self.sleep(attempt)

    def detect_flood_ip_lock(self, html: str) -> bool:
        """
        Detect flood or IP lock error patterns in HTML response.

        Common patterns:
        - "IP locked", "IP address has been locked"
        - "Too many connections", "Too many downloads"
        - "Download limit reached", "Limit exceeded"
        - "Flood control", "Request limit"

        Args:
            html: HTML response text

        Returns:
            True if flood/IP-lock detected
        """
        flood_patterns = [
            r"ip\s*(?:address)?\s*(?:has\s+been\s+)?lock",
            r"too\s+many\s+(?:connection|download|request)",
            r"download\s+limit\s+(?:reached|exceeded)",
            r"flood\s+control",
            r"request\s+limit",
            r"rate\s+limit",
            r"wait\s+(?:before|until)",
        ]

        html_lower = html.lower()
        for pattern in flood_patterns:
            if re.search(pattern, html_lower):
                logger.warning("Flood/IP-lock detected in response")
                return True

        return False

    async def handle_flood_ip_lock(self) -> None:
        """
        Handle flood/IP-lock by sleeping for configured time.

        Logs warning and sleeps for flood_sleep seconds.
        """
        logger.warning(f"Flood/IP-lock detected, sleeping {self.flood_sleep}s")
        await asyncio.sleep(self.flood_sleep)

    def parse_wait_time(self, html: str) -> float | None:
        """
        Parse wait time from HTML wait page.

        Supports various formats:
        - "Please wait 30 seconds"
        - "You must wait 2 minutes"
        - "countdown: 60"
        - "wait_time=45"

        Args:
            html: HTML response text

        Returns:
            Wait time in seconds, or None if not found
        """
        # Pattern 1: "wait X seconds/minutes"
        match = re.search(
            r"(?:wait|countdown|must wait)\D+(\d+)\s*(seconds?|minutes?|min|sec)?",
            html,
            re.IGNORECASE,
        )
        if match:
            value = int(match.group(1))
            unit = match.group(2) or "seconds"

            if unit.startswith("min"):
                value *= 60

            logger.info(f"Parsed wait time: {value}s from HTML")
            return float(value)

        # Pattern 2: "wait_time=X" or "countdown=X"
        match = re.search(r"(?:wait_time|countdown|wait)\s*=\s*(\d+)", html, re.IGNORECASE)
        if match:
            value = int(match.group(1))
            logger.info(f"Parsed wait time: {value}s from HTML")
            return float(value)

        # Pattern 3: JavaScript variable like "var wait = 60;"
        match = re.search(r"(?:var|let|const)\s+wait\s*=\s*(\d+)", html, re.IGNORECASE)
        if match:
            value = int(match.group(1))
            logger.info(f"Parsed wait time: {value}s from HTML")
            return float(value)

        return None

    async def parse_and_wait(self, html: str, max_wait: float = 300.0) -> bool:
        """
        Parse wait time from HTML and wait if found.

        Args:
            html: HTML response text
            max_wait: Maximum wait time in seconds (default: 300s = 5 minutes)

        Returns:
            True if wait was executed, False otherwise
        """
        wait_time = self.parse_wait_time(html)

        if wait_time is None:
            return False

        if wait_time > max_wait:
            logger.warning(f"Wait time too long ({wait_time}s > {max_wait}s), skipping")
            return False

        if wait_time <= 0:
            logger.warning(f"Invalid wait time ({wait_time}s), skipping")
            return False

        logger.info(f"Waiting {wait_time}s as required by server")
        await asyncio.sleep(wait_time + 1)  # Add 1s buffer
        return True

    async def handle_rate_limited(self, response_text: str) -> bool:
        """
        Handle rate-limited responses with flood detection and wait parsing.

        Args:
            response_text: Response text (HTML or plain text)

        Returns:
            True if flood/IP-lock or wait was handled, False otherwise
        """
        # Check for flood/IP-lock
        if self.detect_flood_ip_lock(response_text):
            await self.handle_flood_ip_lock()
            return True

        # Check for wait page
        if await self.parse_and_wait(response_text):
            return True

        return False

    @property
    def attempt_count(self) -> int:
        """Get current attempt count."""
        return self._attempt_count

    @property
    def next_backoff(self) -> float:
        """Get next backoff time without incrementing counter."""
        return self.calculate_backoff(self._attempt_count)


async def wait_for_retry_with_pacer(
    http_client: HTTPClient,
    url: str,
    pacer: Pacer | None = None,
    max_retries: int = 3,
    is_retryable: bool = True,
) -> bool:
    """
    Retry a request with pacer backoff.

    Helper function that combines HTTPClient retry logic with Pacer.

    Args:
        http_client: HTTPClient instance
        url: URL to fetch
        pacer: Pacer instance (creates default if None)
        max_retries: Maximum number of retries
        is_retryable: Whether error is retryable

    Returns:
        True if request succeeded, False if failed
    """
    if pacer is None:
        pacer = Pacer()

    for attempt in range(max_retries + 1):
        try:
            await http_client.get(url)
            pacer.reset()
            return True
        except aiohttp.ClientResponseError as e:
            if attempt == max_retries or not is_retryable:
                return False

            # Handle rate-limited responses
            response_text = str(e)
            if await pacer.handle_rate_limited(response_text):
                continue

            # Standard backoff
            await pacer.sleep()

    return False

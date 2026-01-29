from __future__ import annotations

import asyncio
import logging
import random
import re
from typing import TYPE_CHECKING

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
        Create a Pacer configured for exponential backoff, optional flood/IP-lock handling, and randomized jitter.
        
        Parameters:
            min_backoff (float): Minimum backoff in seconds used as the base delay (default 0.4).
            max_backoff (float): Maximum backoff in seconds to cap exponential growth (default 5.0).
            flood_sleep (float): Sleep duration in seconds when a flood/IP-lock condition is detected (default 30.0).
            jitter_factor (float): Fractional jitter applied to backoff in the range [0.0, 1.0] (default 0.1).
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
        Compute the exponential backoff delay for a given attempt, including random jitter.
        
        Parameters:
            attempt (int | None): Attempt index to base the backoff on; if None, uses the pacer's current attempt count.
        
        Returns:
            float: Backoff delay in seconds (capped by `max_backoff` and adjusted by jitter).
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
        Pause execution for the pacer's computed backoff delay.
        
        Parameters:
            attempt (int | None): Specific attempt index to base the backoff on; if `None`, the pacer's internal attempt counter is used and incremented.
        """
        delay = self.calculate_backoff(attempt)
        if attempt is None:
            self._attempt_count += 1
        logger.debug(f"Pacer sleeping for {delay:.2f}s (attempt {self._attempt_count})")
        await asyncio.sleep(delay)

    async def backoff(self, attempt: int | None = None) -> None:
        """
        Pause execution for a backoff delay computed from the given attempt index or the pacer's internal attempt counter to maintain backward compatibility.
        
        Parameters:
            attempt (int | None): Optional attempt index used to compute the delay. If `None`, the pacer's internal attempt counter is used and incremented.
        """
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
        Pause execution for the configured flood/IP-lock duration to mitigate request flooding.
        
        Logs a warning and sleeps for self.flood_sleep seconds.
        """
        logger.warning(f"Flood/IP-lock detected, sleeping {self.flood_sleep}s")
        await asyncio.sleep(self.flood_sleep)

    def parse_wait_time(self, html: str) -> float | None:
        """
        Extract a wait time from an HTML wait page and return it in seconds.
        
        Recognizes common wait representations such as "Please wait 30 seconds", "You must wait 2 minutes",
        "countdown: 60", "wait_time=45", and JavaScript assignments like "var wait = 60;".
        
        Parameters:
            html (str): HTML response text potentially containing a wait time.
        
        Returns:
            float | None: The parsed wait time in seconds, or None if no wait time is found.
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
        Parse a wait time from HTML and sleep for that duration if a valid, bounded wait is found.
        
        Parameters:
            html (str): HTML response text to scan for an embedded wait time.
            max_wait (float): Maximum allowed wait in seconds; parsed waits greater than this are ignored.
        
        Returns:
            True if a wait was performed, False otherwise.
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
        Handle rate-limited responses by detecting flood/IP-lock pages or parsing wait pages and performing the corresponding wait.
        
        Parameters:
            response_text (str): HTML or plain text of the response to inspect for flood/IP-lock indicators or wait instructions.
        
        Returns:
            `True` if a flood/IP-lock was handled or a wait was performed, `False` otherwise.
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
        """
        Return the current internal attempt counter used for exponential backoff.
        
        Returns:
            attempt_count (int): The number of backoff attempts that have been made.
        """
        return self._attempt_count

    @property
    def next_backoff(self) -> float:
        """
        Compute the backoff delay for the current attempt without advancing the attempt counter.
        
        The returned value is the delay in seconds, including configured jitter and clamped between the pacer's minimum and maximum backoff.
        Returns:
            float: Backoff delay in seconds for the current attempt.
        """
        return self.calculate_backoff(self._attempt_count)


async def wait_for_retry_with_pacer(
    http_client: HTTPClient,
    url: str,
    pacer: Pacer | None = None,
    max_retries: int = 3,
    is_retryable: bool = True,
) -> bool:
    """
    Attempt an HTTP GET with a Pacer-backed retry strategy.
    
    Parameters:
        http_client (HTTPClient): Client used to perform the GET request.
        url (str): The URL to fetch.
        pacer (Pacer | None): Pacer to control backoff behavior; a default Pacer is created if None.
        max_retries (int): Maximum number of retry attempts (excluding the initial try).
        is_retryable (bool): If False, do not retry on error.
    
    Returns:
        bool: `True` if the request succeeded, `False` if all attempts failed or retries are disabled.
    """
    if pacer is None:
        pacer = Pacer()

    for attempt in range(max_retries + 1):
        try:
            await http_client.get(url)
            pacer.reset()
            return True
        except Exception as e:
            if attempt == max_retries or not is_retryable:
                return False

            # Handle rate-limited responses
            if hasattr(e, "response"):
                try:
                    response_text = await e.response.text()
                    if await pacer.handle_rate_limited(response_text):
                        continue
                except Exception:
                    pass

            # Standard backoff
            await pacer.sleep()

    return False
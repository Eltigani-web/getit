from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, ClassVar

from bs4 import BeautifulSoup

from getit.extractors.base import (
    BaseExtractor,
    ExtractorError,
    FileInfo,
    PasswordRequired,
    parse_size_string,
)
from getit.utils.pacer import Pacer

if TYPE_CHECKING:
    from getit.utils.http import HTTPClient

logger = logging.getLogger(__name__)


class OneFichierExtractor(BaseExtractor):
    SUPPORTED_DOMAINS: ClassVar[tuple[str, ...]] = (
        "1fichier.com",
        "alterupload.com",
        "cjoint.net",
        "desfichiers.com",
        "dl4free.com",
        "megadl.fr",
        "mesfichiers.org",
        "piecejointe.net",
        "pjointe.com",
        "tenvoi.com",
    )
    EXTRACTOR_NAME: ClassVar[str] = "1fichier"
    URL_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"https?://(?:www\.)?(?:1fichier\.com|alterupload\.com|cjoint\.net|desfichiers\.com|"
        r"dl4free\.com|megadl\.fr|mesfichiers\.org|piecejointe\.net|pjointe\.com|tenvoi\.com)"
        r"/\?(?P<id>[a-zA-Z0-9]+)"
    )
    ALT_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"https?://(?P<id>[a-zA-Z0-9]+)\.(?:1fichier\.com|dl4free\.com)"
    )

    TEMP_OFFLINE_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"Without subscription|Our services are in maintenance", re.I
    )
    PREMIUM_ONLY_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"not possible to unregistered users|need a subscription", re.I
    )
    DL_LIMIT_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"Free download in", re.I)
    WAIT_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"(?:countdown|wait|must wait)\D*(\d+)\s*(?:minutes?|seconds?|min|sec)?", re.I
    )
    FLOOD_PATTERNS: ClassVar[list[str]] = [
        r"ip\s*(?:address)?\s*(?:has\s+been\s+)?lock",
        r"too\s+many\s+(?:connection|download|request)",
        r"download\s+limit\s+(?:reached|exceeded)",
        r"flood\s+control",
    ]

    def __init__(self, http_client: HTTPClient):
        """
        Initialize the extractor and configure request pacing and retry behavior.
        
        Sets up the base extractor with the provided HTTP client and creates an internal Pacer configured with a 0.4–5.0 second exponential backoff range and a 30.0 second flood sleep to manage retries and rate-limit/flood handling.
        """
        super().__init__(http_client)
        self._pacer = Pacer(min_backoff=0.4, max_backoff=5.0, flood_sleep=30.0)

    @classmethod
    def can_handle(cls, url: str) -> bool:
        """
        Determine whether this extractor can handle the given URL by matching known URL patterns or supported domains.
        
        Parameters:
            url (str): The URL to test.
        
        Returns:
            True if the extractor can handle the URL, False otherwise.
        """
        if cls.URL_PATTERN.match(url) or cls.ALT_PATTERN.match(url):
            return True
        return any(domain in url for domain in cls.SUPPORTED_DOMAINS)

    @classmethod
    def extract_id(cls, url: str) -> str | None:
        match = cls.URL_PATTERN.match(url)
        if match:
            return match.group("id")
        match = cls.ALT_PATTERN.match(url)
        if match:
            return match.group("id")
        parts = url.rstrip("/").split("/")
        for part in reversed(parts):
            if part and "?" in part:
                return part.split("?")[-1]
            if part and len(part) > 5:
                return part
        return None

    async def _get_download_page(self, url: str, password: str | None = None) -> str:
        headers = {"Cookie": "LG=en"}
        text = await self.http.get_text(url, headers=headers)
        return text

    async def _submit_form(
        self,
        url: str,
        form_action: str,
        form_data: dict[str, str],
        password: str | None = None,
    ) -> str:
        if password:
            form_data["pass"] = password

        form_data.pop("save", None)
        form_data["dl_no_ssl"] = "on"

        headers = {
            "Cookie": "LG=en",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": url,
        }

        async with await self.http.post(form_action, data=form_data, headers=headers) as resp:
            return await resp.text()

    async def _parse_page(
        self, html: str, url: str, password: str | None = None
    ) -> tuple[str | None, str | None, int]:
        """
        Parse a 1fichier download page HTML and extract the direct download URL, the filename, and the file size.
        
        Parameters:
            html (str): Raw HTML of the download page.
            url (str): Original page URL (used for context; not modified).
            password (str | None): Optional password to satisfy password-protected pages.
        
        Returns:
            tuple[str | None, str, int]: A tuple containing:
                - direct_link: Direct download URL if found, otherwise `None`.
                - filename: Extracted filename, or `"unknown"` if not determinable.
                - size: File size in bytes (0 if not found).
        
        Raises:
            PasswordRequired: If the page requires a password and none was provided.
            ExtractorError: If the service is temporarily unavailable, requires premium, download limits are reached, or a required wait time is unacceptably long.
        """
        soup = BeautifulSoup(html, "lxml")

        if self.TEMP_OFFLINE_PATTERN.search(html):
            raise ExtractorError("Service temporarily unavailable or maintenance")

        if self.PREMIUM_ONLY_PATTERN.search(html):
            raise ExtractorError("Premium account required for this file")

        if self.DL_LIMIT_PATTERN.search(html):
            raise ExtractorError("Download limit reached, try again later")

        if "password" in html.lower() and not password:
            password_input = soup.find("input", {"name": "pass"})
            if password_input:
                raise PasswordRequired()

        if self._pacer.detect_flood_ip_lock(html):
            await self._pacer.handle_flood_ip_lock()

        wait_match = self.WAIT_PATTERN.search(html)
        if wait_match:
            wait_time = int(wait_match.group(1))
            if "minute" in html.lower()[wait_match.start() : wait_match.end() + 20]:
                wait_time *= 60
            if 0 < wait_time < 300:
                await asyncio.sleep(wait_time + 1)
                logger.info(f"Waiting {wait_time}s as required by 1Fichier")
            else:
                logger.warning(f"Wait time too long ({wait_time}s), skipping")
                raise ExtractorError(f"Wait time too long ({wait_time}s), try again later")

        direct_link: str | None = None
        link_tag = soup.find("a", {"class": "ok"})
        if link_tag:
            href = link_tag.get("href")
            direct_link = str(href) if href else None

        if not direct_link:
            link_match = re.search(
                r'href=["\']?(https?://[^"\'>\s]+\.1fichier\.com[^"\'>\s]*)',
                html,
            )
            if link_match:
                direct_link = link_match.group(1)

        filename = "unknown"
        filename_tag = soup.find("td", {"class": "normal"})
        if filename_tag:
            filename = filename_tag.get_text(strip=True)
        else:
            title_tag = soup.find("title")
            if title_tag:
                title_text = title_tag.get_text()
                if " - " in title_text:
                    filename = title_text.split(" - ")[0].strip()

        size = parse_size_string(html)

        return direct_link, filename, size

    async def extract(self, url: str, password: str | None = None) -> list[FileInfo]:
        """
        Attempt to extract file metadata and a direct download URL from a 1fichier-style page.
        
        Parameters:
            url (str): The page URL to extract from.
            password (str | None): Optional password to submit if the file is password-protected.
        
        Returns:
            list[FileInfo]: A list containing a single FileInfo with fields:
                - url: the original page URL
                - filename: extracted filename or "unknown"
                - size: extracted file size in bytes (0 if unknown)
                - direct_url: the direct download URL
                - extractor_name: the extractor identifier ("1fichier")
        
        Raises:
            PasswordRequired: If the page requires a password and none was provided.
            ExtractorError: If extraction fails (including when no direct link can be found or after retrying).
        """
        max_retries = 3
        self._pacer.reset()

        for attempt in range(max_retries + 1):
            try:
                html = await self._get_download_page(url, password)
                soup = BeautifulSoup(html, "lxml")

                form = soup.find("form", {"method": "post"})
                if form:
                    form_action_raw = form.get("action", url)
                    form_action = str(form_action_raw) if form_action_raw else url
                    if not form_action.startswith("http"):
                        form_action = url

                    form_data: dict[str, str] = {}
                    for inp in form.find_all("input"):
                        name = inp.get("name")
                        value = inp.get("value", "")
                        if name:
                            form_data[str(name)] = str(value)

                    html = await self._submit_form(url, form_action, form_data, password)

                direct_link, filename, size = await self._parse_page(html, url, password)

                if not direct_link:
                    raise ExtractorError("Could not extract download link")

                return [
                    FileInfo(
                        url=url,
                        filename=filename or "unknown",
                        size=size,
                        direct_url=direct_link,
                        extractor_name=self.EXTRACTOR_NAME,
                    )
                ]
            except (ExtractorError, PasswordRequired):
                raise
            except Exception as e:
                if attempt == max_retries:
                    raise ExtractorError(f"Failed after {max_retries} retries: {e}") from e

                await self._pacer.sleep(attempt)
                logger.info(f"Retrying 1Fichier extraction (attempt {attempt + 1}/{max_retries})")
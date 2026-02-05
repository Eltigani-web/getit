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
from getit.registry import ExtractorRegistry
from getit.utils.pacer import Pacer

if TYPE_CHECKING:
    from getit.utils.http import HTTPClient

logger = logging.getLogger(__name__)


@ExtractorRegistry.register
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
        super().__init__(http_client)
        self._pacer = Pacer(min_backoff=0.4, max_backoff=5.0, flood_sleep=30.0)

    @classmethod
    def can_handle(cls, url: str) -> bool:
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
            return None, None, -1

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
                    if size == -1 and attempt < max_retries:
                        logger.info(
                            f"Retrying 1Fichier extraction after flood detection (attempt {attempt + 1}/{max_retries})"
                        )
                        await self._pacer.sleep(attempt)
                        continue
                    if attempt < max_retries:
                        logger.info(
                            f"Retrying 1Fichier extraction (attempt {attempt + 1}/{max_retries})"
                        )
                        await self._pacer.sleep(attempt)
                        continue
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

                logger.info(f"Retrying 1Fichier extraction (attempt {attempt + 1}/{max_retries})")
                await self._pacer.sleep(attempt)

        raise ExtractorError("Failed to extract 1Fichier file list")

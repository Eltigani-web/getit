from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, ClassVar, Optional

from bs4 import BeautifulSoup

from getit.extractors.base import (
    BaseExtractor,
    ExtractorError,
    FileInfo,
    PasswordRequired,
    parse_size_string,
)

if TYPE_CHECKING:
    from getit.utils.http import HTTPClient


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

    def __init__(self, http_client: HTTPClient):
        super().__init__(http_client)

    @classmethod
    def can_handle(cls, url: str) -> bool:
        if cls.URL_PATTERN.match(url) or cls.ALT_PATTERN.match(url):
            return True
        for domain in cls.SUPPORTED_DOMAINS:
            if domain in url:
                return True
        return False

    @classmethod
    def extract_id(cls, url: str) -> Optional[str]:
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

    async def _get_download_page(self, url: str, password: Optional[str] = None) -> str:
        headers = {"Cookie": "LG=en"}
        text = await self.http.get_text(url, headers=headers)
        return text

    async def _submit_form(
        self,
        url: str,
        form_action: str,
        form_data: dict[str, str],
        password: Optional[str] = None,
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
        self, html: str, url: str, password: Optional[str] = None
    ) -> tuple[Optional[str], Optional[str], int]:
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

        wait_match = self.WAIT_PATTERN.search(html)
        if wait_match:
            wait_time = int(wait_match.group(1))
            if "minute" in html.lower()[wait_match.start() : wait_match.end() + 20]:
                wait_time *= 60
            if 0 < wait_time < 300:
                await asyncio.sleep(wait_time + 1)

        direct_link = None
        link_tag = soup.find("a", {"class": "ok"})
        if link_tag:
            direct_link = link_tag.get("href")

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

    async def extract(self, url: str, password: Optional[str] = None) -> list[FileInfo]:
        html = await self._get_download_page(url, password)
        soup = BeautifulSoup(html, "lxml")

        form = soup.find("form", {"method": "post"})
        if form:
            form_action = form.get("action", url)
            if not form_action.startswith("http"):
                form_action = url

            form_data: dict[str, str] = {}
            for inp in form.find_all("input"):
                name = inp.get("name")
                value = inp.get("value", "")
                if name:
                    form_data[name] = value

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

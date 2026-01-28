from __future__ import annotations

import base64
import re
from typing import TYPE_CHECKING, ClassVar

from bs4 import BeautifulSoup

from getit.extractors.base import (
    BaseExtractor,
    ExtractorError,
    FileInfo,
    FolderInfo,
    NotFound,
    parse_size_string,
)

if TYPE_CHECKING:
    from getit.utils.http import HTTPClient


class MediaFireExtractor(BaseExtractor):
    SUPPORTED_DOMAINS: ClassVar[tuple[str, ...]] = ("mediafire.com",)
    EXTRACTOR_NAME: ClassVar[str] = "mediafire"
    URL_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"https?://(?:www\.)?mediafire\.com/"
        r"(?:file(?:_premium)?/|view/\??|download(?:\.php\?|/)|(?:\?))(?P<id>[a-zA-Z0-9]+)"
    )
    FOLDER_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"https?://(?:www\.)?mediafire\.com/(?:folder/|\?sharekey=)(?P<id>[a-zA-Z0-9]+)"
    )

    API_URL = "https://www.mediafire.com/api/1.5"

    def __init__(self, http_client: HTTPClient):
        super().__init__(http_client)

    @classmethod
    def can_handle(cls, url: str) -> bool:
        return bool(cls.URL_PATTERN.match(url) or cls.FOLDER_PATTERN.match(url))

    @classmethod
    def extract_id(cls, url: str) -> str | None:
        match = cls.URL_PATTERN.match(url) or cls.FOLDER_PATTERN.match(url)
        if match:
            return match.group("id")
        return None

    @classmethod
    def _is_folder(cls, url: str) -> bool:
        return bool(cls.FOLDER_PATTERN.match(url))

    async def _get_file_info_api(self, quick_key: str) -> dict | None:
        try:
            url = f"{self.API_URL}/file/get_info.php"
            params = {"quick_key": quick_key, "response_format": "json"}
            data = await self.http.get_json(url, params=params)
            if data.get("response", {}).get("result") == "Success":
                return data["response"]["file_info"]
        except Exception:
            pass
        return None

    async def _get_direct_link_html(self, url: str) -> tuple[str, str, int] | None:
        try:
            text = await self.http.get_text(url)
            soup = BeautifulSoup(text, "lxml")

            if "solvemedia" in text.lower() or "recaptcha" in text.lower():
                raise ExtractorError("CAPTCHA required - cannot proceed automatically")

            download_btn = soup.find("a", {"id": "downloadButton"})
            if download_btn:
                scrambled = download_btn.get("data-scrambled-url")
                if scrambled:
                    try:
                        direct_url = base64.b64decode(str(scrambled)).decode()
                    except Exception:
                        href = download_btn.get("href", "")
                        direct_url = str(href) if href else ""
                else:
                    href = download_btn.get("href", "")
                    direct_url = str(href) if href else ""

                if direct_url and direct_url.startswith("http"):
                    filename_div = soup.find("div", {"class": "filename"})
                    filename = filename_div.get_text(strip=True) if filename_div else "unknown"

                    size = 0
                    size_span = soup.find("span", {"class": "dl-info"})
                    if size_span:
                        size = parse_size_string(size_span.get_text())

                    return direct_url, filename, size
        except ExtractorError:
            raise
        except Exception:
            pass
        return None

    async def _get_folder_contents(self, folder_key: str) -> list[dict]:
        files: list[dict] = []
        chunk = 1
        chunk_size = 1000

        while True:
            url = f"{self.API_URL}/folder/get_content.php"
            params = {
                "folder_key": folder_key,
                "content_type": "files",
                "chunk": chunk,
                "chunk_size": chunk_size,
                "filter": "public",
                "response_format": "json",
            }
            try:
                data = await self.http.get_json(url, params=params)
                folder_content = data.get("response", {}).get("folder_content", {})
                chunk_files = folder_content.get("files", [])
                if not chunk_files:
                    break
                files.extend(chunk_files)
                if len(chunk_files) < chunk_size:
                    break
                chunk += 1
            except Exception:
                break

        return files

    async def extract(self, url: str, password: str | None = None) -> list[FileInfo]:
        file_id = self.extract_id(url)
        if not file_id:
            raise ExtractorError(f"Could not extract file ID from {url}")

        if self._is_folder(url):
            return await self._extract_folder_files(file_id)

        api_info = await self._get_file_info_api(file_id)
        if api_info:
            return [
                FileInfo(
                    url=url,
                    filename=api_info.get("filename", "unknown"),
                    size=int(api_info.get("size", 0)),
                    direct_url=api_info.get("links", {}).get("normal_download"),
                    extractor_name=self.EXTRACTOR_NAME,
                    checksum=api_info.get("hash"),
                    checksum_type="sha256" if api_info.get("hash") else None,
                )
            ]

        result = await self._get_direct_link_html(url)
        if result:
            direct_url, filename, size = result
            return [
                FileInfo(
                    url=url,
                    filename=filename,
                    size=size,
                    direct_url=direct_url,
                    extractor_name=self.EXTRACTOR_NAME,
                )
            ]

        raise NotFound(f"Could not extract download link from {url}")

    async def _extract_folder_files(self, folder_key: str) -> list[FileInfo]:
        folder_files = await self._get_folder_contents(folder_key)
        files: list[FileInfo] = []

        for file_data in folder_files:
            quick_key = file_data.get("quickkey", "")
            file_url = f"https://www.mediafire.com/file/{quick_key}"
            extracted = await self.extract(file_url)
            files.extend(extracted)

        return files

    async def extract_folder(self, url: str, password: str | None = None) -> FolderInfo | None:
        if not self._is_folder(url):
            return None

        folder_key = self.extract_id(url)
        if not folder_key:
            return None

        folder = FolderInfo(url=url, name=folder_key)
        folder.files = await self._extract_folder_files(folder_key)
        return folder

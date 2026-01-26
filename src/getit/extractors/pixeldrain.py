from __future__ import annotations

import re
from typing import TYPE_CHECKING, ClassVar, Optional

from getit.extractors.base import (
    BaseExtractor,
    ExtractorError,
    FileInfo,
    FolderInfo,
    NotFound,
)

if TYPE_CHECKING:
    from getit.utils.http import HTTPClient


class PixelDrainExtractor(BaseExtractor):
    SUPPORTED_DOMAINS: ClassVar[tuple[str, ...]] = ("pixeldrain.com", "pixeldrain.net")
    EXTRACTOR_NAME: ClassVar[str] = "pixeldrain"
    URL_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"https?://(?:www\.)?pixeldrain\.(?:com|net)/(?P<type>u|l|api/file)/(?P<id>[a-zA-Z0-9]+)"
    )

    API_URL = "https://pixeldrain.com/api"

    def __init__(self, http_client: HTTPClient, api_key: Optional[str] = None):
        super().__init__(http_client)
        self._api_key = api_key

    def _get_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._api_key:
            import base64

            auth = base64.b64encode(f":{self._api_key}".encode()).decode()
            headers["Authorization"] = f"Basic {auth}"
        return headers

    @classmethod
    def extract_id(cls, url: str) -> Optional[str]:
        match = cls.URL_PATTERN.match(url)
        if match:
            return match.group("id")
        return None

    @classmethod
    def _extract_type(cls, url: str) -> str:
        match = cls.URL_PATTERN.match(url)
        if match:
            return match.group("type")
        return "u"

    async def _get_file_info(self, file_id: str) -> dict:
        url = f"{self.API_URL}/file/{file_id}/info"
        data = await self.http.get_json(url, headers=self._get_headers())
        if not data.get("success", True):
            message = data.get("message", "Unknown error")
            if "not found" in message.lower():
                raise NotFound(f"File {file_id} not found")
            raise ExtractorError(message)
        return data

    async def _get_list_info(self, list_id: str) -> dict:
        url = f"{self.API_URL}/list/{list_id}"
        data = await self.http.get_json(url, headers=self._get_headers())
        if not data.get("success", True):
            message = data.get("message", "Unknown error")
            raise ExtractorError(message)
        return data

    def _parse_file(self, file_data: dict, folder_name: Optional[str] = None) -> FileInfo:
        file_id = file_data.get("id", "")
        return FileInfo(
            url=f"https://pixeldrain.com/u/{file_id}",
            filename=file_data.get("name", "unknown"),
            size=file_data.get("size", 0),
            direct_url=f"{self.API_URL}/file/{file_id}?download",
            headers=self._get_headers(),
            parent_folder=folder_name,
            extractor_name=self.EXTRACTOR_NAME,
            checksum=file_data.get("hash_sha256"),
            checksum_type="sha256" if file_data.get("hash_sha256") else None,
        )

    async def extract(self, url: str, password: Optional[str] = None) -> list[FileInfo]:
        file_id = self.extract_id(url)
        if not file_id:
            raise ExtractorError(f"Could not extract file ID from {url}")

        url_type = self._extract_type(url)

        if url_type == "l":
            return await self._extract_list(file_id)

        file_info = await self._get_file_info(file_id)
        return [self._parse_file(file_info)]

    async def _extract_list(self, list_id: str) -> list[FileInfo]:
        list_info = await self._get_list_info(list_id)
        files: list[FileInfo] = []
        list_name = list_info.get("title", list_id)

        for file_data in list_info.get("files", []):
            files.append(self._parse_file(file_data, list_name))

        return files

    async def extract_folder(
        self, url: str, password: Optional[str] = None
    ) -> Optional[FolderInfo]:
        file_id = self.extract_id(url)
        if not file_id:
            return None

        url_type = self._extract_type(url)
        if url_type != "l":
            return None

        list_info = await self._get_list_info(file_id)
        folder = FolderInfo(
            url=url,
            name=list_info.get("title", file_id),
        )

        for file_data in list_info.get("files", []):
            folder.files.append(self._parse_file(file_data, folder.name))

        return folder

from __future__ import annotations

import hashlib
import re
import time
from typing import TYPE_CHECKING, ClassVar, Optional

from aiolimiter import AsyncLimiter

from getit.extractors.base import (
    BaseExtractor,
    ExtractorError,
    FileInfo,
    FolderInfo,
    NotFound,
    PasswordRequired,
)

if TYPE_CHECKING:
    from getit.utils.http import HTTPClient


class GoFileExtractor(BaseExtractor):
    SUPPORTED_DOMAINS: ClassVar[tuple[str, ...]] = ("gofile.io",)
    EXTRACTOR_NAME: ClassVar[str] = "gofile"
    URL_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"https?://(?:www\.)?gofile\.io/d/(?P<id>[a-zA-Z0-9]+)"
    )

    API_URL = "https://api.gofile.io"

    JS_URLS = [
        "https://gofile.io/dist/js/config.js",
    ]

    WT_PATTERNS = [
        r'\.wt\s*=\s*["\']([^"\']+)["\']',
        r'wt\s*[:=]\s*["\']([^"\']+)["\']',
        r'fetchData\s*=\s*\{\s*wt:\s*"([^"]+)"',
        r'appdata\.wt\s*=\s*"([^"]+)"',
    ]

    FALLBACK_WT = "4fd6sg89d7s6"
    TOKEN_TTL = 86400

    _STATUS_ERRORS: ClassVar[dict[str, tuple[type[Exception], str]]] = {
        "error-notFound": (NotFound, "Content {content_id} not found"),
        "error-passwordRequired": (PasswordRequired, ""),
        "error-expiredContent": (NotFound, "Content has expired"),
        "error-disabledAccount": (ExtractorError, "Account has been disabled"),
        "error-bannedAccount": (ExtractorError, "Account has been banned"),
        "error-overloaded": (ExtractorError, "Server overloaded, try again later"),
    }

    def __init__(self, http_client: HTTPClient, api_token: Optional[str] = None):
        super().__init__(http_client)
        self._token: Optional[str] = api_token
        self._website_token: Optional[str] = None
        self._website_token_expiry: float = 0
        self._token_expiry: float = 0
        self._limiter = AsyncLimiter(10, 1)

    async def _get_guest_token(self) -> str:
        if self._token and time.time() < self._token_expiry:
            return self._token

        async with self._limiter:
            resp = await self.http.post(f"{self.API_URL}/accounts", data={})
            async with resp:
                resp.raise_for_status()
                data = await resp.json()

        if data.get("status") == "ok":
            self._token = data["data"]["token"]
            self._token_expiry = time.time() + self.TOKEN_TTL
            self.http.update_cookies({"accountToken": self._token})
            return self._token

        raise ExtractorError(f"Failed to create guest account: {data.get('status', 'unknown')}")

    async def _get_website_token(self) -> str:
        if self._website_token and time.time() < self._website_token_expiry:
            return self._website_token

        for js_url in self.JS_URLS:
            try:
                async with self._limiter:
                    text = await self.http.get_text(js_url)
                for pattern in self.WT_PATTERNS:
                    match = re.search(pattern, text)
                    if match:
                        self._website_token = match.group(1)
                        self._website_token_expiry = time.time() + self.TOKEN_TTL
                        return self._website_token
            except Exception:
                continue

        self._website_token = self.FALLBACK_WT
        self._website_token_expiry = time.time() + 3600
        return self._website_token

    def _invalidate_tokens(self, include_website_token: bool = False) -> None:
        self._token = None
        self._token_expiry = 0
        if include_website_token:
            self._website_token = None
            self._website_token_expiry = 0

    def _check_status_error(self, status: str, content_id: str) -> None:
        if status in self._STATUS_ERRORS:
            exc_class, msg_template = self._STATUS_ERRORS[status]
            raise exc_class(msg_template.format(content_id=content_id) if msg_template else None)

    async def _get_content(
        self, content_id: str, password: Optional[str] = None, max_retries: int = 2
    ) -> dict:
        last_error: Optional[Exception] = None

        for attempt in range(max_retries + 1):
            try:
                token = await self._get_guest_token()
                wt = await self._get_website_token()

                headers = {
                    "Authorization": f"Bearer {token}",
                    "X-Website-Token": wt,
                }
                params: dict[str, str] = {}
                if password:
                    params["password"] = hashlib.sha256(password.encode()).hexdigest()

                url = f"{self.API_URL}/contents/{content_id}"

                async with self._limiter:
                    data = await self.http.get_json(url, headers=headers, params=params)

                status = data.get("status", "")

                if status in ("error-wrongToken", "error-tokenInvalid"):
                    self._invalidate_tokens()
                    if attempt < max_retries:
                        continue
                    raise ExtractorError("Invalid token after retries")

                self._check_status_error(status, content_id)

                if status != "ok":
                    raise ExtractorError(f"API error: {status}")

                return data["data"]

            except (NotFound, PasswordRequired, ExtractorError):
                raise
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                if "401" in error_str or "403" in error_str or "unauthorized" in error_str:
                    self._invalidate_tokens(include_website_token=True)
                    if attempt < max_retries:
                        continue
                raise

        if last_error:
            raise last_error
        raise ExtractorError("Unknown error fetching content")

    def _parse_file(self, file_data: dict, folder_name: Optional[str] = None) -> FileInfo:
        link = file_data.get("link", "")
        if link == "overloaded":
            link = file_data.get("directLink", "")

        return FileInfo(
            url=link,
            filename=file_data.get("name", "unknown"),
            size=file_data.get("size", 0),
            direct_url=link,
            headers={"Authorization": f"Bearer {self._token}"},
            cookies={"accountToken": self._token} if self._token else {},
            parent_folder=folder_name,
            extractor_name=self.EXTRACTOR_NAME,
            checksum=file_data.get("md5"),
            checksum_type="md5" if file_data.get("md5") else None,
        )

    async def extract(
        self, url: str, password: Optional[str] = None, max_depth: int = 10
    ) -> list[FileInfo]:
        return await self._extract_recursive(url, password, max_depth, 0)

    async def _extract_recursive(
        self,
        url: str,
        password: Optional[str],
        max_depth: int,
        current_depth: int,
    ) -> list[FileInfo]:
        content_id = self.extract_id(url)
        if not content_id:
            raise ExtractorError(f"Could not extract content ID from {url}")

        content = await self._get_content(content_id, password)
        files: list[FileInfo] = []

        children = content.get("children", content.get("contents", {}))
        if isinstance(children, dict):
            children = list(children.values())

        for item in children:
            if item.get("type") == "file":
                files.append(self._parse_file(item, content.get("name")))
            elif item.get("type") == "folder" and current_depth < max_depth:
                sub_files = await self._extract_recursive(
                    f"https://gofile.io/d/{item['id']}",
                    password,
                    max_depth,
                    current_depth + 1,
                )
                files.extend(sub_files)

        return files

    async def extract_folder(
        self, url: str, password: Optional[str] = None
    ) -> Optional[FolderInfo]:
        content_id = self.extract_id(url)
        if not content_id:
            return None

        content = await self._get_content(content_id, password)
        folder = FolderInfo(url=url, name=content.get("name", content_id))

        children = content.get("children", content.get("contents", {}))
        if isinstance(children, dict):
            children = list(children.values())

        for item in children:
            if item.get("type") == "file":
                folder.files.append(self._parse_file(item, folder.name))
            elif item.get("type") == "folder":
                sub_folder = await self.extract_folder(
                    f"https://gofile.io/d/{item['id']}", password
                )
                if sub_folder:
                    folder.subfolders.append(sub_folder)

        return folder

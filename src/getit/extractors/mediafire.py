from __future__ import annotations

import base64
import hashlib
import logging
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
from getit.utils.pacer import Pacer

if TYPE_CHECKING:
    from getit.utils.http import HTTPClient

logger = logging.getLogger(__name__)


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

    CAPTCHA_PATTERNS: ClassVar[list[str]] = [
        r"solvemedia",
        r"recaptcha",
        r"hcaptcha",
        r"captcha",
        r"challenge",
        r"verification",
    ]

    def __init__(self, http_client: HTTPClient):
        """
        Initialize the extractor with an HTTP client and configure a Pacer for retry/backoff behavior.
        
        Creates an instance-level Pacer configured with min_backoff=0.4, max_backoff=5.0, and flood_sleep=30.0 to manage request backoff and IP flood handling.
        """
        super().__init__(http_client)
        self._pacer = Pacer(min_backoff=0.4, max_backoff=5.0, flood_sleep=30.0)

    @classmethod
    def can_handle(cls, url: str) -> bool:
        """
        Check whether the given URL is a MediaFire file or folder URL.
        
        Returns:
            True if the URL matches the extractor's file or folder pattern, False otherwise.
        """
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
        """
        Extracts a direct download URL, filename, and size from a MediaFire file page HTML.
        
        Parameters:
            url (str): The MediaFire page URL to fetch and parse.
        
        Returns:
            tuple[str, str, int] | None: `(direct_url, filename, size)` when a downloadable link is found; `None` if no direct link could be extracted.
        
        Raises:
            ExtractorError: If a CAPTCHA is detected on the page which prevents automatic extraction.
        """
        try:
            text = await self.http.get_text(url)
            soup = BeautifulSoup(text, "lxml")

            for pattern in self.CAPTCHA_PATTERNS:
                if re.search(pattern, text, re.IGNORECASE):
                    raise ExtractorError("CAPTCHA required - cannot proceed automatically")

            if self._pacer.detect_flood_ip_lock(text):
                await self._pacer.handle_flood_ip_lock()

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
        """
        Extracts file or folder FileInfo entries from a MediaFire URL.
        
        Parameters:
            url (str): MediaFire file or folder URL to extract.
            password (str | None): Optional password (not used by this extractor).
        
        Returns:
            list[FileInfo]: A list of FileInfo objects for the file or files found.
        
        Raises:
            ExtractorError: If the URL does not contain a valid ID or extraction fails after retries.
            NotFound: If a download link cannot be located for the given URL.
        """
        file_id = self.extract_id(url)
        if not file_id:
            raise ExtractorError(f"Could not extract file ID from {url}")

        if self._is_folder(url):
            return await self._extract_folder_files(file_id)

        max_retries = 3
        self._pacer.reset()

        for attempt in range(max_retries + 1):
            try:
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
            except (ExtractorError, NotFound):
                raise
            except Exception as e:
                if attempt == max_retries:
                    raise ExtractorError(f"Failed after {max_retries} retries: {e}") from e

                await self._pacer.sleep(attempt)
                logger.info(f"Retrying MediaFire extraction (attempt {attempt + 1}/{max_retries})")

    async def _extract_folder_files(self, folder_key: str) -> list[FileInfo]:
        """
        Fetches all files listed in a MediaFire folder and returns their extracted FileInfo entries.
        
        Parameters:
            folder_key (str): The MediaFire folder identifier (folder key).
        
        Returns:
            list[FileInfo]: A list of FileInfo objects for every file found in the folder.
        """
        folder_files = await self._get_folder_contents(folder_key)
        files: list[FileInfo] = []

        for file_data in folder_files:
            quick_key = file_data.get("quickkey", "")
            file_url = f"https://www.mediafire.com/file/{quick_key}"
            extracted = await self.extract(file_url)
            files.extend(extracted)

        return files

    async def extract_folder(self, url: str, password: str | None = None) -> FolderInfo | None:
        """
        Create and return a FolderInfo for the given MediaFire folder URL.
        
        If the URL denotes a MediaFire folder and a folder id can be extracted, returns a FolderInfo whose `files` list is populated by fetching the folder's contents; otherwise returns None.
        
        Parameters:
            url (str): The MediaFire URL to inspect.
            password (str | None): Ignored for MediaFire folders (accepted for API compatibility).
        
        Returns:
            FolderInfo | None: FolderInfo with populated `files` if the URL is a folder and the folder id was found, `None` otherwise.
        """
        if not self._is_folder(url):
            return None

        folder_key = self.extract_id(url)
        if not folder_key:
            return None

        folder = FolderInfo(url=url, name=folder_key)
        folder.files = await self._extract_folder_files(folder_key)
        return folder

    def verify_hash(self, file_path: str, expected_hash: str, hash_type: str = "sha256") -> bool:
        """
        Check whether the checksum of the file at file_path matches the provided expected_hash.
        
        Parameters:
            file_path (str): Path to the local file to verify.
            expected_hash (str): Expected hash string to compare against (hexadecimal).
            hash_type (str): Hash algorithm to use; "md5" for MD5, anything else selects SHA-256.
        
        Returns:
            bool: `True` if the computed hash equals `expected_hash` (comparison is case-insensitive), `False` otherwise.
        """
        try:
            hash_func = hashlib.md5 if hash_type.lower() == "md5" else hashlib.sha256

            with open(file_path, "rb") as f:
                file_hash = hash_func()
                while chunk := f.read(8192):
                    file_hash.update(chunk)

            actual_hash = file_hash.hexdigest()
            is_valid = actual_hash.lower() == expected_hash.lower()

            if not is_valid:
                logger.warning(
                    f"Hash verification failed for {file_path}: "
                    f"expected {expected_hash}, got {actual_hash}"
                )

            return is_valid
        except Exception as e:
            logger.error(f"Hash verification error for {file_path}: {e}")
            return False
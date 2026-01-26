from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar, Optional
from urllib.parse import urlparse

if TYPE_CHECKING:
    from getit.utils.http import HTTPClient


class ExtractorError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class PasswordRequired(ExtractorError):
    def __init__(self, message: str = "Password required"):
        super().__init__(message)


class NotFound(ExtractorError):
    def __init__(self, message: str = "Content not found"):
        super().__init__(message, 404)


class InvalidURLError(ExtractorError):
    def __init__(self, message: str = "Invalid URL"):
        super().__init__(message)


ALLOWED_SCHEMES = frozenset({"http", "https"})

SIZE_MULTIPLIERS: dict[str, int] = {
    "B": 1,
    "KB": 1024,
    "KO": 1024,
    "K": 1024,
    "MB": 1024**2,
    "MO": 1024**2,
    "M": 1024**2,
    "GB": 1024**3,
    "GO": 1024**3,
    "G": 1024**3,
    "TB": 1024**4,
    "TO": 1024**4,
    "T": 1024**4,
}

SIZE_PATTERN = re.compile(r"([\d.]+)\s*(KB|MB|GB|TB|Ko|Mo|Go|To|K|M|G|T|B)?", re.I)


def parse_size_string(text: str) -> int:
    match = SIZE_PATTERN.search(text)
    if not match:
        return 0

    value = float(match.group(1))
    unit = (match.group(2) or "B").upper()

    if unit.endswith("O"):
        unit = unit[:-1] + "B"

    multiplier = SIZE_MULTIPLIERS.get(unit, 1)
    return int(value * multiplier)


def validate_url_scheme(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise InvalidURLError(f"Invalid URL scheme: {parsed.scheme!r}. Only http/https allowed.")
    if not parsed.netloc:
        raise InvalidURLError(f"Invalid URL: missing host")


@dataclass
class FileInfo:
    url: str
    filename: str
    size: int = 0
    direct_url: Optional[str] = None
    headers: dict[str, str] = field(default_factory=dict)
    cookies: dict[str, str] = field(default_factory=dict)
    password_protected: bool = False
    checksum: Optional[str] = None
    checksum_type: Optional[str] = None
    parent_folder: Optional[str] = None
    extractor_name: str = ""
    # Mega.nz encryption support
    encryption_key: Optional[bytes] = None
    encryption_iv: Optional[bytes] = None
    encrypted: bool = False


@dataclass
class FolderInfo:
    url: str
    name: str
    files: list[FileInfo] = field(default_factory=list)
    subfolders: list[FolderInfo] = field(default_factory=list)


class BaseExtractor(ABC):
    SUPPORTED_DOMAINS: ClassVar[tuple[str, ...]] = ()
    EXTRACTOR_NAME: ClassVar[str] = "base"
    URL_PATTERN: ClassVar[Optional[re.Pattern[str]]] = None

    def __init__(self, http_client: HTTPClient):
        self.http = http_client

    @classmethod
    def can_handle(cls, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme.lower() not in ALLOWED_SCHEMES:
            return False
        if not parsed.netloc:
            return False
        domain = parsed.netloc.lower().replace("www.", "")
        if any(d in domain for d in cls.SUPPORTED_DOMAINS):
            if cls.URL_PATTERN:
                return bool(cls.URL_PATTERN.match(url))
            return True
        return False

    @classmethod
    def extract_id(cls, url: str) -> Optional[str]:
        if cls.URL_PATTERN:
            match = cls.URL_PATTERN.match(url)
            if match:
                groups = match.groupdict()
                return groups.get("id") or groups.get("content_id")
        parsed = urlparse(url)
        parts = parsed.path.strip("/").split("/")
        return parts[-1] if parts else None

    @abstractmethod
    async def extract(self, url: str, password: Optional[str] = None) -> list[FileInfo]:
        pass

    async def extract_folder(
        self, url: str, password: Optional[str] = None
    ) -> Optional[FolderInfo]:
        return None

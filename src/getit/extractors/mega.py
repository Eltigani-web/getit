from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import random
import re
import struct
from typing import TYPE_CHECKING, Any, ClassVar, Optional

from Cryptodome.Cipher import AES
from Cryptodome.Util import Counter

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


def a32_to_str(a: list[int]) -> bytes:
    return struct.pack(">%dI" % len(a), *a)


def str_to_a32(s: bytes) -> list[int]:
    if len(s) % 4:
        s += b"\x00" * (4 - len(s) % 4)
    return list(struct.unpack(">%dI" % (len(s) // 4), s))


def base64_url_decode(data: str) -> bytes:
    data += "=" * ((4 - len(data) % 4) % 4)
    data = data.replace("-", "+").replace("_", "/")
    return base64.b64decode(data)


def base64_url_encode(data: bytes) -> str:
    return base64.b64encode(data).decode().replace("+", "-").replace("/", "_").rstrip("=")


def decrypt_key(encrypted_key: list[int], master_key: list[int]) -> list[int]:
    cipher = AES.new(a32_to_str(master_key), AES.MODE_ECB)
    decrypted = b""
    for i in range(0, len(encrypted_key), 4):
        decrypted += cipher.decrypt(a32_to_str(encrypted_key[i : i + 4]))
    return str_to_a32(decrypted)


def decrypt_attr(attr: bytes, key: list[int]) -> dict[str, Any]:
    cipher = AES.new(a32_to_str(key), AES.MODE_CBC, b"\x00" * 16)
    attr = cipher.decrypt(attr)
    if attr[:4] != b"MEGA":
        return {}
    try:
        return json.loads(attr[4:].rstrip(b"\x00").decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


class MegaExtractor(BaseExtractor):
    SUPPORTED_DOMAINS: ClassVar[tuple[str, ...]] = ("mega.nz", "mega.co.nz", "mega.io")
    EXTRACTOR_NAME: ClassVar[str] = "mega"
    URL_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"https?://mega\.(?:nz|co\.nz|io)/"
        r"(?:(?P<type>file|folder)/(?P<id>[a-zA-Z0-9_-]+)(?:#(?P<key>[a-zA-Z0-9_-]+))?"
        r"|#(?P<legacy_type>F)?!(?P<legacy_id>[a-zA-Z0-9_-]+)(?:!(?P<legacy_key>[a-zA-Z0-9_-]+))?)"
    )

    API_URL = "https://g.api.mega.co.nz/cs"

    def __init__(self, http_client: HTTPClient):
        super().__init__(http_client)
        self._session_id: Optional[str] = None
        self._sequence_num = random.randint(0, 0xFFFFFFFF)

    def _derive_key(self, key_a32: list[int]) -> list[int]:
        if len(key_a32) == 8:
            return [
                key_a32[0] ^ key_a32[4],
                key_a32[1] ^ key_a32[5],
                key_a32[2] ^ key_a32[6],
                key_a32[3] ^ key_a32[7],
            ]
        return key_a32[:4]

    @classmethod
    def extract_id(cls, url: str) -> Optional[str]:
        match = cls.URL_PATTERN.match(url)
        if match:
            return match.group("id") or match.group("legacy_id")
        return None

    def _extract_key(self, url: str) -> Optional[str]:
        match = self.URL_PATTERN.match(url)
        if match:
            return match.group("key") or match.group("legacy_key")
        if "#" in url:
            return url.split("#")[-1].split("!")[-1]
        return None

    def _is_folder(self, url: str) -> bool:
        match = self.URL_PATTERN.match(url)
        if match:
            return match.group("type") == "folder" or match.group("legacy_type") == "F"
        return False

    async def _api_request(
        self, data: list[dict[str, Any]], query_params: Optional[dict[str, str]] = None
    ) -> Any:
        params = {"id": self._sequence_num}
        if query_params:
            params.update(query_params)
        self._sequence_num += 1

        async with await self.http.post(
            self.API_URL,
            params=params,
            json=data,
        ) as resp:
            result = await resp.json()

        if isinstance(result, int):
            error_codes = {
                -2: "EARGS - Invalid arguments",
                -3: "EAGAIN - Temporary congestion",
                -4: "ERATELIMIT - Rate limit exceeded",
                -5: "EFAILED - Upload failed",
                -6: "ETOOMANY - Too many connections",
                -9: "ENOENT - File not found",
                -11: "EACCESS - Access denied",
                -14: "EINCOMPLETE - Incomplete request",
                -15: "EKEY - Invalid key",
                -16: "ESID - Invalid session",
                -17: "EBLOCKED - User blocked",
                -18: "EOVERQUOTA - Quota exceeded",
            }
            if result == -9:
                raise NotFound("File not found")
            raise ExtractorError(error_codes.get(result, f"API error: {result}"))

        return result[0] if isinstance(result, list) else result

    async def _get_file_info(self, file_id: str, file_key: str) -> dict[str, Any]:
        data = [{"a": "g", "g": 1, "p": file_id}]
        result = await self._api_request(data)

        if "at" not in result:
            raise ExtractorError("Invalid file response")

        key_bytes = base64_url_decode(file_key)
        key_a32 = str_to_a32(key_bytes)
        key = self._derive_key(key_a32)

        attr_data = base64_url_decode(result["at"])
        attr = decrypt_attr(attr_data, key)

        return {
            "id": file_id,
            "name": attr.get("n", "unknown"),
            "size": result.get("s", 0),
            "download_url": result.get("g", ""),
            "key": key,
            "key_str": file_key,
        }

    async def _get_folder_contents(self, folder_id: str, folder_key: str) -> list[dict[str, Any]]:
        query_params = {"n": folder_id}
        data = [{"a": "f", "c": 1, "r": 1}]
        result = await self._api_request(data, query_params)

        files: list[dict[str, Any]] = []
        folder_key_bytes = base64_url_decode(folder_key)
        folder_key_a32 = str_to_a32(folder_key_bytes)
        master_key = self._derive_key(folder_key_a32)

        for item in result.get("f", []):
            if item.get("t") == 0:
                try:
                    encrypted_key = str_to_a32(base64_url_decode(item["k"].split(":")[1]))
                    file_key = decrypt_key(encrypted_key, master_key)
                    file_key = self._derive_key(file_key)

                    attr_data = base64_url_decode(item["a"])
                    attr = decrypt_attr(attr_data, file_key[:4])

                    files.append(
                        {
                            "id": item["h"],
                            "name": attr.get("n", "unknown"),
                            "size": item.get("s", 0),
                            "key": file_key,
                            "parent_id": item.get("p"),
                        }
                    )
                except Exception:
                    continue

        return files

    def _build_encryption_params(self, key: list[int]) -> tuple[bytes, bytes]:
        """Build AES key and IV for file decryption from the 8-int key array."""
        key_bytes = a32_to_str(key[:4])
        iv_bytes = a32_to_str([key[4], key[5], 0, 0])
        return key_bytes, iv_bytes

    async def extract(self, url: str, password: Optional[str] = None) -> list[FileInfo]:
        file_id = self.extract_id(url)
        file_key = self._extract_key(url)

        if not file_id:
            raise ExtractorError(f"Could not extract file ID from {url}")
        if not file_key:
            raise ExtractorError("Missing decryption key in URL")

        if self._is_folder(url):
            return await self._extract_folder_files(file_id, file_key)

        file_info = await self._get_file_info(file_id, file_key)

        enc_key, enc_iv = self._build_encryption_params(file_info["key"])

        return [
            FileInfo(
                url=url,
                filename=file_info["name"],
                size=file_info["size"],
                direct_url=file_info["download_url"],
                extractor_name=self.EXTRACTOR_NAME,
                encryption_key=enc_key,
                encryption_iv=enc_iv,
                encrypted=True,
            )
        ]

    async def _extract_folder_files(self, folder_id: str, folder_key: str) -> list[FileInfo]:
        folder_contents = await self._get_folder_contents(folder_id, folder_key)
        files: list[FileInfo] = []

        for item in folder_contents:
            key_str = base64_url_encode(a32_to_str(item["key"]))

            try:
                file_url = f"https://mega.nz/file/{item['id']}#{key_str}"
                data = [{"a": "g", "g": 1, "n": item["id"]}]
                query_params = {"n": folder_id}
                result = await self._api_request(data, query_params)

                download_url = result.get("g", "") if isinstance(result, dict) else ""

                enc_key, enc_iv = self._build_encryption_params(item["key"])

                files.append(
                    FileInfo(
                        url=file_url,
                        filename=item["name"],
                        size=item["size"],
                        direct_url=download_url,
                        extractor_name=self.EXTRACTOR_NAME,
                        encryption_key=enc_key,
                        encryption_iv=enc_iv,
                        encrypted=True,
                    )
                )
            except Exception:
                continue

        return files

    async def extract_folder(
        self, url: str, password: Optional[str] = None
    ) -> Optional[FolderInfo]:
        if not self._is_folder(url):
            return None

        folder_id = self.extract_id(url)
        folder_key = self._extract_key(url)

        if not folder_id or not folder_key:
            return None

        folder = FolderInfo(url=url, name=folder_id)
        folder.files = await self._extract_folder_files(folder_id, folder_key)
        return folder

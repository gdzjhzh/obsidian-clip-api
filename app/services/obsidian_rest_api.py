"""Obsidian Local REST API integration."""

import asyncio
import re
from datetime import datetime
from typing import Any, Dict

import aiohttp

from ..config import config
from ..services.notification import notifier


class ObsidianRestAPIService:
    def __init__(self):
        self.base_url = config.obsidian_api_url
        self.api_key = config.obsidian_api_key
        self.timeout = config.obsidian_api_timeout
        self.retry_count = config.obsidian_api_retry_count
        self.retry_delay = config.obsidian_api_retry_delay
        self.verify_ssl = config.obsidian_api_verify_ssl

        self.base_url = self._normalize_url(self.base_url)
        self.clippings_path = config.obsidian_clippings_path.strip("/")
        self.date_folder = config.obsidian_date_folder

    def _normalize_url(self, url: str) -> str:
        if not url:
            raise ValueError("Obsidian API URL cannot be empty")
        if not url.startswith(("http://", "https://")):
            url = f"http://{url}"
        url = url.replace("://0.0.0.0:", "://127.0.0.1:")
        return url.rstrip("/")

    def _sanitize_filename(self, title: str) -> str:
        title = re.sub(r'[<>:"/\\|?*]', "", title)
        title = re.sub(r"\s+", "_", title.strip())
        title = re.sub(r"[^\w\u4e00-\u9fff._-]", "", title)
        if len(title) > 100:
            title = title[:100]
        return title or "untitled"

    def _request_ssl(self):
        return None if self.verify_ssl else False

    def generate_file_path(self, title: str) -> str:
        now = datetime.now()
        date_str = now.strftime("%Y%m%d")
        time_str = now.strftime("%H%M")
        sanitized_title = self._sanitize_filename(title)
        filename = f"{date_str}_{time_str}_{sanitized_title}.md"

        path_parts = [self.clippings_path]
        if self.date_folder:
            path_parts.extend([now.strftime("%Y"), now.strftime("%m")])
        path_parts.append(filename)
        return "/".join(path_parts)

    async def _read_error_message(self, response: aiohttp.ClientResponse) -> str:
        try:
            error_data = await response.json()
            return error_data.get("message", "Unknown error")
        except Exception:
            return await response.text() or f"HTTP {response.status} error"

    async def save_document(self, title: str, content: str, url: str) -> str:
        file_path = self.generate_file_path(title)
        request_url = f"{self.base_url}/vault/{file_path}"

        for attempt in range(self.retry_count + 1):
            try:
                notifier.send_progress("文档保存", f"正在保存到 Obsidian: {file_path}")
                timeout = aiohttp.ClientTimeout(total=self.timeout)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.put(
                        request_url,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Accept": "*/*",
                            "Content-Type": "text/markdown",
                        },
                        data=content.encode("utf-8"),
                        ssl=self._request_ssl(),
                    ) as response:
                        if response.status == 204:
                            return file_path

                        error_message = await self._read_error_message(response)
                        if response.status == 401:
                            raise Exception("Obsidian REST API authentication failed, check API key")
                        if response.status == 400:
                            raise Exception(f"Document creation failed: {error_message}")
                        if response.status == 405:
                            raise Exception(
                                f"Document creation failed: path '{file_path}' points to a directory"
                            )
                        if response.status == 404:
                            raise Exception("Obsidian REST API endpoint not found, check URL")
                        raise Exception(
                            f"Obsidian API request failed (HTTP {response.status}): {error_message}"
                        )

            except aiohttp.ClientError as e:
                if attempt < self.retry_count:
                    wait_time = self.retry_delay * (2 ** attempt)
                    notifier.send_progress(
                        "重试",
                        f"网络错误，{wait_time} 秒后重试 ({attempt + 1}/{self.retry_count})",
                    )
                    await asyncio.sleep(wait_time)
                    continue
                raise Exception(f"Cannot connect to Obsidian REST API: {e}")

        raise Exception("Document save failed: exceeded max retries")

    async def health_check(self) -> bool:
        try:
            connection_info = await self.test_connection()
            return connection_info["status"] == "connected"
        except Exception:
            return False

    async def test_connection(self) -> Dict[str, Any]:
        request_url = f"{self.base_url}/"
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    request_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Accept": "application/json",
                    },
                    ssl=self._request_ssl(),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "status": "connected",
                            "authenticated": data.get("authenticated", False),
                            "service": data.get("service", "Unknown"),
                            "version": data.get("versions", {}).get("self", "Unknown"),
                            "url": request_url,
                            "verify_ssl": self.verify_ssl,
                        }

                    error_text = await response.text()
                    return {
                        "status": "error",
                        "error": f"HTTP {response.status}: {error_text}",
                        "authenticated": False,
                        "url": request_url,
                        "verify_ssl": self.verify_ssl,
                    }
        except aiohttp.ClientError as e:
            return {
                "status": "connection_failed",
                "error": str(e),
                "authenticated": False,
                "url": request_url,
                "verify_ssl": self.verify_ssl,
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "authenticated": False,
                "url": request_url,
                "verify_ssl": self.verify_ssl,
            }

    def get_document_path(self, file_path: str) -> str:
        return file_path


obsidian_rest_api = ObsidianRestAPIService()

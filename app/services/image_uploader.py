"""
Image upload service.
"""

import asyncio
import json
import os
import re
import tempfile
import time
from typing import Dict, List, Tuple
from urllib.parse import unquote, urljoin, urlparse

import aiohttp

from ..config import config
from ..logger import logger
from ..utils.debug_manager import debug_manager


class ImageUploader:
    """Download remote images and upload them to PicList/PicGo."""

    def __init__(self):
        self.picgo_server = config.picgo_server
        self.upload_path = config.picgo_upload_path
        self.local_path_prefix = config.picgo_local_path_prefix
        self.local_use_wikilink = config.picgo_local_use_wikilink

    def _normalize_local_image_target(self, uploaded_url: str) -> tuple[str, str]:
        """Convert PicList local-upload paths into Obsidian-friendly references."""
        if not uploaded_url:
            return "markdown", uploaded_url

        if self.local_path_prefix and uploaded_url.startswith(self.local_path_prefix):
            relative_path = uploaded_url[len(self.local_path_prefix):].lstrip("/")
            if self.local_use_wikilink:
                return "wikilink", relative_path
            return "markdown", f"/{relative_path}"

        return "markdown", uploaded_url

    def _sanitize_filename_part(self, value: str) -> str:
        """Remove characters that are unsafe for local files."""
        value = unquote(value or "").strip()
        value = re.sub(r'[<>:"/\\|?*]', "_", value)
        value = re.sub(r"\s+", "_", value)
        return value.strip("._") or "image"

    def _detect_file_extension(self, image_url: str, content_type: str, image_data: bytes) -> str:
        """Infer a usable extension so uploaded files are real image files on disk."""
        parsed_path = unquote(urlparse(image_url).path)
        _, parsed_ext = os.path.splitext(parsed_path)
        parsed_ext = parsed_ext.lower()
        if parsed_ext in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}:
            return parsed_ext

        content_type = (content_type or "").split(";", 1)[0].strip().lower()
        content_type_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "image/bmp": ".bmp",
            "image/svg+xml": ".svg",
        }
        if content_type in content_type_map:
            return content_type_map[content_type]

        header = image_data[:12]
        if header.startswith(b"\xff\xd8\xff"):
            return ".jpg"
        if header.startswith(b"\x89PNG\r\n\x1a\n"):
            return ".png"
        if header[:6] in {b"GIF87a", b"GIF89a"}:
            return ".gif"
        if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
            return ".webp"
        if header.startswith(b"BM"):
            return ".bmp"
        if image_data.lstrip().startswith(b"<svg"):
            return ".svg"

        return ".jpg"

    def _guess_upload_filename(self, image_url: str, alt: str, content_type: str, image_data: bytes) -> str:
        """Build a stable filename with an explicit extension."""
        parsed_path = unquote(urlparse(image_url).path)
        original_filename = os.path.basename(parsed_path)
        original_stem, original_ext = os.path.splitext(original_filename)
        extension = original_ext.lower() or self._detect_file_extension(image_url, content_type, image_data)

        stem_source = alt or original_stem or "image"
        stem = self._sanitize_filename_part(stem_source)
        return f"{stem}{extension}"

    async def _download_image(self, session: aiohttp.ClientSession, image_url: str) -> tuple[bytes, str]:
        """Download a remote image and return its bytes plus content type."""
        start_time = time.time()
        logger.debug(f"Start downloading image: {image_url}")

        try:
            async with session.get(image_url) as response:
                if response.status != 200:
                    raise Exception(f"Download failed with status {response.status}")

                content_type = response.headers.get("content-type", "")
                if not content_type.startswith("image/"):
                    raise Exception(f"Unexpected content type: {content_type}")

                image_data = await response.read()
                elapsed = time.time() - start_time
                logger.debug(
                    f"Image downloaded successfully: size={len(image_data)} elapsed={elapsed:.2f}s"
                )
                return image_data, content_type
        except Exception as exc:
            logger.debug(f"Image download failed: {exc}")
            raise

    async def _upload_to_picgo(
        self,
        session: aiohttp.ClientSession,
        image_data: bytes,
        filename: str,
        content_type: str,
    ) -> str:
        """Upload a single image to PicList/PicGo."""
        start_time = time.time()
        logger.debug(f"Start uploading image to PicGo: {filename}")

        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                form = aiohttp.FormData()
                form.add_field(
                    "image",
                    image_data,
                    filename=filename,
                    content_type=content_type or "application/octet-stream",
                )

                upload_url = urljoin(self.picgo_server, self.upload_path)
                logger.debug(f"Upload URL: {upload_url}")

                timeout = aiohttp.ClientTimeout(total=30)
                async with session.post(upload_url, data=form, timeout=timeout) as response:
                    if response.status != 200:
                        raise Exception(f"Upload failed with status {response.status}")

                    result = await response.json()
                    logger.debug(f"PicGo response: {json.dumps(result, ensure_ascii=False)}")

                    if not result.get("success"):
                        raise Exception(f"Upload failed: {result.get('msg')}")
                    if not result.get("result"):
                        raise Exception("Upload succeeded but returned no URL")

                    new_url = result["result"][0]
                    if not new_url:
                        raise Exception("Upload succeeded but returned an empty URL")

                    elapsed = time.time() - start_time
                    logger.debug(f"Image uploaded successfully: {new_url} elapsed={elapsed:.2f}s")
                    return new_url

            except asyncio.TimeoutError:
                retry_count += 1
                if retry_count < max_retries:
                    logger.debug(f"Upload timed out, retrying ({retry_count}/{max_retries})")
                    await asyncio.sleep(2)
                else:
                    raise Exception("Upload timed out repeatedly")
            except Exception as exc:
                retry_count += 1
                if retry_count < max_retries:
                    logger.debug(f"Upload failed: {exc}, retrying ({retry_count}/{max_retries})")
                    await asyncio.sleep(2)
                else:
                    raise Exception(f"Upload failed after retries: {exc}")

    async def _process_single_image(
        self, session: aiohttp.ClientSession, image_url: str, alt: str
    ) -> Tuple[str, str]:
        """Download and upload one image."""
        start_time = time.time()

        try:
            image_data, content_type = await self._download_image(session, image_url)
            filename = self._guess_upload_filename(image_url, alt, content_type, image_data)

            debug_manager.save_binary_file(f"image_{filename}", image_data, prefix="img")

            new_url = await self._upload_to_picgo(session, image_data, filename, content_type)
            elapsed = time.time() - start_time
            logger.debug(f"Single image processed successfully: elapsed={elapsed:.2f}s")
            return image_url, new_url
        except Exception as exc:
            logger.debug(f"Processing image failed: {exc}")
            return image_url, image_url

    async def upload_images(self, images: List[Tuple[str, str]]) -> Dict[str, str]:
        """Upload all images concurrently."""
        if not images:
            return {}

        start_time = time.time()
        logger.info(f"[ImageUploader] Start processing {len(images)} images")

        with tempfile.TemporaryDirectory() as temp_dir:
            logger.debug(f"Created temp directory: {temp_dir}")

            semaphore = asyncio.Semaphore(2)
            timeout = aiohttp.ClientTimeout(total=60)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async def process_with_semaphore(image_url: str, alt: str) -> Tuple[str, str]:
                    async with semaphore:
                        try:
                            return await self._process_single_image(session, image_url, alt)
                        except Exception as exc:
                            logger.debug(f"Processing image failed: {exc}")
                            return image_url, image_url

                tasks = [
                    asyncio.create_task(process_with_semaphore(image_url, alt))
                    for image_url, alt in images
                ]

                try:
                    results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=120)
                except asyncio.TimeoutError:
                    logger.debug("Image processing exceeded 120 seconds, cancelling remaining tasks")
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    results = [(image_url, image_url) for image_url, _ in images]

                url_mapping = {old_url: new_url for old_url, new_url in results}

                debug_manager.save_file(
                    "url_mapping.json",
                    json.dumps(url_mapping, ensure_ascii=False, indent=2),
                    prefix="img",
                )

                elapsed = time.time() - start_time
                logger.info(f"[ImageUploader] Processing complete: count={len(url_mapping)}, time={elapsed:.2f}s")
                for old_url, new_url in url_mapping.items():
                    logger.debug(f"[ImageUploader] URL mapping: {old_url} -> {new_url}")

                return url_mapping

    def replace_image_urls(self, markdown: str, url_mapping: Dict[str, str]) -> str:
        """Replace remote image URLs in Markdown with uploaded local targets."""
        start_time = time.time()
        logger.debug("Start replacing image URLs")

        debug_manager.save_file("before_replace.md", markdown, prefix="img")
        debug_manager.save_file(
            "replace_mapping.json",
            json.dumps(url_mapping, indent=2, ensure_ascii=False),
            prefix="img",
        )

        for old_url, new_url in url_mapping.items():
            logger.debug(f"Replace image URL: {old_url} -> {new_url}")
            target_type, rendered_target = self._normalize_local_image_target(new_url)
            old_url_escaped = re.escape(old_url)

            if target_type == "wikilink":
                markdown = re.sub(
                    f"!\\[(.*?)\\]\\({old_url_escaped}\\)",
                    f"![[{rendered_target}]]",
                    markdown,
                )
                markdown = re.sub(
                    f"!\\[\\]\\({old_url_escaped}\\)",
                    f"![[{rendered_target}]]",
                    markdown,
                )
            else:
                markdown = re.sub(
                    f"!\\[(.*?)\\]\\({old_url_escaped}\\)",
                    f"![\\1]({rendered_target})",
                    markdown,
                )
                markdown = re.sub(
                    f"!\\[\\]\\({old_url_escaped}\\)",
                    f"![]({rendered_target})",
                    markdown,
                )
                markdown = markdown.replace(old_url, rendered_target)

        debug_manager.save_file("final.md", markdown, prefix="img")

        elapsed = time.time() - start_time
        logger.debug(f"Image URL replacement complete: elapsed={elapsed:.2f}s")
        return markdown


image_uploader = ImageUploader()

"""
Markdown conversion service.
"""

import re
import time
from typing import List, Tuple

from bs4 import BeautifulSoup
from markdownify import markdownify as md

from ..logger import logger
from ..utils.debug_manager import debug_manager


class MarkdownConverter:
    """Convert HTML into Markdown and track image URLs."""

    def _extract_images(self, html: str) -> List[Tuple[str, str]]:
        """Extract image URLs from regular img tags."""
        start_time = time.time()
        logger.debug("Start extracting image URLs")

        soup = BeautifulSoup(html, "html.parser")
        images: List[Tuple[str, str]] = []

        for img in soup.find_all("img"):
            src = img.get("src", "") or img.get("data-src", "")
            if src:
                alt = img.get("alt", "")
                images.append((src, alt))
                img["data-processed"] = "true"

        if images:
            debug_manager.save_file(
                "images.txt",
                "\n".join([f"{src}\t{alt}" for src, alt in images]),
                prefix="md",
            )

        elapsed = time.time() - start_time
        logger.debug(f"Image extraction complete: count={len(images)} elapsed={elapsed:.2f}s")
        return images

    def _clean_html(self, html: str) -> str:
        """Drop noisy tags while preserving readable structure."""
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "meta", "link", "noscript", "iframe"]):
            tag.decompose()

        for span in soup.find_all("span"):
            if not span.get_text(strip=True):
                span.decompose()

        for a in soup.find_all("a"):
            href = a.get("href", "")
            text = a.get_text(strip=True)
            if not href or "javascript:" in href:
                if text:
                    a.replace_with(text)
                else:
                    a.decompose()

        for section in soup.find_all("section"):
            links = section.find_all("a")
            headings = section.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
            images = section.find_all("img")

            if links or headings or images:
                section.append(soup.new_string("\n\n"))
                continue

            span = section.find("span")
            if span:
                text = span.get_text()
                section.clear()
                section.append(soup.new_string(text + "\n\n"))
            elif section.get_text(strip=True):
                text = section.get_text()
                section.clear()
                section.append(soup.new_string(text + "\n\n"))

        for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            if heading.previous_sibling:
                heading.insert_before(soup.new_string("\n\n"))
            if heading.next_sibling:
                heading.append(soup.new_string("\n\n"))

        return str(soup)

    def _extract_wechat_js_content(self, html: str) -> str:
        """Extract article HTML from WeChat JS payloads when needed."""
        match = re.search(r"content_noencode:\s*JsDecode\('([^']+)'\)", html)
        if not match:
            return ""

        content = match.group(1)
        content = content.replace("\\x0a", "\n")
        content = content.replace("\\x3c", "<")
        content = content.replace("\\x3e", ">")
        content = content.replace("\\x22", '"')
        content = content.replace("\\x26amp;", "&")
        content = content.replace("\\x27", "'")
        content = content.replace("\\/", "/")
        content = content.replace("\\\\", "\\")

        logger.debug(f"Extracted WeChat JS content, length={len(content)}")
        return content

    def _extract_wechat_images(self, html: str) -> List[Tuple[str, str]]:
        """Extract正文图片 from WeChat picture_page_info_list."""
        match = re.search(r"picture_page_info_list\s*=\s*(\[[\s\S]*?\])\s*\.slice", html)
        if not match:
            return []

        raw_list = match.group(1)
        main_urls = re.findall(r"\{\s*width:[^}]*?cdn_url:\s*'([^']+)'", raw_list)

        images: List[Tuple[str, str]] = []
        seen = set()
        for url in main_urls:
            url = url.replace("\\x26amp;", "&")
            url = url.replace("\\x26", "&")
            url = url.replace("\\x22", '"')
            if url in seen:
                continue
            seen.add(url)
            images.append((url, ""))

        logger.debug(f"Extracted WeChat images from JS: count={len(images)}")
        return images

    def _clean_wechat_content(self, html: str) -> str:
        """Choose the best available WeChat article body extraction strategy."""
        cut_point = html.find("预览时标签不可点")
        if cut_point != -1:
            logger.info("[MarkdownConverter] Parse mode: truncated WeChat HTML")
            return html[:cut_point].strip()

        js_content = self._extract_wechat_js_content(html)
        if js_content:
            logger.info("[MarkdownConverter] Parse mode: WeChat JS fallback")
            paragraphs = js_content.split("\n\n")
            html_paragraphs = []
            for paragraph in paragraphs:
                paragraph = paragraph.strip()
                if not paragraph:
                    continue
                if "<a " in paragraph or "<img " in paragraph:
                    html_paragraphs.append(f"<p>{paragraph}</p>")
                else:
                    paragraph_html = paragraph.replace("\n", "<br/>")
                    html_paragraphs.append(f"<p>{paragraph_html}</p>")

            result = "\n".join(html_paragraphs)
            return re.sub(r'data-src="([^"]*)"', r'src="\1"', result)

        logger.info("[MarkdownConverter] Parse mode: raw HTML")
        return html

    def _strip_empty_image_placeholders(self, markdown: str) -> str:
        """Remove broken image placeholders such as ![]()."""
        markdown = re.sub(r"^[ \t]*!\[[^\]]*\]\(\s*\)[ \t]*\n?", "", markdown, flags=re.MULTILINE)
        markdown = re.sub(r"\n{3,}", "\n\n", markdown)
        return markdown.strip() + "\n"

    def _merge_wechat_images_into_markdown(
        self, markdown: str, expected_images: List[Tuple[str, str]]
    ) -> str:
        """Ensure extracted article images are still present after markdownify."""
        if not expected_images:
            return self._strip_empty_image_placeholders(markdown)

        present_urls = {
            url.strip()
            for url in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", markdown)
            if url.strip()
        }
        missing_urls = [url for url, _ in expected_images if url and url not in present_urls]

        next_index = 0

        def replace_placeholder(_: re.Match[str]) -> str:
            nonlocal next_index
            if next_index >= len(missing_urls):
                return ""
            next_index += 1
            return f"![图片{next_index}]({missing_urls[next_index - 1]})"

        markdown = re.sub(r"!\[[^\]]*\]\(\s*\)", replace_placeholder, markdown)

        if next_index < len(missing_urls):
            remaining = missing_urls[next_index:]
            image_block = "\n\n".join(
                f"![图片{index}]({url})"
                for index, url in enumerate(remaining, start=next_index + 1)
            )
            heading_match = re.search(r"^# .+$", markdown, flags=re.MULTILINE)
            if heading_match:
                insert_at = heading_match.end()
                markdown = markdown[:insert_at] + "\n\n" + image_block + markdown[insert_at:]
            else:
                markdown = image_block + "\n\n" + markdown

        return self._strip_empty_image_placeholders(markdown)

    def convert(self, html: str) -> Tuple[str, List[Tuple[str, str]]]:
        """Convert HTML into Markdown and collect image metadata."""
        try:
            start_time = time.time()
            logger.info("[MarkdownConverter] Start converting HTML to Markdown")

            debug_manager.save_file("original.html", html, prefix="md")

            wechat_images = self._extract_wechat_images(html)
            html = self._clean_wechat_content(html)
            tag_images = self._extract_images(html)

            seen_urls = set()
            images: List[Tuple[str, str]] = []
            for image_url, alt in wechat_images + tag_images:
                if image_url in seen_urls:
                    continue
                seen_urls.add(image_url)
                images.append((image_url, alt))

            if wechat_images:
                logger.info(
                    "[MarkdownConverter] Image sources: "
                    f"WeChatJS={len(wechat_images)}, HTMLTags={len(tag_images)}, merged={len(images)}"
                )

            html = self._clean_html(html)
            debug_manager.save_file("processed.html", html, prefix="md")

            markdown = md(
                html,
                heading_style="ATX",
                bullets="-",
                autolinks=True,
                wrap=False,
                default_title=True,
                escape_underscores=True,
                newline_style="\n",
                strip=["script", "style", "meta", "link", "noscript", "iframe"],
                options={
                    "emphasis_mark": "*",
                    "code_mark": "`",
                    "hr_mark": "---",
                    "br_mark": "  \n",
                    "strong_mark": "**",
                    "link_brackets": True,
                    "convert_links": True,
                    "keep_links": True,
                },
            )

            markdown = re.sub(r"\n{3,}", "\n\n", markdown)
            markdown = re.sub(r"(\[.*?\]\(.*?\))\n", r"\1\n\n", markdown)
            markdown = self._merge_wechat_images_into_markdown(markdown, images)

            debug_manager.save_file("result.md", markdown, prefix="md")

            elapsed = time.time() - start_time
            logger.info(f"[MarkdownConverter] Conversion complete: images={len(images)}, time={elapsed:.2f}s")
            return markdown, images
        except Exception as exc:
            error_msg = f"Markdown conversion failed: {exc}"
            logger.error(f"[MarkdownConverter] {error_msg}")
            raise Exception(error_msg)


markdown_converter = MarkdownConverter()

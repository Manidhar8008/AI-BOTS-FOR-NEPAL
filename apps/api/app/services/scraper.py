from __future__ import annotations

import asyncio
import hashlib
import os
import re
import tempfile
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
import pymupdf4llm
from bs4 import BeautifulSoup

from app.core.config import settings

DocumentKind = Literal["html", "pdf"]


@dataclass(frozen=True)
class CrawledDocument:
    """A source document extracted from a tenant website.

    Text is intentionally markdown-ish rather than plain text so headers, table
    rows, and PDF structure survive well enough for semantic chunking and cited
    answers.
    """

    source_url: str
    doc_type: DocumentKind
    text: str
    title: str | None
    content_hash: str
    byte_size: int
    http_status: int
    metadata: dict[str, str | int | float | bool | None] = field(default_factory=dict)


@dataclass(frozen=True)
class CrawlResult:
    """Result object with enough counts to update scrape job progress."""

    documents: list[CrawledDocument]
    discovered_urls: set[str]
    failed_urls: list[str]


class GovernmentSiteScraper:
    """Bounded same-domain crawler for large government websites.

    This MVP crawler is deliberately conservative:
    - same-domain links only, preventing accidental web-wide crawls;
    - breadth-first traversal, so high-level pages are captured first;
    - hard max page and depth limits, because government sites can contain
      years of notices and hundreds of PDFs.
    """

    def __init__(
        self,
        *,
        max_pages: int | None = None,
        max_depth: int | None = None,
        timeout_seconds: float | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.max_pages = max_pages or settings.max_crawl_pages
        self.max_depth = max_depth or settings.max_crawl_depth
        self.timeout_seconds = timeout_seconds or settings.crawl_timeout_seconds
        self.user_agent = user_agent or settings.crawl_user_agent

    async def crawl(self, start_url: str) -> CrawlResult:
        """Crawl a target URL and return extracted HTML/PDF documents."""
        normalized_start_url = self._normalize_url(start_url)
        base_domain = self._normalized_domain(normalized_start_url)

        queue: deque[tuple[str, int]] = deque([(normalized_start_url, 0)])
        visited: set[str] = set()
        discovered_urls: set[str] = {normalized_start_url}
        failed_urls: list[str] = []
        documents: list[CrawledDocument] = []

        timeout = httpx.Timeout(self.timeout_seconds)
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
        }

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout,
            headers=headers,
        ) as client:
            while queue and len(documents) < self.max_pages:
                current_url, depth = queue.popleft()
                if current_url in visited:
                    continue

                visited.add(current_url)

                try:
                    response = await client.get(current_url)
                    response.raise_for_status()
                except httpx.HTTPError:
                    failed_urls.append(current_url)
                    continue

                content_type = response.headers.get("content-type", "").lower()
                is_pdf = self._looks_like_pdf(current_url, content_type)

                if is_pdf:
                    document = await self._extract_pdf(response, current_url, depth)
                    if document is not None:
                        documents.append(document)
                    continue

                document, links = self._extract_html_and_links(
                    response=response,
                    source_url=current_url,
                    base_domain=base_domain,
                    depth=depth,
                )

                if document is not None:
                    documents.append(document)

                if depth >= self.max_depth:
                    continue

                for link in links:
                    if len(discovered_urls) >= self.max_pages * 4:
                        # Avoid unbounded queues on sites with huge archives.
                        break
                    if link not in visited and link not in discovered_urls:
                        discovered_urls.add(link)
                        queue.append((link, depth + 1))

        return CrawlResult(
            documents=documents,
            discovered_urls=discovered_urls,
            failed_urls=failed_urls,
        )

    def _extract_html_and_links(
        self,
        *,
        response: httpx.Response,
        source_url: str,
        base_domain: str,
        depth: int,
    ) -> tuple[CrawledDocument | None, list[str]]:
        """Extract markdown-friendly text and same-domain links from an HTML page."""
        soup = BeautifulSoup(response.text, "lxml")

        title = self._clean_inline_text(soup.title.get_text(" ")) if soup.title else None
        links = self._discover_links(soup=soup, source_url=source_url, base_domain=base_domain)

        for tag in soup(["script", "style", "noscript", "svg", "canvas", "iframe"]):
            tag.decompose()

        text = self._html_to_markdownish_text(soup)
        if len(text) < 120:
            return None, links

        body_bytes = response.content or text.encode("utf-8")
        date_scraped = datetime.now(UTC).isoformat()

        return (
            CrawledDocument(
                source_url=source_url,
                doc_type="html",
                text=text,
                title=title,
                content_hash=self._hash_text(text),
                byte_size=len(body_bytes),
                http_status=response.status_code,
                metadata={
                    "content_type": response.headers.get("content-type"),
                    "crawl_depth": depth,
                    "date_scraped": date_scraped,
                },
            ),
            links,
        )

    async def _extract_pdf(
        self,
        response: httpx.Response,
        source_url: str,
        depth: int,
    ) -> CrawledDocument | None:
        """Extract PDF content with PyMuPDF4LLM to preserve headers/tables as markdown."""
        pdf_bytes = response.content
        if not pdf_bytes:
            return None

        markdown = await asyncio.to_thread(self._pdf_bytes_to_markdown, pdf_bytes)
        markdown = self._normalize_document_text(markdown)
        if len(markdown) < 80:
            return None

        filename = os.path.basename(urlparse(source_url).path) or None
        date_scraped = datetime.now(UTC).isoformat()

        return CrawledDocument(
            source_url=source_url,
            doc_type="pdf",
            text=markdown,
            title=filename,
            content_hash=self._hash_text(markdown),
            byte_size=len(pdf_bytes),
            http_status=response.status_code,
            metadata={
                "content_type": response.headers.get("content-type"),
                "crawl_depth": depth,
                "date_scraped": date_scraped,
            },
        )

    @staticmethod
    def _pdf_bytes_to_markdown(pdf_bytes: bytes) -> str:
        """Run PyMuPDF4LLM against a temp file because it expects a file path."""
        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
                temp_file.write(pdf_bytes)
                temp_path = temp_file.name

            return pymupdf4llm.to_markdown(temp_path)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    def _discover_links(
        self,
        *,
        soup: BeautifulSoup,
        source_url: str,
        base_domain: str,
    ) -> list[str]:
        """Return normalized same-domain HTML/PDF links from a page."""
        links: list[str] = []

        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href")
            if not href or href.startswith(("mailto:", "tel:", "javascript:")):
                continue

            candidate = self._normalize_url(urljoin(source_url, href))
            parsed = urlparse(candidate)
            if parsed.scheme not in {"http", "https"}:
                continue
            if self._normalized_domain(candidate) != base_domain:
                continue

            links.append(candidate)

        # Stable ordering keeps crawl behavior predictable and easier to debug.
        return sorted(set(links))

    @staticmethod
    def _html_to_markdownish_text(soup: BeautifulSoup) -> str:
        """Convert useful HTML elements into text that preserves document shape."""
        lines: list[str] = []

        # Prefer semantic containers when present, but gracefully fall back to body.
        root = soup.find("main") or soup.find("article") or soup.body or soup

        for element in root.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "tr"]):
            name = element.name.lower()

            if name.startswith("h"):
                level = int(name[1])
                text = GovernmentSiteScraper._clean_inline_text(element.get_text(" "))
                if text:
                    lines.append(f"{'#' * level} {text}")
                continue

            if name == "tr":
                cells = [
                    GovernmentSiteScraper._clean_inline_text(cell.get_text(" "))
                    for cell in element.find_all(["th", "td"])
                ]
                cells = [cell for cell in cells if cell]
                if cells:
                    lines.append(" | ".join(cells))
                continue

            text = GovernmentSiteScraper._clean_inline_text(element.get_text(" "))
            if text:
                prefix = "- " if name == "li" else ""
                lines.append(f"{prefix}{text}")

        if not lines:
            lines.append(root.get_text(separator=" "))

        return GovernmentSiteScraper._normalize_document_text("\n".join(lines))

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Remove fragments and normalize obvious URL noise without changing semantics."""
        url_without_fragment, _fragment = urldefrag(url.strip())
        parsed = urlparse(url_without_fragment)

        # Remove trailing slashes except for bare domains to improve dedupe.
        normalized = parsed.geturl()
        if parsed.path not in {"", "/"}:
            normalized = normalized.rstrip("/")

        return normalized

    @staticmethod
    def _normalized_domain(url: str) -> str:
        """Compare domains in a www-insensitive way."""
        return urlparse(url).netloc.lower().removeprefix("www.")

    @staticmethod
    def _looks_like_pdf(url: str, content_type: str) -> bool:
        parsed_path = urlparse(url).path.lower()
        return parsed_path.endswith(".pdf") or "application/pdf" in content_type

    @staticmethod
    def _clean_inline_text(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _normalize_document_text(text: str) -> str:
        text = text.replace("\x00", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

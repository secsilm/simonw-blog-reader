"""Fetch and parse Simon Willison blog posts and the pages they reference.

The blog uses a fairly stable HTML structure (an ``<article>`` or
``div.entry``-style container per post). We try those selectors first and
fall back to ``trafilatura`` for arbitrary external pages.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

USER_AGENT = (
    "simonw-blog-reader/0.1 (+https://github.com/secsilm/simonw-blog-reader)"
)

DEFAULT_TIMEOUT = 20.0

# Extensions that aren't worth fetching as references.
_BINARY_EXTS = (
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
    ".mp3", ".mp4", ".mov", ".webm", ".zip", ".tar", ".gz",
)


class FetchError(RuntimeError):
    """Raised when a URL cannot be fetched or parsed."""


@dataclass
class Reference:
    url: str
    anchor_text: str
    context: str  # Surrounding paragraph text, for understanding the citation's role.


@dataclass
class BlogPost:
    url: str
    title: str
    text: str  # Plain-text article body, one paragraph per line.
    html_excerpt: str = ""  # Optional: small slice of original HTML, for debugging.
    references: list[Reference] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Low-level HTTP


def _client(**kwargs) -> httpx.Client:
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en;q=0.9"}
    return httpx.Client(
        headers=headers,
        follow_redirects=True,
        timeout=DEFAULT_TIMEOUT,
        **kwargs,
    )


def fetch_html(url: str) -> str:
    """Download a URL and return its HTML body. Raises ``FetchError`` on failure."""
    try:
        with _client() as client:
            resp = client.get(url)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise FetchError(f"Failed to fetch {url}: {exc}") from exc

    ctype = resp.headers.get("content-type", "")
    if "html" not in ctype and "xml" not in ctype:
        raise FetchError(
            f"Unsupported content-type {ctype!r} for {url} (expected HTML)"
        )
    return resp.text


# ---------------------------------------------------------------------------
# Parsing Simon's blog posts


_MAIN_SELECTORS = ("article", "div.entry", "div.entryPage", "main", "#primary")


def _find_main(soup: BeautifulSoup) -> Tag:
    for sel in _MAIN_SELECTORS:
        node = soup.select_one(sel)
        if node:
            return node
    return soup.body or soup


def _clean_text(node: Tag) -> str:
    # Drop noise that confuses the LLM.
    for bad in node.select("script, style, noscript, nav, footer, .meta, .tags"):
        bad.decompose()
    # Convert <br> to newlines, then collapse paragraphs.
    for br in node.find_all("br"):
        br.replace_with("\n")
    paragraphs: list[str] = []
    for block in node.find_all(["p", "li", "h1", "h2", "h3", "h4", "blockquote", "pre"]):
        text = block.get_text(" ", strip=True)
        if text:
            paragraphs.append(text)
    if not paragraphs:
        # Fallback: whole-node text.
        return re.sub(r"\n{3,}", "\n\n", node.get_text("\n", strip=True))
    return "\n\n".join(paragraphs)


def _extract_title(soup: BeautifulSoup, main: Tag) -> str:
    for sel in ("h1", "h2", "header h2"):
        n = main.select_one(sel)
        if n and n.get_text(strip=True):
            return n.get_text(strip=True)
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return "(untitled)"


def _is_useful_link(href: str, base_url: str) -> bool:
    href, _ = urldefrag(href)
    if not href:
        return False
    parsed = urlparse(href)
    if parsed.scheme not in ("http", "https"):
        return False
    base = urlparse(base_url)
    # Skip same-page or pure-fragment links.
    if (parsed.netloc == base.netloc) and parsed.path == base.path:
        return False
    if parsed.path.lower().endswith(_BINARY_EXTS):
        return False
    return True


def _extract_references(main: Tag, base_url: str) -> list[Reference]:
    seen: set[str] = set()
    refs: list[Reference] = []
    for a in main.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        href, _ = urldefrag(href)
        if not _is_useful_link(href, base_url):
            continue
        if href in seen:
            continue
        seen.add(href)

        anchor = a.get_text(" ", strip=True)
        # Find enclosing paragraph-like ancestor for context.
        ctx_node: Tag | None = a
        for parent in a.parents:
            if isinstance(parent, Tag) and parent.name in (
                "p", "li", "blockquote", "h1", "h2", "h3", "h4",
            ):
                ctx_node = parent
                break
        ctx = ctx_node.get_text(" ", strip=True) if ctx_node else anchor
        refs.append(Reference(url=href, anchor_text=anchor, context=ctx))
    return refs


def fetch_and_parse(url: str) -> BlogPost:
    """Fetch a Simon Willison blog post and return its parsed representation."""
    html = fetch_html(url)
    soup = BeautifulSoup(html, "lxml")
    main = _find_main(soup)
    title = _extract_title(soup, main)
    references = _extract_references(main, url)
    text = _clean_text(main)
    if not text.strip():
        raise FetchError(f"Could not extract any readable content from {url}")
    return BlogPost(
        url=url,
        title=title,
        text=text,
        html_excerpt=str(main)[:2000],
        references=references,
    )


# ---------------------------------------------------------------------------
# Generic readable extraction (used for referenced pages)


def fetch_readable(url: str, max_chars: int = 6000) -> str:
    """Fetch a URL and return readable plain text, truncated to ``max_chars``.

    Uses ``trafilatura`` for robustness against arbitrary site layouts.
    """
    html = fetch_html(url)
    extracted = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=False,
        favor_recall=True,
        url=url,
    )
    if not extracted:
        # Last-ditch fallback: strip tags ourselves.
        soup = BeautifulSoup(html, "lxml")
        for bad in soup.select("script, style, nav, footer, header"):
            bad.decompose()
        extracted = soup.get_text(" ", strip=True)
    extracted = re.sub(r"\n{3,}", "\n\n", extracted).strip()
    if not extracted:
        raise FetchError(f"No extractable text in {url}")
    if len(extracted) > max_chars:
        extracted = extracted[:max_chars].rstrip() + "\n\n[...truncated...]"
    return extracted


# ---------------------------------------------------------------------------
# Helpers


def select_top_references(
    refs: Iterable[Reference], limit: int
) -> list[Reference]:
    """Pick the most informative subset of references.

    Prefers references with a meaningful anchor text (more than just "here"
    or a domain name).
    """
    weak = {"here", "this", "link", "post", "tweet", "article"}
    scored: list[tuple[int, Reference]] = []
    for r in refs:
        score = 0
        anchor = (r.anchor_text or "").strip().lower()
        if anchor and anchor not in weak and len(anchor) > 3:
            score += 2
        if len(r.context) > 80:
            score += 1
        scored.append((score, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:limit]]

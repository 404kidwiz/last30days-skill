"""DuckDuckGo HTML web search via Scrapling — key-free web fallback.

Scrapes DuckDuckGo HTML results using Scrapling when no grounding API key
(Brave/Exa/Serper) is available.

Install:   pip install scrapling
Stealth:   pip install "scrapling[fetchers]" && scrapling install
           then set SCRAPLING_STEALTH=true in config for StealthyFetcher.

Auto-enabled when scrapling package is importable; no API key required.
Opt-in forced: add 'scrapling' to INCLUDE_SOURCES to always activate.
"""

import sys
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlencode, urlparse

from . import log
from .relevance import token_overlap_relevance as _compute_relevance

DUCKDUCKGO_URL = "https://html.duckduckgo.com/html/"

DEPTH_CONFIG = {
    "quick":   {"results": 8},
    "default": {"results": 15},
    "deep":    {"results": 25},
}

# Headers to look like a real browser to DDG
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _log(msg: str) -> None:
    log.source_log("Scrapling", msg)


def is_available() -> bool:
    """Return True if scrapling package can be imported."""
    try:
        import scrapling  # noqa: F401
        return True
    except ImportError:
        return False


def _extract_real_url(ddg_href: str) -> str:
    """Extract actual destination URL from a DuckDuckGo redirect href.

    DDG wraps result links as //duckduckgo.com/l/?uddg=ENCODED_URL.
    If the href is already a direct URL, return it unchanged.
    """
    if not ddg_href:
        return ""
    if ddg_href.startswith("//"):
        ddg_href = "https:" + ddg_href
    try:
        parsed = urlparse(ddg_href)
        if "duckduckgo.com" in (parsed.netloc or "") and parsed.path.startswith("/l/"):
            params = parse_qs(parsed.query)
            uddg = params.get("uddg", [""])[0]
            return unquote(uddg) if uddg else ddg_href
    except Exception:
        pass
    return ddg_href


def _get_attr(element: Any, attr: str) -> str:
    """Safely extract an attribute from a Scrapling element."""
    try:
        # Scrapling supports .get_attribute() as primary method
        val = element.get_attribute(attr)
        if val:
            return str(val)
    except (AttributeError, Exception):
        pass
    try:
        # Some versions expose dict-like access
        val = element[attr]
        if val:
            return str(val)
    except (KeyError, TypeError, Exception):
        pass
    return ""


def _css_text(element: Any, selector: str) -> str:
    """Extract text via CSS selector with ::text pseudo-element."""
    try:
        return (element.css(f"{selector}::text").get() or "").strip()
    except Exception:
        return ""


def _parse_results(page: Any, topic: str, max_results: int) -> List[Dict[str, Any]]:
    """Parse DuckDuckGo HTML results into normalized dicts."""
    items: List[Dict[str, Any]] = []
    try:
        result_elements = page.css(".result") or []
    except Exception:
        return []

    seen_urls: set[str] = set()
    for i, elem in enumerate(result_elements):
        if len(items) >= max_results:
            break
        try:
            # Title and URL from the result anchor
            anchors = elem.css(".result__a") or []
            if not anchors:
                continue
            anchor = anchors[0] if hasattr(anchors, "__getitem__") else anchors

            # Handle both list-like and single-element responses
            if isinstance(anchor, list):
                if not anchor:
                    continue
                anchor = anchor[0]

            title = _css_text(anchor, "")
            if not title:
                # Fallback: try getting text directly
                try:
                    title = (anchor.css("::text").get() or "").strip()
                except Exception:
                    continue
            if not title:
                continue

            href = _get_attr(anchor, "href")
            real_url = _extract_real_url(href)

            # Skip duplicate URLs
            if real_url and real_url in seen_urls:
                continue
            if real_url:
                seen_urls.add(real_url)

            snippet = _css_text(elem, ".result__snippet")
            domain = _css_text(elem, ".result__url")

            # Use domain as fallback URL
            if not real_url and domain:
                real_url = f"https://{domain.lstrip('/')}"

            rank_score = max(0.2, 1.0 - (i * 0.03))
            text_relevance = _compute_relevance(topic, f"{title} {snippet}")
            relevance = min(1.0, text_relevance * 0.5 + rank_score * 0.4 + 0.1)

            items.append({
                "id": f"SL{i + 1}",
                "title": title,
                "snippet": snippet,
                "url": real_url,
                "date": None,
                "source_domain": domain or (urlparse(real_url).netloc if real_url else ""),
                "relevance": round(relevance, 2),
                "why_relevant": f"Web: {title[:70]}",
                "engagement": {},
                "metadata": {"scraped_by": "scrapling"},
            })
        except Exception:
            continue

    return items


def search_scrapling(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    stealth: bool = False,
) -> Dict[str, Any]:
    """Search DuckDuckGo HTML via Scrapling for key-free web results.

    Args:
        topic: Search query
        from_date: Start date (YYYY-MM-DD) — used only for context; DDG df=m applied
        to_date: End date (YYYY-MM-DD)
        depth: 'quick', 'default', or 'deep'
        stealth: Use StealthyFetcher (requires scrapling[fetchers] + scrapling install)

    Returns:
        Dict with 'items' list and optional 'error'.
    """
    config = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])

    # Dynamic import so missing package fails gracefully
    try:
        if stealth:
            from scrapling.fetchers import StealthyFetcher as _FetcherCls
            _log("Using StealthyFetcher (stealth mode)")
        else:
            from scrapling.fetchers import Fetcher as _FetcherCls
    except ImportError as exc:
        msg = "scrapling not installed"
        if stealth:
            msg = "scrapling[fetchers] not installed (pip install \"scrapling[fetchers]\" && scrapling install)"
        return {"items": [], "error": msg}

    # DDG time filter: month (~30 days) matches skill default
    params = urlencode({"q": topic, "df": "m"})
    url = f"{DUCKDUCKGO_URL}?{params}"

    _log(f"Searching DuckDuckGo HTML for '{topic}' (depth={depth})")

    try:
        if stealth:
            # StealthyFetcher uses .fetch(), not .get(); no custom headers (browser handles them)
            page = _FetcherCls.fetch(url)
        else:
            page = _FetcherCls.get(url, headers=_HEADERS)
    except Exception as exc:
        _log(f"Fetch failed: {type(exc).__name__}: {exc}")
        return {"items": [], "error": f"{type(exc).__name__}: {exc}"}

    items = _parse_results(page, topic, config["results"])
    _log(f"Found {len(items)} web results")

    if not items:
        return {"items": [], "error": "No results from DuckDuckGo HTML"}

    return {"items": items}


def parse_scrapling_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return items list from a scrapling search response."""
    return response.get("items", [])

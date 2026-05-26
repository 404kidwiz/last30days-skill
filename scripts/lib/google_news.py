"""Google News RSS search — free, no key, returns dated news articles.

Fetches Google News RSS feed for a topic and parses items with title, URL,
publication date, and source publication name. Uses stdlib only — no extra
package install required.

Always available — pure urllib + xml.etree.ElementTree, no auth needed.
"""

import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from . import log
from .relevance import token_overlap_relevance as _compute_relevance

GNEWS_BASE = "https://news.google.com/rss/search"

DEPTH_CONFIG = {
    "quick":   {"results": 10},
    "default": {"results": 20},
    "deep":    {"results": 40},
}

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _log(msg: str) -> None:
    log.source_log("GNews", msg)


def _parse_pubdate(pubdate: str) -> Optional[str]:
    """Parse RFC 2822 pubDate (e.g. 'Mon, 01 Jan 2024 12:00:00 GMT') to YYYY-MM-DD."""
    if not pubdate:
        return None
    try:
        dt = parsedate_to_datetime(pubdate)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return None


def _parse_rss(xml_bytes: bytes, topic: str, max_results: int) -> List[Dict[str, Any]]:
    """Parse Google News RSS XML into normalized item dicts."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        _log(f"XML parse error: {exc}")
        return []

    channel = root.find("channel")
    if channel is None:
        return []

    items: List[Dict[str, Any]] = []
    for i, item_el in enumerate(channel.findall("item")):
        if len(items) >= max_results:
            break

        title = (item_el.findtext("title") or "").strip()
        link = (item_el.findtext("link") or "").strip()
        pub_date = (item_el.findtext("pubDate") or "").strip()
        description = (item_el.findtext("description") or "").strip()

        # <source url="https://...">Publication Name</source>
        source_el = item_el.find("source")
        source_name = ""
        if source_el is not None:
            source_name = (source_el.text or "").strip()

        if not title:
            continue

        date_str = _parse_pubdate(pub_date)
        rank_score = max(0.2, 1.0 - (i * 0.025))
        text_relevance = _compute_relevance(topic, f"{title} {description}")
        relevance = min(1.0, text_relevance * 0.55 + rank_score * 0.35 + 0.1)

        items.append({
            "id": f"GN{i + 1}",
            "title": title,
            "snippet": description,
            "url": link,
            "date": date_str,
            "source_domain": source_name,
            "relevance": round(relevance, 2),
            "why_relevant": f"Google News: {title[:70]}",
        })

    return items


def search_google_news(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
) -> Dict[str, Any]:
    """Search Google News RSS for recent articles about a topic.

    Args:
        topic: Search query
        from_date: Start date (YYYY-MM-DD) — used only for context; RSS returns ~7 days naturally
        to_date: End date (YYYY-MM-DD)
        depth: 'quick', 'default', or 'deep'

    Returns:
        Dict with 'items' list and optional 'error'.
    """
    config = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])

    params = urlencode({"q": topic, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    url = f"{GNEWS_BASE}?{params}"
    _log(f"Fetching Google News RSS for '{topic}' (depth={depth})")

    try:
        req = Request(url, headers={"User-Agent": _USER_AGENT})
        with urlopen(req, timeout=15) as resp:
            xml_bytes = resp.read()
    except Exception as exc:
        _log(f"Fetch error: {type(exc).__name__}: {exc}")
        return {"items": [], "error": f"{type(exc).__name__}: {exc}"}

    items = _parse_rss(xml_bytes, topic, config["results"])
    _log(f"Found {len(items)} Google News articles")

    if not items:
        return {"items": [], "error": "No results from Google News RSS"}

    return {"items": items}


def parse_google_news_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return items list from a Google News search response."""
    return response.get("items", [])

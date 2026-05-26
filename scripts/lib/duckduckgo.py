"""DuckDuckGo search via duckduckgo-search package — free, no API key.

Returns structured web and news results with dates via DDGS().news() and
DDGS().text(). Prefers news results (include publication date) and supplements
with text results when news returns few hits.

Requires: pip install duckduckgo-search
Auto-enabled when package is importable; no API key required.
"""

import math
from typing import Any, Dict, List, Optional

from . import dates, log
from .relevance import token_overlap_relevance as _compute_relevance

DEPTH_CONFIG = {
    "quick":   {"news": 8,  "text": 5},
    "default": {"news": 15, "text": 10},
    "deep":    {"news": 25, "text": 15},
}


def _log(msg: str) -> None:
    log.source_log("DDG", msg)


def is_available() -> bool:
    """Return True if duckduckgo-search package is importable."""
    try:
        from duckduckgo_search import DDGS  # noqa: F401
        return True
    except ImportError:
        return False


def _parse_news_items(raw_items: List[Dict[str, Any]], topic: str) -> List[Dict[str, Any]]:
    """Parse DDGS().news() results — includes publication date."""
    out = []
    for i, item in enumerate(raw_items):
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        body = str(item.get("body") or "").strip()
        source = str(item.get("source") or "").strip()
        date_raw = item.get("date")

        date_str = None
        if date_raw:
            d = dates.parse_date(str(date_raw))
            if d:
                date_str = d.strftime("%Y-%m-%d")

        rank_score = max(0.2, 1.0 - (i * 0.025))
        text_relevance = _compute_relevance(topic, f"{title} {body}")
        relevance = min(1.0, text_relevance * 0.5 + rank_score * 0.4 + 0.1)

        out.append({
            "id": f"DDG{i + 1}",
            "title": title,
            "snippet": body,
            "url": url,
            "date": date_str,
            "source_domain": source,
            "relevance": round(relevance, 2),
            "why_relevant": f"DDG news: {title[:70]}",
        })
    return out


def _parse_text_items(
    raw_items: List[Dict[str, Any]], topic: str, id_offset: int = 0
) -> List[Dict[str, Any]]:
    """Parse DDGS().text() results — no dates, general web."""
    out = []
    for i, item in enumerate(raw_items):
        title = str(item.get("title") or "").strip()
        url = str(item.get("href") or "").strip()
        body = str(item.get("body") or "").strip()

        rank_score = max(0.2, 1.0 - (i * 0.025))
        text_relevance = _compute_relevance(topic, f"{title} {body}")
        relevance = min(1.0, text_relevance * 0.5 + rank_score * 0.35 + 0.05)

        out.append({
            "id": f"DDG{id_offset + i + 1}",
            "title": title,
            "snippet": body,
            "url": url,
            "date": None,
            "source_domain": "",
            "relevance": round(relevance, 2),
            "why_relevant": f"DDG web: {title[:70]}",
        })
    return out


def search_duckduckgo(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
) -> Dict[str, Any]:
    """Search DuckDuckGo for news and web results.

    Args:
        topic: Search query
        from_date: Start date (YYYY-MM-DD) — used only for context; DDG timelimit='m' applied
        to_date: End date (YYYY-MM-DD)
        depth: 'quick', 'default', or 'deep'

    Returns:
        Dict with 'items' list and optional 'error'.
    """
    config = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])

    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return {"items": [], "error": "duckduckgo-search not installed (pip install duckduckgo-search)"}

    _log(f"Searching DDG news+web for '{topic}' (depth={depth})")

    items: List[Dict[str, Any]] = []

    # News first — returns dates
    try:
        with DDGS() as ddgs:
            news_raw = list(ddgs.news(topic, max_results=config["news"], timelimit="m"))
        items.extend(_parse_news_items(news_raw, topic))
        _log(f"News: {len(news_raw)} results")
    except Exception as exc:
        _log(f"News search failed: {type(exc).__name__}: {exc}")

    # Supplement with text results when news returned few hits
    if len(items) < config["news"] // 2:
        try:
            with DDGS() as ddgs:
                text_raw = list(ddgs.text(topic, max_results=config["text"], timelimit="m"))
            items.extend(_parse_text_items(text_raw, topic, id_offset=len(items)))
            _log(f"Text: {len(text_raw)} results (news was thin)")
        except Exception as exc:
            _log(f"Text search failed: {type(exc).__name__}: {exc}")

    dated = sum(1 for i in items if i.get("date"))
    _log(f"Total: {len(items)} results ({dated} with dates)")
    return {"items": items}


def parse_duckduckgo_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return items list from a duckduckgo search response."""
    return response.get("items", [])

"""GDELT global news monitoring — free REST API, no key required.

Uses GDELT 2.0 Document API (ArtList mode) to surface news articles matching
a query from thousands of global news sources. Results include publication
dates, source domain, and country of origin.

Always available — no Python package or API key needed, pure HTTP.
Reference: https://blog.gdeltproject.org/gdelt-2-0-our-global-news-archive-is-now-live/
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from . import http, log
from .relevance import token_overlap_relevance as _compute_relevance

GDELT_API = "https://api.gdeltproject.org/api/v2/doc/doc"

DEPTH_CONFIG = {
    "quick":   {"results": 10},
    "default": {"results": 20},
    "deep":    {"results": 40},
}


def _log(msg: str) -> None:
    log.source_log("GDELT", msg)


def _parse_seendate(seendate: str) -> Optional[str]:
    """Convert GDELT seendate (20240101T120000Z) to YYYY-MM-DD."""
    if not seendate:
        return None
    try:
        dt = datetime.strptime(seendate[:15], "%Y%m%dT%H%M%S")
        return dt.strftime("%Y-%m-%d")
    except (ValueError, IndexError):
        return None


def search_gdelt(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
) -> Dict[str, Any]:
    """Search GDELT global news coverage for a topic.

    Args:
        topic: Search query (supports GDELT query syntax: quotes, AND/OR/NOT)
        from_date: Start date (YYYY-MM-DD) — context only; GDELT timespan=1month applied
        to_date: End date (YYYY-MM-DD)
        depth: 'quick', 'default', or 'deep'

    Returns:
        Dict with 'items' list and optional 'error'.
    """
    config = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])

    params = {
        "query": topic,
        "mode": "ArtList",
        "maxrecords": config["results"],
        "timespan": "1month",
        "sort": "DateDesc",
        "format": "json",
    }
    url = f"{GDELT_API}?{urlencode(params)}"
    _log(f"Querying GDELT for '{topic}' (depth={depth}, max={config['results']})")

    try:
        data = http.get(url, timeout=20, retries=2)
    except Exception as exc:
        _log(f"GDELT API error: {exc}")
        return {"items": [], "error": f"{type(exc).__name__}: {exc}"}

    articles = data.get("articles") or []
    items: List[Dict[str, Any]] = []

    for i, art in enumerate(articles):
        url_str = str(art.get("url") or "").strip()
        title = str(art.get("title") or "").strip()
        domain = str(art.get("domain") or "").strip()
        seendate = art.get("seendate") or ""
        date_str = _parse_seendate(seendate)

        if not title:
            continue

        rank_score = max(0.2, 1.0 - (i * 0.025))
        text_relevance = _compute_relevance(topic, title)
        relevance = min(1.0, text_relevance * 0.55 + rank_score * 0.35 + 0.1)

        items.append({
            "id": f"GD{i + 1}",
            "title": title,
            "snippet": "",
            "url": url_str,
            "date": date_str,
            "source_domain": domain,
            "relevance": round(relevance, 2),
            "why_relevant": f"GDELT news: {title[:70]}",
            "metadata": {
                "language": art.get("language", ""),
                "sourcecountry": art.get("sourcecountry", ""),
            },
        })

    _log(f"Found {len(items)} GDELT news articles")
    return {"items": items}


def parse_gdelt_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return items list from a GDELT search response."""
    return response.get("items", [])

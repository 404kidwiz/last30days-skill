"""Dev.to developer articles API — free, no key required.

Searches the Forem/Dev.to public API for developer articles published within
the last 30 days. Returns titles, descriptions, publication dates, reaction
counts, and comment counts.

Always available — no package install or API key needed, pure HTTP.
Rate limit: 500 requests/hour unauthenticated.
"""

from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from . import dates, http, log
from .relevance import token_overlap_relevance as _compute_relevance

DEVTO_API = "https://dev.to/api/articles"

DEPTH_CONFIG = {
    "quick":   {"results": 10},
    "default": {"results": 20},
    "deep":    {"results": 40},
}


def _log(msg: str) -> None:
    log.source_log("Dev.to", msg)


def _parse_date(raw: str) -> Optional[str]:
    if not raw:
        return None
    d = dates.parse_date(raw)
    return d.strftime("%Y-%m-%d") if d else None


def search_devto(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
) -> Dict[str, Any]:
    """Search Dev.to for developer articles about a topic.

    Args:
        topic: Search query
        from_date: Start date (YYYY-MM-DD) — context only; top=30 applied
        to_date: End date (YYYY-MM-DD)
        depth: 'quick', 'default', or 'deep'

    Returns:
        Dict with 'items' list and optional 'error'.
    """
    config = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])

    params = urlencode({
        "q": topic,
        "top": 30,
        "per_page": config["results"],
    })
    url = f"{DEVTO_API}?{params}"
    _log(f"Searching Dev.to for '{topic}' (depth={depth})")

    try:
        articles = http.get(url, timeout=12, retries=2)
    except Exception as exc:
        _log(f"Dev.to API error: {exc}")
        return {"items": [], "error": f"{type(exc).__name__}: {exc}"}

    # API returns a list directly (not wrapped in a dict)
    if isinstance(articles, list):
        raw_list = articles
    else:
        raw_list = articles.get("items") or articles.get("data") or []

    items: List[Dict[str, Any]] = []
    for i, art in enumerate(raw_list):
        title = str(art.get("title") or "").strip()
        url_str = str(art.get("url") or "").strip()
        description = str(art.get("description") or "").strip()
        published_raw = art.get("published_at") or art.get("published_timestamp") or ""
        date_str = _parse_date(published_raw)

        tags = art.get("tag_list") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]

        user = art.get("user") or {}
        author = (user.get("name") or user.get("username") or "").strip()

        reactions = int(art.get("positive_reactions_count") or art.get("reactions_count") or 0)
        comments = int(art.get("comments_count") or 0)

        if not title:
            continue

        rank_score = max(0.2, 1.0 - (i * 0.025))
        text_relevance = _compute_relevance(topic, f"{title} {description}")
        relevance = min(1.0, text_relevance * 0.5 + rank_score * 0.4 + 0.1)

        items.append({
            "id": str(art.get("id") or f"DT{i + 1}"),
            "title": title,
            "snippet": description,
            "url": url_str,
            "date": date_str,
            "source_domain": "dev.to",
            "relevance": round(relevance, 2),
            "why_relevant": f"Dev.to: {title[:70]}",
            "engagement": {"reactions": reactions, "comments": comments},
            "metadata": {"author": author, "tags": tags},
        })

    _log(f"Found {len(items)} Dev.to articles")
    return {"items": items}


def parse_devto_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return items list from a Dev.to search response."""
    return response.get("items", [])

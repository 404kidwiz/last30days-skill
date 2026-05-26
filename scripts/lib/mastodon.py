"""Mastodon federated social search — free public API, no key required.

Searches a Mastodon instance's public statuses API for recent posts about a topic.
Defaults to mastodon.social; set MASTODON_INSTANCE config key for a different server
(e.g., fosstodon.org, hachyderm.io, infosec.exchange).

Always available — pure HTTP, no auth needed for public search.
Rate limit: ~300 requests / 5 min unauthenticated on mastodon.social.
"""

import html
import math
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from . import dates, http, log
from .relevance import token_overlap_relevance as _compute_relevance

DEFAULT_INSTANCE = "mastodon.social"

DEPTH_CONFIG = {
    "quick":   {"results": 10},
    "default": {"results": 20},
    "deep":    {"results": 40},
}


def _log(msg: str) -> None:
    log.source_log("Mastodon", msg)


def _strip_html(text: str) -> str:
    """Strip HTML tags, convert <br> to newlines, decode HTML entities."""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return " ".join(text.split())


def _parse_date(created_at: str) -> Optional[str]:
    """Parse Mastodon ISO 8601 timestamp to YYYY-MM-DD."""
    if not created_at:
        return None
    d = dates.parse_date(created_at)
    return d.strftime("%Y-%m-%d") if d else None


def search_mastodon(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    instance: str = DEFAULT_INSTANCE,
) -> Dict[str, Any]:
    """Search Mastodon public statuses for a topic.

    Args:
        topic: Search query
        from_date: Start date (YYYY-MM-DD) — used for post-fetch date filter
        to_date: End date (YYYY-MM-DD)
        depth: 'quick', 'default', or 'deep'
        instance: Mastodon instance hostname (default: mastodon.social)

    Returns:
        Dict with 'items' list and optional 'error'.
    """
    config = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])

    # Mastodon v2 search API caps results at 40 per request
    limit = min(config["results"], 40)
    params = urlencode({
        "q": topic,
        "type": "statuses",
        "limit": limit,
        "resolve": "false",
    })
    url = f"https://{instance}/api/v2/search?{params}"
    _log(f"Searching {instance} for '{topic}' (depth={depth})")

    try:
        data = http.get(url, timeout=12, retries=2)
    except Exception as exc:
        _log(f"Mastodon API error: {exc}")
        return {"items": [], "error": f"{type(exc).__name__}: {exc}"}

    statuses = data.get("statuses") or []
    items: List[Dict[str, Any]] = []

    for i, status in enumerate(statuses):
        raw_content = status.get("content") or ""
        text = _strip_html(raw_content)
        if not text:
            continue

        account = status.get("account") or {}
        handle = account.get("acct") or account.get("username") or ""
        display_name = (account.get("display_name") or handle).strip()

        status_url = (
            status.get("url")
            or f"https://{instance}/@{handle}/{status.get('id', '')}"
        )
        date_str = _parse_date(status.get("created_at") or "")

        favourites = int(status.get("favourites_count") or 0)
        reblogs = int(status.get("reblogs_count") or 0)
        replies = int(status.get("replies_count") or 0)

        rank_score = max(0.2, 1.0 - (i * 0.025))
        engagement_boost = min(0.15, math.log1p(favourites + reblogs) / 40)
        text_relevance = _compute_relevance(topic, text)
        relevance = min(1.0, text_relevance * 0.5 + rank_score * 0.3 + engagement_boost + 0.1)

        items.append({
            "id": str(status.get("id") or f"MA{i + 1}"),
            "handle": handle,
            "display_name": display_name,
            "text": text,
            "url": status_url,
            "date": date_str,
            "engagement": {
                "likes": favourites,
                "reposts": reblogs,
                "replies": replies,
            },
            "relevance": round(relevance, 2),
            "why_relevant": (
                f"Mastodon: @{handle}: {text[:60]}" if text else f"Mastodon: @{handle}"
            ),
        })

    # Sort by engagement descending
    items.sort(key=lambda x: x["engagement"]["likes"] + x["engagement"]["reposts"], reverse=True)

    # Date filter: prefer in-range posts but keep all if none qualify
    in_range = [it for it in items if it["date"] and from_date <= it["date"] <= to_date]
    if in_range:
        items = in_range

    _log(f"Found {len(items)} Mastodon posts")
    return {"items": items}


def parse_mastodon_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return items list from a Mastodon search response."""
    return response.get("items", [])

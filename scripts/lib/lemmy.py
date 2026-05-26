"""Lemmy federated community search — free public API, no key required.

Searches Lemmy (federated Reddit alternative) for recent posts about a topic.
Uses the Lemmy API v3 at a configurable instance (default: lemmy.world).

Set LEMMY_INSTANCE to use a different server (e.g., lemmy.ml, programming.dev,
beehaw.org, lemmy.ca).

Always available — pure HTTP, no auth needed for public search.
"""

import math
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from . import dates, http, log
from .relevance import token_overlap_relevance as _compute_relevance

DEFAULT_INSTANCE = "lemmy.world"

DEPTH_CONFIG = {
    "quick":   {"results": 10},
    "default": {"results": 20},
    "deep":    {"results": 40},
}


def _log(msg: str) -> None:
    log.source_log("Lemmy", msg)


def _parse_date(raw: str) -> Optional[str]:
    if not raw:
        return None
    d = dates.parse_date(raw)
    return d.strftime("%Y-%m-%d") if d else None


def search_lemmy(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    instance: str = DEFAULT_INSTANCE,
) -> Dict[str, Any]:
    """Search Lemmy federated communities for posts about a topic.

    Args:
        topic: Search query
        from_date: Start date (YYYY-MM-DD) — used for post-fetch date filter
        to_date: End date (YYYY-MM-DD)
        depth: 'quick', 'default', or 'deep'
        instance: Lemmy instance hostname (default: lemmy.world)

    Returns:
        Dict with 'items' list and optional 'error'.
    """
    config = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])

    params = urlencode({
        "q": topic,
        "type_": "Posts",
        "listing_type": "All",
        "sort": "Active",
        "limit": min(config["results"], 50),  # Lemmy max is 50
    })
    url = f"https://{instance}/api/v3/search?{params}"
    _log(f"Searching {instance} for '{topic}' (depth={depth})")

    try:
        data = http.get(url, timeout=12, retries=2)
    except Exception as exc:
        _log(f"Lemmy API error: {exc}")
        return {"items": [], "error": f"{type(exc).__name__}: {exc}"}

    post_views = data.get("posts") or []
    items: List[Dict[str, Any]] = []

    for i, pv in enumerate(post_views):
        post = pv.get("post") or {}
        counts = pv.get("counts") or {}
        community = pv.get("community") or {}
        creator = pv.get("creator") or {}

        title = str(post.get("name") or "").strip()
        body = str(post.get("body") or "").strip()
        external_url = str(post.get("url") or "").strip()
        post_url = str(post.get("ap_id") or "").strip()
        # Prefer external URL for context; fall back to post URL
        display_url = external_url or post_url

        published = post.get("published") or ""
        date_str = _parse_date(published)

        score = int(counts.get("score") or 0)
        comment_count = int(counts.get("comments") or 0)
        community_name = str(community.get("name") or community.get("display_name") or "").strip()
        author = str(creator.get("name") or creator.get("actor_id") or "").strip()

        if not title:
            continue

        rank_score = max(0.2, 1.0 - (i * 0.025))
        engagement_boost = min(0.15, math.log1p(max(0, score) + comment_count) / 40)
        text_relevance = _compute_relevance(topic, f"{title} {body[:200]}")
        relevance = min(1.0, text_relevance * 0.5 + rank_score * 0.3 + engagement_boost + 0.1)

        items.append({
            "id": str(post.get("id") or f"LM{i + 1}"),
            "title": title,
            "selftext": body,
            "url": display_url,
            "date": date_str,
            "subreddit": community_name,  # reuse Reddit field name for normalize_reddit compat
            "engagement": {"score": score, "comments": comment_count},
            "relevance": round(relevance, 2),
            "why_relevant": (
                f"Lemmy/{community_name}: {title[:60]}" if community_name else f"Lemmy: {title[:70]}"
            ),
            "metadata": {"author": author, "instance": instance},
        })

    # Date filter: prefer in-range posts but keep all if none qualify
    in_range = [it for it in items if it["date"] and from_date <= it["date"] <= to_date]
    if in_range:
        items = in_range

    _log(f"Found {len(items)} Lemmy posts")
    return {"items": items}


def parse_lemmy_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return items list from a Lemmy search response."""
    return response.get("items", [])

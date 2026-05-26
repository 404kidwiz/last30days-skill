"""PeerTube federated video search — free public API, no key required.

Searches a PeerTube instance for recent videos about a topic. PeerTube is a
federated open-source video platform (alternative to YouTube).

Set PEERTUBE_INSTANCE to use a specific server (e.g., peertube.social,
video.blender.org, tube.selea.de). Defaults to peertube.social.

Always available — pure HTTP, no auth needed for public search.
"""

import math
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from . import dates, http, log
from .relevance import token_overlap_relevance as _compute_relevance

DEFAULT_INSTANCE = "peertube.social"

DEPTH_CONFIG = {
    "quick":   {"results": 8},
    "default": {"results": 15},
    "deep":    {"results": 25},
}


def _log(msg: str) -> None:
    log.source_log("PeerTube", msg)


def _parse_date(raw: str) -> Optional[str]:
    if not raw:
        return None
    d = dates.parse_date(raw)
    return d.strftime("%Y-%m-%d") if d else None


def search_peertube(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    instance: str = DEFAULT_INSTANCE,
) -> Dict[str, Any]:
    """Search PeerTube for videos about a topic.

    Args:
        topic: Search query
        from_date: Start date (YYYY-MM-DD) — used for post-fetch date filter
        to_date: End date (YYYY-MM-DD)
        depth: 'quick', 'default', or 'deep'
        instance: PeerTube instance hostname (default: peertube.social)

    Returns:
        Dict with 'items' list and optional 'error'.
    """
    config = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])

    params = urlencode({
        "search": topic,
        "count": config["results"],
        "sort": "-publishedAt",
        "isLocal": "false",  # search federated content too
    })
    url = f"https://{instance}/api/v1/search/videos?{params}"
    _log(f"Searching {instance} for '{topic}' (depth={depth})")

    try:
        data = http.get(url, timeout=12, retries=2)
    except Exception as exc:
        _log(f"PeerTube API error: {exc}")
        return {"items": [], "error": f"{type(exc).__name__}: {exc}"}

    raw_videos = data.get("data") or []
    items: List[Dict[str, Any]] = []

    for i, video in enumerate(raw_videos):
        name = str(video.get("name") or "").strip()
        description = str(video.get("description") or "").strip()
        published_raw = video.get("publishedAt") or video.get("originallyPublishedAt") or ""
        date_str = _parse_date(published_raw)

        # Build watch URL
        uuid = video.get("uuid") or video.get("id") or ""
        video_url = video.get("url") or (f"https://{instance}/w/{uuid}" if uuid else "")

        account = video.get("account") or {}
        channel = video.get("channel") or {}
        creator = (account.get("displayName") or account.get("name") or "").strip()
        channel_name = (channel.get("displayName") or channel.get("name") or "").strip()

        views = int(video.get("views") or 0)
        likes = int(video.get("likes") or 0)
        duration = int(video.get("duration") or 0)

        if not name:
            continue

        rank_score = max(0.2, 1.0 - (i * 0.03))
        engagement_boost = min(0.1, math.log1p(likes + views // 100) / 40)
        text_relevance = _compute_relevance(topic, f"{name} {description[:200]}")
        relevance = min(1.0, text_relevance * 0.5 + rank_score * 0.35 + engagement_boost + 0.05)

        items.append({
            "id": str(uuid or f"PT{i + 1}"),
            "title": name,
            "snippet": description[:300] if description else "",
            "url": video_url,
            "date": date_str,
            "source_domain": instance,
            "relevance": round(relevance, 2),
            "why_relevant": f"PeerTube: {name[:70]}",
            "engagement": {"views": views, "likes": likes},
            "metadata": {
                "creator": creator,
                "channel": channel_name,
                "duration_seconds": duration,
            },
        })

    # Date filter: prefer in-range videos but keep all if none qualify
    in_range = [it for it in items if it["date"] and from_date <= it["date"] <= to_date]
    if in_range:
        items = in_range

    _log(f"Found {len(items)} PeerTube videos")
    return {"items": items}


def parse_peertube_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return items list from a PeerTube search response."""
    return response.get("items", [])

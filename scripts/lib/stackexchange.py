"""Stack Exchange / Stack Overflow API — free, no key required (basic tier).

Searches Stack Overflow (default) or any Stack Exchange site for recent
questions about a topic. Returns question title, URL, score, answer count,
and view count.

Always available — no package install needed. Without API key: 300 req/day.
Set STACKEXCHANGE_API_KEY for 10,000 req/day.
"""

import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from . import http, log
from .relevance import token_overlap_relevance as _compute_relevance

SE_API = "https://api.stackexchange.com/2.3"

DEPTH_CONFIG = {
    "quick":   {"results": 10, "site": "stackoverflow"},
    "default": {"results": 20, "site": "stackoverflow"},
    "deep":    {"results": 30, "site": "stackoverflow"},
}


def _log(msg: str) -> None:
    log.source_log("StackExchange", msg)


def _unix_from_date(date_str: str) -> int:
    """Convert YYYY-MM-DD to Unix timestamp (start of day UTC)."""
    try:
        import calendar
        from datetime import datetime
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return int(calendar.timegm(dt.timetuple()))
    except Exception:
        return 0


def _date_from_unix(ts: int) -> Optional[str]:
    """Convert Unix timestamp to YYYY-MM-DD."""
    if not ts:
        return None
    try:
        from datetime import datetime, timezone
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return None


def search_stackexchange(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    site: str = "stackoverflow",
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Search Stack Exchange for questions about a topic.

    Args:
        topic: Search query
        from_date: Start date (YYYY-MM-DD)
        to_date: End date (YYYY-MM-DD)
        depth: 'quick', 'default', or 'deep'
        site: Stack Exchange site slug (default: stackoverflow)
        api_key: Optional API key for higher rate limits (STACKEXCHANGE_API_KEY)

    Returns:
        Dict with 'items' list and optional 'error'.
    """
    config = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])
    active_site = site or config["site"]

    params: Dict[str, Any] = {
        "q": topic,
        "site": active_site,
        "order": "desc",
        "sort": "activity",
        "pagesize": config["results"],
        "fromdate": _unix_from_date(from_date),
        "filter": "default",
    }
    if api_key:
        params["key"] = api_key

    url = f"{SE_API}/search/advanced?{urlencode(params)}"
    _log(f"Searching {active_site} for '{topic}' (depth={depth})")

    try:
        data = http.get(url, timeout=12, retries=2)
    except Exception as exc:
        _log(f"Stack Exchange API error: {exc}")
        return {"items": [], "error": f"{type(exc).__name__}: {exc}"}

    raw_items = data.get("items") or []
    items: List[Dict[str, Any]] = []

    for i, q in enumerate(raw_items):
        title = str(q.get("title") or "").strip()
        link = str(q.get("link") or "").strip()
        score = int(q.get("score") or 0)
        answers = int(q.get("answer_count") or 0)
        views = int(q.get("view_count") or 0)
        is_answered = bool(q.get("is_answered"))
        creation_ts = q.get("creation_date") or q.get("last_activity_date") or 0
        date_str = _date_from_unix(int(creation_ts))
        tags = q.get("tags") or []

        if not title:
            continue

        rank_score = max(0.2, 1.0 - (i * 0.025))
        text_relevance = _compute_relevance(topic, f"{title} {' '.join(tags)}")
        # Boost for answered and high-score questions
        quality_boost = min(0.1, (score / 200 + (0.05 if is_answered else 0)))
        relevance = min(1.0, text_relevance * 0.5 + rank_score * 0.35 + quality_boost + 0.05)

        items.append({
            "id": str(q.get("question_id") or f"SE{i + 1}"),
            "title": title,
            "snippet": "",
            "url": link,
            "date": date_str,
            "source_domain": f"{active_site}.com",
            "relevance": round(relevance, 2),
            "why_relevant": f"Stack Exchange: {title[:70]}",
            "engagement": {"score": score, "answers": answers, "views": views},
            "metadata": {"tags": tags, "is_answered": is_answered},
        })

    # Log quota remaining if returned (helps detect rate-limit proximity)
    quota = data.get("quota_remaining")
    if quota is not None:
        _log(f"Found {len(items)} questions (quota remaining: {quota})")
    else:
        _log(f"Found {len(items)} questions")

    return {"items": items}


def parse_stackexchange_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return items list from a Stack Exchange search response."""
    return response.get("items", [])

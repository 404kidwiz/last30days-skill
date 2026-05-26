"""X/Twitter scraping via BrowserOS MCP — uses the user's real logged-in browser session.

No API key or cookies required beyond BrowserOS running with an active X session.
Opens X search in a hidden tab, waits for JS to render tweets, extracts via DOM,
then closes the tab. Returns items in the standard microblog shape.

Auto-enabled when BrowserOS is running AND the browser has an X session.
Disable by setting BROWSEROS_X=false in your config.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from . import dates, log
from .browseros_scraper import _tool_call, _log as _bos_log, DEFAULT_MCP_URL

# JS to extract tweet data from X search results page
_EXTRACT_JS = """
JSON.stringify(
  Array.from(document.querySelectorAll('[data-testid="tweet"]'))
    .slice(0, {limit})
    .map(t => {{
      const nameEl = t.querySelector('[data-testid="User-Name"]');
      const nameText = nameEl ? nameEl.innerText : '';
      const lines = nameText.split('\\n').filter(Boolean);
      return {{
        text: (t.querySelector('[data-testid="tweetText"]') || {{}}).innerText || '',
        url:  (t.querySelector('a[href*="/status/"]') || {{}}).href || '',
        displayName: lines[0] || '',
        handle: (lines[1] || '').replace('@', ''),
        time: ((t.querySelector('time') || {{}}).dateTime) || '',
        likes: (t.querySelector('[data-testid="like"]') || {{}}).innerText || '0',
        reposts: (t.querySelector('[data-testid="retweet"]') || {{}}).innerText || '0',
        replies: (t.querySelector('[data-testid="reply"]') || {{}}).innerText || '0',
      }};
    }})
    .filter(t => t.text && t.text.length > 5)
)
"""

DEPTH_CONFIG = {
    "quick":   {"results": 8,  "settle_s": 2.5},
    "default": {"results": 15, "settle_s": 3.0},
    "deep":    {"results": 25, "settle_s": 4.0},
}


def _log(msg: str) -> None:
    log.source_log("BrowserOS-X", msg)


def _parse_engagement(raw: str) -> int:
    """Parse engagement string like '1.2K', '42', '' into int."""
    raw = (raw or "").strip().upper()
    if not raw:
        return 0
    try:
        if raw.endswith("K"):
            return int(float(raw[:-1]) * 1000)
        if raw.endswith("M"):
            return int(float(raw[:-1]) * 1_000_000)
        return int(raw)
    except ValueError:
        return 0


def _parse_date(iso: str) -> Optional[str]:
    if not iso:
        return None
    d = dates.parse_date(iso[:10])
    return d.strftime("%Y-%m-%d") if d else None


def search_x_via_browser(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    mcp_url: str = DEFAULT_MCP_URL,
    tab: str = "live",
) -> Dict[str, Any]:
    """Search X/Twitter via BrowserOS hidden tab using the user's active session.

    Args:
        topic: Search query
        from_date: Start date (YYYY-MM-DD) for post-fetch date filter
        to_date: End date (YYYY-MM-DD)
        depth: 'quick', 'default', or 'deep'
        mcp_url: BrowserOS MCP endpoint
        tab: X search tab — 'live' (real-time) or 'top' (ranked)

    Returns:
        Dict with 'items' list and optional 'error'.
    """
    config = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])
    limit = config["results"]
    settle_s = config["settle_s"]

    search_url = (
        f"https://x.com/search?q={quote_plus(topic)}"
        f"&f={'live' if tab == 'live' else 'top'}&src=typed_query"
    )
    _log(f"Opening hidden tab: {search_url[:80]}")

    # 1. Open hidden tab
    result = _tool_call("new_hidden_page", {"url": search_url}, mcp_url=mcp_url, timeout=15)
    if not result:
        return {"items": [], "error": "Failed to open X search tab"}

    page_id = result["structured"].get("pageId")
    if page_id is None:
        for text in result["texts"]:
            if "Page ID:" in text:
                try:
                    page_id = int(text.split("Page ID:")[-1].strip())
                    break
                except ValueError:
                    pass
    if page_id is None:
        return {"items": [], "error": "No pageId from BrowserOS"}

    _log(f"  page_id={page_id}, waiting {settle_s}s for X JS to render")
    time.sleep(settle_s)

    # 2. Extract tweets via JS
    expr = _EXTRACT_JS.format(limit=limit)
    js_result = _tool_call("evaluate_script", {"page": page_id, "expression": expr}, mcp_url=mcp_url, timeout=20)

    # 3. Always close tab
    _tool_call("close_page", {"page": page_id}, mcp_url=mcp_url, timeout=10)

    if not js_result:
        return {"items": [], "error": "evaluate_script returned nothing"}

    # 4. Parse JSON from result text
    raw_json = ""
    for text in js_result["texts"]:
        text = text.strip()
        if text.startswith("["):
            raw_json = text
            break

    if not raw_json:
        _log("No tweet JSON in evaluate_script output")
        return {"items": [], "error": "No tweet data extracted"}

    try:
        raw_tweets = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return {"items": [], "error": f"JSON parse error: {exc}"}

    _log(f"Extracted {len(raw_tweets)} raw tweets")

    # 5. Normalize to microblog shape
    items: List[Dict[str, Any]] = []
    for i, tweet in enumerate(raw_tweets):
        text = (tweet.get("text") or "").strip()
        if not text:
            continue

        url = (tweet.get("url") or "").strip()
        handle = (tweet.get("handle") or "").strip().lstrip("@")
        display_name = (tweet.get("displayName") or handle or "").strip()
        date_str = _parse_date(tweet.get("time") or "")
        likes = _parse_engagement(tweet.get("likes"))
        reposts = _parse_engagement(tweet.get("reposts"))
        replies = _parse_engagement(tweet.get("replies"))

        items.append({
            "id": f"X{i + 1}",
            "handle": handle,
            "display_name": display_name,
            "text": text,
            "url": url,
            "date": date_str,
            "source_domain": "x.com",
            "relevance": round(max(0.2, 1.0 - i * 0.05), 2),
            "why_relevant": f"X (BrowserOS): {text[:60]}",
            "engagement": {
                "likes": likes,
                "reposts": reposts,
                "replies": replies,
            },
            "metadata": {
                "platform": "x",
                "via": "browseros",
            },
        })

    # Date filter: prefer in-range but keep all if none qualify
    in_range = [it for it in items if it["date"] and from_date <= it["date"] <= to_date]
    if in_range:
        items = in_range

    _log(f"Returning {len(items)} X posts")
    return {"items": items}


def parse_browseros_x_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return items from a BrowserOS-X response."""
    return response.get("items", [])


def has_x_session(mcp_url: str = DEFAULT_MCP_URL) -> bool:
    """Return True if BrowserOS has an active X/Twitter session.

    Checks list_pages for an x.com tab — if the user is logged in,
    BrowserOS will have x.com in its page list.
    """
    result = _tool_call("list_pages", {}, mcp_url=mcp_url, timeout=5)
    if not result:
        return False
    pages = result.get("structured", {}).get("pages", [])
    return any("x.com" in (p.get("url") or "") for p in pages)

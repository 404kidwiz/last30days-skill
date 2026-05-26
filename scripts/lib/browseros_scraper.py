"""BrowserOS MCP scraping backend — uses a real browser, bypasses anti-bot.

Calls the BrowserOS MCP server (http://127.0.0.1:9000/mcp) to:
  1. Open a hidden browser tab at the target URL
  2. Wait for the page to settle
  3. Extract clean markdown content via get_page_content
  4. Close the hidden tab

Auto-enabled when BrowserOS is running (port 9000 responds).
Set BROWSEROS_MCP_URL to override the default endpoint.

Items returned in the standard grounding shape so the existing
normalizer pipeline handles them without changes.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional
from urllib.request import urlopen, Request

try:
    import requests as _requests
    _USE_REQUESTS = True
except ImportError:
    _USE_REQUESTS = False

from . import log
from .relevance import token_overlap_relevance as _compute_relevance

DEFAULT_MCP_URL = "http://127.0.0.1:9000/mcp"

# Cache availability check result for 60s to avoid a live HTTP ping
# on every source dispatch call within a single run.
_availability_cache: dict[str, tuple[bool, float]] = {}
_CACHE_TTL = 60.0

DEPTH_CONFIG = {
    "quick":   {"results": 5,  "settle_ms": 800},
    "default": {"results": 10, "settle_ms": 1200},
    "deep":    {"results": 20, "settle_ms": 2000},
}


def _log(msg: str) -> None:
    log.source_log("BrowserOS", msg)


def _mcp_call(
    method: str,
    params: Dict[str, Any],
    mcp_url: str,
    timeout: int = 20,
) -> Optional[Dict[str, Any]]:
    """Make a single JSON-RPC call to the BrowserOS MCP server."""
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": int(time.time() * 1000) % 1_000_000,
        "method": method,
        "params": params,
    }).encode()

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    try:
        if _USE_REQUESTS:
            r = _requests.post(mcp_url, data=payload, headers=headers, timeout=timeout)
            r.raise_for_status()
            return r.json()
        else:
            req = Request(mcp_url, data=payload, headers=headers, method="POST")
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
    except Exception as exc:
        _log(f"MCP call failed ({method}): {exc}")
        return None


def _tool_call(
    tool_name: str,
    arguments: Dict[str, Any],
    mcp_url: str,
    timeout: int = 20,
) -> Optional[Any]:
    """Call a BrowserOS tool and return the result content text, or None."""
    resp = _mcp_call(
        "tools/call",
        {"name": tool_name, "arguments": arguments},
        mcp_url=mcp_url,
        timeout=timeout,
    )
    if not resp:
        return None
    result = resp.get("result") or {}
    if resp.get("error") or result.get("isError"):
        err = resp.get("error") or (result.get("content") or [{}])[0].get("text", "unknown")
        _log(f"{tool_name} error: {str(err)[:120]}")
        return None
    content = result.get("content") or []
    texts = [c.get("text", "") for c in content if c.get("type") == "text"]
    structured = result.get("structuredContent") or {}
    return {"texts": texts, "structured": structured}


def _check_available(mcp_url: str) -> bool:
    """Live HTTP check — call is_available() which caches result."""
    try:
        if _USE_REQUESTS:
            r = _requests.get(mcp_url, timeout=3)
            return r.status_code < 500
        else:
            req = Request(mcp_url)
            with urlopen(req, timeout=3) as resp:
                return resp.status < 500
    except Exception:
        return False


def is_available(mcp_url: str = DEFAULT_MCP_URL) -> bool:
    """Return True if BrowserOS MCP server is reachable.

    Result is cached for _CACHE_TTL seconds (60s) so repeated calls within
    a single pipeline run don't each hit the network.
    """
    now = time.time()
    cached = _availability_cache.get(mcp_url)
    if cached is not None and now - cached[1] < _CACHE_TTL:
        return cached[0]
    result = _check_available(mcp_url)
    _availability_cache[mcp_url] = (result, now)
    return result


def fetch_url(
    url: str,
    mcp_url: str = DEFAULT_MCP_URL,
    settle_ms: int = 1200,
    selector: Optional[str] = None,
) -> Optional[str]:
    """Open URL in a hidden browser tab, extract markdown content, close tab.

    Returns extracted markdown string, or None on any failure.
    """
    _log(f"Opening hidden tab: {url}")

    # 1. Open hidden page
    result = _tool_call("new_hidden_page", {"url": url}, mcp_url=mcp_url, timeout=15)
    if not result:
        _log("Failed to open hidden page")
        return None

    page_id = result["structured"].get("pageId")
    if page_id is None:
        # Try parsing from text
        for text in result["texts"]:
            if "Page ID:" in text:
                try:
                    page_id = int(text.split("Page ID:")[-1].strip())
                    break
                except ValueError:
                    pass
    if page_id is None:
        _log("Could not determine pageId — cannot extract content")
        return None

    _log(f"  page_id={page_id}, waiting {settle_ms}ms for page to settle")

    # 2. Wait for page to settle
    if settle_ms > 0:
        time.sleep(settle_ms / 1000.0)

    # 3. Extract content
    args: Dict[str, Any] = {"page": page_id}
    if selector:
        args["selector"] = selector
    content_result = _tool_call("get_page_content", args, mcp_url=mcp_url, timeout=20)

    # 4. Always close the tab, even if content extraction failed
    _tool_call("close_page", {"page": page_id}, mcp_url=mcp_url, timeout=10)

    if not content_result:
        _log("Content extraction failed")
        return None

    markdown = "\n".join(t for t in content_result["texts"] if t.strip())
    _log(f"  extracted {len(markdown)} chars of markdown")
    return markdown or None


def search_via_browser(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    mcp_url: str = DEFAULT_MCP_URL,
) -> Dict[str, Any]:
    """Search DuckDuckGo via BrowserOS (real browser, no anti-bot risk).

    Uses BrowserOS to open DuckDuckGo search results in a hidden tab,
    extract links, and return them in the standard grounding item shape.

    Args:
        topic: Search query
        from_date: Start date (YYYY-MM-DD) — for item labeling
        to_date: End date (YYYY-MM-DD)
        depth: 'quick', 'default', or 'deep'
        mcp_url: BrowserOS MCP endpoint

    Returns:
        Dict with 'items' list and optional 'error'.
    """
    from urllib.parse import quote_plus

    config = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])
    settle_ms = config["settle_ms"]
    max_results = config["results"]

    # Use DuckDuckGo HTML (no JS required for basic results)
    ddg_url = f"https://html.duckduckgo.com/html/?q={quote_plus(topic)}"
    _log(f"BrowserOS DDG search: '{topic}' (depth={depth})")

    # Open DuckDuckGo search page
    result = _tool_call("new_hidden_page", {"url": ddg_url}, mcp_url=mcp_url, timeout=15)
    if not result:
        return {"items": [], "error": "Failed to open DDG search page"}

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
        return {"items": [], "error": "No pageId from new_hidden_page"}

    time.sleep(settle_ms / 1000.0)

    # Get links from the results page
    links_result = _tool_call(
        "get_page_links",
        {"page": page_id},
        mcp_url=mcp_url,
        timeout=20,
    )

    # Also grab text content for snippets
    content_result = _tool_call(
        "get_page_content",
        {"page": page_id},
        mcp_url=mcp_url,
        timeout=20,
    )

    _tool_call("close_page", {"page": page_id}, mcp_url=mcp_url, timeout=10)

    items: List[Dict[str, Any]] = []

    if links_result:
        # Parse links from structured content or text
        structured_links = links_result.get("structured", {}).get("links") or []
        rank = 0
        for link in structured_links:
            href = link.get("href") or link.get("url") or ""
            text = (link.get("text") or link.get("title") or "").strip()
            if not href or not text or len(text) < 5:
                continue
            # Unwrap DDG redirect: /l/?uddg=<encoded-real-url>
            real_url = _unwrap_ddg_redirect(href)
            if not real_url:
                continue
            if rank >= max_results:
                break
            relevance = _compute_relevance(topic, text)
            items.append({
                "id": f"BOS{rank + 1}",
                "title": text[:200],
                "snippet": "",
                "url": real_url,
                "date": None,
                "source_domain": _domain(real_url),
                "relevance": round(max(0.15, relevance * 0.7 + max(0.0, 1.0 - rank * 0.04) * 0.3), 2),
                "why_relevant": f"BrowserOS DDG: {text[:60]}",
            })
            rank += 1

    if not items and content_result:
        # Fallback: extract from markdown text (rough parse)
        markdown = "\n".join(t for t in content_result["texts"] if t)
        items = _parse_ddg_markdown(topic, markdown, max_results)

    _log(f"Found {len(items)} results via BrowserOS DDG")
    return {"items": items}


def _unwrap_ddg_redirect(href: str) -> Optional[str]:
    """Extract real URL from DuckDuckGo redirect (/l/?uddg=<encoded>).

    Returns the real URL, or None if this is a DDG-internal link.
    """
    from urllib.parse import urlparse, parse_qs, unquote
    try:
        parsed = urlparse(href)
        # Direct external link (not a DDG redirect)
        if parsed.netloc and "duckduckgo.com" not in parsed.netloc:
            return href
        # DDG redirect: ?uddg=<encoded-url>
        if parsed.netloc and "duckduckgo.com" in parsed.netloc:
            qs = parse_qs(parsed.query)
            uddg = qs.get("uddg", [None])[0]
            if uddg:
                real = unquote(uddg)
                # Must be a proper http(s) URL
                if real.startswith("http"):
                    return real
        return None
    except Exception:
        return None


def _domain(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc or url
    except Exception:
        return url


def _parse_ddg_markdown(topic: str, markdown: str, max_results: int) -> List[Dict[str, Any]]:
    """Rough extraction of result titles and URLs from DDG markdown."""
    import re
    items = []
    # Match markdown links: [title](url)
    for i, m in enumerate(re.finditer(r'\[([^\]]+)\]\((https?://[^\)]+)\)', markdown)):
        title, url = m.group(1).strip(), m.group(2).strip()
        if "duckduckgo.com" in url or len(title) < 5:
            continue
        relevance = _compute_relevance(topic, title)
        items.append({
            "id": f"BOS{i + 1}",
            "title": title[:200],
            "snippet": "",
            "url": url,
            "date": None,
            "source_domain": _domain(url),
            "relevance": round(max(0.15, relevance * 0.6 + max(0.0, 1.0 - i * 0.05) * 0.4), 2),
            "why_relevant": f"BrowserOS DDG: {title[:60]}",
        })
        if len(items) >= max_results:
            break
    return items


def parse_browseros_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return items list from a BrowserOS search response."""
    return response.get("items", [])

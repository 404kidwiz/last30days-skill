"""Exa neural-search + URL-crawl backend for last30days.

Distinct from grounding.py's Exa integration:
  - grounding.py uses type="auto" (keyword-first, strict date filter, 5 results)
  - exa_mcp.py uses type="neural" (semantic/conceptual, looser date filter, 10-20 results)
    plus /contents endpoint for clean URL text extraction.

Opt-in: enabled via INCLUDE_SOURCES=exa_mcp (shares EXA_API_KEY with grounding).
Disable alongside grounding to avoid double-spend; enable when you want semantic
retrieval in addition to or instead of keyword search.

Auto-on when EXA_API_KEY is set AND "exa_mcp" appears in INCLUDE_SOURCES.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import log
from . import http as _http
from .relevance import token_overlap_relevance as _compute_relevance

EXA_SEARCH_URL = "https://api.exa.ai/search"
EXA_CONTENTS_URL = "https://api.exa.ai/contents"

DEPTH_CONFIG = {
    "quick":   {"results": 5,  "max_chars": 500},
    "default": {"results": 10, "max_chars": 1500},
    "deep":    {"results": 20, "max_chars": 3000},
}


def _log(msg: str) -> None:
    log.source_log("Exa-Neural", msg)


def search_exa_neural(
    topic: str,
    from_date: str,
    to_date: str,
    api_key: str,
    depth: str = "default",
    livecrawl: str = "fallback",
) -> Dict[str, Any]:
    """Semantic (neural) web search via Exa API.

    Uses type="neural" so retrieval is concept-aware — finds relevant content
    even when exact keywords are absent. Better than keyword search for
    trend/aesthetic/conceptual queries like "design trends 2026".

    Args:
        topic: Search query (natural language or keywords)
        from_date: Start date YYYY-MM-DD
        to_date: End date YYYY-MM-DD
        api_key: EXA_API_KEY
        depth: 'quick' / 'default' / 'deep'
        livecrawl: 'always' | 'fallback' | 'never'. 'fallback' uses live crawl
                   when cached content is stale or missing. Good for recent topics.

    Returns:
        Dict with 'items' list in grounding shape.
    """
    config = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])
    num_results = config["results"]
    max_chars = config["max_chars"]

    _log(f"Neural search: '{topic[:60]}' (depth={depth}, n={num_results})")

    payload: Dict[str, Any] = {
        "query": topic,
        "type": "neural",
        "numResults": num_results,
        "startPublishedDate": f"{from_date}T00:00:00.000Z",
        "endPublishedDate": f"{to_date}T23:59:59.000Z",
        "contents": {
            "text": {
                "maxCharacters": max_chars,
                "includeHtmlTags": False,
            },
            "livecrawl": livecrawl,
        },
    }

    try:
        data = _http.request(
            "POST",
            EXA_SEARCH_URL,
            headers={"x-api-key": api_key},
            json_data=payload,
            timeout=20,
        )
    except Exception as exc:
        _log(f"Search failed: {exc}")
        return {"items": [], "error": str(exc)}

    raw_results = data.get("results") or []
    _log(f"Got {len(raw_results)} results")

    items: List[Dict[str, Any]] = []
    for i, r in enumerate(raw_results):
        url = (r.get("url") or "").strip()
        title = (r.get("title") or "").strip()
        if not url or not title:
            continue
        pub_date = _parse_exa_date(r.get("publishedDate") or "")
        text = (r.get("text") or "").strip()
        snippet = text[:300] if text else ""
        # Exa neural search returns a float score (higher = more relevant).
        # Normalize into [0,1] and blend with positional decay.
        exa_score = float(r.get("score") or 0.5)
        exa_norm = min(1.0, max(0.0, (exa_score - 0.1) / 0.9))
        positional = max(0.0, 1.0 - i * 0.04)
        relevance = round(exa_norm * 0.6 + positional * 0.3 + _compute_relevance(topic, f"{title} {snippet}") * 0.1, 3)
        items.append({
            "id": f"EXAN{i + 1}",
            "title": title[:200],
            "snippet": snippet,
            "url": url,
            "date": pub_date,
            "source_domain": _domain(url),
            "relevance": round(max(0.15, relevance), 2),
            "why_relevant": f"Exa neural: {title[:60]}",
            "full_text": text,
        })

    return {"items": items}


def fetch_url_exa(
    url: str,
    api_key: str,
    max_chars: int = 5000,
    livecrawl: str = "always",
) -> Optional[str]:
    """Extract clean text from a URL via Exa /contents endpoint.

    Returns markdown-like text, or None on failure.
    Can be used as a BrowserOS fallback for URL content extraction when
    BrowserOS MCP is not running.

    Args:
        url: Target URL to crawl
        api_key: EXA_API_KEY
        max_chars: Maximum characters to extract
        livecrawl: 'always' forces fresh crawl (bypasses Exa cache)
    """
    _log(f"Crawling URL: {url[:80]}")
    try:
        data = _http.request(
            "POST",
            EXA_CONTENTS_URL,
            headers={"x-api-key": api_key},
            json_data={
                "ids": [url],
                "text": {
                    "maxCharacters": max_chars,
                    "includeHtmlTags": False,
                },
                "livecrawl": livecrawl,
            },
            timeout=20,
        )
    except Exception as exc:
        _log(f"Crawl failed: {exc}")
        return None

    results = data.get("results") or []
    if not results:
        _log("No content returned")
        return None
    text = (results[0].get("text") or "").strip()
    _log(f"  extracted {len(text)} chars")
    return text or None


def parse_exa_mcp_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return items list from an Exa neural search response."""
    return response.get("items", [])


def _parse_exa_date(raw: str) -> Optional[str]:
    if not raw:
        return None
    try:
        return raw[:10]  # "YYYY-MM-DD" from ISO string
    except Exception:
        return None


def _domain(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc or url
    except Exception:
        return url

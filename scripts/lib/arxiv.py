"""arXiv academic paper search — free, no key required.

Uses the arXiv public API (Atom/XML) to find recent academic papers on a topic.
Ideal for AI/ML, computer science, physics, mathematics, and biology topics.

Always available — stdlib only (urllib + xml.etree.ElementTree), no auth needed.
Rate limit: arXiv asks for max 3 req/second; no hard limit for low-volume use.
"""

import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

from . import dates, log
from .relevance import token_overlap_relevance as _compute_relevance

ARXIV_API = "http://export.arxiv.org/api/query"
ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"

DEPTH_CONFIG = {
    "quick":   {"results": 8},
    "default": {"results": 15},
    "deep":    {"results": 30},
}

_USER_AGENT = "last30days/3.0 (research tool; https://github.com/mvanhorn/last30days-skill)"


def _log(msg: str) -> None:
    log.source_log("arXiv", msg)


def _parse_arxiv_date(raw: str) -> Optional[str]:
    """Parse arXiv ISO 8601 datetime to YYYY-MM-DD."""
    if not raw:
        return None
    d = dates.parse_date(raw.strip())
    return d.strftime("%Y-%m-%d") if d else None


def _parse_feed(xml_bytes: bytes, topic: str, max_results: int) -> List[Dict[str, Any]]:
    """Parse arXiv Atom XML into normalized item dicts."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        _log(f"XML parse error: {exc}")
        return []

    items: List[Dict[str, Any]] = []
    for i, entry in enumerate(root.findall(f"{ATOM_NS}entry")):
        if len(items) >= max_results:
            break

        # arXiv ID URL (canonical)
        id_el = entry.find(f"{ATOM_NS}id")
        arxiv_url = (id_el.text or "").strip() if id_el is not None else ""
        # Convert http://arxiv.org/abs/... to https://
        if arxiv_url.startswith("http://"):
            arxiv_url = "https://" + arxiv_url[7:]

        title_el = entry.find(f"{ATOM_NS}title")
        title = " ".join((title_el.text or "").split()) if title_el is not None else ""

        summary_el = entry.find(f"{ATOM_NS}summary")
        abstract = " ".join((summary_el.text or "").split()) if summary_el is not None else ""
        # Truncate abstract to a useful snippet
        snippet = abstract[:400] + ("..." if len(abstract) > 400 else "")

        published_el = entry.find(f"{ATOM_NS}published")
        date_str = _parse_arxiv_date(
            (published_el.text or "") if published_el is not None else ""
        )

        # Authors
        authors = [
            (a.find(f"{ATOM_NS}name").text or "").strip()
            for a in entry.findall(f"{ATOM_NS}author")
            if a.find(f"{ATOM_NS}name") is not None
        ]

        # Primary category
        cat_el = entry.find(f"{ARXIV_NS}primary_category")
        if cat_el is None:
            cat_el = entry.find("primary_category")
        category = (cat_el.get("term") or "") if cat_el is not None else ""

        if not title:
            continue

        rank_score = max(0.2, 1.0 - (i * 0.03))
        text_relevance = _compute_relevance(topic, f"{title} {abstract[:200]}")
        relevance = min(1.0, text_relevance * 0.55 + rank_score * 0.35 + 0.1)

        items.append({
            "id": arxiv_url.split("/abs/")[-1].replace("/", "_") or f"AX{i + 1}",
            "title": title,
            "snippet": snippet,
            "url": arxiv_url,
            "date": date_str,
            "source_domain": "arxiv.org",
            "relevance": round(relevance, 2),
            "why_relevant": f"arXiv: {title[:70]}",
            "metadata": {
                "authors": authors[:4],
                "category": category,
            },
        })

    return items


def search_arxiv(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
) -> Dict[str, Any]:
    """Search arXiv for recent academic papers on a topic.

    Args:
        topic: Search query (supports arXiv query syntax: ti: ab: au: etc.)
        from_date: Start date (YYYY-MM-DD) — context only; sortBy=submittedDate applied
        to_date: End date (YYYY-MM-DD)
        depth: 'quick', 'default', or 'deep'

    Returns:
        Dict with 'items' list and optional 'error'.
    """
    config = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])

    # Build query: search all fields (title, abstract, author)
    params = urlencode({
        "search_query": f"all:{topic}",
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": config["results"],
    })
    url = f"{ARXIV_API}?{params}"
    _log(f"Searching arXiv for '{topic}' (depth={depth}, max={config['results']})")

    try:
        req = Request(url, headers={"User-Agent": _USER_AGENT})
        with urlopen(req, timeout=20) as resp:
            xml_bytes = resp.read()
    except Exception as exc:
        _log(f"arXiv API error: {type(exc).__name__}: {exc}")
        return {"items": [], "error": f"{type(exc).__name__}: {exc}"}

    items = _parse_feed(xml_bytes, topic, config["results"])
    _log(f"Found {len(items)} arXiv papers")

    return {"items": items}


def parse_arxiv_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return items list from an arXiv search response."""
    return response.get("items", [])

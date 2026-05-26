"""Generic RSS/Atom feed reader — no dependencies beyond stdlib.

Reads one or more feed URLs supplied via EXTRA_RSS_FEEDS (comma-separated).
Each feed is fetched and parsed; items are returned in the standard grounding
shape so the existing normalizer pipeline handles them without changes.

Configuration (env / .env):
    EXTRA_RSS_FEEDS=https://example.com/feed.rss,https://other.com/atom.xml

Always available when EXTRA_RSS_FEEDS is set; disabled otherwise.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

from . import dates, log
from .relevance import token_overlap_relevance as _compute_relevance

DEPTH_CONFIG = {
    "quick":   {"per_feed": 5},
    "default": {"per_feed": 10},
    "deep":    {"per_feed": 20},
}

_ATOM_NS = "{http://www.w3.org/2005/Atom}"


def _log(msg: str) -> None:
    log.source_log("RSS", msg)


def _source_domain(url: str) -> str:
    try:
        return urlparse(url).netloc or url
    except Exception:
        return url


def _parse_date(raw: str) -> Optional[str]:
    if not raw:
        return None
    # Try RFC 2822 (RSS pubDate)
    try:
        return parsedate_to_datetime(raw).strftime("%Y-%m-%d")
    except Exception:
        pass
    # Try ISO 8601 (Atom updated/published)
    d = dates.parse_date(raw[:10])
    return d.strftime("%Y-%m-%d") if d else None


def _parse_rss_feed(xml_bytes: bytes, feed_url: str, topic: str, max_results: int) -> List[Dict[str, Any]]:
    """Parse RSS 2.0 or Atom feed bytes into item dicts."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        _log(f"XML parse error for {feed_url}: {exc}")
        return []

    items: List[Dict[str, Any]] = []
    domain = _source_domain(feed_url)

    # RSS 2.0
    channel = root.find("channel")
    if channel is not None:
        entries = channel.findall("item")
        for i, item in enumerate(entries[:max_results]):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            description = (item.findtext("description") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            date_str = _parse_date(pub_date)
            if not title:
                continue
            relevance = _compute_relevance(topic, f"{title} {description[:200]}")
            items.append({
                "id": link or f"RSS{i + 1}",
                "title": title,
                "snippet": description[:300],
                "url": link,
                "date": date_str,
                "source_domain": domain,
                "relevance": round(max(0.15, relevance * 0.8 + max(0.0, 1.0 - i * 0.04) * 0.2), 2),
                "why_relevant": f"RSS: {title[:70]}",
            })
        return items

    # Atom
    ns = _ATOM_NS
    entries = root.findall(f"{ns}entry")
    if not entries:
        # try without namespace
        entries = root.findall("entry")
        ns = ""

    for i, entry in enumerate(entries[:max_results]):
        title_el = entry.find(f"{ns}title")
        title = (title_el.text if title_el is not None else "").strip()

        link_el = entry.find(f"{ns}link")
        link = ""
        if link_el is not None:
            link = link_el.get("href", "") or (link_el.text or "")

        summary_el = entry.find(f"{ns}summary") or entry.find(f"{ns}content")
        description = (summary_el.text if summary_el is not None else "").strip() if summary_el is not None else ""

        updated_el = entry.find(f"{ns}updated") or entry.find(f"{ns}published")
        date_str = _parse_date((updated_el.text or "").strip() if updated_el is not None else "")

        if not title:
            continue
        relevance = _compute_relevance(topic, f"{title} {description[:200]}")
        items.append({
            "id": link or f"RSS{i + 1}",
            "title": title,
            "snippet": description[:300],
            "url": link,
            "date": date_str,
            "source_domain": domain,
            "relevance": round(max(0.15, relevance * 0.8 + max(0.0, 1.0 - i * 0.04) * 0.2), 2),
            "why_relevant": f"RSS: {title[:70]}",
        })

    return items


def search_rss(
    topic: str,
    from_date: str,
    to_date: str,
    feed_urls: List[str],
    depth: str = "default",
) -> Dict[str, Any]:
    """Fetch and aggregate all configured RSS/Atom feeds.

    Args:
        topic: Used for relevance scoring against item title/snippet.
        from_date: Start date (YYYY-MM-DD) for post-fetch filtering.
        to_date: End date (YYYY-MM-DD).
        feed_urls: List of feed URLs to fetch.
        depth: 'quick', 'default', or 'deep'.

    Returns:
        Dict with 'items' list and optional 'error'.
    """
    if not feed_urls:
        return {"items": []}

    config = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])
    per_feed = config["per_feed"]

    all_items: List[Dict[str, Any]] = []
    errors: List[str] = []

    for feed_url in feed_urls:
        feed_url = feed_url.strip()
        if not feed_url:
            continue
        _log(f"Fetching {feed_url}")
        try:
            with urlopen(feed_url, timeout=10) as resp:
                xml_bytes = resp.read()
        except URLError as exc:
            errors.append(f"{feed_url}: {exc}")
            _log(f"Fetch error: {exc}")
            continue
        except Exception as exc:
            errors.append(f"{feed_url}: {type(exc).__name__}")
            _log(f"Unexpected error: {exc}")
            continue

        parsed = _parse_rss_feed(xml_bytes, feed_url, topic, per_feed)
        _log(f"  → {len(parsed)} items from {_source_domain(feed_url)}")
        all_items.extend(parsed)

    # Date filter: prefer in-range but keep all if none qualify
    in_range = [it for it in all_items if it["date"] and from_date <= it["date"] <= to_date]
    if in_range:
        all_items = in_range

    all_items.sort(key=lambda x: x.get("relevance", 0), reverse=True)

    result: Dict[str, Any] = {"items": all_items}
    if errors:
        result["error"] = "; ".join(errors)
    _log(f"Total RSS items: {len(all_items)}")
    return result


def parse_rss_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return items list from an RSS search response."""
    return response.get("items", [])

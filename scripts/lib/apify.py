"""Apify actor client for last30days fallback scraping.

Provides fallback search paths for TikTok, Instagram, and Threads
when ScrapeCreators is unavailable. Uses Apify's run-sync endpoint.

Actor IDs are well-known public actors on the Apify store:
  - clockworks/tiktok-scraper  (highly rated, actively maintained)
  - apify/instagram-scraper
  - apify/threads-scraper

Set APIFY_API_TOKEN in your .env to enable these fallbacks.
Apify has a generous free tier (~$5/month of free usage).
"""

from __future__ import annotations

import sys
from typing import Any

from . import http, log

APIFY_BASE = "https://api.apify.com/v2"

ACTOR_TIKTOK = "clockworks/tiktok-scraper"
ACTOR_INSTAGRAM = "apify/instagram-hashtag-scraper"
ACTOR_THREADS = "apify/threads-scraper"

# Sync timeout for actor runs (seconds). Cold starts can take 30-60s.
APIFY_TIMEOUT = 120


def _run_actor(
    actor_id: str,
    token: str,
    input_data: dict[str, Any],
    *,
    timeout: int = APIFY_TIMEOUT,
    memory_mbytes: int = 256,
) -> list[dict[str, Any]]:
    """Run an Apify actor synchronously and return dataset items.

    Returns empty list on any error so callers can chain gracefully.
    """
    # Apify REST API requires '~' not '/' in actor IDs within URL paths.
    # e.g. "clockworks/tiktok-scraper" → "clockworks~tiktok-scraper"
    actor_url_id = actor_id.replace("/", "~")
    url = (
        f"{APIFY_BASE}/acts/{actor_url_id}/run-sync-get-dataset-items"
        f"?token={token}&timeout={timeout}&memory={memory_mbytes}"
    )
    try:
        result = http.request(
            "POST",
            url,
            headers={"Content-Type": "application/json"},
            json_data=input_data,
            timeout=timeout + 15,
            retries=1,
        )
    except Exception as exc:
        log.source_log("Apify", f"Actor {actor_id} error: {exc}", tty_only=False)
        return []

    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return result.get("items") or result.get("data") or []
    return []


def tiktok_search(query: str, count: int = 20, *, token: str) -> list[dict[str, Any]]:
    """Search TikTok via Apify clockworks/tiktok-scraper."""
    log.source_log("Apify/TikTok", f"Searching '{query}' (count={count})", tty_only=False)
    return _run_actor(
        ACTOR_TIKTOK,
        token,
        {
            "searchQueries": [query],
            "maxVideos": count,
            "shouldDownloadCovers": False,
            "shouldDownloadVideos": False,
            "shouldDownloadSubtitles": False,
        },
    )


def instagram_search(query: str, count: int = 20, *, token: str) -> list[dict[str, Any]]:
    """Search Instagram via Apify apify/instagram-hashtag-scraper.

    Strips spaces from query to form a hashtag (e.g. "claude ai" -> "claudeai").
    Uses the dedicated hashtag scraper actor which is more reliable than the
    general-purpose instagram-scraper for hashtag searches.
    """
    hashtag = query.replace(" ", "").lower()
    log.source_log("Apify/Instagram", f"Searching '#{hashtag}' (count={count})", tty_only=False)
    return _run_actor(
        ACTOR_INSTAGRAM,
        token,
        {
            "hashtags": [hashtag],
            "resultsLimit": count,
        },
    )


def threads_search(query: str, count: int = 20, *, token: str) -> list[dict[str, Any]]:
    """Search Threads via Apify apify/threads-scraper."""
    log.source_log("Apify/Threads", f"Searching '{query}' (count={count})", tty_only=False)
    return _run_actor(
        ACTOR_THREADS,
        token,
        {
            "searchTerms": [query],
            "maxPosts": count,
        },
    )

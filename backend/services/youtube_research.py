"""
youtube_research.py — YouTube metadata research for GameCut AI.

Uses yt-dlp to search YouTube for videos similar to the user's clip.
Pulls ONLY metadata (title, views, duration, channel, description).
No creator footage is downloaded or reused.

Returns structured research data the AI planner uses to choose
edit style, pacing, and caption tone.
"""
from __future__ import annotations

import re
from typing import Any

import yt_dlp


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def research_youtube(
    game_name: str,
    style: str,
    dominant_tone: str = "neutral",
    max_results: int = 15,
    audience: list | None = None,
) -> dict[str, Any]:
    """
    Search YouTube for gameplay content matching this game + style + audience.

    Returns:
        {
            "query": str,
            "results": list[VideoMeta],
            "summary": str,
            "top_channels": list[str],
            "avg_duration": float,
            "avg_views": int,
            "style_signals": list[str],
        }
    """
    query = _build_query(game_name, style, dominant_tone, audience or [])
    raw_results = _search_youtube(query, max_results)

    if not raw_results:
        return _empty_research(game_name, style, query)

    # Compute aggregate signals
    views = [r["view_count"] for r in raw_results if r["view_count"] > 0]
    durations = [r["duration"] for r in raw_results if r["duration"] > 0]
    channels = [r["channel"] for r in raw_results if r["channel"]]

    avg_views = int(sum(views) / len(views)) if views else 0
    avg_duration = round(sum(durations) / len(durations), 1) if durations else 60.0
    top_channels = _top_unique(channels, 5)

    style_signals = _extract_style_signals(raw_results, style)
    summary = _build_summary(game_name, style, raw_results, top_channels, avg_views, avg_duration)

    return {
        "query": query,
        "results": raw_results[:max_results],
        "summary": summary,
        "top_channels": top_channels,
        "avg_duration": avg_duration,
        "avg_views": avg_views,
        "style_signals": style_signals,
    }


# ---------------------------------------------------------------------------
# yt-dlp search
# ---------------------------------------------------------------------------

def _search_youtube(query: str, max_results: int) -> list[dict[str, Any]]:
    """Run a YouTube search via yt-dlp and return cleaned metadata."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "default_search": f"ytsearch{max_results}",
        "noplaylist": True,
    }

    results: list[dict[str, Any]] = []

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            entries = info.get("entries") or []

            for entry in entries:
                if not isinstance(entry, dict):
                    continue

                cleaned = _clean_entry(entry)
                if cleaned:
                    results.append(cleaned)

    except Exception:
        pass

    return results


def _clean_entry(entry: dict) -> dict[str, Any] | None:
    """Extract only the metadata fields we need from a yt-dlp entry."""
    url = entry.get("url") or entry.get("webpage_url") or ""
    if not url:
        return None

    # Make sure it's a real YouTube URL
    if not re.search(r"(youtube\.com|youtu\.be)", url):
        url = f"https://www.youtube.com/watch?v={entry.get('id', '')}"

    title = str(entry.get("title") or "").strip()
    if not title:
        return None

    return {
        "id": str(entry.get("id") or ""),
        "title": title,
        "url": url,
        "channel": str(entry.get("channel") or entry.get("uploader") or "").strip(),
        "view_count": int(entry.get("view_count") or 0),
        "duration": float(entry.get("duration") or 0),
        "description": str(entry.get("description") or "")[:300],
    }


# ---------------------------------------------------------------------------
# Signal extraction
# ---------------------------------------------------------------------------

_STYLE_KEYWORDS: dict[str, list[str]] = {
    "hype": ["best", "insane", "montage", "highlights", "clutch", "epic", "op", "crazy", "kills"],
    "cinematic": ["cinematic", "story", "film", "atmospheric", "4k", "beautiful", "emotional"],
    "funny": ["funny", "fails", "moments", "hilarious", "meme", "trolling", "cursed", "lol"],
    "tutorial": ["how to", "guide", "tips", "tricks", "tutorial", "beginner", "explained"],
    "horror": ["scary", "horror", "terrifying", "jumpscares", "dark", "survival", "nightmare"],
}


def _extract_style_signals(results: list[dict], style: str) -> list[str]:
    """
    Look at titles and descriptions to find common phrasing/patterns
    that perform well for this style. Returns up to 8 signal strings.
    """
    keywords = _STYLE_KEYWORDS.get(style, _STYLE_KEYWORDS["hype"])
    found: dict[str, int] = {}

    for r in results:
        text = (r["title"] + " " + r["description"]).lower()
        for kw in keywords:
            if kw in text:
                found[kw] = found.get(kw, 0) + 1

    # Also pull common title patterns from high-view videos
    high_view = sorted(results, key=lambda x: x["view_count"], reverse=True)[:5]
    for r in high_view:
        # Extract title patterns like "X kills in Y" or "INSANE X"
        matches = re.findall(r"\b([A-Z][A-Z]+)\b", r["title"])
        for m in matches:
            if len(m) >= 3:
                found[m.lower()] = found.get(m.lower(), 0) + 1

    # Sort by frequency, return top 8
    sorted_signals = sorted(found.items(), key=lambda x: x[1], reverse=True)
    return [s[0] for s in sorted_signals[:8]]


def _build_summary(
    game_name: str,
    style: str,
    results: list[dict],
    top_channels: list[str],
    avg_views: int,
    avg_duration: float,
) -> str:
    if not results:
        return f"No YouTube results found for {game_name} {style} content."

    channel_str = ", ".join(top_channels) if top_channels else "various creators"
    views_str = f"{avg_views:,}" if avg_views > 0 else "unknown"
    dur_str = f"{int(avg_duration)}s" if avg_duration > 0 else "unknown"

    return (
        f"Found {len(results)} {game_name} {style} videos on YouTube. "
        f"Top creators in this niche: {channel_str}. "
        f"Average video length: {dur_str}, average views: {views_str}. "
        f"Used as pacing and style reference only — no creator footage is reused."
    )


def _build_query(game_name: str, style: str, dominant_tone: str, audience: list) -> str:
    style_terms = {
        "hype": "highlights montage",
        "cinematic": "cinematic gameplay",
        "funny": "funny moments fails",
        "tutorial": "tips guide how to",
        "horror": "horror gameplay scary moments",
    }
    term = style_terms.get(style, "gameplay")

    tone_modifier = ""
    if dominant_tone == "dark":
        tone_modifier = " dark"
    elif dominant_tone == "bright":
        tone_modifier = " action"

    # If user picked a creator audience, add one name to the query for better results
    creator_hint = f" {audience[0]}" if audience else ""

    return f"{game_name}{tone_modifier}{creator_hint} {term}"


def _top_unique(items: list[str], n: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
        if len(result) >= n:
            break
    return result


def _empty_research(game_name: str, style: str, query: str) -> dict[str, Any]:
    return {
        "query": query,
        "results": [],
        "summary": f"YouTube research unavailable for {game_name}. Using built-in style recipes.",
        "top_channels": [],
        "avg_duration": 60.0,
        "avg_views": 0,
        "style_signals": _STYLE_KEYWORDS.get(style, []),
    }

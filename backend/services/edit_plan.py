from __future__ import annotations

from typing import Any


STYLE_EFFECTS = {
    "horror": ["suspense hold", "dark grade", "reaction zoom", "static hit"],
    "cinematic": ["cinematic grade", "slow fade", "subtle sharpen"],
    "funny": ["freeze frame", "reaction caption", "quick zoom"],
    "tutorial": ["clean trim", "step caption", "highlight zoom"],
    "hype": ["style grade", "fade", "punch zoom"],
    "greenscreen": ["chroma key", "clean trim", "subtle sharpen"],
    "vintage": ["sepia tone", "film grain", "vignette"],
    "neon": ["glow effect", "color shift", "high contrast"],
    "blur": ["gaussian blur", "soft focus", "dreamy"],
}


def create_edit_plan(
    options: dict[str, Any],
    highlights: list[float],
    research: dict[str, Any] | None = None,
) -> dict[str, Any]:
    options = dict(options or {})
    research = dict(research or {})

    game_name = str(options.get("game_name") or "Gameplay")
    style = str(options.get("style") or "hype").lower()
    target_duration = int(options.get("target_duration") or 60)
    add_effects = options.get("add_effects", True)
    add_subtitles = options.get("add_subtitles", True)

    genre = str(research.get("genre") or _genre_from_style(style))
    creator_targets = list(research.get("creator_targets") or [])
    start = max(0.0, float(highlights[0])) if highlights else 0.0

    clip = {
        "start": start,
        "end": start + float(target_duration),
        "effect": style,
        "transition": "fade" if add_effects else "cut",
    }

    return {
        "version": 1,
        "game_name": game_name,
        "style": style,
        "genre": genre,
        "creator_targets": creator_targets,
        "target_duration": target_duration,
        "clips": [clip],
        "effects": list(STYLE_EFFECTS.get(style, STYLE_EFFECTS["hype"])) if add_effects else [],
        "captions_enabled": bool(add_subtitles),
        "research_summary": str(research.get("summary") or ""),
    }


def _genre_from_style(style: str) -> str:
    if style == "horror":
        return "horror"
    return "general"

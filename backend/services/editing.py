"""
editing.py — Edit options, ASS subtitle generation, and FFmpeg filter helpers.
"""
from __future__ import annotations

from pathlib import Path

ALLOWED_STYLES = {"hype", "cinematic", "funny", "tutorial", "horror",
                  "greenscreen", "vintage", "neon", "blur"}


# ---------------------------------------------------------------------------
# Option normalization
# ---------------------------------------------------------------------------

def _as_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on", "checked"}


def _as_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def normalize_edit_options(raw: dict | None) -> dict:
    raw = raw or {}
    game_name = str(raw.get("game_name") or raw.get("gameName") or "Gameplay").strip() or "Gameplay"
    style = str(raw.get("style") or "hype").strip().lower()
    if style not in ALLOWED_STYLES:
        style = "hype"

    return {
        "game_name": game_name[:80],
        "style": style,
        "target_duration": _as_int(
            raw.get("target_duration") or raw.get("targetDuration"), 60, 5, 7200
        ),
        "add_subtitles": _as_bool(
            raw.get("add_subtitles") if "add_subtitles" in raw else raw.get("addSubtitles"), True
        ),
        "add_effects": _as_bool(
            raw.get("add_effects") if "add_effects" in raw else raw.get("addEffects"), True
        ),
        "use_whisper": _as_bool(
            raw.get("use_whisper") if "use_whisper" in raw else raw.get("useWhisper"), False
        ),
        "remove_silence": _as_bool(
            raw.get("remove_silence") if "remove_silence" in raw else raw.get("removeSilence"), False
        ),
        "remove_fillers": _as_bool(
            raw.get("remove_fillers") if "remove_fillers" in raw else raw.get("removeFillers"), False
        ),
        "jump_cuts": _as_bool(
            raw.get("jump_cuts") if "jump_cuts" in raw else raw.get("jumpCuts"), False
        ),
        "export_resolution": str(raw.get("export_resolution") or raw.get("exportResolution") or "1080p").strip(),
        "export_fps": _as_int(raw.get("export_fps") or raw.get("exportFps"), 30, 24, 60),
        "export_aspect_ratio": str(raw.get("export_aspect_ratio") or raw.get("exportAspectRatio") or "16:9").strip(),
        "audience": [str(c) for c in raw.get("audience", []) if c][:5],
    }


# ---------------------------------------------------------------------------
# ASS subtitle generation
# ---------------------------------------------------------------------------

def _ass_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    cs = int((seconds - int(seconds)) * 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _escape_ass_text(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


_ASS_HEADER = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: GameCut,Arial Black,82,&H00FFFFFF,&H0000FFFF,&H00101010,&HAA000000,-1,0,0,0,100,100,0,0,1,5,2,2,80,80,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def write_ass_subtitles(events: list[dict], output_path: str | Path) -> None:
    """Write ASS subtitle file from [{start, end, text}] events."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"Dialogue: 0,{_ass_time(e['start'])},{_ass_time(e['end'])},GameCut,,0,0,0,,"
        f"{{\\fad(100,100)\\be2}}{_escape_ass_text(e['text'])}"
        for e in events
        if e.get("text") and float(e.get("end", 0)) > float(e.get("start", 0))
    ]
    output_path.write_text(_ASS_HEADER + "\n".join(lines) + "\n", encoding="utf-8")


def write_ass_subtitles_from_plan(
    captions: list[dict],
    output_path: str | Path,
    timeline_offset: float = 0.0,
) -> None:
    """
    Write ASS subtitles from an AI planner caption list.

    timeline_offset: subtract this from all caption times so they align
    with the output video's timeline (not the source video's timestamps).
    Caption format: [{time, end, text, style}]
    """
    events = []
    for cap in captions:
        if not cap.get("text"):
            continue
        raw_start = float(cap.get("time") or cap.get("start") or 0)
        raw_end = float(cap.get("end") or raw_start + 2.5)
        # Re-time to output position
        start = max(0.0, raw_start - timeline_offset)
        end = max(start + 0.2, raw_end - timeline_offset)
        events.append({"start": start, "end": end, "text": str(cap["text"])})

    write_ass_subtitles(events, output_path)


# ---------------------------------------------------------------------------
# Caption re-timing helper
# ---------------------------------------------------------------------------

def retimed_captions(captions: list[dict], clips: list[dict]) -> list[dict]:
    """
    Re-time captions from source-video timestamps to output-timeline timestamps.

    The AI plan has captions with source timestamps.
    After cutting clips and concatenating, those timestamps no longer match.
    This maps each caption to its correct position in the output.

    Returns a new caption list with `time` and `end` relative to output start.
    """
    if not captions or not clips:
        return captions

    # Build a mapping: for each output second, what source second does it correspond to?
    # clips = [{start, end, ...}] sorted by start
    sorted_clips = sorted(clips, key=lambda c: float(c.get("start", 0)))

    result = []
    for cap in captions:
        src_time = float(cap.get("time") or cap.get("start") or 0)
        src_end = float(cap.get("end") or src_time + 2.5)

        # Find which clip this caption falls in
        output_offset = 0.0
        placed = False
        for clip in sorted_clips:
            c_start = float(clip.get("start", 0))
            c_end = float(clip.get("end", c_start))
            c_dur = c_end - c_start

            if c_start <= src_time < c_end:
                # Caption is within this clip
                out_start = output_offset + (src_time - c_start)
                out_end = output_offset + min(src_end - c_start, c_dur)
                result.append({**cap, "time": round(out_start, 3), "end": round(out_end, 3)})
                placed = True
                break

            output_offset += c_dur

        if not placed:
            # Caption doesn't land in any clip — place it at the very start of output
            result.append({**cap, "time": 0.5, "end": 3.0})

    return result


# ---------------------------------------------------------------------------
# Legacy build_caption_events (kept for backward compat)
# ---------------------------------------------------------------------------

def build_caption_events(options: dict, duration: float) -> list[dict]:
    if not options.get("add_subtitles", True):
        return []
    safe_dur = max(5.0, float(duration or options.get("target_duration") or 12))
    style = str(options.get("style") or "hype").upper()
    game_name = str(options.get("game_name") or "Gameplay")
    events = [
        {"start": 0.35, "end": min(2.8, safe_dur), "text": game_name},
        {"start": min(3.0, safe_dur * 0.35), "end": min(5.4, safe_dur), "text": f"{style} EDIT"},
    ]
    if safe_dur > 8:
        events.append({
            "start": min(6.2, safe_dur - 2.0),
            "end": min(8.8, safe_dur),
            "text": _style_hook(str(options.get("style") or "hype")),
        })
    return [e for e in events if e["end"] > e["start"]]


def _style_hook(style: str) -> str:
    return {
        "hype": "BEST MOMENT",
        "cinematic": "CLUTCH SEQUENCE",
        "funny": "WAIT FOR IT",
        "tutorial": "WATCH THIS PLAY",
        "horror": "RUN.",
    }.get(style, "BEST MOMENT")


# ---------------------------------------------------------------------------
# Legacy filter chain builders (kept for backward compat)
# ---------------------------------------------------------------------------

def _filter_path(path: str | Path) -> str:
    normalized = str(path).replace("\\", "/").replace(":", "\\:")
    return normalized.replace("'", "\\'")


def _style_filters(style: str) -> list[str]:
    if style == "cinematic":
        return ["eq=contrast=1.1:saturation=0.95:brightness=-0.02", "unsharp=5:5:0.4:3:3:0.15"]
    if style == "funny":
        return ["eq=contrast=1.06:saturation=1.45", "hue=h=5:s=1.1"]
    if style == "tutorial":
        return ["eq=contrast=1.05:saturation=1.1", "unsharp=5:5:0.5:3:3:0.2"]
    if style == "horror":
        return ["eq=contrast=1.2:saturation=0.55:brightness=-0.06", "unsharp=5:5:0.5:3:3:0.2"]
    return ["eq=contrast=1.12:saturation=1.32", "unsharp=5:5:0.8:3:3:0.4"]


def build_filter_chain(options: dict, subtitle_path: str | Path | None = None) -> str:
    filters: list[str] = []
    duration = float(options.get("target_duration") or 12)
    style = str(options.get("style") or "hype")
    if options.get("add_effects", True):
        filters.extend(_style_filters(style))
        filters.append("fade=t=in:st=0:d=0.25")
        if duration > 1:
            filters.append(f"fade=t=out:st={max(0.0, duration - 0.35):.2f}:d=0.35")
    if options.get("add_subtitles", True) and subtitle_path:
        filters.append(f"ass='{_filter_path(subtitle_path)}'")
    return ",".join(filters)


def build_filter_chain_from_plan(
    options: dict,
    subtitle_path: str | Path | None = None,
) -> str:
    """Wrapper used by the pipeline — delegates to build_filter_chain."""
    return build_filter_chain(options, subtitle_path)

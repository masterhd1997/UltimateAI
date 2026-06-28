"""
ai_planner.py — AI edit plan generator for GameCut AI.

Priority order:
  1. Ollama (local, free) — if Ollama is running
  2. OpenAI API        — if OPENAI_API_KEY is set in .env
  3. Rule-based fallback — always works, uses real highlight data
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any

try:
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

OLLAMA_BASE_URL = "http://localhost:11434"

OLLAMA_MODEL_PREFERENCE = [
    "qwen2.5:latest",
    "qwen2.5",
    "mistral:latest",
    "mistral",
    "llama3.1:latest",
    "llama3.1",
    "llama3.2:latest",
    "llama3.2",
    "mistral-nemo:latest",
    "mistral-nemo",
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_edit_plan(
    options: dict[str, Any],
    video_analysis: dict[str, Any],
    transcript: str,
    research: dict[str, Any],
) -> dict[str, Any]:
    """
    Generate a full edit plan. Tries Ollama → OpenAI → rule-based fallback.
    """
    # Try Ollama first (free, local)
    ollama_model = _find_ollama_model()
    if ollama_model:
        try:
            return _ollama_edit_plan(options, video_analysis, transcript, research, ollama_model)
        except Exception as e:
            import traceback
            print(f"[ai_planner] Ollama failed ({ollama_model}): {e}")
            traceback.print_exc()

    # Try OpenAI if key is set
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if _OPENAI_AVAILABLE and api_key:
        try:
            return _openai_edit_plan(options, video_analysis, transcript, research, api_key)
        except Exception as e:
            print(f"[ai_planner] OpenAI failed: {e}")

    # Rule-based fallback
    return _rule_based_plan(options, video_analysis, research)


# ---------------------------------------------------------------------------
# Ollama (local, free)
# ---------------------------------------------------------------------------

def _find_ollama_model() -> str | None:
    """Check if Ollama is running and return the best available model."""
    for timeout in (3, 6):
        try:
            with urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/tags", timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
            available = [m["name"] for m in data.get("models", [])]
            for preferred in OLLAMA_MODEL_PREFERENCE:
                if preferred in available:
                    return preferred
            if available:
                return available[0]
            return None
        except Exception:
            continue
    return None


def _ollama_edit_plan(
    options: dict[str, Any],
    video_analysis: dict[str, Any],
    transcript: str,
    research: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    prompt = _build_prompt(options, video_analysis, transcript, research)

    payload = json.dumps({
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are GameCut AI, an expert gameplay video editor. "
                    "Analyze footage data and return a precise edit plan as JSON only. "
                    "No markdown, no explanation — only valid JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 2000,
        },
    }).encode()

    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode())

    raw = result.get("message", {}).get("content") or ""
    plan = _parse_json_response(raw)
    return _merge_with_defaults(plan, options, video_analysis, research)


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

def _openai_edit_plan(
    options: dict[str, Any],
    video_analysis: dict[str, Any],
    transcript: str,
    research: dict[str, Any],
    api_key: str,
) -> dict[str, Any]:
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key)
    prompt = _build_prompt(options, video_analysis, transcript, research)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are GameCut AI, an expert gameplay video editor. "
                    "Always respond with valid JSON only — no markdown, no explanation outside the JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
        max_tokens=2000,
    )

    raw = response.choices[0].message.content or ""
    plan = _parse_json_response(raw)
    return _merge_with_defaults(plan, options, video_analysis, research)


# ---------------------------------------------------------------------------
# Shared prompt
# ---------------------------------------------------------------------------

def _build_prompt(
    options: dict[str, Any],
    analysis: dict[str, Any],
    transcript: str,
    research: dict[str, Any],
) -> str:
    game = options.get("game_name", "Gameplay")
    style = options.get("style", "hype")
    target_dur = int(options.get("target_duration", 60))
    add_subs = options.get("add_subtitles", True)
    add_fx = options.get("add_effects", True)
    remove_silence = options.get("remove_silence", False)
    remove_fillers = options.get("remove_fillers", False)
    jump_cuts = options.get("jump_cuts", False)

    duration = analysis.get("duration", 0)
    highlights = analysis.get("highlights", [])[:12]

    # Build AI enhancement instructions
    silence_removal_instruction = ""
    filler_removal_instruction = ""
    jump_cut_instruction = ""

    if remove_silence:
        silence_removal_instruction = "- Identify and mark silent segments (audio < -40dB) for removal"
    if remove_fillers:
        filler_removal_instruction = "- Identify and mark filler words (um, uh, like, you know) for removal"
    if jump_cuts:
        jump_cut_instruction = "- Suggest jump cut points at natural pauses for faster pacing"
    scene_changes = analysis.get("scene_changes", [])[:20]
    audio_peaks = analysis.get("audio_peaks", [])[:20]
    tone = analysis.get("dominant_tone", "neutral")
    intensity_curve = analysis.get("intensity_curve", [])
    top_moments = sorted(intensity_curve, key=lambda x: x.get("intensity", 0), reverse=True)[:8]

    yt_summary = research.get("summary", "")
    style_signals = research.get("style_signals", [])
    top_channels = research.get("top_channels", [])
    avg_yt_duration = research.get("avg_duration", 60)
    transcript_snippet = transcript[:600] if transcript else "No transcript."
    audience = options.get("audience", [])

    num_clips = min(8, max(2, target_dur // 10))

    pacing_desc = {
        "hype": "fast cuts, high energy",
        "cinematic": "slow, atmospheric",
        "funny": "comedic timing",
        "tutorial": "clear and clean",
        "horror": "suspense and tension",
    }.get(style, "medium pacing")

    audience_line = f"Target audience: viewers of {', '.join(audience)}" if audience else ""

    return f"""Edit a {game} gameplay video.

VIDEO: duration={duration:.1f}s, target={target_dur}s, style={style}, tone={tone}, subtitles={add_subs}, effects={add_fx}
{audience_line}
HIGHLIGHTS: {json.dumps(highlights)}
SCENE CHANGES: {json.dumps(scene_changes)}
AUDIO PEAKS: {json.dumps(audio_peaks)}
TOP MOMENTS: {json.dumps(top_moments)}
PLAYER SPEECH: {transcript_snippet}
YOUTUBE: {yt_summary}
Top channels: {', '.join(top_channels) if top_channels else 'N/A'}
Signals: {', '.join(style_signals) if style_signals else 'N/A'}
Avg YT length: {avg_yt_duration:.0f}s

TASK: Create a {target_dur}s {style} edit of {game}.
- Select {num_clips} non-overlapping clips from 0 to {duration:.1f}s
- Focus clips on highlights and audio peaks
- Pacing: {pacing_desc}
- Write 3-5 fitting captions
- Generate a catchy, descriptive video title (max 60 chars) based on game, speech, and style
{silence_removal_instruction}
{filler_removal_instruction}
{jump_cut_instruction}

Respond ONLY with valid JSON, no markdown, no extra text:
{{"clips":[{{"start":0.0,"end":8.0,"effect":"punch_zoom","transition":"cut","reason":"opening highlight"}}],"captions":[{{"time":1.0,"end":3.0,"text":"CAPTION","style":"pop"}}],"effects":["eq_hype","fade_in","fade_out"],"pacing":"fast","edit_notes":"brief note","suggested_title":"Amazing {game} Highlights","silence_segments":[],"filler_segments":[],"jump_cut_points":[]}}"""


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------

def _parse_json_response(raw: str) -> dict[str, Any]:
    raw = re.sub(r"```(?:json)?\s*", "", raw).strip().strip("`").strip()
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start >= 0 and end > start:
        raw = raw[start:end]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


# ---------------------------------------------------------------------------
# Merge / validate model output
# ---------------------------------------------------------------------------

def _merge_with_defaults(
    plan: dict[str, Any],
    options: dict[str, Any],
    analysis: dict[str, Any],
    research: dict[str, Any],
) -> dict[str, Any]:
    """Validate model output and fill any gaps with rule-based logic."""
    fallback = _rule_based_plan(options, analysis, research)
    duration = float(analysis.get("duration") or 9999)

    # Validate clips
    clips = plan.get("clips")
    if not isinstance(clips, list) or not clips:
        clips = fallback["clips"]
    else:
        valid = []
        for c in clips:
            if not isinstance(c, dict):
                continue
            s = float(c.get("start") or 0)
            e = float(c.get("end") or 0)
            if e > s and s >= 0 and e <= duration + 1:
                valid.append({
                    "start": round(s, 2),
                    "end": round(e, 2),
                    "effect": str(c.get("effect") or "cut"),
                    "transition": str(c.get("transition") or "cut"),
                    "reason": str(c.get("reason") or ""),
                })
        clips = valid if valid else fallback["clips"]

    # Validate captions
    captions = plan.get("captions")
    if not isinstance(captions, list):
        captions = fallback["captions"]
    else:
        valid_caps = []
        for cap in captions:
            if isinstance(cap, dict) and cap.get("text"):
                valid_caps.append({
                    "time": float(cap.get("time") or 0),
                    "end": float(cap.get("end") or float(cap.get("time") or 0) + 2.5),
                    "text": str(cap["text"])[:80],
                    "style": str(cap.get("style") or "pop"),
                })
        captions = valid_caps if valid_caps else fallback["captions"]

    # Validate effects
    effects = plan.get("effects")
    if not isinstance(effects, list) or not effects:
        effects = fallback["effects"]

    # Preserve the model's edit_notes
    model_notes = str(plan.get("edit_notes") or "").strip()
    fallback_notes = fallback.get("edit_notes", "Rule-based plan (no AI available).")
    edit_notes = model_notes if model_notes else fallback_notes
    ai_powered = bool(model_notes)

    return {
        "version": 2,
        "game_name": options.get("game_name", "Gameplay"),
        "style": options.get("style", "hype"),
        "genre": research.get("genre", _genre_from_style(options.get("style", "hype"))),
        "target_duration": int(options.get("target_duration", 60)),
        "clips": clips,
        "captions": captions,
        "effects": effects,
        "pacing": str(plan.get("pacing") or fallback.get("pacing", "medium")),
        "edit_notes": edit_notes,
        "ai_powered": ai_powered,
        "research_summary": research.get("summary", ""),
        "top_channels": research.get("top_channels", []),
        "style_signals": research.get("style_signals", []),
        "captions_enabled": bool(options.get("add_subtitles", True)),
        "creator_targets": research.get("top_channels", []),
    }


# ---------------------------------------------------------------------------
# Rule-based fallback
# ---------------------------------------------------------------------------

_STYLE_EFFECTS = {
    "hype":      ["eq_hype", "punch_zoom", "fade_in", "fade_out"],
    "cinematic": ["eq_cinematic", "slow_fade", "subtle_sharpen", "fade_in", "fade_out"],
    "funny":     ["eq_funny", "freeze_frame", "quick_zoom", "fade_in", "fade_out"],
    "tutorial":  ["eq_tutorial", "highlight_zoom", "fade_in", "fade_out"],
    "horror":    ["eq_dark", "suspense_hold", "reaction_zoom", "static_hit", "fade_in"],
}

_STYLE_PACING = {
    "hype": "fast",
    "cinematic": "slow",
    "funny": "medium",
    "tutorial": "medium",
    "horror": "slow",
}


def _rule_based_plan(
    options: dict[str, Any],
    analysis: dict[str, Any],
    research: dict[str, Any],
) -> dict[str, Any]:
    style = str(options.get("style") or "hype").lower()
    target_dur = int(options.get("target_duration") or 60)
    game = str(options.get("game_name") or "Gameplay")
    add_subs = bool(options.get("add_subtitles", True))

    highlights = analysis.get("highlights", [])
    audio_peaks = analysis.get("audio_peaks", [])
    scene_changes = analysis.get("scene_changes", [])
    duration = float(analysis.get("duration") or target_dur + 5)

    candidate_times = sorted(set(
        [h["time"] for h in highlights] +
        scene_changes[:10] +
        audio_peaks[:10]
    ))
    candidate_times = [t for t in candidate_times if 0.5 <= t <= duration - 3.0]

    clip_duration = max(3.0, target_dur / max(3, len(candidate_times[:8]) or 3))
    clips = []
    total_so_far = 0.0

    if candidate_times:
        for t in candidate_times[:8]:
            if total_so_far >= target_dur:
                break
            remaining = target_dur - total_so_far
            end_t = min(t + min(clip_duration, remaining), duration)
            if end_t - t < 1.5:
                continue
            clips.append({
                "start": round(t, 2),
                "end": round(end_t, 2),
                "effect": style,
                "transition": "fade" if style in ("cinematic", "horror") else "cut",
                "reason": "highlight moment",
            })
            total_so_far += end_t - t
    else:
        intensity_curve = analysis.get("intensity_curve", [])
        if intensity_curve:
            best = max(intensity_curve, key=lambda x: x.get("intensity", 0))
            start_t = max(0.0, best["time"] - 2.0)
        else:
            start_t = 0.0
        clips = [{
            "start": round(start_t, 2),
            "end": round(min(start_t + target_dur, duration), 2),
            "effect": style,
            "transition": "fade",
            "reason": "full clip",
        }]

    return {
        "version": 2,
        "game_name": game,
        "style": style,
        "genre": research.get("genre", _genre_from_style(style)),
        "target_duration": target_dur,
        "clips": clips,
        "captions": _style_captions(game, style, add_subs),
        "effects": _STYLE_EFFECTS.get(style, _STYLE_EFFECTS["hype"]),
        "pacing": _STYLE_PACING.get(style, "medium"),
        "edit_notes": "Rule-based plan (no AI available).",
        "ai_powered": False,
        "research_summary": research.get("summary", ""),
        "top_channels": research.get("top_channels", []),
        "style_signals": research.get("style_signals", []),
        "captions_enabled": add_subs,
        "creator_targets": research.get("top_channels", []),
    }


def _style_captions(game: str, style: str, add_subs: bool) -> list[dict]:
    if not add_subs:
        return []
    hooks = {
        "hype":      [game, "INSANE MOMENT", "BEST CLIP"],
        "cinematic": [game, "CLUTCH SEQUENCE", "CINEMATIC"],
        "funny":     [game, "WAIT FOR IT...", "LOL"],
        "tutorial":  [game, "WATCH THIS", "PRO TIP"],
        "horror":    [game, "DON'T LOOK AWAY", "RUN."],
    }
    texts = hooks.get(style, hooks["hype"])
    captions = []
    for i, text in enumerate(texts):
        start = 0.5 + i * 3.5
        captions.append({
            "time": round(start, 2),
            "end": round(start + 2.5, 2),
            "text": text,
            "style": "pop",
        })
    return captions


def _genre_from_style(style: str) -> str:
    return {
        "horror": "horror",
        "cinematic": "cinematic",
        "tutorial": "tutorial",
        "funny": "comedy",
    }.get(style, "general")

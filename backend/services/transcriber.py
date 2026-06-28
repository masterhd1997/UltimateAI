"""
transcriber.py — Speech-to-text for GameCut AI.

Uses OpenAI Whisper (local, already installed) to transcribe
gameplay audio. The transcript feeds into the AI planner so GPT
understands what the player is saying (reactions, callouts, commentary)
and can produce more contextually accurate captions and edit decisions.

Falls back to an empty transcript gracefully if whisper fails.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any


def transcribe_video(
    video_path: str,
    ffmpeg_path: str | None = None,
    model_size: str = "tiny",
) -> dict[str, Any]:
    """
    Transcribe the audio from a video file using Whisper.

    Uses 'tiny' model by default for speed. 'base' or 'small' give
    better accuracy at the cost of a few extra seconds.

    Returns:
        {
            "text": str,          — full transcript
            "language": str,      — detected language
            "segments": list,     — [{start, end, text}]
            "success": bool,
        }
    """
    try:
        import whisper
    except ImportError:
        return _empty_transcript("Whisper not installed.")

    # Extract audio to a temp WAV first (whisper is more reliable with WAV)
    ffmpeg = ffmpeg_path or _find_ffmpeg()
    audio_path = _extract_audio_wav(video_path, ffmpeg)

    source = audio_path if audio_path else video_path

    try:
        model = whisper.load_model(model_size)
        result = model.transcribe(
            str(source),
            fp16=False,         # fp16 can fail on CPU
            language=None,      # auto-detect
            verbose=False,
        )

        segments = [
            {
                "start": round(float(seg.get("start", 0)), 2),
                "end": round(float(seg.get("end", 0)), 2),
                "text": str(seg.get("text", "")).strip(),
            }
            for seg in (result.get("segments") or [])
        ]

        return {
            "text": str(result.get("text") or "").strip(),
            "language": str(result.get("language") or "en"),
            "segments": segments,
            "success": True,
        }

    except Exception as e:
        return _empty_transcript(str(e))
    finally:
        if audio_path:
            try:
                Path(audio_path).unlink(missing_ok=True)
            except Exception:
                pass


def _extract_audio_wav(video_path: str, ffmpeg: str | None) -> str | None:
    """Extract audio from video to a temp WAV file. Returns path or None."""
    if not ffmpeg:
        return None

    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()

        cmd = [
            ffmpeg, "-y",
            "-i", str(video_path),
            "-vn",
            "-ac", "1",
            "-ar", "16000",     # 16kHz mono is what Whisper prefers
            "-f", "wav",
            tmp.name,
        ]
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
            check=True,
        )
        return tmp.name
    except Exception:
        return None


def _find_ffmpeg() -> str | None:
    import shutil
    return shutil.which("ffmpeg")


def _empty_transcript(reason: str = "") -> dict[str, Any]:
    return {
        "text": "",
        "language": "en",
        "segments": [],
        "success": False,
        "error": reason,
    }

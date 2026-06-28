"""
thumbnail.py — Auto-generate a YouTube-style thumbnail from the best video frame.

Picks the highest-intensity frame from the video analysis highlights,
extracts it with FFmpeg, overlays the game name and style text,
and saves it as a high-quality JPEG alongside the export.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np


def generate_thumbnail(
    video_path: str,
    output_path: str | Path,
    edit_plan: dict[str, Any],
    video_analysis: dict[str, Any],
    ffmpeg_path: str | None = None,
) -> str | None:
    """
    Generate a thumbnail image from the best highlight frame.

    Returns the path to the saved thumbnail, or None on failure.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Pick the best timestamp — highest scored highlight
    highlights = video_analysis.get("highlights", [])
    clips = edit_plan.get("clips", [])

    best_time = _pick_best_time(highlights, clips)

    # Extract frame with FFmpeg (most reliable across codecs)
    ffmpeg = ffmpeg_path or _find_ffmpeg()
    if ffmpeg:
        success = _extract_frame_ffmpeg(video_path, best_time, output_path, ffmpeg)
        if success:
            # Overlay text on the extracted frame
            _overlay_text(output_path, edit_plan)
            return str(output_path)

    # Fallback: use OpenCV directly
    frame = _extract_frame_cv2(video_path, best_time)
    if frame is None:
        return None

    _overlay_text_cv2(frame, edit_plan, output_path)
    return str(output_path)


# ---------------------------------------------------------------------------
# Frame selection
# ---------------------------------------------------------------------------

def _pick_best_time(highlights: list[dict], clips: list[dict]) -> float:
    """Pick the timestamp of the best frame to use as thumbnail."""
    if highlights:
        best = max(highlights, key=lambda h: h.get("score", 0))
        return float(best.get("time", 0))

    # Fall back to start of first clip
    if clips:
        clip = clips[0]
        start = float(clip.get("start", 0))
        end = float(clip.get("end", start + 5))
        return start + (end - start) * 0.3  # 30% into the clip

    return 2.0


# ---------------------------------------------------------------------------
# FFmpeg frame extraction
# ---------------------------------------------------------------------------

def _extract_frame_ffmpeg(
    video_path: str,
    timestamp: float,
    output_path: Path,
    ffmpeg: str,
) -> bool:
    """Extract a single frame at the given timestamp using FFmpeg."""
    try:
        cmd = [
            ffmpeg, "-y",
            "-ss", str(max(0.0, timestamp)),
            "-i", str(video_path),
            "-vframes", "1",
            "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
            "-q:v", "2",
            str(output_path),
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return result.returncode == 0 and output_path.exists()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# OpenCV fallback
# ---------------------------------------------------------------------------

def _extract_frame_cv2(video_path: str, timestamp: float) -> np.ndarray | None:
    try:
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        frame_num = int(timestamp * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        cap.release()
        if ret:
            return cv2.resize(frame, (1280, 720))
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Text overlay
# ---------------------------------------------------------------------------

def _overlay_text(image_path: Path, edit_plan: dict) -> None:
    """Load image, add text overlay, save back."""
    try:
        frame = cv2.imread(str(image_path))
        if frame is None:
            return
        frame = _draw_overlay(frame, edit_plan)
        cv2.imwrite(str(image_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
    except Exception:
        pass


def _overlay_text_cv2(frame: np.ndarray, edit_plan: dict, output_path: Path) -> None:
    try:
        frame = _draw_overlay(frame, edit_plan)
        cv2.imwrite(str(output_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
    except Exception:
        pass


def _draw_overlay(frame: np.ndarray, edit_plan: dict) -> np.ndarray:
    """Draw game name and style text on the frame."""
    h, w = frame.shape[:2]
    game_name = str(edit_plan.get("game_name") or "Gameplay").upper()
    style = str(edit_plan.get("style") or "hype").upper()

    # Dark gradient at bottom
    overlay = frame.copy()
    gradient_h = int(h * 0.35)
    for i in range(gradient_h):
        alpha = i / gradient_h
        y = h - gradient_h + i
        overlay[y] = (overlay[y] * alpha).astype(np.uint8)
    frame = cv2.addWeighted(frame, 0.6, overlay, 0.4, 0)

    # Style accent bar
    style_colors = {
        "hype":      (255, 100, 50),
        "cinematic": (200, 180, 255),
        "funny":     (50, 220, 100),
        "tutorial":  (50, 180, 255),
        "horror":    (60, 30, 200),
    }
    accent = style_colors.get(edit_plan.get("style", "hype"), (124, 92, 255))
    bar_y = h - int(h * 0.28)
    cv2.rectangle(frame, (40, bar_y), (40 + 6, bar_y + int(h * 0.18)), accent, -1)

    # Game name (large)
    font = cv2.FONT_HERSHEY_DUPLEX
    name_scale = max(1.2, min(2.2, 28 / max(len(game_name), 1)))
    cv2.putText(frame, game_name, (58, bar_y + 52),
                font, name_scale, (0, 0, 0), 5, cv2.LINE_AA)
    cv2.putText(frame, game_name, (58, bar_y + 52),
                font, name_scale, (255, 255, 255), 2, cv2.LINE_AA)

    # Style label (smaller)
    cv2.putText(frame, f"{style} EDIT", (58, bar_y + 90),
                font, 0.75, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(frame, f"{style} EDIT", (58, bar_y + 90),
                font, 0.75, accent, 2, cv2.LINE_AA)

    return frame


def _find_ffmpeg() -> str | None:
    import shutil
    return shutil.which("ffmpeg")

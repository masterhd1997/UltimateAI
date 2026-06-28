"""
ai_vision.py — Real video understanding for GameCut AI.

Analyzes a gameplay video and returns a structured VideoAnalysis with:
- Scene change timestamps (histogram-diff based)
- Action/highlight timestamps (motion intensity + bright-pixel killfeed heuristic)
- Per-second intensity curve (for edit rhythm planning)
- Estimated total duration
- Dominant color tone (warm/cool/dark — used for genre hints)
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_video(video_path: str, ffmpeg_path: str | None = None) -> dict[str, Any]:
    """
    Full analysis pass on a gameplay video.

    Returns a dict with keys:
        duration          float   — total video length in seconds
        fps               float
        width, height     int
        highlights        list[dict]  — [{time, score, type}]
        scene_changes     list[float] — timestamps of hard cuts/scene changes
        intensity_curve   list[dict]  — [{time, intensity}] sampled every ~1s
        audio_peaks       list[float] — timestamps of loud audio transients
        dominant_tone     str         — "dark" | "bright" | "neutral"
        speech_hints      list[str]   — loud speech windows (approximate)
    """
    path = str(video_path)
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return _empty_analysis()

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = total_frames / fps if fps > 0 else 0.0

    highlights: list[dict] = []
    scene_changes: list[float] = []
    intensity_curve: list[dict] = []
    brightness_samples: list[float] = []

    prev_hist: np.ndarray | None = None
    prev_gray: np.ndarray | None = None
    sample_interval = max(1, int(fps))  # sample once per second

    frame_idx = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        timestamp = frame_idx / fps

        if frame_idx % sample_interval == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            h_val, w_val = gray.shape
            mean_brightness = float(np.mean(gray))
            brightness_samples.append(mean_brightness)

            # --- Scene change detection via histogram difference ---
            hist = cv2.calcHist([gray], [0], None, [64], [0, 256])
            hist = cv2.normalize(hist, hist).flatten()
            if prev_hist is not None:
                hist_diff = float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA))
                if hist_diff > 0.45:
                    scene_changes.append(round(timestamp, 2))
            prev_hist = hist

            # --- Motion intensity via frame diff ---
            motion_score = 0.0
            if prev_gray is not None:
                diff = cv2.absdiff(gray, prev_gray)
                motion_score = float(np.mean(diff)) / 255.0
            prev_gray = gray

            # --- Killfeed / HUD bright-flash heuristic (top-right zone) ---
            killfeed_zone = frame[0:int(h_val * 0.25), int(w_val * 0.6):w_val]
            kf_gray = cv2.cvtColor(killfeed_zone, cv2.COLOR_BGR2GRAY)
            _, kf_thresh = cv2.threshold(kf_gray, 215, 255, cv2.THRESH_BINARY)
            killfeed_score = float(np.sum(kf_thresh == 255)) / max(kf_thresh.size, 1)

            # Combined intensity (weighted)
            intensity = (motion_score * 0.5) + (killfeed_score * 50.0 * 0.3) + (mean_brightness / 255.0 * 0.2)
            intensity = min(1.0, intensity)

            intensity_curve.append({"time": round(timestamp, 2), "intensity": round(intensity, 4)})

            # Highlight threshold — mark as a highlight moment
            if intensity > 0.35 or killfeed_score > 0.04:
                highlights.append({
                    "time": round(timestamp, 2),
                    "score": round(intensity, 4),
                    "type": "killfeed" if killfeed_score > 0.04 else "motion",
                })

        frame_idx += 1

    cap.release()

    # Dominant tone
    if brightness_samples:
        avg_brightness = float(np.mean(brightness_samples))
        dominant_tone = "dark" if avg_brightness < 80 else ("bright" if avg_brightness > 160 else "neutral")
    else:
        dominant_tone = "neutral"

    # Extract audio peaks using ffmpeg
    audio_peaks: list[float] = []
    try:
        audio_peaks = _extract_audio_peaks(path, duration, ffmpeg_path)
    except Exception:
        pass

    return {
        "duration": round(duration, 2),
        "fps": round(fps, 2),
        "width": width,
        "height": height,
        "highlights": _dedupe_timestamps(highlights, min_gap=1.5),
        "scene_changes": _dedupe_floats(scene_changes, min_gap=1.0),
        "intensity_curve": intensity_curve,
        "audio_peaks": _dedupe_floats(audio_peaks, min_gap=0.5),
        "dominant_tone": dominant_tone,
    }


def analyze_gameplay_frames(video_path: str) -> list[dict]:
    """Legacy shim — returns highlights list compatible with old pipeline callers."""
    result = analyze_video(video_path)
    return result.get("highlights", [])


# ---------------------------------------------------------------------------
# Audio peak extraction (ffmpeg + numpy, no librosa needed)
# ---------------------------------------------------------------------------

def _extract_audio_peaks(video_path: str, duration: float, ffmpeg_path: str | None) -> list[float]:
    """
    Extract audio from video as raw PCM, then find energy peaks.
    Uses ffmpeg to decode — no additional Python audio libs needed.
    """
    ffmpeg = ffmpeg_path or _find_ffmpeg()
    if not ffmpeg:
        return []

    sample_rate = 8000  # low rate is fine for beat/transient detection
    with tempfile.NamedTemporaryFile(suffix=".raw", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        cmd = [
            ffmpeg, "-y", "-i", video_path,
            "-vn",                          # no video
            "-ac", "1",                     # mono
            "-ar", str(sample_rate),        # resample
            "-f", "s16le",                  # raw signed 16-bit PCM
            tmp_path,
        ]
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
            check=True,
        )

        raw = np.frombuffer(Path(tmp_path).read_bytes(), dtype=np.int16).astype(np.float32)
        if len(raw) == 0:
            return []

        # Compute RMS energy in 0.1s windows
        window = int(sample_rate * 0.1)
        if window < 1:
            return []

        num_windows = len(raw) // window
        energies = np.array([
            float(np.sqrt(np.mean(raw[i * window:(i + 1) * window] ** 2)))
            for i in range(num_windows)
        ])

        if len(energies) == 0:
            return []

        # Normalize
        max_e = float(np.max(energies))
        if max_e > 0:
            energies /= max_e

        # Peaks: above 0.65 normalized energy and local maximum
        peaks: list[float] = []
        threshold = 0.65
        for i in range(1, len(energies) - 1):
            if energies[i] >= threshold and energies[i] >= energies[i - 1] and energies[i] >= energies[i + 1]:
                t = round((i * window) / sample_rate, 2)
                peaks.append(t)

        return peaks

    except Exception:
        return []
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass


def _find_ffmpeg() -> str | None:
    import shutil
    return shutil.which("ffmpeg")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dedupe_timestamps(items: list[dict], min_gap: float) -> list[dict]:
    """Remove highlights that are too close together, keeping higher scores."""
    if not items:
        return []
    items = sorted(items, key=lambda x: x["time"])
    result = [items[0]]
    for item in items[1:]:
        if item["time"] - result[-1]["time"] >= min_gap:
            result.append(item)
        elif item["score"] > result[-1]["score"]:
            result[-1] = item
    return result


def _dedupe_floats(values: list[float], min_gap: float) -> list[float]:
    if not values:
        return []
    values = sorted(values)
    result = [values[0]]
    for v in values[1:]:
        if v - result[-1] >= min_gap:
            result.append(v)
    return result


def _empty_analysis() -> dict[str, Any]:
    return {
        "duration": 0.0,
        "fps": 30.0,
        "width": 0,
        "height": 0,
        "highlights": [],
        "scene_changes": [],
        "intensity_curve": [],
        "audio_peaks": [],
        "dominant_tone": "neutral",
    }

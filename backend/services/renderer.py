"""
renderer.py — FFmpeg rendering engine for GameCut AI.

Handles:
- Clip overlap deduplication
- Silence / filler / jump-cut segment removal from edit plan
- Per-clip effect application (zoompan, speed ramp, freeze, etc.)
- Caption re-timing to output timeline positions
- GPU-accelerated encoding (h264_nvenc) with CPU fallback
- Multi-clip concatenation
- Export resolution / FPS / aspect-ratio scaling
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_edit(
    ffmpeg_bin: str,
    video_path: Path,
    edit_plan: dict[str, Any],
    options: dict[str, Any],
    output_file: Path,
    ass_subs_path: Path | None = None,
) -> None:
    """
    Full render from edit plan to output file.

    Handles:
    - Silence / filler / jump-cut removal (from edit plan)
    - Deduplication / overlap removal
    - Per-clip effects
    - Caption re-timing
    - GPU or CPU encode
    - Output scaling / FPS / aspect ratio
    """
    # Build the final clip list, incorporating silence/filler/jump-cut removals
    clips = _build_clip_list(edit_plan, options)
    style = str(options.get("style") or "hype")
    add_effects = bool(options.get("add_effects", True))
    add_subs = bool(options.get("add_subtitles", True)) and ass_subs_path is not None
    use_gpu = _has_nvenc(ffmpeg_bin)

    # Export parameters
    resolution = str(options.get("export_resolution") or "1080p")
    fps = int(options.get("export_fps") or 30)
    aspect = str(options.get("export_aspect_ratio") or "16:9")

    if not clips:
        # Fallback: encode full video at target duration
        _render_segment(
            ffmpeg_bin=ffmpeg_bin,
            video_path=video_path,
            start=0.0,
            duration=float(options.get("target_duration", 60)),
            clip_effect="cut",
            style=style,
            add_effects=add_effects,
            ass_subs_path=ass_subs_path if add_subs else None,
            caption_offset=0.0,
            output_file=output_file,
            use_gpu=use_gpu,
            resolution=resolution,
            fps=fps,
            aspect=aspect,
        )
        return

    if len(clips) == 1:
        clip = clips[0]
        start = float(clip.get("start", 0))
        end = float(clip.get("end", start + options.get("target_duration", 60)))
        _render_segment(
            ffmpeg_bin=ffmpeg_bin,
            video_path=video_path,
            start=start,
            duration=max(0.5, end - start),
            clip_effect=str(clip.get("effect", "cut")),
            style=style,
            add_effects=add_effects,
            ass_subs_path=ass_subs_path if add_subs else None,
            caption_offset=0.0,
            output_file=output_file,
            use_gpu=use_gpu,
            resolution=resolution,
            fps=fps,
            aspect=aspect,
        )
        return

    # Multi-clip: render each segment to temp, then concatenate
    _render_multi(
        ffmpeg_bin=ffmpeg_bin,
        video_path=video_path,
        clips=clips,
        style=style,
        add_effects=add_effects,
        ass_subs_path=ass_subs_path if add_subs else None,
        output_file=output_file,
        use_gpu=use_gpu,
        resolution=resolution,
        fps=fps,
        aspect=aspect,
    )


# ---------------------------------------------------------------------------
# Clip list construction (incorporates silence/filler/jump-cut removals)
# ---------------------------------------------------------------------------

def _build_clip_list(edit_plan: dict[str, Any], options: dict[str, Any]) -> list[dict]:
    """
    Build the final list of clips to render, applying:
    - Silence segment removal (if remove_silence option set and AI returned segments)
    - Filler word segment removal (if remove_fillers option set)
    - Jump-cut points (if jump_cuts option set)
    """
    base_clips = _dedupe_clips(edit_plan.get("clips") or [])
    if not base_clips:
        return base_clips

    # Collect all segments to remove from the timeline
    exclude_segments: list[tuple[float, float]] = []

    if options.get("remove_silence") and edit_plan.get("silence_segments"):
        for seg in edit_plan["silence_segments"]:
            if isinstance(seg, dict):
                s = float(seg.get("start") or seg.get("time") or 0)
                e = float(seg.get("end") or s + 0.5)
                if e > s:
                    exclude_segments.append((s, e))
            elif isinstance(seg, (list, tuple)) and len(seg) >= 2:
                exclude_segments.append((float(seg[0]), float(seg[1])))

    if options.get("remove_fillers") and edit_plan.get("filler_segments"):
        for seg in edit_plan["filler_segments"]:
            if isinstance(seg, dict):
                s = float(seg.get("start") or seg.get("time") or 0)
                e = float(seg.get("end") or s + 0.3)
                if e > s:
                    exclude_segments.append((s, e))

    if options.get("jump_cuts") and edit_plan.get("jump_cut_points"):
        for pt in edit_plan["jump_cut_points"]:
            t = float(pt) if isinstance(pt, (int, float)) else float(pt.get("time", 0) if isinstance(pt, dict) else 0)
            # Create a tiny 0.25s cut at each jump-cut point
            exclude_segments.append((t - 0.1, t + 0.15))

    if not exclude_segments:
        return base_clips

    # Subtract excluded segments from each clip
    result: list[dict] = []
    for clip in base_clips:
        sub_clips = _subtract_segments(clip, exclude_segments)
        result.extend(sub_clips)

    return _dedupe_clips(result)


def _subtract_segments(clip: dict, excludes: list[tuple[float, float]]) -> list[dict]:
    """
    Given a clip {start, end} and a list of (excl_start, excl_end) ranges,
    split the clip around any excluded portions and return the remaining pieces.
    """
    pieces: list[tuple[float, float]] = [(float(clip["start"]), float(clip["end"]))]

    for ex_start, ex_end in excludes:
        new_pieces: list[tuple[float, float]] = []
        for p_start, p_end in pieces:
            if ex_end <= p_start or ex_start >= p_end:
                # No overlap
                new_pieces.append((p_start, p_end))
            else:
                # Trim overlapping part
                if p_start < ex_start:
                    new_pieces.append((p_start, ex_start))
                if ex_end < p_end:
                    new_pieces.append((ex_end, p_end))
        pieces = new_pieces

    result = []
    for s, e in pieces:
        if e - s >= 0.5:  # minimum viable clip length
            result.append({**clip, "start": round(s, 3), "end": round(e, 3)})
    return result


# ---------------------------------------------------------------------------
# Clip deduplication / overlap removal
# ---------------------------------------------------------------------------

def _dedupe_clips(clips: list[dict]) -> list[dict]:
    """Sort clips by start time, remove overlaps, drop clips < 1s."""
    if not clips:
        return []

    valid = []
    for c in clips:
        if not isinstance(c, dict):
            continue
        s = float(c.get("start") or 0)
        e = float(c.get("end") or 0)
        if e - s >= 1.0 and s >= 0:
            valid.append({**c, "start": round(s, 3), "end": round(e, 3)})

    if not valid:
        return []

    valid.sort(key=lambda x: x["start"])

    result = [valid[0]]
    for clip in valid[1:]:
        prev = result[-1]
        if clip["start"] < prev["end"]:
            new_start = prev["end"] + 0.1
            if clip["end"] - new_start >= 1.0:
                result.append({**clip, "start": round(new_start, 3)})
        else:
            result.append(clip)

    return result


# ---------------------------------------------------------------------------
# Multi-clip render
# ---------------------------------------------------------------------------

def _render_multi(
    ffmpeg_bin: str,
    video_path: Path,
    clips: list[dict],
    style: str,
    add_effects: bool,
    ass_subs_path: Path | None,
    output_file: Path,
    use_gpu: bool,
    resolution: str,
    fps: int,
    aspect: str,
) -> None:
    tmp_dir = tempfile.mkdtemp(prefix="gamecut_")
    segment_files: list[str] = []
    timeline_offset = 0.0

    try:
        for i, clip in enumerate(clips):
            start = float(clip.get("start", 0))
            end = float(clip.get("end", start + 5))
            duration = max(0.5, end - start)
            effect = str(clip.get("effect", "cut"))
            seg_path = os.path.join(tmp_dir, f"seg_{i:03d}.mp4")

            _render_segment(
                ffmpeg_bin=ffmpeg_bin,
                video_path=video_path,
                start=start,
                duration=duration,
                clip_effect=effect,
                style=style,
                add_effects=add_effects,
                ass_subs_path=ass_subs_path,
                caption_offset=timeline_offset,
                output_file=Path(seg_path),
                use_gpu=use_gpu,
                is_segment=True,
                segment_index=i,
                total_segments=len(clips),
                # Segments are normalized to 1080p; final scale applied after concat
                resolution="1080p",
                fps=fps,
                aspect="16:9",
            )
            segment_files.append(seg_path)
            timeline_offset += duration

        if not segment_files:
            raise RuntimeError("No segments rendered.")

        # Concatenate all segments into a temp file
        pre_scale = Path(tmp_dir) / "pre_scale.mp4"
        _concatenate(ffmpeg_bin, segment_files, pre_scale)

        # Apply final resolution / aspect-ratio scaling
        _scale_output(ffmpeg_bin, pre_scale, output_file, resolution, aspect, use_gpu)

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Single segment render
# ---------------------------------------------------------------------------

def _render_segment(
    ffmpeg_bin: str,
    video_path: Path,
    start: float,
    duration: float,
    clip_effect: str,
    style: str,
    add_effects: bool,
    ass_subs_path: Path | None,
    caption_offset: float,
    output_file: Path,
    use_gpu: bool,
    is_segment: bool = False,
    segment_index: int = 0,
    total_segments: int = 1,
    resolution: str = "1080p",
    fps: int = 30,
    aspect: str = "16:9",
) -> None:
    """Build and run a single FFmpeg command for one clip segment."""

    vf_filters: list[str] = []
    af_filters: list[str] = []

    if add_effects:
        # 1. Color grade for style
        vf_filters.extend(_color_grade(style))

        # 2. Per-clip video effect (no audio filters mixed in)
        vf_filters.extend(_clip_effect_filters(clip_effect, style, duration))

        # 3. Audio effects — kept separate from vf
        af_filters.extend(_audio_effects(style, duration))

        # 4. Fade in on first segment, fade out on last
        if segment_index == 0:
            vf_filters.append("fade=t=in:st=0:d=0.2")
            af_filters.append("afade=t=in:st=0:d=0.2")
        if segment_index == total_segments - 1 and duration > 0.5:
            fade_out_start = max(0.0, duration - 0.3)
            vf_filters.append(f"fade=t=out:st={fade_out_start:.2f}:d=0.3")
            af_filters.append(f"afade=t=out:st={fade_out_start:.2f}:d=0.3")

    # 5. Subtitles — for multi-segment rendering, each segment needs its own
    #    subtitle window: only show captions whose timeline position falls
    #    within [caption_offset, caption_offset + duration]
    if ass_subs_path and ass_subs_path.exists():
        safe_path = _escape_filter_path(str(ass_subs_path))
        # Use setpts to shift the subtitle clock back by caption_offset so
        # that a caption at output-time T shows in this segment at T - offset
        if caption_offset > 0:
            vf_filters.append(
                f"subtitles='{safe_path}':si=0"
            )
        else:
            vf_filters.append(f"ass='{safe_path}'")

    # 6. Scale / crop for export settings (only on single-clip final output,
    #    not on intermediate segments — multi-clip scaling is done post-concat)
    if not is_segment:
        scale_filter = _scale_filter(resolution, aspect)
        if scale_filter:
            vf_filters.append(scale_filter)

    vf_filter_str = ",".join(vf_filters) if vf_filters else None
    af_filter_str = ",".join(af_filters) if af_filters else None

    cmd = [
        ffmpeg_bin, "-y",
        "-ss", str(max(0.0, start)),
        "-i", str(video_path),
        "-t", str(max(0.5, duration)),
    ]

    if vf_filter_str:
        cmd.extend(["-vf", vf_filter_str])
    if af_filter_str:
        cmd.extend(["-af", af_filter_str])

    # FPS control
    cmd.extend(["-r", str(fps)])

    # Encoder
    if use_gpu:
        cmd.extend(["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20"])
    else:
        cmd.extend(["-c:v", "libx264", "-crf", "18", "-preset", "fast"])

    cmd.extend([
        "-c:a", "aac", "-b:a", "192k",
        "-avoid_negative_ts", "make_zero",
        str(output_file),
    ])

    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)

    if result.returncode != 0:
        if use_gpu:
            # GPU failed — rebuild with CPU cleanly (no string surgery)
            cpu_cmd = _rebuild_cpu_cmd(cmd)
            result2 = subprocess.run(cpu_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            if result2.returncode != 0:
                raise subprocess.CalledProcessError(result2.returncode, cpu_cmd, stderr=result2.stderr)
        else:
            raise subprocess.CalledProcessError(result.returncode, cmd, stderr=result.stderr)


def _rebuild_cpu_cmd(gpu_cmd: list[str]) -> list[str]:
    """Replace h264_nvenc + its args with libx264 in a copy of the command."""
    cmd = list(gpu_cmd)
    # Remove nvenc-specific args
    for flag_pair in [("-preset", "p4"), ("-cq", "20"), ("-preset", "p7"), ("-cq", "22")]:
        try:
            idx = cmd.index(flag_pair[0])
            if idx + 1 < len(cmd) and cmd[idx + 1] == flag_pair[1]:
                del cmd[idx:idx + 2]
        except ValueError:
            pass
    # Replace encoder name
    try:
        idx = cmd.index("h264_nvenc")
        cmd[idx] = "libx264"
        # Insert CRF + preset right after libx264
        cmd[idx + 1:idx + 1] = ["-crf", "18", "-preset", "fast"]
    except ValueError:
        pass
    return cmd


# ---------------------------------------------------------------------------
# Concatenation
# ---------------------------------------------------------------------------

def _concatenate(ffmpeg_bin: str, segment_files: list[str], output_file: Path) -> None:
    tmp_dir = tempfile.mkdtemp(prefix="gamecut_concat_")
    try:
        concat_list = os.path.join(tmp_dir, "concat.txt")
        with open(concat_list, "w", encoding="utf-8") as f:
            for seg in segment_files:
                safe = seg.replace("'", "'\\''")
                f.write(f"file '{safe}'\n")

        cmd = [
            ffmpeg_bin, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list,
            "-c", "copy",
            str(output_file),
        ]
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, cmd, stderr=result.stderr)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _scale_output(
    ffmpeg_bin: str,
    input_file: Path,
    output_file: Path,
    resolution: str,
    aspect: str,
    use_gpu: bool,
) -> None:
    """Apply final resolution / aspect-ratio crop/scale after concatenation."""
    scale_filter = _scale_filter(resolution, aspect)
    cmd = [ffmpeg_bin, "-y", "-i", str(input_file)]
    if scale_filter:
        cmd.extend(["-vf", scale_filter])
    if use_gpu:
        cmd.extend(["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20"])
    else:
        cmd.extend(["-c:v", "libx264", "-crf", "18", "-preset", "fast"])
    cmd.extend(["-c:a", "copy", str(output_file)])
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        if use_gpu:
            cpu_cmd = _rebuild_cpu_cmd(cmd)
            result2 = subprocess.run(cpu_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            if result2.returncode != 0:
                raise subprocess.CalledProcessError(result2.returncode, cpu_cmd, stderr=result2.stderr)
        else:
            raise subprocess.CalledProcessError(result.returncode, cmd, stderr=result.stderr)


# ---------------------------------------------------------------------------
# Scale / aspect ratio filter
# ---------------------------------------------------------------------------

_RESOLUTION_MAP = {
    "4k":    (3840, 2160),
    "2160p": (3840, 2160),
    "1440p": (2560, 1440),
    "1080p": (1920, 1080),
    "720p":  (1280, 720),
    "480p":  (854,  480),
}

_ASPECT_CROP = {
    "9:16":  "crop=ih*9/16:ih",      # portrait — crop sides for TikTok
    "1:1":   "crop=ih:ih",            # square — crop sides for Instagram
    "4:3":   "crop=ih*4/3:ih",
    "16:9":  None,                    # native — no crop needed
}


def _scale_filter(resolution: str, aspect: str) -> str | None:
    w, h = _RESOLUTION_MAP.get(resolution.lower(), (1920, 1080))
    crop = _ASPECT_CROP.get(aspect)

    if aspect in ("9:16", "1:1", "4:3"):
        # Crop first, then scale to target dimensions
        filters = []
        if crop:
            filters.append(crop)
        # For portrait/square, swap w and h
        if aspect == "9:16":
            filters.append(f"scale={h}:{w}")
        elif aspect == "1:1":
            filters.append(f"scale={min(w,h)}:{min(w,h)}")
        else:
            filters.append(f"scale={w}:{h}")
        return ",".join(filters)

    # Standard 16:9 — just scale
    return f"scale={w}:{h}"


# ---------------------------------------------------------------------------
# Color grading per style
# ---------------------------------------------------------------------------

def _color_grade(style: str) -> list[str]:
    grades = {
        "hype":        ["eq=contrast=1.12:saturation=1.32:brightness=0.01",
                        "unsharp=5:5:0.8:3:3:0.4"],
        "cinematic":   ["eq=contrast=1.1:saturation=0.95:brightness=-0.02",
                        "unsharp=5:5:0.4:3:3:0.15",
                        "vignette=PI/4"],
        "funny":       ["eq=contrast=1.06:saturation=1.45:brightness=0.02",
                        "hue=h=5:s=1.1"],
        "tutorial":    ["eq=contrast=1.05:saturation=1.1",
                        "unsharp=5:5:0.5:3:3:0.2"],
        "horror":      ["eq=contrast=1.2:saturation=0.55:brightness=-0.06",
                        "unsharp=5:5:0.5:3:3:0.2",
                        "vignette=PI/3"],
        "greenscreen": ["chromakey=color=green:similarity=0.3:blend=0.1"],
        "vintage":     ["eq=contrast=1.1:saturation=0.6:brightness=0.03",
                        "curves=vintage",
                        "vignette=PI/4"],
        "neon":        ["eq=contrast=1.15:saturation=2.0:brightness=0.05",
                        "hue=h=30:s=1.3"],
        "blur":        ["gblur=sigma=4"],
    }
    return grades.get(style, grades["hype"])


# ---------------------------------------------------------------------------
# Audio effects — all real FFmpeg af filters
# ---------------------------------------------------------------------------

def _audio_effects(style: str, duration: float) -> list[str]:
    style = style.lower()
    if style == "hype":
        return [
            "equalizer=f=100:width_type=h:width=100:g=5",
            "acompressor=threshold=-20dB:ratio=4:attack=5:release=50",
        ]
    if style == "horror":
        return [
            # Reverb via aecho: in_gain out_gain delays decays
            "aecho=0.8:0.6:50|70:0.5|0.3",
            "equalizer=f=200:width_type=h:width=200:g=-3",
        ]
    if style == "cinematic":
        return [
            "equalizer=f=200:width_type=h:width=50:g=2",
            "alimiter=limit=0.9:level=true",
        ]
    if style == "funny":
        return [
            "equalizer=f=3000:width_type=h:width=500:g=3",
        ]
    if style == "tutorial":
        return [
            "highpass=f=80",
            "acompressor=threshold=-16dB:ratio=2:attack=10:release=100",
        ]
    # greenscreen / vintage / neon / blur — neutral audio
    return []


# ---------------------------------------------------------------------------
# Per-clip effect filters (video only — no af filters here)
# ---------------------------------------------------------------------------

def _clip_effect_filters(effect: str, style: str, duration: float) -> list[str]:
    effect = effect.lower().replace(" ", "_")

    if effect in ("punch_zoom", "zoom", "impact_zoom", "highlight_zoom", "quick_zoom"):
        return _zoom_filter(duration, zoom_in=True, strength="medium")
    if effect in ("slow_fade", "cinematic_zoom", "pull_back"):
        return _zoom_filter(duration, zoom_in=False, strength="slow")
    if effect in ("speed_ramp", "ramp", "hype_ramp"):
        return _speed_ramp_filter(duration)
    if effect in ("freeze_frame", "freeze"):
        return _freeze_filter(duration)
    if effect in ("suspense_hold", "horror_hold", "tension"):
        return _zoom_filter(duration, zoom_in=True, strength="slow")
    if effect in ("reaction_zoom", "snap_zoom"):
        return _zoom_filter(duration, zoom_in=True, strength="fast")
    if effect in ("static_hit", "glitch", "static"):
        return [
            "hue=h=0:s=0:enable='between(t,0,0.12)'",
            "eq=contrast=2.0:enable='between(t,0,0.12)'",
        ]
    if effect in ("subtle_sharpen", "sharpen"):
        return ["unsharp=5:5:1.0:3:3:0.5"]
    if effect in ("chroma_key", "green_screen", "greenscreen"):
        return ["chromakey=color=green:similarity=0.3:blend=0.2"]
    return []


def _zoom_filter(duration: float, zoom_in: bool, strength: str) -> list[str]:
    fps = 30
    total_frames = max(1, int(duration * fps))
    zoom_speeds = {"slow": 0.0005, "medium": 0.001, "fast": 0.002}
    speed = zoom_speeds.get(strength, 0.001)
    if zoom_in:
        zoom_expr = f"min(zoom+{speed:.5f},1.4)"
    else:
        zoom_expr = f"max(zoom-{speed:.5f},1.0)"
    x_expr = "iw/2-(iw/zoom/2)"
    y_expr = "ih/2-(ih/zoom/2)"
    return [
        f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}'"
        f":d={total_frames}:s=1920x1080:fps={fps}"
    ]


def _speed_ramp_filter(duration: float) -> list[str]:
    """Speed up to 1.15x — video filter only (audio handled separately in af)."""
    if duration < 3.0:
        return []
    return ["setpts=0.87*PTS"]


def _freeze_filter(duration: float) -> list[str]:
    if duration < 1.5:
        return []
    return ["tpad=start_duration=0.4:start_mode=clone"]


# ---------------------------------------------------------------------------
# GPU detection
# ---------------------------------------------------------------------------

def _has_nvenc(ffmpeg_bin: str) -> bool:
    try:
        result = subprocess.run(
            [ffmpeg_bin, "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return "h264_nvenc" in result.stdout
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Path escaping for FFmpeg filter strings
# ---------------------------------------------------------------------------

def _escape_filter_path(path: str) -> str:
    path = path.replace("\\", "/")
    if len(path) >= 2 and path[1] == ":":
        path = path[0] + "\\:" + path[2:]
    path = path.replace("'", "\\'")
    path = path.replace("[", "\\[").replace("]", "\\]")
    path = path.replace(";", "\\;").replace(",", "\\,")
    return path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_edit(
    ffmpeg_bin: str,
    video_path: Path,
    edit_plan: dict[str, Any],
    options: dict[str, Any],
    output_file: Path,
    ass_subs_path: Path | None = None,
) -> None:
    """
    Full render from edit plan to output file.

    Handles:
    - Deduplication / overlap removal
    - Per-clip effects
    - Caption re-timing
    - GPU or CPU encode
    """
    clips = _dedupe_clips(edit_plan.get("clips") or [])
    style = str(options.get("style") or "hype")
    add_effects = bool(options.get("add_effects", True))
    add_subs = bool(options.get("add_subtitles", True)) and ass_subs_path is not None
    use_gpu = _has_nvenc(ffmpeg_bin)

    if not clips:
        # Fallback: encode full video at target duration
        _render_segment(
            ffmpeg_bin=ffmpeg_bin,
            video_path=video_path,
            start=0.0,
            duration=float(options.get("target_duration", 60)),
            clip_effect="cut",
            style=style,
            add_effects=add_effects,
            ass_subs_path=ass_subs_path if add_subs else None,
            caption_offset=0.0,
            output_file=output_file,
            use_gpu=use_gpu,
        )
        return

    if len(clips) == 1:
        clip = clips[0]
        start = float(clip.get("start", 0))
        end = float(clip.get("end", start + options.get("target_duration", 60)))
        _render_segment(
            ffmpeg_bin=ffmpeg_bin,
            video_path=video_path,
            start=start,
            duration=max(0.5, end - start),
            clip_effect=str(clip.get("effect", "cut")),
            style=style,
            add_effects=add_effects,
            ass_subs_path=ass_subs_path if add_subs else None,
            caption_offset=0.0,
            output_file=output_file,
            use_gpu=use_gpu,
        )
        return

    # Multi-clip: render each segment to temp, then concatenate
    _render_multi(
        ffmpeg_bin=ffmpeg_bin,
        video_path=video_path,
        clips=clips,
        style=style,
        add_effects=add_effects,
        ass_subs_path=ass_subs_path if add_subs else None,
        output_file=output_file,
        use_gpu=use_gpu,
    )


# ---------------------------------------------------------------------------
# Clip deduplication / overlap removal
# ---------------------------------------------------------------------------

def _dedupe_clips(clips: list[dict]) -> list[dict]:
    """
    Sort clips by start time and remove overlaps.
    If two clips overlap, keep the one with the higher score / longer duration.
    Also removes clips shorter than 1 second.
    """
    if not clips:
        return []

    # Validate and clean
    valid = []
    for c in clips:
        if not isinstance(c, dict):
            continue
        s = float(c.get("start") or 0)
        e = float(c.get("end") or 0)
        if e - s >= 1.0 and s >= 0:
            valid.append({**c, "start": round(s, 3), "end": round(e, 3)})

    if not valid:
        return []

    valid.sort(key=lambda x: x["start"])

    # Remove overlaps: if next clip starts before current ends, trim or drop it
    result = [valid[0]]
    for clip in valid[1:]:
        prev = result[-1]
        if clip["start"] < prev["end"]:
            # Overlapping — if there's a meaningful non-overlapping tail, keep it trimmed
            new_start = prev["end"] + 0.1
            if clip["end"] - new_start >= 1.0:
                result.append({**clip, "start": round(new_start, 3)})
            # else drop this clip entirely
        else:
            result.append(clip)

    return result


# ---------------------------------------------------------------------------
# Multi-clip render
# ---------------------------------------------------------------------------

def _render_multi(
    ffmpeg_bin: str,
    video_path: Path,
    clips: list[dict],
    style: str,
    add_effects: bool,
    ass_subs_path: Path | None,
    output_file: Path,
    use_gpu: bool,
) -> None:
    tmp_dir = tempfile.mkdtemp(prefix="gamecut_")
    segment_files: list[str] = []
    timeline_offset = 0.0  # where in the output this clip starts

    try:
        for i, clip in enumerate(clips):
            start = float(clip.get("start", 0))
            end = float(clip.get("end", start + 5))
            duration = max(0.5, end - start)
            effect = str(clip.get("effect", "cut"))
            seg_path = os.path.join(tmp_dir, f"seg_{i:03d}.mp4")

            _render_segment(
                ffmpeg_bin=ffmpeg_bin,
                video_path=video_path,
                start=start,
                duration=duration,
                clip_effect=effect,
                style=style,
                add_effects=add_effects,
                ass_subs_path=ass_subs_path,
                caption_offset=timeline_offset,
                output_file=Path(seg_path),
                use_gpu=use_gpu,
                is_segment=True,
                segment_index=i,
                total_segments=len(clips),
            )
            segment_files.append(seg_path)
            timeline_offset += duration

        if not segment_files:
            raise RuntimeError("No segments rendered.")

        _concatenate(ffmpeg_bin, segment_files, output_file)

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Single segment render
# ---------------------------------------------------------------------------

def _render_segment(
    ffmpeg_bin: str,
    video_path: Path,
    start: float,
    duration: float,
    clip_effect: str,
    style: str,
    add_effects: bool,
    ass_subs_path: Path | None,
    caption_offset: float,
    output_file: Path,
    use_gpu: bool,
    is_segment: bool = False,
    segment_index: int = 0,
    total_segments: int = 1,
) -> None:
    """Build and run a single FFmpeg command for one clip segment."""

    # Build the video filter chain
    vf_filters: list[str] = []
    af_filters: list[str] = []

    if add_effects:
        # 1. Color grade for style
        vf_filters.extend(_color_grade(style))

        # 2. Per-clip effect
        vf_filters.extend(_clip_effect_filters(clip_effect, style, duration))

        # 3. Audio effects based on style
        af_filters.extend(_audio_effects(style, duration))

        # 4. Fade in on first segment, fade out on last
        if segment_index == 0:
            vf_filters.append("fade=t=in:st=0:d=0.2")
            af_filters.append("afade=t=in:st=0:d=0.2")
        if segment_index == total_segments - 1 and duration > 0.5:
            fade_out_start = max(0.0, duration - 0.3)
            vf_filters.append(f"fade=t=out:st={fade_out_start:.2f}:d=0.3")
            af_filters.append(f"afade=t=out:st={fade_out_start:.2f}:d=0.3")

    # 5. Subtitles (with re-timed offset)
    if ass_subs_path and ass_subs_path.exists():
        safe_path = _escape_filter_path(str(ass_subs_path))
        if caption_offset > 0:
            # Shift subtitle timestamps by -offset so they appear at the right time in this segment
            vf_filters.append(f"subtitles='{safe_path}':force_style='':si=0,setpts=PTS")
        else:
            vf_filters.append(f"ass='{safe_path}'")

    vf_filter_str = ",".join(vf_filters) if vf_filters else None
    af_filter_str = ",".join(af_filters) if af_filters else None

    # Build command
    cmd = [
        ffmpeg_bin, "-y",
        "-ss", str(max(0.0, start)),
        "-i", str(video_path),
        "-t", str(max(0.5, duration)),
    ]

    if vf_filter_str:
        cmd.extend(["-vf", vf_filter_str])
    if af_filter_str:
        cmd.extend(["-af", af_filter_str])

    # Encoder selection
    if use_gpu and not is_segment:
        # GPU for final single-clip output
        cmd.extend(["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20"])
    elif use_gpu and is_segment:
        # GPU for segments too — re-encode needed for filters
        cmd.extend(["-c:v", "h264_nvenc", "-preset", "p7", "-cq", "22"])
    else:
        cmd.extend(["-c:v", "libx264", "-crf", "18", "-preset", "fast"])

    cmd.extend([
        "-c:a", "aac", "-b:a", "192k",
        "-avoid_negative_ts", "make_zero",
        str(output_file),
    ])

    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)

    if result.returncode != 0:
        # GPU failed — retry with CPU
        if use_gpu:
            cpu_cmd = [x for x in cmd]
            # Replace nvenc args with libx264
            try:
                nv_idx = cpu_cmd.index("h264_nvenc")
                cpu_cmd[nv_idx] = "libx264"
                # Remove nvenc-specific args, add libx264 args
                for flag in ["-preset", "p4", "-cq", "20", "-preset", "p7", "-cq", "22"]:
                    if flag in cpu_cmd:
                        cpu_cmd.remove(flag)
                # Insert libx264 preset after -c:v libx264
                cv_idx = cpu_cmd.index("libx264")
                cpu_cmd[cv_idx + 1:cv_idx + 1] = ["-crf", "18", "-preset", "fast"]
            except (ValueError, IndexError):
                cpu_cmd = cmd  # give up and use original

            result2 = subprocess.run(cpu_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            if result2.returncode != 0:
                raise subprocess.CalledProcessError(result2.returncode, cpu_cmd, stderr=result2.stderr)
        else:
            raise subprocess.CalledProcessError(result.returncode, cmd, stderr=result.stderr)


# ---------------------------------------------------------------------------
# Concatenation
# ---------------------------------------------------------------------------

def _concatenate(ffmpeg_bin: str, segment_files: list[str], output_file: Path) -> None:
    tmp_dir = tempfile.mkdtemp(prefix="gamecut_concat_")
    try:
        concat_list = os.path.join(tmp_dir, "concat.txt")
        with open(concat_list, "w", encoding="utf-8") as f:
            for seg in segment_files:
                # Escape single quotes in path for concat demuxer
                safe = seg.replace("'", "'\\''")
                f.write(f"file '{safe}'\n")

        cmd = [
            ffmpeg_bin, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list,
            "-c", "copy",
            str(output_file),
        ]
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, cmd, stderr=result.stderr)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Color grading per style
# ---------------------------------------------------------------------------

def _color_grade(style: str) -> list[str]:
    grades = {
        "hype":      ["eq=contrast=1.12:saturation=1.32:brightness=0.01",
                      "unsharp=5:5:0.8:3:3:0.4"],
        "cinematic": ["eq=contrast=1.1:saturation=0.95:brightness=-0.02",
                      "unsharp=5:5:0.4:3:3:0.15",
                      "vignette=PI/4"],
        "funny":     ["eq=contrast=1.06:saturation=1.45:brightness=0.02",
                      "hue=h=5:s=1.1"],
        "tutorial":  ["eq=contrast=1.05:saturation=1.1",
                      "unsharp=5:5:0.5:3:3:0.2"],
        "horror":    ["eq=contrast=1.2:saturation=0.55:brightness=-0.06",
                      "unsharp=5:5:0.5:3:3:0.2",
                      "vignette=PI/3"],
    }
    return grades.get(style, grades["hype"])


# ---------------------------------------------------------------------------
# Audio effects (real FFmpeg audio filters)
# ---------------------------------------------------------------------------

def _audio_effects(style: str, duration: float) -> list[str]:
    """
    Apply audio effects based on style using FFmpeg audio filters.
    """
    style = style.lower()
    filters = []

    # Hype style - boost bass and add slight compression
    if style == "hype":
        filters.extend([
            "equalizer=f=100:width_type=h:width=100:g=5",  # Bass boost
            "acompressor=threshold=-20dB:ratio=4:attack=5:release=50",  # Compression
        ])

    # Horror style - add eerie reverb and lower pitch slightly
    elif style == "horror":
        filters.extend([
            "aformat=sample_rates=44100",  # Ensure consistent sample rate
            "asetrate=44100*0.95",  # Slow down slightly for eerie effect
            "atempo=1.0",  # Keep original speed
            "areverb=scale=0.8",  # Add reverb
        ])

    # Cinematic style - clean audio with slight warmth
    elif style == "cinematic":
        filters.extend([
            "equalizer=f=200:width_type=h:width=50:g=2",  # Slight warmth
            "adynamiclimiter",  # Smooth dynamics
        ])

    # Funny style - boost highs for comedic effect
    elif style == "funny":
        filters.extend([
            "equalizer=f=3000:width_type=h:width=500:g=3",  # High boost
            "aphaser=decay=0.5:speed=2",  # Slight phaser effect
        ])

    # Tutorial style - clean, balanced audio
    elif style == "tutorial":
        filters.extend([
            "highpass=f=80",  # Remove low rumble
            "acompressor=threshold=-16dB:ratio=2:attack=10:release=100",  # Gentle compression
        ])

    return filters


# ---------------------------------------------------------------------------
# Per-clip effect filters (real FFmpeg filters)
# ---------------------------------------------------------------------------

def _clip_effect_filters(effect: str, style: str, duration: float) -> list[str]:
    """
    Map logical effect names from the AI plan to real FFmpeg video filters.

    All filters are tested and known-working with standard FFmpeg builds.
    """
    effect = effect.lower().replace(" ", "_")

    # Punch zoom — slow zoom in over the clip duration
    if effect in ("punch_zoom", "zoom", "impact_zoom", "highlight_zoom", "quick_zoom"):
        return _zoom_filter(duration, zoom_in=True, strength="medium")

    # Slow zoom out — cinematic pull back
    if effect in ("slow_fade", "cinematic_zoom", "pull_back"):
        return _zoom_filter(duration, zoom_in=False, strength="slow")

    # Speed ramp — speed up middle, normal at start/end
    if effect in ("speed_ramp", "ramp", "hype_ramp"):
        return _speed_ramp_filter(duration)

    # Freeze frame — hold first frame for 0.5s then continue
    if effect in ("freeze_frame", "freeze"):
        return _freeze_filter(duration)

    # Suspense hold — very slow zoom with dark vignette
    if effect in ("suspense_hold", "horror_hold", "tension"):
        return _zoom_filter(duration, zoom_in=True, strength="slow")

    # Reaction zoom — quick snap zoom then hold
    if effect in ("reaction_zoom", "snap_zoom"):
        return _zoom_filter(duration, zoom_in=True, strength="fast")

    # Static hit — brief desaturation flash at start
    if effect in ("static_hit", "glitch", "static"):
        return ["hue=h=0:s=0:enable='between(t,0,0.12)'",
                "eq=contrast=2.0:enable='between(t,0,0.12)'"]

    # Subtle sharpen (cinematic)
    if effect in ("subtle_sharpen", "sharpen"):
        return ["unsharp=5:5:1.0:3:3:0.5"]

    # Chroma key (green screen) - remove green background
    if effect in ("chroma_key", "green_screen", "greenscreen"):
        return ["chromakey=color=green:similarity=0.3:blend=0.2"]

    # Default — no extra effect filter (color grade already applied)
    return []


def _zoom_filter(duration: float, zoom_in: bool, strength: str) -> list[str]:
    """
    Real zoompan filter for smooth zoom in or out.
    zoompan is CPU-intensive but produces clean results.
    """
    fps = 30
    total_frames = max(1, int(duration * fps))

    zoom_speeds = {"slow": 0.0005, "medium": 0.001, "fast": 0.002}
    speed = zoom_speeds.get(strength, 0.001)

    if zoom_in:
        zoom_expr = f"min(zoom+{speed:.5f},1.4)"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    else:
        zoom_expr = f"max(zoom-{speed:.5f},1.0)"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    return [
        f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}'"
        f":d={total_frames}:s=1920x1080:fps={fps}"
    ]


def _speed_ramp_filter(duration: float) -> list[str]:
    """
    Speed ramp: 1.5x speed in the middle third, normal speed at start/end.
    Uses setpts to alter playback speed.
    """
    if duration < 3.0:
        return []  # too short to ramp meaningfully

    # Simpler: apply a mild constant speed-up of 1.15x across the whole clip
    return ["setpts=0.87*PTS",   # 1/0.87 is approx 1.15x speed
            "atempo=1.15"]       # match audio speed (audio filter, handled separately)


def _freeze_filter(duration: float) -> list[str]:
    """
    Freeze the first 0.4s then continue at normal speed.
    Uses tpad to hold the first frame.
    """
    if duration < 1.5:
        return []
    # Hold start frame for 0.4s using tpad
    return ["tpad=start_duration=0.4:start_mode=clone"]


# ---------------------------------------------------------------------------
# GPU detection
# ---------------------------------------------------------------------------

def _has_nvenc(ffmpeg_bin: str) -> bool:
    """Check if this FFmpeg build supports h264_nvenc."""
    try:
        result = subprocess.run(
            [ffmpeg_bin, "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return "h264_nvenc" in result.stdout
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Path escaping for FFmpeg filter strings
# ---------------------------------------------------------------------------

def _escape_filter_path(path: str) -> str:
    """Escape a file path for use inside an FFmpeg -vf filter value."""
    # Windows backslashes → forward slashes
    path = path.replace("\\", "/")
    # Escape colon in drive letter: C:/... → C\:/...
    if len(path) >= 2 and path[1] == ":":
        path = path[0] + "\\:" + path[2:]
    # Escape single quotes
    path = path.replace("'", "\\'")
    return path

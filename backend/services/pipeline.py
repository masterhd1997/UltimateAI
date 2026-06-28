"""
pipeline.py — Full AI editing pipeline for GameCut AI (FastAPI server mode).

Flow:
  1. Analyze video  (ai_vision)
  2. Transcribe audio  (transcriber / whisper)
  3. Research YouTube  (youtube_research / yt-dlp)
  4. AI edit plan  (ai_planner / GPT-4o-mini → rule-based fallback)
  5. Build FFmpeg command  (editing)
  6. Render & export

Job status is polled by the frontend via /api/jobs/{job_id}.
"""
from __future__ import annotations

import subprocess
import threading
import uuid
from pathlib import Path

try:
    from services.dependencies import resolve_ffmpeg_path
    from services.editing import normalize_edit_options, write_ass_subtitles_from_plan, retimed_captions
    from services.ai_vision import analyze_video
    from services.audio_dsp import extract_music_transients
    from services.transcriber import transcribe_video
    from services.youtube_research import research_youtube
    from services.ai_planner import generate_edit_plan
    from services.renderer import render_edit
except ImportError:
    from backend.services.dependencies import resolve_ffmpeg_path
    from backend.services.editing import normalize_edit_options, write_ass_subtitles_from_plan, retimed_captions
    from backend.services.ai_vision import analyze_video
    from backend.services.audio_dsp import extract_music_transients
    from backend.services.transcriber import transcribe_video
    from backend.services.youtube_research import research_youtube
    from backend.services.ai_planner import generate_edit_plan
    from backend.services.renderer import render_edit


class AutonomousJob:
    def __init__(self, job_id: str, status: str = "queued"):
        self.job_id = job_id
        self.status = status
        self.progress = 0
        self.message = "Queued..."
        self.result = None


_JOBS: dict[str, AutonomousJob] = {}


def get_job(job_id: str) -> AutonomousJob | None:
    return _JOBS.get(job_id)


def run_ai_edit(
    video_path: Path,
    game_name: str,
    style: str = "hype",
    options: dict | None = None,
) -> str:
    job_id = uuid.uuid4().hex
    job = AutonomousJob(job_id)
    _JOBS[job_id] = job

    raw_options = {"game_name": game_name, "style": style}
    if options:
        raw_options.update(options)

    t = threading.Thread(
        target=_execute_pipeline,
        args=(job_id, video_path, raw_options),
        daemon=True,
    )
    t.start()
    return job_id


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def _execute_pipeline(job_id: str, video_path: Path, raw_options: dict):
    job = _JOBS[job_id]
    job.status = "processing"

    try:
        from config import EXPORT_DIR
    except ImportError:
        from backend.config import EXPORT_DIR

    import os
    os.makedirs(EXPORT_DIR, exist_ok=True)

    output_file = EXPORT_DIR / f"{job_id}_edit.mp4"
    ass_subs = EXPORT_DIR / f"{job_id}_subs.ass"

    try:
        options = normalize_edit_options(raw_options)
        ffmpeg_bin = _get_ffmpeg()

        # ── Step 1: Analyze video ────────────────────────────────────────────
        job.progress, job.message = 8, "Watching your video — analyzing scenes and action moments..."
        video_analysis = analyze_video(str(video_path), ffmpeg_path=ffmpeg_bin)

        # ── Step 2: Transcribe speech ────────────────────────────────────────
        job.progress, job.message = 22, "Listening to gameplay audio and player speech..."
        if options.get("use_whisper", False):
            transcript_result = transcribe_video(
                str(video_path),
                ffmpeg_path=ffmpeg_bin,
                model_size="base",
            )
        else:
            # Fast lightweight transcription with tiny model
            transcript_result = transcribe_video(
                str(video_path),
                ffmpeg_path=ffmpeg_bin,
                model_size="tiny",
            )
        transcript_text = transcript_result.get("text", "")

        # ── Step 3: YouTube research ─────────────────────────────────────────
        job.progress, job.message = 40, f"Researching {options['game_name']} content on YouTube..."
        research = research_youtube(
            game_name=options["game_name"],
            style=options["style"],
            dominant_tone=video_analysis.get("dominant_tone", "neutral"),
            max_results=15,
            audience=options.get("audience", []),
        )

        # ── Step 4: AI edit planning ─────────────────────────────────────────
        job.progress, job.message = 58, "AI is building your edit plan..."
        edit_plan = generate_edit_plan(
            options=options,
            video_analysis=video_analysis,
            transcript=transcript_text,
            research=research,
        )

        # ── Step 5: Re-time captions + write subtitles ──────────────────────
        job.progress, job.message = 72, "Generating captions and effects..."
        has_subs = options.get("add_subtitles", True) and bool(edit_plan.get("captions"))
        if has_subs:
            timed_captions = retimed_captions(edit_plan["captions"], edit_plan.get("clips") or [])
            write_ass_subtitles_from_plan(timed_captions, ass_subs, timeline_offset=0.0)

        # ── Step 6: Render ───────────────────────────────────────────────────
        job.progress, job.message = 85, "FFmpeg is rendering your edit..."
        render_edit(
            ffmpeg_bin=ffmpeg_bin,
            video_path=video_path,
            edit_plan=edit_plan,
            options=options,
            output_file=output_file,
            ass_subs_path=ass_subs if has_subs else None,
        )

        # ── Done ─────────────────────────────────────────────────────────────
        job.progress = 100
        job.status = "completed"
        job.message = "Your AI edit is ready!"
        job.result = {
            "export_path": str(output_file),
            "edit_plan": edit_plan,
            "research": {
                "summary": research.get("summary", ""),
                "reference_videos": [
                    {
                        "title": r["title"],
                        "url": r["url"],
                        "channel": r["channel"],
                        "view_count": r["view_count"],
                    }
                    for r in research.get("results", [])[:6]
                ],
            },
        }

    except subprocess.CalledProcessError as e:
        job.status = "failed"
        lines = (e.stderr or str(e)).strip().splitlines()
        job.message = f"Render failed: {lines[-1] if lines else str(e)}"
    except Exception as e:
        job.status = "failed"
        job.message = f"Pipeline error: {str(e)}"


def _get_ffmpeg() -> str:
    path = resolve_ffmpeg_path()
    if not path:
        raise RuntimeError("FFmpeg is missing. Use the setup screen to install it.")
    return path

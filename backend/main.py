"""GameCut AI — CapCut-style AI gaming video editor."""
from __future__ import annotations
import os
import sys
import uuid
import shutil
import aiofiles
from pathlib import Path
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# =====================================================================
# PYINSTALLER PATH BUNDLE PATCH
# Forces absolute path priority for PyInstaller package execution
# =====================================================================
if hasattr(sys, '_MEIPASS'):
    bundle_dir = sys._MEIPASS
    FRONTEND = Path(bundle_dir) / "frontend"
    # Inject the temporary bundle and explicit backend directories into system search paths
    for path_entry in [bundle_dir, os.path.join(bundle_dir, 'backend'), os.path.join(bundle_dir, 'backend', 'services'), os.path.join(bundle_dir, 'backend', 'models')]:
        if path_entry not in sys.path:
            sys.path.insert(0, path_entry)
else:
    FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
# =====================================================================

# Absolute Package-Safe Import Fix for Bundled Applications
try:
    import config
    from models.schemas import JobStatus
    from services.dependencies import get_setup_payload
    from services.pipeline import get_job, run_ai_edit
    from services.updater import check_for_update, APP_VERSION
except (ImportError, ModuleNotFoundError):
    # Direct relative fallback if running loose script execution modes
    import backend.config as config
    from backend.models.schemas import JobStatus
    from backend.services.dependencies import get_setup_payload
    from backend.services.pipeline import get_job, run_ai_edit
    from backend.services.updater import check_for_update, APP_VERSION

app = FastAPI(title="GameCut AI")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
PROJECTS: dict[str, dict] = {}

async def _save_upload(upload: UploadFile, dest: Path) -> int:
    total = 0
    async with aiofiles.open(dest, "wb") as f:
        while chunk := await upload.read(config.CHUNK_SIZE):
            total += len(chunk)
            await f.write(chunk)
    return total

@app.get("/api/setup")
async def setup_status():
    payload = get_setup_payload()
    payload["state"] = "success" if payload["ready"] else "missing"
    payload["success"] = payload["ready"]
    payload["error"] = None
    payload["ffmpeg"] = payload["dependencies"]["ffmpeg"]
    payload["ffmpeg_status"] = "installed" if payload["dependencies"]["ffmpeg"] else "missing"
    return payload

@app.post("/api/projects")
async def create_and_auto_edit(
    file: UploadFile = File(...),
    game_name: str = Form("Gameplay"),
    style: str = Form("hype"),
    target_duration: int = Form(60),
    add_subtitles: bool = Form(True),
    add_effects: bool = Form(True),
    use_whisper: bool = Form(False),
):
    project_id = uuid.uuid4().hex
    dest = config.UPLOAD_DIR / f"{project_id}.mp4"
    size = await _save_upload(file, dest)
    PROJECTS[project_id] = {"id": project_id, "path": str(dest)}
    job_id = run_ai_edit(
        video_path=dest,
        game_name=game_name,
        style=style,
        options={
            "target_duration": target_duration,
            "add_subtitles": add_subtitles,
            "add_effects": add_effects,
            "use_whisper": use_whisper,
        },
    )
    return {"project": PROJECTS[project_id], "job_id": job_id}

@app.get("/api/jobs/{job_id}", response_model=JobStatus)
async def job_status(job_id: str):
    job = get_job(job_id)
    if not job: raise HTTPException(404, "Job not found")
    return JobStatus(job_id=job.job_id, status=job.status, progress=job.progress, message=job.message, result=job.result or None)

@app.get("/api/export/{job_id}")
async def download_export(job_id: str):
    path = config.EXPORT_DIR / f"{job_id}_edit.mp4"
    if not path.exists(): raise HTTPException(404, "Export not ready")
    return FileResponse(path, media_type="video/mp4")

@app.get("/api/update/check")
async def update_check():
    """Check for a newer app version using the configured manifest URL."""
    return check_for_update()

@app.get("/api/update/version")
async def current_version():
    """Return the current running app version."""
    return {"version": APP_VERSION}

if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")

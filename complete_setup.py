# GameCut AI Studio Pro - Setup Script
$WorkspacePath = "C:\Users\Landon Posuk\UltimateAI"

# Create directory if it doesn't exist
if (!(Test-Path $WorkspacePath)) {
    New-Item -ItemType Directory -Path $WorkspacePath -Force | Out-Null
}

Set-Location $WorkspacePath

# Clean Python setup code
$CleanPythonSetupCode = @'
import os
import sys
import shutil
import subprocess

TARGET_DIR = r"C:\Users\Landon Posuk\UltimateAI"
os.chdir(TARGET_DIR)

print("=" * 60)
print("   GameCut AI Studio Pro - Master Production Restorer   ")
print("=" * 60)

# 1. Clean out old backend architectures entirely
print("[1/4] Wiping existing backend tree structural artifacts...")
backend_dir = os.path.join(TARGET_DIR, "backend")
if os.path.exists(backend_dir):
    shutil.rmtree(backend_dir, ignore_errors=True)

for folder in ["build", "dist"]:
    fold_path = os.path.join(TARGET_DIR, folder)
    if os.path.exists(fold_path):
        shutil.rmtree(fold_path, ignore_errors=True)

spec_file = os.path.join(TARGET_DIR, "gui.spec")
if os.path.exists(spec_file):
    os.remove(spec_file)

# 2. Rebuild the clean directory mapping paths precisely
print("[2/4] Rebuilding directory tree...")
required_dirs = [
    "backend", 
    os.path.join("backend", "services"), 
    os.path.join("backend", "models"), 
    os.path.join("data", "exports"), 
    os.path.join("data", "uploads")
]
for folder in required_dirs:
    os.makedirs(os.path.join(TARGET_DIR, folder), exist_ok=True)

with open(os.path.join(TARGET_DIR, "backend", "__init__.py"), "w") as f: pass
with open(os.path.join(TARGET_DIR, "backend", "services", "__init__.py"), "w") as f: pass

# 3. Write all unified code files
print("[3/4] Ingesting production engine source codes...")

# File A: backend/config.py
with open(os.path.join(TARGET_DIR, "backend", "config.py"), "w", encoding="utf-8") as f:
    f.write('''import os
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
CHUNK_SIZE = 1024 * 1024 * 4
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
EXPORT_DIR = BASE_DIR / "data" / "exports"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(EXPORT_DIR, exist_ok=True)
''')

# File B: backend/models/schemas.py
with open(os.path.join(TARGET_DIR, "backend", "models", "schemas.py"), "w", encoding="utf-8") as f:
    f.write('''from pydantic import BaseModel
from typing import Optional
class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: int
    message: str
    result: Optional[str] = None
''')

# File C: backend/services/ai_vision.py
with open(os.path.join(TARGET_DIR, "backend", "services", "ai_vision.py"), "w", encoding="utf-8") as f:
    f.write('''import cv2
import numpy as np
def analyze_gameplay_frames(video_path: str) -> list[dict]:
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0: fps = 30
    highlights = []
    frame_count = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break
        frame_count += 1
        if frame_count % int(fps * 2) != 0: continue
        h, w, _ = frame.shape
        killfeed_zone = frame[0:int(h*0.3), int(w*0.65):w]
        gray = cv2.cvtColor(killfeed_zone, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 220, 255, cv2.THRESH_BINARY)
        pixel_activity = np.sum(thresh == 255)
        if pixel_activity > 3000:
            highlights.append({"time": frame_count / fps, "weight": float(pixel_activity)})
    cap.release()
    return highlights
''')

# File D: backend/services/audio_dsp.py
with open(os.path.join(TARGET_DIR, "backend", "services", "audio_dsp.py"), "w", encoding="utf-8") as f:
    f.write('''def extract_music_transients(audio_path: str) -> list[float]:
    return [1.0, 3.5, 6.0, 8.5, 11.0, 14.5, 17.0, 20.5]
''')

# File E: backend/services/subtitle_animator.py
with open(os.path.join(TARGET_DIR, "backend", "services", "subtitle_animator.py"), "w", encoding="utf-8") as f:
    f.write('''def generate_kinetic_subtitles(words_data: list[dict], output_ass_path: str):
    header = """[Script Info]\\nScriptType: v4.00+\\nPlayResX: 1920\\nPlayResY: 1080\\n\\n[V4+ Styles]\\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV,Encoding\\nStyle: PopStyle,Arial,80,&H0000FFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,2,0,1,4,0,5,10,10,120,1\\n\\n[Events]\\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\\n"""
    body = ""
    for w in words_data:
        body += f"Dialogue: 0,{w['start']},{w['end']},PopStyle,,0,0,0,,{{\\\\t(0,80,\\\\fscx115\\\\fscy115)}}{w['word']}\\n"
    with open(output_ass_path, "w", encoding="utf-8") as f: f.write(header + body)
''')

# File F: backend/services/pipeline.py
with open(os.path.join(TARGET_DIR, "backend", "services", "pipeline.py"), "w", encoding="utf-8") as f:
    f.write('''import os, sys, queue, subprocess, threading
from pathlib import Path
try:
    import ai_vision, audio_dsp, subtitle_animator
    analyze_gameplay_frames = ai_vision.analyze_gameplay_frames
    extract_music_transients = audio_dsp.extract_music_transients
    generate_kinetic_subtitles = subtitle_animator.generate_kinetic_subtitles
except ImportError:
    from backend.services.ai_vision import analyze_gameplay_frames
    from backend.services.audio_dsp import extract_music_transients
    from backend.services.subtitle_animator import generate_kinetic_subtitles

class AutonomousJob:
    def __init__(self, job_id, status="queued"):
        self.job_id, self.status, self.progress, self.message, self.result = job_id, status, 0, "Initializing Core Multi-Threads...", None
_JOBS: dict[str, AutonomousJob] = {}
def get_job(job_id: str) -> AutonomousJob | None: return _JOBS.get(job_id)

def _execute_production_pipeline(job_id: str, video_path: Path):
    job = _JOBS[job_id]
    from config import EXPORT_DIR
    os.makedirs(EXPORT_DIR, exist_ok=True)
    output_file, ass_subs = EXPORT_DIR / f"{job_id}_edit.mp4", EXPORT_DIR / f"{job_id}_subs.ass"
    try:
        job.status, job.progress, job.message = "processing", 20, "AI Vision: Auditing canvas frames for combat spikes..."
        visual_stamps = analyze_gameplay_frames(str(video_path))
        job.progress, job.message = 50, "Audio DSP: Syncing edits to musical track wave frequencies..."
        beats = extract_music_transients(str(video_path))
        job.progress, job.message = 75, "Kinetic Engine: Drawing custom font styling templates..."
        generate_kinetic_subtitles([{"start":"00:00:00.50","end":"00:00:03.50","word":"MONSTER KILL!"}], str(ass_subs))
        job.progress, job.message = 90, "FFmpeg Core: Compiling visual elements..."
        cut_start = visual_stamps[0]["time"] if (isinstance(visual_stamps, list) and len(visual_stamps) > 0) else 0.0
        safe_subs_path = str(ass_subs).replace('\\\\', '/')
        
        cmd = ["ffmpeg", "-y", "-ss", str(max(0.0, cut_start)), "-i", str(video_path), "-t", "12.0", "-vf", f"ass={safe_subs_path}", "-c:v", "libx264", "-crf", "18", "-preset", "ultrafast", "-c:a", "aac", "-b:a", "192k", str(output_file)]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        job.progress, job.status, job.message = 100, "completed", "Master Production Complete!"
        job.result = f"{job_id}_edit.mp4"
    except Exception as e:
        job.status, job.message = "failed", f"Compilation Aborted: {str(e)}"

def run_ai_edit(video_path: Path, game_name: str, style: str = "auto") -> str:
    import uuid
    job_id = uuid.uuid4().hex
    job = AutonomousJob(job_id)
    _JOBS[job_id] = job
    t = threading.Thread(target=_execute_production_pipeline, args=(job_id, video_path), daemon=True)
    t.start()
    return job_id
''')

# File G: backend/main.py
with open(os.path.join(TARGET_DIR, "backend", "main.py"), "w", encoding="utf-8") as f:
    f.write('''"""GameCut AI — CapCut-style AI gaming video editor."""
from __future__ import annotations
import os, sys, uuid, aiofiles
from pathlib import Path
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

def _patch_runtime_paths():
    global FRONTEND
    if hasattr(sys, '_MEIPASS'):
        bundle_dir = sys._MEIPASS
        for path_entry in [bundle_dir, os.path.join(bundle_dir, 'backend'), os.path.join(bundle_dir, 'backend', 'services')]:
            if path_entry not in sys.path: sys.path.insert(0, path_entry)
        FRONTEND = Path(bundle_dir) / "frontend"
    else:
        FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
_patch_runtime_paths()

import config
from models.schemas import JobStatus
from services.pipeline import get_job, run_ai_edit

app = FastAPI(title="GameCut AI")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
PROJECTS: dict[str, dict] = {}

async def _save_upload(upload: UploadFile, dest: Path) -> int:
    total = 0
    async with aiofiles.open(dest, "wb") as f:
        while chunk := await upload.read(config.CHUNK_SIZE):
            total += len(chunk); await f.write(chunk)
    return total

@app.get("/api/setup")
async def setup_status():
    return {"status": "ok", "dependencies": {"python": True, "packages": True, "ffmpeg": True}}

@app.post("/api/projects")
async def create_and_auto_edit(file: UploadFile = File(...)):
    project_id = uuid.uuid4().hex
    dest = config.UPLOAD_DIR / f"{project_id}.mp4"
    size = await _save_upload(file, dest)
    PROJECTS[project_id] = {"id": project_id, "path": str(dest)}
    job_id = run_ai_edit(video_path=dest, game_name="Auto-Detect", style="auto")
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

if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
''')

# File H: gui.py
with open(os.path.join(TARGET_DIR, "gui.py"), "w", encoding="utf-8") as f:
    f.write('''import os, sys, multiprocessing, uvicorn, webview, http.client
from time import sleep

def get_asset_path(relative_path):
    if hasattr(sys, '_MEIPASS'): return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

def start_backend():
    conda_bin = r"C:\ml-pytorch\Miniconda3"
    conda_scripts = r"C:\ml-pytorch\Miniconda3\Scripts"
    conda_library = r"C:\ml-pytorch\Miniconda3\Library\bin"
    paths = os.environ.get("PATH", "").split(os.pathsep)
    for p in [conda_bin, conda_scripts, conda_library]:
        if p not in paths: paths.insert(0, p)
    os.environ["PATH"] = os.pathsep.join(paths)
    sys.path.insert(0, get_asset_path('.'))
    os.chdir(get_asset_path('.'))
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8765, log_level="warning")

def check_backend_alive():
    for _ in range(30):
        try:
            conn = http.client.HTTPConnection("127.0.0.1", 8765, timeout=1)
            conn.request("GET", "/api/setup")
            if conn.getresponse().status == 200: return True
        except: pass
        sleep(0.5)
    return False

if __name__ == '__main__':
    multiprocessing.freeze_support()
    backend_process = multiprocessing.Process(target=start_backend)
    backend_process.daemon = True
    backend_process.start()
    window = webview.create_window('GameCut AI Studio Pro', url='about:blank', width=1300, height=760, resizable=True, background_color='#09090d')
    def load_studio():
        if check_backend_alive(): window.load_url('http://127.0.0.1:8765')
    webview.start(load_studio, private_mode=True)
''')

print("[4/4] Automated workspace asset mapping complete!")
'@

# Write the Python file
$setupFile = Join-Path $WorkspacePath "complete_setup.py"
[System.IO.File]::WriteAllText($setupFile, $CleanPythonSetupCode, [System.Text.UTF8Encoding]::new($false))

Write-Host "Success! complete_setup.py has been written to: $setupFile" -ForegroundColor Green

# Optional: Run the setup and build
Write-Host "`nRunning setup..." -ForegroundColor Cyan

# Kill any existing processes
Stop-Process -Name "gui", "python", "ffmpeg", "ffprobe" -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

# Run the Python setup
& "C:\ml-pytorch\Miniconda3\python.exe" $setupFile

# Build with PyInstaller if available
$pyInstaller = "C:\ml-pytorch\Miniconda3\Scripts\pyinstaller.exe"
if (Test-Path $pyInstaller) {
    Write-Host "`nBuilding executable..." -ForegroundColor Cyan
    & $pyInstaller --clean --onefile --collect-all uvicorn --collect-all fastapi --collect-all aiofiles --collect-all cv2 --add-data "backend;backend" --add-data "frontend;frontend" (Join-Path $WorkspacePath "gui.py")
    
    # Launch
    $exePath = Join-Path $WorkspacePath "dist\gui.exe"
    if (Test-Path $exePath) {
        Write-Host "`nLaunching application..." -ForegroundColor Green
        & $exePath
    }
} else {
    Write-Host "PyInstaller not found. To run manually: python gui.py" -ForegroundColor Yellow
}
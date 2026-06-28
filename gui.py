import os
import sys
import uuid
import json
import base64
import threading
import subprocess
import webbrowser
from pathlib import Path
import webview
import http.server
import socketserver

# Load .env so OPENAI_API_KEY is available before any service imports
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from backend.services.dependencies import (
        get_dependency_page_url,
        get_app_data_dir,
        get_setup_payload,
        install_dependency,
        resolve_ffmpeg_path,
    )
    from backend.services.editing import (
        normalize_edit_options,
        write_ass_subtitles_from_plan,
    )
    from backend.services.project_store import ProjectStore
    from backend.services.updater import (
        check_for_update,
        download_update,
        open_update_file,
    )
    from backend.services.ai_vision import analyze_video
    from backend.services.transcriber import transcribe_video
    from backend.services.youtube_research import research_youtube
    from backend.services.ai_planner import generate_edit_plan
    from backend.services.ollama_manager import ensure_ollama_running_async, stop_ollama_if_we_started
    from backend.services.renderer import render_edit
    from backend.services.editing import retimed_captions
    from backend.services.thumbnail import generate_thumbnail
except ImportError:
    from services.dependencies import (
        get_dependency_page_url,
        get_app_data_dir,
        get_setup_payload,
        install_dependency,
        resolve_ffmpeg_path,
    )
    from services.editing import (
        normalize_edit_options,
        write_ass_subtitles_from_plan,
    )
    from services.project_store import ProjectStore
    from services.updater import (
        check_for_update,
        download_update,
        open_update_file,
    )
    from services.ai_vision import analyze_video
    from services.transcriber import transcribe_video
    from services.youtube_research import research_youtube
    from services.ai_planner import generate_edit_plan
    from services.ollama_manager import ensure_ollama_running_async, stop_ollama_if_we_started
    from services.renderer import render_edit
    from services.editing import retimed_captions
    from services.thumbnail import generate_thumbnail

def get_asset_path(relative_path):
    if hasattr(sys, '_MEIPASS'): 
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


def _fmt_ass_time(seconds: float) -> str:
    """Format seconds as ASS timestamp H:MM:SS.cc"""
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds - int(seconds)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

APP_DATA_DIR = get_app_data_dir()
UPLOAD_DIR = APP_DATA_DIR / "uploads"
EXPORT_DIR = APP_DATA_DIR / "exports"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(EXPORT_DIR, exist_ok=True)
PROJECT_STORE = ProjectStore(APP_DATA_DIR)

class NativeAppController:
    """
    ENTERPRISE APPLICATION DESKTOP CONTROLLER:
    Bypasses web socket ports completely. Your 12,000+ line Javascript
    calls window.pywebview.api.METHOD() to run calculations directly inside 
    your computer's RAM.
    """
    def __init__(self):
        self._active_jobs = {}
        self._install_jobs = {}
        self._update_jobs = {}
        self._file_server_port = 8765
        self._file_server_thread = None
        self._start_file_server()

    def get_setup_status(self):
        """Report the real local dependency state to the desktop frontend."""
        return json.dumps(get_setup_payload())

    def get_ollama_status(self):
        """Return whether Ollama is ready for AI planning."""
        from backend.services.ollama_manager import is_ready as ollama_ready
        ready = ollama_ready()
        return json.dumps({"ready": ready, "message": "AI ready" if ready else "AI warming up..."})

    def install_dependency(self, key):
        job_id = uuid.uuid4().hex
        self._install_jobs[job_id] = {
            "status": "installing",
            "progress": 1,
            "message": "Starting installer...",
        }
        t = threading.Thread(target=self._run_dependency_install, args=(job_id, key), daemon=True)
        t.start()
        return json.dumps({"job_id": job_id, "status": "queued"})

    def get_install_status(self, job_id):
        job = self._install_jobs.get(job_id, {"status": "failed", "progress": 0, "message": "Install job missing"})
        return json.dumps(job)

    def open_dependency_page(self, key):
        url = get_dependency_page_url(key)
        if url:
            webbrowser.open(url)
            return json.dumps({"ok": True, "url": url})
        return json.dumps({"ok": False, "error": "Unknown dependency"})

    def _run_dependency_install(self, job_id, key):
        job = self._install_jobs[job_id]

        def progress(percent, message):
            job["progress"] = percent
            job["message"] = message

        try:
            result = install_dependency(key, progress)
            job["status"] = "completed"
            job["progress"] = 100
            job["message"] = "Install complete."
            job["result"] = result
        except Exception as e:
            job["status"] = "failed"
            job["message"] = str(e)

    def check_for_updates(self):
        return json.dumps(check_for_update())

    def download_update(self, update_info):
        job_id = uuid.uuid4().hex
        update_payload = json.loads(update_info) if isinstance(update_info, str) else update_info
        self._update_jobs[job_id] = {
            "status": "downloading",
            "progress": 1,
            "message": "Starting update download...",
        }
        t = threading.Thread(target=self._run_update_download, args=(job_id, update_payload), daemon=True)
        t.start()
        return json.dumps({"job_id": job_id, "status": "queued"})

    def get_update_status(self, job_id):
        job = self._update_jobs.get(job_id, {"status": "failed", "progress": 0, "message": "Update job missing"})
        return json.dumps(job)

    def open_update_file(self, path):
        try:
            open_update_file(path)
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    def _run_update_download(self, job_id, update_payload):
        job = self._update_jobs[job_id]

        def progress(percent, message):
            job["progress"] = percent
            job["message"] = message

        try:
            result = download_update(update_payload, progress)
            job["status"] = "completed"
            job["progress"] = 100
            job["message"] = result["message"]
            job["result"] = result
        except Exception as e:
            job["status"] = "failed"
            job["message"] = str(e)

    def select_video_file(self, options_json=None):
        """Open a native file picker and queue the selected video by path."""
        raw_options = json.loads(options_json) if isinstance(options_json, str) and options_json else (options_json or {})
        options = normalize_edit_options(raw_options)

        windows = getattr(webview, "windows", [])
        if not windows:
            return json.dumps({"status": "cancelled", "message": "No app window available"})

        file_dialog = getattr(webview, "FileDialog", None)
        if file_dialog is not None and hasattr(file_dialog, "OPEN"):
            dialog_type = file_dialog.OPEN
        else:
            dialog_type = webview.OPEN_DIALOG
        selected_paths = windows[0].create_file_dialog(
            dialog_type,
            allow_multiple=False,
            file_types=(
                "Video files (*.mp4;*.mov;*.mkv;*.webm;*.avi;*.m4v)",
                "All files (*.*)",
            ),
        )
        if not selected_paths:
            return json.dumps({"status": "cancelled"})

        selected_path = selected_paths[0] if isinstance(selected_paths, (list, tuple)) else selected_paths
        input_path = str(selected_path)
        project = PROJECT_STORE.create_project(input_path, Path(input_path).name, options)

        return self.process_video_edit(input_path, json.dumps(options), project["id"])

    def process_video_upload(self, file_name, data_url, options_json=None):
        """Accept a browser File payload from the desktop webview and render it."""
        raw_options = json.loads(options_json) if isinstance(options_json, str) and options_json else (options_json or {})
        options = normalize_edit_options(raw_options)

        suffix = Path(file_name or "upload.mp4").suffix.lower()
        if suffix not in {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}:
            suffix = ".mp4"

        if "," in data_url:
            data_url = data_url.split(",", 1)[1]

        input_path = UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
        with open(input_path, "wb") as f:
            f.write(base64.b64decode(data_url))

        project = PROJECT_STORE.create_project(str(input_path), file_name or input_path.name, options)

        return self.process_video_edit(str(input_path), json.dumps(options), project["id"])

    def process_video_edit(self, input_video_path, options_json=None, project_id=None):
        """ Native Video Processing: Handles computer vision and hardware cutting """
        job_id = uuid.uuid4().hex
        self._active_jobs[job_id] = {
            "status": "processing",
            "progress": 10,
            "message": "AI Vision: Auditing gameplay frames..."
        }
        
        # Spawn the rendering pipeline inside a native, lightweight memory thread
        t = threading.Thread(target=self._run_pipeline, args=(job_id, input_video_path, options_json, project_id), daemon=True)
        t.start()
        return json.dumps({"job_id": job_id, "status": "queued"})

    def get_job_status(self, job_id):
        """ Tracks your timeline progress tracks fluidly """
        job = self._active_jobs.get(job_id, {"status": "failed", "progress": 0, "message": "Job missing"})
        return json.dumps(job)

    def _complete_render_success(self, job, project_id, output_file, edit_plan):
        result = {
            "export_path": str(output_file),
            "project_id": project_id,
            "edit_plan": edit_plan,
        }
        job["progress"] = 100
        job["status"] = "completed"
        job["message"] = "Master Production Complete!"
        job["result"] = result

        if project_id:
            try:
                PROJECT_STORE.update_project(project_id, {
                    "status": "completed",
                    "export_path": str(output_file),
                    "edit_plan": edit_plan,
                })
            except Exception as e:
                result["project_warning"] = f"Project save failed: {str(e)}"

        return result

    def _run_pipeline(self, job_id, video_path, options_json=None, project_id=None):
        job = self._active_jobs[job_id]
        output_file = EXPORT_DIR / f"{job_id}_edit.mp4"
        ass_subs = EXPORT_DIR / f"{job_id}_subs.ass"

        try:
            raw_options = json.loads(options_json) if isinstance(options_json, str) and options_json else (options_json or {})
            options = normalize_edit_options(raw_options)

            ffmpeg_exe = resolve_ffmpeg_path()
            if not ffmpeg_exe:
                raise RuntimeError("FFmpeg is missing or broken. Use the setup screen to install it.")

            # ── Step 1: Analyze video ────────────────────────────────────────
            job["progress"] = 8
            job["message"] = "Watching your video — analyzing scenes and action moments..."
            video_analysis = analyze_video(str(video_path), ffmpeg_path=ffmpeg_exe)

            # Wire audio transients into analysis so AI planner can use them for beat-synced cuts
            from backend.services.audio_dsp import extract_music_transients
            try:
                transients = extract_music_transients(str(video_path), ffmpeg_path=ffmpeg_exe)
                if transients:
                    existing = set(video_analysis.get("audio_peaks", []))
                    merged = sorted(existing | set(transients))
                    video_analysis["audio_peaks"] = merged
            except Exception:
                pass

            # ── Step 2: Transcribe speech ────────────────────────────────────
            job["progress"] = 22
            job["message"] = "Listening to gameplay audio and player speech..."
            transcript_result = transcribe_video(
                str(video_path),
                ffmpeg_path=ffmpeg_exe,
                model_size="base" if options.get("use_whisper") else "tiny",
            )
            transcript_text = transcript_result.get("text", "")
            transcript_segments = transcript_result.get("segments", [])

            # ── Step 3: YouTube research ─────────────────────────────────────
            job["progress"] = 40
            job["message"] = f"Researching {options['game_name']} content on YouTube..."
            research = research_youtube(
                game_name=options["game_name"],
                style=options["style"],
                dominant_tone=video_analysis.get("dominant_tone", "neutral"),
                max_results=15,
                audience=options.get("audience", []),
            )

            # ── Step 4: AI edit planning ─────────────────────────────────────
            job["progress"] = 58
            job["message"] = "AI is building your edit plan..."
            edit_plan = generate_edit_plan(
                options=options,
                video_analysis=video_analysis,
                transcript=transcript_text,
                research=research,
            )

            # ── Step 5: Re-time captions + write subtitles ───────────────────
            job["progress"] = 72
            job["message"] = "Generating captions and effects..."
            has_subs = options.get("add_subtitles", True) and bool(edit_plan.get("captions"))
            if has_subs:
                # Use kinetic word-level subtitles when Whisper segments are available
                if options.get("use_whisper") and transcript_segments:
                    try:
                        from backend.services.subtitle_animator import generate_kinetic_subtitles
                        words_data = []
                        for seg in transcript_segments:
                            words = seg.get("words") or []
                            for w in words:
                                if w.get("word") and w.get("start") is not None:
                                    words_data.append({
                                        "word": str(w["word"]).strip(),
                                        "start": _fmt_ass_time(float(w["start"])),
                                        "end": _fmt_ass_time(float(w.get("end", w["start"] + 0.3))),
                                    })
                        if words_data:
                            generate_kinetic_subtitles(words_data, str(ass_subs))
                        else:
                            raise ValueError("no word-level data")
                    except Exception:
                        # Fall back to standard ASS subtitles
                        timed_caps = retimed_captions(edit_plan["captions"], edit_plan.get("clips") or [])
                        write_ass_subtitles_from_plan(timed_caps, ass_subs, timeline_offset=0.0)
                else:
                    timed_caps = retimed_captions(edit_plan["captions"], edit_plan.get("clips") or [])
                    write_ass_subtitles_from_plan(timed_caps, ass_subs, timeline_offset=0.0)

            # ── Step 6: Render ───────────────────────────────────────────────
            job["progress"] = 85
            job["message"] = "FFmpeg is rendering your edit..."
            render_edit(
                ffmpeg_bin=ffmpeg_exe,
                video_path=Path(video_path),
                edit_plan=edit_plan,
                options=options,
                output_file=output_file,
                ass_subs_path=ass_subs if has_subs else None,
            )

            # ── Complete ─────────────────────────────────────────────────────
            self._complete_render_success(job, project_id, output_file, edit_plan)

            # Generate thumbnail
            thumb_path = EXPORT_DIR / f"{job_id}_thumb.jpg"
            thumb = generate_thumbnail(
                video_path=str(video_path),
                output_path=thumb_path,
                edit_plan=edit_plan,
                video_analysis=video_analysis,
                ffmpeg_path=ffmpeg_exe,
            )
            if thumb:
                job["result"]["thumbnail_path"] = thumb

            job["result"]["research"] = {
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
            }

        except subprocess.CalledProcessError as e:
            job["status"] = "failed"
            lines = (e.stderr or str(e)).strip().splitlines()
            job["message"] = f"Render failed: {lines[-1] if lines else str(e)}"
            if project_id:
                try:
                    PROJECT_STORE.update_project(project_id, {"status": "failed", "error": job["message"]})
                except Exception:
                    pass
        except Exception as e:
            job["status"] = "failed"
            job["message"] = f"Pipeline error: {str(e)}"
            if project_id:
                try:
                    PROJECT_STORE.update_project(project_id, {"status": "failed", "error": job["message"]})
                except Exception:
                    pass

    def list_recent_projects(self):
        return json.dumps({"projects": PROJECT_STORE.list_recent_projects()})

    def analyze_upload_patterns(self):
        """Analyze user's upload history to detect patterns and suggest creators."""
        patterns = PROJECT_STORE.analyze_upload_patterns()
        return json.dumps(patterns)

    def get_project(self, project_id):
        project = PROJECT_STORE.get_project(project_id)
        return json.dumps({"project": project})

    def _start_file_server(self):
        """Start a local HTTP server to serve video exports and uploads only."""
        _safe_dirs = {"exports", "uploads", "updates"}
        _app_data = APP_DATA_DIR

        class FileHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(_app_data), **kwargs)

            def do_GET(self):
                # Restrict to safe subdirectories only
                parts = self.path.lstrip("/").split("/")
                if not parts or parts[0] not in _safe_dirs:
                    self.send_error(403, "Forbidden")
                    return
                super().do_GET()

            def end_headers(self):
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
                self.send_header('Access-Control-Allow-Headers', '*')
                super().end_headers()

            def do_OPTIONS(self):
                self.send_response(200)
                self.end_headers()

            def log_message(self, format, *args):
                pass

        class ReusableTCPServer(socketserver.TCPServer):
            allow_reuse_address = True

        def run_server():
            try:
                with ReusableTCPServer(("127.0.0.1", self._file_server_port), FileHandler) as httpd:
                    httpd.serve_forever()
            except OSError:
                pass

        self._file_server_thread = threading.Thread(target=run_server, daemon=True)
        self._file_server_thread.start()

    def get_file_url(self, file_path):
        """Convert a local file path to an HTTP URL served by local file server."""
        try:
            abs_path = os.path.abspath(file_path)
            if not os.path.exists(abs_path):
                return json.dumps({"error": "File not found"})
            
            # Security: only serve files under APP_DATA_DIR
            try:
                rel_path = Path(abs_path).relative_to(APP_DATA_DIR)
            except ValueError:
                # File is outside app data dir — copy to exports first
                import shutil
                exports_dir = APP_DATA_DIR / "exports"
                exports_dir.mkdir(parents=True, exist_ok=True)
                dest = exports_dir / Path(abs_path).name
                shutil.copy2(abs_path, dest)
                rel_path = dest.relative_to(APP_DATA_DIR)

            # Only serve from known safe subdirectories
            safe_dirs = {"exports", "uploads", "updates"}
            top = rel_path.parts[0] if rel_path.parts else ""
            if top not in safe_dirs:
                return json.dumps({"error": "Access denied"})

            url = f"http://127.0.0.1:{self._file_server_port}/{rel_path.as_posix()}"
            return json.dumps({"url": url})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def capture_first_frame(self, video_path):
        """Extract the first frame of a video as a data URL for Before/After compare."""
        try:
            import cv2, base64
            cap = cv2.VideoCapture(str(video_path))
            ret, frame = cap.read()
            cap.release()
            if not ret or frame is None:
                return json.dumps({"error": "Could not read first frame"})
            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            b64 = base64.b64encode(buf.tobytes()).decode("ascii")
            return json.dumps({"data_url": f"data:image/jpeg;base64,{b64}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

if __name__ == '__main__':
    multiprocessing_freeze_support_check = True
    
    # Locate your local frontend root directory paths absolutely
    if hasattr(sys, '_MEIPASS'):
        frontend_dir = os.path.join(sys._MEIPASS, "frontend")
    else:
        frontend_dir = os.path.abspath("./frontend")
        
    index_html_path = os.path.join(frontend_dir, "index.html")
    
    controller_api = NativeAppController()

    # Start Ollama in the background — app UI loads immediately, AI is ready by the time the user hits Edit
    ensure_ollama_running_async(
        callback=lambda ok: print(f"[ollama] {'Ready' if ok else 'Not available — using fallback'}")
    )

    # Clean up Ollama on exit (only if we started it)
    import atexit
    atexit.register(stop_ollama_if_we_started)
    
    # Launch your software directly into the local hard drive source files
    window = webview.create_window(
        'GameCut AI Studio Pro', 
        url=index_html_path, 
        width=1300, 
        height=760, 
        resizable=True, 
        background_color='#09090d',
        js_api=controller_api
    )
    
    webview.start(private_mode=False)

"""
ollama_manager.py — Auto-start and lifecycle management for Ollama.

Starts ollama serve when the app launches (if not already running),
and optionally stops it when the app exits (only if we started it).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_STARTUP_TIMEOUT = 20  # seconds to wait for ollama to become ready

_ollama_proc: subprocess.Popen | None = None  # process we started (not one already running)
_we_started_it = False


def ensure_ollama_running() -> bool:
    """
    Make sure Ollama is running.

    Returns True if Ollama is ready (already running or we started it),
    False if it couldn't be started.
    """
    global _ollama_proc, _we_started_it

    # Already responding?
    if _is_ollama_ready():
        return True

    # Find the ollama executable
    ollama_exe = _find_ollama()
    if not ollama_exe:
        return False

    # Start it
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        _ollama_proc = subprocess.Popen(
            [ollama_exe, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        _we_started_it = True
    except Exception as e:
        print(f"[ollama_manager] Failed to start ollama: {e}")
        return False

    # Wait for it to become ready
    deadline = time.time() + OLLAMA_STARTUP_TIMEOUT
    while time.time() < deadline:
        if _is_ollama_ready():
            print("[ollama_manager] Ollama started successfully.")
            return True
        time.sleep(0.5)

    print("[ollama_manager] Ollama did not become ready in time.")
    return False


def ensure_ollama_running_async(callback=None):
    """
    Start Ollama in a background thread so the app UI doesn't block.
    Calls callback(success: bool) when done.
    """
    def _run():
        success = ensure_ollama_running()
        if callback:
            callback(success)

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def stop_ollama_if_we_started():
    """
    Stop Ollama only if this process started it.
    If it was already running before the app launched, leave it alone.
    """
    global _ollama_proc, _we_started_it
    if _we_started_it and _ollama_proc is not None:
        try:
            _ollama_proc.terminate()
            _ollama_proc.wait(timeout=5)
            print("[ollama_manager] Ollama stopped.")
        except Exception:
            pass
        finally:
            _ollama_proc = None
            _we_started_it = False


def is_ready() -> bool:
    return _is_ollama_ready()


def _is_ollama_ready() -> bool:
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/tags", timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def _find_ollama() -> str | None:
    # Check well-known Windows install path first
    known = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
    if known.exists():
        return str(known)

    # Fall back to PATH
    return shutil.which("ollama")

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

FFMPEG_KEY = "ffmpeg"
FFMPEG_DOWNLOAD_PAGE = "https://www.gyan.dev/ffmpeg/builds/"
FFMPEG_DOWNLOAD_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
FFMPEG_SHA256_URL = FFMPEG_DOWNLOAD_URL + ".sha256"


def _local_app_data() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))


def get_app_data_dir() -> Path:
    return _local_app_data() / "GameCutAI"


APP_DEPENDENCY_DIR = get_app_data_dir() / "dependencies"
FFMPEG_INSTALL_DIR = APP_DEPENDENCY_DIR / "ffmpeg"
FFMPEG_CURRENT_DIR = FFMPEG_INSTALL_DIR / "current"


def _creationflags() -> int:
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _ffmpeg_exe_name() -> str:
    return "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"


def _dedupe(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path).lower() if sys.platform == "win32" else str(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _candidate_paths() -> list[Path]:
    exe_name = _ffmpeg_exe_name()
    candidates: list[Path] = []

    env_path = os.environ.get("FFMPEG_PATH")
    if env_path:
        candidates.append(Path(env_path))

    env_dir = os.environ.get("FFMPEG_DIR")
    if env_dir:
        candidates.append(Path(env_dir) / exe_name)
        candidates.append(Path(env_dir) / "bin" / exe_name)

    candidates.append(FFMPEG_CURRENT_DIR / "bin" / exe_name)

    which = shutil.which("ffmpeg")
    if which:
        candidates.append(Path(which))

    if sys.platform == "win32":
        candidates.extend([
            Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
            Path(r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"),
            Path(r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe"),
        ])

    return _dedupe(candidates)


def check_ffmpeg_executable(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {
            "ok": False,
            "path": str(path),
            "detail": "Executable was not found.",
            "exit_code": None,
        }

    try:
        proc = subprocess.run(
            [str(path), "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
            creationflags=_creationflags(),
        )
    except Exception as exc:
        return {
            "ok": False,
            "path": str(path),
            "detail": str(exc),
            "exit_code": None,
        }

    output = (proc.stdout or proc.stderr or "").strip()
    first_line = output.splitlines()[0] if output else "No version output."
    return {
        "ok": proc.returncode == 0,
        "path": str(path),
        "detail": first_line if proc.returncode == 0 else f"Exit code {proc.returncode}: {first_line}",
        "exit_code": proc.returncode,
    }


def find_ffmpeg() -> dict:
    failures: list[dict] = []
    for candidate in _candidate_paths():
        if not candidate.exists():
            continue
        result = check_ffmpeg_executable(candidate)
        if result["ok"]:
            return {
                "ok": True,
                "path": result["path"],
                "detail": result["detail"],
                "failures": failures,
            }
        failures.append(result)

    if failures:
        first = failures[0]
        return {
            "ok": False,
            "path": first["path"],
            "detail": first["detail"],
            "failures": failures,
        }

    return {
        "ok": False,
        "path": None,
        "detail": "FFmpeg is not installed.",
        "failures": [],
    }


def resolve_ffmpeg_path() -> str | None:
    result = find_ffmpeg()
    return result["path"] if result["ok"] else None


def get_setup_payload() -> dict:
    ffmpeg = find_ffmpeg()
    ffmpeg_ok = bool(ffmpeg["ok"])
    if ffmpeg_ok:
        ffmpeg_detail = ffmpeg["detail"]
        ffmpeg_fix = ""
    elif ffmpeg["path"]:
        ffmpeg_detail = f"Found at {ffmpeg['path']}, but it could not run."
        ffmpeg_fix = ffmpeg["detail"]
    else:
        ffmpeg_detail = "Not installed."
        ffmpeg_fix = "Install FFmpeg to render and export videos."

    checks = [
        {
            "key": "python",
            "name": "App runtime",
            "ok": True,
            "required": True,
            "detail": sys.version.split()[0],
        },
        {
            "key": FFMPEG_KEY,
            "name": "FFmpeg",
            "ok": ffmpeg_ok,
            "required": True,
            "detail": ffmpeg_detail,
            "path": ffmpeg.get("path"),
            "fix": ffmpeg_fix,
            "installable": True,
            "install_label": "Install FFmpeg",
            "download_url": FFMPEG_DOWNLOAD_PAGE,
        },
    ]

    return {
        "status": "ok" if ffmpeg_ok else "missing",
        "ready": ffmpeg_ok,
        "checks": checks,
        "dependencies": {
            "python": True,
            "packages": True,
            "ffmpeg": ffmpeg_ok,
        },
    }


def get_dependency_page_url(key: str) -> str | None:
    return FFMPEG_DOWNLOAD_PAGE if key == FFMPEG_KEY else None


def _report(progress: Callable[[int, str], None] | None, percent: int, message: str) -> None:
    if progress:
        progress(percent, message)


def _download_text(url: str, timeout: int = 30) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _download_file(url: str, dest: Path, progress: Callable[[int, str], None] | None) -> None:
    last_percent = {"value": -1}

    def hook(block_count: int, block_size: int, total_size: int) -> None:
        if total_size <= 0:
            _report(progress, 15, "Downloading FFmpeg...")
            return
        loaded = min(block_count * block_size, total_size)
        percent = 10 + int((loaded / total_size) * 55)
        if percent != last_percent["value"]:
            last_percent["value"] = percent
            _report(progress, percent, "Downloading FFmpeg...")

    urllib.request.urlretrieve(url, dest, hook)


def _expected_sha256() -> str:
    text = _download_text(FFMPEG_SHA256_URL).strip()
    first = text.split()[0].strip().lower()
    if len(first) != 64:
        raise RuntimeError("Could not read the FFmpeg checksum.")
    return first


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def install_ffmpeg(progress: Callable[[int, str], None] | None = None) -> dict:
    if sys.platform != "win32":
        raise RuntimeError("Automatic FFmpeg installation is currently only supported on Windows.")

    FFMPEG_INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = FFMPEG_INSTALL_DIR / "ffmpeg-release-essentials.zip"
    staging = FFMPEG_INSTALL_DIR / "staging"
    temp_current = FFMPEG_INSTALL_DIR / "current_tmp"

    _report(progress, 5, "Preparing FFmpeg install...")
    expected_hash = _expected_sha256()

    _download_file(FFMPEG_DOWNLOAD_URL, zip_path, progress)
    _report(progress, 68, "Verifying FFmpeg download...")
    actual_hash = _file_sha256(zip_path)
    if actual_hash != expected_hash:
        raise RuntimeError("Downloaded FFmpeg did not match the expected checksum.")

    for path in (staging, temp_current):
        if path.exists():
            shutil.rmtree(path)
    staging.mkdir(parents=True, exist_ok=True)

    _report(progress, 75, "Extracting FFmpeg...")
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(staging)

    matches = list(staging.glob("**/bin/ffmpeg.exe"))
    if not matches:
        raise RuntimeError("The FFmpeg download did not contain ffmpeg.exe.")

    extracted_root = matches[0].parent.parent
    shutil.copytree(extracted_root, temp_current)

    installed_exe = temp_current / "bin" / "ffmpeg.exe"
    _report(progress, 88, "Testing FFmpeg...")
    test = check_ffmpeg_executable(installed_exe)
    if not test["ok"]:
        raise RuntimeError(f"Installed FFmpeg could not run: {test['detail']}")

    _report(progress, 94, "Finalizing FFmpeg install...")
    if FFMPEG_CURRENT_DIR.exists():
        shutil.rmtree(FFMPEG_CURRENT_DIR)
    temp_current.rename(FFMPEG_CURRENT_DIR)
    shutil.rmtree(staging, ignore_errors=True)

    result = find_ffmpeg()
    if not result["ok"]:
        raise RuntimeError("FFmpeg installed, but the app could not verify it.")

    _report(progress, 100, "FFmpeg installed.")
    return result


def install_dependency(key: str, progress: Callable[[int, str], None] | None = None) -> dict:
    if key != FFMPEG_KEY:
        raise ValueError(f"Unknown dependency: {key}")
    return install_ffmpeg(progress)

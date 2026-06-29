from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Callable

try:
    from backend.services.dependencies import get_app_data_dir
except ImportError:
    from services.dependencies import get_app_data_dir

APP_VERSION = os.environ.get("GAMECUT_VERSION", "1.0.0")
CONFIG_FILE_NAME = "update_config.json"


def _creationflags() -> int:
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _config_candidates() -> list[Path]:
    candidates = [Path.cwd() / CONFIG_FILE_NAME, get_app_data_dir() / CONFIG_FILE_NAME]
    if getattr(sys, "frozen", False):
        candidates.insert(0, Path(sys.executable).resolve().parent / CONFIG_FILE_NAME)
    return candidates


def load_update_config() -> dict:
    env_url = os.environ.get("GAMECUT_UPDATE_MANIFEST_URL")
    if env_url:
        return {"manifest_url": env_url}

    for path in _config_candidates():
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return {"manifest_url": ""}
    return {"manifest_url": ""}


def compare_versions(left: str, right: str) -> int:
    left_parts = _version_parts(left)
    right_parts = _version_parts(right)
    length = max(len(left_parts), len(right_parts), 3)
    left_parts += [0] * (length - len(left_parts))
    right_parts += [0] * (length - len(right_parts))
    if left_parts > right_parts:
        return 1
    if left_parts < right_parts:
        return -1
    return 0


def _version_parts(version: str) -> list[int]:
    return [int(part) for part in re.findall(r"\d+", str(version))]


def evaluate_update_manifest(current_version: str, manifest: dict) -> dict:
    latest_version = str(manifest.get("version") or "").strip()
    download_url = str(manifest.get("download_url") or "").strip()
    sha256 = str(manifest.get("sha256") or "").strip().lower()
    notes = str(manifest.get("notes") or "").strip()

    update_available = bool(
        latest_version
        and download_url
        and compare_versions(latest_version, current_version) > 0
    )

    return {
        "enabled": True,
        "current_version": current_version,
        "latest_version": latest_version or current_version,
        "update_available": update_available,
        "download_url": download_url,
        "sha256": sha256,
        "notes": notes,
        "message": "Update available." if update_available else "You are up to date.",
    }


def check_for_update(manifest_url: str | None = None, current_version: str = APP_VERSION) -> dict:
    # Only fall back to config when manifest_url was not supplied at all (None).
    # An explicit empty string means "no URL" — return disabled immediately.
    if manifest_url is None:
        manifest_url = str(load_update_config().get("manifest_url") or "").strip()
    else:
        manifest_url = manifest_url.strip()

    if not manifest_url:
        return {
            "enabled": False,
            "current_version": current_version,
            "latest_version": current_version,
            "update_available": False,
            "message": "No update feed is configured yet.",
        }

    manifest = _read_json(manifest_url)
    result = evaluate_update_manifest(current_version, manifest)
    result["manifest_url"] = manifest_url
    return result


def _read_json(location: str) -> dict:
    if location.startswith(("http://", "https://")):
        # Handle GitHub releases API format
        if "api.github.com/repos" in location and "/releases" in location:
            with urllib.request.urlopen(location, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
                # Convert GitHub release format to our manifest format
                if isinstance(data, dict) and "tag_name" in data:
                    return {
                        "version": data.get("tag_name", "").lstrip("v"),
                        "download_url": data.get("assets", [{}])[0].get("browser_download_url", ""),
                        "sha256": "",  # GitHub doesn't provide this in API
                        "notes": data.get("body", "")
                    }
                return data
        with urllib.request.urlopen(location, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    # Handle local file paths
    return json.loads(Path(location).read_text(encoding="utf-8-sig"))


def _report(progress: Callable[[int, str], None] | None, percent: int, message: str) -> None:
    if progress:
        progress(percent, message)


def _download_file(url: str, dest: Path, progress: Callable[[int, str], None] | None) -> None:
    # Handle local file paths
    if not url.startswith(("http://", "https://")):
        import shutil
        shutil.copy(url, dest)
        _report(progress, 80, "Copying update file...")
        return

    last_percent = {"value": -1}

    def hook(block_count: int, block_size: int, total_size: int) -> None:
        if total_size <= 0:
            _report(progress, 10, "Downloading update...")
            return
        loaded = min(block_count * block_size, total_size)
        percent = 5 + int((loaded / total_size) * 75)
        if percent != last_percent["value"]:
            last_percent["value"] = percent
            _report(progress, percent, "Downloading update...")

    urllib.request.urlretrieve(url, dest, hook)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def download_update(update_info: dict, progress: Callable[[int, str], None] | None = None) -> dict:
    if not update_info.get("update_available"):
        raise RuntimeError("No update is available.")

    download_url = str(update_info.get("download_url") or "").strip()
    if not download_url:
        raise RuntimeError("The update manifest does not include a download URL.")

    version = str(update_info.get("latest_version") or "latest")
    suffix = Path(download_url.split("?", 1)[0]).suffix or ".exe"
    update_dir = get_app_data_dir() / "updates"
    update_dir.mkdir(parents=True, exist_ok=True)
    dest = update_dir / f"GameCutAI-{version}{suffix}"

    _report(progress, 5, "Starting update download...")
    _download_file(download_url, dest, progress)

    expected_hash = str(update_info.get("sha256") or "").strip().lower()
    if expected_hash:
        _report(progress, 84, "Verifying update...")
        actual_hash = _file_sha256(dest)
        if actual_hash != expected_hash:
            dest.unlink(missing_ok=True)
            raise RuntimeError("Downloaded update did not match the expected checksum.")

    _report(progress, 100, "Update downloaded.")
    return {
        "path": str(dest),
        "version": version,
        "message": "Update downloaded. Run the downloaded installer to finish updating.",
    }


def open_update_file(path: str | Path) -> None:
    path = Path(path)
    if not path.exists():
        raise RuntimeError("Downloaded update file is missing.")
    if sys.platform == "win32":
        os.startfile(str(path))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])

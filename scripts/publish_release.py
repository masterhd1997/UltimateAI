#!/usr/bin/env python3
"""
publish_release.py — Local release helper for GameCutAI.

Usage:
    python scripts/publish_release.py --version 0.1.1

What it does:
    1. Builds the .exe with PyInstaller (sets GAMECUT_VERSION).
    2. Computes the SHA-256 of the built installer.
    3. Writes latest.json (the update manifest) to the project root.
    4. Prints the git commands to tag and push, which triggers the
       GitHub Actions release workflow automatically.

Requirements:
    - PyInstaller installed  (pip install pyinstaller)
    - git initialized and remote 'origin' pointing at GitHub
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST_EXE = ROOT / "dist" / "GameCutAI.exe"
MANIFEST_OUT = ROOT / "latest.json"


def _abort(msg: str) -> None:
    print(f"\n✖  {msg}", file=sys.stderr)
    sys.exit(1)


def _run(cmd: list[str], env: dict | None = None) -> str:
    merged = {**os.environ, **(env or {})}
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, env=merged)
    if result.returncode != 0:
        _abort(f"Command failed: {' '.join(cmd)}\n{result.stderr.strip()}")
    return result.stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def _valid_version(v: str) -> bool:
    return bool(re.fullmatch(r"\d+\.\d+\.\d+", v))


def _github_remote() -> str | None:
    try:
        url = _run(["git", "remote", "get-url", "origin"])
        # Extract owner/repo from https or ssh URL
        m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
        return m.group(1) if m else None
    except SystemExit:
        return None


def build(version: str) -> None:
    print(f"\n▶  Building GameCutAI {version} ...")
    _run(
        ["pyinstaller", "gui.spec", "--noconfirm"],
        env={"GAMECUT_VERSION": version},
    )
    if not DIST_EXE.exists():
        _abort("Build succeeded but dist/GameCutAI.exe was not found.")
    print(f"   Built: {DIST_EXE} ({DIST_EXE.stat().st_size // 1024 // 1024} MB)")


def write_manifest(version: str, repo: str | None) -> None:
    tag = f"v{version}"
    if repo:
        download_url = f"https://github.com/{repo}/releases/download/{tag}/GameCutAI-{version}.exe"
    else:
        download_url = ""
        print("   ⚠  No GitHub remote detected — download_url left blank in manifest.")

    sha = _sha256(DIST_EXE)
    manifest = {
        "version": version,
        "download_url": download_url,
        "sha256": sha,
        "notes": f"GameCutAI {version}",
    }

    MANIFEST_OUT.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"   Manifest written to: {MANIFEST_OUT}")
    print(f"   SHA-256: {sha}")
    print(f"   Download URL: {download_url or '(not set)'}")


def wire_update_config(repo: str | None) -> None:
    config_path = ROOT / "update_config.json"
    if repo:
        manifest_url = f"https://raw.githubusercontent.com/{repo}/main/latest.json"
        config_path.write_text(
            json.dumps({"manifest_url": manifest_url}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"   update_config.json → {manifest_url}")
    else:
        print("   Skipping update_config.json — no GitHub remote.")


def print_next_steps(version: str, repo: str | None) -> None:
    tag = f"v{version}"
    print("\n── Next steps ──────────────────────────────────────────────")
    if repo:
        print(f"""
  git add latest.json update_config.json
  git commit -m "chore: release {version}"
  git tag {tag}
  git push origin main
  git push origin {tag}

  The GitHub Actions workflow will then:
    • Build the .exe in CI
    • Compute its SHA-256
    • Create a GitHub Release at:
        https://github.com/{repo}/releases/tag/{tag}
    • Upload GameCutAI-{version}.exe + latest.json
    • Commit latest.json back to main

  After the workflow finishes, every installed copy will detect the
  update the next time the user clicks "Check Updates".
""")
    else:
        print("""
  1. Create a GitHub repo and add it as origin:
       git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git

  2. Re-run this script — it will wire update_config.json automatically.

  3. Push your tag to trigger the release workflow:
       git tag v{version}
       git push origin main --tags
""")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and release GameCutAI")
    parser.add_argument("--version", required=True, help="Release version, e.g. 0.1.1")
    parser.add_argument("--skip-build", action="store_true", help="Skip PyInstaller (use existing dist/GameCutAI.exe)")
    args = parser.parse_args()

    version = args.version.lstrip("v")
    if not _valid_version(version):
        _abort(f"Version must be in X.Y.Z format, got: {version!r}")

    repo = _github_remote()
    if repo:
        print(f"   GitHub repo: {repo}")
    else:
        print("   No GitHub remote detected yet.")

    if not args.skip_build:
        build(version)
    elif not DIST_EXE.exists():
        _abort("--skip-build was set but dist/GameCutAI.exe does not exist.")

    write_manifest(version, repo)
    wire_update_config(repo)
    print_next_steps(version, repo)


if __name__ == "__main__":
    main()

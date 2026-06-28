# Releasing GameCutAI

Everything from building the `.exe` to users getting the update prompt is automated.
This doc explains the one-time setup and the release process going forward.

---

## One-time setup

### 1. Create a GitHub repo

Go to https://github.com/new and create a **public** repository named `GameCutAI`
(or whatever you want — private repos work too, but the raw `latest.json` URL
must be publicly accessible for the update check to work without authentication).

### 2. Add it as the remote and push

```bat
cd C:\Users\Landon Posuk\UltimateAI
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git add .
git commit -m "chore: initial commit"
git branch -M main
git push -u origin main
```

### 3. Wire update_config.json

Run the release script once (with `--skip-build` if you haven't built yet):

```bat
python scripts/publish_release.py --version 0.1.0 --skip-build
```

It detects your GitHub remote and fills in `update_config.json` automatically:

```json
{
  "manifest_url": "https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main/latest.json"
}
```

Commit and push that change:

```bat
git add update_config.json latest.json
git commit -m "chore: wire update feed"
git push origin main
```

---

## Releasing a new version

Every release is a git tag push. The GitHub Actions workflow handles the rest.

### Step 1 — bump the version in updater.py

Edit the default in `backend/services/updater.py`:

```python
APP_VERSION = os.environ.get("GAMECUT_VERSION", "0.2.0")   # ← new version
```

### Step 2 — run the release script locally (optional but recommended)

This builds the `.exe`, computes its SHA-256, and writes `latest.json`.
You can review it before it goes live.

```bat
set GAMECUT_VERSION=0.2.0
python scripts/publish_release.py --version 0.2.0
```

### Step 3 — tag and push

```bat
git add .
git commit -m "chore: release 0.2.0"
git tag v0.2.0
git push origin main
git push origin v0.2.0
```

The GitHub Actions workflow (`.github/workflows/release.yml`) will:

1. Build `GameCutAI-0.2.0.exe` with PyInstaller on a clean Windows runner
2. Compute its SHA-256
3. Write `latest.json` with the version, download URL, and hash
4. Create a GitHub Release at `github.com/YOUR_USERNAME/YOUR_REPO/releases`
5. Upload `GameCutAI-0.2.0.exe` and `latest.json` as release assets
6. Commit the updated `latest.json` back to `main`

After step 6, every installed copy of GameCutAI will see the update the next time
the user clicks **Check Updates**.

---

## How the update flow works at runtime

```
User clicks "Check Updates"
  ↓
check_for_update() reads update_config.json
  ↓
fetches latest.json from GitHub raw URL
  ↓
compares manifest["version"] vs APP_VERSION
  ↓
if newer → shows update overlay with version + notes
  ↓
user clicks "Download Update"
  ↓
downloads GameCutAI-X.Y.Z.exe to %LOCALAPPDATA%\GameCutAI\updates\
  ↓
verifies SHA-256
  ↓
launches installer and closes overlay
```

---

## Files involved

| File | Purpose |
|---|---|
| `latest.json` | Hosted update manifest — auto-updated by CI on each release |
| `update_config.json` | Points installed copies at the manifest URL |
| `scripts/publish_release.py` | Local build + release helper |
| `scripts/rthook_version.py` | PyInstaller runtime hook — stamps version into the frozen exe |
| `.github/workflows/release.yml` | Full CI/CD pipeline — build, hash, release, commit |
| `backend/services/updater.py` | Core update logic (check, download, verify, launch) |

---

## Distributing update_config.json with your installer

When you ship the installer, `update_config.json` needs to be present next to
`GameCutAI.exe` so the app can find it. The GitHub Actions workflow uploads it
as a release asset — include it in your NSIS/Inno Setup installer script, or
just tell users to place it in the same folder as the `.exe`.

The app also checks `%LOCALAPPDATA%\GameCutAI\update_config.json` as a fallback,
and the `GAMECUT_UPDATE_MANIFEST_URL` environment variable takes highest priority.

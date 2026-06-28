# AI Editor Foundation Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the local desktop editor foundation reliable enough for the AI-first gameplay editor: clean UI text, persistent projects, structured edit plans, safe asset library, and render/project recovery wiring.

**Architecture:** Keep rendering local and deterministic. Add small backend services for project storage, edit-plan modeling, and asset lookup, then connect them to the existing `gui.py` native controller and frontend. This phase creates extension points for accounts, shared recipes, and YouTube research without building those cloud systems yet.

**Tech Stack:** Python 3.11, `unittest`, PyWebView native bridge, FFmpeg, OpenCV, plain frontend JavaScript/CSS/HTML, JSON project storage under `%LOCALAPPDATA%\GameCutAI`.

---

## Scope

This plan implements the local foundation only.

Included:

- Clean visible UI text encoding.
- Project save/recovery service.
- Structured edit plan model.
- Local asset library manifest and lookup.
- Render integration that saves project metadata, edit plans, and exported paths.
- Frontend project recovery surface.

Deferred to separate implementation plans:

- Real account sign-in.
- Shared recipe database.
- YouTube research service.
- Cloud video backup.
- Pro billing and entitlements.

## File Structure

- `backend/services/project_store.py`: JSON-backed local project persistence.
- `backend/services/edit_plan.py`: structured edit-plan creation and serialization.
- `backend/services/asset_library.py`: reads built-in safe asset manifest and selects assets by genre/style.
- `assets/library/manifest.json`: safe built-in asset metadata; starts with metadata entries and empty file paths until real licensed assets are added.
- `tests/test_project_store.py`: project save/load/recovery tests.
- `tests/test_edit_plan.py`: edit-plan model tests.
- `tests/test_asset_library.py`: asset lookup tests.
- `gui.py`: native bridge methods for projects, render project save, and recent projects.
- `frontend/index.html`: clean encoding text and recent project area.
- `frontend/js/app.js`: project recovery UI logic and project metadata display.
- `frontend/css/editor.css`: recent project list styling.

---

### Task 1: Clean Visible UI Text Encoding

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/js/app.js`

- [ ] **Step 1: Inspect current visible text**

Run:

```powershell
rg -n "â|Ã|Â|ð|Ÿ|š|œ" frontend
```

Expected: Finds encoded characters in visible text.

- [ ] **Step 2: Replace visible garbled text in `frontend/index.html`**

Use these replacements exactly:

```html
<!-- Setup overlay - shown if FFmpeg or other required components are missing -->
<div class="setup-overlay" id="setupOverlay">
  <div class="setup-card">
    <div class="setup-icon">⚙</div>
    <h2>Almost ready</h2>
    <p class="setup-sub">Install missing components to unlock full AI editing</p>
    <ul class="setup-list" id="setupList"></ul>
    <button class="btn primary" id="btnSetupDismiss">Check again</button>
  </div>
</div>
```

Replace the style chips with ASCII-safe labels:

```html
<button class="style-chip active" data-style="hype">Hype</button>
<button class="style-chip" data-style="cinematic">Cinematic</button>
<button class="style-chip" data-style="funny">Funny</button>
<button class="style-chip" data-style="tutorial">Tutorial</button>
```

Replace the AI button text with:

```html
<button id="btnAiEdit" class="btn ai" disabled>
  <span class="btn-shine"></span>
  AI Edit My Video
</button>
```

Replace assistant intro text with:

```html
Upload your clip, pick your game, hit <strong>AI Edit</strong> - I will build an edit automatically.
```

- [ ] **Step 3: Replace visible garbled strings in `frontend/js/app.js`**

Make sure user-facing strings use plain ASCII:

```javascript
els.uploadText.textContent = `Uploading... ${formatBytes(e.loaded)} / ${formatBytes(e.total)}`;
log(`Starting AI edit for <strong>${escapeHtml(els.gameName.value.trim())}</strong>...`, "user");
log("Footage loaded into the editor. Analyzing your gameplay...");
log("Footage uploaded. Analyzing your gameplay...");
log("Your AI edit is ready. Preview above or hit <strong>Export</strong>.", "ai");
```

- [ ] **Step 4: Verify no garbled visible text remains**

Run:

```powershell
rg -n "â|Ã|Â|ð|Ÿ|š|œ" frontend
```

Expected: No matches.

- [ ] **Step 5: Verify JavaScript syntax**

Run:

```powershell
node --check frontend\js\app.js
```

Expected: Exit code `0`.

---

### Task 2: Add Local Project Store

**Files:**
- Create: `backend/services/project_store.py`
- Create: `tests/test_project_store.py`

- [ ] **Step 1: Write the failing project store tests**

Create `tests/test_project_store.py`:

```python
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.services.project_store import ProjectStore


class ProjectStoreTests(unittest.TestCase):
    def test_creates_project_with_metadata(self):
        with TemporaryDirectory() as temp_dir:
            store = ProjectStore(Path(temp_dir))
            project = store.create_project(
                source_path="C:/videos/input.mp4",
                file_name="input.mp4",
                options={"game_name": "Valorant", "style": "hype"},
            )

            self.assertEqual(project["file_name"], "input.mp4")
            self.assertEqual(project["options"]["game_name"], "Valorant")
            self.assertEqual(project["status"], "created")
            self.assertTrue((Path(temp_dir) / "projects" / project["id"] / "project.json").exists())

    def test_updates_project_after_render(self):
        with TemporaryDirectory() as temp_dir:
            store = ProjectStore(Path(temp_dir))
            project = store.create_project("C:/videos/input.mp4", "input.mp4", {"style": "funny"})

            updated = store.update_project(project["id"], {
                "status": "completed",
                "export_path": "C:/exports/out.mp4",
                "edit_plan": {"target_duration": 30},
            })

            self.assertEqual(updated["status"], "completed")
            self.assertEqual(updated["export_path"], "C:/exports/out.mp4")
            self.assertEqual(updated["edit_plan"]["target_duration"], 30)

    def test_lists_recent_projects_newest_first(self):
        with TemporaryDirectory() as temp_dir:
            store = ProjectStore(Path(temp_dir))
            first = store.create_project("C:/videos/one.mp4", "one.mp4", {})
            second = store.create_project("C:/videos/two.mp4", "two.mp4", {})

            recent = store.list_recent_projects(limit=5)

            self.assertEqual([item["id"] for item in recent], [second["id"], first["id"]])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
& 'C:\ml-pytorch\Miniconda3\python.exe' -m unittest tests.test_project_store
```

Expected: `ModuleNotFoundError: No module named 'backend.services.project_store'`.

- [ ] **Step 3: Implement `ProjectStore`**

Create `backend/services/project_store.py`:

```python
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProjectStore:
    def __init__(self, app_data_dir: Path):
        self.app_data_dir = Path(app_data_dir)
        self.projects_dir = self.app_data_dir / "projects"
        self.projects_dir.mkdir(parents=True, exist_ok=True)

    def create_project(self, source_path: str, file_name: str, options: dict[str, Any]) -> dict[str, Any]:
        project_id = uuid.uuid4().hex
        timestamp = _now()
        project = {
            "id": project_id,
            "file_name": file_name,
            "source_path": source_path,
            "options": dict(options or {}),
            "status": "created",
            "created_at": timestamp,
            "updated_at": timestamp,
            "edit_plan": None,
            "export_path": None,
        }
        self._write(project)
        return project

    def update_project(self, project_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        project = self.get_project(project_id)
        if not project:
            raise KeyError(f"Project not found: {project_id}")
        project.update(changes)
        project["updated_at"] = _now()
        self._write(project)
        return project

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        path = self._project_file(project_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_recent_projects(self, limit: int = 20) -> list[dict[str, Any]]:
        projects = []
        for path in self.projects_dir.glob("*/project.json"):
            try:
                projects.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        projects.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return projects[:limit]

    def _project_file(self, project_id: str) -> Path:
        return self.projects_dir / project_id / "project.json"

    def _write(self, project: dict[str, Any]) -> None:
        path = self._project_file(project["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(project, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run project store tests**

Run:

```powershell
& 'C:\ml-pytorch\Miniconda3\python.exe' -m unittest tests.test_project_store
```

Expected: `Ran 3 tests` and `OK`.

---

### Task 3: Add Structured Edit Plan Model

**Files:**
- Create: `backend/services/edit_plan.py`
- Create: `tests/test_edit_plan.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_edit_plan.py`:

```python
import unittest

from backend.services.edit_plan import create_edit_plan


class EditPlanTests(unittest.TestCase):
    def test_creates_plan_with_clip_effects_and_captions(self):
        plan = create_edit_plan(
            options={"game_name": "Resident Evil", "style": "horror", "target_duration": 45, "add_subtitles": True, "add_effects": True},
            highlights=[2.0, 19.5],
            research={"genre": "horror", "creator_targets": ["Markiplier", "IGP"]},
        )

        self.assertEqual(plan["target_duration"], 45)
        self.assertEqual(plan["genre"], "horror")
        self.assertEqual(plan["creator_targets"], ["Markiplier", "IGP"])
        self.assertGreaterEqual(len(plan["clips"]), 1)
        self.assertTrue(plan["captions_enabled"])
        self.assertIn("suspense hold", plan["effects"])

    def test_defaults_to_uploaded_gameplay_when_research_is_empty(self):
        plan = create_edit_plan(
            options={"game_name": "Gameplay", "style": "hype", "target_duration": 30},
            highlights=[],
            research=None,
        )

        self.assertEqual(plan["genre"], "general")
        self.assertEqual(plan["clips"][0]["start"], 0.0)
        self.assertEqual(plan["clips"][0]["end"], 30.0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
& 'C:\ml-pytorch\Miniconda3\python.exe' -m unittest tests.test_edit_plan
```

Expected: `ModuleNotFoundError: No module named 'backend.services.edit_plan'`.

- [ ] **Step 3: Implement edit plan creation**

Create `backend/services/edit_plan.py`:

```python
from __future__ import annotations

from typing import Any


STYLE_EFFECTS = {
    "horror": ["suspense hold", "dark grade", "reaction zoom", "static hit"],
    "cinematic": ["cinematic grade", "slow fade", "subtle sharpen"],
    "funny": ["freeze frame", "reaction caption", "quick zoom"],
    "tutorial": ["clean trim", "step caption", "highlight zoom"],
    "hype": ["style grade", "fade", "punch zoom"],
}


def create_edit_plan(options: dict[str, Any], highlights: list[float], research: dict[str, Any] | None = None) -> dict[str, Any]:
    options = dict(options or {})
    research = dict(research or {})
    target_duration = int(options.get("target_duration") or 60)
    style = str(options.get("style") or "hype").lower()
    genre = str(research.get("genre") or _genre_from_style(style))
    creator_targets = list(research.get("creator_targets") or [])

    start = max(0.0, float(highlights[0])) if highlights else 0.0
    clip = {
        "start": start,
        "end": start + float(target_duration),
        "effect": style,
        "transition": "fade" if options.get("add_effects", True) else "cut",
    }

    return {
        "version": 1,
        "game_name": str(options.get("game_name") or "Gameplay"),
        "style": style,
        "genre": genre,
        "creator_targets": creator_targets,
        "target_duration": target_duration,
        "clips": [clip],
        "effects": STYLE_EFFECTS.get(style, STYLE_EFFECTS["hype"]) if options.get("add_effects", True) else [],
        "captions_enabled": bool(options.get("add_subtitles", True)),
        "research_summary": str(research.get("summary") or ""),
    }


def _genre_from_style(style: str) -> str:
    if style == "horror":
        return "horror"
    if style in {"cinematic", "funny", "tutorial", "hype"}:
        return "general"
    return "general"
```

- [ ] **Step 4: Run edit plan tests**

Run:

```powershell
& 'C:\ml-pytorch\Miniconda3\python.exe' -m unittest tests.test_edit_plan
```

Expected: `Ran 2 tests` and `OK`.

---

### Task 4: Add Safe Asset Library Manifest

**Files:**
- Create: `assets/library/manifest.json`
- Create: `backend/services/asset_library.py`
- Create: `tests/test_asset_library.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_asset_library.py`:

```python
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.services.asset_library import AssetLibrary


class AssetLibraryTests(unittest.TestCase):
    def test_selects_assets_by_genre_and_style(self):
        with TemporaryDirectory() as temp_dir:
            manifest = Path(temp_dir) / "manifest.json"
            manifest.write_text(json.dumps({
                "assets": [
                    {"id": "static-hit", "type": "sound", "path": "sounds/static-hit.wav", "genres": ["horror"], "styles": ["horror"], "license": "owned"},
                    {"id": "punch-zoom", "type": "effect", "path": "", "genres": ["general"], "styles": ["hype"], "license": "built-in"},
                ]
            }), encoding="utf-8")

            library = AssetLibrary(manifest)
            assets = library.select_assets(genre="horror", style="horror")

            self.assertEqual([asset["id"] for asset in assets], ["static-hit"])

    def test_rejects_assets_without_safe_license(self):
        with TemporaryDirectory() as temp_dir:
            manifest = Path(temp_dir) / "manifest.json"
            manifest.write_text(json.dumps({
                "assets": [
                    {"id": "unsafe", "type": "image", "path": "memes/unsafe.png", "genres": ["funny"], "styles": ["funny"], "license": "unknown"}
                ]
            }), encoding="utf-8")

            library = AssetLibrary(manifest)
            assets = library.select_assets(genre="funny", style="funny")

            self.assertEqual(assets, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
& 'C:\ml-pytorch\Miniconda3\python.exe' -m unittest tests.test_asset_library
```

Expected: `ModuleNotFoundError: No module named 'backend.services.asset_library'`.

- [ ] **Step 3: Add starter asset manifest**

Create `assets/library/manifest.json`:

```json
{
  "assets": [
    {
      "id": "punch-zoom",
      "type": "effect",
      "path": "",
      "genres": ["general", "fps", "racing"],
      "styles": ["hype", "funny"],
      "license": "built-in",
      "description": "Metadata entry for punch zoom render effect."
    },
    {
      "id": "suspense-hold",
      "type": "effect",
      "path": "",
      "genres": ["horror", "survival"],
      "styles": ["horror", "cinematic"],
      "license": "built-in",
      "description": "Metadata entry for suspense pacing and fade treatment."
    },
    {
      "id": "reaction-caption",
      "type": "caption",
      "path": "",
      "genres": ["funny", "simulator", "sandbox"],
      "styles": ["funny"],
      "license": "built-in",
      "description": "Metadata entry for reaction caption templates."
    }
  ]
}
```

- [ ] **Step 4: Implement asset library**

Create `backend/services/asset_library.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SAFE_LICENSES = {"owned", "licensed", "built-in", "public-domain"}


class AssetLibrary:
    def __init__(self, manifest_path: str | Path):
        self.manifest_path = Path(manifest_path)

    def select_assets(self, genre: str, style: str, limit: int = 8) -> list[dict[str, Any]]:
        manifest = self._read_manifest()
        genre = str(genre or "general").lower()
        style = str(style or "hype").lower()
        selected = []

        for asset in manifest.get("assets", []):
            if str(asset.get("license", "")).lower() not in SAFE_LICENSES:
                continue
            genres = {str(item).lower() for item in asset.get("genres", [])}
            styles = {str(item).lower() for item in asset.get("styles", [])}
            if genre in genres or style in styles:
                selected.append(asset)
            if len(selected) >= limit:
                break

        return selected

    def _read_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            return {"assets": []}
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))
```

- [ ] **Step 5: Run asset library tests**

Run:

```powershell
& 'C:\ml-pytorch\Miniconda3\python.exe' -m unittest tests.test_asset_library
```

Expected: `Ran 2 tests` and `OK`.

---

### Task 5: Wire Project Store and Edit Plan into Desktop Rendering

**Files:**
- Modify: `gui.py`
- Modify: `tests/test_editing_options.py`

- [ ] **Step 1: Add a test proving render result shape can be stored**

Modify `tests/test_editing_options.py` by adding:

```python
from backend.services.edit_plan import create_edit_plan


class EditPlanIntegrationTests(unittest.TestCase):
    def test_edit_plan_result_contains_project_save_fields(self):
        options = normalize_edit_options({
            "game_name": "Minecraft",
            "style": "funny",
            "target_duration": 20,
            "add_subtitles": True,
            "add_effects": True,
        })

        plan = create_edit_plan(options, [4.0], {"genre": "sandbox", "creator_targets": ["Drae"]})

        self.assertEqual(plan["game_name"], "Minecraft")
        self.assertEqual(plan["clips"][0]["start"], 4.0)
        self.assertTrue(plan["captions_enabled"])
```

- [ ] **Step 2: Run the new integration test**

Run:

```powershell
& 'C:\ml-pytorch\Miniconda3\python.exe' -m unittest tests.test_editing_options
```

Expected: Passes after Task 3 exists.

- [ ] **Step 3: Import new services in `gui.py`**

Add imports beside existing service imports:

```python
from backend.services.edit_plan import create_edit_plan
from backend.services.project_store import ProjectStore
```

In the fallback block:

```python
from services.edit_plan import create_edit_plan
from services.project_store import ProjectStore
```

- [ ] **Step 4: Initialize project store**

After `EXPORT_DIR` setup:

```python
PROJECT_STORE = ProjectStore(APP_DATA_DIR)
```

- [ ] **Step 5: Track project IDs in upload and render**

Change `process_video_upload` so it creates a project before rendering:

```python
options = normalize_edit_options(json.loads(options_json) if options_json else {})
project = PROJECT_STORE.create_project(str(input_path), file_name or input_path.name, options)
return self.process_video_edit(str(input_path), json.dumps(options), project["id"])
```

Change method signatures:

```python
def process_video_edit(self, input_video_path, options_json=None, project_id=None):
```

Thread call:

```python
t = threading.Thread(target=self._run_pipeline, args=(job_id, input_video_path, options_json, project_id), daemon=True)
```

Pipeline signature:

```python
def _run_pipeline(self, job_id, video_path, options_json=None, project_id=None):
```

- [ ] **Step 6: Save edit plan on completion**

Inside `_run_pipeline`, after highlights are known and before FFmpeg command:

```python
edit_plan = create_edit_plan(
    options,
    highlights,
    {"genre": options.get("style", "general"), "creator_targets": []},
)
```

In the successful result block:

```python
result = {
    "export_path": str(output_file),
    "project_id": project_id,
    "edit_plan": edit_plan,
}
job["result"] = result
if project_id:
    PROJECT_STORE.update_project(project_id, {
        "status": "completed",
        "export_path": str(output_file),
        "edit_plan": edit_plan,
    })
```

In exception handlers, add:

```python
if project_id:
    PROJECT_STORE.update_project(project_id, {"status": "failed", "error": job["message"]})
```

- [ ] **Step 7: Add native project APIs**

Add to `NativeAppController`:

```python
def list_recent_projects(self):
    return json.dumps({"projects": PROJECT_STORE.list_recent_projects()})

def get_project(self, project_id):
    project = PROJECT_STORE.get_project(project_id)
    return json.dumps({"project": project})
```

- [ ] **Step 8: Run focused tests**

Run:

```powershell
& 'C:\ml-pytorch\Miniconda3\python.exe' -m unittest tests.test_project_store tests.test_edit_plan tests.test_editing_options
```

Expected: All tests pass.

---

### Task 6: Add Recent Project Recovery UI

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/js/app.js`
- Modify: `frontend/css/editor.css`

- [ ] **Step 1: Add recent projects section to `frontend/index.html`**

Under the import footage section, add:

```html
<section class="panel-section recent-projects" id="recentProjectsSection" hidden>
  <h3>Recent projects</h3>
  <div class="recent-list" id="recentProjects"></div>
</section>
```

- [ ] **Step 2: Add DOM bindings in `frontend/js/app.js`**

Add to `els`:

```javascript
recentProjectsSection: $("recentProjectsSection"),
recentProjects: $("recentProjects"),
```

In `DOMContentLoaded`, after `bindEvents();`:

```javascript
loadRecentProjects();
```

- [ ] **Step 3: Add recent project loading functions**

Add to `frontend/js/app.js`:

```javascript
async function loadRecentProjects() {
  if (!hasNativeApi()) return;
  try {
    const data = JSON.parse(await window.pywebview.api.list_recent_projects());
    renderRecentProjects(data.projects || []);
  } catch {
    renderRecentProjects([]);
  }
}

function renderRecentProjects(projects) {
  els.recentProjects.innerHTML = "";
  els.recentProjectsSection.hidden = projects.length === 0;
  projects.slice(0, 5).forEach((project) => {
    const button = document.createElement("button");
    button.className = "recent-project";
    button.type = "button";
    button.innerHTML = `<strong>${escapeHtml(project.file_name || "Untitled project")}</strong><span>${escapeHtml(project.status || "saved")}</span>`;
    button.addEventListener("click", () => showProjectSummary(project));
    els.recentProjects.appendChild(button);
  });
}

function showProjectSummary(project) {
  const plan = project.edit_plan || {};
  log(`Recovered project <strong>${escapeHtml(project.file_name || project.id)}</strong> (${escapeHtml(project.status || "saved")})`, "ai");
  if (project.export_path) {
    exportUrl = pathToFileUrl(project.export_path);
    els.preview.src = exportUrl + "?t=" + Date.now();
    els.preview.style.display = "block";
    els.placeholder.style.display = "none";
    els.btnExport.disabled = false;
  }
  if (plan.clips) {
    renderTimeline(plan.clips);
    els.statsRow.hidden = false;
    els.statClips.textContent = plan.clips.length || 0;
    els.statDuration.textContent = `${Math.round(plan.target_duration || 0)}s`;
    els.statEffects.textContent = plan.effects?.length || 0;
  }
}
```

At the end of `finishEdit`, call:

```javascript
loadRecentProjects();
```

- [ ] **Step 4: Add recent project CSS**

Add to `frontend/css/editor.css`:

```css
.recent-list {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}

.recent-project {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text);
  cursor: pointer;
  font-family: var(--font);
  padding: 0.55rem 0.65rem;
  text-align: left;
  transition: border-color 0.2s var(--ease), transform 0.2s var(--ease);
}

.recent-project:hover {
  border-color: var(--border-hover);
  transform: translateY(-1px);
}

.recent-project strong,
.recent-project span {
  display: block;
}

.recent-project span {
  color: var(--muted);
  font-size: 0.72rem;
  margin-top: 0.1rem;
}
```

- [ ] **Step 5: Verify JavaScript syntax**

Run:

```powershell
node --check frontend\js\app.js
```

Expected: Exit code `0`.

---

### Task 7: Full Verification and Rebuild

**Files:**
- Existing files from prior tasks.

- [ ] **Step 1: Run all Python tests**

Run:

```powershell
& 'C:\ml-pytorch\Miniconda3\python.exe' -m unittest discover -s tests
```

Expected: All tests pass.

- [ ] **Step 2: Compile Python files**

Run:

```powershell
& 'C:\ml-pytorch\Miniconda3\python.exe' -m py_compile gui.py backend\main.py backend\services\pipeline.py backend\services\dependencies.py backend\services\editing.py backend\services\updater.py backend\services\project_store.py backend\services\edit_plan.py backend\services\asset_library.py
```

Expected: Exit code `0`.

- [ ] **Step 3: Check frontend syntax**

Run:

```powershell
node --check frontend\js\app.js
```

Expected: Exit code `0`.

- [ ] **Step 4: Run a real render with project persistence**

Run:

```powershell
New-Item -ItemType Directory -Force -Path "$env:LOCALAPPDATA\GameCutAI\uploads" | Out-Null
& "$env:LOCALAPPDATA\GameCutAI\dependencies\ffmpeg\current\bin\ffmpeg.exe" -y -f lavfi -i testsrc=duration=8:size=640x360:rate=30 -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 -shortest -c:v libx264 -pix_fmt yuv420p -c:a aac "$env:LOCALAPPDATA\GameCutAI\uploads\foundation_test.mp4"
& 'C:\ml-pytorch\Miniconda3\python.exe' -c "import json, os, time, gui; c=gui.NativeAppController(); opts={'game_name':'Foundation Test','style':'funny','target_duration':5,'add_subtitles':True,'add_effects':True}; path=os.path.join(os.environ['LOCALAPPDATA'],'GameCutAI','uploads','foundation_test.mp4'); queued=json.loads(c.process_video_edit(path,json.dumps(opts))); jid=queued['job_id']; deadline=time.time()+45; status={};
while time.time()<deadline:
    status=json.loads(c.get_job_status(jid))
    if status['status'] in ('completed','failed'): break
    time.sleep(0.5)
print(json.dumps(status, indent=2))
raise SystemExit(0 if status.get('status')=='completed' and status.get('result',{}).get('edit_plan') else 1)"
```

Expected: status `completed`, result includes `edit_plan`.

- [ ] **Step 5: Rebuild executable**

Run:

```powershell
& 'C:\ml-pytorch\Miniconda3\python.exe' -m PyInstaller gui.spec --noconfirm
```

Expected: `Build complete! The results are available in: C:\Users\Landon Posuk\UltimateAI\dist`.

- [ ] **Step 6: Check rebuilt artifact**

Run:

```powershell
Get-Item dist\gui.exe | Select-Object FullName, Length, LastWriteTime
```

Expected: `dist\gui.exe` exists with a fresh `LastWriteTime`.

- [ ] **Step 7: Clean verification media**

Run:

```powershell
Remove-Item -LiteralPath "$env:LOCALAPPDATA\GameCutAI\uploads\foundation_test.mp4" -ErrorAction SilentlyContinue
```

Expected: Exit code `0`.

---

## Plan Self-Review

Spec coverage:

- AI-first editor product direction: covered by edit plan model and project persistence foundation.
- Local desktop reliability: covered by project store, render wiring, and rebuild verification.
- Safe assets: covered by asset manifest and license filtering.
- Project recovery: covered by recent project UI and native APIs.
- Accounts/shared learning/YouTube research: intentionally deferred to separate plans because they require cloud/service architecture choices and privacy controls.

Placeholder scan:

- No placeholder markers or open-ended placeholder steps are included.
- Each code-changing task includes concrete code blocks.

Type consistency:

- Project fields are consistently `id`, `file_name`, `source_path`, `options`, `status`, `edit_plan`, `export_path`.
- Edit plan fields are consistently `version`, `game_name`, `style`, `genre`, `creator_targets`, `target_duration`, `clips`, `effects`, `captions_enabled`, `research_summary`.
- Native methods are consistently named `list_recent_projects` and `get_project`.

Git note:

- This workspace currently is not a git repository. If executing in a git clone, commit after each task with a focused message. If executing in this exact workspace, record changed files in the final response instead of running git commits.

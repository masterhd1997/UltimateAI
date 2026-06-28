const $ = (id) => document.getElementById(id);

const els = {
  dropZone: $("dropZone"),
  fileInput: $("fileInput"),
  preview: $("preview"),
  placeholder: $("placeholder"),
  gameName: $("gameName"),
  targetDuration: $("targetDuration"),
  targetDurationInput: $("targetDurationInput"),
  durationVal: $("durationVal"),
  btnAiEdit: $("btnAiEdit"),
  btnUpdate: $("btnUpdate"),
  btnExport: $("btnExport"),
  btnCompare: $("btnCompare"),
  btnSplit: $("btnSplit"),
  btnDeleteLeft: $("btnDeleteLeft"),
  btnDeleteRight: $("btnDeleteRight"),
  btnDelete: $("btnDelete"),
  btnReverse: $("btnReverse"),
  btnSpeed: $("btnSpeed"),
  exportPlatform: $("exportPlatform"),
  exportResolution: $("exportResolution"),
  exportFps: $("exportFps"),
  exportAspectRatio: $("exportAspectRatio"),
  removeSilence: $("removeSilence"),
  removeFillers: $("removeFillers"),
  jumpCuts: $("jumpCuts"),
  aiLog: $("aiLog"),
  researchPanel: $("researchPanel"),
  researchList: $("researchList"),
  timelineTrack: $("timelineTrack"),
  timelineRuler: $("timelineRuler"),
  timelineMeta: $("timelineMeta"),
  statsRow: $("statsRow"),
  statClips: $("statClips"),
  statDuration: $("statDuration"),
  statEffects: $("statEffects"),
  setupOverlay: $("setupOverlay"),
  setupList: $("setupList"),
  btnSetupDismiss: $("btnSetupDismiss"),
  updateOverlay: $("updateOverlay"),
  updateTitle: $("updateTitle"),
  updateSub: $("updateSub"),
  updateNotes: $("updateNotes"),
  updateProgress: $("updateProgress"),
  updateFill: $("updateFill"),
  updateText: $("updateText"),
  btnDownloadUpdate: $("btnDownloadUpdate"),
  btnUpdateClose: $("btnUpdateClose"),
  processOverlay: $("processOverlay"),
  processTitle: $("processTitle"),
  processSub: $("processSub"),
  overlayProgress: $("overlayProgress"),
  pipelineSteps: $("pipelineSteps"),
  statusPill: $("statusPill"),
  uploadProgress: $("uploadProgress"),
  uploadFill: $("uploadFill"),
  uploadText: $("uploadText"),
  recentProjectsSection: $("recentProjectsSection"),
  recentProjects: $("recentProjects"),
  toastStack: $("toastStack"),
};

let projectId = null;
let selectedFile = null;
let exportUrl = null;
let originalUrl = null;
let showingOriginal = false;
let selectedStyle = "hype";
let selectedCreators = [];
let pollTimer = null;
let lastJobMessage = "";
let systemReady = false;
let activeJobId = null;
let setupChecks = [];
let installPollTimer = null;
let activeInstallKey = null;
let latestUpdateInfo = null;
let updatePollTimer = null;

document.addEventListener("DOMContentLoaded", () => {
  checkSetup();
  bindEvents();
  loadRecentProjects();
  pollOllamaReady();
  analyzeUserPatterns();
});
window.addEventListener("pywebviewready", () => {
  checkSetup();
  loadRecentProjects();
  pollOllamaReady();
  analyzeUserPatterns();
});

function hasNativeApi() {
  return Boolean(window.pywebview?.api);
}

function normalizeSetup(data) {
  const dependencies = data.dependencies || {};
  const checks = data.checks || [
    { name: "Python runtime", ok: dependencies.python !== false, required: true, detail: "Installed" },
    { name: "Python packages", ok: dependencies.packages !== false, required: true, detail: "Installed" },
    { name: "FFmpeg", ok: dependencies.ffmpeg !== false, required: true, detail: dependencies.ffmpeg === false ? "Not found" : "Installed" },
  ];
  const ready = data.ready ?? checks.every((c) => !c.required || c.ok);
  return { ready, checks };
}

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

function validTimelineClips(clips) {
  if (!Array.isArray(clips)) return [];
  return clips.filter((clip) => {
    if (!clip || typeof clip.start !== "number" || typeof clip.end !== "number") return false;
    return Number.isFinite(clip.start) && Number.isFinite(clip.end) && clip.end > clip.start;
  });
}

function clearTimelineStats() {
  els.statsRow.hidden = true;
  els.statClips.textContent = "0";
  els.statDuration.textContent = "0s";
  els.statEffects.textContent = "0";
}

function updateTimelineFromPlan(plan) {
  const clips = validTimelineClips(plan?.clips);
  renderTimeline(clips);
  if (!clips.length) {
    clearTimelineStats();
    return;
  }

  els.statsRow.hidden = false;
  els.statClips.textContent = clips.length;
  els.statDuration.textContent = `${Math.round(plan?.target_duration || 0)}s`;
  els.statEffects.textContent = Array.isArray(plan?.effects) ? plan.effects.length : 0;
}

function showProjectSummary(project) {
  const plan = project.edit_plan || {};
  const projectName = project.file_name || project.id || "Untitled project";
  const projectStatus = project.status || "saved";
  const hasMatchingOriginal = Boolean(originalUrl && selectedFile?.name && project.file_name && selectedFile.name === project.file_name);
  els.researchPanel.hidden = true;
  els.researchList.innerHTML = "";
  showingOriginal = false;
  els.btnCompare.textContent = "Before / After";
  els.btnCompare.disabled = true;
  log(`Recovered project <strong>${escapeHtml(projectName)}</strong> (${escapeHtml(projectStatus)})`, "ai");

  if (project.export_path) {
    exportUrl = pathToFileUrl(project.export_path);
    els.preview.src = exportUrl + "?t=" + Date.now();
    els.preview.style.display = "block";
    els.placeholder.style.display = "none";
    els.btnExport.disabled = false;
    els.btnCompare.disabled = !hasMatchingOriginal;
  } else {
    exportUrl = null;
    els.btnExport.disabled = true;
    if (hasMatchingOriginal) {
      els.preview.src = originalUrl;
      els.preview.style.display = "block";
      els.placeholder.style.display = "none";
    } else {
      els.preview.removeAttribute("src");
      els.preview.style.display = "none";
      els.placeholder.style.display = "flex";
    }
  }

  updateTimelineFromPlan(plan);
}

function bindEvents() {
  els.dropZone.addEventListener("click", () => {
    if (hasNativeApi() && typeof window.pywebview.api.select_video_file === "function") {
      selectNativeVideoFile();
      return;
    }
    els.fileInput.click();
  });
  els.dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    els.dropZone.classList.add("dragover");
  });
  els.dropZone.addEventListener("dragleave", () => els.dropZone.classList.remove("dragover"));
  els.dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    els.dropZone.classList.remove("dragover");
    if (e.dataTransfer.files[0]) pickFile(e.dataTransfer.files[0]);
  });
  els.fileInput.addEventListener("change", () => {
    if (els.fileInput.files[0]) pickFile(els.fileInput.files[0]);
  });
  els.gameName.addEventListener("input", setReady);
  els.targetDuration.addEventListener("input", () => {
    els.durationVal.textContent = `${els.targetDuration.value}s`;
    els.targetDurationInput.value = els.targetDuration.value;
  });
  els.targetDurationInput.addEventListener("input", () => {
    const val = parseInt(els.targetDurationInput.value) || 60;
    els.targetDuration.value = Math.min(Math.max(val, 15), 7200);
    els.durationVal.textContent = `${val}s`;
  });
  els.btnAiEdit.addEventListener("click", startAiEdit);
  els.btnUpdate.addEventListener("click", checkForUpdates);
  els.btnExport.addEventListener("click", exportVideo);
  els.btnCompare.addEventListener("click", toggleCompare);
  els.btnSplit.addEventListener("click", splitClipAtPlayhead);
  els.btnDeleteLeft.addEventListener("click", deleteLeftOfPlayhead);
  els.btnDeleteRight.addEventListener("click", deleteRightOfPlayhead);
  els.btnDelete.addEventListener("click", deleteSelectedClip);
  els.btnReverse.addEventListener("click", reverseClip);
  els.btnSpeed.addEventListener("click", showSpeedControl);
  els.exportPlatform.addEventListener("change", applyPlatformPreset);
  els.btnDownloadUpdate.addEventListener("click", downloadLatestUpdate);
  els.btnUpdateClose.addEventListener("click", () => {
    clearInterval(updatePollTimer);
    els.updateOverlay.hidden = true;
  });
  els.btnSetupDismiss.addEventListener("click", () => {
    checkSetup();
  });
  els.setupList.addEventListener("click", (event) => {
    const installButton = event.target.closest("[data-install-key]");
    const openButton = event.target.closest("[data-open-key]");
    if (installButton) {
      startDependencyInstall(installButton.dataset.installKey);
    } else if (openButton) {
      openDependencyPage(openButton.dataset.openKey, openButton.dataset.url);
    }
  });

  document.querySelectorAll(".style-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      document.querySelectorAll(".style-chip").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      selectedStyle = chip.dataset.style;
    });
  });

  document.querySelectorAll(".creator-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      chip.classList.toggle("active");
      const creator = chip.dataset.creator;
      if (chip.classList.contains("active")) {
        if (!selectedCreators.includes(creator)) selectedCreators.push(creator);
      } else {
        selectedCreators = selectedCreators.filter((c) => c !== creator);
      }
    });
  });
}

async function checkSetup() {
  try {
    let data;
    if (hasNativeApi()) {
      data = JSON.parse(await window.pywebview.api.get_setup_status());
    } else {
      data = await fetch("/api/setup").then((r) => r.json());
    }
    const setup = normalizeSetup(data);
    systemReady = setup.ready;
    setupChecks = setup.checks;
    renderSetupList(setup.checks);
    updateStatusPill(setup.ready, setup.checks);
    els.setupOverlay.hidden = setup.ready;
  } catch {
    systemReady = false;
    const checks = [{
      name: "App connection",
      ok: false,
      required: true,
      detail: "Desktop bridge or local server is unavailable",
      fix: "Restart the app",
    }];
    renderSetupList(checks);
    updateStatusPill(false, checks);
    els.setupOverlay.hidden = false;
  }
}

function renderSetupList(checks) {
  els.setupList.innerHTML = checks.map((c) => {
    const cls = c.ok ? "ok" : (c.required ? "fail" : "warn");
    const icon = c.ok ? "OK" : (c.required ? "X" : "!");
    const actions = c.ok ? "" : `<div class="dependency-actions">
        ${c.installable ? `<button class="dependency-action" type="button" data-install-key="${escapeAttr(c.key)}">${escapeHtml(c.install_label || "Install")}</button>` : ""}
        ${c.download_url ? `<button class="dependency-action ghost" type="button" data-open-key="${escapeAttr(c.key)}" data-url="${escapeAttr(c.download_url)}">Manual download</button>` : ""}
      </div>
      <div class="install-status" data-install-status="${escapeAttr(c.key)}" hidden></div>`;
    return `<li class="${cls}">
      <span class="check-icon">${icon}</span>
      <div>
        <strong>${escapeHtml(c.name)}</strong>${c.required ? "" : " (optional)"}
        <span class="fix">${escapeHtml(c.ok ? c.detail : (c.fix || c.detail || ""))}</span>
        ${actions}
      </div>
    </li>`;
  }).join("");
}

async function startDependencyInstall(key) {
  const check = setupChecks.find((item) => item.key === key);
  if (!hasNativeApi()) {
    if (check?.download_url) window.open(check.download_url, "_blank", "noopener");
    toast("Open the download page, then refresh setup.", "error");
    return;
  }

  clearInterval(installPollTimer);
  activeInstallKey = key;
  setInstallStatus(key, 1, "Starting installer...");
  setDependencyButtonsDisabled(true);

  try {
    const queued = JSON.parse(await window.pywebview.api.install_dependency(key));
    installPollTimer = setInterval(async () => {
      try {
        const status = JSON.parse(await window.pywebview.api.get_install_status(queued.job_id));
        setInstallStatus(key, status.progress || 0, status.message || "Installing...");

        if (status.status === "completed") {
          clearInterval(installPollTimer);
          setDependencyButtonsDisabled(false);
          toast("FFmpeg installed");
          await checkSetup();
        } else if (status.status === "failed") {
          clearInterval(installPollTimer);
          setDependencyButtonsDisabled(false);
          toast(status.message || "Install failed", "error");
          setInstallStatus(key, status.progress || 0, status.message || "Install failed");
        }
      } catch (err) {
        clearInterval(installPollTimer);
        setDependencyButtonsDisabled(false);
        toast(err.message || "Install failed", "error");
      }
    }, 900);
  } catch (err) {
    setDependencyButtonsDisabled(false);
    toast(err.message || "Install failed", "error");
  }
}

async function openDependencyPage(key, url) {
  if (hasNativeApi()) {
    await window.pywebview.api.open_dependency_page(key);
  } else if (url) {
    window.open(url, "_blank", "noopener");
  }
}

function setDependencyButtonsDisabled(disabled) {
  els.setupList.querySelectorAll(".dependency-action").forEach((button) => {
    button.disabled = disabled;
  });
}

function setInstallStatus(key, progress, message) {
  const statusEl = els.setupList.querySelector(`[data-install-status="${cssEscape(key)}"]`);
  if (!statusEl) return;
  statusEl.hidden = false;
  statusEl.textContent = `${Math.max(0, Math.min(100, Math.round(progress)))}% - ${message}`;
}

function updateStatusPill(ready, checks) {
  const missing = checks.filter((c) => c.required && !c.ok);
  if (ready) {
    els.statusPill.innerHTML = '<span class="dot"></span> Ready';
    els.statusPill.className = "status-pill ready";
  } else {
    els.statusPill.innerHTML = `<span class="dot"></span> ${escapeHtml(missing[0]?.name || "Setup")} needed`;
    els.statusPill.className = "status-pill warn";
  }
}

let _ollamaPollTimer = null;
let _ollamaReady = false;

function pollOllamaReady() {
  if (!hasNativeApi()) return;
  if (_ollamaReady) return;

  // Show warming up indicator
  const pill = els.statusPill;
  if (pill.classList.contains("ready")) {
    pill.innerHTML = '<span class="dot"></span> AI warming up...';
    pill.className = "status-pill warn";
  }

  clearInterval(_ollamaPollTimer);
  _ollamaPollTimer = setInterval(async () => {
    try {
      const data = JSON.parse(await window.pywebview.api.get_ollama_status());
      if (data.ready) {
        clearInterval(_ollamaPollTimer);
        _ollamaReady = true;
        if (systemReady) {
          els.statusPill.innerHTML = '<span class="dot"></span> Ready';
          els.statusPill.className = "status-pill ready";
        }
        log("AI model ready.", "ai");
      }
    } catch {
      clearInterval(_ollamaPollTimer);
    }
  }, 1500);
}

async function analyzeUserPatterns() {
  if (!hasNativeApi()) return;
  
  try {
    const patterns = JSON.parse(await window.pywebview.api.analyze_upload_patterns());
    
    if (patterns.total_projects > 0) {
      // Auto-select suggested creators based on patterns
      if (patterns.suggested_creators && patterns.suggested_creators.length > 0) {
        selectedCreators = [];
        document.querySelectorAll(".creator-chip").forEach(chip => {
          chip.classList.remove("active");
          if (patterns.suggested_creators.includes(chip.dataset.creator)) {
            chip.classList.add("active");
            selectedCreators.push(chip.dataset.creator);
          }
        });
        
        if (patterns.dominant_game) {
          log(`Detected you mainly play <strong>${escapeHtml(patterns.dominant_game)}</strong>. Auto-selected creators: ${patterns.suggested_creators.join(", ")}`, "ai");
        }
      }
      
      // Auto-fill game name if dominant pattern detected
      if (patterns.dominant_game && !els.gameName.value.trim()) {
        els.gameName.value = patterns.dominant_game.charAt(0).toUpperCase() + patterns.dominant_game.slice(1);
        setReady();
      }
    }
  } catch (err) {
    // Pattern analysis is optional, don't show error
    console.log("Pattern analysis not available yet");
  }
}

function log(msg, type = "ai") {
  const el = document.createElement("div");
  el.className = `ai-msg ${type}`;
  el.innerHTML = msg;
  els.aiLog.appendChild(el);
  els.aiLog.scrollTop = els.aiLog.scrollHeight;
}

function toast(msg, type = "success") {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = msg;
  els.toastStack.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

function setReady() {
  els.btnAiEdit.disabled = !(selectedFile && els.gameName.value.trim());
}

function formatBytes(n) {
  if (n < 1024) return n + " B";
  if (n < 1048576) return (n / 1024).toFixed(1) + " KB";
  if (n < 1073741824) return (n / 1048576).toFixed(1) + " MB";
  return (n / 1073741824).toFixed(2) + " GB";
}

function clearFallbackSelection() {
  selectedFile = null;
  if (originalUrl) URL.revokeObjectURL(originalUrl);
  originalUrl = null;
  els.fileInput.value = "";
  els.dropZone.querySelector(".drop-title").textContent = "Drop video here";
  els.btnCompare.disabled = true;
  if (exportUrl) {
    els.preview.src = exportUrl;
    els.preview.style.display = "block";
    els.placeholder.style.display = "none";
  } else {
    els.preview.removeAttribute("src");
    els.preview.style.display = "none";
    els.placeholder.style.display = "flex";
  }
  setReady();
}

async function selectNativeVideoFile() {
  if (!els.gameName.value.trim()) {
    toast("Enter a game name before choosing a desktop file", "error");
    els.gameName.focus();
    return;
  }
  if (!systemReady) await checkSetup();
  if (!systemReady) {
    toast("Setup still needs attention", "error");
    els.setupOverlay.hidden = false;
    return;
  }

  els.dropZone.classList.add("busy");

  try {
    const editOptions = collectEditOptions();
    const queued = JSON.parse(await window.pywebview.api.select_video_file(JSON.stringify(editOptions)));
    if (queued.status === "cancelled") return;
    if (!queued.job_id) throw new Error(queued.message || "No render job was started");

    selectedFile = null;
    if (originalUrl) URL.revokeObjectURL(originalUrl);
    originalUrl = null;
    exportUrl = null;
    showingOriginal = false;
    activeJobId = queued.job_id;
    projectId = queued.project_id || null;

    // Capture first frame of the selected video for Before/After compare
    if (hasNativeApi() && typeof window.pywebview.api.capture_first_frame === "function") {
      try {
        const frameData = JSON.parse(await window.pywebview.api.capture_first_frame(selected_paths?.[0] || ""));
        if (frameData.data_url) {
          originalUrl = frameData.data_url;
        }
      } catch {
        // Non-fatal — Before/After just won't be available
      }
    }

    els.btnAiEdit.disabled = true;
    els.btnExport.disabled = true;
    els.btnCompare.disabled = true;
    els.preview.removeAttribute("src");
    els.preview.style.display = "none";
    els.placeholder.style.display = "flex";
    els.dropZone.querySelector(".drop-title").textContent = queued.file_name || "Desktop video selected";
    els.processOverlay.hidden = false;
    els.overlayProgress.style.width = "0%";
    setPipelineStep("analyze");

    log(`Starting AI edit for <strong>${escapeHtml(els.gameName.value.trim())}</strong>...`, "user");
    log("Desktop file selected. Analyzing your gameplay...");
    pollJob(activeJobId);
  } catch (err) {
    log(escapeHtml(err.message || String(err)), "error");
    toast(err.message || "Edit failed", "error");
    els.processOverlay.hidden = true;
    setReady();
  } finally {
    els.dropZone.classList.remove("busy");
  }
}

function pickFile(file) {
  selectedFile = file;
  if (originalUrl) URL.revokeObjectURL(originalUrl);
  originalUrl = URL.createObjectURL(file);
  els.preview.src = originalUrl;
  els.preview.style.display = "block";
  els.placeholder.style.display = "none";
  els.dropZone.querySelector(".drop-title").textContent = file.name;
  log(`Loaded <strong>${escapeHtml(file.name)}</strong> (${formatBytes(file.size)})`, "user");
  toast("Video loaded");
  setReady();
}

function uploadWithProgress(form) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable) {
        const pct = (e.loaded / e.total) * 100;
        els.uploadProgress.hidden = false;
        els.uploadFill.style.width = `${pct}%`;
        els.uploadText.textContent = `Uploading... ${formatBytes(e.loaded)} / ${formatBytes(e.total)}`;
      }
    });
    xhr.addEventListener("load", () => {
      els.uploadProgress.hidden = true;
      if (xhr.status >= 200 && xhr.status < 300) resolve(JSON.parse(xhr.responseText));
      else reject(new Error(xhr.responseText || `Upload failed (${xhr.status})`));
    });
    xhr.addEventListener("error", () => reject(new Error("Network error")));
    xhr.open("POST", "/api/projects");
    xhr.send(form);
  });
}

function setPipelineStep(step) {
  const map = { analyze: 0, transcribe: 1, research: 2, plan: 3, render: 4 };
  const idx = map[step] ?? -1;
  els.pipelineSteps.querySelectorAll(".step").forEach((el, i) => {
    el.classList.remove("active", "done");
    if (i < idx) el.classList.add("done");
    else if (i === idx) el.classList.add("active");
  });
}

function progressToStep(pct) {
  if (pct < 15) setPipelineStep("analyze");
  else if (pct < 30) setPipelineStep("transcribe");
  else if (pct < 55) setPipelineStep("research");
  else if (pct < 75) setPipelineStep("plan");
  else setPipelineStep("render");
}

function collectEditOptions() {
  return {
    game_name: els.gameName.value.trim(),
    style: selectedStyle,
    target_duration: Number(els.targetDuration.value),
    add_subtitles: $("addSubtitles").checked,
    add_effects: $("addEffects").checked,
    use_whisper: $("useWhisper").checked,
    remove_silence: els.removeSilence.checked,
    remove_fillers: els.removeFillers.checked,
    jump_cuts: els.jumpCuts.checked,
    export_resolution: els.exportResolution.value,
    export_fps: parseInt(els.exportFps.value) || 30,
    export_aspect_ratio: els.exportAspectRatio.value,
    audience: selectedCreators.slice(),
  };
}

async function startAiEdit() {
  if (!selectedFile || !els.gameName.value.trim()) return;
  if (!systemReady) await checkSetup();
  if (!systemReady) {
    toast("Setup still needs attention", "error");
    els.setupOverlay.hidden = false;
    return;
  }

  els.btnAiEdit.disabled = true;
  els.btnExport.disabled = true;
  els.btnCompare.disabled = true;
  exportUrl = null;
  els.processOverlay.hidden = false;
  els.overlayProgress.style.width = "0%";
  setPipelineStep("analyze");

  log(`Starting AI edit for <strong>${escapeHtml(els.gameName.value.trim())}</strong>...`, "user");

  try {
    const editOptions = collectEditOptions();
    if (hasNativeApi()) {
      const payload = await readFileAsDataUrl(selectedFile);
      const queued = JSON.parse(await window.pywebview.api.process_video_upload(selectedFile.name, payload, JSON.stringify(editOptions)));
      activeJobId = queued.job_id;
      log("Footage loaded into the editor. Analyzing your gameplay...");
      pollJob(activeJobId);
      return;
    }

    const form = new FormData();
    form.append("file", selectedFile);
    form.append("game_name", editOptions.game_name);
    form.append("style", editOptions.style);
    form.append("target_duration", editOptions.target_duration);
    form.append("add_subtitles", editOptions.add_subtitles);
    form.append("add_effects", editOptions.add_effects);
    form.append("use_whisper", editOptions.use_whisper);

    const proj = await uploadWithProgress(form);
    projectId = proj.project?.id || proj.id;
    activeJobId = proj.job_id;
    log("Footage uploaded. Analyzing your gameplay...");

    if (activeJobId) {
      pollJob(activeJobId);
      return;
    }

    const editForm = new FormData();
    editForm.append("project_id", projectId);
    editForm.append("add_subtitles", $("addSubtitles").checked);
    editForm.append("add_effects", $("addEffects").checked);
    editForm.append("auto_cut", true);
    editForm.append("use_whisper", $("useWhisper").checked);
    editForm.append("target_duration", els.targetDuration.value);

    const { job_id } = await fetch("/api/edit", { method: "POST", body: editForm }).then((r) => r.json());
    activeJobId = job_id;
    pollJob(job_id);
  } catch (err) {
    log(escapeHtml(err.message || String(err)), "error");
    toast(err.message || "Edit failed", "error");
    els.btnAiEdit.disabled = false;
    els.processOverlay.hidden = true;
  }
}

function readFileAsDataUrl(file) {
  els.uploadProgress.hidden = false;
  els.uploadFill.style.width = "35%";
  els.uploadText.textContent = "Loading video into editor...";
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => {
      els.uploadFill.style.width = "100%";
      els.uploadText.textContent = "Video loaded";
      setTimeout(() => { els.uploadProgress.hidden = true; }, 500);
      resolve(reader.result);
    });
    reader.addEventListener("error", () => reject(new Error("Could not read the selected video")));
    reader.readAsDataURL(file);
  });
}

function pollJob(jobId) {
  clearInterval(pollTimer);
  lastJobMessage = "";
  pollTimer = setInterval(async () => {
    try {
      const job = hasNativeApi()
        ? JSON.parse(await window.pywebview.api.get_job_status(jobId))
        : await fetch(`/api/jobs/${jobId}`).then((r) => r.json());
      els.overlayProgress.style.width = `${job.progress}%`;
      els.processSub.textContent = job.message;
      progressToStep(job.progress);

      if (job.message && job.message !== lastJobMessage) {
        lastJobMessage = job.message;
        log(escapeHtml(job.message));
      }

      if (job.status === "done" || job.status === "completed") {
        clearInterval(pollTimer);
        finishEdit(job, jobId);
      } else if (job.status === "error" || job.status === "failed") {
        clearInterval(pollTimer);
        log(escapeHtml(job.message), "error");
        toast(job.message, "error");
        setReady();
        els.processOverlay.hidden = true;
      }
    } catch (err) {
      log(escapeHtml(err.message || String(err)), "error");
    }
  }, 1200);
}

async function finishEdit(job, jobId) {
  const r = job.result || {};
  let exportPath = null;
  
  if (typeof r === "string") {
    exportPath = r;
  } else {
    exportPath = r.export_path || r.export_url;
  }

  // Get proper file URL from native API
  if (hasNativeApi() && exportPath) {
    try {
      const urlData = JSON.parse(await window.pywebview.api.get_file_url(exportPath));
      exportUrl = urlData.url || exportPath;
    } catch {
      exportUrl = pathToFileUrl(exportPath);
    }
  } else {
    exportUrl = exportPath ? pathToFileUrl(exportPath) : `/api/export/${jobId}`;
  }

  els.processOverlay.hidden = true;
  els.pipelineSteps.querySelectorAll(".step").forEach((el) => el.classList.add("done"));

  // Show YouTube research results
  if (r.research) {
    const researchData = r.research;
    if (researchData.summary) {
      log(escapeHtml(researchData.summary), "ai");
    }
    const refVideos = researchData.reference_videos || [];
    if (refVideos.length > 0) {
      els.researchPanel.hidden = false;
      els.researchList.innerHTML = "";
      refVideos.slice(0, 6).forEach((v) => {
        const div = document.createElement("div");
        div.className = "ref-item";
        const link = document.createElement("a");
        const url = safeHttpUrl(v.url);
        link.textContent = v.title || "Reference video";
        if (url) {
          link.href = url;
          link.target = "_blank";
          link.rel = "noopener";
        }
        const meta = document.createElement("div");
        meta.className = "views";
        meta.textContent = `${v.channel || "Unknown channel"} — ${(v.view_count || 0).toLocaleString()} views`;
        div.appendChild(link);
        div.appendChild(meta);
        els.researchList.appendChild(div);
      });
    }
  }

  // Show AI edit notes
  const plan = r.edit_plan || {};
  
  // Store edit plan globally for export naming
  window.currentEditPlan = plan;
  
  if (plan.edit_notes && plan.edit_notes !== "Rule-based plan (GPT unavailable).") {
    log(`AI edit plan: ${escapeHtml(plan.edit_notes)}`, "ai");
  }
  if (plan.style_signals && plan.style_signals.length > 0) {
    log(`Style signals: ${escapeHtml(plan.style_signals.slice(0, 5).join(", "))}`, "ai");
  }
  if (plan.suggested_title) {
    log(`AI suggested title: "${escapeHtml(plan.suggested_title)}"`, "ai");
  }

  if (r.edit_plan) updateTimelineFromPlan(r.edit_plan);

  if (exportUrl) {
    els.preview.src = exportUrl + (exportUrl.includes("?") ? "&" : "?") + "t=" + Date.now();
    els.preview.style.display = "block";
    els.placeholder.style.display = "none";
    els.btnExport.disabled = false;
    els.btnCompare.disabled = !originalUrl;
    log("Your AI edit is ready. Preview above or hit <strong>Export</strong>.", "ai");
    toast("Edit complete!");

    // Show thumbnail link if generated
    if (r.thumbnail_path) {
      const thumbUrl = pathToFileUrl(r.thumbnail_path);
      log(`Thumbnail saved — <a href="${thumbUrl}" target="_blank" rel="noopener" style="color:var(--accent)">open thumbnail</a>`, "ai");
    }
  }

  setReady();
  loadRecentProjects();
}

async function checkForUpdates() {
  if (!hasNativeApi()) {
    toast("Updates are only available in the desktop app", "error");
    return;
  }

  try {
    els.btnUpdate.disabled = true;
    const info = JSON.parse(await window.pywebview.api.check_for_updates());
    latestUpdateInfo = info;

    if (!info.enabled) {
      toast(info.message || "No update feed configured", "error");
      log("Update feed is not configured yet. Add an update_config.json manifest URL before selling builds.", "ai");
      return;
    }

    if (!info.update_available) {
      toast(info.message || "You are up to date");
      return;
    }

    els.updateTitle.textContent = `Version ${info.latest_version} available`;
    els.updateSub.textContent = `You are running ${info.current_version}.`;
    els.updateNotes.textContent = info.notes || "Download the latest version to update.";
    els.updateProgress.hidden = true;
    els.updateFill.style.width = "0%";
    els.btnDownloadUpdate.disabled = false;
    els.updateOverlay.hidden = false;
  } catch (err) {
    toast(err.message || "Update check failed", "error");
  } finally {
    els.btnUpdate.disabled = false;
  }
}

async function downloadLatestUpdate() {
  if (!latestUpdateInfo || !latestUpdateInfo.update_available) return;
  clearInterval(updatePollTimer);
  els.btnDownloadUpdate.disabled = true;
  els.updateProgress.hidden = false;
  els.updateFill.style.width = "1%";
  els.updateText.textContent = "Starting update download...";

  try {
    const queued = JSON.parse(await window.pywebview.api.download_update(JSON.stringify(latestUpdateInfo)));
    updatePollTimer = setInterval(async () => {
      try {
        const status = JSON.parse(await window.pywebview.api.get_update_status(queued.job_id));
        const progress = Math.max(0, Math.min(100, Math.round(status.progress || 0)));
        els.updateFill.style.width = `${progress}%`;
        els.updateText.textContent = status.message || "Downloading update...";

        if (status.status === "completed") {
          clearInterval(updatePollTimer);
          els.btnDownloadUpdate.disabled = false;
          toast("Update downloaded");
          if (status.result?.path) {
            els.updateText.textContent = "Opening update installer...";
            await window.pywebview.api.open_update_file(status.result.path);
            // Give the OS a moment to launch the installer, then close the overlay
            setTimeout(() => { els.updateOverlay.hidden = true; }, 1500);
          }
        } else if (status.status === "failed") {
          clearInterval(updatePollTimer);
          els.btnDownloadUpdate.disabled = false;
          toast(status.message || "Update download failed", "error");
        }
      } catch (err) {
        clearInterval(updatePollTimer);
        els.btnDownloadUpdate.disabled = false;
        toast(err.message || "Update download failed", "error");
      }
    }, 900);
  } catch (err) {
    els.btnDownloadUpdate.disabled = false;
    toast(err.message || "Update download failed", "error");
  }
}

function pathToFileUrl(path) {
  const normalized = String(path).replace(/\\/g, "/");
  const parts = normalized.split("/");
  const encoded = parts.map((part, index) => {
    if (index === 0 && /^[A-Za-z]:$/.test(part)) return part;
    return encodeURIComponent(part);
  });
  return "file:///" + encoded.join("/");
}

function renderTimeline(clips) {
  clips = validTimelineClips(clips);
  els.timelineTrack.innerHTML = "";
  els.timelineRuler.innerHTML = "";
  if (!clips.length) {
    els.timelineMeta.textContent = "No clips yet";
    return;
  }

  const total = clips.reduce((s, c) => s + (c.end - c.start), 0);
  els.timelineMeta.textContent = `${clips.length} clips - ${total.toFixed(1)}s total`;

  for (let t = 0; t <= total; t += Math.max(2, total / 8)) {
    const tick = document.createElement("span");
    tick.className = "tick";
    tick.style.left = `${(t / total) * 100}%`;
    tick.textContent = `${t.toFixed(0)}s`;
    els.timelineRuler.appendChild(tick);
  }

  clips.forEach((c, i) => {
    const w = Math.max(48, ((c.end - c.start) / total) * 500);
    const div = document.createElement("div");
    div.className = "clip-block";
    div.style.width = `${w}px`;
    div.style.animationDelay = `${i * 0.05}s`;
    div.innerHTML = `<span>#${i + 1}</span><span class="clip-fx">${escapeHtml(c.effect || "cut")}</span>`;
    div.title = `${c.effect} - ${c.transition} - ${(c.end - c.start).toFixed(1)}s`;
    els.timelineTrack.appendChild(div);
  });
}

function toggleCompare() {
  if (!exportUrl || !originalUrl) return;
  showingOriginal = !showingOriginal;
  els.preview.src = showingOriginal ? originalUrl : exportUrl + "?t=" + Date.now();
  els.btnCompare.textContent = showingOriginal ? "Show AI Edit" : "Before / After";
}

// Manual editing tools (CapCut-style)
let currentClips = [];
let selectedClipIndex = -1;

function renderTimeline(clips) {
  clips = validTimelineClips(clips);
  currentClips = clips;
  selectedClipIndex = -1;
  els.timelineTrack.innerHTML = "";
  els.timelineRuler.innerHTML = "";

  if (!clips.length) {
    els.timelineMeta.textContent = "No clips yet";
    return;
  }

  const total = clips.reduce((s, c) => s + (c.end - c.start), 0);
  els.timelineMeta.textContent = `${clips.length} clips — ${total.toFixed(1)}s total`;

  // Ruler ticks
  const tickCount = Math.min(10, Math.ceil(total));
  const tickInterval = total / Math.max(tickCount - 1, 1);
  for (let i = 0; i <= tickCount - 1; i++) {
    const t = i * tickInterval;
    const tick = document.createElement("span");
    tick.className = "tick";
    tick.style.left = `${(t / total) * 100}%`;
    tick.textContent = `${t.toFixed(0)}s`;
    els.timelineRuler.appendChild(tick);
  }

  // Clip blocks
  clips.forEach((c, i) => {
    const dur = c.end - c.start;
    const widthPct = (dur / total) * 100;
    const div = document.createElement("div");
    div.className = "clip-block";
    div.style.width = `${Math.max(3, widthPct)}%`;
    div.style.animationDelay = `${i * 0.05}s`;
    div.dataset.index = i;
    div.innerHTML = `<span>#${i + 1}</span><span class="clip-fx">${escapeHtml(c.effect || "cut")}</span>`;
    div.title = `${escapeHtml(c.effect || "cut")} — ${dur.toFixed(1)}s (${c.start.toFixed(1)}s–${c.end.toFixed(1)}s)`;
    div.addEventListener("click", () => {
      els.timelineTrack.querySelectorAll(".clip-block").forEach(b => b.classList.remove("selected"));
      div.classList.add("selected");
      selectedClipIndex = i;
      if (exportUrl) {
        els.preview.currentTime = c.start;
      }
    });
    els.timelineTrack.appendChild(div);
  });
}

function splitClipAtPlayhead() {
  if (!exportUrl) { toast("No video loaded", "error"); return; }
  const t = els.preview.currentTime;
  const idx = selectedClipIndex >= 0 ? selectedClipIndex :
    currentClips.findIndex(c => t >= c.start && t <= c.end);
  if (idx < 0) { toast("Seek to a point inside a clip to split", "error"); return; }
  const clip = currentClips[idx];
  if (t <= clip.start + 0.5 || t >= clip.end - 0.5) {
    toast("Too close to clip edge to split"); return;
  }
  const left  = { ...clip, end: t };
  const right = { ...clip, start: t };
  currentClips.splice(idx, 1, left, right);
  renderTimeline(currentClips);
  updateTimelineFromPlan({ clips: currentClips, target_duration: currentClips.reduce((s,c)=>s+(c.end-c.start),0), effects: [] });
  log(`Split clip #${idx + 1} at ${t.toFixed(2)}s`, "ai");
  toast("Clip split");
}

function deleteLeftOfPlayhead() {
  if (!exportUrl) { toast("No video loaded", "error"); return; }
  const t = els.preview.currentTime;
  currentClips = currentClips.filter(c => c.end > t).map(c => c.start < t ? { ...c, start: t } : c);
  renderTimeline(currentClips);
  log(`Deleted everything left of ${t.toFixed(2)}s`, "ai");
  toast("Deleted left");
}

function deleteRightOfPlayhead() {
  if (!exportUrl) { toast("No video loaded", "error"); return; }
  const t = els.preview.currentTime;
  currentClips = currentClips.filter(c => c.start < t).map(c => c.end > t ? { ...c, end: t } : c);
  renderTimeline(currentClips);
  log(`Deleted everything right of ${t.toFixed(2)}s`, "ai");
  toast("Deleted right");
}

function deleteSelectedClip() {
  if (selectedClipIndex < 0 || selectedClipIndex >= currentClips.length) {
    toast("Select a clip first", "error"); return;
  }
  currentClips.splice(selectedClipIndex, 1);
  selectedClipIndex = -1;
  renderTimeline(currentClips);
  log("Clip deleted", "ai");
  toast("Clip deleted");
}

function reverseClip() {
  if (!exportUrl) { toast("No video loaded", "error"); return; }
  toast("Reverse requires re-render — this marks the clip for reversal", "success");
  if (selectedClipIndex >= 0) {
    currentClips[selectedClipIndex] = { ...currentClips[selectedClipIndex], effect: "reverse" };
    renderTimeline(currentClips);
    log("Marked selected clip for reversal. Re-run AI Edit to apply.", "ai");
  } else {
    log("Select a clip on the timeline first, then use Reverse.", "ai");
  }
}

function showSpeedControl() {
  if (!exportUrl) { toast("No video loaded", "error"); return; }
  const newSpeed = prompt("Playback speed (0.25 – 4.0):", "1.0");
  if (newSpeed === null) return;
  const parsed = parseFloat(newSpeed);
  if (isNaN(parsed) || parsed < 0.25 || parsed > 4.0) {
    toast("Enter a value between 0.25 and 4.0", "error"); return;
  }
  els.preview.playbackRate = parsed;
  log(`Preview speed: ${parsed}x (re-render to bake into export)`, "ai");
  toast(`Speed: ${parsed}x`);
}

function applyPlatformPreset() {
  const platform = els.exportPlatform.value;
  if (platform === "custom") return;

  const presets = {
    youtube:   { aspectRatio: "16:9", resolution: "1080p", fps: "30" },
    tiktok:    { aspectRatio: "9:16", resolution: "1080p", fps: "30" },
    instagram: { aspectRatio: "1:1",  resolution: "1080p", fps: "30" },
  };

  const preset = presets[platform];
  if (preset) {
    els.exportAspectRatio.value = preset.aspectRatio;
    els.exportResolution.value  = preset.resolution;
    els.exportFps.value         = preset.fps;
    log(`Applied ${platform} preset: ${preset.resolution} ${preset.aspectRatio} ${preset.fps}fps`, "ai");
    toast(`Preset: ${platform}`);
  }
}

function exportVideo() {
  if (!exportUrl) return;
  const a = document.createElement("a");
  a.href = exportUrl;

  const suggestedTitle = window.currentEditPlan?.suggested_title;
  const baseName = suggestedTitle || els.gameName.value.trim() || "edit";
  const safeName = baseName.replace(/[^a-zA-Z0-9\s\-_]/g, "").trim() || "edit";

  const platform = els.exportPlatform.value;
  const resolution = els.exportResolution.value;
  const fps = els.exportFps.value;
  const aspect = els.exportAspectRatio.value.replace(":", "x");
  a.download = `${safeName}_${platform}_${resolution}_${aspect}_${fps}fps.mp4`;

  log(`Exporting for ${platform}: ${resolution} ${aspect} ${fps}fps`, "ai");
  a.click();
  toast("Download started");
}

function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function escapeAttr(s) {
  return escapeHtml(s).replace(/"/g, "&quot;");
}

function safeHttpUrl(url) {
  try {
    const parsed = new URL(String(url || ""));
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : "";
  } catch {
    return "";
  }
}

function cssEscape(s) {
  if (window.CSS?.escape) return CSS.escape(String(s));
  return String(s).replace(/[^a-zA-Z0-9_-]/g, "\\$&");
}

# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files
import os

# Version is injected by the CI pipeline via GAMECUT_VERSION env var.
# Locally: set GAMECUT_VERSION=0.1.1 before running pyinstaller.
# Falls back to reading from latest.json if the env var isn't set.
_app_version = os.environ.get("GAMECUT_VERSION", "0.1.0")

datas = [
    ('frontend', 'frontend'),
    ('assets', 'assets'),
]

# Include .env only if it exists and has content
if os.path.exists('.env'):
    datas.append(('.env', '.'))

binaries = []
hiddenimports = []

# OpenCV
tmp = collect_all('cv2')
datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]

# Whisper (local speech-to-text)
tmp = collect_all('whisper')
datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]

# yt-dlp (YouTube research)
tmp = collect_all('yt_dlp')
datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]

# tiktoken (used by whisper)
try:
    tmp = collect_all('tiktoken')
    datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]
except Exception:
    pass

# openai SDK
hiddenimports += collect_submodules('openai')
hiddenimports += collect_submodules('httpx')
hiddenimports += collect_submodules('httpcore')

# python-dotenv
hiddenimports += ['dotenv', 'python_dotenv']

# numpy
hiddenimports += collect_submodules('numpy')

# All backend services
hiddenimports += [
    'backend',
    'backend.services',
    'backend.services.ai_vision',
    'backend.services.audio_dsp',
    'backend.services.ai_planner',
    'backend.services.transcriber',
    'backend.services.youtube_research',
    'backend.services.pipeline',
    'backend.services.editing',
    'backend.services.edit_plan',
    'backend.services.project_store',
    'backend.services.asset_library',
    'backend.services.dependencies',
    'backend.services.updater',
    'backend.services.subtitle_animator',
    'backend.services.ollama_manager',
    'backend.services.renderer',
    'backend.services.thumbnail',
]
hiddenimports += collect_submodules('backend')


a = Analysis(
    ['gui.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['scripts/rthook_version.py'],
    excludes=['torch', 'torchvision', 'torchaudio', 'tensorflow', 'matplotlib',
              'pandas', 'scipy', 'sklearn', 'IPython', 'jupyter'],
    noarchive=False,
    optimize=0,
)

# Write the runtime hook that stamps GAMECUT_VERSION before any app code runs.
# This file is regenerated every build by gui.spec, so it always reflects the
# current GAMECUT_VERSION env var (set by CI or by the developer locally).
import pathlib
_rthook = pathlib.Path('scripts/rthook_version.py')
_rthook.parent.mkdir(exist_ok=True)
_rthook.write_text(
    f'import os\nos.environ.setdefault("GAMECUT_VERSION", "{_app_version}")\n',
    encoding='utf-8',
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='GameCutAI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

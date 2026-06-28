@echo off
cd /d "%~dp0"
title GameCut AI

set "python=C:\ml-pytorch\Miniconda3\python.exe"
set "pip=C:\ml-pytorch\Miniconda3\Scripts\pip.exe"

echo.
echo  ========================================
echo    GameCut AI - Setup Check
echo  ========================================
echo.

"%python%" --version >nul 2>&1
if errorlevel 1 (
  echo [X] Python not found at %python%. Please check the path.
  pause
  exit /b 1
)
echo [OK] Python

"%pip%" install -r requirements.txt -q
echo [OK] Python packages

"%python%" -c "from backend.services.dependencies import get_setup_payload; p=get_setup_payload(); print('[OK] FFmpeg' if p['dependencies']['ffmpeg'] else '[!] FFmpeg missing - use the setup screen to install it')"

"%python%" -c "import yt_dlp; print('[OK] yt-dlp')" 2>nul || echo [!] yt-dlp missing - run: pip install yt-dlp
"%python%" -c "import whisper; print('[OK] Whisper')" 2>nul || echo [!] Whisper missing - run: pip install openai-whisper
"%python%" -c "import openai; print('[OK] OpenAI')" 2>nul || echo [!] OpenAI missing - run: pip install openai

if not exist .env (
  echo [i] No .env found - copying .env.example
  copy .env.example .env >nul
)

"%python%" -c "
from dotenv import load_dotenv; import os; load_dotenv()
key = os.environ.get('OPENAI_API_KEY','').strip()
if key:
    print('[OK] OpenAI API key set')
else:
    print('[!] OPENAI_API_KEY is empty in .env - AI planning will use rule-based fallback')
" 2>nul

echo.
echo  Starting server at http://127.0.0.1:8765
echo  (For the desktop app, run gui.py directly with python gui.py)
echo  ========================================
echo.

cd backend
start http://127.0.0.1:8765
"%python%" -m uvicorn main:app --host 127.0.0.1 --port 8765 --reload

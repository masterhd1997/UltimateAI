import os
from pathlib import Path

# Absolute base project workspace mapping
BASE_DIR = Path(__file__).resolve().parent.parent

CHUNK_SIZE = 1024 * 1024 * 4  # 4MB Stream Buffering Optimization

UPLOAD_DIR = BASE_DIR / "data" / "uploads"
EXPORT_DIR = BASE_DIR / "data" / "exports"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(EXPORT_DIR, exist_ok=True)
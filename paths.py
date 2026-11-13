"""Lokasi file proyek, tidak bergantung pada direktori kerja saat aplikasi dijalankan."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
ASSETS_DIR = BASE_DIR / "assets"
# Lokasi database dapat diganti lewat environment variable (berguna untuk pengujian).
DB_PATH = os.environ.get("CYBERSHIELD_DB", str(BASE_DIR / "cybershield.db"))

def data_file(name: str) -> str:
    return str(DATA_DIR / name)

def asset_file(name: str) -> str:
    return str(ASSETS_DIR / name)
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = BASE_DIR / "templates"

UPLOAD_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = DATA_DIR / "outputs"
HISTORY_AUDIO_DIR = DATA_DIR / "history_audio"
HISTORY_TEXT_DIR = DATA_DIR / "history_text"
DB_PATH = DATA_DIR / "db" / "history.db"

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}

SECRET_KEY = os.getenv("SECRET_KEY", "cambia-esta-clave-por-una-larga")
APP_PORT = int(os.getenv("APP_PORT", 8000))
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE_MB", 5)) * 1024 * 1024
MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT", 10))
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "large-v3-turbo")


def ensure_dirs():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_TEXT_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
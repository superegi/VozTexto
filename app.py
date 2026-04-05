from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from faster_whisper import WhisperModel
import uuid
import logging
import sqlite3
import time
from datetime import datetime
import asyncio
import os



MAX_CONCURRENT = 10
semaphore = asyncio.Semaphore(MAX_CONCURRENT)
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voz_a_texto")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

UPLOAD_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = DATA_DIR / "outputs"
TEMPLATES_DIR = BASE_DIR / "templates"
HISTORY_AUDIO_DIR = DATA_DIR / "history_audio"
HISTORY_TEXT_DIR = DATA_DIR / "history_text"
DB_PATH = DATA_DIR / "db" / "history.db"

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)
HISTORY_AUDIO_DIR.mkdir(exist_ok=True)
HISTORY_TEXT_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Voz a Texto")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

SECRET_KEY = os.getenv("SECRET_KEY", "cambia-esta-clave-por-una-larga")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)



model = WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}


def get_logged_user(request: Request):
    return request.session.get("username")


def require_login(request: Request):
    return get_logged_user(request)


def render_index(request: Request, text=None, download_link=None, error=None):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "text": text,
            "download_link": download_link,
            "error": error,
            "username": get_logged_user(request),
        },
    )


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transcriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            description TEXT,
            speaker TEXT,
            stored_audio_path TEXT NOT NULL,
            stored_text_path TEXT NOT NULL,
            transcribed_text TEXT NOT NULL,
            file_size_bytes INTEGER NOT NULL,
            duration_seconds REAL,
            processing_seconds REAL NOT NULL,
            status TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

def save_history(
    created_at: str,
    original_filename: str,
    description: str,
    speaker: str,
    stored_audio_path: str,
    stored_text_path: str,
    transcribed_text: str,
    file_size_bytes: int,
    duration_seconds: float | None,
    processing_seconds: float,
    status: str,
):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO transcriptions (
            created_at,
            original_filename,
            description,
            speaker,
            stored_audio_path,
            stored_text_path,
            transcribed_text,
            file_size_bytes,
            duration_seconds,
            processing_seconds,
            status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        created_at,
        original_filename,
        description,
        speaker,
        stored_audio_path,
        stored_text_path,
        transcribed_text,
        file_size_bytes,
        duration_seconds,
        processing_seconds,
        status
    ))
    conn.commit()
    conn.close()


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    if get_logged_user(request):
        return RedirectResponse(url="/", status_code=302)

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "request": request,
            "error": None
        }
    )


@app.post("/login", response_class=HTMLResponse)
async def login_post(request: Request):
    form = await request.form()
    username = form.get("username", "").strip()

    if username:
        request.session["username"] = username
        return RedirectResponse(url="/", status_code=302)

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "request": request,
            "error": "Debes ingresar un nombre"
        }
    )


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    if not require_login(request):
        return RedirectResponse(url="/login", status_code=302)

    return render_index(request)



@app.post("/transcribir", response_class=HTMLResponse)
async def transcribir(
    request: Request,
    description: str = Form(""),
    speaker: str = Form(""),
    audio: UploadFile = File(...)
):

    if semaphore.locked() and semaphore._value == 0:
        return render_index(request, error="Servidor ocupado. Intenta nuevamente en unos segundos.")

    async with semaphore:

        if not audio.filename:
            return render_index(request, error="No se recibió ningún archivo.")

        suffix = Path(audio.filename).suffix.lower()

        if suffix not in ALLOWED_EXTENSIONS:
            return render_index(request, error=f"Formato no permitido: {suffix}")

        file_id = str(uuid.uuid4())
        input_path = UPLOAD_DIR / f"{file_id}{suffix}"
        output_path = OUTPUT_DIR / f"{file_id}.txt"
        history_audio_path = HISTORY_AUDIO_DIR / f"{file_id}{suffix}"
        history_text_path = HISTORY_TEXT_DIR / f"{file_id}.txt"

        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        start_time = time.time()

        description = description.strip()
        speaker = speaker.strip()

        try:
            contents = await audio.read()

            if len(contents) > MAX_FILE_SIZE:
                return render_index(
                    request,
                    error="Archivo demasiado grande (máximo 5 MB)"
                )

            file_size_bytes = len(contents)

            with input_path.open("wb") as buffer:
                buffer.write(contents)

            with history_audio_path.open("wb") as buffer:
                buffer.write(contents)

            segments, info = model.transcribe(str(input_path), language="es")

            texto = "\n".join(
                seg.text.strip()
                for seg in segments
                if seg.text and seg.text.strip()
            )

            if not texto.strip():
                texto = "[No se detectó texto]"

            output_path.write_text(texto, encoding="utf-8")
            history_text_path.write_text(texto, encoding="utf-8")

            processing_seconds = round(time.time() - start_time, 2)

            duration_seconds = None
            try:
                if getattr(info, "duration", None):
                    duration_seconds = round(float(info.duration), 2)
            except Exception:
                duration_seconds = None

            save_history(
                created_at=created_at,
                original_filename=audio.filename,
                description=description,
                speaker=speaker,
                stored_audio_path=str(history_audio_path),
                stored_text_path=str(history_text_path),
                transcribed_text=texto,
                file_size_bytes=file_size_bytes,
                duration_seconds=duration_seconds,
                processing_seconds=processing_seconds,
                status="ok",
            )

            return render_index(
                request,
                text=texto,
                download_link=f"/descargar/{output_path.name}"
            )

        except Exception as e:
            processing_seconds = round(time.time() - start_time, 2)

            save_history(
                created_at=created_at,
                original_filename=audio.filename or "desconocido",
                description=description,
                speaker=speaker,
                stored_audio_path="",
                stored_text_path="",
                transcribed_text=f"ERROR: {e}",
                file_size_bytes=0,
                duration_seconds=None,
                processing_seconds=processing_seconds,
                status="error",
            )

            logger.exception("Error en transcripción")
            return render_index(request, error=f"Error: {e}")

        finally:
            try:
                audio.file.close()
            except Exception:
                pass

@app.get("/historial", response_class=HTMLResponse)
def historial(request: Request):
    if not require_login(request):
        return RedirectResponse(url="/login", status_code=302)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            created_at,
            original_filename,
            description,
            speaker,
            stored_audio_path,
            stored_text_path,
            file_size_bytes,
            duration_seconds,
            processing_seconds,
            status
        FROM transcriptions
        ORDER BY id DESC
        LIMIT 100
    """)
    rows = cur.fetchall()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="historial.html",
        context={
            "request": request,
            "rows": rows
        }
    )


@app.get("/descargar_texto_historial/{record_id}")
def descargar_texto_historial(record_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT original_filename, stored_text_path
        FROM transcriptions
        WHERE id = ?
    """, (record_id,))
    row = cur.fetchone()
    conn.close()

    if not row or not row["stored_text_path"]:
        raise HTTPException(status_code=404, detail="Texto no encontrado")

    file_path = Path(row["stored_text_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Texto no encontrado")

    base_name = Path(row["original_filename"]).stem
    download_name = f"{base_name}.txt"

    return FileResponse(
        path=file_path,
        filename=download_name,
        media_type="text/plain; charset=utf-8"
    )


@app.get("/descargar_audio_historial/{record_id}")
def descargar_audio_historial(record_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT original_filename, stored_audio_path
        FROM transcriptions
        WHERE id = ?
    """, (record_id,))
    row = cur.fetchone()
    conn.close()

    if not row or not row["stored_audio_path"]:
        raise HTTPException(status_code=404, detail="Audio no encontrado")

    file_path = Path(row["stored_audio_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio no encontrado")

    return FileResponse(
        path=file_path,
        filename=row["original_filename"]
    )
    
@app.get("/descargar/{filename}")
def descargar(filename: str):
    file_path = OUTPUT_DIR / filename

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="text/plain; charset=utf-8"
    )
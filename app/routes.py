from pathlib import Path
from datetime import datetime
import asyncio
import logging
import time
import uuid

from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse

from app.auth import get_logged_user, require_login
from app.config import (
    MAX_CONCURRENT,
    MAX_FILE_SIZE,
    ALLOWED_EXTENSIONS,
    UPLOAD_DIR,
    OUTPUT_DIR,
    HISTORY_AUDIO_DIR,
    HISTORY_TEXT_DIR,
)
from app.db import save_history, get_history_rows, get_text_record, get_audio_record
from app.transcription import transcribe_audio

logger = logging.getLogger("voz_a_texto")
router = APIRouter()
semaphore = asyncio.Semaphore(MAX_CONCURRENT)

templates = None


def set_templates(t):
    global templates
    templates = t


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


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    if get_logged_user(request):
        return RedirectResponse(url="/", status_code=302)

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"request": request, "error": None}
    )


@router.post("/login", response_class=HTMLResponse)
async def login_post(request: Request):
    form = await request.form()
    username = form.get("username", "").strip()

    if username:
        request.session["username"] = username
        return RedirectResponse(url="/", status_code=302)

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"request": request, "error": "Debes ingresar un nombre"}
    )


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    if not require_login(request):
        return RedirectResponse(url="/login", status_code=302)

    return render_index(request)


@router.post("/transcribir", response_class=HTMLResponse)
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
                return render_index(request, error="Archivo demasiado grande (máximo 5 MB)")

            file_size_bytes = len(contents)

            with input_path.open("wb") as buffer:
                buffer.write(contents)

            with history_audio_path.open("wb") as buffer:
                buffer.write(contents)

            texto, duration_seconds = transcribe_audio(str(input_path))

            output_path.write_text(texto, encoding="utf-8")
            history_text_path.write_text(texto, encoding="utf-8")

            processing_seconds = round(time.time() - start_time, 2)

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


@router.get("/historial", response_class=HTMLResponse)
def historial(request: Request):
    if not require_login(request):
        return RedirectResponse(url="/login", status_code=302)

    rows = get_history_rows()

    return templates.TemplateResponse(
        request=request,
        name="historial.html",
        context={"request": request, "rows": rows}
    )


@router.get("/descargar_texto_historial/{record_id}")
def descargar_texto_historial(record_id: int):
    row = get_text_record(record_id)

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


@router.get("/descargar_audio_historial/{record_id}")
def descargar_audio_historial(record_id: int):
    row = get_audio_record(record_id)

    if not row or not row["stored_audio_path"]:
        raise HTTPException(status_code=404, detail="Audio no encontrado")

    file_path = Path(row["stored_audio_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio no encontrado")

    return FileResponse(
        path=file_path,
        filename=row["original_filename"]
    )


@router.get("/descargar/{filename}")
def descargar(filename: str):
    file_path = OUTPUT_DIR / filename

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="text/plain; charset=utf-8"
    )
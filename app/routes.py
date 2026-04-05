from pathlib import Path
from datetime import datetime
import asyncio
import logging
import time
import uuid
import difflib

from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, Response

from app.auth import get_logged_user, require_login, is_admin
from app.config import (
    MAX_CONCURRENT,
    MAX_FILE_SIZE,
    ALLOWED_EXTENSIONS,
    UPLOAD_DIR,
    OUTPUT_DIR,
    HISTORY_AUDIO_DIR,
    HISTORY_TEXT_DIR,
)
from app.db import (
    save_history,
    get_history_rows,
    get_history_rows_by_user,
    get_text_record,
    get_audio_record,
    get_transcription_owner,
    verify_user_credentials,
    get_user_by_username,
    create_user,
    update_final_text,
    get_transcription_by_id,
    update_transcription_edit,
    get_audio_path_by_record_id,
)
from app.transcription import transcribe_audio

logger = logging.getLogger("voz_a_texto")
router = APIRouter()
semaphore = asyncio.Semaphore(MAX_CONCURRENT)

templates = None


def set_templates(t):
    global templates
    templates = t

def can_access_record(request: Request, record_id: int) -> bool:
    current_user = require_login(request)
    if not current_user:
        return False

    if current_user["is_admin"]:
        return True

    owner = get_transcription_owner(record_id)
    if not owner:
        return False

    return owner["user_id"] == current_user["user_id"]


def character_change_count(original: str | None, final: str | None) -> int:
    original = original or ""
    final = final or ""

    matcher = difflib.SequenceMatcher(None, original, final)
    total = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "replace":
            total += max(i2 - i1, j2 - j1)
        elif tag == "delete":
            total += (i2 - i1)
        elif tag == "insert":
            total += (j2 - j1)

    return total


def render_index(request: Request, text=None, download_link=None, error=None):
    current_user = get_logged_user(request)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "text": text,
            "download_link": download_link,
            "error": error,
            "username": current_user["username"] if current_user else None,
            "current_user": current_user,
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
    password = form.get("password", "")

    await asyncio.sleep(4)

    if not username or not password:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "request": request,
                "error": "Debes ingresar usuario y contraseña"
            }
        )

    user = verify_user_credentials(username, password)

    if not user:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "request": request,
                "error": "Credenciales inválidas"
            }
        )

    request.session["user_id"] = user["id"]
    request.session["username"] = user["username"]
    request.session["is_admin"] = bool(user["is_admin"])

    return RedirectResponse(url="/", status_code=302)


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
    exam_date: str = Form(""),
    modality: str = Form(""),
    hospital: str = Form(""),
    description: str = Form(""),
    speaker: str = Form(""),
    audio: UploadFile = File(...)
):
    current_user = require_login(request)
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

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

        exam_date = exam_date.strip()
        modality = modality.strip()
        hospital = hospital.strip()
        description = description.strip()
        speaker = speaker.strip()

        try:
            contents = await audio.read()

            if len(contents) > MAX_FILE_SIZE:
                return render_index(request, error="Archivo demasiado grande (máximo permitido).")

            file_size_bytes = len(contents)

            with input_path.open("wb") as buffer:
                buffer.write(contents)

            with history_audio_path.open("wb") as buffer:
                buffer.write(contents)

            texto, duration_seconds = transcribe_audio(str(input_path))

            output_path.write_text(texto, encoding="utf-8")
            history_text_path.write_text(texto, encoding="utf-8")

            processing_seconds = round(time.time() - start_time, 2)

            record_id = save_history(
                created_at=created_at,
                original_filename=audio.filename,
                exam_date=exam_date,
                modality=modality,
                hospital=hospital,
                description=description,
                speaker=speaker,
                stored_audio_path=str(history_audio_path),
                stored_text_path=str(history_text_path),
                transcribed_text=texto,
                final_text=texto,
                user_id=current_user["user_id"],
                file_size_bytes=file_size_bytes,
                duration_seconds=duration_seconds,
                processing_seconds=processing_seconds,
                status="ok",
            )

            return RedirectResponse(url=f"/editar/{record_id}", status_code=302)

        except Exception as e:
            processing_seconds = round(time.time() - start_time, 2)

            save_history(
                created_at=created_at,
                original_filename=audio.filename or "desconocido",
                exam_date=exam_date,
                modality=modality,
                hospital=hospital,
                description=description,
                speaker=speaker,
                stored_audio_path="",
                stored_text_path="",
                transcribed_text=f"ERROR: {e}",
                final_text=None,
                user_id=current_user["user_id"],
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
    current_user = require_login(request)
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    if is_admin(request):
        rows = get_history_rows()
    else:
        rows = get_history_rows_by_user(current_user["user_id"])

    processed_rows = []
    for row in rows:
        row_dict = dict(row)
        row_dict["character_changes"] = character_change_count(
            row_dict.get("transcribed_text"),
            row_dict.get("final_text"),
        )
        processed_rows.append(row_dict)

    return templates.TemplateResponse(
        request=request,
        name="historial.html",
        context={
            "request": request,
            "rows": processed_rows,
            "current_user": current_user,
        }
    )


@router.get("/admin/usuarios", response_class=HTMLResponse)
def admin_usuarios_form(request: Request):
    current_user = require_login(request)
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    if not current_user["is_admin"]:
        raise HTTPException(status_code=403, detail="Solo el administrador puede crear usuarios")

    return templates.TemplateResponse(
        request=request,
        name="admin_usuarios.html",
        context={
            "request": request,
            "current_user": current_user,
            "error": None,
            "success": None,
        }
    )


@router.post("/admin/usuarios", response_class=HTMLResponse)
async def admin_usuarios_create(request: Request):
    current_user = require_login(request)
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    if not current_user["is_admin"]:
        raise HTTPException(status_code=403, detail="Solo el administrador puede crear usuarios")

    form = await request.form()

    username = form.get("username", "").strip()
    email = form.get("email", "").strip()
    password = form.get("password", "")
    is_admin_value = form.get("is_admin", "0")

    if not username or not email or not password:
        return templates.TemplateResponse(
            request=request,
            name="admin_usuarios.html",
            context={
                "request": request,
                "current_user": current_user,
                "error": "Debes completar usuario, correo y contraseña",
                "success": None,
            }
        )

    existing_user = get_user_by_username(username)
    if existing_user:
        return templates.TemplateResponse(
            request=request,
            name="admin_usuarios.html",
            context={
                "request": request,
                "current_user": current_user,
                "error": "Ese nombre de usuario ya existe",
                "success": None,
            }
        )

    try:
        create_user(
            username=username,
            email=email,
            password=password,
            is_admin=1 if is_admin_value == "1" else 0,
        )
    except Exception as e:
        return templates.TemplateResponse(
            request=request,
            name="admin_usuarios.html",
            context={
                "request": request,
                "current_user": current_user,
                "error": f"No se pudo crear el usuario: {e}",
                "success": None,
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="admin_usuarios.html",
        context={
            "request": request,
            "current_user": current_user,
            "error": None,
            "success": f"Usuario '{username}' creado correctamente",
        }
    )


@router.get("/editar/{record_id}", response_class=HTMLResponse)
def editar(request: Request, record_id: int):
    current_user = require_login(request)
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    if not can_access_record(request, record_id):
        raise HTTPException(status_code=403)

    row = get_transcription_by_id(record_id)

    if not row:
        raise HTTPException(status_code=404)

    return templates.TemplateResponse(
        request=request,
        name="editar.html",
        context={
            "request": request,
            "row": row,
            "current_user": current_user,
        }
    )

@router.post("/editar/{record_id}")
async def guardar_edicion(request: Request, record_id: int):
    current_user = require_login(request)
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    if not can_access_record(request, record_id):
        raise HTTPException(status_code=403)

    form = await request.form()
    final_text = form.get("final_text", "")
    exam_date = form.get("exam_date", "").strip()
    hospital = form.get("hospital", "").strip()
    modality = form.get("modality", "").strip()

    update_transcription_edit(
        record_id=record_id,
        final_text=final_text,
        exam_date=exam_date,
        hospital=hospital,
        modality=modality,
    )

    return RedirectResponse(url="/historial", status_code=302)

@router.get("/descargar_texto_historial/{record_id}")
def descargar_texto_historial(request: Request, record_id: int):
    current_user = require_login(request)
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    if not can_access_record(request, record_id):
        raise HTTPException(status_code=403, detail="No autorizado para acceder a este texto")

    row = get_text_record(record_id)

    if not row:
        raise HTTPException(status_code=404, detail="Texto no encontrado")

    text_to_download = row["final_text"] if row["final_text"] else row["transcribed_text"]
    if text_to_download is None:
        raise HTTPException(status_code=404, detail="Texto no encontrado")

    base_name = Path(row["original_filename"]).stem
    download_name = f"{base_name}.txt"

    return Response(
        content=text_to_download,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{download_name}"'
        }
    )


@router.get("/descargar_audio_historial/{record_id}")
def descargar_audio_historial(request: Request, record_id: int):
    current_user = require_login(request)
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    if not can_access_record(request, record_id):
        raise HTTPException(status_code=403, detail="No autorizado para acceder a este audio")

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
def descargar(request: Request, filename: str):
    current_user = require_login(request)
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    file_path = OUTPUT_DIR / filename

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="text/plain; charset=utf-8"
    )


@router.get("/audio/{record_id}")
def servir_audio_edicion(request: Request, record_id: int):
    current_user = require_login(request)
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    if not can_access_record(request, record_id):
        raise HTTPException(status_code=403, detail="No autorizado para acceder a este audio")

    row = get_audio_path_by_record_id(record_id)
    if not row or not row["stored_audio_path"]:
        raise HTTPException(status_code=404, detail="Audio no encontrado")

    file_path = Path(row["stored_audio_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio no encontrado")

    return FileResponse(path=file_path)
from faster_whisper import WhisperModel
from app.config import WHISPER_MODEL


model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")


def transcribe_audio(input_path: str):
    segments, info = model.transcribe(input_path, language="es")

    texto = "\n".join(
        seg.text.strip()
        for seg in segments
        if seg.text and seg.text.strip()
    )

    if not texto.strip():
        texto = "[No se detectó texto]"

    duration_seconds = None
    try:
        if getattr(info, "duration", None):
            duration_seconds = round(float(info.duration), 2)
    except Exception:
        duration_seconds = None

    return texto, duration_seconds
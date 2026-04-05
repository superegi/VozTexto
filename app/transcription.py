from app.config import WHISPER_MODEL, DISABLE_WHISPER

if not DISABLE_WHISPER:
    from faster_whisper import WhisperModel
    model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
else:
    model = None


def transcribe_audio(input_path: str):
    if DISABLE_WHISPER:
        return "[TRANSCRIPCIÓN DESACTIVADA PARA PRUEBAS]", 0.0

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
from app.config import (
    WHISPER_MODEL,
    DISABLE_WHISPER,
    WHISPER_DEVICE,
    WHISPER_COMPUTE_TYPE,
    WHISPER_CPU_THREADS,
    WHISPER_NUM_WORKERS,
)

if not DISABLE_WHISPER:
    import ctranslate2
    from faster_whisper import WhisperModel

    def build_whisper_model():
        requested_device = WHISPER_DEVICE.lower().strip()
        requested_compute = WHISPER_COMPUTE_TYPE.lower().strip()

        cuda_available = False
        try:
            cuda_available = ctranslate2.get_cuda_device_count() > 0
        except Exception:
            cuda_available = False

        if requested_device == "cuda" and cuda_available:
            device = "cuda"
            compute_type = requested_compute
        else:
            device = "cpu"
            compute_type = "int8"

        print(
            f"[Whisper] model={WHISPER_MODEL} device={device} "
            f"compute_type={compute_type} cpu_threads={WHISPER_CPU_THREADS} "
            f"num_workers={WHISPER_NUM_WORKERS}"
        )

        return WhisperModel(
            WHISPER_MODEL,
            device=device,
            compute_type=compute_type,
            cpu_threads=WHISPER_CPU_THREADS,
            num_workers=WHISPER_NUM_WORKERS,
        )

    model = build_whisper_model()
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

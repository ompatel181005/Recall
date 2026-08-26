"""faster-whisper transcription service — implemented in M1.

M0 exposes only a CUDA availability probe for /api/health.
"""


def cuda_available() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def transcribe_audio(audio_path: str) -> dict:
    """M1: run faster-whisper (model/device from config.yaml `transcription:`)
    and return {full_text, segments, language, model_used}."""
    raise NotImplementedError("Transcription lands in milestone M1")

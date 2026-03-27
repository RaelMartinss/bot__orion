"""
utils/transcriber.py
Transcreve áudio para texto usando faster-whisper (modelo local, sem API).
Na primeira execução baixa o modelo ~240MB automaticamente.
"""

import logging
import os
import tempfile

logger = logging.getLogger(__name__)

_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        logger.info("Carregando modelo Whisper 'small' (pode demorar na 1ª vez)...")
        _model = WhisperModel("small", device="cpu", compute_type="int8")
        logger.info("Modelo Whisper pronto.")
    return _model


def transcrever_audio(audio_path: str) -> str:
    """Transcreve um arquivo de áudio (OGG, WAV, MP3…) e retorna o texto."""
    model = _get_model()
    segments, info = model.transcribe(audio_path, language="pt", beam_size=5)
    texto = " ".join(seg.text for seg in segments).strip()
    logger.info(f"Transcrição: '{texto}' (idioma: {info.language}, prob: {info.language_probability:.2f})")
    return texto


def transcrever_numpy(audio: "np.ndarray", sample_rate: int = 16000) -> str:
    """Transcreve um array numpy de áudio (float32, mono) e retorna o texto."""
    import numpy as np
    model = _get_model()
    audio_f32 = audio.astype(np.float32)
    segments, info = model.transcribe(audio_f32, language="pt", beam_size=5)
    texto = " ".join(seg.text for seg in segments).strip()
    logger.info(f"Transcrição: '{texto}' (idioma: {info.language}, prob: {info.language_probability:.2f})")
    return texto

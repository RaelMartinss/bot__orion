"""
utils/vision.py
Orion Vision — captura de tela + OCR + detecção de contexto.
Roda em background thread e envia sugestões via Telegram.

Ativação: vision_on / vision_off
"""

import logging
import threading
import time

logger = logging.getLogger(__name__)

# ── Estado global ─────────────────────────────────────────────────────────────
_VISION_ATIVO = False
_ultimo_contexto: str | None = None       # cache para evitar repetir sugestões
_thread: threading.Thread | None = None
_stop_event = threading.Event()

# Callback injetado por main.py para enviar mensagem ao usuário
_send_callback = None   # callable: (texto: str) -> None

# Intervalo entre capturas (segundos)
INTERVALO = 10

# Configuração do Tesseract (Windows)
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


# ── API pública ───────────────────────────────────────────────────────────────

def configure(send_fn):
    """Registra o callback que envia a sugestão ao usuário via Telegram."""
    global _send_callback
    _send_callback = send_fn


def iniciar():
    """Ativa o loop de visão em background."""
    global _VISION_ATIVO, _thread, _stop_event
    if _VISION_ATIVO:
        return "👁️ Visão já está ativa."
    _VISION_ATIVO = True
    _stop_event.clear()
    _thread = threading.Thread(target=_loop_vision, daemon=True, name="orion-vision")
    _thread.start()
    logger.info("Orion Vision iniciado.")
    return "👁️ Visão ativada! Vou monitorar sua tela."


def parar():
    """Desativa o loop de visão."""
    global _VISION_ATIVO
    if not _VISION_ATIVO:
        return "👁️ Visão já está desativada."
    _VISION_ATIVO = False
    _stop_event.set()
    logger.info("Orion Vision parado.")
    return "🔇 Visão desativada."


def ativo() -> bool:
    return _VISION_ATIVO


def analisar_agora() -> str | None:
    """Força uma análise imediata e retorna sugestão (ou None se nada relevante)."""
    try:
        img = _capturar_tela()
        img_proc = _preprocessar(img)
        texto = _extrair_texto(img_proc)
        return _sugestao_contexto(texto)
    except Exception as e:
        logger.error(f"Vision — erro na análise: {e}")
        return None


# ── Loop interno ──────────────────────────────────────────────────────────────

def _loop_vision():
    global _ultimo_contexto
    while not _stop_event.is_set():
        try:
            sugestao = analisar_agora()
            if sugestao and sugestao != _ultimo_contexto:
                _ultimo_contexto = sugestao
                if _send_callback:
                    _send_callback(sugestao)
        except Exception as e:
            logger.error(f"Vision loop erro: {e}")
        _stop_event.wait(INTERVALO)


# ── Pipeline ──────────────────────────────────────────────────────────────────

def _capturar_tela():
    """Captura a tela inteira. Usa mss (mais rápido) com fallback para PIL."""
    try:
        import mss
        import numpy as np
        from PIL import Image
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # monitor principal
            raw = sct.grab(monitor)
            return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    except ImportError:
        from PIL import ImageGrab
        return ImageGrab.grab()


def _preprocessar(img):
    """Converte para escala de cinza + binarização para melhorar OCR."""
    try:
        import cv2
        import numpy as np
        arr = np.array(img)
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
        return thresh
    except ImportError:
        # sem opencv: retorna a imagem original (pytesseract aceita PIL direto)
        return img


def _extrair_texto(img) -> str:
    """Extrai texto da imagem via pytesseract."""
    try:
        import pytesseract
        import os
        if os.path.isfile(TESSERACT_CMD):
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        return pytesseract.image_to_string(img, lang="por+eng")
    except Exception as e:
        logger.warning(f"OCR falhou: {e}")
        return ""


# ── Detecção de contexto ──────────────────────────────────────────────────────

def _detectar_contexto(texto: str) -> str | None:
    t = texto.lower()

    if any(k in t for k in ("traceback", "error:", "exception:", "syntaxerror", "typeerror",
                            "nameerror", "attributeerror", "importerror")):
        return "erro_python"

    if any(k in t for k in ("err!", "error TS", "cannot find module", "module not found",
                            "npm warn", "npm error")):
        return "erro_node"

    if any(k in t for k in ("failed to compile", "compilation error", "webpack")):
        return "erro_build"

    if any(k in t for k in ("npm", "node_modules", "vite", "package.json", "localhost:5173")):
        return "node_project"

    if "youtube.com" in t or "youtu.be" in t:
        return "youtube"

    if "github.com" in t or "pull request" in t or "merge" in t:
        return "github"

    if any(k in t for k in ("stackoverflow.com", "stack overflow")):
        return "stackoverflow"

    return None


def _sugestao_contexto(texto: str) -> str | None:
    """Retorna sugestão textual para o contexto detectado ou None."""
    ctx = _detectar_contexto(texto)

    _SUGESTOES = {
        "erro_python":  "⚠️ *Detectei um erro Python na tela.* Quer que eu analise e te ajude?",
        "erro_node":    "⚠️ *Erro Node/npm detectado.* Quer que eu verifique o problema?",
        "erro_build":   "🔨 *Erro de compilação detectado.* Posso ajudar a resolver?",
        "node_project": "👨‍💻 *Projeto Node ativo.* Quer rodar com `npm run dev`?",
        "youtube":      "▶️ *YouTube detectado.* Precisa de algo?",
        "github":       "🐙 *GitHub detectado.* Posso ajudar com o PR?",
        "stackoverflow": "🔍 *Stack Overflow detectado.* Posso pesquisar isso para você?",
    }
    return _SUGESTOES.get(ctx)  # type: ignore[return-value]

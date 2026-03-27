"""
handlers/controle.py
Controle de reprodução de mídia: pause, play, próxima, anterior.

Estratégia:
  1. Se houver janela de browser com YouTube no título → foca e usa tecla 'k'
  2. Caso contrário → usa tecla de mídia universal (pausa Spotify, VLC, etc.)
"""

import logging
import time
import pyautogui
from telegram import Update
from telegram.ext import ContextTypes

import utils.mic_listener as mic_listener

logger = logging.getLogger(__name__)

pyautogui.FAILSAFE = False  # evita exception ao mover mouse pro canto


# ── Utilitário de janela ──────────────────────────────────────────────────────

def _focar_youtube() -> bool:
    """Foca a janela do browser que contém YouTube. Retorna True se encontrou."""
    try:
        import pygetwindow as gw
        janelas = gw.getAllWindows()
        for janela in janelas:
            if "youtube" in janela.title.lower() and janela.title:
                janela.activate()
                time.sleep(0.25)
                return True
    except Exception as e:
        logger.debug(f"pygetwindow não disponível: {e}")
    return False


# ── Funções de controle ───────────────────────────────────────────────────────

def ctrl_pausar() -> str:
    if _focar_youtube():
        pyautogui.press("k")          # toggle pause/play no YouTube
        return "⏯️ YouTube pause/play."
    pyautogui.press("playpause")      # tecla de mídia universal (toggle)
    return "⏯️ Mídia pause/play."


def ctrl_proxima() -> str:
    if _focar_youtube():
        pyautogui.hotkey("shift", "n")   # próximo vídeo no YouTube
        return "⏭️ Próximo vídeo."
    pyautogui.press("nexttrack")
    return "⏭️ Próxima faixa."


def ctrl_anterior() -> str:
    if _focar_youtube():
        pyautogui.hotkey("shift", "p")   # vídeo anterior no YouTube
        return "⏮️ Vídeo anterior."
    pyautogui.press("prevtrack")
    return "⏮️ Faixa anterior."


# ── Handlers Telegram ─────────────────────────────────────────────────────────

async def pausar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mic_listener.update_chat_id(update.effective_chat.id)
    resultado = ctrl_pausar()
    await update.message.reply_text(resultado)


async def proxima(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mic_listener.update_chat_id(update.effective_chat.id)
    resultado = ctrl_proxima()
    await update.message.reply_text(resultado)


async def anterior(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mic_listener.update_chat_id(update.effective_chat.id)
    resultado = ctrl_anterior()
    await update.message.reply_text(resultado)

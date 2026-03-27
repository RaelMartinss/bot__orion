"""
handlers/volume.py
Controle de volume do Windows via pycaw (COM/Windows Audio API).
Instale: pip install pycaw
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

PASSO_VOLUME = 0.10  # 10% por comando


def _get_volume_interface():
    """Retorna a interface de controle de volume do Windows."""
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL

    dispositivos = AudioUtilities.GetSpeakers()
    interface = dispositivos.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


async def volume_up(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /vol_up — Aumenta o volume em 10%.
    /vol_up 20 — Aumenta em 20%.
    """
    try:
        passo = float(context.args[0]) / 100 if context.args else PASSO_VOLUME
        vol = _get_volume_interface()
        atual = vol.GetMasterVolumeLevelScalar()
        novo = min(1.0, atual + passo)
        vol.SetMasterVolumeLevelScalar(novo, None)
        await update.message.reply_text(f"🔊 Volume: *{int(novo * 100)}%*", parse_mode="Markdown")
    except ImportError:
        await update.message.reply_text(
            "❌ `pycaw` não instalado.\nRode: `pip install pycaw`", parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Erro no volume_up: {e}")
        await update.message.reply_text(f"❌ Erro ao ajustar volume: `{e}`", parse_mode="Markdown")


async def volume_down(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /vol_down — Diminui o volume em 10%.
    /vol_down 20 — Diminui em 20%.
    """
    try:
        passo = float(context.args[0]) / 100 if context.args else PASSO_VOLUME
        vol = _get_volume_interface()
        atual = vol.GetMasterVolumeLevelScalar()
        novo = max(0.0, atual - passo)
        vol.SetMasterVolumeLevelScalar(novo, None)
        await update.message.reply_text(f"🔉 Volume: *{int(novo * 100)}%*", parse_mode="Markdown")
    except ImportError:
        await update.message.reply_text(
            "❌ `pycaw` não instalado.\nRode: `pip install pycaw`", parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Erro no volume_down: {e}")
        await update.message.reply_text(f"❌ Erro ao ajustar volume: `{e}`", parse_mode="Markdown")


async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /mute — Alterna mute (muta/desmuta).
    """
    try:
        vol = _get_volume_interface()
        estado_atual = vol.GetMute()
        vol.SetMute(not estado_atual, None)
        emoji = "🔇" if not estado_atual else "🔊"
        status = "Mutado" if not estado_atual else "Desmutado"
        await update.message.reply_text(f"{emoji} *{status}*", parse_mode="Markdown")
    except ImportError:
        await update.message.reply_text(
            "❌ `pycaw` não instalado.\nRode: `pip install pycaw`", parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Erro no mute: {e}")
        await update.message.reply_text(f"❌ Erro ao alternar mute: `{e}`", parse_mode="Markdown")

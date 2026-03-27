"""
handlers/volume.py
Controle de volume do Windows via pycaw (Windows Audio API).
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

AGUARDANDO_VOLUME = 1

logger = logging.getLogger(__name__)

PASSO_VOLUME = 0.10  # 10% padrão


def _get_vol():
    """Retorna a interface IAudioEndpointVolume compatível com pycaw antigo e novo."""
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL

    dispositivos = AudioUtilities.GetSpeakers()
    if dispositivos is None:
        raise RuntimeError("Nenhum dispositivo de áudio encontrado.")

    # pycaw >= 20240210 envolve o device num objeto AudioDevice com ._dev
    dev = getattr(dispositivos, "_dev", dispositivos)
    interface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def _barra(pct: int) -> str:
    """Barra visual do volume."""
    blocos = round(pct / 10)
    return "█" * blocos + "░" * (10 - blocos)


# ── Handlers ──────────────────────────────────────────────────────────────────

async def volume_up(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/vol_up [%] — Aumenta o volume (padrão 10%)."""
    try:
        passo = float(context.args[0]) / 100 if context.args else PASSO_VOLUME
        vol = _get_vol()
        novo = min(1.0, vol.GetMasterVolumeLevelScalar() + passo)
        vol.SetMasterVolumeLevelScalar(novo, None)
        pct = int(novo * 100)
        await update.message.reply_text(
            f"🔊 *{pct}%*  {_barra(pct)}", parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"vol_up: {e}")
        await update.message.reply_text(f"❌ Erro ao ajustar volume: `{e}`", parse_mode="Markdown")


async def volume_down(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/vol_down [%] — Diminui o volume (padrão 10%)."""
    try:
        passo = float(context.args[0]) / 100 if context.args else PASSO_VOLUME
        vol = _get_vol()
        novo = max(0.0, vol.GetMasterVolumeLevelScalar() - passo)
        vol.SetMasterVolumeLevelScalar(novo, None)
        pct = int(novo * 100)
        await update.message.reply_text(
            f"🔉 *{pct}%*  {_barra(pct)}", parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"vol_down: {e}")
        await update.message.reply_text(f"❌ Erro ao ajustar volume: `{e}`", parse_mode="Markdown")


async def volume_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/volume — Pergunta o valor e aguarda a resposta."""
    try:
        vol = _get_vol()
        pct = int(vol.GetMasterVolumeLevelScalar() * 100)
    except Exception:
        pct = "?"

    await update.message.reply_text(
        f"🔊 Volume atual: *{pct}%*\n\nDigite o novo valor _(0 a 100)_:",
        parse_mode="Markdown",
    )
    return AGUARDANDO_VOLUME


async def volume_receber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o número digitado e aplica o volume."""
    texto = update.message.text.strip()
    if not texto.isdigit():
        await update.message.reply_text("❌ Digite apenas um número entre 0 e 100.")
        return AGUARDANDO_VOLUME

    alvo = max(0, min(100, int(texto)))
    try:
        vol = _get_vol()
        vol.SetMasterVolumeLevelScalar(alvo / 100, None)
        await update.message.reply_text(
            f"🔊 Volume: *{alvo}%*  {_barra(alvo)}", parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"volume_receber: {e}")
        await update.message.reply_text(f"❌ Erro: `{e}`", parse_mode="Markdown")

    return ConversationHandler.END


async def volume_cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelado.")
    return ConversationHandler.END


async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/mute — Alterna mute."""
    try:
        vol = _get_vol()
        estado = vol.GetMute()
        vol.SetMute(not estado, None)
        emoji, status = ("🔊", "Desmutado") if estado else ("🔇", "Mutado")
        await update.message.reply_text(f"{emoji} *{status}*", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"mute: {e}")
        await update.message.reply_text(f"❌ Erro ao alternar mute: `{e}`", parse_mode="Markdown")

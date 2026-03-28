"""
handlers/custom/steam.py
Abre o cliente Steam no PC do usuário.
"""
import os
import logging

logger = logging.getLogger(__name__)


async def steam(update, context):
    """
    /steam — Abre o cliente Steam.
    """
    try:
        os.startfile("steam://open/main")
        await update.message.reply_text("🎮 Steam aberto! Boa noite!")
    except Exception as e:
        logger.error(f"Erro em steam: {e}")
        await update.message.reply_text(f"❌ Erro: `{e}`", parse_mode="Markdown")
"""
handlers/voice.py
Handlers para mensagens de voz e texto livre no Telegram.
"""

import logging
import os
import tempfile
from telegram import Update
from telegram.ext import ContextTypes

from utils.transcriber import transcrever_audio
from utils.intent_parser import parse_intent
from utils.executor import executar_intent
import utils.mic_listener as mic_listener

logger = logging.getLogger(__name__)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe áudio/voz do Telegram, transcreve e executa o comando."""
    # Atualiza chat_id para o mic_listener poder enviar notificações
    mic_listener.update_chat_id(update.effective_chat.id)

    msg = await update.message.reply_text("🎙️ Transcrevendo áudio...")

    voice = update.message.voice or update.message.audio
    if not voice:
        await msg.edit_text("❌ Formato de áudio não suportado.")
        return

    file = await context.bot.get_file(voice.file_id)

    suffix = ".ogg" if update.message.voice else ".mp3"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        await file.download_to_drive(tmp.name)
        tmp_path = tmp.name

    try:
        texto = transcrever_audio(tmp_path)
        if not texto:
            await msg.edit_text("❌ Não consegui entender o áudio.")
            return

        await msg.edit_text(f"🗣️ _{texto}_\n⚙️ Executando...", parse_mode="Markdown")

        intent = parse_intent(texto)
        resultado = executar_intent(intent)

        await msg.edit_text(f"🗣️ _{texto}_\n\n{resultado}", parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Erro ao processar voz: {e}", exc_info=True)
        await msg.edit_text(f"❌ Erro ao processar áudio: `{e}`", parse_mode="Markdown")
    finally:
        os.unlink(tmp_path)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe texto livre (não-comando) e executa a ação correspondente."""
    # Atualiza chat_id para o mic_listener
    mic_listener.update_chat_id(update.effective_chat.id)

    texto = update.message.text.strip()
    if not texto:
        return

    intent = parse_intent(texto)

    if intent["action"] == "desconhecido":
        await update.message.reply_text(
            "❓ Não entendi. Exemplos:\n"
            "• _toca menino da porteira_\n"
            "• _abre o minecraft_\n"
            "• _aumenta o volume_\n"
            "• _desliga o pc_",
            parse_mode="Markdown",
        )
        return

    resultado = executar_intent(intent)
    await update.message.reply_text(resultado, parse_mode="Markdown")

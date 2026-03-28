"""
handlers/voice.py
Handler para texto livre no Telegram.
(O handler de áudio/voz foi integrado ao ConversationHandler em auto_learn.py)

Suporta wake word "Orion":
  - "Orion bom dia"           → saudação
  - "Orion abri minecraft"    → abre o jogo
  - "Orion toca funk no youtube" → reproduz vídeo
  - Texto sem "Orion"         → tenta executar normalmente
  - Intenção desconhecida     → pergunta se deve aprender (botões inline)
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from utils.intent_parser import parse_intent, extract_orion_command
from utils.executor import executar_intent
import utils.mic_listener as mic_listener

logger = logging.getLogger(__name__)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe texto livre (não-comando) e executa a ação correspondente."""
    mic_listener.update_chat_id(update.effective_chat.id)

    texto_original = update.message.text.strip()
    if not texto_original:
        from telegram.ext import ConversationHandler
        return ConversationHandler.END

    # Detecta wake word "Orion" (case-insensitive)
    from utils.intent_parser import extract_orion_command
    tem_wake_word, comando = extract_orion_command(texto_original)

    # Se tem wake word mas nenhum comando depois → saudação genérica
    if tem_wake_word and not comando:
        from datetime import datetime
        hora = datetime.now().hour
        periodo = "bom dia" if hora < 12 else "boa tarde" if hora < 18 else "boa noite"
        await update.message.reply_text(
            f"🤖 Olá! {periodo.capitalize()}! Como posso ajudar?",
            parse_mode="Markdown",
        )
        from telegram.ext import ConversationHandler
        return ConversationHandler.END

    texto_para_ia = comando if tem_wake_word else texto_original

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    from utils.orchestrator import run_orchestrator
    
    # Resgata memória amnésica para passar como contexto
    historico = context.user_data.get("chat_history", [])
    
    # Executa a orquestração via Cloud (Tool Use) enviando o histórico
    result = await run_orchestrator(texto_para_ia, chat_history=historico)
    
    # Salva o resultado do novo histórico para não sofrer amnésia
    if "new_history" in result:
        context.user_data["chat_history"] = result["new_history"]
    
    # Opcional: Mostra a resposta do bot (pós ferramentas)
    if result.get("response"):
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        games = result.get("games_listed", [])
        if games:
            buttons = [[InlineKeyboardButton(f"🕹️ Abrir {j}", callback_data=f"abrir_jogo|{j}")] for j in games]
            reply_markup = InlineKeyboardMarkup(buttons)
            await update.message.reply_text(result["response"], parse_mode="Markdown", reply_markup=reply_markup)
        else:
            await update.message.reply_text(result["response"], parse_mode="Markdown")
        
    # Se a IA avaliou que precisa que você ensine o comando e engatilhou a feramenta de criar:
    if result.get("wants_to_learn"):
        from handlers.auto_learn import ask_confirmation
        return await ask_confirmation(
            update, context, 
            texto_desconhecido=texto_para_ia,
            custom_message_text="👇 Confirme aqui abaixo se quiser me ensinar esse novo truque:"
        )

    from telegram.ext import ConversationHandler
    return ConversationHandler.END

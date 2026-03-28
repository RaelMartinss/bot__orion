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
from utils.memoria import carregar_historico, persistir_historico, carregar_memoria_longa
from utils.tts_manager import gerar_audio, limpar_audio

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

    from utils.orchestrator import try_local_route
    local_result = try_local_route(texto_para_ia)
    if local_result is not None:
        mem = carregar_memoria_longa(user_id=update.effective_user.id)
        voice_active = mem.get("preferencias", {}).get("voice_active", False)

        if voice_active:
            audio_path = await gerar_audio(local_result)
            if audio_path:
                try:
                    await update.message.reply_voice(voice=open(audio_path, 'rb'), caption=local_result)
                finally:
                    limpar_audio(audio_path)
            else:
                await update.message.reply_text(local_result)
        else:
            await update.message.reply_text(local_result)

        from telegram.ext import ConversationHandler
        return ConversationHandler.END

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    from utils.orchestrator import run_orchestrator
    
    user_id = update.effective_user.id
    # Resgata memória amnésica para passar como contexto — agora via JSON persistente
    historico = carregar_historico(user_id)
    
    async def notificar_imediato_telegram(msg_texto: str):
        """Callback para enviar mensagem imediata no Telegram."""
        if msg_texto:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=msg_texto,
                parse_mode="Markdown"
            )

    # Executa a orquestração passando o callback de notificação imediata
    result = await run_orchestrator(
        texto_para_ia, 
        chat_history=historico, 
        user_id=user_id, 
        is_mic=False,
        notifier_callback=notificar_imediato_telegram
    )
    
    # Salva o resultado do novo histórico para não sofrer amnésia (JSON)
    if "new_history" in result:
        persistir_historico(user_id, result["new_history"])
        # Mantém no context também para legibilidade de sessão, se necessário
        context.user_data["chat_history"] = result["new_history"]
    
    # Opcional: Mostra a resposta do bot (pós ferramentas). 
    # Se ele já notificou via tool, a resposta final será "Tarefas finalizadas..."
    if result.get("response") and "Tarefas finalizadas" not in result["response"]:
        # Verifica se o usuário quer resposta por voz
        mem = carregar_memoria_longa(user_id)
        voice_active = mem.get("preferencias", {}).get("voice_active", False)
        
        if voice_active:
            # Envia áudio
            audio_path = await gerar_audio(result["response"])
            if audio_path:
                try:
                    await update.message.reply_voice(voice=open(audio_path, 'rb'), caption=result["response"])
                finally:
                    limpar_audio(audio_path)
            else:
                # Fallback para texto se falhar o TTS
                await update.message.reply_text(result["response"])
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

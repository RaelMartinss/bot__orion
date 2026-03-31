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
import re
from telegram import Update
from telegram.ext import ContextTypes

from utils.intent_parser import parse_intent, extract_orion_command
from utils.executor import executar_intent
from ml.intent_model import interpretar_comando
import utils.mic_listener as mic_listener
from utils import interface_bridge
from utils.memoria import carregar_historico, persistir_historico, carregar_memoria_longa, salvar_pending, limpar_pending, carregar_pending, salvar_ultimo_objeto
from utils.context_resolver import resolver_contexto
from utils.tts_manager import gerar_audio, limpar_audio

logger = logging.getLogger(__name__)


async def _responder(update: Update, texto: str, voice_active: bool) -> None:
    """Envia resposta por voz (se ativo) ou texto. Único ponto de saída de mensagem."""
    if voice_active:
        audio_path = await gerar_audio(texto)
        if audio_path:
            try:
                # Telegram limita caption a 1024 chars — envia texto completo separado se necessário
                caption = texto[:1021] + "…" if len(texto) > 1024 else texto
                await update.message.reply_voice(voice=open(audio_path, "rb"), caption=caption)
                if len(texto) > 1024:
                    await update.message.reply_text(texto, parse_mode="Markdown")
            finally:
                limpar_audio(audio_path)
            return
    await update.message.reply_text(texto, parse_mode="Markdown")


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
    user_id = update.effective_user.id
    await interface_bridge.emit_state("pensando", f"Processando: {texto_para_ia[:120]}")

    # Verifica se é uma resposta contextual ("no youtube", "no spotify") antes de parsear normalmente
    intent = resolver_contexto(user_id, texto_para_ia)

    if intent is None:
        intent = parse_intent(texto_para_ia)

        # Guard aplicado antes do ML e do Claude: evita rodar modelos em texto claramente conversacional
        _parece_comando = len(texto_para_ia) >= 6 and not re.match(
            r'^(ok|sim|não|nao|tudo bem|oi|olá|ola|ei|e aí|eai|valeu|obrigad|certo|entendi|legal|show|'
            r'bom dia|boa tarde|boa noite|boa|bom|tudo|como vai|obrigado|obrigada|opa|hey|ae|aeee|eae|'
            r'blz|beleza|opa|falou|tmj|vlw)\b',
            texto_para_ia.lower()
        )
        # Comandos de navegação web vão direto ao orchestrator — o ML confunde com jogos
        _BROWSER_RE = (
            r'\b(site|web|internet|pesquisa|pesquisar|google)\b'
            r'|\b(abr[ae]|abrir)\b.{0,20}\b(site|página|pagina|url|link)\b'
            r'|\b(acessa|acessar|entra em|entrar em|vai em|vá em)\b'
            r'|\.com\b|\.com\.br\b|https?://'
        )
        _parece_browser = bool(re.search(_BROWSER_RE, texto_para_ia.lower()))

        if intent.get("action") == "desconhecido" and _parece_comando and not _parece_browser:
            ml_intent = interpretar_comando(texto_para_ia)
            if ml_intent:
                intent = ml_intent

        # Regex + ML falharam → Claude extrai intent estruturado (rápido, sem orchestrator)
        if intent.get("action") == "desconhecido" and _parece_comando and not _parece_browser:
            from utils.claude_client import extrair_intent_estruturado
            structured = await extrair_intent_estruturado(texto_para_ia)
            if structured and structured.get("action") not in ("desconhecido", "conversa", None):
                intent = structured

    if intent.get("action") != "desconhecido":
        resultado = executar_intent(intent)
        # Salva contexto pendente para permitir redirect posterior ("tocou no spotify → no youtube")
        if intent.get("action") in ("spotify", "youtube", "netflix") and intent.get("query"):
            salvar_pending(user_id, intent["action"], intent["query"])
        # Salva último objeto aberto para resolver referências pronominais ("rode ele")
        if intent.get("action") == "open_project" and intent.get("target"):
            salvar_ultimo_objeto(user_id, "open_project", intent["target"], intent.get("app"))
        # Persiste time favorito na memória longa
        if intent.get("action") == "set_favorite_team" and intent.get("query"):
            from utils.memoria import salvar_preferencia
            salvar_preferencia(user_id, "time_favorito", intent["query"])
        mem = carregar_memoria_longa(user_id=update.effective_user.id)
        voice_active = mem.get("preferencias", {}).get("voice_active", False)
        # Resultado especial: imagem QR
        from utils.executor import QR_IMAGE_PREFIX
        if isinstance(resultado, str) and resultado.startswith(QR_IMAGE_PREFIX):
            import os
            img_path = resultado[len(QR_IMAGE_PREFIX):]
            try:
                await update.message.reply_photo(
                    photo=open(img_path, "rb"),
                    caption="📱 Escaneie pelo WhatsApp → *Aparelhos Conectados* → *Conectar dispositivo*",
                    parse_mode="Markdown"
                )
            finally:
                try: os.unlink(img_path)
                except Exception: pass
            await interface_bridge.emit_state("idle", "Sistema em espera.")
            from telegram.ext import ConversationHandler
            return ConversationHandler.END
        await interface_bridge.emit_state("falando", resultado[:160])
        await _responder(update, resultado, voice_active)
        await interface_bridge.emit_state("idle", "Sistema em espera.")
        from telegram.ext import ConversationHandler
        return ConversationHandler.END

    from utils.orchestrator import try_local_route
    local_result = try_local_route(texto_para_ia)
    if local_result is not None:
        mem = carregar_memoria_longa(user_id=update.effective_user.id)
        voice_active = mem.get("preferencias", {}).get("voice_active", False)
        await interface_bridge.emit_state("falando", local_result[:160])
        await _responder(update, local_result, voice_active)
        await interface_bridge.emit_state("idle", "Sistema em espera.")
        from telegram.ext import ConversationHandler
        return ConversationHandler.END

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    from utils.orchestrator import run_orchestrator

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
        notifier_callback=notificar_imediato_telegram,
        pending_context=carregar_pending(user_id),
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
        await interface_bridge.emit_state("falando", result["response"][:160])
        await _responder(update, result["response"], voice_active)
        
    # Se a IA avaliou que precisa que você ensine o comando e engatilhou a feramenta de criar:
    if result.get("wants_to_learn"):
        await interface_bridge.emit_state("pensando", "Aguardando confirmação para aprendizado.")
        from handlers.auto_learn import ask_confirmation
        return await ask_confirmation(
            update, context, 
            texto_desconhecido=texto_para_ia,
            custom_message_text="👇 Confirme aqui abaixo se quiser me ensinar esse novo truque:"
        )

    await interface_bridge.emit_state("idle", "Sistema em espera.")
    from telegram.ext import ConversationHandler
    return ConversationHandler.END

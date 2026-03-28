"""
handlers/auto_learn.py

ConversationHandler que gerencia o fluxo completo de criação de novos comandos:
  1. Detecta /comando desconhecido OU áudio com intenção não reconhecida
  2. Pergunta se o usuário quer que o Orion aprenda (confirmação com botões inline)
  3. Se confirmado: pede o nome (fluxo de voz) ou a descrição (fluxo de /comando)
  4. Chama a API da Anthropic para gerar o handler
  5. Valida, salva e registra o novo comando

Estados:
  AGUARDANDO_CONFIRMACAO  — aguarda o usuário confirmar (Sim/Não) via callback inline
  AGUARDANDO_NOME_COMANDO — voz não reconhecida, aguarda o nome do novo comando
  AGUARDANDO_INTENCAO     — nome definido, aguarda a descrição do que o comando faz
"""

import logging
import os
import tempfile

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from utils.prompt_builder import build_prompt
from utils.claude_client import generate_handler, APIError
from utils.code_validator import validate, ValidationError
from utils.handler_registry import (
    save_handler_file,
    load_and_register,
    update_telegram_menu,
)
from utils.transcriber import transcrever_audio
from utils.intent_parser import parse_intent, extract_orion_command
from utils.executor import executar_intent
import utils.mic_listener as mic_listener

logger = logging.getLogger(__name__)

# ── Estados ───────────────────────────────────────────────────────────────────
AGUARDANDO_CONFIRMACAO  = 3   # Aguarda o usuário confirmar (Sim/Não)
AGUARDANDO_NOME_COMANDO = 1   # Fluxo de voz: aguarda o nome do comando
AGUARDANDO_INTENCAO     = 2   # Aguarda a descrição do que o comando deve fazer

# ── Chaves no user_data ───────────────────────────────────────────────────────
_KEY_COMMAND       = "auto_learn_command"
_KEY_VOICE_TEXT    = "voice_unknown_text"
_KEY_ORIGINAL_TEXT = "auto_learn_original_text"  # texto original que disparou o fluxo


# ── Helpers de UI ─────────────────────────────────────────────────────────────

def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("EXECUTE", callback_data="learn_yes"),
            InlineKeyboardButton("ABORTE", callback_data="learn_no"),
        ]
    ])


# ── Confirmação ───────────────────────────────────────────────────────────────

async def ask_confirmation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    texto_desconhecido: str,
    command_name: str | None = None,
    edit_message=None,
    custom_message_text: str | None = None,
) -> int:
    """
    Pergunta ao usuário se ele quer criar um novo comando/contexto.
    Guarda o texto original e (opcionalmente) o nome do comando no user_data.
    Retorna o estado AGUARDANDO_CONFIRMACAO.

    Parâmetros:
      texto_desconhecido — o texto/transcrição que não foi reconhecido
      command_name       — nome do slash-command, se vier de /comando desconhecido
      edit_message       — objeto Message para editar (ex: msg de "Transcrevendo…")
    """
    context.user_data[_KEY_ORIGINAL_TEXT] = texto_desconhecido
    if command_name:
        context.user_data[_KEY_COMMAND] = command_name
    else:
        # Garante que um comando anterior fantasma não seja reutilizado acidentalmente
        context.user_data.pop(_KEY_COMMAND, None)

    if custom_message_text:
        msg_texto = custom_message_text
    else:
        msg_texto = (
            f"Comando falhou. Entrada não reconhecida: _\"{texto_desconhecido}\"_\n\n"
            "Deseja iniciar rotina de aprendizado para esta ação?"
        )

    if edit_message:
        await edit_message.edit_text(
            msg_texto,
            parse_mode="Markdown",
            reply_markup=_confirm_keyboard(),
        )
    else:
        await update.message.reply_text(
            msg_texto,
            parse_mode="Markdown",
            reply_markup=_confirm_keyboard(),
        )

    return AGUARDANDO_CONFIRMACAO


async def handle_confirmation_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """
    Lida com a resposta do botão inline (learn_yes / learn_no).
    Registrado tanto no ConversationHandler quanto como handler separado no app.
    """
    query = update.callback_query
    await query.answer()

    if query.data == "learn_no":
        context.user_data.pop(_KEY_COMMAND, None)
        context.user_data.pop(_KEY_ORIGINAL_TEXT, None)
        context.user_data.pop(_KEY_VOICE_TEXT, None)
        await query.edit_message_text("Abortado. Sistema operando normalmente.")
        return ConversationHandler.END

    # learn_yes — determinar próximo estado
    command_name = context.user_data.get(_KEY_COMMAND)
    original_text = context.user_data.get(_KEY_ORIGINAL_TEXT, "")

    if command_name:
        # Veio de /comando desconhecido — já temos o nome, pede a intenção
        await query.edit_message_text(
            f"Rotina de inserção iniciada para `/{command_name}`.\n\n"
            "Parâmetros vazios. Especifique as instruções diretas de sistema ou envie /cancelar.",
            parse_mode="Markdown"
        )
        return AGUARDANDO_INTENCAO
    else:
        # Veio de texto/voz livre — salva como voice_text e pede o nome
        context.user_data[_KEY_VOICE_TEXT] = original_text
        await query.edit_message_text(
            f"Iniciando síntese de nova subrotina baseada em: _\"{original_text}\"_\n\n"
            f"Defina o identificador primário desta rotina de sistema (ex: `/limpar_temp`).",
            parse_mode="Markdown"
        )
        return AGUARDANDO_NOME_COMANDO


# ── Entry-points ──────────────────────────────────────────────────────────────

async def handle_unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Entry-point: /comando desconhecido.
    Pergunta se o usuário quer criar o comando.
    """
    raw = update.message.text or ""
    command_name = raw.lstrip("/").split("@")[0].split()[0].lower()

    if not command_name:
        return ConversationHandler.END

    logger.info(f"Comando desconhecido detectado: /{command_name}")
    return await ask_confirmation(
        update, context,
        texto_desconhecido=f"/{command_name}",
        command_name=command_name,
    )


async def handle_voice_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Entry-point: mensagem de áudio/voz.
    Transcreve e tenta executar. Se a intenção for desconhecida,
    pergunta se o usuário quer criar um novo comando antes de iniciar a criação.
    """
    mic_listener.update_chat_id(update.effective_chat.id)

    msg = await update.message.reply_text("🎙️ Transcrevendo áudio...")

    voice = update.message.voice or update.message.audio
    if not voice:
        await msg.edit_text("Formato de áudio não reconhecido.")
        return ConversationHandler.END

    file = await context.bot.get_file(voice.file_id)
    suffix = ".ogg" if update.message.voice else ".mp3"

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            await file.download_to_drive(tmp.name)
            tmp_path = tmp.name

        texto = transcrever_audio(tmp_path)
        if not texto:
            await msg.edit_text("Falha na decodificação do áudio.")
            return ConversationHandler.END

        await msg.edit_text(f"🗣️ _{texto}_\n⚙️ Executando...", parse_mode="Markdown")

        await msg.edit_text(f"🗣️ _{texto}_\n⚙️ Analisando...", parse_mode="Markdown")

        from utils.orchestrator import run_orchestrator
        
        historico = context.user_data.get("chat_history", [])
        result = await run_orchestrator(texto, chat_history=historico)
        
        if "new_history" in result:
            context.user_data["chat_history"] = result["new_history"]


        if result.get("response"):
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            games = result.get("games_listed", [])
            if games:
                buttons = [[InlineKeyboardButton(f"🕹️ Abrir {j}", callback_data=f"abrir_jogo|{j}")] for j in games]
                reply_markup = InlineKeyboardMarkup(buttons)
                await msg.edit_text(f"🗣️ _{texto}_\n\n{result['response']}", parse_mode="Markdown", reply_markup=reply_markup)
            else:
                await msg.edit_text(f"🗣️ _{texto}_\n\n{result['response']}", parse_mode="Markdown")

        if result.get("wants_to_learn"):
            # Guarda a transcrição e pergunta antes de criar usando os botões inline
            return await ask_confirmation(
                update, context,
                texto_desconhecido=texto,
                edit_message=msg,
                custom_message_text="Confirme abaixo se deseja integrar esta nova funcionalidade ao sistema:"
            )
        
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Erro ao processar voz: {e}", exc_info=True)
        await msg.edit_text(f"Erro no processamento de áudio: `{e}`", parse_mode="Markdown")
        return ConversationHandler.END
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ── Estados ───────────────────────────────────────────────────────────────────

async def handle_voice_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Estado AGUARDANDO_NOME_COMANDO:
    Usuário digitou o nome desejado para o novo comando.
    """
    voice_text = context.user_data.get(_KEY_VOICE_TEXT, "")
    command_name = (update.message.text or "").strip().lstrip("/").split()[0].lower()

    if not command_name:
        await update.message.reply_text(
            "Formato inválido. Insira apenas o identificador (sem espaços ou caracteres especiais).\n"
            "Ex: `steam`, `obs`, `spotify`",
            parse_mode="Markdown",
        )
        return AGUARDANDO_NOME_COMANDO

    context.user_data[_KEY_COMMAND] = command_name

    await update.message.reply_text(
        f"Identificador `/{command_name}` aceito.\n\n"
        f"Transcrição: _\"{voice_text}\"_\n\n"
        f"Forneça as instruções de execução ou envie **ok** para confirmar a transcrição atual.",
        parse_mode="Markdown",
    )
    return AGUARDANDO_INTENCAO


async def receive_intention(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Estado AGUARDANDO_INTENCAO:
    Recebe a descrição do usuário e executa o pipeline completo.
    """
    command_name = context.user_data.get(_KEY_COMMAND)
    if not command_name:
        await update.message.reply_text("Sessão expirada. Reinicie a solicitação.")
        return ConversationHandler.END

    text = (update.message.text or "").strip()
    voice_text = context.user_data.get(_KEY_VOICE_TEXT, "")

    # Verifica se é uma confirmação simples → usa a transcrição de voz
    _confirmations = {"ok", "sim", "yes", "confirmar", "confirma"}
    if text.lower() in _confirmations and voice_text:
        user_intention = voice_text
    else:
        user_intention = text

    if not user_intention:
        await update.message.reply_text("Entrada inválida. Por favor, especifique a função desejada.")
        return AGUARDANDO_INTENCAO

    status_msg = await update.message.reply_text(
        f"Sintetizando lógica e arquitetura do módulo `/{command_name}`...\n"
        "_Processando..._",
        parse_mode="Markdown",
    )

    try:
        system_prompt, user_prompt = build_prompt(command_name, user_intention)
        raw_response = await generate_handler(system_prompt, user_prompt)
        code = validate(raw_response, command_name)
        save_handler_file(command_name, code)

        app: Application = context.application
        success = load_and_register(app, command_name)
        if not success:
            raise RuntimeError("Falha ao registrar o handler no app.")

        await update_telegram_menu(app)

        await status_msg.edit_text(
            f"Integração de sistema concluída.\n"
            f"Arquivo alocado: `handlers/custom/{command_name}.py`\n"
            f"Nova ferramenta pronta para execução: `/{command_name}`",
            parse_mode="Markdown",
        )
        logger.info(f"Comando /{command_name} criado e registrado com sucesso.")

    except APIError as e:
        logger.error(f"Erro na API ao gerar /{command_name}: {e}")
        await status_msg.edit_text(
            f"Falha na compilação do núcleo.\nMotivo mapeado: `{e}`",
            parse_mode="Markdown",
        )

    except ValidationError as e:
        logger.warning(f"Código inválido para /{command_name}: {e}")
        await status_msg.edit_text(
            f"Falha na validação de segurança do código gerado:\n`{e}`\n\n"
            "Reavalie a intenção e tente novamente.",
            parse_mode="Markdown",
        )

    except Exception as e:
        logger.error(f"Erro inesperado ao criar /{command_name}: {e}", exc_info=True)
        await status_msg.edit_text(
            f"Erro crítico no sistema: `{e}`",
            parse_mode="Markdown",
        )

    finally:
        context.user_data.pop(_KEY_COMMAND, None)
        context.user_data.pop(_KEY_VOICE_TEXT, None)
        context.user_data.pop(_KEY_ORIGINAL_TEXT, None)

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela o fluxo de criação de comando."""
    context.user_data.pop(_KEY_COMMAND, None)
    context.user_data.pop(_KEY_VOICE_TEXT, None)
    context.user_data.pop(_KEY_ORIGINAL_TEXT, None)
    await update.message.reply_text("🚫 Criação de comando cancelada.")
    return ConversationHandler.END


# ── Builder ───────────────────────────────────────────────────────────────────

def build_auto_learn_handler() -> ConversationHandler:
    """
    Constrói e retorna o ConversationHandler.

    IMPORTANTE: deve ser adicionado ANTES dos MessageHandlers genéricos
    (handle_text) no main.py para que os estados AGUARDANDO_* não sejam
    interceptados pelo handler de texto livre.
    """
    from handlers.voice import handle_text
    
    return ConversationHandler(
        entry_points=[
            # /comando desconhecido
            MessageHandler(filters.COMMAND, handle_unknown_command),
            # áudio/voz
            MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_entry),
            # chat em texto — Agora como entry point para poder criar comandos (Tool Calling)
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text),
        ],
        states={
            AGUARDANDO_CONFIRMACAO: [
                CallbackQueryHandler(handle_confirmation_callback, pattern="^learn_(yes|no)$"),
            ],
            AGUARDANDO_NOME_COMANDO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_voice_name),
            ],
            AGUARDANDO_INTENCAO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_intention),
            ],
        },
        fallbacks=[
            CommandHandler("cancelar", cancel),
        ],
        per_chat=True,
        per_user=True,
        conversation_timeout=120,
    )

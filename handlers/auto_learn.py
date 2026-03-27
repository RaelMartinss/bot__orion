"""
handlers/auto_learn.py

ConversationHandler que gerencia o fluxo completo de criação de novos comandos:
  1. Detecta comando desconhecido
  2. Pergunta o que o usuário quer que o comando faça
  3. Chama a API da Anthropic para gerar o handler
  4. Valida, salva e registra o novo comando

Estados do ConversationHandler:
  AGUARDANDO_INTENCAO — bot perguntou, aguarda resposta do usuário
"""

import logging

from telegram import Update
from telegram.ext import (
    Application,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
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

logger = logging.getLogger(__name__)

# Estado único do ConversationHandler
AGUARDANDO_INTENCAO = 1

# Chave usada para guardar o nome do comando no context.user_data
_KEY_COMMAND = "auto_learn_command"


async def handle_unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Ponto de entrada: detecta qualquer /comando desconhecido.
    Armazena o nome do comando e pergunta a intenção.
    """
    # Extrai o nome do comando (ex: "/obs@bot" → "obs")
    raw = update.message.text or ""
    command_name = raw.lstrip("/").split("@")[0].split()[0].lower()

    if not command_name:
        return ConversationHandler.END

    context.user_data[_KEY_COMMAND] = command_name
    logger.info(f"Comando desconhecido detectado: /{command_name}")

    await update.message.reply_text(
        f"🤖 O comando `/{command_name}` não existe ainda.\n\n"
        f"O que você quer que `/{command_name}` faça?\n"
        f"_(Descreva com suas palavras. Ex: \"abrir o OBS Studio\")_\n\n"
        f"Ou envie /cancelar para ignorar.",
        parse_mode="Markdown",
    )
    return AGUARDANDO_INTENCAO


async def receive_intention(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Recebe a descrição do usuário e executa o pipeline completo:
    prompt → API → validação → salvar → registrar → menu.
    """
    command_name = context.user_data.get(_KEY_COMMAND)
    if not command_name:
        await update.message.reply_text("❌ Sessão expirada. Tente o comando novamente.")
        return ConversationHandler.END

    user_intention = (update.message.text or "").strip()
    if not user_intention:
        await update.message.reply_text("❓ Não entendi. Descreva o que o comando deve fazer.")
        return AGUARDANDO_INTENCAO

    # Feedback imediato — a API pode demorar alguns segundos
    status_msg = await update.message.reply_text(
        f"⚙️ Gerando o comando `/{command_name}`...\n"
        f"_Isso pode levar alguns segundos._",
        parse_mode="Markdown",
    )

    try:
        # 1. Monta o prompt
        system_prompt, user_prompt = build_prompt(command_name, user_intention)

        # 2. Chama a API
        raw_response = await generate_handler(system_prompt, user_prompt)

        # 3. Valida via AST
        code = validate(raw_response, command_name)

        # 4. Salva o arquivo handlers/custom/<cmd>.py
        save_handler_file(command_name, code)

        # 5. Registra no app em runtime (sem restart)
        app: Application = context.application
        success = load_and_register(app, command_name)
        if not success:
            raise RuntimeError("Falha ao registrar o handler no app.")

        # 6. Atualiza o menu do Telegram
        await update_telegram_menu(app)

        await status_msg.edit_text(
            f"✅ Comando `/{command_name}` criado com sucesso!\n\n"
            f"📝 Intenção: _{user_intention}_\n"
            f"📁 Arquivo: `handlers/custom/{command_name}.py`\n\n"
            f"Use agora: `/{command_name}`",
            parse_mode="Markdown",
        )
        logger.info(f"Comando /{command_name} criado e registrado com sucesso.")

    except APIError as e:
        logger.error(f"Erro na API ao gerar /{command_name}: {e}")
        await status_msg.edit_text(
            f"❌ Erro ao chamar a API:\n`{e}`\n\nTente novamente mais tarde.",
            parse_mode="Markdown",
        )

    except ValidationError as e:
        logger.warning(f"Código inválido para /{command_name}: {e}")
        await status_msg.edit_text(
            f"⚠️ O código gerado não passou na validação de segurança:\n`{e}`\n\n"
            f"Tente descrever a intenção de forma diferente.",
            parse_mode="Markdown",
        )

    except Exception as e:
        logger.error(f"Erro inesperado ao criar /{command_name}: {e}", exc_info=True)
        await status_msg.edit_text(
            f"❌ Erro inesperado: `{e}`",
            parse_mode="Markdown",
        )

    finally:
        context.user_data.pop(_KEY_COMMAND, None)

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela o fluxo de criação de comando."""
    context.user_data.pop(_KEY_COMMAND, None)
    await update.message.reply_text("🚫 Criação de comando cancelada.")
    return ConversationHandler.END


def build_auto_learn_handler() -> ConversationHandler:
    """
    Constrói e retorna o ConversationHandler pronto para ser
    registrado no app via app.add_handler().

    IMPORTANTE: deve ser adicionado ANTES de qualquer fallback genérico,
    mas DEPOIS dos CommandHandlers fixos — assim comandos conhecidos
    nunca chegam até aqui.
    """
    return ConversationHandler(
        entry_points=[
            # Captura qualquer mensagem que comece com / e não seja conhecida
            MessageHandler(filters.COMMAND, handle_unknown_command),
        ],
        states={
            AGUARDANDO_INTENCAO: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_intention,
                ),
            ],
        },
        fallbacks=[
            MessageHandler(filters.COMMAND, cancel),
        ],
        # Cada chat_id tem seu próprio estado — sem interferência entre usuários
        per_chat=True,
        per_user=True,
        conversation_timeout=120,  # Expira em 2 minutos se o usuário não responder
    )

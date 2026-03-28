import asyncio
import logging
import os

from telegram import BotCommand, Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ConversationHandler,
    MessageHandler, CallbackQueryHandler, filters, ContextTypes,
)

from utils.memoria import carregar_memoria_longa, salvar_preferencia
from handlers.start import start
from handlers.jogos import jogo, listar_jogos, handle_jogo_botoes
from handlers.midia import youtube, netflix, spotify
from handlers.sistema import desligar, reiniciar, cancelar_desligamento
from handlers.volume import (
    volume_up, volume_down, volume_set, volume_receber, volume_cancelar,
    mute, AGUARDANDO_VOLUME,
)
from handlers.auto_learn import build_auto_learn_handler, handle_confirmation_callback
from utils.handler_registry import load_all_custom_handlers, update_telegram_menu
from handlers.voice import handle_text
from handlers.controle import pausar, proxima, anterior
import utils.mic_listener as mic_listener

from dotenv import load_dotenv

load_dotenv()  # Carrega variáveis de ambiente do .env

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("orion.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('TOKEN_TELEGRAM')
ADMIN_ID = 178663471  # ID do Rael para o Mic Listener usar a mesma consciência


async def handle_voz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ativa ou desativa a resposta por voz."""
    user_id = update.effective_user.id
    mem = carregar_memoria_longa(user_id)
    atual = mem.get("preferencias", {}).get("voice_active", False)
    
    novo_estado = not atual
    salvar_preferencia(user_id, "voice_active", novo_estado)
    
    status = "ATIVADO 🔊" if novo_estado else "DESATIVADO 🔇"
    await update.message.reply_text(f"Protocolo de voz {status}.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exibe a lista de comandos do Orion."""
    help_text = (
        "🤖 *ORION - Comandos Disponíveis*\n\n"
        "/start - Iniciar o sistema\n"
        "/ajuda - Mostrar esta lista\n"
        "/voz - Ligar/Desligar respostas por voz\n"
        "/cancelar - Abortar operação atual\n\n"
        "🎙️ *Dica*: Você pode falar diretamente comigo enviando áudios!"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def _run():
    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .build()
    )

    # Comandos padrão
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ajuda", help_command))
    app.add_handler(CommandHandler("voz", handle_voz))
    app.add_handler(CommandHandler("jogos", listar_jogos))
    app.add_handler(CommandHandler("jogo", jogo))
    app.add_handler(CommandHandler("youtube", youtube))
    app.add_handler(CommandHandler("netflix", netflix))
    app.add_handler(CommandHandler("spotify", spotify))
    app.add_handler(CommandHandler("vol_up", volume_up))
    app.add_handler(CommandHandler("vol_down", volume_down))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("volume", volume_set)],
        states={AGUARDANDO_VOLUME: [MessageHandler(filters.TEXT & ~filters.COMMAND, volume_receber)]},
        fallbacks=[CommandHandler("cancelar", volume_cancelar)],
    ))
    app.add_handler(CommandHandler("pause", pausar))
    app.add_handler(CommandHandler("proxima", proxima))
    app.add_handler(CommandHandler("anterior", anterior))
    app.add_handler(CommandHandler("desligar", desligar))
    app.add_handler(CommandHandler("reiniciar", reiniciar))
    app.add_handler(CommandHandler("cancelar", cancelar_desligamento))

    # Auto-aprendizado — ANTES dos handlers de texto/voz livre.
    # O ConversationHandler precisa interceptar o texto em AGUARDANDO_INTENCAO
    # antes que o handle_text captura a mensagem e responda "Não entendi".
    app.add_handler(build_auto_learn_handler())

    # CallbackQueryHandler separado: captura botões inline learn_yes/learn_no
    # quando o fluxo foi disparado pelo handle_text (fora do ConversationHandler)
    app.add_handler(CallbackQueryHandler(handle_confirmation_callback, pattern=r"^learn_(yes|no)$"))
    app.add_handler(CallbackQueryHandler(handle_jogo_botoes, pattern=r"^abrir_jogo\|"))

    # Texto livre (fica DEPOIS do ConversationHandler para nao interceptar estados)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("✅ Handlers registrados. Aguardando mensagens...")

    # ← FIX 2: removido app.run_polling() que bloqueava tudo abaixo
    async with app:
        await app.start()

        # ← FIX 3: removido set_my_commands manual — update_telegram_menu
        #           (chamado pelo on_startup) já faz isso incluindo os custom

        loop = asyncio.get_running_loop()
        mic_listener.configure(loop=loop, bot=app.bot)
        mic_listener.update_chat_id(chat_id=ADMIN_ID, user_id=ADMIN_ID)
        mic_listener.iniciar()

        logger.info("✅ Orion Bot rodando — voz, texto e microfone ativos.")
        await app.updater.start_polling()

        try:
            await asyncio.Event().wait()  # Roda até Ctrl+C
        finally:
            mic_listener.parar()
            await app.updater.stop()
            await app.stop()


async def on_startup(app):
    """Executado uma vez após o bot conectar, antes de começar a receber updates."""
    load_all_custom_handlers(app)
    await update_telegram_menu(app)
    logger.info("✅ Boot completo. Bot pronto.")


if __name__ == "__main__":
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("Bot encerrado pelo usuário.")
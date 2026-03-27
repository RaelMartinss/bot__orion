import asyncio
import logging
import os

from telegram import BotCommand
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ConversationHandler,
    MessageHandler, filters,
)

from handlers.start import start
from handlers.jogos import jogo, listar_jogos
from handlers.midia import youtube, netflix, spotify
from handlers.sistema import desligar, reiniciar, cancelar_desligamento
from handlers.volume import (
    volume_up, volume_down, volume_set, volume_receber, volume_cancelar,
    mute, AGUARDANDO_VOLUME,
)
from handlers.auto_learn import build_auto_learn_handler
from utils.handler_registry import load_all_custom_handlers, update_telegram_menu
from handlers.voice import handle_voice, handle_text
from handlers.controle import pausar, proxima, anterior
import utils.mic_listener as mic_listener

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("orion.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('TOKEN_TELEGRAM')


async def _run():
    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .post_init(on_startup)   # ← FIX 1: conecta o on_startup
        .build()
    )

    # Comandos padrão
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ajuda", start))
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

    # Áudio e texto livre
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Auto-aprendizado — DEPOIS dos fixos
    app.add_handler(build_auto_learn_handler())
    logger.info("✅ Handlers registrados. Aguardando mensagens...")

    # ← FIX 2: removido app.run_polling() que bloqueava tudo abaixo
    async with app:
        await app.start()

        # ← FIX 3: removido set_my_commands manual — update_telegram_menu
        #           (chamado pelo on_startup) já faz isso incluindo os custom

        loop = asyncio.get_running_loop()
        mic_listener.configure(loop=loop, bot=app.bot)
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
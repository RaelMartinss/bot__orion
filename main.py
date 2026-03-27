import logging
from telegram.ext import ApplicationBuilder, CommandHandler

from handlers.start import start
from handlers.jogos import jogo, listar_jogos
from handlers.midia import youtube, netflix, spotify
from handlers.sistema import desligar, reiniciar, cancelar_desligamento
from handlers.volume import volume_up, volume_down, mute

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("orion.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

TOKEN = "8671153150:AAG_KgzQBkThl_-1ZWwXcJj7e1EBfPci634"


def main():
    logger.info("🛰️ Iniciando Orion Bot...")
    app = ApplicationBuilder().token(TOKEN).build()

    # Registro
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ajuda", start))

    # Jogos
    app.add_handler(CommandHandler("jogos", listar_jogos))
    app.add_handler(CommandHandler("jogo", jogo))

    # Mídia
    app.add_handler(CommandHandler("youtube", youtube))
    app.add_handler(CommandHandler("netflix", netflix))
    app.add_handler(CommandHandler("spotify", spotify))

    # Volume
    app.add_handler(CommandHandler("vol_up", volume_up))
    app.add_handler(CommandHandler("vol_down", volume_down))
    app.add_handler(CommandHandler("mute", mute))

    # Sistema
    app.add_handler(CommandHandler("desligar", desligar))
    app.add_handler(CommandHandler("reiniciar", reiniciar))
    app.add_handler(CommandHandler("cancelar", cancelar_desligamento))

    logger.info("✅ Handlers registrados. Bot rodando...")
    app.run_polling()


if __name__ == "__main__":
    main()

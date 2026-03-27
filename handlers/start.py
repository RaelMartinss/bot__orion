"""
handlers/start.py
Mensagem de boas-vindas e lista de comandos.
"""

from telegram import Update
from telegram.ext import ContextTypes


MENU = """
🛰️ *Orion Bot — Painel de Controle*

🎮 *Jogos*
`/jogos` — Lista todos os jogos Steam instalados
`/jogo <nome>` — Abre um jogo (nome parcial funciona!)

🎵 *Mídia*
`/youtube <busca>` — Abre o YouTube
`/netflix <busca>` — Abre a Netflix
`/spotify <busca>` — Abre o Spotify

🔊 *Volume*
`/vol_up [%]` — Aumenta o volume (padrão: 10%)
`/vol_down [%]` — Diminui o volume (padrão: 10%)
`/mute` — Muta/desmuta

⚙️ *Sistema*
`/desligar [segundos]` — Desliga o PC (padrão: 60s)
`/reiniciar [segundos]` — Reinicia o PC (padrão: 60s)
`/cancelar` — Cancela desligamento agendado

ℹ️ `/ajuda` — Mostra este menu
"""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(MENU, parse_mode="Markdown")

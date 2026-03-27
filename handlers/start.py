"""
handlers/start.py
Mensagem de boas-vindas e lista de comandos.
"""

from telegram import Update
from telegram.ext import ContextTypes


MENU = """
🛰️ *Orion Bot — Painel de Controle*

🎙️ *Voz & Texto Livre*
Envie um áudio ou escreva em linguagem natural:
• _toca menino da porteira_
• _abre o minecraft_
• _aumenta o volume_
• _desliga o pc em 5 minutos_
O microfone do PC também escuta comandos!

🎮 *Jogos*
`/jogos` — Lista todos os jogos Steam instalados
`/jogo <nome>` — Abre um jogo (nome parcial funciona!)

🎵 *Mídia*
`/youtube <busca>` — Abre o YouTube
`/netflix <busca>` — Abre a Netflix
`/spotify <busca>` — Abre o Spotify

⏯️ *Reprodução*
`/pause` — Pausa/retoma toggle (YouTube ou mídia ativa)
`/proxima` — Próxima faixa/vídeo
`/anterior` — Faixa/vídeo anterior
Ou fale: _"pausa"_, _"próxima"_, _"anterior"_

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
SEU_USER_ID = 178663471

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SEU_USER_ID:
        return
    await update.message.reply_text(MENU, parse_mode="Markdown")

"""
handlers/midia.py
Comandos de mídia: YouTube, Netflix, Spotify.
"""

import webbrowser
import logging
from urllib.parse import quote_plus
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def youtube(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /youtube <busca> — Abre o YouTube com a busca especificada.
    /youtube           — Abre a página inicial do YouTube.
    """
    if context.args:
        query = " ".join(context.args)
        url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
        webbrowser.open(url)
        await update.message.reply_text(f"▶️ Buscando no YouTube: *{query}*", parse_mode="Markdown")
    else:
        webbrowser.open("https://www.youtube.com")
        await update.message.reply_text("▶️ YouTube aberto.")


async def netflix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /netflix <busca> — Abre o Netflix (com busca, se informada).
    """
    if context.args:
        query = " ".join(context.args)
        url = f"https://www.netflix.com/search?q={quote_plus(query)}"
        webbrowser.open(url)
        await update.message.reply_text(f"🎬 Buscando na Netflix: *{query}*", parse_mode="Markdown")
    else:
        webbrowser.open("https://www.netflix.com")
        await update.message.reply_text("🎬 Netflix aberto.")


async def spotify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /spotify <busca> — Abre o Spotify Web com a busca especificada.
    /spotify          — Abre a página inicial do Spotify.
    """
    if context.args:
        query = " ".join(context.args)
        url = f"https://open.spotify.com/search/{quote_plus(query)}"
        webbrowser.open(url)
        await update.message.reply_text(f"🎵 Buscando no Spotify: *{query}*", parse_mode="Markdown")
    else:
        webbrowser.open("https://open.spotify.com")
        await update.message.reply_text("🎵 Spotify aberto.")

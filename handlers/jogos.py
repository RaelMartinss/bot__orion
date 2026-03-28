"""
handlers/jogos.py
Comandos relacionados a jogos — lista e abre automaticamente
qualquer jogo Steam instalado, sem hardcode de caminhos.
"""

import os
import subprocess
import logging
from difflib import get_close_matches
from telegram import Update
from telegram.ext import ContextTypes

from utils.steam_scanner import escanear_jogos_steam

logger = logging.getLogger(__name__)

# Cache dos jogos escaneados (atualizado sob demanda com /jogos)
_cache_jogos: dict[str, str] = {}


def _get_jogos() -> dict[str, str]:
    """Retorna jogos do cache, escaneando se ainda não foi feito."""
    global _cache_jogos
    if not _cache_jogos:
        _cache_jogos = escanear_jogos_steam()
    return _cache_jogos


async def listar_jogos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /jogos — Lista todos os jogos Steam instalados e atualiza o cache.
    """
    global _cache_jogos
    msg = await update.message.reply_text("🔍 Escaneando jogos Steam instalados...")

    _cache_jogos = escanear_jogos_steam()  # Força rescan
    jogos = _cache_jogos

    if not jogos:
        await msg.edit_text(
            "❌ Nenhum jogo Steam encontrado.\n"
            "Verifique se o Steam está instalado e os jogos aparecem como instalados."
        )
        return

    # Monta lista paginada (Telegram tem limite de 4096 chars por mensagem)
    nomes = sorted(jogos.keys(), key=str.lower)
    linhas = [f"🎮 *{len(nomes)} jogos encontrados:*\n"]
    for i, nome in enumerate(nomes, 1):
        linhas.append(f"`{i:02d}.` {nome}")

    linhas.append("\n💡 Use `/jogo <nome>` para abrir — funciona com nome parcial!")

    # Divide se necessário
    texto_completo = "\n".join(linhas)
    if len(texto_completo) <= 4000:
        await msg.edit_text(texto_completo, parse_mode="Markdown")
    else:
        # Envia em partes
        await msg.edit_text(linhas[0], parse_mode="Markdown")
        chunk = []
        for linha in linhas[1:]:
            chunk.append(linha)
            if len("\n".join(chunk)) > 3500:
                await update.message.reply_text("\n".join(chunk[:-1]), parse_mode="Markdown")
                chunk = [chunk[-1]]
        if chunk:
            await update.message.reply_text("\n".join(chunk), parse_mode="Markdown")


async def jogo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /jogo <nome> — Abre o jogo pelo nome (busca aproximada).
    Exemplos:
        /jogo minecraft
        /jogo counter
        /jogo the witcher
    """
    if not context.args:
        await update.message.reply_text(
            "❓ Informe o nome do jogo.\n"
            "Exemplo: `/jogo minecraft`\n\n"
            "Use `/jogos` para ver todos disponíveis.",
            parse_mode="Markdown",
        )
        return

    busca = " ".join(context.args).strip()
    jogos = _get_jogos()

    if not jogos:
        await update.message.reply_text(
            "❌ Nenhum jogo encontrado. Use `/jogos` para escanear.", parse_mode="Markdown"
        )
        return

    nomes = list(jogos.keys())

    # 1. Correspondência exata (case-insensitive)
    match_exato = next((n for n in nomes if n.lower() == busca.lower()), None)

    # 2. Correspondência parcial
    if not match_exato:
        match_parcial = [n for n in nomes if busca.lower() in n.lower()]
        if len(match_parcial) == 1:
            match_exato = match_parcial[0]
        elif len(match_parcial) > 1:
            lista = "\n".join(f"• {n}" for n in sorted(match_parcial)[:10])
            await update.message.reply_text(
                f"🔎 Vários jogos encontrados para *{busca}*:\n\n{lista}\n\n"
                "Seja mais específico!",
                parse_mode="Markdown",
            )
            return

    # 3. Busca aproximada (fuzzy)
    if not match_exato:
        sugestoes = get_close_matches(busca, nomes, n=3, cutoff=0.4)
        if sugestoes:
            lista = "\n".join(f"• `{s}`" for s in sugestoes)
            await update.message.reply_text(
                f"❓ *{busca}* não encontrado. Você quis dizer:\n\n{lista}\n\n"
                "Tente `/jogo <nome exato>`.",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                f"❌ Jogo *{busca}* não encontrado.\n"
                "Use `/jogos` para ver todos os jogos instalados.",
                parse_mode="Markdown",
            )
        return

    # Abre o jogo
    caminho = jogos[match_exato]
    logger.info(f"Abrindo jogo: {match_exato} → {caminho}")

    try:
        if caminho.startswith("steam://"):
            # Abre via protocolo Steam (jogos sem .exe direto)
            os.startfile(caminho)
        else:
            # Abre o executável diretamente
            subprocess.Popen(
                [caminho],
                cwd=os.path.dirname(caminho),
                creationflags=subprocess.DETACHED_PROCESS if os.name == "nt" else 0,
            )
        await update.message.reply_text(
            f"🎮 Abrindo *{match_exato}*...", parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Erro ao abrir {match_exato}: {e}")
        await update.message.reply_text(
            f"❌ Erro ao abrir *{match_exato}*: `{e}`", parse_mode="Markdown"
        )

async def handle_jogo_botoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lida com o clique nos botões inline de jogo gerados pelo Claude."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("abrir_jogo|"):
        nome_jogo = data.split("|", 1)[1]
        
        from utils.executor import _abrir_jogo
        res = _abrir_jogo(nome_jogo)
        
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=res,
            parse_mode="Markdown"
        )

"""
handlers/sistema.py
Comandos de controle do sistema: desligar e reiniciar com contagem regressiva.
"""

import os
import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

DELAY_PADRAO = 60  # segundos


async def desligar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /desligar       — Desliga o PC em 60 segundos.
    /desligar 300   — Desliga em 5 minutos.
    /desligar 0     — Desliga imediatamente.
    """
    try:
        delay = int(context.args[0]) if context.args else DELAY_PADRAO
        delay = max(0, delay)

        os.system(f"shutdown /s /t {delay}")
        logger.info(f"Desligamento agendado em {delay}s pelo usuário {update.effective_user.id}")

        if delay == 0:
            await update.message.reply_text("💤 Desligando agora...")
        else:
            minutos = delay // 60
            segundos = delay % 60
            tempo_str = f"{minutos}min {segundos}s" if minutos else f"{segundos}s"
            await update.message.reply_text(
                f"⏳ PC será desligado em *{tempo_str}*.\n"
                "Use `/cancelar` para cancelar.",
                parse_mode="Markdown",
            )
    except Exception as e:
        logger.error(f"Erro ao desligar: {e}")
        await update.message.reply_text(f"❌ Erro ao desligar: `{e}`", parse_mode="Markdown")


async def reiniciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /reiniciar       — Reinicia o PC em 60 segundos.
    /reiniciar 0     — Reinicia imediatamente.
    """
    try:
        delay = int(context.args[0]) if context.args else DELAY_PADRAO
        delay = max(0, delay)

        os.system(f"shutdown /r /t {delay}")
        logger.info(f"Reinicialização agendada em {delay}s pelo usuário {update.effective_user.id}")

        if delay == 0:
            await update.message.reply_text("🔄 Reiniciando agora...")
        else:
            minutos = delay // 60
            segundos = delay % 60
            tempo_str = f"{minutos}min {segundos}s" if minutos else f"{segundos}s"
            await update.message.reply_text(
                f"⏳ PC será reiniciado em *{tempo_str}*.\n"
                "Use `/cancelar` para cancelar.",
                parse_mode="Markdown",
            )
    except Exception as e:
        logger.error(f"Erro ao reiniciar: {e}")
        await update.message.reply_text(f"❌ Erro ao reiniciar: `{e}`", parse_mode="Markdown")


async def cancelar_desligamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /cancelar — Cancela qualquer desligamento/reinicialização agendada.
    """
    try:
        resultado = os.system("shutdown /a")
        if resultado == 0:
            await update.message.reply_text("✅ Desligamento/reinicialização *cancelado*.", parse_mode="Markdown")
        else:
            await update.message.reply_text("ℹ️ Nenhum desligamento agendado no momento.")
    except Exception as e:
        logger.error(f"Erro ao cancelar desligamento: {e}")
        await update.message.reply_text(f"❌ Erro: `{e}`", parse_mode="Markdown")

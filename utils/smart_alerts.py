"""
utils/smart_alerts.py

Motor de notificações inteligentes do Orion.

Monitores ativos:
  - 📧 Email: avisa quando chega e-mail importante (não lido)
  - 📅 Agenda: avisa reuniões/compromissos 15 min antes
  - 📥 Downloads: avisa quando um arquivo novo aparece na pasta Downloads

Integração: chamado em main.py com asyncio.create_task(start_smart_alerts(bot, user_ids))
Usa presence.py para entregar por voz se o usuário estiver no PC.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from utils.presence import usuario_presente, aguardar_retorno

logger = logging.getLogger(__name__)

# ── Persistência de UIDs já notificados (sobrevive a restart) ─────────────────

_UIDS_FILE = Path("memoria/email_uids_notificados.json")

def _carregar_uids() -> set[str]:
    if _UIDS_FILE.exists():
        try:
            return set(json.loads(_UIDS_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return set()

def _salvar_uids(uids: set[str]) -> None:
    _UIDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Mantém apenas os 500 mais recentes para não crescer infinitamente
    lista = list(uids)[-500:]
    _UIDS_FILE.write_text(json.dumps(lista), encoding="utf-8")

# ── Anti-spam / estado dos monitores ─────────────────────────────────────────

_email_uids_vistos: set[str] = _carregar_uids()  # persiste entre restarts
_agenda_ids_notificados: set[str] = set()      # IDs de eventos já alertados
_downloads_vistos: set[str] = set()            # Arquivos já notificados
_downloads_inicializado: bool = False           # Ignora arquivos pré-existentes

# Pendentes para quando o usuário voltar: {user_id → [(telegram, voz)]}
_pendentes: dict[int, list[tuple[str, str]]] = {}


# ── Entrega de alertas ────────────────────────────────────────────────────────

async def _falar(texto: str) -> None:
    try:
        from utils.tts_manager import gerar_audio, limpar_audio, reproduzir_local
        audio_path = await gerar_audio(texto)
        if audio_path:
            await asyncio.to_thread(reproduzir_local, audio_path, True)
            limpar_audio(audio_path)
    except Exception as e:
        logger.warning("TTS falhou no smart_alerts: %s", e)


async def _entregar(bot, user_id: int, msg_telegram: str, msg_voz: str) -> None:
    """Envia Telegram e fala no PC se o usuário estiver presente."""
    try:
        await bot.send_message(chat_id=user_id, text=msg_telegram,
                               parse_mode="Markdown", disable_notification=False)
    except Exception as e:
        logger.error("Erro ao enviar notificação para %s: %s", user_id, e)

    if usuario_presente():
        await _falar(msg_voz)
    else:
        _pendentes.setdefault(user_id, []).append((msg_telegram, msg_voz))
        asyncio.create_task(_aguardar_e_entregar_pendentes(bot, user_id))


async def _aguardar_e_entregar_pendentes(bot, user_id: int) -> None:
    """Quando o usuário voltar ao PC, entrega os alertas de voz pendentes."""
    voltou = await aguardar_retorno(timeout_minutos=480)
    if not voltou:
        _pendentes.pop(user_id, None)
        return

    pendentes = _pendentes.pop(user_id, [])
    if not pendentes:
        return

    hora = datetime.now().hour
    saudacao = "Bom dia" if hora < 12 else "Boa tarde" if hora < 18 else "Boa noite"
    await _falar(f"{saudacao}, Rael. Algumas coisas aconteceram enquanto você estava fora.")
    await asyncio.sleep(1)

    for _, msg_voz in pendentes:
        await _falar(msg_voz)
        await asyncio.sleep(0.8)


# ── Monitor de E-mail ─────────────────────────────────────────────────────────

# Palavras-chave que indicam e-mail promocional/marketing — ignorados
_FILTRO_PROMO_REMETENTE = {
    "shein", "serasa", "kucoin", "picpay", "uniasselvi", "capcut",
    "noreply", "no-reply", "newsletter", "marketing", "promocao",
    "promoção", "desconto", "oferta", "fatura", "boleto", "cupom",
    "notificacao", "notificação", "donotreply", "do-not-reply",
}
_FILTRO_PROMO_ASSUNTO = {
    "desconto", "oferta", "promoção", "promocao", "ganhe", "grátis",
    "gratis", "indique", "recompensa", "cupom", "até 99%", "até 90%",
    "score mudou", "limpa nome", "dívida", "divida", "não perca",
    "não deixe", "última chance", "convite especial", "transmitir",
    "reivindicar", "invite", "unsubscribe",
}

def _eh_promocional(remetente: str, assunto: str) -> bool:
    """Retorna True se o e-mail parece ser marketing/promoção."""
    rem = remetente.lower()
    subj = assunto.lower()
    # Header List-Unsubscribe = e-mail marketing por definição
    # (verificado via flag is_promo no dict)
    for palavra in _FILTRO_PROMO_REMETENTE:
        if palavra in rem:
            return True
    for palavra in _FILTRO_PROMO_ASSUNTO:
        if palavra in subj:
            return True
    return False


async def _checar_email(bot, user_ids: list[int]) -> None:
    """
    Detecta e-mails não lidos novos e notifica com resumo agrupado.
    Filtros:
      - Apenas UNSEEN (não lidos)
      - Apenas dos últimos 10 dias
      - Máx 5 por ciclo de notificação
      - Exclui promoções e marketing
      - UIDs persistidos em disco (sem repetição após restart)
    """
    import imaplib
    import email as email_lib
    from email.header import decode_header
    from email.utils import parsedate_to_datetime

    EMAIL_ADDR = "raelpgm2@gmail.com"
    APP_PWD = "zwfy aruq fadb kmqx"
    LIMITE_DIAS = 10
    LIMITE_EMAILS = 5

    def _buscar_nao_lidos() -> list[dict]:
        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(EMAIL_ADDR, APP_PWD.replace(" ", ""))
            mail.select("inbox")

            # Busca apenas UNSEEN dos últimos LIMITE_DIAS dias
            since = (datetime.now() - timedelta(days=LIMITE_DIAS)).strftime("%d-%b-%Y")
            _, data = mail.search(None, f'(UNSEEN SINCE {since})')
            uids = data[0].split()
            if not uids:
                mail.logout()
                return []

            # Pega os mais recentes primeiro, limita para evitar sobrecarga
            uids = uids[-20:][::-1]

            resultados = []
            for uid in uids:
                if len(resultados) >= LIMITE_EMAILS:
                    break
                uid_str = uid.decode()
                if uid_str in _email_uids_vistos:
                    continue

                # Busca apenas headers (mais rápido que RFC822 completo)
                _, msg_data = mail.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE LIST-UNSUBSCRIBE)])")
                for part in msg_data:
                    if not isinstance(part, tuple):
                        continue
                    msg = email_lib.message_from_bytes(part[1])

                    # Decodifica assunto
                    subj_raw = msg.get("Subject") or ""
                    subj_parts = decode_header(subj_raw)
                    subj = ""
                    for s, enc in subj_parts:
                        if isinstance(s, bytes):
                            subj += s.decode(enc or "utf-8", errors="ignore")
                        else:
                            subj += s or ""

                    remetente = msg.get("From", "Desconhecido")
                    tem_unsubscribe = bool(msg.get("List-Unsubscribe"))

                    # Filtra promoções
                    if tem_unsubscribe or _eh_promocional(remetente, subj):
                        _email_uids_vistos.add(uid_str)  # marca como visto para não re-checar
                        continue

                    resultados.append({
                        "uid": uid_str,
                        "assunto": subj.strip() or "(sem assunto)",
                        "de": remetente.split("<")[0].strip().strip('"'),
                    })
                    _email_uids_vistos.add(uid_str)

            mail.logout()
            _salvar_uids(_email_uids_vistos)
            return resultados

        except Exception as e:
            logger.debug("Monitor email: %s", e)
            return []

    novos = await asyncio.to_thread(_buscar_nao_lidos)
    if not novos:
        return

    # Notificação agrupada em vez de uma mensagem por e-mail
    qtd = len(novos)
    linhas = "\n".join(f"• *{m['de']}*: _{m['assunto']}_" for m in novos)
    telegram = (
        f"📧 *{qtd} e-mail{'s' if qtd > 1 else ''} não lido{'s' if qtd > 1 else ''} novo{'s' if qtd > 1 else ''}*\n\n"
        f"{linhas}"
    )
    voz = (
        f"Rael, você tem {qtd} e-mail{'s' if qtd > 1 else ''} não lido{'s' if qtd > 1 else ''} novo{'s' if qtd > 1 else ''}. "
        f"Os remetentes são: {', '.join(m['de'] for m in novos)}."
    )
    for uid in user_ids:
        await _entregar(bot, uid, telegram, voz)


# ── Monitor de Agenda ─────────────────────────────────────────────────────────

async def _checar_agenda(bot, user_ids: list[int]) -> None:
    """Alerta compromissos que começam em até 15 minutos."""
    def _proximos_eventos() -> list[dict]:
        try:
            from plugins.agenda import eventos_hoje
            agora = datetime.now(timezone.utc)
            eventos = eventos_hoje()
            alertar = []
            for ev in eventos:
                ev_id = ev.get("id", "")
                if ev_id in _agenda_ids_notificados:
                    continue
                inicio_str = ev.get("start", {}).get("dateTime")
                if not inicio_str:
                    continue
                inicio = datetime.fromisoformat(inicio_str)
                if inicio.tzinfo is None:
                    inicio = inicio.replace(tzinfo=timezone.utc)
                diff = (inicio - agora).total_seconds()
                if 0 < diff <= 15 * 60:  # entre agora e 15 minutos
                    alertar.append(ev)
                    _agenda_ids_notificados.add(ev_id)
            return alertar
        except Exception as e:
            logger.debug("Monitor agenda: %s", e)
            return []

    eventos = await asyncio.to_thread(_proximos_eventos)
    for ev in eventos:
        titulo = ev.get("summary", "Compromisso")
        inicio_str = ev.get("start", {}).get("dateTime", "")
        try:
            inicio = datetime.fromisoformat(inicio_str)
            horario = inicio.strftime("%H:%M")
        except Exception:
            horario = "em breve"
        telegram = f"📅 *Lembrete de agenda*\n_{titulo}_ começa às *{horario}*"
        voz = f"Rael, atenção: {titulo} começa às {horario}. Faltam cerca de 15 minutos."
        for uid in user_ids:
            await _entregar(bot, uid, telegram, voz)


# ── Monitor de Downloads ──────────────────────────────────────────────────────

async def _checar_downloads(bot, user_ids: list[int]) -> None:
    """Detecta arquivos novos (completos) na pasta Downloads."""
    global _downloads_inicializado

    pasta = Path.home() / "Downloads"
    if not pasta.exists():
        return

    def _listar() -> list[Path]:
        try:
            return [
                f for f in pasta.iterdir()
                if f.is_file()
                and not f.name.startswith(".")
                and not f.suffix.lower() in (".crdownload", ".part", ".tmp")
                and f.stat().st_size > 0
            ]
        except Exception:
            return []

    arquivos = await asyncio.to_thread(_listar)

    if not _downloads_inicializado:
        # Primeira rodada: apenas popula o set sem notificar
        for f in arquivos:
            _downloads_vistos.add(f.name)
        _downloads_inicializado = True
        return

    for f in arquivos:
        if f.name in _downloads_vistos:
            continue
        _downloads_vistos.add(f.name)

        tamanho_mb = f.stat().st_size / (1024 * 1024)
        tamanho_str = f"{tamanho_mb:.1f} MB" if tamanho_mb >= 1 else f"{f.stat().st_size // 1024} KB"
        telegram = f"📥 *Download concluído*\n`{f.name}` — {tamanho_str}"
        voz = f"Rael, o download de {f.stem} foi concluído. {tamanho_str}."
        for uid in user_ids:
            await _entregar(bot, uid, telegram, voz)


# ── Loop principal ────────────────────────────────────────────────────────────

async def _loop_smart_alerts(bot, user_ids: list[int]) -> None:
    logger.info("🔔 Smart alerts iniciado para %d usuário(s).", len(user_ids))

    tick = 0
    while True:
        await asyncio.sleep(30)  # pulso a cada 30 segundos
        tick += 1

        try:
            # Downloads: a cada 30s
            await _checar_downloads(bot, user_ids)

            # Agenda: a cada 2 min (tick par)
            if tick % 4 == 0:
                await _checar_agenda(bot, user_ids)

            # E-mail: a cada 5 min
            if tick % 10 == 0:
                await _checar_email(bot, user_ids)

        except Exception as e:
            logger.error("Erro no loop smart_alerts: %s", e, exc_info=True)


async def start_smart_alerts(bot, user_ids: list[int]) -> None:
    """Entry point: chame com asyncio.create_task() no main.py."""
    asyncio.create_task(_loop_smart_alerts(bot, user_ids))

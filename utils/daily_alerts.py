"""
utils/daily_alerts.py

Alertas automáticos diários: verifica se o time favorito do usuário joga hoje
e notifica via Telegram + voz no PC (se presente).

Integração: chamado em main.py com asyncio.create_task(start_daily_alerts(bot, user_ids))
"""

import asyncio
import logging
from datetime import datetime, date

from utils.memoria import carregar_memoria_longa
from utils.presence import usuario_presente, aguardar_retorno

logger = logging.getLogger(__name__)

# Anti-spam: {user_id → data da última notificação}
_notificado_em: dict[int, date] = {}

# Alertas pendentes para entregar quando o usuário voltar: {user_id → [mensagens]}
_pendentes: dict[int, list[str]] = {}


def _time_do_usuario(user_id: int) -> str | None:
    mem = carregar_memoria_longa(user_id)
    time_fav = mem.get("preferencias", {}).get("time_favorito")
    if time_fav:
        return time_fav
    for fato in mem.get("fatos", []):
        for time in ("flamengo", "vasco", "palmeiras", "corinthians", "são paulo",
                     "sao paulo", "botafogo", "fluminense", "grêmio", "gremio",
                     "internacional", "cruzeiro", "atlético", "atletico"):
            if time in fato.lower():
                return time
    return None


def _jogo_hoje(time: str) -> dict | None:
    import json
    import urllib.parse
    import urllib.request

    def _get(url):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))

    try:
        teams = _get(
            "https://www.thesportsdb.com/api/v1/json/3/searchteams.php?t="
            + urllib.parse.quote(time)
        ).get("teams") or []
        if not teams:
            return None

        team = next(
            (t for t in teams if "brazil" in (t.get("strCountry") or "").lower()),
            teams[0],
        )
        team_id = team.get("idTeam")
        if not team_id:
            return None

        events = _get(
            f"https://www.thesportsdb.com/api/v1/json/3/eventsnext.php?id={team_id}"
        ).get("events") or []
        if not events:
            return None

        event = events[0]
        event_date_str = event.get("dateEvent", "")
        if not event_date_str:
            return None

        if datetime.strptime(event_date_str, "%Y-%m-%d").date() != date.today():
            return None

        return {
            "home": event.get("strHomeTeam", "?"),
            "away": event.get("strAwayTeam", "?"),
            "league": event.get("strLeague", ""),
            "time_utc": event.get("strTime", ""),
            "venue": event.get("strVenue", ""),
        }
    except Exception as e:
        logger.warning("Erro ao consultar jogo de hoje para '%s': %s", time, e)
        return None


def _formatar_telegram(time: str, jogo: dict) -> str:
    home, away = jogo["home"], jogo["away"]
    league = f" — {jogo['league']}" if jogo["league"] else ""
    horario = f" às {jogo['time_utc']} UTC" if jogo["time_utc"] else ""
    venue = f"\n🏟️ {jogo['venue']}" if jogo["venue"] else ""
    return (
        f"⚽ *Hoje tem jogo do {time.title()}!*{league}\n"
        f"🆚 {home} x {away}{horario}{venue}"
    )


def _formatar_voz(time: str, jogo: dict) -> str:
    home, away = jogo["home"], jogo["away"]
    horario = f" às {jogo['time_utc']} UTC" if jogo["time_utc"] else ""
    return f"Rael, hoje tem jogo do {time.title()}{horario}. {home} contra {away}."


async def _falar(texto: str) -> None:
    """Gera TTS e reproduz nos speakers do PC."""
    try:
        from utils.tts_manager import gerar_audio, limpar_audio, reproduzir_local
        audio_path = await gerar_audio(texto)
        if audio_path:
            await asyncio.to_thread(reproduzir_local, audio_path, True)
            limpar_audio(audio_path)
    except Exception as e:
        logger.warning("Erro ao falar alerta: %s", e)


async def _entregar_alerta(bot, user_id: int, msg_telegram: str, msg_voz: str) -> None:
    """Envia Telegram e, se presente, também fala no PC."""
    try:
        await bot.send_message(chat_id=user_id, text=msg_telegram, parse_mode="Markdown")
    except Exception as e:
        logger.error("Erro ao enviar Telegram para %s: %s", user_id, e)

    if usuario_presente():
        await _falar(msg_voz)
    else:
        # Guarda para entregar ao voltar
        _pendentes.setdefault(user_id, []).append(msg_voz)
        logger.info("Usuário ausente — alerta de voz guardado para entrega posterior.")


async def _monitorar_retorno(bot, user_id: int) -> None:
    """
    Fica em background aguardando o usuário voltar ao PC.
    Quando detecta presença, entrega os alertas pendentes com saudação Jarvis.
    """
    voltou = await aguardar_retorno(timeout_minutos=480)  # Aguarda até 8h
    if not voltou:
        _pendentes.pop(user_id, None)
        return

    pendentes = _pendentes.pop(user_id, [])
    if not pendentes:
        return

    hora = datetime.now().hour
    saudacao = "Bom dia" if hora < 12 else "Boa tarde" if hora < 18 else "Boa noite"
    intro = f"{saudacao}, Rael. Bem-vindo de volta. Algumas coisas aconteceram enquanto você estava ausente."
    await _falar(intro)
    await asyncio.sleep(1)

    for msg in pendentes:
        await _falar(msg)
        await asyncio.sleep(0.5)


async def _checar_e_notificar(bot, user_id: int) -> None:
    hoje = date.today()
    if _notificado_em.get(user_id) == hoje:
        return

    time = _time_do_usuario(user_id)
    if not time:
        return

    jogo = await asyncio.to_thread(_jogo_hoje, time)
    if not jogo:
        logger.info("Alerta diário: %s não joga hoje.", time)
        return

    msg_telegram = _formatar_telegram(time, jogo)
    msg_voz = _formatar_voz(time, jogo)

    _notificado_em[user_id] = hoje
    await _entregar_alerta(bot, user_id, msg_telegram, msg_voz)

    # Se estava ausente, monitora o retorno em background
    if not usuario_presente():
        asyncio.create_task(_monitorar_retorno(bot, user_id))


async def _loop_diario(bot, user_ids: list[int]) -> None:
    logger.info("Daily alerts iniciado para %d usuário(s).", len(user_ids))
    while True:
        agora = datetime.now()
        if agora.hour == 8 and agora.minute == 0:
            for uid in user_ids:
                await _checar_e_notificar(bot, uid)
            await asyncio.sleep(61)
        else:
            await asyncio.sleep(30)


async def start_daily_alerts(bot, user_ids: list[int]) -> None:
    """Entry point: chame com asyncio.create_task() no main.py."""
    asyncio.create_task(_loop_diario(bot, user_ids))

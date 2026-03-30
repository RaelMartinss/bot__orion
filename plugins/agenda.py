"""
plugins/agenda.py

Integração com Google Calendar via API oficial.

Primeira vez: rode `uv run python plugins/agenda.py --setup`
Isso abre o navegador para autorizar e salva o token em memoria/google_token.json.
Depois disso, tudo funciona automaticamente.

Credenciais: baixe credentials.json em console.cloud.google.com
→ APIs & Services → Credentials → OAuth 2.0 Client ID → Desktop app
"""

import os
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_CREDS_FILE = Path("credentials.json")          # Baixado do Google Cloud Console
_TOKEN_FILE = Path("memoria/google_token.json") # Gerado automaticamente no --setup
_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _autenticar():
    """Retorna credenciais válidas. Renova token automaticamente se expirado."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None

    if _TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_FILE), _SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not _CREDS_FILE.exists():
                raise FileNotFoundError(
                    "Arquivo credentials.json não encontrado.\n"
                    "Baixe em: console.cloud.google.com → APIs & Services → Credentials\n"
                    "Salve como credentials.json na raiz do projeto."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(_CREDS_FILE), _SCOPES)
            creds = flow.run_local_server(port=0)

        _TOKEN_FILE.parent.mkdir(exist_ok=True)
        _TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return creds


def _service():
    from googleapiclient.discovery import build
    return build("calendar", "v3", credentials=_autenticar(), cache_discovery=False)


def _fmt_horario(evento: dict) -> str:
    """Formata horário do evento (pode ser dia inteiro ou com hora)."""
    inicio = evento.get("start", {})
    if "dateTime" in inicio:
        dt = datetime.fromisoformat(inicio["dateTime"])
        return dt.strftime("%H:%M")
    return "dia inteiro"


def _fmt_evento(e: dict, idx: int = 0) -> str:
    horario = _fmt_horario(e)
    titulo = e.get("summary", "Sem título")
    local = e.get("location", "")
    loc_str = f" 📍 {local}" if local else ""
    return f"*{idx+1}.* 🗓️ {horario} — {titulo}{loc_str}"


# ── API pública ───────────────────────────────────────────────────────────────

def eventos_hoje() -> list[dict]:
    agora = datetime.now(timezone.utc)
    inicio_dia = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    fim_dia = inicio_dia + timedelta(days=1)
    result = _service().events().list(
        calendarId="primary",
        timeMin=inicio_dia.isoformat(),
        timeMax=fim_dia.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    return result.get("items", [])


def eventos_semana() -> list[dict]:
    agora = datetime.now(timezone.utc)
    fim = agora + timedelta(days=7)
    result = _service().events().list(
        calendarId="primary",
        timeMin=agora.isoformat(),
        timeMax=fim.isoformat(),
        singleEvents=True,
        orderBy="startTime",
        maxResults=20,
    ).execute()
    return result.get("items", [])


def proximo_evento() -> dict | None:
    agora = datetime.now(timezone.utc)
    result = _service().events().list(
        calendarId="primary",
        timeMin=agora.isoformat(),
        singleEvents=True,
        orderBy="startTime",
        maxResults=1,
    ).execute()
    items = result.get("items", [])
    return items[0] if items else None


def criar_evento(titulo: str, inicio: str, duracao_min: int = 60,
                 descricao: str = "", local: str = "") -> str:
    """
    inicio: string ISO ou 'HH:MM' (assume hoje).
    """
    try:
        # Resolve horário
        if "T" in inicio or "-" in inicio[:4]:
            dt_inicio = datetime.fromisoformat(inicio)
        else:
            hoje = datetime.now()
            h, m = map(int, inicio.split(":"))
            dt_inicio = hoje.replace(hour=h, minute=m, second=0, microsecond=0)

        dt_fim = dt_inicio + timedelta(minutes=duracao_min)
        tz = "America/Sao_Paulo"

        evento = {
            "summary": titulo,
            "description": descricao,
            "location": local,
            "start": {"dateTime": dt_inicio.isoformat(), "timeZone": tz},
            "end": {"dateTime": dt_fim.isoformat(), "timeZone": tz},
        }

        criado = _service().events().insert(calendarId="primary", body=evento).execute()
        link = criado.get("htmlLink", "")
        return f"✅ Evento criado: *{titulo}* às {dt_inicio.strftime('%H:%M')} de {dt_inicio.strftime('%d/%m/%Y')}"
    except Exception as e:
        return f"❌ Erro ao criar evento: {e}"


# ── Formatação para Telegram ──────────────────────────────────────────────────

def resumo_hoje() -> str:
    try:
        eventos = eventos_hoje()
        data_str = datetime.now().strftime("%d/%m/%Y")
        if not eventos:
            return f"📅 *{data_str}* — Agenda livre! Nenhum compromisso hoje."
        linhas = [f"📅 *Hoje — {data_str}* ({len(eventos)} evento(s))\n"]
        linhas += [_fmt_evento(e, i) for i, e in enumerate(eventos)]
        return "\n".join(linhas)
    except Exception as e:
        return f"❌ Erro ao acessar agenda: {e}"


def resumo_semana() -> str:
    try:
        eventos = eventos_semana()
        if not eventos:
            return "📅 Nenhum evento nos próximos 7 dias."
        # Agrupa por dia
        por_dia: dict[str, list] = {}
        for e in eventos:
            inicio = e.get("start", {})
            dt_str = inicio.get("dateTime", inicio.get("date", ""))
            dia = datetime.fromisoformat(dt_str[:10]).strftime("%d/%m (%a)")
            por_dia.setdefault(dia, []).append(e)

        linhas = ["📅 *Próximos 7 dias:*\n"]
        for dia, evts in por_dia.items():
            linhas.append(f"*{dia}*")
            linhas += [_fmt_evento(e, i) for i, e in enumerate(evts)]
            linhas.append("")
        return "\n".join(linhas)
    except Exception as e:
        return f"❌ Erro ao acessar agenda: {e}"


def resumo_proximo() -> str:
    try:
        e = proximo_evento()
        if not e:
            return "📅 Nenhum evento futuro encontrado."
        horario = _fmt_horario(e)
        titulo = e.get("summary", "Sem título")
        inicio = e.get("start", {}).get("dateTime", "")
        dt = datetime.fromisoformat(inicio) if inicio else None
        data_str = dt.strftime("%d/%m às %H:%M") if dt else horario
        return f"📅 Próximo evento: *{titulo}* — {data_str}"
    except Exception as e:
        return f"❌ Erro: {e}"


def run(args=None) -> str:
    return resumo_hoje()


# ── Setup via terminal ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if "--setup" in sys.argv:
        print("Iniciando autenticação com Google Calendar...")
        try:
            _autenticar()
            print("Token salvo em memoria/google_token.json")
            print("Testando acesso...")
            print(resumo_hoje())
        except Exception as e:
            print(f"Erro: {e}")
    else:
        print(resumo_hoje())

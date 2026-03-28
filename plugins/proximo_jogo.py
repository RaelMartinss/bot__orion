import json
import urllib.parse
import urllib.request
from datetime import datetime


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _normalizar_time(query: str | None) -> str:
    time = (query or "flamengo").strip().lower()
    aliases = {
        "fla": "flamengo",
        "mengao": "flamengo",
        "mengão": "flamengo",
        "flamengo rj": "flamengo",
        "flamengo do brasil": "flamengo",
    }
    return aliases.get(time, time)


def _escolher_time_correto(teams: list[dict], team_name: str) -> dict | None:
    """Escolhe o time correto priorizando Brasil e ligas conhecidas."""
    if not teams:
        return None

    nome = team_name.lower()

    if nome == "flamengo":
        for team in teams:
            country = (team.get("strCountry") or "").lower()
            league = (team.get("strLeague") or "").lower()
            alt_name = (team.get("strAlternate") or "").lower()
            badge_name = (team.get("strTeam") or "").lower()
            if (
                "brazil" in country
                or "brasil" in country
                or "serie a" in league
                or "clube de regatas do flamengo" in alt_name
                or badge_name == "flamengo"
            ):
                return team

    for team in teams:
        badge_name = (team.get("strTeam") or "").lower()
        alt_name = (team.get("strAlternate") or "").lower()
        if badge_name == nome or nome in alt_name:
            return team

    for team in teams:
        country = (team.get("strCountry") or "").lower()
        if "brazil" in country or "brasil" in country:
            return team

    return teams[0]


def run(query="flamengo"):
    try:
        team_name = _normalizar_time(query)

        search_url = "https://www.thesportsdb.com/api/v1/json/3/searchteams.php?t=" + urllib.parse.quote(team_name)
        team_data = _get_json(search_url)
        teams = team_data.get("teams") or []
        if not teams:
            return f"Não encontrei o time '{query}'."

        team = _escolher_time_correto(teams, team_name)
        if not team:
            return f"Não consegui identificar o time correto para '{query}'."
        team_id = team.get("idTeam")
        official_name = team.get("strTeam", team_name.title())
        if not team_id:
            return f"Não consegui localizar o identificador do time '{official_name}'."

        next_url = f"https://www.thesportsdb.com/api/v1/json/3/eventsnext.php?id={team_id}"
        next_data = _get_json(next_url)
        events = next_data.get("events") or []
        if not events:
            return f"Não encontrei jogos futuros para {official_name}."

        event = events[0]
        home = event.get("strHomeTeam", "?")
        away = event.get("strAwayTeam", "?")
        league = event.get("strLeague", "Competição não informada")
        venue = event.get("strVenue", "Estádio não informado")
        date_str = event.get("dateEvent")
        time_str = event.get("strTime", "")

        data_formatada = date_str or "Data não informada"
        if date_str:
            try:
                data_formatada = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
            except ValueError:
                pass

        horario = f"{time_str} UTC" if time_str else "Horário não informado"

        return (
            f"Próximo jogo do {official_name}:\n"
            f"Competição: {league}\n"
            f"Confronto: {home} x {away}\n"
            f"Data: {data_formatada}\n"
            f"Horário: {horario}\n"
            f"Estádio: {venue}\n"
            f"Fonte: TheSportsDB"
        )
    except Exception as e:
        return f"Erro ao buscar o próximo jogo: {e}"

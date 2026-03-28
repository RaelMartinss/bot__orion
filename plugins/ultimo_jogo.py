import json
import urllib.parse
import urllib.request
from datetime import datetime


def _buscar_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def run(query="flamengo"):
    try:
        team_name = (query or "flamengo").strip()
        team_query = urllib.parse.quote(team_name)

        search_url = f"https://www.thesportsdb.com/api/v1/json/3/searchteams.php?t={team_query}"
        team_data = _buscar_json(search_url)
        teams = team_data.get("teams") or []
        if not teams:
            return f"Não encontrei o time '{team_name}'."

        team = teams[0]
        team_id = team.get("idTeam")
        official_name = team.get("strTeam", team_name.title())
        if not team_id:
            return f"Não consegui localizar o identificador do time '{official_name}'."

        last_url = f"https://www.thesportsdb.com/api/v1/json/3/eventslast.php?id={team_id}"
        last_data = _buscar_json(last_url)
        events = last_data.get("results") or []
        if not events:
            return f"Não encontrei o último jogo de {official_name}."

        event = events[0]
        home = event.get("strHomeTeam", "?")
        away = event.get("strAwayTeam", "?")
        home_score = event.get("intHomeScore", "?")
        away_score = event.get("intAwayScore", "?")
        league = event.get("strLeague", "Competição não informada")
        date_str = event.get("dateEvent")

        data_formatada = date_str or "Data não informada"
        if date_str:
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                data_formatada = dt.strftime("%d/%m/%Y")
            except ValueError:
                pass

        return (
            f"Último jogo do {official_name}:\n"
            f"Competição: {league}\n"
            f"Placar: {home} {home_score} x {away_score} {away}\n"
            f"Data: {data_formatada}"
        )
    except Exception as e:
        return f"Erro ao buscar o último jogo: {e}"

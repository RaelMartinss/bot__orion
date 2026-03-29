"""
utils/intent_parser.py
Analisa texto em linguagem natural (PT-BR) e retorna uma intenção estruturada.
"""

import re
import logging
from datetime import datetime

from utils.apps_config import APP_KEYWORDS as _APP_KEYWORDS

logger = logging.getLogger(__name__)

# Variações de nome aceitas (Whisper pode transcrever diferente)
_ORION_PATTERN = r'^(orion|[óo]rion|oryon|orin|oron|ori[aã]o|orião)[,.]?\s*'

# Intenções semânticas sem app explícito na frase
_APP_SEMANTICOS: dict[str, str] = {
    r'\b(programar|codar|codificar|desenvolvimento|desenvolver)\b': 'vscode',
}

_OPEN_VERBS = r'\b(abra|abre|abrir|iniciar|inicia|open)\b'

_MUSIC_VERBS = r'\b(toca|tocar|play|ouvir|coloca|colocar|reproduz|reproduzir|bota|botar|põe|escuta|escutar)\b'
_MUSIC_NOUNS = r'\b(música|musica|song|faixa|banda|artista|álbum|album|spotify)\b'

_SPOTIFY_TRIGGERS = [
    'quero ouvir', 'queria ouvir', 'gostaria de ouvir',
    'quero escutar', 'queria escutar',
    'toca', 'tocar', 'play', 'ouvir', 'coloca', 'colocar',
    'reproduz', 'reproduzir', 'bota', 'botar', 'põe',
    'escuta', 'escutar', 'spotify', 'música', 'musica',
    'song', 'faixa', 'a música', 'a musica', 'no spotify',
    'quero', 'queria', 'me', 'pra mim', 'para mim',
]

_YOUTUBE_TRIGGERS = [
    'youtube', 'no youtube', 'assistir', 'assiste', 'ver',
    'video', 'vídeo', 'clipe', 'busca', 'buscar',
    'toca', 'tocar', 'play', 'ouvir', 'coloca', 'colocar',
    'escuta', 'escutar', 'reproduz', 'reproduzir',
    'quero ouvir', 'queria ouvir', 'quero ver', 'queria ver',
    'quero', 'queria',
]


def extract_orion_command(texto: str) -> tuple[bool, str]:
    """
    Verifica se o texto começa com 'Orion' (a wake word).
    Retorna (True, restante_do_comando) ou (False, texto_original).
    Aceita variações fonéticas geradas pelo Whisper.
    """
    t = texto.strip()
    m = re.match(_ORION_PATTERN, t, re.IGNORECASE)
    if not m:
        return False, t
    comando = t[m.end():].strip()
    return True, comando


def parse_intent(texto: str) -> dict:
    """
    Retorna dict com:
      action: spotify | youtube | netflix | jogo | vol_up | vol_down | mute |
              desligar | reiniciar | cancelar | saudacao | apresentar | desconhecido
      query:  str | None
      delay:  int | None
      saudacao: str | None  (mensagem de resposta para ação=saudacao)
    """
    t = texto.lower().strip()

    # Saudações e apresentações foram removidas do Regex para que o Claude (LLM) lide com elas de forma 100% natural.

    # ── Volume ──────────────────────────────────────────────────────────────
    if _match(t, r'\b(muta|mutar|mute|silencia|silenciar|silêncio|silencio|cala|calar)\b'):
        return {"action": "mute", "query": None, "delay": None}

    # "coloca volume em 75" / "volume para 75" / "define volume 75" → vol_set
    if _match(t, r'\b(volume|som)\b') and \
       _match(t, r'\b(para|em|a|define|definir|coloca|colocar|set|bota|botar)\b') and \
       _num(t) is not None:
        return {"action": "vol_set", "query": str(_num(t)), "delay": None}

    if _match(t, r'(aumenta|aumentar|sobe|subir|mais|up).{0,15}(volume|som|áudio|audio)'
                 r'|(volume|som|áudio|audio).{0,15}(aumenta|aumentar|sobe|subir|mais|up)'):
        pct = _num(t)
        return {"action": "vol_up", "query": str(pct) if pct else None, "delay": None}

    if _match(t, r'(diminui|diminuir|baixa|baixar|menos|down).{0,15}(volume|som|áudio|audio)'
                 r'|(volume|som|áudio|audio).{0,15}(diminui|diminuir|baixa|baixar|menos|down)'):
        pct = _num(t)
        return {"action": "vol_down", "query": str(pct) if pct else None, "delay": None}

    # ── Controle de reprodução ────────────────────────────────────────────────
    # Verificar ANTES dos verbos de música para "pausa" não virar Spotify
    # "play" sozinho (sem nome de música após) = toggle pause
    _play_sozinho = _match(t, r'^play\s*$') or \
                    (_match(t, r'\bplay\b') and not _match(t, r'\bplay\s+\w{3,}'))

    if _match(t, r'\b(pausa|pausar|pause|para a música|para o video|para o vídeo|'
                 r'continua|continuar|retoma|retomar|resume|resumir)\b') \
            or _play_sozinho:
        if not _match(t, r'\b(spotify|youtube|netflix|jogo)\b'):
            return {"action": "pausar", "query": None, "delay": None}

    if _match(t, r'\b(próxima|proxima|próximo|proximo|next|pular|avança|avançar)\b') \
            and not _match(t, r'\b(spotify|youtube|netflix|jogo)\b'):
        return {"action": "proxima", "query": None, "delay": None}

    if _match(t, r'\b(anterior|volta|voltar|prev|previous|retrocede)\b') \
            and not _match(t, r'\b(spotify|youtube|netflix|jogo|desligar|cancelar)\b'):
        return {"action": "anterior", "query": None, "delay": None}

    # ── Alarme ───────────────────────────────────────────────────────────────
    if _match(t, r'\b(alarme|lembra|lembrete|avisa|notifica|acorda)\b'):
        horario = _hora(t)
        if horario:
            # Extrai mensagem: tudo após "de", "para", "pra" ou "que"
            msg_match = re.search(
                r'\b(?:de|para|pra|que|com mensagem|dizendo|avisando(?:\s+que)?)\s+(.+)$', t
            )
            mensagem = msg_match.group(1).strip() if msg_match else "Lembrete!"
            return {"action": "set_alarm", "query": horario, "message": mensagem, "delay": None}

    # ── Time favorito ────────────────────────────────────────────────────────
    if _match(t, r'\b(meu time|time favorito|torço|torcedor|sou do|sou da)\b'):
        m_time = re.search(
            r'\b(flamengo|vasco|palmeiras|corinthians|s[aã]o paulo|botafogo|'
            r'fluminense|gr[eê]mio|internacional|cruzeiro|atl[eé]tico)\b', t
        )
        if m_time:
            return {"action": "set_favorite_team", "query": m_time.group(1), "delay": None}

    # ── Visão ────────────────────────────────────────────────────────────────
    if _match(t, r'\b(ativa|ativar|liga|ligar|habilita|habilitar|start)\b.{0,20}\bvis[aã]o\b'
                 r'|\bvis[aã]o\b.{0,20}\b(ativa|liga|habilita|on)\b'):
        return {"action": "vision_on", "query": None, "delay": None}

    if _match(t, r'\b(desativa|desativar|desliga|desligar|para|parar|para a)\b.{0,20}\bvis[aã]o\b'
                 r'|\bvis[aã]o\b.{0,20}\b(desativa|desliga|para|off)\b'):
        return {"action": "vision_off", "query": None, "delay": None}

    if _match(t, r'\b(analisa|analise|captura|vê a tela|ve a tela|o que.{0,15}tela|'
                 r'descreve a tela|describe the screen)\b'):
        return {"action": "vision_analyze", "query": None, "delay": None}

    # ── Sistema ──────────────────────────────────────────────────────────────
    if _match(t, r'\b(desliga|desligar|shutdown)\b'):
        return {"action": "desligar", "query": None, "delay": _num(t)}

    if _match(t, r'\b(reinicia|reiniciar|reinicie|restart|restarta)\b'):
        return {"action": "reiniciar", "query": None, "delay": _num(t)}

    if _match(t, r'\b(cancela|cancelar|abort)\b'):
        return {"action": "cancelar", "query": None, "delay": None}

    # ── Data e Hora (Offline) ────────────────────────────────────────────────
    if _match(t, r'\b(que dia|qual a data|que horas?|que dia.{0,5}hoje|que dia.{0,5}amanh[ãa]|calend[áa]rio)\b'):
        return {"action": "date_time", "query": t, "delay": None}

    # ── Spotify — verbos de música têm prioridade (toca/play/ouvir) ──────────
    if (_match(t, _MUSIC_VERBS) or _match(t, _MUSIC_NOUNS)) \
            and not _match(t, r'\byoutube\b') and not _match(t, r'\bnetflix\b'):
        query = _query(t, _SPOTIFY_TRIGGERS)
        return {"action": "spotify", "query": query, "delay": None}

    # ── YouTube ───────────────────────────────────────────────────────────────
    if _match(t, r'\byoutube\b') or _match(t, r'\b(assistir|assiste|ver)\b.{0,20}\b(video|vídeo|clipe)\b'):
        query = _query(t, _YOUTUBE_TRIGGERS)
        return {"action": "youtube", "query": query, "delay": None}

    # ── Netflix ───────────────────────────────────────────────────────────────
    if _match(t, r'\b(netflix|filme|série|serie|episódio|episodio)\b'):
        query = _query(t, ['netflix', 'filme', 'série', 'serie', 'episódio', 'episodio',
                           'na netflix', 'assistir', 'assiste'])
        return {"action": "netflix", "query": query, "delay": None}

    # ── Rodar projeto / comandos de dev server ───────────────────────────────
    # "npm run dev" / "rode o projeto" / "inicia o servidor" / "npm start"
    _RUN_CMD_RE = (
        r'\bnpm\s+run\s+\w+'          # npm run dev / npm run start
        r'|\bnpm\s+start\b'           # npm start
        r'|\buv\s+run\b'              # uv run python main.py
        r'|\bpython\s+\w'             # python main.py
        r'|\bcargo\s+run\b'           # cargo run
        r'|\bgo\s+run\b'              # go run .
        r'|\b(rode|rodar|roda)\b.{0,30}\b(projeto|servidor|app|server)\b'
        r'|\b(projeto|servidor|app|server)\b.{0,30}\b(rodar|rode|roda)\b'
    )
    if _match(t, _RUN_CMD_RE):
        # "rode o projeto travel" → extrai "travel"
        m_p = re.search(r'\bprojeto\s+([\w][\w-]+)', t)
        project_name = m_p.group(1) if m_p else None
        return {"action": "run_project", "query": project_name, "delay": None}

    # ── Criar projeto ────────────────────────────────────────────────────────
    # "cria um projeto react chamado travel na área de trabalho"
    if _match(t, r'\b(criar|cria|create|inicializar|scaffold|montar|novo\s+projeto|new\s+project)\b') and \
       _match(t, r'\b(projeto|app|aplicação|aplicacao|site|sistema|api)\b'):

        # Nome: "chamado X" / "vai se chamar X" / "chama X" / "nome X"
        m_name = re.search(
            r'\b(?:chamado|chamar?|se\s+chama?|nome|named?|called?)\s+([\w][\w-]*)', t
        )
        project_name = m_name.group(1) if m_name else None

        # Framework
        _FRAMEWORKS = [
            'react', 'vue', 'angular', 'next', 'nextjs', 'svelte', 'nuxt',
            'express', 'fastapi', 'django', 'flask', 'laravel', 'vite',
        ]
        framework = next((f for f in _FRAMEWORKS if _match(t, rf'\b{f}\b')), None)

        # Localização: "área de trabalho" → desktop, "documentos" → documents
        if _match(t, r'\b(area\s+de\s+trabalho|área\s+de\s+trabalho|desktop)\b'):
            location = 'desktop'
        elif _match(t, r'\b(documentos|documents)\b'):
            location = 'documents'
        else:
            location = 'desktop'  # padrão

        return {
            "action": "create_project",
            "query": project_name,
            "framework": framework,
            "location": location,
            "delay": None,
        }

    # ── Abrir projeto em IDE específica ──────────────────────────────────────
    # "abra o projeto-node no vscode" / "abre meu app no cursor"
    _IDE_RE = r'(vscode|vs\s*code|cursor|pycharm|idea|intellij|webstorm|sublime)'
    m_proj = re.search(
        rf'\b(?:abra|abre|abrir|open)\b\s+(?:o\s+|a\s+|meu\s+|minha\s+)?(.+?)\s+(?:no|na|em)\s+{_IDE_RE}',
        t,
    )
    if m_proj:
        project_name = m_proj.group(1).strip(' ,')
        ide_name = m_proj.group(2).replace(' ', '')
        run = bool(re.search(
            r'\b(rode|rodar|roda|execute|executar|executa|inicia|iniciar|start|run)\b', t
        ))
        return {"action": "open_project", "app": ide_name, "query": project_name, "run": run, "delay": None}

    # ── Abrir aplicativos / projetos ─────────────────────────────────────────
    # Regra: regex só lida com frases SIMPLES ("abre o vscode", "abre o chrome").
    # Frases com 2+ entidades vão para desconhecido.

    # Atalhos semânticos: "quero programar" → vscode
    for padrao, app in _APP_SEMANTICOS.items():
        if _match(t, padrao):
            if _match(t, r'\bprojeto\b'):
                # "quero programar no projeto-node" → open_project
                m_p = re.search(r'\bprojeto[-\w]*', t)
                project_name = m_p.group(0) if m_p else None
                return {"action": "open_project", "app": app, "query": project_name, "delay": None}
            return {"action": "open_app", "query": app, "delay": None}

    if _match(t, _OPEN_VERBS):
        # Frase simples: contém só um app conhecido, sem outras entidades relevantes
        apps_encontrados = [app for app in _APP_KEYWORDS if app in t]
        if len(apps_encontrados) == 1:
            app = apps_encontrados[0]
            # Verifica se a frase é simples: sem palavras-extras após o app
            resto = t.replace(app, '').replace('abre', '').replace('abra', '').replace('abrir', '').replace('o', '').replace('a', '').strip(' ,.')
            if len(resto) <= 8:  # só artigos/preposições soltos → frase simples
                return {"action": "open_app", "query": app, "delay": None}
        # Frase complexa → desconhecido para Claude resolver
        return {"action": "desconhecido", "query": None, "delay": None}

    # ── Jogos ────────────────────────────────────────────────────────────────
    if _match(t, r'\b(abra|abre|abrir|joga|jogar|iniciar|inicia|lança|lançar|lanca|lancar)\b'):
        query = _query(t, ['abre', 'abrir', 'joga', 'jogar', 'iniciar', 'inicia',
                           'lança', 'lançar', 'lanca', 'lancar', 'o jogo', 'jogo'])
        if query:
            # Se a query contém um app/IDE conhecido (ex: "projeto-node no vscode"), deixa Claude resolver
            if any(app in query for app in _APP_KEYWORDS):
                return {"action": "desconhecido", "query": None, "delay": None}
            return {"action": "jogo", "query": query, "delay": None}

    return {"action": "desconhecido", "query": None, "delay": None}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _match(texto: str, padrao: str) -> bool:
    return bool(re.search(padrao, texto))


def _num(texto: str) -> int | None:
    m = re.search(r'\b(\d+)\b', texto)
    return int(m.group(1)) if m else None


def _query(texto: str, triggers: list[str]) -> str | None:
    """Remove as palavras de trigger e retorna o restante como query."""
    t = texto.lower()
    for palavra in sorted(triggers, key=len, reverse=True):
        t = re.sub(rf'\b{re.escape(palavra)}\b', '', t)
    # Remove artigos/preposições soltos no início
    t = re.sub(r'^[\s,.:;!?]*(a\s|o\s|as\s|os\s|um\s|uma\s|de\s|do\s|da\s|'
               r'dos\s|das\s|no\s|na\s|nos\s|nas\s|para\s|pra\s|em\s|e\s)', '', t)
    t = t.strip(' ,.:;!?-')
    return t if len(t) >= 2 else None


def _hora(texto: str) -> str | None:
    """Extrai horário no formato HH:MM de texto PT-BR. Ex: '16h55', '16:55', '4 e meia' → '16:30'."""
    # 16h55 / 16h / 16:55 / 16.55
    m = re.search(r'\b(\d{1,2})[h:.](\d{2})\b', texto)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return f"{h:02d}:{mi:02d}"

    # "16h" sem minutos
    m = re.search(r'\b(\d{1,2})h\b', texto)
    if m:
        h = int(m.group(1))
        if 0 <= h <= 23:
            return f"{h:02d}:00"

    # "4 e meia" → 4:30 / "4 da tarde" → 16:00
    m = re.search(r'\b(\d{1,2})\s+e\s+meia\b', texto)
    if m:
        h = int(m.group(1))
        if _match(texto, r'\b(tarde|noite)\b') and h < 12:
            h += 12
        return f"{h:02d}:30"

    return None

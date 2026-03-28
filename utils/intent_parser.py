"""
utils/intent_parser.py
Analisa texto em linguagem natural (PT-BR) e retorna uma intenção estruturada.
"""

import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Variações de nome aceitas (Whisper pode transcrever diferente)
_ORION_PATTERN = r'^(orion|[óo]rion|oryon|orin|oron|ori[aã]o|orião)[,.]?\s*'


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

    # ── Sistema ──────────────────────────────────────────────────────────────
    if _match(t, r'\b(desliga|desligar|shutdown)\b'):
        return {"action": "desligar", "query": None, "delay": _num(t)}

    if _match(t, r'\b(reinicia|reiniciar|reinicie|restart|restarta)\b'):
        return {"action": "reiniciar", "query": None, "delay": _num(t)}

    if _match(t, r'\b(cancela|cancelar|abort)\b'):
        return {"action": "cancelar", "query": None, "delay": None}

    # ── Spotify — verbos de música têm prioridade (toca/play/ouvir) ──────────
    # Só cai aqui se NÃO tiver "youtube" ou "netflix" explícito no texto
    _MUSIC_VERBS = r'\b(toca|tocar|play|ouvir|coloca|colocar|reproduz|reproduzir|bota|botar|põe|escuta|escutar)\b'
    _MUSIC_NOUNS = r'\b(música|musica|song|faixa|banda|artista|álbum|album|spotify)\b'
    if (_match(t, _MUSIC_VERBS) or _match(t, _MUSIC_NOUNS)) \
            and not _match(t, r'\byoutube\b') and not _match(t, r'\bnetflix\b'):
        _SPOTIFY_TRIGGERS = ['toca', 'tocar', 'play', 'ouvir', 'coloca', 'colocar',
                             'reproduz', 'reproduzir', 'bota', 'botar', 'põe',
                             'escuta', 'escutar', 'spotify', 'música', 'musica',
                             'song', 'faixa', 'a música', 'a musica', 'no spotify',
                             'me', 'pra mim', 'para mim']
        query = _query(t, _SPOTIFY_TRIGGERS)
        return {"action": "spotify", "query": query, "delay": None}

    # ── YouTube ───────────────────────────────────────────────────────────────
    if _match(t, r'\byoutube\b') or _match(t, r'\b(assistir|assiste|ver)\b.{0,20}\b(video|vídeo|clipe)\b'):
        query = _query(t, ['youtube', 'no youtube', 'assistir', 'assiste', 'ver',
                           'video', 'vídeo', 'clipe', 'busca', 'buscar',
                           'toca', 'tocar', 'play', 'ouvir', 'coloca', 'colocar',
                           'escuta', 'escutar', 'reproduz', 'reproduzir'])
        return {"action": "youtube", "query": query, "delay": None}

    # ── Netflix ───────────────────────────────────────────────────────────────
    if _match(t, r'\b(netflix|filme|série|serie|episódio|episodio)\b'):
        query = _query(t, ['netflix', 'filme', 'série', 'serie', 'episódio', 'episodio',
                           'na netflix', 'assistir', 'assiste'])
        return {"action": "netflix", "query": query, "delay": None}

    # ── Jogos ────────────────────────────────────────────────────────────────
    if _match(t, r'\b(abre|abrir|joga|jogar|iniciar|inicia|lança|lançar|lanca|lancar)\b'):
        query = _query(t, ['abre', 'abrir', 'joga', 'jogar', 'iniciar', 'inicia',
                           'lança', 'lançar', 'lanca', 'lancar', 'o jogo', 'jogo'])
        if query:
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

"""
utils/context_resolver.py
Resolve respostas curtas contextuais antes do parser principal:
- Redirects de plataforma: "no youtube", "no spotify"
- Referências pronominais: "rode ele", "executa isso", "abre de novo"
"""

import re
from utils.memoria import carregar_pending, limpar_pending, carregar_ultimo_objeto

_PLATAFORMA_PATTERNS: dict[str, str] = {
    # Aceita typos comuns: youtbe, youtu, ytube, yt
    "youtube": r'\b(youtube|youtbe|youtu[a-z]{0,3}|ytube|yt)\b',
    "spotify": r'\b(spotify|spotif[a-z]{0,2})\b',
    "netflix": r'\b(netflix|netfix|netfl[a-z]{0,3})\b',
}

# Pronomes e expressões referenciais em PT-BR
_PRONOMES = r'\b(ele|ela|isso|aquilo|o projeto|esse projeto|aquele projeto|o mesmo|de novo|novamente)\b'

# Verbos que indicam intenção de rodar/executar
_VERBOS_RODAR = r'\b(rode|rodar|roda|executa|executar|execute|inicia|iniciar|start|run|npm|yarn|python|uv)\b'


def resolver_contexto(user_id: int, texto: str) -> dict | None:
    """
    Resolve o texto em um intent concreto quando há contexto salvo.
    Retorna None se não houver match contextual.
    """
    t = texto.lower().strip()

    # ── 1. Redirect de plataforma ("no youtube", "no spotify") ────────────────
    pending = carregar_pending(user_id)
    if pending:
        for plataforma, pattern in _PLATAFORMA_PATTERNS.items():
            if re.search(pattern, t):
                limpar_pending(user_id)
                return {
                    "action": plataforma,
                    "query": pending["query"],
                    "delay": None,
                }

    # ── 2. Referência pronominal ("rode ele", "executa isso") ─────────────────
    ultimo = carregar_ultimo_objeto(user_id)
    if not ultimo:
        return None

    tem_pronome = bool(re.search(_PRONOMES, t))
    tem_verbo_rodar = bool(re.search(_VERBOS_RODAR, t))

    # "rode ele" / "executa isso" / "roda o projeto" → run_project
    if tem_verbo_rodar and (tem_pronome or len(t.split()) <= 3):
        return {
            "action": "run_project",
            "target": ultimo["target"],
            "app": ultimo.get("app"),
            "query": ultimo["target"],
            "delay": None,
        }

    # "abre ele de novo" / "abre de novo" → reabre o último projeto/app
    if re.search(r'\b(abre|abra|abrir|open)\b', t) and tem_pronome:
        return {
            "action": ultimo["action"],
            "target": ultimo.get("target"),
            "app": ultimo.get("app"),
            "query": ultimo.get("target"),
            "delay": None,
        }

    return None

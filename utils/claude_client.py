"""
utils/claude_client.py

Wrapper assíncrono para a API da Anthropic.
Isola toda a lógica de chamada HTTP em um único lugar.
"""

import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2048


def _get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise APIError(
            "ANTHROPIC_API_KEY não configurada.\n"
            "Crie o arquivo .env na raiz do projeto com:\n"
            "ANTHROPIC_API_KEY=sk-ant-..."
        )
    return key


class APIError(Exception):
    pass


async def _call_claude_api(
    system: str,
    user_msg: str,
    max_tokens: int = MAX_TOKENS,
    temperature: float | None = None,
    timeout: float = 60.0,
) -> str:
    """Chamada raw à API Anthropic. Retorna o texto da resposta."""
    headers = {
        "x-api-key": _get_api_key(),
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload: dict = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user_msg}],
    }
    if temperature is not None:
        payload["temperature"] = temperature

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(ANTHROPIC_API_URL, headers=headers, json=payload)
        if response.status_code != 200:
            raise APIError(f"API retornou status {response.status_code}: {response.text[:300]}")
        blocks = [b["text"] for b in response.json().get("content", []) if b.get("type") == "text"]
        if not blocks:
            raise APIError("API retornou resposta sem bloco de texto.")
        return "\n".join(blocks)
    except httpx.TimeoutException:
        raise APIError(f"Timeout na chamada à API (>{timeout}s). Tente novamente.")
    except httpx.RequestError as e:
        raise APIError(f"Erro de rede ao chamar a API: {e}")


async def generate_handler(system_prompt: str, user_prompt: str) -> str:
    """Chama a API da Anthropic e retorna o texto da resposta."""
    logger.info(f"Chamando API Anthropic (model={MODEL})...")
    result = await _call_claude_api(system_prompt, user_prompt)
    logger.info("Resposta da API recebida com sucesso.")
    return result

# ── Parser de intenção estruturada ───────────────────────────────────────────

_SYSTEM_INTENT = """Você é um parser de comandos. Converta o texto do usuário em JSON estruturado.
Responda APENAS com JSON válido — sem markdown, sem texto extra.

Ações possíveis e seus campos:

open_project  → {"action": "open_project", "target": "<nome_projeto>", "app": "<ide>"}
open_app      → {"action": "open_app", "app": "<nome_app>"}
youtube       → {"action": "youtube", "query": "<busca>"}
spotify       → {"action": "spotify", "query": "<busca>"}
netflix       → {"action": "netflix", "query": "<busca>"}
jogo          → {"action": "jogo", "query": "<nome_jogo>"}
vol_up        → {"action": "vol_up"}
vol_down      → {"action": "vol_down"}
mute          → {"action": "mute"}
desligar      → {"action": "desligar"}
reiniciar     → {"action": "reiniciar"}
pausar        → {"action": "pausar"}
conversa      → {"action": "conversa"}
desconhecido  → {"action": "desconhecido"}

Exemplos:
"abra o projeto api-node no vscode"                        → {"action": "open_project", "target": "api-node", "app": "vscode"}
"abra o projeto-node no vscode"                            → {"action": "open_project", "target": "projeto-node", "app": "vscode"}
"abra o projeto-node que está na area de trabalho no vscode" → {"action": "open_project", "target": "projeto-node", "app": "vscode"}
"inicie o projeto-node no pycharm"                         → {"action": "open_project", "target": "projeto-node", "app": "pycharm"}
"abre o projeto-node no vscode e rode ele"                 → {"action": "open_project", "target": "projeto-node", "app": "vscode"}
"vamos programar no projeto-node"                          → {"action": "open_project", "target": "projeto-node", "app": "vscode"}
"abre o vscode"                                            → {"action": "open_app", "app": "vscode"}
"quero abrir o chrome"                                     → {"action": "open_app", "app": "chrome"}
"toca zeze di camargo no youtube"                          → {"action": "youtube", "query": "zeze di camargo"}
"quero ouvir funk"                                         → {"action": "spotify", "query": "funk"}
"desliga o pc em 5 minutos"                               → {"action": "desligar", "delay": 300}
"tudo bem?"                                                → {"action": "conversa"}

IMPORTANTE: O campo "target" é SEMPRE o nome da pasta/projeto (ex: "projeto-node", "api-financeira").
Ignore palavras como "que", "está", "na", "área de trabalho", "e rode", "e execute" — extraia só o nome do projeto.
Use "conversa" apenas se não for um comando de PC."""


async def extrair_intent_estruturado(texto: str) -> dict | None:
    """
    Usa Claude para extrair intent estruturado de comandos complexos.
    Retorna dict com 'action' e campos extras, ou None em caso de erro.
    Mais rápido que o orchestrator completo — só retorna JSON, não executa.
    """
    import json

    headers = {
        "x-api-key": _get_api_key(),
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": MODEL,
        "max_tokens": 150,
        "system": _SYSTEM_INTENT,
        "messages": [{"role": "user", "content": texto}],
        "temperature": 0,
    }
    try:
        raw = await _call_claude_api(_SYSTEM_INTENT, texto, max_tokens=150, temperature=0.0, timeout=15.0)
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end != -1:
            return json.loads(raw[start:end + 1])
    except Exception as e:
        logger.warning(f"extrair_intent_estruturado erro: {e}")
    return None


# ── Conversacional (Fallback) ─────────────────────────────────────────────────

SYSTEM_PROMPT_CHAT = """Você é o Orion, um assistente virtual de computador pessoal via Telegram.
Sua personalidade é prestativa, mas natural, não robótica.
O usuário está falando com você em linguagem natural (texto ou voz).

REGRAS:
1. Responda de forma HÚMANA e amigável. Mantenha respostas razoavelmente curtas.
2. Se o usuário pedir para você executar uma tarefa no computador (ex: abrir um app, tocar música, ligar a câmera, etc) e você NÃO SABE fazer (pois este é o fallback de intenção desconhecida), diga natural e gentilmente que ainda não sabe realizar esse comando, mas que PODE aprender se o usuário quiser ensinar.
3. Se o usuário estiver apenas conversando casualmente (ex: "tudo bem?", "boa noite", "me conta uma piada"), responda normalmente ao bate-papo.
4. Você NÃO PODE inventar que abriu o aplicativo. Se caiu para você responder, é porque o sistema nativo falhou em reconhecer o comando.

VOCÊ DEVE RETORNAR EXCLUSIVAMENTE UM JSON VÁLIDO no formato (sem blocos de código markdown nem nada antes ou depois):
{
  "resposta": "Sua resposta humanizada aqui. Use emojis.",
  "is_comando_desconhecido": true ou false
}

Defina 'is_comando_desconhecido' como true APENAS se o usuário te pediu para executar um comando de automação/PC que você não sabe. Assim o sistema exibirá botões para ele criar o comando.
Caso seja só uma conversa, pergunta comum, ou dúvida, defina como false.
"""

async def chat_with_orion(user_message: str) -> dict:
    """Retorna {"resposta": str, "is_comando_desconhecido": bool}."""
    import json
    logger.info(f"Fallback conversacional: {user_message}")
    try:
        raw = await _call_claude_api(SYSTEM_PROMPT_CHAT, user_message, max_tokens=512, temperature=0.7)
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end != -1:
            return json.loads(raw[start:end + 1])
    except Exception as e:
        logger.error(f"Erro ao chamar Claude: {e}", exc_info=True)
    return {"resposta": "⚠️ Desculpe, tive um erro no processamento.", "is_comando_desconhecido": False}


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
    print('ANTHROPIC_API_KEY', key)
    if not key:
        raise APIError(
            "ANTHROPIC_API_KEY não configurada.\n"
            "Crie o arquivo .env na raiz do projeto com:\n"
            "ANTHROPIC_API_KEY=sk-ant-..."
        )
    return key


class APIError(Exception):
    pass


async def generate_handler(system_prompt: str, user_prompt: str) -> str:
    """
    Chama a API da Anthropic e retorna o texto da resposta.

    Raises:
        APIError: Se a chave não estiver configurada, a chamada falhar ou retornar erro.
    """
    headers = {
        "x-api-key": _get_api_key(),
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    payload = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }

    logger.info(f"Chamando API Anthropic (model={MODEL})...")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(ANTHROPIC_API_URL, headers=headers, json=payload)

        if response.status_code != 200:
            raise APIError(
                f"API retornou status {response.status_code}: {response.text[:300]}"
            )

        data = response.json()
        text_blocks = [
            b["text"] for b in data.get("content", []) if b.get("type") == "text"
        ]

        if not text_blocks:
            raise APIError("API retornou resposta sem bloco de texto.")

        logger.info("Resposta da API recebida com sucesso.")
        return "\n".join(text_blocks)

    except httpx.TimeoutException:
        raise APIError("Timeout na chamada à API (>60s). Tente novamente.")
    except httpx.RequestError as e:
        raise APIError(f"Erro de rede ao chamar a API: {e}")

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
    """
    Envia a mensagem para a IA da Anthropic e retorna um dicionário:
    { "resposta": str, "is_comando_desconhecido": bool }
    """
    import json
    
    headers = {
        "x-api-key": _get_api_key(),
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    payload = {
        "model": MODEL,
        "max_tokens": 512,
        "system": SYSTEM_PROMPT_CHAT,
        "messages": [
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.7
    }

    logger.info(f"Enviando para Claude para fallback conversacional: {user_message}")
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(ANTHROPIC_API_URL, headers=headers, json=payload)

        if response.status_code != 200:
            logger.error(f"Erro Claude: {response.text}")
            return {
                "resposta": "⚠️ Desculpe, tive um problema de conexão com a Anthropic.",
                "is_comando_desconhecido": False
            }

        data = response.json()
        content = data.get("content", [])[0].get("text", "")
        
        # Limpar o texto caso o Claude retorne com marcadores ```json ... ``` ou texto extra
        import re
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
            
        json_str = content.strip()
        # Encontrar o primeiro '{' e o último '}' em caso de texto vazando
        start_idx = json_str.find('{')
        end_idx = json_str.rfind('}')
        if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
            json_str = json_str[start_idx:end_idx+1]
        
        logger.info(f"Claude respondeu: {json_str}")
        
        return json.loads(json_str)
        
    except Exception as e:
        logger.error(f"Erro ao chamar Claude: {e}", exc_info=True)
        return {
            "resposta": f"⚠️ Desculpe, tive um erro no processamento: {e}",
            "is_comando_desconhecido": False
        }


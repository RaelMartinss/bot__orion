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

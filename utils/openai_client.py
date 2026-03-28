"""
utils/openai_client.py

Cliente para a API da OpenAI (ChatGPT) usado como backend conversacional interativo do Orion.
Retorna a resposta falada do bot e uma flag indicando se a intenção parecia ser de um comando 
desconhecido, para exibir botões de "Criar Comando".
"""

import os
import json
import logging
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Configuração do System Prompt do Orion
SYSTEM_PROMPT = """Você é o Orion, um assistente virtual de computador pessoal via Telegram.
Sua personalidade é prestativa, mas natural, não robótica.
O usuário está falando com você em linguagem natural (texto ou voz).

REGRAS:
1. Responda de forma HÚMANA e amigável. Mantenha respostas razoavelmente curtas.
2. Se o usuário pedir para você executar uma tarefa no computador (ex: abrir um app, tocar música, ligar a câmera, etc) e você NÃO SABE fazer (pois este é o fallback de intenção desconhecida), diga natural e gentilmente que ainda não sabe realizar esse comando, mas que PODE aprender se o usuário quiser ensinar.
3. Se o usuário estiver apenas conversando casualmente (ex: "tudo bem?", "boa noite", "me conta uma piada"), responda normalmente ao bate-papo.
4. Você NÃO PODE inventar que abriu o aplicativo. Se caiu para você responder, é porque o sistema nativo falhou em reconhecer o comando.

VOCÊ DEVE RETORNAR EXCLUSIVAMENTE UM JSON VÁLIDO no formato:
{
  "resposta": "Sua resposta humanizada aqui. Use emojis.",
  "is_comando_desconhecido": true ou false
}

Defina 'is_comando_desconhecido' como true APENAS se o usuário te pediu para executar um comando de automação/PC que você não sabe. Assim o sistema exibirá botões para ele criar o comando.
Caso seja só uma conversa, pergunta comum, ou dúvida, defina como false.
"""

_client = None

def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OPENAI_API_KEY não configurada no .env")
        _client = AsyncOpenAI(api_key=api_key)
    return _client

async def chat_with_orion(user_message: str) -> dict:
    """
    Envia a mensagem para o ChatGPT e retorna um dicionário:
    { "resposta": str, "is_comando_desconhecido": bool }
    """
    try:
        client = get_client()
    except ValueError as e:
        logger.warning(f"ChatGPT fallback: {e}")
        return {
            "resposta": "⚠️ Minha chave da OpenAI (`OPENAI_API_KEY`) não está no arquivo `.env`. Por favor, adicione-a para que possamos bater um papo!",
            "is_comando_desconhecido": True
        }
    
    logger.info(f"Enviando para OpenAI para fallback conversacional: {user_message}")
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=300
        )
        content = response.choices[0].message.content
        logger.info(f"OpenAI respondeu: {content}")
        return json.loads(content)
    except Exception as e:
        logger.error(f"Erro ao chamar OpenAI: {e}")
        return {
            "resposta": f"⚠️ Desculpe, tive um erro de conexão com meu cérebro (ChatGPT): {e}",
            "is_comando_desconhecido": False
        }

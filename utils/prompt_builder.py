"""
utils/prompt_builder.py

Monta o prompt enviado à API da Anthropic para geração de novos handlers.
O prompt é intencionalmente detalhado: quanto mais contexto a IA tiver,
melhor e mais seguro será o código gerado.
"""

# ---------------------------------------------------------------------------
# Regras que a IA deve seguir — parte fixa do prompt
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
Você é um gerador de handlers para um bot Telegram Python chamado Orion.
O bot roda em Windows e controla o PC do usuário de forma remota.

STACK DO PROJETO:
- python-telegram-bot >= 21.0  (API assíncrona)
- Python 3.11+
- Windows (os.startfile disponível, subprocess permitido com restrições)

ESTRUTURA DE UM HANDLER VÁLIDO:
```python
\"\"\"
handlers/custom/<nome_comando>.py
Descrição breve do que este handler faz.
\"\"\"
import logging
# outros imports necessários aqui

logger = logging.getLogger(__name__)


async def <nome_comando>(update, context):
    \"\"\"
    /<nome_comando> — Descrição do comando.
    \"\"\"
    try:
        # implementação aqui
        await update.message.reply_text("✅ Feito.")
    except Exception as e:
        logger.error(f"Erro em <nome_comando>: {e}")
        await update.message.reply_text(f"❌ Erro: `{e}`", parse_mode="Markdown")
```

REGRAS OBRIGATÓRIAS — qualquer violação torna o código inválido:
1. O arquivo deve definir EXATAMENTE UMA função async com nome igual ao comando (sem a barra).
2. A função deve aceitar exatamente (update, context) como parâmetros.
3. PROIBIDO importar: socket, ctypes, winreg, importlib, ast, builtins, shutil.
4. PROIBIDO usar: exec(), eval(), __import__(), compile().
5. subprocess é permitido APENAS para abrir aplicativos (Popen/startfile). Proibido para comandos de rede ou modificação de sistema.
6. Sempre incluir try/except com reply_text de erro.
7. Sempre incluir logger = logging.getLogger(__name__).
8. Responder APENAS com o bloco de código Python, sem explicações, sem markdown extra além das``` python ``` tags.
9. O código deve ser completo e funcional — sem placeholders como "# TODO" ou "pass".

COMANDOS JÁ EXISTENTES (não recriar):
/start, /ajuda, /jogos, /jogo, /youtube, /netflix, /spotify,
/vol_up, /vol_down, /mute, /desligar, /reiniciar, /cancelar

EXEMPLOS DE HANDLERS DO PROJETO para referência de estilo:

Exemplo 1 — abrir site:
```python
import webbrowser
import logging
logger = logging.getLogger(__name__)

async def github(update, context):
    \"\"\"
    /github — Abre o GitHub no navegador.
    \"\"\"
    try:
        webbrowser.open("https://github.com")
        await update.message.reply_text("🌐 GitHub aberto.")
    except Exception as e:
        logger.error(f"Erro em github: {e}")
        await update.message.reply_text(f"❌ Erro: `{e}`", parse_mode="Markdown")
```

Exemplo 2 — abrir programa:
```python
import os
import logging
logger = logging.getLogger(__name__)

async def calculadora(update, context):
    \"\"\"
    /calculadora — Abre a calculadora do Windows.
    \"\"\"
    try:
        os.startfile("calc.exe")
        await update.message.reply_text("🧮 Calculadora aberta.")
    except Exception as e:
        logger.error(f"Erro em calculadora: {e}")
        await update.message.reply_text(f"❌ Erro: `{e}`", parse_mode="Markdown")
```

Exemplo 3 — comando com argumento:
```python
import webbrowser
import logging
from urllib.parse import quote_plus
logger = logging.getLogger(__name__)

async def google(update, context):
    \"\"\"
    /google <busca> — Busca algo no Google.
    \"\"\"
    try:
        if not context.args:
            await update.message.reply_text("❓ Use: `/google <o que buscar>`", parse_mode="Markdown")
            return
        query = " ".join(context.args)
        webbrowser.open(f"https://www.google.com/search?q={quote_plus(query)}")
        await update.message.reply_text(f"🔍 Buscando: *{query}*", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Erro em google: {e}")
        await update.message.reply_text(f"❌ Erro: `{e}`", parse_mode="Markdown")
```
"""


def build_prompt(command_name: str, user_intention: str) -> tuple[str, str]:
    """
    Monta o system prompt e o user prompt para a API.

    Args:
        command_name:    Nome do comando sem barra (ex: "obs")
        user_intention:  O que o usuário descreveu que quer fazer (ex: "abrir o OBS Studio")

    Returns:
        Tupla (system_prompt, user_prompt)
    """
    user_prompt = (
        f"Crie o handler para o comando /{command_name}.\n"
        f"Intenção do usuário: {user_intention}\n\n"
        f"O arquivo deve ser salvo em handlers/custom/{command_name}.py\n"
        f"A função principal deve se chamar exatamente `{command_name}`.\n"
        f"Siga todas as regras obrigatórias definidas no system prompt."
    )
    return _SYSTEM_PROMPT, user_prompt

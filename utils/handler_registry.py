"""
utils/handler_registry.py

Responsável por:
1. Salvar o arquivo handlers/custom/<cmd>.py gerado
2. Registrar o handler no app em runtime (sem restart)
3. Atualizar o menu de comandos do Telegram (set_my_commands)
4. Carregar todos os comandos custom no boot do bot
"""

import importlib
import importlib.util
import logging
import sys
from pathlib import Path

from telegram import BotCommand
from telegram.ext import Application, CommandHandler

logger = logging.getLogger(__name__)

CUSTOM_DIR = Path(__file__).parent.parent / "handlers" / "custom"


def save_handler_file(command_name: str, code: str) -> Path:
    """
    Salva o código gerado em handlers/custom/<command_name>.py.
    Sobrescreve se já existir (atualização de comando).
    """
    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    file_path = CUSTOM_DIR / f"{command_name}.py"
    file_path.write_text(code, encoding="utf-8")
    logger.info(f"Handler salvo: {file_path}")
    return file_path


def load_and_register(app: Application, command_name: str) -> bool:
    """
    Importa o módulo do handler salvo e registra no app em runtime.

    Retorna True se bem-sucedido, False caso contrário.
    """
    file_path = CUSTOM_DIR / f"{command_name}.py"

    if not file_path.exists():
        logger.error(f"Arquivo não encontrado: {file_path}")
        return False

    module_name = f"handlers.custom.{command_name}"

    # Remove do cache do Python se já existia (permite reload)
    if module_name in sys.modules:
        del sys.modules[module_name]

    try:
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    except Exception as e:
        logger.error(f"Erro ao importar {module_name}: {e}")
        return False

    # Pega a função handler pelo nome do comando
    handler_func = getattr(module, command_name, None)
    if handler_func is None:
        logger.error(f"Função '{command_name}' não encontrada no módulo.")
        return False

    # Remove handler antigo se existir (evita duplicatas)
    for h in list(app.handlers.get(0, [])):
        if isinstance(h, CommandHandler) and command_name in (h.commands or set()):
            app.remove_handler(h, group=0)

    app.add_handler(CommandHandler(command_name, handler_func))
    logger.info(f"Handler /{command_name} registrado no app.")
    return True


async def update_telegram_menu(app: Application):
    """
    Atualiza o menu de comandos do Telegram com todos os comandos
    ativos (fixos + custom).
    """
    # Comandos fixos do bot
    fixed_commands = [
        BotCommand("start",     "Mostra o menu de ajuda"),
        BotCommand("ajuda",     "Mostra o menu de ajuda"),
        BotCommand("jogos",     "Lista jogos Steam instalados"),
        BotCommand("jogo",      "Abre um jogo pelo nome"),
        BotCommand("youtube",   "Abre o YouTube"),
        BotCommand("netflix",   "Abre a Netflix"),
        BotCommand("spotify",   "Abre o Spotify"),
        BotCommand("vol_up",    "Aumenta o volume"),
        BotCommand("vol_down",  "Diminui o volume"),
        BotCommand("mute",      "Muta/desmuta"),
        BotCommand("desligar",  "Desliga o PC"),
        BotCommand("reiniciar", "Reinicia o PC"),
        BotCommand("cancelar",  "Cancela desligamento"),
    ]

    # Descobre comandos custom existentes
    custom_commands = []
    if CUSTOM_DIR.exists():
        for py_file in sorted(CUSTOM_DIR.glob("*.py")):
            if py_file.name == "__init__.py":
                continue
            cmd_name = py_file.stem
            # Tenta extrair descrição do docstring da função
            description = _extract_description(py_file, cmd_name)
            custom_commands.append(BotCommand(cmd_name, description))

    all_commands = fixed_commands + custom_commands

    try:
        await app.bot.set_my_commands(all_commands)
        logger.info(f"Menu Telegram atualizado ({len(all_commands)} comandos).")
    except Exception as e:
        logger.warning(f"Erro ao atualizar menu do Telegram: {e}")


def _extract_description(file_path: Path, command_name: str) -> str:
    """
    Tenta extrair a linha de descrição do docstring do handler.
    Fallback para "Comando personalizado".
    """
    try:
        source = file_path.read_text(encoding="utf-8")
        # Procura padrão: /<cmd> — descrição
        import re
        match = re.search(rf"/{command_name}\s*[—\-]+\s*(.+)", source)
        if match:
            return match.group(1).strip()[:50]
    except Exception:
        pass
    return "Comando personalizado"


def load_all_custom_handlers(app: Application):
    """
    Carrega todos os handlers custom no boot do bot.
    Chamado uma vez no main() antes de run_polling().
    """
    if not CUSTOM_DIR.exists():
        return

    loaded = 0
    for py_file in sorted(CUSTOM_DIR.glob("*.py")):
        if py_file.name == "__init__.py":
            continue
        cmd_name = py_file.stem
        if load_and_register(app, cmd_name):
            loaded += 1

    if loaded:
        logger.info(f"{loaded} handler(s) custom carregado(s) do disco.")

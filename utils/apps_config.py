"""
utils/apps_config.py
Fonte única de verdade para mapeamento de apps e IDEs conhecidos.
Importado por executor.py (para abrir) e intent_parser.py (para detectar).
"""

# alias → comando executável no Windows
KNOWN_APPS: dict[str, str] = {
    "vscode": "code",
    "vs code": "code",
    "visual studio code": "code",
    "visual studio": "devenv",
    "notepad": "notepad",
    "notepad++": "notepad++",
    "bloco de notas": "notepad",
    "calculator": "calc",
    "calculadora": "calc",
    "chrome": "chrome",
    "google chrome": "chrome",
    "firefox": "firefox",
    "edge": "msedge",
    "explorer": "explorer",
    "gerenciador de arquivos": "explorer",
    "task manager": "taskmgr",
    "gerenciador de tarefas": "taskmgr",
    "paint": "mspaint",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "discord": "discord",
    "telegram": "telegram",
    "whatsapp": "whatsapp",
    "obs": "obs64",
    "obs studio": "obs64",
    "vlc": "vlc",
    "winrar": "winrar",
    "7zip": "7zfm",
}

# IDEs com comandos específicos + herda apps de KNOWN_APPS como fallback
IDE_COMMANDS: dict[str, str] = {
    **{k: v for k, v in KNOWN_APPS.items() if v in ("code", "notepad++", "devenv")},
    "pycharm": "pycharm64",
    "intellij": "idea64",
    "sublime": "subl",
    "sublime text": "subl",
    "atom": "atom",
    "vim": "vim",
    "cursor": "cursor",
    "webstorm": "webstorm64",
}

# Lista de nomes para detecção rápida em frases (intent_parser)
APP_KEYWORDS: list[str] = sorted(KNOWN_APPS.keys(), key=len, reverse=True)

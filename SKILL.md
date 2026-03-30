---
name: auto-discovery
description: >
  Gera automaticamente o mapeamento de projetos, pastas e programas instalados
  em um PC Windows, produzindo um JSON pronto para uso no Orion Bot (ou qualquer
  bot/script que precise conhecer o ambiente local). Use esta skill sempre que o
  usuário mencionar "descobrir projetos", "mapear pastas", "auto-discovery",
  "encontrar projetos automaticamente", "gerar PROJETOS dict", "mapear meu PC",
  ou qualquer variação de querer que o bot saiba onde ficam seus arquivos,
  projetos e programas sem precisar cadastrar tudo na mão.
---

# Auto-Discovery — Mapeamento automático de ambiente Windows

## O que esta skill faz

Gera um script Python (`discover.py`) que varre o PC Windows do usuário e
produz um arquivo `environment_map.json` contendo:

1. **Projetos de desenvolvimento** — detectados por marcadores como `.git/`,
   `pyproject.toml`, `package.json`, `Cargo.toml`, `*.sln`, `manage.py`, etc.
2. **Pastas importantes** — Downloads, Documentos, Desktop, OneDrive, e
   quaisquer pastas fixadas no Quick Access do Explorer.
3. **Programas instalados** — lidos do registro do Windows (Uninstall keys) e
   de atalhos do Menu Iniciar.
4. **Projetos VS Code recentes** — extraídos do `storage.json` do VS Code.
5. **Repos Git recentes** — extraídos do Git credential manager / recent repos.

O JSON resultante pode ser importado diretamente pelo Orion Bot para popular o
dict `PROJETOS` e alimentar os plugins `open.py`, `search.py`, etc.

---

## Estrutura do JSON de saída

```json
{
  "generated_at": "2025-06-15T14:30:00",
  "machine_name": "DESKTOP-RAEL",
  "projects": [
    {
      "name": "Portal Frotas",
      "path": "C:\\Users\\rael\\projects\\portal-frotas",
      "type": "django",
      "markers": ["manage.py", ".git", "pyproject.toml"],
      "last_modified": "2025-06-15T12:00:00",
      "aliases": ["portal", "frotas", "portal frotas", "portal-frotas"]
    }
  ],
  "folders": {
    "downloads": "C:\\Users\\rael\\Downloads",
    "documents": "C:\\Users\\rael\\Documents",
    "desktop": "C:\\Users\\rael\\Desktop",
    "onedrive": "C:\\Users\\rael\\OneDrive",
    "quick_access": []
  },
  "programs": [
    {
      "name": "Visual Studio Code",
      "path": "C:\\Program Files\\Microsoft VS Code\\Code.exe",
      "aliases": ["vscode", "code", "vs code"]
    }
  ],
  "vscode_recent_projects": [],
  "steam_games": []
}
```

---

## Como gerar o script

Crie o arquivo `discover.py` com as seções abaixo. O script deve:

- Usar apenas stdlib do Python (pathlib, json, os, winreg, datetime, subprocess)
- Funcionar no Windows 10/11 sem privilégios de admin
- Ter um modo `--dry-run` que mostra o que encontrou sem salvar
- Ter `--output <path>` para definir onde salvar o JSON (default: `environment_map.json` no diretório atual)
- Ter `--roots <paths>` para limitar os diretórios raiz de busca (default: `C:\Users\<user>`)
- Ter `--max-depth <n>` para limitar profundidade de busca (default: 5)
- Excluir automaticamente: `node_modules`, `.venv`, `venv`, `__pycache__`, `.tox`, `site-packages`, `AppData\Local\Temp`, `$Recycle.Bin`

### Seção 1 — Detecção de projetos

```python
PROJECT_MARKERS = {
    ".git":            None,          # qualquer projeto com git
    "manage.py":       "django",
    "pyproject.toml":  "python",
    "setup.py":        "python",
    "package.json":    "node",
    "Cargo.toml":      "rust",
    "go.mod":          "go",
    "*.sln":           "dotnet",
    "pom.xml":         "java",
    "build.gradle":    "java",
    "CMakeLists.txt":  "cpp",
}
```

Ao encontrar um diretório com um ou mais marcadores, registre-o como projeto.
O `type` é o valor do marcador mais específico (priorize `manage.py` sobre
`.git`). Gere `aliases` automaticamente a partir do nome do diretório:
- nome original
- sem hífens/underscores
- palavras separadas
- lowercase de tudo

Pare de descer em subdiretórios ao encontrar um projeto (não indexar
subprojetos dentro de monorepos, a menos que `--deep` seja passado).

### Seção 2 — Pastas especiais do Windows

Use `os.path.expanduser("~")` e as variáveis de ambiente conhecidas:
- `USERPROFILE` → Downloads, Documents, Desktop, Pictures, Videos, Music
- `OneDrive`, `OneDriveCommercial`
- Registry `Shell Folders` para caminhos customizados

### Seção 3 — Programas instalados

Leia as chaves do registro:
```
HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall
HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall
HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall
```

Para cada entrada com `DisplayName` e `InstallLocation` ou `DisplayIcon`,
extraia nome e caminho do executável. Gere aliases inteligentes (ex: "Google
Chrome" → ["chrome", "google chrome", "navegador"]).

Também varra os atalhos `.lnk` em:
- `%APPDATA%\Microsoft\Windows\Start Menu\Programs`
- `%ProgramData%\Microsoft\Windows\Start Menu\Programs`

### Seção 4 — VS Code Recent Projects

Leia o arquivo (se existir):
```
%APPDATA%\Code\User\globalStorage\storage.json
```

Extraia `openedPathsList.entries` ou equivalente para listar projetos recentes.

### Seção 5 — Steam Games (opcional)

Se Steam estiver instalado, leia os arquivos `.acf` em:
```
<steam_path>\steamapps\*.acf
```

Extraia `name` e `installdir` de cada `.acf` para popular `steam_games`.

---

## Geração de aliases inteligentes

Uma parte crucial é gerar aliases em PT-BR que o usuário usaria naturalmente.
O script deve incluir um dict de aliases comuns:

```python
PROGRAM_ALIASES_PTBR = {
    "chrome": ["navegador", "browser"],
    "firefox": ["navegador"],
    "explorer": ["explorador", "pasta"],
    "cmd": ["terminal", "prompt", "prompt de comando"],
    "powershell": ["terminal", "ps"],
    "code": ["vscode", "vs code", "editor"],
    "notepad++": ["notepad", "bloco de notas"],
    "calculator": ["calculadora"],
    "steam": ["steam", "jogos"],
    "discord": ["discord"],
    "spotify": ["spotify", "música"],
    "telegram": ["telegram", "tg"],
}
```

Para projetos, gere aliases a partir do nome do diretório e do tipo:
- "portal-frotas" → ["portal frotas", "portal", "frotas"]
- tipo "django" → adicione "projeto django" como alias contextual

---

## Integração com Orion Bot

Após gerar o `environment_map.json`, o Orion Bot pode carregá-lo assim:

```python
# Em plugins/files/open.py
import json
from pathlib import Path

ENV_MAP_PATH = Path(__file__).parent.parent.parent / "environment_map.json"

def load_environment():
    with open(ENV_MAP_PATH) as f:
        return json.load(f)

def get_projects_dict():
    """Retorna dict compatível com o PROJETOS esperado pelo open.py"""
    env = load_environment()
    projetos = {}
    for proj in env["projects"]:
        for alias in proj["aliases"]:
            projetos[alias] = proj["path"]
    return projetos

# Substitui o dict PROJETOS hardcoded
PROJETOS = get_projects_dict()
```

---

## Re-scan automático

O script pode ser agendado para rodar periodicamente (Task Scheduler) ou ser
chamado pelo próprio Orion Bot com um comando como "atualiza meu mapa" ou
"re-escaneia meus projetos". Para isso, inclua no script:

```python
def needs_rescan(map_path: Path, max_age_hours: int = 24) -> bool:
    """Retorna True se o mapa não existe ou está desatualizado."""
    if not map_path.exists():
        return True
    data = json.loads(map_path.read_text())
    generated = datetime.fromisoformat(data["generated_at"])
    return (datetime.now() - generated).total_seconds() > max_age_hours * 3600
```

---

## Flags e uso

```
python discover.py                          # scan completo, salva environment_map.json
python discover.py --dry-run                # mostra o que encontrou sem salvar
python discover.py --output ~/orion/map.json  # salva em local custom
python discover.py --roots D:\ E:\projetos  # limita busca a drives/pastas específicas
python discover.py --max-depth 3            # limita profundidade
python discover.py --deep                   # indexa subprojetos dentro de monorepos
python discover.py --no-programs            # pula detecção de programas
python discover.py --no-steam               # pula detecção de jogos Steam
```

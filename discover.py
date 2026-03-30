"""
discover.py — Auto-discovery de projetos, pastas e programas no Windows.

Gera um environment_map.json com tudo que o Orion Bot precisa saber
sobre o ambiente local, sem cadastro manual.

Uso:
    python discover.py                        # scan completo
    python discover.py --dry-run              # mostra sem salvar
    python discover.py --output caminho.json  # local customizado
    python discover.py --roots D:\\ E:\\dev   # limita diretórios raiz
    python discover.py --max-depth 3          # limita profundidade
    python discover.py --deep                 # indexa subprojetos em monorepos
    python discover.py --no-programs          # pula programas instalados
    python discover.py --no-steam             # pula jogos Steam
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import struct
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# ─────────────────────────── Constantes ────────────────────────────

EXCLUDE_DIRS = {
    "node_modules", ".venv", "venv", "__pycache__", ".tox",
    "site-packages", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".cargo", "target", "dist", "build", ".next", ".nuxt",
    "$Recycle.Bin", "System Volume Information",
}

EXCLUDE_PATHS_CONTAINS = [
    "AppData\\Local\\Temp",
    "AppData\\Local\\Microsoft",
    "AppData\\Local\\Google",
    "AppData\\Local\\Mozilla",
    "AppData\\Roaming\\npm",
]

# Marcadores de projeto: arquivo/pasta → tipo
# None = genérico (só confirma que é um projeto)
PROJECT_MARKERS: dict[str, str | None] = {
    "manage.py":       "django",
    "pyproject.toml":  "python",
    "setup.py":        "python",
    "setup.cfg":       "python",
    "package.json":    "node",
    "Cargo.toml":      "rust",
    "go.mod":          "go",
    "pom.xml":         "java",
    "build.gradle":    "java",
    "build.gradle.kts":"java",
    "CMakeLists.txt":  "cpp",
    "Makefile":        None,
    ".git":            None,
}

# Glob patterns (para *.sln etc.)
PROJECT_GLOB_MARKERS: dict[str, str | None] = {
    "*.sln":   "dotnet",
    "*.csproj":"dotnet",
    "*.fsproj":"dotnet",
}

# Prioridade de tipo (maior = mais específico)
TYPE_PRIORITY: dict[str, int] = {
    "django": 10,
    "rust":   8,
    "go":     8,
    "java":   8,
    "dotnet": 8,
    "cpp":    7,
    "node":   6,
    "python": 5,
}

# Aliases PT-BR comuns para programas
PROGRAM_ALIASES_PTBR: dict[str, list[str]] = {
    "chrome":       ["navegador", "browser", "google chrome"],
    "firefox":      ["navegador", "mozilla"],
    "msedge":       ["edge", "navegador", "microsoft edge"],
    "explorer":     ["explorador de arquivos", "explorador"],
    "cmd":          ["terminal", "prompt", "prompt de comando"],
    "powershell":   ["terminal", "ps"],
    "code":         ["vscode", "vs code", "editor"],
    "notepad++":    ["notepad", "bloco de notas++"],
    "notepad":      ["bloco de notas"],
    "calc":         ["calculadora"],
    "steam":        ["steam", "jogos"],
    "discord":      ["discord"],
    "spotify":      ["spotify", "música"],
    "telegram":     ["telegram", "tg"],
    "whatsapp":     ["whatsapp", "zap", "wpp"],
    "slack":        ["slack"],
    "obs":          ["obs", "obs studio", "gravação"],
    "vlc":          ["vlc", "player de vídeo"],
    "gimp":         ["gimp", "editor de imagem"],
    "postman":      ["postman", "api"],
    "insomnia":     ["insomnia", "api"],
    "dbeaver":      ["dbeaver", "banco de dados", "database"],
    "pgadmin":      ["pgadmin", "postgres"],
    "sqlplus":      ["sqlplus", "oracle"],
    "sqldeveloper": ["sql developer", "oracle"],
    "git":          ["git"],
    "python":       ["python"],
    "node":         ["node", "nodejs"],
    "wt":           ["windows terminal", "terminal"],
}

# ─────────────────────────── Helpers ───────────────────────────────


def generate_aliases(name: str) -> list[str]:
    """Gera aliases a partir do nome de um diretório/projeto."""
    aliases = set()
    lower = name.lower()
    aliases.add(lower)

    # Sem hífens/underscores
    clean = re.sub(r"[-_.]", " ", lower).strip()
    aliases.add(clean)

    # Palavras individuais (se mais de uma)
    words = clean.split()
    if len(words) > 1:
        for w in words:
            if len(w) > 2:  # ignora palavras muito curtas
                aliases.add(w)

    # camelCase/PascalCase split
    camel_split = re.sub(r"([a-z])([A-Z])", r"\1 \2", name).lower()
    if camel_split != lower:
        aliases.add(camel_split)
        for w in camel_split.split():
            if len(w) > 2:
                aliases.add(w)

    return sorted(aliases)


def get_program_aliases(display_name: str, exe_name: str = "") -> list[str]:
    """Gera aliases para um programa instalado."""
    aliases = set()
    lower = display_name.lower()
    aliases.add(lower)

    # Nome curto do exe
    if exe_name:
        stem = Path(exe_name).stem.lower()
        aliases.add(stem)
        # Verificar aliases PT-BR
        if stem in PROGRAM_ALIASES_PTBR:
            aliases.update(PROGRAM_ALIASES_PTBR[stem])

    # Verificar aliases PT-BR pelo display_name
    for key, ptbr_aliases in PROGRAM_ALIASES_PTBR.items():
        if key in lower:
            aliases.update(ptbr_aliases)

    return sorted(aliases)


def is_excluded(path: Path) -> bool:
    """Verifica se o caminho deve ser excluído."""
    path_str = str(path)
    for exc in EXCLUDE_PATHS_CONTAINS:
        if exc in path_str:
            return True
    return path.name in EXCLUDE_DIRS


def safe_stat(path: Path) -> datetime | None:
    """Tenta obter last modified de forma segura."""
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except (OSError, PermissionError):
        return None


# ─────────────────── Seção 1: Detecção de Projetos ─────────────────


def detect_projects(
    roots: list[Path],
    max_depth: int = 5,
    deep: bool = False,
) -> list[dict[str, Any]]:
    """Varre os diretórios raiz procurando marcadores de projeto."""
    projects: list[dict[str, Any]] = []
    seen: set[str] = set()

    def scan_dir(directory: Path, depth: int) -> bool:
        """Retorna True se encontrou um projeto (para parar descida)."""
        if depth > max_depth:
            return False

        try:
            entries = list(directory.iterdir())
        except (PermissionError, OSError):
            return False

        entry_names = {e.name for e in entries}
        found_markers: list[str] = []
        project_type: str | None = None
        best_priority = -1

        # Checagem de marcadores exatos
        for marker, mtype in PROJECT_MARKERS.items():
            if marker in entry_names:
                found_markers.append(marker)
                prio = TYPE_PRIORITY.get(mtype or "", 0)
                if prio > best_priority:
                    best_priority = prio
                    project_type = mtype

        # Checagem de glob patterns
        for pattern, mtype in PROJECT_GLOB_MARKERS.items():
            if list(directory.glob(pattern)):
                found_markers.append(pattern)
                prio = TYPE_PRIORITY.get(mtype or "", 0)
                if prio > best_priority:
                    best_priority = prio
                    project_type = mtype

        is_project = len(found_markers) > 0 and ".git" in entry_names or any(
            m != ".git" for m in found_markers
        )

        if is_project:
            resolved = str(directory.resolve())
            if resolved not in seen:
                seen.add(resolved)
                aliases = generate_aliases(directory.name)
                if project_type:
                    aliases.append(f"projeto {project_type}")

                last_mod = safe_stat(directory)
                projects.append({
                    "name": directory.name,
                    "path": resolved,
                    "type": project_type or "generic",
                    "markers": sorted(found_markers),
                    "last_modified": last_mod.isoformat() if last_mod else None,
                    "aliases": sorted(set(aliases)),
                })

            if not deep:
                return True  # para de descer

        # Continua descendo nos subdiretórios
        for entry in entries:
            if entry.is_dir() and not is_excluded(entry) and not entry.name.startswith("."):
                scan_dir(entry, depth + 1)

        return is_project

    for root in roots:
        if root.exists() and root.is_dir():
            scan_dir(root, 0)

    # Ordena por last_modified (mais recente primeiro)
    projects.sort(
        key=lambda p: p.get("last_modified") or "",
        reverse=True,
    )
    return projects


# ─────────────── Seção 2: Pastas Especiais do Windows ──────────────


def detect_special_folders() -> dict[str, Any]:
    """Detecta pastas especiais do Windows."""
    home = Path.home()
    folders: dict[str, Any] = {}

    # Pastas padrão
    standard = {
        "downloads":  home / "Downloads",
        "documents":  home / "Documents",
        "desktop":    home / "Desktop",
        "pictures":   home / "Pictures",
        "videos":     home / "Videos",
        "music":      home / "Music",
    }

    for key, path in standard.items():
        if path.exists():
            folders[key] = str(path)

    # OneDrive
    for env_var in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        od = os.environ.get(env_var)
        if od and Path(od).exists():
            folders[env_var.lower()] = od

    # Quick Access — tenta ler via PowerShell
    folders["quick_access"] = _get_quick_access()

    # Tentar ler Shell Folders do registro
    if sys.platform == "win32":
        try:
            import winreg
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                        expanded = os.path.expandvars(value)
                        if Path(expanded).exists() and name not in folders:
                            folders[name.lower().replace(" ", "_")] = expanded
                        i += 1
                    except OSError:
                        break
        except (ImportError, OSError):
            pass

    return folders


def _get_quick_access() -> list[str]:
    """Tenta obter itens do Quick Access via PowerShell."""
    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "(New-Object -ComObject Shell.Application).Namespace('shell:::{679f85cb-0220-4080-b29b-5540cc05aab6}').Items() | ForEach-Object { $_.Path }"
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            paths = [
                line.strip() for line in result.stdout.strip().splitlines()
                if line.strip() and Path(line.strip()).exists()
            ]
            return paths
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return []


# ────────────── Seção 3: Programas Instalados ──────────────────────


def detect_programs() -> list[dict[str, Any]]:
    """Detecta programas instalados via registro do Windows e atalhos."""
    programs: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    if sys.platform == "win32":
        programs.extend(_read_registry_programs(seen_names))
    programs.extend(_read_start_menu_shortcuts(seen_names))

    programs.sort(key=lambda p: p["name"].lower())
    return programs


def _read_registry_programs(seen: set[str]) -> list[dict[str, Any]]:
    """Lê programas do registro do Windows."""
    results = []
    if sys.platform != "win32":
        return results

    import winreg

    reg_paths = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]

    for hive, path in reg_paths:
        try:
            with winreg.OpenKey(hive, path) as key:
                i = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        i += 1
                        with winreg.OpenKey(key, subkey_name) as subkey:
                            try:
                                name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                            except OSError:
                                continue

                            if not name or name.lower() in seen:
                                continue

                            # Tenta pegar o caminho do executável
                            exe_path = ""
                            for val_name in ("InstallLocation", "DisplayIcon"):
                                try:
                                    val = winreg.QueryValueEx(subkey, val_name)[0]
                                    if val:
                                        # DisplayIcon pode ter ",0" no final
                                        clean = val.split(",")[0].strip().strip('"')
                                        if clean.endswith(".exe") and Path(clean).exists():
                                            exe_path = clean
                                            break
                                        elif Path(clean).is_dir():
                                            # Procura .exe dentro
                                            exes = list(Path(clean).glob("*.exe"))
                                            if exes:
                                                exe_path = str(exes[0])
                                                break
                                except OSError:
                                    continue

                            seen.add(name.lower())
                            aliases = get_program_aliases(name, exe_path)
                            results.append({
                                "name": name,
                                "path": exe_path,
                                "aliases": aliases,
                            })
                    except OSError:
                        break
        except (OSError, PermissionError):
            continue

    return results


def _read_start_menu_shortcuts(seen: set[str]) -> list[dict[str, Any]]:
    """Lê atalhos .lnk do Menu Iniciar."""
    results = []
    start_paths = []

    appdata = os.environ.get("APPDATA", "")
    if appdata:
        start_paths.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")

    programdata = os.environ.get("ProgramData", "")
    if programdata:
        start_paths.append(Path(programdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")

    for start_path in start_paths:
        if not start_path.exists():
            continue
        for lnk in start_path.rglob("*.lnk"):
            name = lnk.stem
            if name.lower() in seen or "uninstall" in name.lower():
                continue

            # Tenta resolver o .lnk via PowerShell (leve)
            target = _resolve_lnk(lnk)
            if target and target.endswith(".exe") and Path(target).exists():
                seen.add(name.lower())
                aliases = get_program_aliases(name, target)
                results.append({
                    "name": name,
                    "path": target,
                    "aliases": aliases,
                })

    return results


def _resolve_lnk(lnk_path: Path) -> str:
    """Resolve um .lnk para o target path. Fallback: lê bytes do .lnk."""
    # Método 1: PowerShell (mais confiável)
    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                f"(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk_path}').TargetPath"
            ],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # Método 2: Parse binário básico do .lnk (fallback)
    try:
        with open(lnk_path, "rb") as f:
            content = f.read()
        # O target path geralmente aparece como string no arquivo
        # Busca padrão simples: procura por "C:\" ou "D:\"
        for drive in (b"C:\\", b"D:\\", b"E:\\"):
            idx = content.find(drive)
            if idx >= 0:
                end = content.find(b"\x00", idx)
                if end > idx:
                    path_str = content[idx:end].decode("utf-8", errors="ignore")
                    if path_str.endswith(".exe"):
                        return path_str
    except (OSError, UnicodeDecodeError):
        pass

    return ""


# ──────────── Seção 4: VS Code Recent Projects ────────────────────


def detect_vscode_projects() -> list[str]:
    """Extrai projetos recentes do VS Code."""
    projects: list[str] = []

    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        return projects

    storage_path = Path(appdata) / "Code" / "User" / "globalStorage" / "storage.json"
    if not storage_path.exists():
        # Tenta Insiders
        storage_path = Path(appdata) / "Code - Insiders" / "User" / "globalStorage" / "storage.json"

    if not storage_path.exists():
        return projects

    try:
        data = json.loads(storage_path.read_text(encoding="utf-8"))

        # VS Code >= 1.64 usa openedPathsList
        opened = data.get("openedPathsList", {})
        entries = opened.get("entries", [])

        for entry in entries:
            # Cada entry pode ser {"folderUri": "file:///..."} ou {"fileUri": ...}
            uri = entry.get("folderUri", "") or entry.get("workspace", {}).get("configPath", "")
            if uri.startswith("file:///"):
                # Converte file URI para path do Windows
                path = uri.replace("file:///", "").replace("/", "\\")
                # Decodifica %20 etc.
                from urllib.parse import unquote
                path = unquote(path)
                if Path(path).exists():
                    projects.append(path)

        # Fallback: windowsState
        if not projects:
            windows = data.get("windowsState", {})
            last_active = windows.get("lastActiveWindow", {})
            folder = last_active.get("folder", "")
            if folder.startswith("file:///"):
                from urllib.parse import unquote
                path = unquote(folder.replace("file:///", "").replace("/", "\\"))
                if Path(path).exists():
                    projects.append(path)

    except (json.JSONDecodeError, OSError, KeyError):
        pass

    return projects


# ──────────────── Seção 5: Steam Games ─────────────────────────────


def detect_steam_games() -> list[dict[str, str]]:
    """Detecta jogos Steam instalados lendo arquivos .acf."""
    games: list[dict[str, str]] = []

    # Encontra o diretório do Steam
    steam_paths: list[Path] = []

    # Tenta pelo registro
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam") as key:
                steam_dir = winreg.QueryValueEx(key, "SteamPath")[0]
                if steam_dir:
                    steam_paths.append(Path(steam_dir))
        except (ImportError, OSError):
            pass

    # Fallback: caminhos comuns
    for common in [
        Path("C:/Program Files (x86)/Steam"),
        Path("C:/Program Files/Steam"),
        Path.home() / "Steam",
    ]:
        if common.exists() and common not in steam_paths:
            steam_paths.append(common)

    for steam_path in steam_paths:
        steamapps = steam_path / "steamapps"
        if not steamapps.exists():
            continue

        for acf in steamapps.glob("*.acf"):
            try:
                content = acf.read_text(encoding="utf-8")
                name_match = re.search(r'"name"\s+"(.+?)"', content)
                dir_match = re.search(r'"installdir"\s+"(.+?)"', content)

                if name_match and dir_match:
                    game_name = name_match.group(1)
                    install_dir = dir_match.group(1)
                    full_path = steamapps / "common" / install_dir

                    games.append({
                        "name": game_name,
                        "path": str(full_path) if full_path.exists() else "",
                        "aliases": generate_aliases(game_name),
                    })
            except (OSError, UnicodeDecodeError):
                continue

    games.sort(key=lambda g: g["name"].lower())
    return games


# ──────────────── Re-scan Helper ───────────────────────────────────


def needs_rescan(map_path: Path, max_age_hours: int = 24) -> bool:
    """Retorna True se o mapa não existe ou está desatualizado."""
    if not map_path.exists():
        return True
    try:
        data = json.loads(map_path.read_text(encoding="utf-8"))
        generated = datetime.fromisoformat(data["generated_at"])
        return (datetime.now() - generated).total_seconds() > max_age_hours * 3600
    except (json.JSONDecodeError, KeyError, OSError):
        return True


# ──────────────── Main ─────────────────────────────────────────────


def discover(
    roots: list[Path] | None = None,
    max_depth: int = 5,
    deep: bool = False,
    include_programs: bool = True,
    include_steam: bool = True,
) -> dict[str, Any]:
    """Executa a discovery completa e retorna o mapa do ambiente."""

    if roots is None:
        roots = [Path.home()]

    print(f"🔍 Escaneando {len(roots)} diretório(s) raiz...")
    for r in roots:
        print(f"   📁 {r}")

    # 1. Projetos
    print("\n📦 Detectando projetos...")
    projects = detect_projects(roots, max_depth, deep)
    print(f"   ✅ {len(projects)} projeto(s) encontrado(s)")

    # 2. Pastas especiais
    print("\n📂 Detectando pastas especiais...")
    folders = detect_special_folders()
    print(f"   ✅ {len(folders)} pasta(s)")

    # 3. Programas
    programs: list[dict[str, Any]] = []
    if include_programs:
        print("\n💻 Detectando programas instalados...")
        programs = detect_programs()
        print(f"   ✅ {len(programs)} programa(s)")

    # 4. VS Code
    print("\n🔵 Detectando projetos recentes do VS Code...")
    vscode = detect_vscode_projects()
    print(f"   ✅ {len(vscode)} projeto(s) recente(s)")

    # 5. Steam
    steam: list[dict[str, str]] = []
    if include_steam:
        print("\n🎮 Detectando jogos Steam...")
        steam = detect_steam_games()
        print(f"   ✅ {len(steam)} jogo(s)")

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "machine_name": platform.node(),
        "scan_roots": [str(r) for r in roots],
        "projects": projects,
        "folders": folders,
        "programs": programs,
        "vscode_recent_projects": vscode,
        "steam_games": steam,
    }


def main():
    # Garante UTF-8 no stdout (evita UnicodeEncodeError em terminais cp1252)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    parser = argparse.ArgumentParser(
        description="Auto-discovery de projetos, pastas e programas do Windows"
    )
    parser.add_argument(
        "--output", "-o",
        default="memoria/environment_map.json",
        help="Caminho do arquivo JSON de saída (default: memoria/environment_map.json)",
    )
    parser.add_argument(
        "--roots", "-r",
        nargs="+",
        help="Diretórios raiz para busca (default: pasta do usuário)",
    )
    parser.add_argument(
        "--max-depth", "-d",
        type=int, default=5,
        help="Profundidade máxima de busca (default: 5)",
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help="Indexar subprojetos dentro de monorepos",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra o que encontrou sem salvar",
    )
    parser.add_argument(
        "--no-programs",
        action="store_true",
        help="Pula detecção de programas instalados",
    )
    parser.add_argument(
        "--no-steam",
        action="store_true",
        help="Pula detecção de jogos Steam",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        default=True,
        help="Formata o JSON com indentação (default: True)",
    )

    args = parser.parse_args()

    roots = [Path(r) for r in args.roots] if args.roots else None

    result = discover(
        roots=roots,
        max_depth=args.max_depth,
        deep=args.deep,
        include_programs=not args.no_programs,
        include_steam=not args.no_steam,
    )

    json_str = json.dumps(result, indent=2 if args.pretty else None, ensure_ascii=False)

    if args.dry_run:
        print("\n" + "=" * 60)
        print("🔎 DRY RUN — resultado (não salvo):")
        print("=" * 60)
        print(json_str)
    else:
        output = Path(args.output)
        output.write_text(json_str, encoding="utf-8")
        print(f"\n✅ Mapa salvo em: {output.resolve()}")
        print(f"   📊 {len(result['projects'])} projetos | "
              f"{len(result['programs'])} programas | "
              f"{len(result['steam_games'])} jogos Steam")

    return result


if __name__ == "__main__":
    main()

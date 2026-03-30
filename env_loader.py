"""
env_loader.py — Carrega o environment_map.json gerado pelo discover.py
e expõe dicts prontos para uso nos plugins do Orion Bot.

Uso dentro do Orion Bot:
    from env_loader import env, PROJETOS, PASTAS, PROGRAMAS

    # Abre um projeto pelo alias
    path = PROJETOS.get("portal frotas")  # → "C:\\Users\\rael\\projects\\portal-frotas"

    # Abre uma pasta pelo alias
    path = PASTAS.get("downloads")  # → "C:\\Users\\rael\\Downloads"

    # Abre um programa pelo alias
    path = PROGRAMAS.get("vscode")  # → "C:\\Program Files\\Microsoft VS Code\\Code.exe"
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Caminho padrão do mapa — ajuste conforme a estrutura do Orion Bot
DEFAULT_MAP_PATH = Path(__file__).parent / "memoria" / "environment_map.json"


class EnvironmentMap:
    """Wrapper em cima do environment_map.json com busca por alias."""

    def __init__(self, map_path: Path | str | None = None):
        self.map_path = Path(map_path or DEFAULT_MAP_PATH)
        self._data: dict[str, Any] = {}
        self._projects_dict: dict[str, str] = {}
        self._folders_dict: dict[str, str] = {}
        self._programs_dict: dict[str, str] = {}
        self._games_dict: dict[str, str] = {}
        self.reload()

    def reload(self):
        """(Re)carrega o JSON do disco."""
        if not self.map_path.exists():
            print(f"⚠️  environment_map.json não encontrado em {self.map_path}")
            print("   Execute: python discover.py")
            return

        self._data = json.loads(self.map_path.read_text(encoding="utf-8"))
        self._build_indexes()

    def _build_indexes(self):
        """Constrói os dicts de alias → path."""
        # Projetos
        self._projects_dict = {}
        for proj in self._data.get("projects", []):
            for alias in proj.get("aliases", []):
                self._projects_dict[alias] = proj["path"]
            # Também indexa pelo nome exato
            self._projects_dict[proj["name"].lower()] = proj["path"]

        # Pastas
        self._folders_dict = {}
        folders = self._data.get("folders", {})
        for key, value in folders.items():
            if isinstance(value, str):
                self._folders_dict[key] = value
            elif isinstance(value, list):
                # quick_access
                for path in value:
                    self._folders_dict[Path(path).name.lower()] = path

        # Programas
        self._programs_dict = {}
        for prog in self._data.get("programs", []):
            if not prog.get("path"):
                continue
            for alias in prog.get("aliases", []):
                self._programs_dict[alias] = prog["path"]

        # Jogos Steam
        self._games_dict = {}
        for game in self._data.get("steam_games", []):
            if not game.get("path"):
                continue
            for alias in game.get("aliases", []):
                self._games_dict[alias] = game["path"]

    @property
    def projects(self) -> dict[str, str]:
        """alias → path dos projetos."""
        return self._projects_dict

    @property
    def folders(self) -> dict[str, str]:
        """alias → path das pastas."""
        return self._folders_dict

    @property
    def programs(self) -> dict[str, str]:
        """alias → path dos programas."""
        return self._programs_dict

    @property
    def games(self) -> dict[str, str]:
        """alias → path dos jogos."""
        return self._games_dict

    @property
    def raw(self) -> dict[str, Any]:
        """Dados brutos do JSON."""
        return self._data

    def search(self, query: str) -> list[dict[str, Any]]:
        """Busca fuzzy em todos os aliases (projetos, programas, jogos)."""
        query_lower = query.lower()
        results = []

        for proj in self._data.get("projects", []):
            if any(query_lower in alias for alias in proj.get("aliases", [])):
                results.append({"type": "project", **proj})

        for prog in self._data.get("programs", []):
            if any(query_lower in alias for alias in prog.get("aliases", [])):
                results.append({"type": "program", **prog})

        for game in self._data.get("steam_games", []):
            if any(query_lower in alias for alias in game.get("aliases", [])):
                results.append({"type": "game", **game})

        # Pastas
        for key, path in self._folders_dict.items():
            if query_lower in key:
                results.append({"type": "folder", "name": key, "path": path})

        return results

    def find_project(self, query: str) -> str | None:
        """Encontra o path de um projeto pelo alias (busca parcial)."""
        query_lower = query.lower()

        # Match exato primeiro
        if query_lower in self._projects_dict:
            return self._projects_dict[query_lower]

        # Match parcial
        for alias, path in self._projects_dict.items():
            if query_lower in alias or alias in query_lower:
                return path

        return None

    def find_program(self, query: str) -> str | None:
        """Encontra o path de um programa pelo alias (busca parcial)."""
        query_lower = query.lower()
        if query_lower in self._programs_dict:
            return self._programs_dict[query_lower]
        for alias, path in self._programs_dict.items():
            if query_lower in alias or alias in query_lower:
                return path
        return None


# ── Singleton de conveniência ──

_env: EnvironmentMap | None = None


def get_env(map_path: Path | str | None = None) -> EnvironmentMap:
    """Retorna uma instância singleton do EnvironmentMap."""
    global _env
    if _env is None:
        _env = EnvironmentMap(map_path)
    return _env


# ── Atalhos diretos (para import rápido nos plugins) ──

def _lazy_env() -> EnvironmentMap:
    return get_env()


class _LazyDict:
    """Dict que carrega o environment_map.json só no primeiro acesso."""
    def __init__(self, attr: str):
        self._attr = attr
        self._loaded = False
        self._dict: dict[str, str] = {}

    def _load(self):
        if not self._loaded:
            self._dict = getattr(_lazy_env(), self._attr)
            self._loaded = True

    def get(self, key: str, default=None):
        self._load()
        return self._dict.get(key.lower(), default)

    def __contains__(self, key):
        self._load()
        return key.lower() in self._dict

    def __getitem__(self, key):
        self._load()
        return self._dict[key.lower()]

    def items(self):
        self._load()
        return self._dict.items()

    def keys(self):
        self._load()
        return self._dict.keys()

    def values(self):
        self._load()
        return self._dict.values()


# Estes podem ser importados diretamente nos plugins:
#   from env_loader import PROJETOS, PASTAS, PROGRAMAS
PROJETOS = _LazyDict("projects")
PASTAS = _LazyDict("folders")
PROGRAMAS = _LazyDict("programs")
JOGOS = _LazyDict("games")

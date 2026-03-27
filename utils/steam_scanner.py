"""
utils/steam_scanner.py
Descobre automaticamente todos os jogos instalados via Steam,
lendo os arquivos VDF nativos — sem hardcode de caminho.
"""

import os
import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Caminhos padrão de instalação do Steam no Windows
STEAM_DEFAULT_PATHS = [
    Path("C:/Program Files (x86)/Steam"),
    Path("C:/Program Files/Steam"),
    Path(os.path.expanduser("~")) / "Steam",
]


def _encontrar_pasta_steam() -> Path | None:
    """Tenta localizar a pasta raiz do Steam."""
    # 1. Verifica caminhos padrão
    for caminho in STEAM_DEFAULT_PATHS:
        if caminho.exists():
            return caminho

    # 2. Tenta via registro do Windows
    try:
        import winreg
        chave = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")
        valor, _ = winreg.QueryValueEx(chave, "InstallPath")
        pasta = Path(valor)
        if pasta.exists():
            return pasta
    except Exception:
        pass

    try:
        import winreg
        chave = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam")
        valor, _ = winreg.QueryValueEx(chave, "SteamPath")
        pasta = Path(valor)
        if pasta.exists():
            return pasta
    except Exception:
        pass

    return None


def _parsear_vdf_simples(texto: str) -> dict:
    """
    Parser minimalista de VDF (Valve Data Format).
    Extrai pares chave/valor em nível superficial.
    """
    resultado = {}
    for linha in texto.splitlines():
        linha = linha.strip()
        match = re.match(r'"([^"]+)"\s+"([^"]*)"', linha)
        if match:
            resultado[match.group(1).lower()] = match.group(2)
    return resultado


def _obter_pastas_biblioteca(steam_root: Path) -> list[Path]:
    """
    Lê libraryfolders.vdf para obter todas as pastas de biblioteca
    (o usuário pode ter jogos em outros HDs/SSDs).
    """
    vdf_path = steam_root / "steamapps" / "libraryfolders.vdf"
    pastas = [steam_root / "steamapps"]

    if not vdf_path.exists():
        logger.warning(f"libraryfolders.vdf não encontrado em: {vdf_path}")
        return pastas

    try:
        texto = vdf_path.read_text(encoding="utf-8", errors="ignore")
        # Extrai valores de "path" de todas as bibliotecas
        for match in re.finditer(r'"path"\s+"([^"]+)"', texto, re.IGNORECASE):
            caminho = Path(match.group(1)) / "steamapps"
            if caminho.exists() and caminho not in pastas:
                pastas.append(caminho)
                logger.info(f"Biblioteca Steam encontrada: {caminho}")
    except Exception as e:
        logger.error(f"Erro ao ler libraryfolders.vdf: {e}")

    return pastas


def _obter_executavel_jogo(pasta_jogo: Path) -> Path | None:
    """
    Tenta encontrar o executável principal dentro da pasta do jogo.
    Prioriza .exe na raiz, depois subpastas rasas.
    """
    # Ignora executáveis de instaladores/redistributables
    ignorar = {
        "unins000.exe", "uninstall.exe", "setup.exe", "redist",
        "vcredist", "dotnet", "directx", "crashpad", "crashreport",
        "dxsetup.exe", "vc_redist", "unarc.exe",
    }

    candidatos = []

    # Busca na raiz da pasta do jogo
    for exe in pasta_jogo.glob("*.exe"):
        nome = exe.name.lower()
        if not any(ign in nome for ign in ignorar):
            candidatos.append(exe)

    # Se não achou na raiz, busca um nível abaixo
    if not candidatos:
        for exe in pasta_jogo.glob("*/*.exe"):
            nome = exe.name.lower()
            if not any(ign in nome for ign in ignorar):
                candidatos.append(exe)

    if not candidatos:
        return None

    # Prefere o maior .exe (heurística: jogos são maiores que launchers)
    return max(candidatos, key=lambda p: p.stat().st_size)


def escanear_jogos_steam() -> dict[str, str]:
    """
    Escaneia todos os jogos Steam instalados.

    Retorna:
        dict { "Nome do Jogo": "C:\\caminho\\completo\\jogo.exe" }
    """
    jogos = {}

    steam_root = _encontrar_pasta_steam()
    if not steam_root:
        logger.error("Steam não encontrado no sistema.")
        return jogos

    logger.info(f"Steam encontrado em: {steam_root}")
    pastas_biblioteca = _obter_pastas_biblioteca(steam_root)

    for steamapps in pastas_biblioteca:
        # Cada jogo instalado tem um arquivo appmanifest_<id>.acf
        for manifest in steamapps.glob("appmanifest_*.acf"):
            try:
                texto = manifest.read_text(encoding="utf-8", errors="ignore")
                dados = _parsear_vdf_simples(texto)

                nome = dados.get("name", "").strip()
                pasta_rel = dados.get("installdir", "").strip()
                state_flags = int(dados.get("stateflags", "0"))

                # stateflags=4 significa "totalmente instalado"
                if not nome or not pasta_rel or state_flags != 4:
                    continue

                pasta_jogo = steamapps / "common" / pasta_rel
                if not pasta_jogo.exists():
                    continue

                exe = _obter_executavel_jogo(pasta_jogo)
                if exe:
                    jogos[nome] = str(exe)
                    logger.debug(f"Jogo encontrado: {nome} → {exe}")
                else:
                    # Registra sem executável (pode ser lançado via Steam)
                    jogos[nome] = f"steam://rungameid/{dados.get('appid', '')}"
                    logger.debug(f"Jogo sem .exe direto: {nome}, usando protocolo Steam")

            except Exception as e:
                logger.warning(f"Erro ao processar {manifest.name}: {e}")

    logger.info(f"Total de jogos encontrados: {len(jogos)}")
    return jogos

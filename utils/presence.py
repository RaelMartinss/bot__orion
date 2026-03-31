"""
utils/presence.py

Detecta presença do usuário via pendrive físico (token USB).

Funcionamento:
  - Quando o usuário está no PC → pendrive conectado → Orion fala por voz
  - Quando o usuário sai → pendrive removido → Orion envia Telegram

Configuração:
  - Na primeira vez, rode: definir_pendrive_presenca()
  - Ou diga ao Orion: "configure meu pendrive como presença"
  - O label/letra do pendrive é salvo em memoria/presenca_config.json

Fallback: se nenhum pendrive estiver configurado, usa idle de teclado/mouse.
"""

import ctypes
import string
import json
import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_FILE = Path("memoria/presenca_config.json")
_MAX_IDLE_MINUTOS = 5  # usado apenas como fallback sem pendrive

# ── Detecção de drives removíveis ────────────────────────────────────────────

def listar_pendrives() -> list[dict]:
    """Retorna lista de drives removíveis conectados com letra e label."""
    drives = []
    bitmask = ctypes.windll.kernel32.GetLogicalDrives()
    for letra in string.ascii_uppercase:
        if bitmask & 1:
            caminho = f"{letra}:\\"
            tipo = ctypes.windll.kernel32.GetDriveTypeW(caminho)
            if tipo == 2:  # DRIVE_REMOVABLE
                label = _get_label(caminho)
                drives.append({"letra": letra, "caminho": caminho, "label": label})
        bitmask >>= 1
    return drives


def _get_label(caminho: str) -> str:
    """Retorna o volume label de um drive."""
    buf = ctypes.create_unicode_buffer(261)
    try:
        ctypes.windll.kernel32.GetVolumeInformationW(
            caminho, buf, ctypes.sizeof(buf),
            None, None, None, None, 0
        )
        return buf.value or "(sem nome)"
    except Exception:
        return "(sem nome)"


# ── Configuração do pendrive de presença ──────────────────────────────────────

def _carregar_config() -> dict:
    if _CONFIG_FILE.exists():
        try:
            return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _salvar_config(cfg: dict) -> None:
    _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def definir_pendrive_presenca(letra: str | None = None, label: str | None = None) -> str:
    """
    Define qual pendrive será o token de presença.
    Se não informar letra/label, detecta automaticamente o primeiro removível conectado.
    Retorna mensagem de confirmação.
    """
    pendrives = listar_pendrives()
    if not pendrives:
        return "Nenhum pendrive detectado agora. Conecte o pendrive e tente novamente."

    if letra:
        alvo = next((p for p in pendrives if p["letra"].upper() == letra.upper()), None)
    elif label:
        alvo = next((p for p in pendrives if label.lower() in p["label"].lower()), None)
    else:
        alvo = pendrives[0]  # primeiro removível detectado

    if not alvo:
        listagem = ", ".join(f"{p['letra']}: ({p['label']})" for p in pendrives)
        return f"Pendrive não encontrado. Disponíveis: {listagem}"

    cfg = {"letra": alvo["letra"], "label": alvo["label"]}
    _salvar_config(cfg)
    return (
        f"✅ Pendrive de presença configurado: *{alvo['label']}* ({alvo['letra']}:)\n"
        f"Quando conectado = você está aqui → Orion fala.\n"
        f"Quando removido = você saiu → Orion manda Telegram."
    )


def pendrive_configurado() -> dict | None:
    """Retorna a config do pendrive de presença ou None se não configurado."""
    cfg = _carregar_config()
    return cfg if cfg.get("letra") else None


# ── Detecção de presença ──────────────────────────────────────────────────────

def pendrive_presente() -> bool:
    """True se o pendrive de presença está conectado."""
    cfg = pendrive_configurado()
    if not cfg:
        return False
    caminho = f"{cfg['letra']}:\\"
    tipo = ctypes.windll.kernel32.GetDriveTypeW(caminho)
    return tipo == 2  # DRIVE_REMOVABLE


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def idle_segundos() -> float:
    """Segundos desde o último input de mouse/teclado (fallback)."""
    try:
        lii = _LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
        millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
        return millis / 1000.0
    except Exception:
        return 0.0


def usuario_presente(max_idle_minutos: int = _MAX_IDLE_MINUTOS) -> bool:
    """
    True se o usuário está presente.
    Método primário: pendrive físico conectado.
    Fallback: idle de teclado/mouse < N minutos.
    """
    if pendrive_configurado():
        return pendrive_presente()
    return idle_segundos() < max_idle_minutos * 60


async def aguardar_retorno(timeout_minutos: int = 480) -> bool:
    """
    Aguarda o usuário retornar (pendrive reconectado ou idle cair).
    Retorna True quando detectar presença, False se timeout esgotar.
    """
    fim = asyncio.get_event_loop().time() + timeout_minutos * 60
    while asyncio.get_event_loop().time() < fim:
        if usuario_presente():
            return True
        await asyncio.sleep(10)  # pendrive: polling a cada 10s é suficiente
    return False

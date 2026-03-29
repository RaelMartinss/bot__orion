"""
utils/presence.py

Detecta se o usuário está presente no PC usando tempo de inatividade
de mouse/teclado (Windows GetLastInputInfo via ctypes).

Sem dependências externas.
"""

import ctypes
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_MAX_IDLE_MINUTOS = 5  # Considera ausente após 5 min sem input


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def idle_segundos() -> float:
    """Retorna quantos segundos o usuário está inativo (sem mouse/teclado)."""
    try:
        lii = _LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
        millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
        return millis / 1000.0
    except Exception as e:
        logger.warning("Erro ao ler idle time: %s", e)
        return 0.0


def usuario_presente(max_idle_minutos: int = _MAX_IDLE_MINUTOS) -> bool:
    """True se o usuário interagiu com o PC nos últimos N minutos."""
    return idle_segundos() < max_idle_minutos * 60


async def aguardar_retorno(timeout_minutos: int = 120) -> bool:
    """
    Aguarda o usuário retornar ao PC (idle cai abaixo do limiar).
    Retorna True quando detectar presença, False se timeout esgotar.
    """
    fim = asyncio.get_event_loop().time() + timeout_minutos * 60
    while asyncio.get_event_loop().time() < fim:
        if usuario_presente():
            return True
        await asyncio.sleep(20)
    return False

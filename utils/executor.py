"""
utils/executor.py
Executa intenções sem precisar de um Update do Telegram.
Usado pelo mic_listener e pelos handlers de voz/texto.
"""

import logging
import os
import subprocess
import webbrowser
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


def executar_intent(intent: dict) -> str:
    """Executa a intent e retorna uma string de feedback."""
    action = intent.get("action")
    query = intent.get("query")
    delay = intent.get("delay")

    if action == "spotify":
        if query:
            # URI scheme abre o app do Spotify diretamente (sem browser)
            os.startfile(f"spotify:search:{query}")
            return f"🎵 Tocando no Spotify: *{query}*"
        os.startfile("spotify:")
        return "🎵 Spotify aberto."

    if action == "youtube":
        if query:
            url, titulo = _primeiro_video_youtube(query)
            webbrowser.open(url)
            return f"▶️ Tocando: *{titulo}*"
        webbrowser.open("https://www.youtube.com")
        return "▶️ YouTube aberto."

    if action == "netflix":
        if query:
            webbrowser.open(f"https://www.netflix.com/search?q={quote_plus(query)}")
            return f"🎬 Buscando na Netflix: *{query}*"
        webbrowser.open("https://www.netflix.com")
        return "🎬 Netflix aberto."

    if action == "pausar":
        from handlers.controle import ctrl_pausar
        return ctrl_pausar()

    if action == "proxima":
        from handlers.controle import ctrl_proxima
        return ctrl_proxima()

    if action == "anterior":
        from handlers.controle import ctrl_anterior
        return ctrl_anterior()

    if action == "jogo":
        return _abrir_jogo(query)

    if action == "vol_set":
        return _volume_set(query)

    if action == "vol_up":
        return _volume("up", query)

    if action == "vol_down":
        return _volume("down", query)

    if action == "mute":
        return _mute()

    if action == "desligar":
        d = delay if delay is not None else 60
        os.system(f"shutdown /s /t {d}")
        return f"💤 PC desligando em {d}s."

    if action == "reiniciar":
        d = delay if delay is not None else 60
        os.system(f"shutdown /r /t {d}")
        return f"🔄 PC reiniciando em {d}s."

    if action == "cancelar":
        os.system("shutdown /a")
        return "✅ Desligamento cancelado."

    return "❓ Não entendi o comando."


# ── Helpers ──────────────────────────────────────────────────────────────────

def _primeiro_video_youtube(query: str) -> tuple[str, str]:
    """Retorna (url_com_autoplay, titulo) do primeiro resultado do YouTube."""
    try:
        import yt_dlp
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "skip_download": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}", download=False)
            if info and info.get("entries"):
                entry = info["entries"][0]
                video_id = entry.get("id")
                titulo = entry.get("title", query)
                if video_id:
                    url = f"https://www.youtube.com/watch?v={video_id}&autoplay=1"
                    return url, titulo
    except Exception as e:
        logger.warning(f"yt-dlp falhou, abrindo busca: {e}")
    # Fallback para busca normal
    return f"https://www.youtube.com/results?search_query={quote_plus(query)}", query


def _abrir_jogo(nome: str | None) -> str:
    if not nome:
        return "❓ Informe o nome do jogo."

    from difflib import get_close_matches
    from utils.steam_scanner import escanear_jogos_steam

    jogos = escanear_jogos_steam()
    if not jogos:
        return "❌ Nenhum jogo Steam encontrado."

    nomes = list(jogos.keys())
    match = next((n for n in nomes if n.lower() == nome.lower()), None)

    if not match:
        parciais = [n for n in nomes if nome.lower() in n.lower()]
        if len(parciais) == 1:
            match = parciais[0]
        elif not parciais:
            sugestoes = get_close_matches(nome, nomes, n=1, cutoff=0.4)
            match = sugestoes[0] if sugestoes else None

    if not match:
        return f"❌ Jogo '{nome}' não encontrado."

    caminho = jogos[match]
    try:
        if caminho.startswith("steam://"):
            os.startfile(caminho)
        else:
            subprocess.Popen(
                [caminho],
                cwd=os.path.dirname(caminho),
                creationflags=subprocess.DETACHED_PROCESS,
            )
        return f"🎮 Abrindo *{match}*..."
    except Exception as e:
        logger.error(f"Erro ao abrir {match}: {e}")
        return f"❌ Erro ao abrir *{match}*: {e}"


def _get_vol():
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL

    dispositivos = AudioUtilities.GetSpeakers()
    if dispositivos is None:
        raise RuntimeError("Nenhum dispositivo de áudio encontrado.")
    dev = getattr(dispositivos, "_dev", dispositivos)
    interface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def _barra(pct: int) -> str:
    blocos = round(pct / 10)
    return "█" * blocos + "░" * (10 - blocos)


def _volume(direcao: str, query: str | None) -> str:
    try:
        passo = float(query) / 100 if query and query.isdigit() else 0.10
        vol = _get_vol()
        atual = vol.GetMasterVolumeLevelScalar()
        novo = min(1.0, atual + passo) if direcao == "up" else max(0.0, atual - passo)
        vol.SetMasterVolumeLevelScalar(novo, None)
        pct = int(novo * 100)
        emoji = "🔊" if direcao == "up" else "🔉"
        return f"{emoji} *{pct}%*  {_barra(pct)}"
    except Exception as e:
        return f"❌ Erro no volume: {e}"


def _volume_set(query: str | None) -> str:
    try:
        if not query or not query.isdigit():
            vol = _get_vol()
            pct = int(vol.GetMasterVolumeLevelScalar() * 100)
            return f"🔊 Volume atual: *{pct}%*  {_barra(pct)}"
        alvo = max(0, min(100, int(query)))
        vol = _get_vol()
        vol.SetMasterVolumeLevelScalar(alvo / 100, None)
        return f"🔊 Volume: *{alvo}%*  {_barra(alvo)}"
    except Exception as e:
        return f"❌ Erro no volume: {e}"


def _mute() -> str:
    try:
        vol = _get_vol()
        estado = vol.GetMute()
        vol.SetMute(not estado, None)
        return "🔇 *Mutado*" if not estado else "🔊 *Desmutado*"
    except Exception as e:
        return f"❌ Erro no mute: {e}"

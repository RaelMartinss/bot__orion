"""
utils/mic_listener.py
Escuta o microfone em background via sounddevice e executa comandos por voz.
Envia notificação ao Telegram após cada comando executado.
"""

import asyncio
import logging
import queue
import threading
import time

import numpy as np

logger = logging.getLogger(__name__)

WAKE_WORD = "orion"         # palavra de ativação (lowercase)
SAMPLE_RATE = 16000
BLOCK_SIZE = 1024
SILENCE_THRESHOLD = 0.015   # RMS mínimo para considerar fala
SILENCE_FRAMES = 20         # blocos de silêncio antes de parar (≈1.3s)
MAX_RECORD_FRAMES = 620     # blocos máximos por gravação (≈10s)
MIN_SPEECH_FRAMES = 8       # blocos mínimos de fala para processar (≈0.5s)

# Estado compartilhado
_chat_id: int | None = None
_bot = None
_loop: asyncio.AbstractEventLoop | None = None
_stop_event = threading.Event()
_thread: threading.Thread | None = None


def configure(loop: asyncio.AbstractEventLoop, bot):
    """Deve ser chamado antes de iniciar(), com o loop e bot do PTB."""
    global _loop, _bot
    _loop = loop
    _bot = bot


def update_chat_id(chat_id: int):
    """Atualiza o chat_id para onde notificações serão enviadas."""
    global _chat_id
    _chat_id = chat_id


def iniciar():
    """Inicia o listener em uma thread daemon."""
    global _thread
    _stop_event.clear()
    _thread = threading.Thread(target=_loop_mic, daemon=True, name="mic-listener")
    _thread.start()
    logger.info("🎙️ Mic listener iniciado em background.")


def parar():
    _stop_event.set()


# ── Loop principal ────────────────────────────────────────────────────────────

def _loop_mic():
    try:
        import sounddevice as sd
    except ImportError:
        logger.error("sounddevice não instalado. Rode: uv add sounddevice")
        return

    from utils.transcriber import transcrever_numpy
    from utils.intent_parser import parse_intent
    from utils.executor import executar_intent

    logger.info("🎙️ Aguardando comandos de voz no microfone...")

    while not _stop_event.is_set():
        audio = _gravar_ate_silencio(sd)
        if audio is None:
            continue

        try:
            texto = transcrever_numpy(audio, SAMPLE_RATE)
        except Exception as e:
            logger.error(f"Erro na transcrição: {e}", exc_info=True)
            continue

        if not texto or len(texto.strip()) < 3:
            continue

        logger.info(f"🎙️ Captado: '{texto}'")

        # Exige wake word "orion" no início — ignora silenciosamente se ausente
        comando = _extrair_comando(texto)
        if comando is None:
            logger.debug(f"🎙️ Wake word ausente: '{texto}'")
            continue

        intent = parse_intent(comando)
        if intent["action"] == "desconhecido":
            logger.debug(f"🎙️ Sem intenção reconhecida para: '{comando}'")
            continue

        texto = comando  # usa o texto limpo na notificação

        resultado = executar_intent(intent)

        logger.info(f"🎙️ Executado: {resultado}")
        _notificar_telegram(texto, resultado)


def _extrair_comando(texto: str) -> str | None:
    """
    Verifica se o texto começa com a wake word 'orion' e retorna o restante.
    Aceita variações de transcrição: 'órion', 'oryon', 'oron', etc.
    Retorna None se a wake word não estiver presente.
    """
    import re
    t = texto.lower().strip()
    # Remove pontuação do início antes de checar
    t = re.sub(r'^[,.\s]+', '', t)
    # Aceita variações fonéticas que o Whisper pode gerar
    padrao = r'^(orion|órion|oryon|orin|oron|ori[aã]o|orião)\s*[,.]?\s*'
    m = re.match(padrao, t)
    if not m:
        return None
    return t[m.end():].strip() or None


def _gravar_ate_silencio(sd) -> "np.ndarray | None":
    """
    Grava até detectar silêncio prolongado ou atingir o tempo máximo.
    Retorna array float32 mono ou None se não houver fala detectada.
    """
    audio_q: queue.Queue = queue.Queue()

    def _callback(indata, frames, time_info, status):
        audio_q.put(indata[:, 0].copy())  # mono

    blocos: list = []
    silence_count = 0
    speech_count = 0
    falando = False

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            blocksize=BLOCK_SIZE,
            dtype="float32",
            callback=_callback,
        ):
            for _ in range(MAX_RECORD_FRAMES + SILENCE_FRAMES):
                if _stop_event.is_set():
                    return None

                try:
                    bloco = audio_q.get(timeout=0.5)
                except queue.Empty:
                    continue

                rms = float(np.sqrt(np.mean(bloco ** 2)))

                if rms >= SILENCE_THRESHOLD:
                    falando = True
                    silence_count = 0
                    speech_count += 1
                    blocos.append(bloco)
                elif falando:
                    silence_count += 1
                    blocos.append(bloco)
                    if silence_count >= SILENCE_FRAMES:
                        break  # silêncio suficiente — processa

    except Exception as e:
        logger.warning(f"Erro ao gravar microfone: {e}")
        time.sleep(1)
        return None

    if not falando or speech_count < MIN_SPEECH_FRAMES:
        return None

    return np.concatenate(blocos)


# ── Notificação Telegram ──────────────────────────────────────────────────────

def _notificar_telegram(texto: str, resultado: str):
    if not (_loop and _bot and _chat_id):
        return

    async def _send():
        try:
            await _bot.send_message(
                chat_id=_chat_id,
                text=f"🎙️ _Voz:_ {texto}\n\n{resultado}",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning(f"Falha ao notificar Telegram: {e}")

    asyncio.run_coroutine_threadsafe(_send(), _loop)

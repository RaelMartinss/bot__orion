"""
utils/mic_listener.py
Escuta o microfone em background via sounddevice e executa comandos por voz.
Envia notificação ao Telegram após cada comando executado.
"""

import asyncio
import difflib
import logging
import queue
import threading
import time
from collections import deque
import unicodedata

import numpy as np
from utils import interface_bridge

logger = logging.getLogger(__name__)

WAKE_WORD = "orion"         # palavra de ativação (lowercase)
SAMPLE_RATE = 16000
BLOCK_MS = 30
BLOCK_SIZE = int(SAMPLE_RATE * (BLOCK_MS / 1000))
SILENCE_THRESHOLD = 0.015   # RMS mínimo para considerar fala
SILENCE_FRAMES = 22         # blocos de silêncio antes de parar
MAX_RECORD_FRAMES = 330     # blocos máximos por gravação
MIN_SPEECH_FRAMES = 6       # blocos mínimos de fala para processar
PRE_ROLL_FRAMES = 8         # guarda ~240ms antes da fala começar

# Estado compartilhado
_chat_id: int | None = None
_bot = None
_loop: asyncio.AbstractEventLoop | None = None
_stop_event = threading.Event()
_thread: threading.Thread | None = None
_user_id: int = 0  # Preenchido via main.py ou automaticamente


def configure(loop: asyncio.AbstractEventLoop, bot):
    """Deve ser chamado antes de iniciar(), com o loop e bot do PTB."""
    global _loop, _bot
    _loop = loop
    _bot = bot


def update_chat_id(chat_id: int, user_id: int = 0):
    """Atualiza o chat_id e user_id para contexto e notificações."""
    global _chat_id, _user_id
    _chat_id = chat_id
    if user_id:
        _user_id = user_id


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

    try:
        from silero_vad import load_silero_vad, get_speech_timestamps
        import torch
        _silero_model = load_silero_vad()
        vad = ("silero", _silero_model)
        logger.info("🎙️ Silero VAD ativo.")
    except Exception as e:
        vad = None
        logger.debug("Silero VAD não disponível (%s). Usando fallback por RMS.", e)

    from utils.transcriber import transcrever_numpy
    from utils.intent_parser import parse_intent
    from utils.executor import executar_intent
    from ml.intent_model import interpretar_comando

    logger.info("🎙️ Aguardando comandos de voz no microfone...")

    while not _stop_event.is_set():
        audio = _gravar_ate_silencio(sd, vad)
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

        logger.info(f"🎙️ Wake word detectada! Comando: '{comando}'")
        interface_bridge.emit_state_sync("ouvindo", f"Comando detectado: {comando[:120]}")

        intent = parse_intent(comando)

        _parece_comando = len(comando) >= 6
        _BROWSER_RE = (
            r'\b(site|web|internet|pesquisa|pesquisar|google)\b'
            r'|\b(abr[ae]|abrir)\b.{0,20}\b(site|página|pagina|url|link)\b'
            r'|\b(acessa|acessar|entra em|entrar em|vai em|vá em)\b'
            r'|\.com\b|\.com\.br\b|https?://'
        )
        import re as _re
        _parece_browser = bool(_re.search(_BROWSER_RE, comando.lower()))

        if intent.get("action") == "desconhecido" and _parece_comando and not _parece_browser:
            ml_intent = interpretar_comando(comando)
            if ml_intent:
                intent = ml_intent

        if intent.get("action") == "desconhecido" and _parece_comando and not _parece_browser:
            from utils.claude_client import extrair_intent_estruturado
            import asyncio as _asyncio
            try:
                structured = _asyncio.run_coroutine_threadsafe(
                    extrair_intent_estruturado(comando), _loop
                ).result(timeout=5)
                if structured and structured.get("action") not in ("desconhecido", "conversa", None):
                    intent = structured
            except Exception:
                pass

        if intent.get("action") != "desconhecido":
            resultado = executar_intent(intent)
            logger.info(f"🎙️ Execução local direta: {intent.get('action')} -> {resultado}")
            interface_bridge.emit_state_sync("falando", resultado[:160])
            _processar_resposta_local_async(comando, resultado)
            continue
        
        # Execução Inteligente (Jarvis Mode)
        _processar_comando_async(comando)


def _processar_resposta_local_async(comando: str, resposta: str):
    """Fala e notifica resultados locais sem envolver o orquestrador."""
    if not _loop:
        return

    async def _task():
        from utils.tts_manager import gerar_audio, reproduzir_local, limpar_audio

        audio_path = await gerar_audio(resposta)
        if audio_path:
            try:
                reproduzir_local(audio_path, wait=True)
            finally:
                limpar_audio(audio_path)

        _notificar_telegram(comando, resposta)
        await interface_bridge.emit_state("idle", "Sistema em espera.")

    asyncio.run_coroutine_threadsafe(_task(), _loop)


def _processar_comando_async(comando: str):
    """Encapsula a lógica assíncrona para ser chamada de uma thread."""
    if not _loop:
        return

    async def _task():
        from utils.orchestrator import run_orchestrator, try_local_route
        from utils.memoria import carregar_historico, persistir_historico
        from utils.tts_manager import gerar_audio, reproduzir_local, limpar_audio

        async def notificar_imediato_mic(msg_texto: str):
            """Callback para falar imediatamente via speakers."""
            logger.info(f"🎙️ Notificação Imediata (Mic): {msg_texto}")
            a_path = await gerar_audio(msg_texto)
            if a_path:
                try:
                    reproduzir_local(a_path, wait=True)
                finally:
                    limpar_audio(a_path)

        # 1. Carrega o contexto (memória curto prazo)
        historico = carregar_historico(_user_id)
        await interface_bridge.emit_state("pensando", f"Processando áudio: {comando[:120]}")

        # 1.5. Tenta rota local determinística antes de chamar a IA
        local_result = try_local_route(comando)
        if local_result is not None:
            logger.info(f"🎙️ Rota local aplicada no mic para comando: {comando}")
            await interface_bridge.emit_state("falando", local_result[:160])
            audio_path = await gerar_audio(local_result)
            if audio_path:
                try:
                    reproduzir_local(audio_path, wait=True)
                finally:
                    limpar_audio(audio_path)
            _notificar_telegram(comando, local_result)
            await interface_bridge.emit_state("idle", "Sistema em espera.")
            return

        # 2. Chama o "Cérebro" (Claude) passando o callback de voz imediato
        result = await run_orchestrator(
            comando, 
            chat_history=historico, 
            user_id=_user_id, 
            is_mic=True,
            notifier_callback=notificar_imediato_mic
        )
        
        resposta = result.get("response", "")
        # Se Claude não usou a tool de notificação imediata, fala a resposta final aqui
        if resposta and "Tarefas finalizadas" not in resposta:
            logger.info(f"🎙️ Resposta Final (Mic): {resposta}")
            await interface_bridge.emit_state("falando", resposta[:160])
            audio_path = await gerar_audio(resposta)
            if audio_path:
                try:
                    reproduzir_local(audio_path, wait=True)
                finally:
                    limpar_audio(audio_path)
            
            # Notifica o Telegram
            _notificar_telegram(comando, resposta)
        await interface_bridge.emit_state("idle", "Sistema em espera.")

        # 5. Salva no histórico persistente
        if "new_history" in result:
            persistir_historico(_user_id, result["new_history"])

    asyncio.run_coroutine_threadsafe(_task(), _loop)


def _extrair_comando(texto: str) -> str | None:
    """
    Verifica se o texto começa com a wake word 'orion' e retorna o restante.
    Aceita variações de transcrição: 'órion', 'oryon', 'oron', etc.
    Retorna None se a wake word não estiver presente.
    """
    import re
    t = texto.strip()
    t = re.sub(r'^[,.\s]+', '', t)
    if not t:
        return None

    tokens = t.split(maxsplit=1)
    primeiro = tokens[0].strip(" ,.;:!?").lower()
    primeiro_norm = _normalizar_wake_token(primeiro)

    variacoes = {
        "orion", "oryon", "orin", "oron", "oriao", "oriaum", "orio",
        "oreo", "oreo", "oreum", "oreon", "oreo", "audio", "olho",
        "horeo", "horeum", "horion", "aurion",
    }

    matchou = primeiro_norm in variacoes
    if not matchou:
        similares = difflib.get_close_matches(primeiro_norm, list(variacoes), n=1, cutoff=0.72)
        matchou = bool(similares)

    if not matchou:
        return None

    restante = tokens[1].strip() if len(tokens) > 1 else ""
    return restante or None


def _normalizar_wake_token(token: str) -> str:
    token = unicodedata.normalize("NFD", token)
    token = "".join(ch for ch in token if unicodedata.category(ch) != "Mn")
    token = "".join(ch for ch in token if ch.isalnum())
    return token.lower()


def _bloco_tem_fala(bloco: np.ndarray, vad) -> bool:
    """Decide se o bloco contém fala usando Silero VAD com fallback RMS."""
    if vad is not None and isinstance(vad, tuple) and vad[0] == "silero":
        try:
            import torch
            modelo = vad[1]
            tensor = torch.from_numpy(bloco).float()
            confianca = modelo(tensor, SAMPLE_RATE).item()
            return confianca >= 0.5
        except Exception:
            logger.debug("Falha no Silero VAD; usando fallback RMS.", exc_info=True)

    rms = float(np.sqrt(np.mean(bloco ** 2)))
    return rms >= SILENCE_THRESHOLD


def _gravar_ate_silencio(sd, vad=None) -> "np.ndarray | None":
    """
    Grava até detectar silêncio prolongado ou atingir o tempo máximo.
    Retorna array float32 mono ou None se não houver fala detectada.
    """
    audio_q: queue.Queue = queue.Queue()

    def _callback(indata, frames, time_info, status):
        audio_q.put(indata[:, 0].copy())  # mono

    blocos: list = []
    pre_roll: deque = deque(maxlen=PRE_ROLL_FRAMES)
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

                pre_roll.append(bloco)

                if _bloco_tem_fala(bloco, vad):
                    if not falando:
                        falando = True
                        blocos.extend(list(pre_roll))
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
            # Envia mensagem silenciosa (sem som/notificação no celular)
            # para logar a atividade do PC sem poluir o chat principal
            await _bot.send_message(
                chat_id=_chat_id,
                text=f"🖥️ _Log Mic-Local_:\n> {texto}\n\n{resultado}",
                parse_mode="Markdown",
                disable_notification=True
            )
        except Exception as e:
            logger.warning(f"Falha ao notificar Telegram: {e}")

    asyncio.run_coroutine_threadsafe(_send(), _loop)

import edge_tts
import asyncio
import os
import uuid
import logging
import time
import re
import unicodedata

logger = logging.getLogger(__name__)

# Configuração Padrão
DEFAULT_VOICE = "pt-BR-AntonioNeural" # Voz masculina elegante
TEMP_DIR = "temp_audio"


def limpar_texto_para_tts(texto: str) -> str:
    """
    Remove marcações visuais e caracteres decorativos para a fala soar natural.
    """
    if not texto:
        return ""

    texto_limpo = texto

    # Remove markdown comum usado no Telegram.
    texto_limpo = re.sub(r"[*_`~#>\[\]\(\)]", "", texto_limpo)

    # Remove labels técnicas/logs que ficam estranhas em voz.
    texto_limpo = re.sub(r"\b(?:INFO|DEBUG|WARNING|ERROR)\b:?", "", texto_limpo, flags=re.IGNORECASE)

    # Remove emojis e símbolos decorativos.
    filtrado = []
    for ch in texto_limpo:
        categoria = unicodedata.category(ch)
        if categoria == "So":
            continue
        if ch in {"⚡", "🎙", "🎙️", "💻", "🇧", "🇷", "🌿", "😄", "✅", "❌", "🤖", "🔊", "🔇", "▶", "🎵", "🎬", "🖥"}:
            continue
        filtrado.append(ch)
    texto_limpo = "".join(filtrado)

    # Colapsa espaços e linhas demais.
    texto_limpo = texto_limpo.replace("\r", "\n")
    texto_limpo = re.sub(r"\n{2,}", ". ", texto_limpo)
    texto_limpo = re.sub(r"\s{2,}", " ", texto_limpo)

    return texto_limpo.strip()

async def gerar_audio(texto: str, voice: str = DEFAULT_VOICE) -> str:
    """
    Converte o texto em áudio usando Edge-TTS (formato MP3 para PC).
    Retorna o caminho do arquivo .mp3 gerado.
    """
    if not os.path.exists(TEMP_DIR):
        os.makedirs(TEMP_DIR)
        
    filename = f"{uuid.uuid4()}.mp3"
    filepath = os.path.join(TEMP_DIR, filename)
    
    try:
        texto_limpo = limpar_texto_para_tts(texto)
        if not texto_limpo:
            logger.warning("Texto vazio após limpeza para TTS.")
            return None
        
        communicate = edge_tts.Communicate(texto_limpo, voice)
        await communicate.save(filepath)
        return filepath
    except Exception as e:
        logger.error(f"Erro ao gerar áudio com Edge-TTS: {e}")
        return None

def reproduzir_local(filepath: str, wait: bool = True):
    """
    Reproduz o arquivo de áudio nos speakers do PC usando playsound.
    """
    try:
        from playsound import playsound
        abs_path = os.path.abspath(filepath)
        logger.info(f"🔊 Iniciando reprodução local: {abs_path}")
        
        # playsound 1.2.2 no Windows é síncrono por padrão se block=True
        playsound(abs_path, block=wait)
        
        logger.info("🔊 Reprodução concluída.")
    except Exception as e:
        logger.error(f"Erro ao reproduzir áudio localmente via playsound: {e}")

def limpar_audio(filepath: str):
    """Remove o arquivo de áudio temporário."""
    try:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
    except Exception as e:
        logger.error(f"Erro ao deletar áudio temporário {filepath}: {e}")

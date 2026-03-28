import edge_tts
import asyncio
import os
import uuid
import logging
import time

logger = logging.getLogger(__name__)

# Configuração Padrão
DEFAULT_VOICE = "pt-BR-AntonioNeural" # Voz masculina elegante
TEMP_DIR = "temp_audio"

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
        # Limpa o texto de marcações Markdown que podem confundir o TTS
        texto_limpo = texto.replace("*", "").replace("_", "").replace("`", "")
        
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

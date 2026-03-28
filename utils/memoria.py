import json
import os
import logging

logger = logging.getLogger(__name__)

MEM_DIR = "memoria"

def _get_path(user_id, tipo):
    """tipo: 'curto' ou 'longo'"""
    if not os.path.exists(MEM_DIR):
        os.makedirs(MEM_DIR)
    return os.path.join(MEM_DIR, f"{tipo}_prazo_{user_id}.json")

def carregar_historico(user_id, max_msgs=20):
    """Carrega as últimas mensagens persistidas."""
    path = _get_path(user_id, 'curto')
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            hist = json.load(f)
            return hist[-max_msgs:]
    except Exception as e:
        logger.error(f"Erro ao carregar historico {user_id}: {e}")
        return []

def persistir_historico(user_id, messages):
    """Salva o histórico atual em disco."""
    path = _get_path(user_id, 'curto')
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(messages[-20:], f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Erro ao persistir historico {user_id}: {e}")

def carregar_memoria_longa(user_id):
    """Carrega o dicionário de memória (fatos e preferências) do usuário."""
    path = _get_path(user_id, 'longo')
    if not os.path.exists(path):
        return {"fatos": [], "preferencias": {}}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Garante estrutura mínima
            if isinstance(data, list): # Migração de formato antigo
                return {"fatos": data, "preferencias": {}}
            return data
    except Exception as e:
        logger.error(f"Erro ao carregar memoria longa {user_id}: {e}")
        return {"fatos": [], "preferencias": {}}

def salvar_fato(user_id, fato):
    """Adiciona um novo fato à lista de fatos na memória."""
    mem = carregar_memoria_longa(user_id)
    if fato not in mem["fatos"]:
        mem["fatos"].append(fato)
        path = _get_path(user_id, 'longo')
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(mem, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Erro ao salvar fato {user_id}: {e}")
    return False

def salvar_preferencia(user_id, chave, valor):
    """Salva ou atualiza uma preferência específica (ex: voice_active=True)."""
    mem = carregar_memoria_longa(user_id)
    mem["preferencias"][chave] = valor
    path = _get_path(user_id, 'longo')
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(mem, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar preferencia {user_id}: {e}")
    return False

"""
plugins/files/indexer.py
Indexador de arquivos do Orion.

Mantém um índice JSON em memoria/file_index.json para buscas rápidas,
evitando varrer o C:/ inteiro a cada comando.

Uso:
    from plugins.files.indexer import reindexar, buscar_no_indice
    reindexar()                         # reconstrói o índice em background
    resultados = buscar_no_indice("contrato")
"""

import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Configuração ──────────────────────────────────────────────────────────────

INDEX_PATH = os.path.join("memoria", "file_index.json")

# Fallback estático — usado quando o environment_map.json ainda não existe
_HOME = os.path.expanduser("~")
_PASTAS_FALLBACK = [
    os.path.join(_HOME, "Desktop"),
    os.path.join(_HOME, "Documents"),
    os.path.join(_HOME, "Downloads"),
    os.path.join(_HOME, "OneDrive"),
    os.path.join(_HOME, "OneDrive - Personal"),
]


def _get_pastas_indexadas() -> list[str]:
    """
    Retorna a lista de pastas a indexar.
    Prioridade: folders do environment_map.json > fallback estático.
    """
    try:
        from env_loader import PASTAS as _ep
        pastas = [
            path for path in _ep.values()
            if isinstance(path, str) and os.path.isdir(path)
        ]
        if pastas:
            return pastas
    except Exception:
        pass
    return [p for p in _PASTAS_FALLBACK if os.path.isdir(p)]

# Extensões de interesse (ignora executáveis, dlls, arquivos de sistema)
EXTENSOES_INTERES = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
    ".txt", ".csv", ".json", ".xml", ".md",
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".mp4", ".mp3", ".zip", ".rar", ".7z",
    ".py", ".js", ".ts", ".html", ".css",
}

# Pastas a ignorar completamente
PASTAS_IGNORADAS = {
    ".git", ".venv", "node_modules", "__pycache__", ".vscode",
    "AppData", "WindowsApps", "Temp", "temp",
}

# Reindexar automaticamente após N horas de índice antigo
REINDEX_APOS_HORAS = 12


# ── Estado interno ────────────────────────────────────────────────────────────

_indice: dict = {}         # {nome_arquivo: {path, size, modified, ext}}
_indice_carregado = False
_lock = threading.Lock()


# ── Funções públicas ──────────────────────────────────────────────────────────

def carregar_indice() -> dict:
    """Carrega o índice do disco. Reindexar se estiver desatualizado."""
    global _indice, _indice_carregado

    if _indice_carregado:
        return _indice

    if os.path.exists(INDEX_PATH):
        try:
            with open(INDEX_PATH, "r", encoding="utf-8") as f:
                dados = json.load(f)
            _indice = dados.get("arquivos", {})
            ultima_atualizacao = dados.get("atualizado_em", "")
            logger.info(f"📂 Índice carregado: {len(_indice)} arquivos (atualizado: {ultima_atualizacao})")

            # Verifica se precisa reindexar em background
            if ultima_atualizacao:
                try:
                    dt = datetime.fromisoformat(ultima_atualizacao)
                    if datetime.now() - dt > timedelta(hours=REINDEX_APOS_HORAS):
                        logger.info("🔄 Índice antigo — reindexando em background...")
                        threading.Thread(target=_reindexar_interno, daemon=True, name="orion-indexer").start()
                except Exception:
                    pass

            _indice_carregado = True
            return _indice
        except Exception as e:
            logger.warning(f"Erro ao carregar índice: {e}")

    # Índice não existe → cria em background
    logger.info("📂 Nenhum índice encontrado — criando em background...")
    threading.Thread(target=_reindexar_interno, daemon=True, name="orion-indexer-init").start()
    _indice_carregado = True
    return _indice


def reindexar():
    """Reconstrói o índice em uma thread de background."""
    threading.Thread(target=_reindexar_interno, daemon=True, name="orion-indexer-manual").start()
    return "🔄 Reindexando arquivos em background... (pode levar alguns minutos)"


def buscar_no_indice(termo: str, tipo: str | None = None) -> list[dict]:
    """
    Busca no índice por nome de arquivo.
    Retorna lista de dicts: [{path, nome, ext, size, modified, score}]
    """
    indice = carregar_indice()
    termo_lower = termo.lower().strip()
    palavras = termo_lower.split()
    resultados = []

    for nome, meta in indice.items():
        nome_lower = nome.lower()
        path = meta.get("path", "")
        ext = meta.get("ext", "")

        # Filtro de tipo
        if tipo and not ext.endswith(tipo.lstrip(".")):
            continue

        # Calcula score
        score = 0
        for palavra in palavras:
            if palavra in nome_lower:
                score += 3 if nome_lower.startswith(palavra) else 1
        # Bonus se estiver em pasta relevante (não em subpastas profundas)
        if path.count(os.sep) < 6:
            score += 1

        if score > 0:
            resultados.append({
                "path": path,
                "nome": nome,
                "ext": ext,
                "size": meta.get("size", 0),
                "modified": meta.get("modified", ""),
                "score": score,
            })

    # Ordena por score decrescente, depois por data de modificação
    resultados.sort(key=lambda x: (x["score"], x["modified"]), reverse=True)
    return resultados[:10]


def status_indice() -> str:
    """Retorna um resumo do estado do índice."""
    if not os.path.exists(INDEX_PATH):
        return "⚠️ Índice ainda não criado. Diga _reindexar arquivos_ para criar."
    try:
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            dados = json.load(f)
        total = len(dados.get("arquivos", {}))
        atualizado = dados.get("atualizado_em", "desconhecido")
        return f"📂 Índice: *{total} arquivos* indexados\n🕐 Última atualização: {atualizado}"
    except Exception as e:
        return f"❌ Erro ao ler índice: {e}"


# ── Internos ──────────────────────────────────────────────────────────────────

def _reindexar_interno():
    """Varre as pastas e salva o índice no disco."""
    global _indice

    logger.info("🔍 Iniciando indexação de arquivos...")
    inicio = time.time()
    novo_indice = {}
    total = 0

    pastas = _get_pastas_indexadas()
    logger.info(f"📁 Indexando {len(pastas)} pasta(s): {pastas}")
    for raiz in pastas:
        if not os.path.isdir(raiz):
            continue
        for dirpath, dirnames, filenames in os.walk(raiz):
            # Remove pastas ignoradas in-place (evita descender nelas)
            dirnames[:] = [
                d for d in dirnames
                if d not in PASTAS_IGNORADAS and not d.startswith(".")
            ]
            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in EXTENSOES_INTERES:
                    continue
                try:
                    fpath = os.path.join(dirpath, fname)
                    stat = os.stat(fpath)
                    novo_indice[fname] = {
                        "path": fpath,
                        "ext": ext,
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    }
                    total += 1
                except (PermissionError, OSError):
                    continue

    dados = {
        "arquivos": novo_indice,
        "atualizado_em": datetime.now().isoformat(),
        "total": total,
    }

    os.makedirs("memoria", exist_ok=True)
    with _lock:
        with open(INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        _indice = novo_indice

    elapsed = round(time.time() - inicio, 1)
    logger.info(f"✅ Indexação concluída: {total} arquivos em {elapsed}s")

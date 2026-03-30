"""
plugins/files/search.py
Busca contextual de arquivos para o Orion.

Suporta:
  - Busca por nome/contexto: "contrato", "planilha de estoque"
  - Filtro de tipo: "pdf do contrato", "planilha de vendas"
  - Filtro de data: "de ontem", "de março", "da semana passada"

Uso:
    from plugins.files.search import buscar_arquivo
    resultado = buscar_arquivo("contrato", tipo="pdf", data_ref="março")
"""

import logging
import os
import re
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Mapeamento de palavras de tipo → extensões
_TIPO_EXTENSOES: dict[str, list[str]] = {
    "pdf":        [".pdf"],
    "planilha":   [".xlsx", ".xls", ".csv"],
    "excel":      [".xlsx", ".xls"],
    "word":       [".docx", ".doc"],
    "documento":  [".docx", ".doc", ".pdf"],
    "imagem":     [".jpg", ".jpeg", ".png", ".gif", ".webp"],
    "foto":       [".jpg", ".jpeg", ".png"],
    "video":      [".mp4", ".avi", ".mov", ".mkv"],
    "audio":      [".mp3", ".wav", ".ogg"],
    "zip":        [".zip", ".rar", ".7z"],
    "texto":      [".txt", ".md"],
    "apresentacao": [".pptx", ".ppt"],
    "script":     [".py", ".js", ".ts", ".sh", ".bat"],
}

# Pastas prioritárias para fallback os.walk (quando não está no índice)
_HOME = os.path.expanduser("~")
_PASTAS_FALLBACK = [
    os.path.join(_HOME, "Downloads"),
    os.path.join(_HOME, "Desktop"),
    os.path.join(_HOME, "Documents"),
    os.path.join(_HOME, "OneDrive"),
    os.path.join(_HOME, "OneDrive - Personal"),
]


def buscar_arquivo(
    query: str,
    tipo: str | None = None,
    data_ref: str | None = None,
) -> str:
    """
    Busca arquivos por contexto e retorna mensagem formatada para o Telegram.

    Args:
        query:    Termo de busca em linguagem natural (ex: "contrato fornecedora")
        tipo:     Tipo de arquivo em PT (ex: "pdf", "planilha") — opcional
        data_ref: Referência de data (ex: "ontem", "março", "semana passada") — opcional
    """
    from plugins.files.indexer import buscar_no_indice, carregar_indice

    # Resolve extensões a filtrar
    extensoes_filtro = _resolver_extensoes(tipo) if tipo else None

    # Resolve filtro de data
    filtro_data = _resolver_data(data_ref) if data_ref else None

    # Carrega índice (lazy, cria em background se não existir)
    carregar_indice()

    # Tenta primeiro no índice
    resultados = buscar_no_indice(query, tipo=tipo)

    # Aplica filtro de data
    if filtro_data and resultados:
        resultados = [
            r for r in resultados
            if _arquivo_dentro_periodo(r.get("modified", ""), filtro_data)
        ]

    # Aplica filtro de extensão
    if extensoes_filtro and resultados:
        resultados = [
            r for r in resultados
            if r.get("ext", "") in extensoes_filtro
        ]

    # Fallback: os.walk nas pastas prioritárias
    if not resultados:
        resultados = _busca_fallback(query, extensoes_filtro, filtro_data)

    if not resultados:
        dica = f" do tipo {tipo}" if tipo else ""
        dica_data = f" de {data_ref}" if data_ref else ""
        return (
            f"🔍 Não encontrei nenhum arquivo{dica}{dica_data} com *{query}* no nome.\n\n"
            f"💡 Dica: diga _reindexar arquivos_ para atualizar o índice de busca."
        )

    # Monta a resposta
    linhas = [f"🔍 Encontrei {len(resultados)} resultado(s) para *{query}*:\n"]
    for i, r in enumerate(resultados[:5], 1):
        nome = r["nome"]
        pasta = os.path.dirname(r["path"])
        pasta_curta = _encurtar_caminho(pasta)
        tamanho = _formatar_tamanho(r.get("size", 0))
        data = _formatar_data(r.get("modified", ""))
        linhas.append(f"*{i}.* 📄 `{nome}`")
        linhas.append(f"   📁 {pasta_curta}")
        linhas.append(f"   📅 {data} · {tamanho}")
    linhas.append("\n💡 Para abrir: _abre o arquivo [nome]_")
    return "\n".join(linhas)


def abrir_arquivo_por_nome(query: str) -> str:
    """Localiza um arquivo pelo nome/contexto e o abre."""
    from plugins.files.indexer import buscar_no_indice, carregar_indice

    carregar_indice()
    resultados = buscar_no_indice(query)

    if not resultados:
        resultados = _busca_fallback(query, None, None)

    if not resultados:
        return f"❌ Arquivo *{query}* não encontrado."

    melhor = resultados[0]
    try:
        os.startfile(melhor["path"])
        return f"📄 Abrindo *{melhor['nome']}*...\n📁 `{_encurtar_caminho(os.path.dirname(melhor['path']))}`"
    except Exception as e:
        return f"❌ Erro ao abrir *{melhor['nome']}*: {e}"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolver_extensoes(tipo: str) -> list[str] | None:
    """Converte nome de tipo em lista de extensões."""
    tipo_lower = tipo.lower().strip()
    for chave, exts in _TIPO_EXTENSOES.items():
        if chave in tipo_lower or tipo_lower in chave:
            return exts
    # Tenta diretamente como extensão: "pdf" → ".pdf"
    ext = tipo_lower if tipo_lower.startswith(".") else f".{tipo_lower}"
    return [ext]


def _resolver_data(data_ref: str) -> dict | None:
    """
    Converte referência de data em {desde, ate}.
    Ex: "ontem" → {desde: datetime(ontem 00:00), ate: datetime(ontem 23:59)}
    """
    agora = datetime.now()
    ref = data_ref.lower().strip()

    if "hoje" in ref:
        desde = agora.replace(hour=0, minute=0, second=0, microsecond=0)
        return {"desde": desde, "ate": agora}

    if "ontem" in ref:
        ontem = agora - timedelta(days=1)
        desde = ontem.replace(hour=0, minute=0, second=0, microsecond=0)
        ate = ontem.replace(hour=23, minute=59, second=59)
        return {"desde": desde, "ate": ate}

    if "semana passada" in ref or "semana anterior" in ref:
        inicio_semana = agora - timedelta(days=agora.weekday() + 7)
        fim_semana = inicio_semana + timedelta(days=6)
        return {"desde": inicio_semana.replace(hour=0, minute=0, second=0), "ate": fim_semana.replace(hour=23, minute=59)}

    if "essa semana" in ref or "esta semana" in ref:
        inicio = agora - timedelta(days=agora.weekday())
        return {"desde": inicio.replace(hour=0, minute=0, second=0), "ate": agora}

    if "mês passado" in ref or "mes passado" in ref:
        primeiro_dia = agora.replace(day=1) - timedelta(days=1)
        desde = primeiro_dia.replace(day=1, hour=0, minute=0, second=0)
        return {"desde": desde, "ate": primeiro_dia.replace(hour=23, minute=59)}

    # Mês por nome: "janeiro", "fevereiro"... / "março" etc.
    _MESES = {
        "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3,
        "abril": 4, "maio": 5, "junho": 6,
        "julho": 7, "agosto": 8, "setembro": 9,
        "outubro": 10, "novembro": 11, "dezembro": 12,
    }
    for nome_mes, num_mes in _MESES.items():
        if nome_mes in ref:
            ano = agora.year if num_mes <= agora.month else agora.year - 1
            desde = datetime(ano, num_mes, 1)
            # Último dia do mês
            if num_mes == 12:
                ate = datetime(ano + 1, 1, 1) - timedelta(seconds=1)
            else:
                ate = datetime(ano, num_mes + 1, 1) - timedelta(seconds=1)
            return {"desde": desde, "ate": ate}

    return None


def _arquivo_dentro_periodo(modified_iso: str, filtro: dict) -> bool:
    """Verifica se a data de modificação do arquivo está dentro do período."""
    if not modified_iso:
        return True
    try:
        dt = datetime.fromisoformat(modified_iso)
        return filtro["desde"] <= dt <= filtro["ate"]
    except Exception:
        return True


def _busca_fallback(
    query: str,
    extensoes: list[str] | None,
    filtro_data: dict | None,
) -> list[dict]:
    """os.walk nas pastas prioritárias — fallback quando o índice não tem resultado."""
    palavras = query.lower().split()
    resultados = []

    for pasta in _PASTAS_FALLBACK:
        if not os.path.isdir(pasta):
            continue
        for dirpath, dirnames, filenames in os.walk(pasta):
            # Não desce muito fundo: máximo 3 níveis
            nivel = dirpath.replace(pasta, "").count(os.sep)
            if nivel > 3:
                dirnames.clear()
                continue
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]

            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if extensoes and ext not in extensoes:
                    continue
                nome_lower = fname.lower()
                score = sum(1 for p in palavras if p in nome_lower)
                if score == 0:
                    continue
                try:
                    fpath = os.path.join(dirpath, fname)
                    stat = os.stat(fpath)
                    modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
                    if filtro_data and not _arquivo_dentro_periodo(modified, filtro_data):
                        continue
                    resultados.append({
                        "path": fpath,
                        "nome": fname,
                        "ext": ext,
                        "size": stat.st_size,
                        "modified": modified,
                        "score": score,
                    })
                except (PermissionError, OSError):
                    continue

    resultados.sort(key=lambda x: (x["score"], x["modified"]), reverse=True)
    return resultados[:10]


def _encurtar_caminho(path: str) -> str:
    """Substitui o diretório home por ~ para exibição compacta."""
    home = os.path.expanduser("~")
    if path.startswith(home):
        return "~" + path[len(home):]
    return path


def _formatar_tamanho(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / 1024 ** 2:.1f} MB"


def _formatar_data(iso: str) -> str:
    if not iso:
        return "data desconhecida"
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return iso

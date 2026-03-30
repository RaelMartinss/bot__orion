"""
plugins/files/organize.py
Organização automática de arquivos para o Orion.

Funcionalidades:
  - organizar_downloads()     → move arquivos por tipo (PDF, imagens, etc.)
  - organizar_por_mes(pasta)  → move arquivos para subpastas AAAA-MM
  - listar_downloads()        → lista o que está na pasta Downloads
  - renomear_inteligente()    → (futuro) renomeia com padrão legível

Modo dry-run: por padrão, apenas SIMULA as ações e retorna o que faria.
Passe confirmar=True para executar de verdade.

Uso:
    from plugins.files.organize import organizar_downloads
    resultado = organizar_downloads()              # simula
    resultado = organizar_downloads(confirmar=True) # executa
"""

import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_HOME = os.path.expanduser("~")
DOWNLOADS = os.path.join(_HOME, "Downloads")

# ── Regras de organização por extensão ───────────────────────────────────────
# Formato: extensão → nome da subpasta de destino
REGRAS_TIPO: dict[str, str] = {
    # Documentos
    ".pdf":   "PDFs",
    ".docx":  "Word",
    ".doc":   "Word",
    ".xlsx":  "Planilhas",
    ".xls":   "Planilhas",
    ".csv":   "Planilhas",
    ".pptx":  "Apresentações",
    ".ppt":   "Apresentações",
    ".txt":   "Textos",
    ".md":    "Textos",

    # Imagens
    ".jpg":   "Imagens",
    ".jpeg":  "Imagens",
    ".png":   "Imagens",
    ".gif":   "Imagens",
    ".webp":  "Imagens",
    ".svg":   "Imagens",
    ".ico":   "Imagens",

    # Vídeos
    ".mp4":   "Vídeos",
    ".avi":   "Vídeos",
    ".mov":   "Vídeos",
    ".mkv":   "Vídeos",
    ".wmv":   "Vídeos",

    # Áudio
    ".mp3":   "Áudio",
    ".wav":   "Áudio",
    ".ogg":   "Áudio",
    ".flac":  "Áudio",

    # Compactados
    ".zip":   "Compactados",
    ".rar":   "Compactados",
    ".7z":    "Compactados",
    ".tar":   "Compactados",
    ".gz":    "Compactados",

    # Instaladores / executáveis
    ".exe":   "Instaladores",
    ".msi":   "Instaladores",
    ".dmg":   "Instaladores",

    # Código
    ".py":    "Código",
    ".js":    "Código",
    ".ts":    "Código",
    ".html":  "Código",
    ".css":   "Código",
    ".json":  "Código",
    ".xml":   "Código",
}


# ── Funções públicas ──────────────────────────────────────────────────────────

def organizar_downloads(confirmar: bool = False, pasta: str | None = None) -> str:
    """
    Organiza a pasta Downloads (ou outra pasta) por tipo de arquivo.

    Args:
        confirmar: False = apenas simula (dry-run); True = executa de verdade
        pasta:     Caminho alternativo (padrão: ~/Downloads)
    """
    alvo = pasta or DOWNLOADS
    if not os.path.isdir(alvo):
        return f"❌ Pasta não encontrada: `{alvo}`"

    acoes: list[tuple[str, str]] = []  # (origem, destino)
    ignorados: list[str] = []

    for entrada in os.scandir(alvo):
        if not entrada.is_file():
            continue
        ext = os.path.splitext(entrada.name)[1].lower()
        subpasta = REGRAS_TIPO.get(ext)
        if not subpasta:
            ignorados.append(entrada.name)
            continue
        destino_dir = os.path.join(alvo, subpasta)
        destino_arquivo = os.path.join(destino_dir, entrada.name)
        acoes.append((entrada.path, destino_arquivo))

    if not acoes:
        return (
            f"✅ A pasta *Downloads* já está organizada!\n"
            f"📊 {len(ignorados)} arquivo(s) sem regra de organização."
        )

    if not confirmar:
        # Dry-run: mostra o que seria feito
        linhas = [
            f"🗂️ *Simulação — o que seria organizado:*\n",
            f"📁 Pasta: `{alvo}`\n",
        ]
        por_subpasta: dict[str, list[str]] = {}
        for orig, dest in acoes:
            subpasta_nome = os.path.basename(os.path.dirname(dest))
            por_subpasta.setdefault(subpasta_nome, []).append(os.path.basename(orig))

        for subpasta_nome, arquivos in sorted(por_subpasta.items()):
            linhas.append(f"📂 *{subpasta_nome}/* ({len(arquivos)} arquivo(s))")
            for arq in arquivos[:5]:
                linhas.append(f"   • `{arq}`")
            if len(arquivos) > 5:
                linhas.append(f"   _... e mais {len(arquivos) - 5}_")

        if ignorados:
            linhas.append(f"\n⚪ {len(ignorados)} arquivo(s) sem regra (serão mantidos no lugar)")

        linhas.append(f"\n✅ Total: *{len(acoes)} arquivo(s)* serão movidos.")
        linhas.append("👉 Para executar de verdade, diga: _confirma organizar downloads_")
        return "\n".join(linhas)

    # Executa de verdade
    movidos = 0
    erros = []
    for orig, dest in acoes:
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            # Evita sobrescrever arquivo com mesmo nome
            dest_final = _resolver_conflito(dest)
            shutil.move(orig, dest_final)
            movidos += 1
        except Exception as e:
            logger.error(f"Erro ao mover {orig}: {e}")
            erros.append(os.path.basename(orig))

    linhas = [f"✅ *Downloads organizado!*\n"]
    linhas.append(f"📦 *{movidos}* arquivo(s) movido(s) para subpastas.")
    if erros:
        linhas.append(f"⚠️ Erros em {len(erros)} arquivo(s): {', '.join(erros[:3])}")
    if ignorados:
        linhas.append(f"⚪ {len(ignorados)} arquivo(s) mantido(s) no lugar (sem regra)")

    # Atualiza índice em background
    try:
        from plugins.files.indexer import reindexar
        reindexar()
    except Exception:
        pass

    return "\n".join(linhas)


def organizar_por_mes(pasta: str | None = None, confirmar: bool = False) -> str:
    """
    Move arquivos de uma pasta para subpastas por mês (AAAA-MM).

    Ex: arquivo de março/2025 vai para pasta/2025-03/

    Args:
        pasta:     Caminho da pasta (padrão: ~/Downloads)
        confirmar: False = simula; True = executa
    """
    alvo = pasta or DOWNLOADS
    if not os.path.isdir(alvo):
        return f"❌ Pasta não encontrada: `{alvo}`"

    acoes: list[tuple[str, str]] = []

    for entrada in os.scandir(alvo):
        if not entrada.is_file():
            continue
        try:
            mtime = os.path.getmtime(entrada.path)
            dt = datetime.fromtimestamp(mtime)
            nome_mes = dt.strftime("%Y-%m")
            destino_dir = os.path.join(alvo, nome_mes)
            destino_arquivo = os.path.join(destino_dir, entrada.name)
            acoes.append((entrada.path, destino_arquivo))
        except Exception:
            continue

    if not acoes:
        return "✅ Nenhum arquivo encontrado para organizar por mês."

    if not confirmar:
        # Contagem por mês
        por_mes: dict[str, int] = {}
        for _, dest in acoes:
            mes = os.path.basename(os.path.dirname(dest))
            por_mes[mes] = por_mes.get(mes, 0) + 1

        linhas = [f"📅 *Simulação — organizar por mês:*\n"]
        for mes in sorted(por_mes.keys(), reverse=True):
            linhas.append(f"📁 `{mes}/` → {por_mes[mes]} arquivo(s)")
        linhas.append(f"\n✅ Total: *{len(acoes)}* arquivo(s) serão movidos.")
        linhas.append("👉 Para executar: _confirma organizar por mês_")
        return "\n".join(linhas)

    # Executa
    movidos = 0
    for orig, dest in acoes:
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            dest_final = _resolver_conflito(dest)
            shutil.move(orig, dest_final)
            movidos += 1
        except Exception as e:
            logger.error(f"Erro ao mover {orig}: {e}")

    return f"✅ *{movidos}* arquivo(s) organizados por mês em `{alvo}`."


def listar_downloads(limite: int = 15) -> str:
    """Lista os arquivos mais recentes da pasta Downloads."""
    if not os.path.isdir(DOWNLOADS):
        return "❌ Pasta Downloads não encontrada."

    arquivos = []
    for entrada in os.scandir(DOWNLOADS):
        if not entrada.is_file():
            continue
        try:
            mtime = os.path.getmtime(entrada.path)
            size = os.path.getsize(entrada.path)
            arquivos.append((entrada.name, mtime, size))
        except Exception:
            continue

    if not arquivos:
        return "📥 Pasta Downloads está vazia."

    # Ordena por data de modificação, mais recente primeiro
    arquivos.sort(key=lambda x: x[1], reverse=True)

    linhas = [f"📥 *Downloads* ({len(arquivos)} arquivo(s) — mais recentes):\n"]
    for nome, mtime, size in arquivos[:limite]:
        dt = datetime.fromtimestamp(mtime).strftime("%d/%m %H:%M")
        ext = os.path.splitext(nome)[1].lower()
        emoji = _emoji_por_ext(ext)
        kb = f"{size / 1024:.0f} KB" if size < 1024 ** 2 else f"{size / 1024 ** 2:.1f} MB"
        linhas.append(f"{emoji} `{nome}` — {dt} · {kb}")

    if len(arquivos) > limite:
        linhas.append(f"\n_... e mais {len(arquivos) - limite} arquivo(s)_")

    return "\n".join(linhas)


# ── Helpers internos ──────────────────────────────────────────────────────────

def _resolver_conflito(destino: str) -> str:
    """Se o destino já existe, adiciona sufixo numérico ao nome."""
    if not os.path.exists(destino):
        return destino
    base, ext = os.path.splitext(destino)
    i = 1
    while os.path.exists(f"{base}_{i}{ext}"):
        i += 1
    return f"{base}_{i}{ext}"


def _emoji_por_ext(ext: str) -> str:
    mapa = {
        ".pdf": "📄", ".docx": "📝", ".doc": "📝",
        ".xlsx": "📊", ".xls": "📊", ".csv": "📊",
        ".jpg": "🖼️", ".jpeg": "🖼️", ".png": "🖼️",
        ".mp4": "🎬", ".avi": "🎬", ".mkv": "🎬",
        ".mp3": "🎵", ".wav": "🎵",
        ".zip": "📦", ".rar": "📦", ".7z": "📦",
        ".exe": "⚙️", ".msi": "⚙️",
        ".py": "🐍", ".js": "📜", ".ts": "📜",
    }
    return mapa.get(ext, "📎")

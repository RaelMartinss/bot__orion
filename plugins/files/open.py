"""
plugins/files/open.py
Abertura rápida de pastas e projetos para o Orion.

Projetos são carregados automaticamente do environment_map.json gerado
pelo discover.py (via env_loader). Edite _PROJETOS_LOCAL apenas como
fallback de emergência caso o mapa ainda não exista.

Uso:
    from plugins.files.open import abrir_pasta, abrir_arquivo
    abrir_pasta("downloads")
    abrir_pasta("pdv")        # alias de projeto
    abrir_arquivo("C:/docs/contrato.pdf")
"""

import logging
import os
import subprocess

logger = logging.getLogger(__name__)

_HOME = os.path.expanduser("~")


# ── Helpers que precisam existir antes dos dicts globais ─────────────────────

def _onedrive_path() -> str:
    """Detecta o caminho correto do OneDrive."""
    candidatos = [
        os.path.join(_HOME, "OneDrive"),
        os.path.join(_HOME, "OneDrive - Personal"),
        os.path.join(_HOME, "OneDrive - Empresarial"),
    ]
    for c in candidatos:
        if os.path.isdir(c):
            return c
    return os.path.join(_HOME, "OneDrive")  # fallback


# ── Pastas do sistema — aliases PT-BR ─────────────────────────────────────────
PASTAS_RAPIDAS: dict[str, str] = {
    # Downloads / Desktop / Documents
    "downloads":           os.path.join(_HOME, "Downloads"),
    "download":            os.path.join(_HOME, "Downloads"),
    "desktop":             os.path.join(_HOME, "Desktop"),
    "área de trabalho":    os.path.join(_HOME, "Desktop"),
    "area de trabalho":    os.path.join(_HOME, "Desktop"),
    "documentos":          os.path.join(_HOME, "Documents"),
    "documents":           os.path.join(_HOME, "Documents"),
    "imagens":             os.path.join(_HOME, "Pictures"),
    "fotos":               os.path.join(_HOME, "Pictures"),
    "pictures":            os.path.join(_HOME, "Pictures"),
    "videos":              os.path.join(_HOME, "Videos"),
    "musicas":             os.path.join(_HOME, "Music"),
    "músicas":             os.path.join(_HOME, "Music"),

    # OneDrive (verifica qual existe)
    "onedrive":            _onedrive_path(),

    # Raiz do disco
    "disco":               "C:\\",
    "c":                   "C:\\",
}

# ── Fallback local — usado se environment_map.json ainda não existir ──────────
# Adicione aqui projetos críticos que devem sempre funcionar.
_PROJETOS_LOCAL: dict[str, str] = {
    "orion": r"R:\orion_bot",
}

# ── Projetos dinâmicos via env_loader ─────────────────────────────────────────
# A variável PROJETOS aponta para o LazyDict do env_loader, que carrega
# o environment_map.json gerado pelo discover.py.
# Ela suporta .get(), __contains__, .items(), .keys(), .values() como um dict.
try:
    from env_loader import PROJETOS  # _LazyDict — carrega na primeira chamada
except ImportError:
    PROJETOS = _PROJETOS_LOCAL  # type: ignore[assignment]


def reload_projetos() -> str:
    """Recarrega o environment_map.json em runtime (após um re-scan do discover)."""
    try:
        from env_loader import get_env
        get_env().reload()
        return "✅ Mapa de projetos recarregado do environment_map.json."
    except Exception as e:
        logger.warning(f"Erro ao recarregar projetos: {e}")
        return f"⚠️ Não foi possível recarregar os projetos: {e}"


# ── Funções públicas ──────────────────────────────────────────────────────────

def abrir_pasta(alias: str) -> str:
    """
    Abre uma pasta pelo alias PT-BR.
    Ordem de busca:
      1. PASTAS_RAPIDAS (estático — pastas do sistema)
      2. env_loader.PROJETOS (dinâmico — environment_map.json)
      3. env_loader.PASTAS  (pastas especiais detectadas pelo discover)
      4. _PROJETOS_LOCAL    (fallback hardcoded de emergência)
      5. Busca parcial em tudo acima
    """
    alias_lower = _normalizar(alias)

    # 1. Pastas rápidas do sistema
    caminho = PASTAS_RAPIDAS.get(alias_lower)

    # 2. Projetos do environment_map
    if not caminho:
        try:
            caminho = PROJETOS.get(alias_lower)
        except Exception:
            pass

    # 3. Pastas especiais detectadas pelo discover (OneDrive, Quick Access, etc.)
    if not caminho:
        try:
            from env_loader import PASTAS as _ep
            caminho = _ep.get(alias_lower)
        except Exception:
            pass

    # 4. Fallback local hardcoded
    if not caminho:
        caminho = _PROJETOS_LOCAL.get(alias_lower)

    # 5. Busca parcial em tudo
    if not caminho:
        caminho = _busca_parcial(alias_lower)

    if not caminho:
        sugestoes = _sugerir_similares(alias_lower)
        msg = f"❌ Não encontrei a pasta *{alias}*."
        if sugestoes:
            msg += f"\n\n💡 Você quis dizer: {', '.join(f'`{s}`' for s in sugestoes)}?"
        return msg

    # Verifica existência / tenta alternativo
    if not os.path.isdir(caminho):
        alternativo = _tentar_alternativo(alias_lower, caminho)
        if alternativo:
            caminho = alternativo
        else:
            return f"❌ Pasta *{alias}* não existe em `{caminho}`."

    try:
        os.startfile(caminho)
        return f"📂 Abrindo *{alias}*...\n`{caminho}`"
    except Exception as e:
        logger.error(f"Erro ao abrir pasta {alias}: {e}")
        return f"❌ Erro ao abrir *{alias}*: {e}"


def abrir_arquivo(path: str) -> str:
    """Abre um arquivo pelo caminho absoluto."""
    if not os.path.exists(path):
        return f"❌ Arquivo não encontrado: `{path}`"
    try:
        os.startfile(path)
        nome = os.path.basename(path)
        return f"📄 Abrindo *{nome}*..."
    except Exception as e:
        logger.error(f"Erro ao abrir arquivo {path}: {e}")
        return f"❌ Erro ao abrir arquivo: {e}"


def abrir_pasta_no_explorer(path: str) -> str:
    """Abre uma pasta específica no Windows Explorer."""
    if not os.path.isdir(path):
        return f"❌ Pasta não encontrada: `{path}`"
    try:
        subprocess.Popen(["explorer", path])
        return f"📂 Explorer aberto em `{path}`"
    except Exception as e:
        return f"❌ Erro ao abrir Explorer: {e}"


def listar_projetos() -> str:
    """Lista os projetos disponíveis (do environment_map + fallback local)."""
    linhas = ["📂 *Projetos disponíveis:*\n"]

    # Projetos do environment_map
    try:
        items = list(PROJETOS.items())
        # Deduplica por caminho para não mostrar todos os aliases
        vistos: set[str] = set()
        for alias, path in items:
            if path in vistos:
                continue
            vistos.add(path)
            existe = "✅" if os.path.isdir(path) else "❌"
            linhas.append(f"{existe} `{alias}` → `{path}`")
    except Exception:
        pass

    # Fallback local (se não duplicar)
    for alias, path in _PROJETOS_LOCAL.items():
        if not any(alias in l for l in linhas):
            existe = "✅" if os.path.isdir(path) else "❌"
            linhas.append(f"{existe} `{alias}` → `{path}` _(local)_")

    if len(linhas) == 1:
        return (
            "📂 Nenhum projeto encontrado.\n"
            "Execute `python discover.py` para mapear seus projetos automaticamente."
        )
    return "\n".join(linhas)


def listar_pastas_rapidas() -> str:
    """Lista os aliases de pastas rápidas disponíveis."""
    vistos: set[str] = set()
    linhas = ["⚡ *Pastas rápidas disponíveis:*\n"]
    for alias, path in PASTAS_RAPIDAS.items():
        if path in vistos or not path:
            continue
        vistos.add(path)
        existe = "✅" if os.path.isdir(path) else "❌"
        linhas.append(f"{existe} `{alias}` → `{os.path.basename(path) or path}`")
    return "\n".join(linhas)


# ── Helpers internos ──────────────────────────────────────────────────────────


def _normalizar(texto: str) -> str:
    """Normaliza o alias removendo artigos e espaços extras."""
    t = texto.lower().strip()
    t = t.removeprefix("a ").removeprefix("o ").removeprefix("as ").removeprefix("os ")
    t = t.removeprefix("pasta de ").removeprefix("pasta do ").removeprefix("pasta da ")
    t = t.removeprefix("projeto do ").removeprefix("projeto de ").removeprefix("projeto ")
    t = t.removeprefix("de ").removeprefix("do ").removeprefix("da ")
    return t.strip()


def _busca_parcial(alias_lower: str) -> str | None:
    """Busca parcial em todas as fontes."""
    todas: dict[str, str] = dict(PASTAS_RAPIDAS)
    todas.update(_PROJETOS_LOCAL)
    try:
        todas.update(dict(PROJETOS.items()))
    except Exception:
        pass
    try:
        from env_loader import PASTAS as _ep
        todas.update(dict(_ep.items()))
    except Exception:
        pass

    for chave, path in todas.items():
        if alias_lower in chave or chave in alias_lower:
            return path
    return None


def _sugerir_similares(alias: str) -> list[str]:
    """Sugere aliases parecidos com o que foi digitado."""
    todos = list(PASTAS_RAPIDAS.keys()) + list(_PROJETOS_LOCAL.keys())
    try:
        todos += list(PROJETOS.keys())
    except Exception:
        pass
    return [a for a in todos if alias[:4] in a or a[:4] in alias][:3]


def _tentar_alternativo(alias: str, caminho_original: str) -> str | None:
    """Tenta caminhos alternativos quando o principal não existe."""
    if "onedrive" in alias:
        for nome in os.listdir(_HOME):
            if "onedrive" in nome.lower():
                alt = os.path.join(_HOME, nome)
                if os.path.isdir(alt):
                    return alt
    return None

"""
plugins/files/__init__.py
Módulo de gerenciamento de arquivos do Orion.

No import, dispara automaticamente (em background) o discover.py
se o environment_map.json não existir ou estiver desatualizado (>24h).
"""

import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

from plugins.files.search import buscar_arquivo
from plugins.files.open import abrir_pasta, abrir_arquivo, reload_projetos, PASTAS_RAPIDAS
from plugins.files.organize import organizar_downloads, organizar_por_mes

__all__ = [
    "buscar_arquivo",
    "abrir_pasta",
    "abrir_arquivo",
    "reload_projetos",
    "organizar_downloads",
    "organizar_por_mes",
    "PASTAS_RAPIDAS",
]


# ── Bootstrap: re-scan automático silencioso ──────────────────────────────────

def _bootstrap_discover():
    """
    Roda o discover.py em background se o mapa não existir ou estiver
    desatualizado. Chamado uma única vez no import deste módulo.
    """
    try:
        import sys
        import os
        # Garante que conseguimos importar discover a partir da raiz do projeto
        root = Path(__file__).parent.parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))

        from discover import needs_rescan, discover
        import json

        map_path = root / "memoria" / "environment_map.json"

        if not needs_rescan(map_path, max_age_hours=24):
            logger.debug("🗺️ environment_map.json está atualizado — sem re-scan.")
            return

        logger.info("🔍 environment_map.json ausente ou desatualizado — iniciando discover em background...")

        def run_discover():
            try:
                os.makedirs(map_path.parent, exist_ok=True)
                result = discover()
                map_path.write_text(
                    json.dumps(result, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                logger.info(
                    f"✅ Discover concluído: {len(result['projects'])} projetos | "
                    f"{len(result['programs'])} programas | "
                    f"{len(result['steam_games'])} jogos"
                )
                # Recarrega o env_loader para que PROJETOS reflita o novo mapa
                try:
                    from env_loader import get_env
                    get_env().reload()
                    logger.info("🔄 env_loader recarregado após discover.")
                except Exception as e:
                    logger.warning(f"Não foi possível recarregar env_loader: {e}")
            except Exception as e:
                logger.warning(f"Erro no discover em background: {e}")

        threading.Thread(target=run_discover, daemon=True, name="orion-discover").start()

    except Exception as e:
        logger.debug(f"Bootstrap discover ignorado: {e}")


_bootstrap_discover()

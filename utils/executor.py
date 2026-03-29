"""
utils/executor.py
Executa intenções sem precisar de um Update do Telegram.
Usado pelo mic_listener e pelos handlers de voz/texto.
"""

import logging
import os
import subprocess
import threading
import webbrowser
from urllib.parse import quote_plus

from utils.apps_config import KNOWN_APPS, IDE_COMMANDS

logger = logging.getLogger(__name__)


def executar_intent(intent: dict) -> str:
    """Executa a intent e retorna uma string de feedback."""
    action = intent.get("action")
    query = intent.get("query")
    delay = intent.get("delay")

    if action == "saudacao":
        from datetime import datetime
        hora = datetime.now().hour
        if hora < 12:
            periodo = "bom dia"
        elif hora < 18:
            periodo = "boa tarde"
        else:
            periodo = "boa noite"
        return f"🤖 {periodo.capitalize()}! Sou o *Orion*, seu assistente pessoal.\nComo posso ajudar?"

    if action == "apresentar":
        return (
            "🤖 Olá! Eu sou o *Orion*, seu assistente pessoal.\n\n"
            "Posso:\n"
            "• Tocar música no Spotify ou YouTube\n"
            "• Abrir jogos da Steam\n"
            "• Controlar o volume\n"
            "• Desligar/reiniciar o PC\n"
            "• Criar novos comandos personalizados\n\n"
            "_Pode me chamar por voz dizendo 'Orion' + o que você quer!_"
        )

    if action == "spotify":
        if query:
            # URI scheme abre o app do Spotify diretamente (sem browser)
            os.startfile(f"spotify:search:{query}")
            return f"🎵 Tocando no Spotify: *{query}*"
        os.startfile("spotify:")
        return "🎵 Spotify aberto."

    if action == "steam":
        os.startfile("steam:")
        return "🎮 Steam aberto."

    if action == "youtube":
        if query:
            url, titulo = _primeiro_video_youtube(query)
            webbrowser.open(url)
            return f"▶️ Tocando: *{titulo}*"
        webbrowser.open("https://www.youtube.com")
        return "▶️ YouTube aberto."

    if action == "netflix":
        if query:
            webbrowser.open(f"https://www.netflix.com/search?q={quote_plus(query)}")
            return f"🎬 Buscando na Netflix: *{query}*"
        webbrowser.open("https://www.netflix.com")
        return "🎬 Netflix aberto."

    if action == "pausar":
        from handlers.controle import ctrl_pausar
        return ctrl_pausar()

    if action == "proxima":
        from handlers.controle import ctrl_proxima
        return ctrl_proxima()

    if action == "anterior":
        from handlers.controle import ctrl_anterior
        return ctrl_anterior()

    if action == "create_project":
        return _criar_projeto(
            name=query,
            framework=intent.get("framework"),
            location=intent.get("location", "desktop"),
        )

    if action == "open_project":
        app_nome = intent.get("app") or "vscode"
        target = intent.get("target") or query
        ide_lower = app_nome.lower().replace(" ", "")
        resultado = _abrir_projeto(target, app_nome)
        if intent.get("run") and target:
            caminho = _encontrar_pasta_projeto(target)
            run_cmd = _get_run_cmd(caminho) if caminho else None
            if run_cmd and ide_lower in ("vscode", "code", "cursor"):
                threading.Thread(
                    target=_abrir_terminal_vscode_cmd,
                    args=(run_cmd, target),
                    daemon=True,
                ).start()
                return f"{resultado}\n▶️ Terminal integrado: `{run_cmd}`"
            elif run_cmd:
                return f"{resultado}\n{_rodar_projeto(target)}"
        return resultado

    if action == "run_project":
        target = intent.get("target") or query
        return _rodar_projeto(target)

    if action == "open_app":
        app_nome = intent.get("app") or query
        resultado = _abrir_app_conhecido(app_nome)
        return resultado if resultado else f"❌ App '{app_nome}' não reconhecido."

    if action == "jogo":
        return _abrir_jogo(query)

    if action == "vol_set":
        return _volume_set(query)

    if action == "vol_up":
        return _volume("up", query)

    if action == "vol_down":
        return _volume("down", query)

    if action == "mute":
        return _mute()

    if action == "desligar":
        d = delay if delay is not None else 60
        os.system(f"shutdown /s /t {d}")
        return f"💤 PC desligando em {d}s."

    if action == "reiniciar":
        d = delay if delay is not None else 60
        os.system(f"shutdown /r /t {d}")
        return f"🔄 PC reiniciando em {d}s."

    if action == "cancelar":
        os.system("shutdown /a")
        return "✅ Desligamento cancelado."

    # Tenta carregar módulos dinâmicos da pasta /plugins
    resultado_custom = _executar_modulo_custom(action, query)
    if resultado_custom:
        return resultado_custom

    return "❓ Não entendi o comando."


# ── Helpers ──────────────────────────────────────────────────────────────────

def _primeiro_video_youtube(query: str) -> tuple[str, str]:
    """Retorna (url_com_autoplay, titulo) do primeiro resultado do YouTube."""
    try:
        import yt_dlp
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "skip_download": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}", download=False)
            if info and info.get("entries"):
                entry = info["entries"][0]
                video_id = entry.get("id")
                titulo = entry.get("title", query)
                if video_id:
                    url = f"https://www.youtube.com/watch?v={video_id}&autoplay=1"
                    return url, titulo
    except Exception as e:
        logger.warning(f"yt-dlp falhou, abrindo busca: {e}")
    # Fallback para busca normal
    return f"https://www.youtube.com/results?search_query={quote_plus(query)}", query


def _abrir_app_conhecido(nome: str) -> str | None:
    """Tenta abrir um app Windows pelo nome. Retorna mensagem ou None se não reconheceu."""
    chave = nome.lower().strip()
    cmd = KNOWN_APPS.get(chave)
    if not cmd:
        for alias, comando in KNOWN_APPS.items():
            if chave in alias or alias in chave:
                cmd = comando
                chave = alias
                break
    if not cmd:
        return None
    try:
        subprocess.Popen(cmd, shell=True, creationflags=subprocess.DETACHED_PROCESS)
        return f"💻 Abrindo *{chave}*..."
    except Exception as e:
        logger.error(f"Erro ao abrir app {chave}: {e}")
        return f"❌ Erro ao abrir *{chave}*: {e}"


def _criar_projeto(name: str | None, framework: str | None = None, location: str = "desktop") -> str:
    """Cria a estrutura de um novo projeto usando o scaffolding do framework."""
    if not name:
        return "❓ Não entendi o nome do projeto. Diga algo como: _cria um projeto react chamado travel_"

    home = os.path.expanduser("~")
    if location == "documents":
        dest = os.path.join(home, "Documents")
    else:
        dest = os.path.join(home, "Desktop")
        # Prefere OneDrive Desktop se existir (comum no Windows com OneDrive)
        for onedrive in ("OneDrive", "OneDrive - Personal"):
            od_desktop = os.path.join(home, onedrive, "Desktop")
            if os.path.isdir(od_desktop):
                dest = od_desktop
                break

    project_path = os.path.join(dest, name)
    if os.path.exists(project_path):
        return f"❌ Já existe uma pasta *{name}* em `{os.path.basename(dest)}`."

    # Comando de scaffolding por framework — totalmente não-interativo
    # npx --yes: aceita instalação sem perguntar
    # flags extras eliminam todas as perguntas de variante/configuração
    _SCAFFOLD: dict[str, str] = {
        "react":   f"(echo n) | npm create --yes vite@5 {name} -- --template react && cd {name} && npm install",
        "vue":     f"(echo n) | npm create --yes vite@5 {name} -- --template vue && cd {name} && npm install",
        "svelte":  f"(echo n) | npm create --yes vite@5 {name} -- --template svelte && cd {name} && npm install",
        "vite":    f"(echo n) | npm create --yes vite@5 {name} -- --template vanilla && cd {name} && npm install",
        "next":    f"npx --yes create-next-app@latest {name} --ts --eslint --no-tailwind --no-src-dir --app --import-alias @/* && cd {name} && npm install",
        "nextjs":  f"npx --yes create-next-app@latest {name} --ts --eslint --no-tailwind --no-src-dir --app --import-alias @/* && cd {name} && npm install",
        "angular": f"npx --yes @angular/cli new {name} --routing --style css --skip-git",
        "express": f"npx --yes express-generator {name} && cd {name} && npm install",
        "nuxt":    f"npx --yes nuxi@latest init {name} && cd {name} && npm install",
        "django":  f"django-admin startproject {name} .",
        "flask":   None,
        "fastapi": None,
        "laravel": f"composer create-project laravel/laravel {name}",
    }

    scaffold_cmd = _SCAFFOLD.get(framework or "") if framework else None

    try:
        if scaffold_cmd:
            os.system(f'start cmd /k "cd /d {dest} && {scaffold_cmd}"')
            return (
                f"🚀 Criando *{name}*"
                f"{f' com {framework}' if framework else ''}...\n"
                f"📂 `{dest}`\n"
                f"Sem perguntas — dependências instaladas automaticamente.\n"
                f"Quando o terminal fechar: _abra o {name} no vscode e rode ele_"
            )
        else:
            os.makedirs(project_path, exist_ok=True)
            tipo = framework or "genérico"
            return (
                f"📁 Pasta *{name}* criada em `{os.path.basename(dest)}`.\n"
                f"Tipo: {tipo} — configure manualmente ou diga o comando de init."
            )
    except Exception as e:
        logger.error(f"Erro ao criar projeto {name}: {e}")
        return f"❌ Erro ao criar projeto *{name}*: {e}"


def _get_run_cmd(caminho: str) -> str | None:
    """Detecta e retorna o comando de run para um projeto sem executá-lo."""
    arquivos = {f.lower() for f in os.listdir(caminho)}
    if "package.json" in arquivos:
        return "npm run dev" if _tem_script_dev(caminho) else "npm start"
    if "pyproject.toml" in arquivos or "uv.lock" in arquivos:
        return "uv run python main.py"
    if "requirements.txt" in arquivos or any(f.endswith(".py") for f in arquivos):
        entry = "main.py" if "main.py" in arquivos else next(
            (f for f in arquivos if f.endswith(".py")), None
        )
        return f"python {entry}" if entry else None
    if "cargo.toml" in arquivos:
        return "cargo run"
    if "go.mod" in arquivos:
        return "go run ."
    return None


def _rodar_projeto(nome: str | None) -> str:
    """Detecta o tipo de projeto e executa o comando de run em nova janela CMD."""
    if not nome:
        return "❓ Informe o nome do projeto para rodar."

    caminho = _encontrar_pasta_projeto(nome)
    if not caminho:
        return f"❌ Projeto *{nome}* não encontrado para rodar."

    run_cmd = _get_run_cmd(caminho)
    if not run_cmd:
        return f"❓ Não reconheci o tipo de projeto em *{nome}*. Diga o comando manualmente."

    try:
        os.system(f'start cmd /k "cd /d {caminho} && {run_cmd}"')
        return f"▶️ Rodando *{nome}*..."
    except Exception as e:
        return f"❌ Erro ao rodar *{nome}*: {e}"


def _abrir_terminal_vscode_cmd(run_cmd: str, project_name: str) -> None:
    """
    Abre o terminal integrado do VSCode (Ctrl+`) e executa run_cmd.
    Roda em thread daemon com delay para aguardar o VSCode carregar.
    Usa WSH SendKeys via PowerShell — funciona sem dependências externas.
    """
    import time
    time.sleep(3.5)  # aguarda VSCode carregar o projeto

    # Escapa caracteres especiais do WSH SendKeys no run_cmd
    safe_cmd = (
        run_cmd
        .replace("+", "{+}")
        .replace("^", "{^}")
        .replace("%", "{%}")
        .replace("~", "{~}")
        .replace("(", "{(}").replace(")", "{)}")
        .replace("[", "{[}").replace("]", "{]}")
        .replace("{", "{{").replace("}", "}}")
    )

    ps_script = (
        "$wshell = New-Object -ComObject wscript.shell\n"
        f"$null = $wshell.AppActivate('{project_name}')\n"
        "Start-Sleep -Milliseconds 600\n"
        "$wshell.SendKeys('^`')\n"           # Ctrl+` → abre terminal integrado
        "Start-Sleep -Milliseconds 900\n"
        f"$wshell.SendKeys('{safe_cmd}')\n"  # digita o comando
        "$wshell.SendKeys('~')\n"            # ~ = Enter no SendKeys
    )

    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
        )
    except Exception as e:
        logger.warning(f"Erro ao abrir terminal integrado VSCode: {e}")


def _tem_script_dev(caminho: str) -> bool:
    """Verifica se package.json tem o script 'dev'."""
    try:
        import json
        with open(os.path.join(caminho, "package.json"), encoding="utf-8") as f:
            pkg = json.load(f)
        return "dev" in pkg.get("scripts", {})
    except Exception:
        return False


def _abrir_projeto(nome: str | None, ide: str = "vscode") -> str:  # noqa: C901
    """Localiza a pasta do projeto e abre na IDE especificada."""
    ide_lower = ide.lower().strip()
    cmd_ide = IDE_COMMANDS.get(ide_lower)
    if not cmd_ide:
        for alias, cmd in IDE_COMMANDS.items():
            if ide_lower in alias or alias in ide_lower:
                cmd_ide = cmd
                break
    if not cmd_ide:
        cmd_ide = KNOWN_APPS.get(ide_lower, ide_lower)

    if not nome:
        subprocess.Popen(cmd_ide, shell=True, creationflags=subprocess.DETACHED_PROCESS)
        return f"💻 Abrindo *{ide}*..."

    caminho = _encontrar_pasta_projeto(nome)
    if not caminho:
        buscados = ", ".join(os.path.basename(r) for r in _raizes_dev())
        return (
            f"❌ Pasta *{nome}* não encontrada.\n"
            f"Busquei em: {buscados}\n"
            f"Dica: diga o caminho completo, ex: _abra C:\\\\Users\\\\rael\\\\Desktop\\\\{nome} no vscode_"
        )
    try:
        subprocess.Popen(f'{cmd_ide} "{caminho}"', shell=True, creationflags=subprocess.DETACHED_PROCESS)
        return f"💻 Abrindo *{nome}* no {ide}..."
    except Exception as e:
        logger.error(f"Erro ao abrir projeto {nome} em {ide}: {e}")
        return f"❌ Erro ao abrir projeto *{nome}*: {e}"


def _raizes_dev() -> list[str]:
    """Retorna diretórios de desenvolvimento existentes (cacheado por processo)."""
    if not hasattr(_raizes_dev, "_cache"):
        home = os.path.expanduser("~")
        candidatos = [
            home,
            os.path.join(home, "Documents"),
            os.path.join(home, "Desktop"),
            # OneDrive Desktop (comum no Windows com OneDrive ativo)
            os.path.join(home, "OneDrive", "Desktop"),
            os.path.join(home, "OneDrive - Personal", "Desktop"),
            os.path.join(home, "projects"),
            os.path.join(home, "repos"),
            os.path.join(home, "dev"),
            os.path.join(home, "code"),
            os.path.join(home, "workspace"),
            "C:\\projects",
            "C:\\dev",
        ]
        _raizes_dev._cache = [p for p in candidatos if os.path.isdir(p)]
    return _raizes_dev._cache


def _encontrar_pasta_projeto(nome: str) -> str | None:
    """Busca uma pasta pelo nome nos diretórios comuns de desenvolvimento (até 2 níveis)."""
    nome_lower = nome.lower()
    raizes = _raizes_dev()
    logger.info(f"Buscando projeto '{nome}' em: {raizes}")
    for raiz in raizes:
        try:
            for entrada in os.scandir(raiz):
                if not entrada.is_dir():
                    continue
                if entrada.name.lower() == nome_lower:
                    logger.info(f"Projeto encontrado: {entrada.path}")
                    return entrada.path
                # Segundo nível: raiz/subpasta/projeto
                try:
                    for sub in os.scandir(entrada.path):
                        if sub.is_dir() and sub.name.lower() == nome_lower:
                            logger.info(f"Projeto encontrado (nível 2): {sub.path}")
                            return sub.path
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError):
            continue
    logger.warning(f"Projeto '{nome}' não encontrado em nenhum diretório padrão")
    return None


def _abrir_jogo(nome: str | None) -> str:
    if not nome:
        return "❓ Informe o nome do app ou jogo."

    # Tenta apps conhecidos antes de consultar Steam
    resultado_app = _abrir_app_conhecido(nome)
    if resultado_app:
        return resultado_app

    from difflib import get_close_matches
    from utils.steam_scanner import escanear_jogos_steam

    jogos = escanear_jogos_steam()
    if not jogos:
        return "❌ Nenhum jogo Steam encontrado."

    nomes = list(jogos.keys())
    match = next((n for n in nomes if n.lower() == nome.lower()), None)

    if not match:
        parciais = [n for n in nomes if nome.lower() in n.lower()]
        if len(parciais) == 1:
            match = parciais[0]
        elif not parciais:
            sugestoes = get_close_matches(nome, nomes, n=1, cutoff=0.4)
            match = sugestoes[0] if sugestoes else None

    if not match:
        return f"❌ Jogo '{nome}' não encontrado."

    caminho = jogos[match]
    try:
        if caminho.startswith("steam://"):
            os.startfile(caminho)
        else:
            subprocess.Popen(
                [caminho],
                cwd=os.path.dirname(caminho),
                creationflags=subprocess.DETACHED_PROCESS,
            )
        return f"🎮 Abrindo *{match}*..."
    except Exception as e:
        logger.error(f"Erro ao abrir {match}: {e}")
        return f"❌ Erro ao abrir *{match}*: {e}"


def _get_vol():
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL

    dispositivos = AudioUtilities.GetSpeakers()
    if dispositivos is None:
        raise RuntimeError("Nenhum dispositivo de áudio encontrado.")
    dev = getattr(dispositivos, "_dev", dispositivos)
    interface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def _barra(pct: int) -> str:
    blocos = round(pct / 10)
    return "█" * blocos + "░" * (10 - blocos)


def _volume(direcao: str, query: str | None) -> str:
    try:
        passo = float(query) / 100 if query and query.isdigit() else 0.10
        vol = _get_vol()
        atual = vol.GetMasterVolumeLevelScalar()
        novo = min(1.0, atual + passo) if direcao == "up" else max(0.0, atual - passo)
        vol.SetMasterVolumeLevelScalar(novo, None)
        pct = int(novo * 100)
        emoji = "🔊" if direcao == "up" else "🔉"
        return f"{emoji} *{pct}%*  {_barra(pct)}"
    except Exception as e:
        return f"❌ Erro no volume: {e}"


def _volume_set(query: str | None) -> str:
    try:
        if not query or not query.isdigit():
            vol = _get_vol()
            pct = int(vol.GetMasterVolumeLevelScalar() * 100)
            return f"🔊 Volume atual: *{pct}%*  {_barra(pct)}"
        alvo = max(0, min(100, int(query)))
        vol = _get_vol()
        vol.SetMasterVolumeLevelScalar(alvo / 100, None)
        return f"🔊 Volume: *{alvo}%*  {_barra(alvo)}"
    except Exception as e:
        return f"❌ Erro no volume: {e}"


def _mute() -> str:
    try:
        vol = _get_vol()
        estado = vol.GetMute()
        vol.SetMute(not estado, None)
        return "🔇 *Mutado*" if not estado else "🔊 *Desmutado*"
    except Exception as e:
        return f"❌ Erro no mute: {e}"

def _executar_modulo_custom(action: str, query: str | None) -> str | None:
    """
    Tenta encontrar e executar um script em /plugins/ que corresponda à action.
    """
    try:
        import importlib.util
        import sys
        
        modulo_path = os.path.join("plugins", f"{action}.py")
        if not os.path.exists(modulo_path):
            return None
            
        spec = importlib.util.spec_from_file_location(action, modulo_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Procura uma função 'run' ou 'executar' no módulo
            func = getattr(module, "run", getattr(module, "executar", None))
            if func:
                return func(query)
            return f"⚠️ Módulo '{action}' encontrado, mas falta função 'run(query)'."
    except Exception as e:
        logger.error(f"Erro ao executar módulo custom {action}: {e}")
        return f"❌ Erro no módulo custom '{action}': {e}"
    
    return None

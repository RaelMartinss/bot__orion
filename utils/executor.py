"""
utils/executor.py
Executa intenções sem precisar de um Update do Telegram.
Usado pelo mic_listener e pelos handlers de voz/texto.
"""

import logging
import os
import subprocess

# Sentinel compartilhado com handlers/voice.py para respostas especiais
QR_IMAGE_PREFIX = "_QR_IMAGE:"

import webbrowser
from urllib.parse import quote_plus

from utils.apps_config import KNOWN_APPS, IDE_COMMANDS

logger = logging.getLogger(__name__)


async def _fechar_browser_async() -> None:
    from utils.browser_manager import get_browser_manager
    bm = await get_browser_manager()
    await bm.close()


def executar_intent(intent: dict) -> str:
    """Executa a intent e retorna uma string de feedback."""
    action = intent.get("action")
    query = intent.get("query")
    delay = intent.get("delay")
    
    if action == "date_time":
        from utils.datetime_utils import get_current_datetime_string
        from datetime import datetime
        res = get_current_datetime_string()
        # Se contém "amanhã" na query, calcula o dia seguinte
        if query and "amanhã" in query.lower():
            from datetime import timedelta
            now = datetime.now()
            amanha = now + timedelta(days=1)
            
            from utils.datetime_utils import DIAS_SEMANA, MESES
            dia_semana = DIAS_SEMANA[amanha.weekday()]
            return f"📅 {res}\nAmanhã será **{dia_semana}, {amanha.day} de {MESES[amanha.month]} de {amanha.year}**."
        return f"📅 {res}"

    if action == "saudacao":
        from datetime import datetime
        hora = datetime.now().hour
        if hora < 12:
            periodo = "Bom dia"
            complemento = "Sistemas online. Pronto para o dia."
        elif hora < 18:
            periodo = "Boa tarde"
            complemento = "Tudo operacional por aqui."
        else:
            periodo = "Boa noite"
            complemento = "Ainda acordado? Estou aqui."
        return f"🤖 {periodo}. {complemento}"

    if action == "apresentar":
        return (
            "🤖 Olá! Eu sou o *Orion*, seu assistente pessoal.\n\n"
            "Posso:\n"
            "• 🎵 Tocar música no Spotify ou YouTube\n"
            "• 🎮 Abrir jogos da Steam\n"
            "• 🔊 Controlar o volume\n"
            "• 💤 Desligar/reiniciar o PC\n"
            "• 📂 Abrir pastas e projetos rapidamente\n"
            "• 🔍 Buscar arquivos por contexto\n"
            "• 🗂️ Organizar seus Downloads automaticamente\n"
            "• ✉️ Ler e enviar e-mails\n"
            "• 📅 Gerenciar sua agenda\n"
            "• 🧠 Criar novos comandos personalizados\n\n"
            "💡 *Exemplos de arquivos:*\n"
            "_'acha o contrato de março'_\n"
            "_'abre a pasta de downloads'_\n"
            "_'organiza meus downloads'_\n\n"
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

    if action == "whatsapp_enviar":
        from utils.whatsapp_client import enviar_mensagem, iniciar_servidor, status as wpp_status, salvar_contato
        destinatario = intent.get("query") or query or ""
        mensagem = intent.get("message") or ""

        # Número embutido no texto → salva contato automaticamente
        phone = intent.get("phone")
        phone_name = intent.get("phone_name") or destinatario
        if phone and phone_name:
            salvar_contato(phone_name, phone)
            if not destinatario:
                destinatario = phone_name

        if not destinatario:
            return "Para quem devo enviar a mensagem? Diga: *'manda mensagem pro João que...'*"
        if not mensagem:
            if phone:
                return f"✅ Contato *{phone_name}* salvo com o número {phone}. Qual mensagem devo enviar?"
            return f"Qual mensagem devo enviar para *{destinatario}*?"
        # Garante que servidor está pronto
        st = wpp_status()
        if not st.get("pronto"):
            resultado_inicio = iniciar_servidor(aguardar_conexao=True, timeout=60)
            if resultado_inicio == "qr":
                return "📱 WhatsApp precisa ser conectado. Diga *'conecta whatsapp'* para ver o QR Code."
            if resultado_inicio == "timeout":
                return "⏳ WhatsApp demorou para iniciar. Tente novamente em alguns segundos."
            if resultado_inicio.startswith("❌"):
                return resultado_inicio
        return enviar_mensagem(destinatario, mensagem)

    if action == "whatsapp_status":
        from utils.whatsapp_client import status, iniciar_servidor, servidor_online
        if not servidor_online():
            res = iniciar_servidor()
            return f"Servidor iniciado. {res}"
        st = status()
        estado = st.get("estado", "desconhecido")
        emoji = {"conectado": "✅", "qr": "📱", "desconectado": "❌", "inicializando": "⏳"}.get(estado, "❓")
        return f"{emoji} WhatsApp: *{estado}*"

    if action == "whatsapp_qr":
        from utils.whatsapp_client import get_qr, iniciar_servidor, servidor_online
        if not servidor_online():
            iniciar_servidor(aguardar_conexao=False)
            import time; time.sleep(5)
        qr = get_qr()
        if not qr:
            st = __import__("utils.whatsapp_client", fromlist=["status"]).status()
            if st.get("pronto"):
                return "✅ WhatsApp já está conectado! Não precisa escanear QR."
            return "⏳ QR Code ainda não disponível — o servidor ainda está inicializando. Aguarde alguns segundos e repita."
        # Gera imagem PNG do QR Code
        try:
            import qrcode as _qr_lib
            import tempfile, os
            img = _qr_lib.make(qr)
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            img.save(tmp.name)
            tmp.close()
            return f"{QR_IMAGE_PREFIX}{tmp.name}"
        except Exception:
            return f"📱 Escaneie pelo WhatsApp → *Aparelhos Conectados*:\n`{qr[:400]}`"

    if action == "configurar_pendrive":
        from utils.presence import definir_pendrive_presenca, listar_pendrives
        pendrives = listar_pendrives()
        if not pendrives:
            return "Nenhum pendrive detectado. Conecte o pendrive e repita o comando."
        if len(pendrives) == 1:
            return definir_pendrive_presenca()
        listagem = "\n".join(f"• {p['letra']}: — {p['label']}" for p in pendrives)
        return (
            f"Encontrei {len(pendrives)} pendrives conectados:\n{listagem}\n\n"
            f"Diga qual usar: *'configura presença com o pendrive X'*"
        )

    if action == "reiniciar_video":
        from handlers.controle import ctrl_reiniciar_video
        return ctrl_reiniciar_video()

    if action == "browser_abrir":
        webbrowser.open("https://www.google.com")
        return "🌐 Navegador aberto."

    if action == "browser_fechar":
        # Fecha via Playwright se houver sessão ativa, senão Alt+F4 na janela do browser
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(_fechar_browser_async())
            else:
                loop.run_until_complete(_fechar_browser_async())
        except Exception:
            import pyautogui, pygetwindow as gw
            for janela in gw.getAllWindows():
                if any(b in janela.title.lower() for b in ["chrome", "firefox", "edge", "chromium"]):
                    janela.activate()
                    import time; time.sleep(0.2)
                    pyautogui.hotkey("alt", "f4")
                    break
        return "🌐 Navegador fechado."

    if action == "create_project":
        return _criar_projeto(
            name=query,
            framework=intent.get("framework"),
            location=intent.get("location", "desktop"),
        )

    if action == "open_project":
        app_nome = intent.get("app") or "vscode"
        target = intent.get("target") or query
        resultado = _abrir_projeto(target, app_nome)
        if intent.get("run") and target:
            return f"{resultado}\n{_rodar_projeto(target)}"
        return resultado

    if action == "run_project":
        target = intent.get("target") or query
        return _rodar_projeto(target)

    if action == "set_alarm":
        return _criar_alarme(query, intent.get("message", "Lembrete!"))

    if action == "agenda_hoje":
        from plugins.agenda import resumo_hoje
        return resumo_hoje()

    if action == "agenda_semana":
        from plugins.agenda import resumo_semana
        return resumo_semana()

    if action == "agenda_proximo":
        from plugins.agenda import resumo_proximo
        return resumo_proximo()

    if action == "agenda_criar":
        from plugins.agenda import criar_evento
        horario = intent.get("time") or "09:00"
        titulo = query or "Compromisso"
        return criar_evento(titulo, horario)

    if action == "email_inbox":
        from plugins.email_manager import resumo_inbox
        return resumo_inbox()

    if action == "email_nao_lidos":
        from plugins.email_manager import resumo_nao_lidos
        return resumo_nao_lidos()

    if action == "email_ler":
        from plugins.email_manager import ler_mais_recente
        return ler_mais_recente()

    if action == "email_buscar":
        from plugins.email_manager import resultado_busca
        return resultado_busca(query or "")

    if action == "email_enviar":
        if not query:
            return "❓ Informe o destinatário. Ex: _mande email para fulano@gmail.com_"
        from plugins.email_manager import enviar_email
        para = query.strip(" ,;")
        assunto = intent.get("message") or "Mensagem do Orion"
        corpo = intent.get("body") or assunto
        return enviar_email(para, assunto, corpo)

    if action == "vision_on":
        from utils import vision
        return vision.iniciar()

    if action == "vision_off":
        from utils import vision
        return vision.parar()

    if action == "vision_analyze":
        from utils import vision
        sugestao = vision.analisar_agora()
        return sugestao if sugestao else "🖥️ Nada relevante detectado na tela no momento."

    if action == "set_favorite_team":
        if query:
            from utils.memoria import salvar_preferencia
            # user_id não está disponível no executor — salvo via callback no voice.py
            return f"⚽ Time favorito salvo: *{query.title()}*! Vou te avisar quando ele jogar."
        return "❓ Não identifiquei o time."

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

    if action == "bloquear_pc":
        os.system("rundll32.exe user32.dll,LockWorkStation")
        return "🔒 Computador bloqueado."

    if action == "fechar_app":
        return _fechar_app_conhecido(query or "")


    # ── Gerenciamento de Arquivos ─────────────────────────────────────────────

    if action == "file_search":
        from plugins.files.search import buscar_arquivo
        return buscar_arquivo(
            query=query or "",
            tipo=intent.get("tipo"),
            data_ref=intent.get("data_ref"),
        )

    if action == "file_open_file":
        from plugins.files.search import abrir_arquivo_por_nome
        return abrir_arquivo_por_nome(query or "")

    if action == "file_open_folder":
        from plugins.files.open import abrir_pasta
        return abrir_pasta(query or "")

    if action == "file_organize":
        from plugins.files.organize import organizar_downloads, organizar_por_mes
        por_mes = intent.get("por_mes", False)
        if por_mes:
            return organizar_por_mes(confirmar=False)
        return organizar_downloads(confirmar=False)

    if action == "file_organize_confirm":
        from plugins.files.organize import organizar_downloads, organizar_por_mes
        if intent.get("query") == "por_mes":
            return organizar_por_mes(confirmar=True)
        return organizar_downloads(confirmar=True)

    if action == "file_reindex":
        from plugins.files.indexer import reindexar
        return reindexar()

    if action == "file_index_status":
        from plugins.files.indexer import status_indice
        return status_indice()

    if action == "file_list_downloads":
        from plugins.files.organize import listar_downloads
        return listar_downloads()

    if action == "file_list_projects":
        from plugins.files.open import listar_projetos
        return listar_projetos()

    # Tenta carregar módulos dinâmicos da pasta /plugins
    resultado_custom = _executar_modulo_custom(action, query)
    if resultado_custom:
        return resultado_custom

    return "❓ Não entendi o comando."


async def executar_manutencao(acao: str, permitir: bool = False) -> str:
    """Implementa o self-healing do Orion."""
    import shutil
    import subprocess
    import sys
    
    if acao == "verificar_saude":
        report = ["🏥 **Relatório de Saúde Orion**", ""]
        
        # 1. Internet
        import socket
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            report.append("✅ Conexão com Internet: Ativa")
        except Exception:
            report.append("❌ Conexão com Internet: Indisponível")
            
        # 2. Ollama
        if shutil.which("ollama"):
            report.append("✅ Conexão Local (Ollama): Instalado")
        else:
            report.append("❌ Conexão Local (Ollama): Faltando (Use 'instalar_ollama')")
            
        # 3. YT-DLP
        if shutil.which("yt-dlp"):
            report.append("✅ Mídia (yt-dlp): Pronto")
        else:
            report.append("⚠️ Mídia (yt-dlp): Faltando")
            
        return "\n".join(report)

    if acao == "instalar_ollama":
        if not permitir:
            return "Ollma detectado como faltando. Gostaria que eu realizasse o download e a instalação silenciosa? (Confirme 'Sim')"
            
        if shutil.which("ollama"):
            return "Ollama já está instalado no sistema."
            
        try:
            # Instalação Totalmente Via Terminal (Conforme sugerido: irm | iex)
            cmd = "powershell -Command \"[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; irm https://ollama.com/install.ps1 | iex\""
            
            # Executa de forma detached para não travar o bot mas logar o resultado
            subprocess.Popen(cmd, shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
            
            return "🚀 Comando de instalação enviado ao PowerShell. O Ollama será instalado em segundo plano sem necessidade de interação. Após as janelas fecharem, reinicie o Orion."
        except Exception as e:
            return f"❌ Erro ao disparar instalação do Ollama: {e}"

    if acao == "configurar_cerebro_local":
        if not shutil.which("ollama"):
            return "Erro: Ollama não instalado. Instale-o primeiro."
        
        try:
            process = subprocess.Popen(["ollama", "pull", "mistral"], creationflags=subprocess.CREATE_NEW_CONSOLE)
            return "🧠 Iniciando download do modelo Mistral em nova janela. Isso pode demorar alguns minutos dependendo da sua internet."
        except Exception as e:
            return f"❌ Erro ao configurar cérebro local: {e}"

    if acao == "instalar_yt_dlp":
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "yt-dlp"])
            return "✅ yt-dlp instalado com sucesso."
        except Exception as e:
            return f"❌ Erro ao instalar yt-dlp: {e}"

    return "Ação de manutenção desconhecida."


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
        if cmd.startswith("__browser__"):
            # Abre browser via webbrowser (funciona independente do PATH)
            browser_name = cmd.replace("__browser__", "").strip() or None
            if browser_name:
                webbrowser.get(browser_name).open("https://www.google.com")
            else:
                webbrowser.open("https://www.google.com")
        elif ":" in cmd and not cmd.startswith(("cmd", "powershell", "python")):
            os.startfile(cmd)
        else:
            subprocess.Popen(cmd, shell=True, creationflags=subprocess.DETACHED_PROCESS)
        return f"💻 Abrindo *{chave}*..."
    except Exception as e:
        logger.error(f"Erro ao abrir app {chave}: {e}")
        return f"❌ Erro ao abrir *{chave}*: {e}"


def _fechar_app_conhecido(nome: str) -> str:
    """Tenta fechar um app Windows pelo nome."""
    chave = nome.lower().strip()
    cmd = KNOWN_APPS.get(chave)
    if not cmd:
        for alias, comando in KNOWN_APPS.items():
            if chave in alias or alias in chave:
                cmd = comando
                chave = alias
                break

    # Mapa de processos conhecidos
    proc_map = {
        "__browser__": ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"],
        "__browser__firefox": ["firefox.exe"],
        "__browser__msedge": ["msedge.exe"],
        "code": ["Code.exe"],
        "notepad": ["notepad.exe"],
        "notepad++": ["notepad++.exe"],
        "calc": ["CalculatorApp.exe", "calc.exe"],
        "explorer": ["explorer.exe"],
        "steam:": ["steam.exe"],
        "discord": ["Discord.exe"],
        "obs64": ["obs64.exe"],
        "vlc": ["vlc.exe"],
        "winword": ["WINWORD.EXE"],
        "excel": ["EXCEL.EXE"],
        "powerpnt": ["POWERPNT.EXE"],
    }

    if not cmd:
        # Fallback: se não for mapeado, tenta matar pelo nome da query crua
        os.system(f'taskkill /F /IM "{chave.replace(" ", "")}.exe" /T >nul 2>&1')
        return f"🛑 Tentando fechar *{chave}*..."

    processos = proc_map.get(cmd, [f"{cmd}.exe"])
    for p in processos:
        os.system(f'taskkill /F /IM "{p}" /T >nul 2>&1')
        
    return f"🛑 Fechando *{chave}*..."


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


def _criar_alarme(horario: str | None, mensagem: str = "Lembrete!") -> str:
    """Cria um alarme de thread que dispara notificação Windows no horário dado (HH:MM)."""
    import threading
    import time as _time
    from datetime import datetime

    if not horario:
        return "❓ Não entendi o horário. Diga algo como: _me lembra às 16h55 de tomar água_"

    def _loop():
        while True:
            if datetime.now().strftime("%H:%M") == horario:
                try:
                    from win10toast import ToastNotifier
                    ToastNotifier().show_toast("⏰ Orion", mensagem, duration=10, threaded=True)
                except Exception:
                    # Fallback: notificação via PowerShell (sem dependência extra)
                    import subprocess
                    ps_cmd = (
                        f'[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, '
                        f'ContentType = WindowsRuntime] | Out-Null; '
                        f'$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent('
                        f'[Windows.UI.Notifications.ToastTemplateType]::ToastText01); '
                        f'$xml.GetElementsByTagName("text")[0].AppendChild($xml.CreateTextNode("{mensagem}")) | Out-Null; '
                        f'[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Orion")'
                        f'.Show([Windows.UI.Notifications.ToastNotification]::new($xml))'
                    )
                    subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True)
                break
            _time.sleep(20)

    threading.Thread(target=_loop, daemon=True, name=f"alarm-{horario}").start()
    return f"⏰ Alarme configurado para *{horario}*: _{mensagem}_"


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

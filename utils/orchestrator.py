"""
utils/orchestrator.py

Implementa o fluxo de Function Calling usando a API da Anthropic.
O Claude agora atua como um agente orquestrador: ele recebe a mensagem do usuário,
decide se precisa de uma ferramenta (como pausar mídia, listar jogos, desligar pc),
pede para rodar a ferramenta, e nós devolvemos o resultado local para ele formular
a resposta final pro usuário.
"""

import json
import logging
import httpx
import asyncio
import importlib.util
import os
import re
import urllib.parse
import urllib.request
from html import unescape
from html.parser import HTMLParser
from collections import defaultdict
from utils.claude_client import _get_api_key, ANTHROPIC_API_URL, MODEL
from utils.executor import (
    _abrir_jogo, _volume_set, _volume, _mute,
    _primeiro_video_youtube
)
from utils.steam_scanner import escanear_jogos_steam
from utils.memoria import carregar_memoria_longa, salvar_fato

logger = logging.getLogger(__name__)

_USER_LOCKS: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
_MAX_TURNS = 4
_MAX_API_RETRIES = 4
_BACKOFF_BASE_SECONDS = 2
_PLUGINS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "plugins"))
_DEFAULT_HEADERS = {"User-Agent": "Mozilla/5.0"}

SYSTEM_ORCHESTRATOR = """Você é o ORION, o núcleo de um Agente de Dados Resiliente (Nível Pro). Sua missão é nunca falhar por falta de informação.

PROTOCOLO DE RESILIÊNCIA (CRÍTICO):
1. MÚLTIPLAS FONTES: Se uma tarefa exige dados externos (futebol, clima, notícias, etc), seus plugins DEVERÃO tentar múltiplas fontes. 
   - Ex: Fonte 1 (API) -> Fonte 2 (Scraping via BeautifulSoup/Requests) -> Fonte 3 (Google Search).
2. PLUGIN PATTERN: Crie plugins em `plugins/{nome}.py` com a função `def run(args):`.
3. CONSCIÊNCIA: Sempre use `listar_arquivos('plugins')` antes de agir para reusar o que já existe.
4. FEEDBACK: Use `enviar_mensagem_imediata` para reportar o progresso ("Fonte A falhou, consultando Fonte B...").
5. WEB REAL: Para perguntas factuais, atuais ou informacionais, use `buscar_web` e `ler_url` antes de responder. Não invente fatos atuais.
6. FONTES: Ao responder com dados da web, cite a fonte no texto final de forma curta e inclua a URL quando fizer sentido.
7. DADOS ATUAIS DE ESPORTE: Próximo jogo, placar, tabela, agenda e resultados devem vir da web, não de plugin local.

ESTRUTURA: Use a pasta `plugins/` para todas as extensões. Nunca cite 'modulos/'.
"""

TOOLS = [
    {
        "name": "listar_jogos",
        "description": "Faz uma varredura na Steam instalada e lista os nomes de todos os jogos disponíveis no PC.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "abrir_jogo",
        "description": "Abre um jogo específico pelo nome. Requer que o jogo retorne na varredura.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": "Nome do jogo a ser aberto"}
            },
            "required": ["nome"]
        }
    },
    {
        "name": "controle_midia",
        "description": "Controla mídias ativas no Windows (ex: pausar YouTube, próxima música Spotify).",
        "input_schema": {
            "type": "object",
            "properties": {
                "acao": {"type": "string", "enum": ["pausar", "proxima", "anterior"]}
            },
            "required": ["acao"]
        }
    },
    {
        "name": "controle_volume",
        "description": "Controla o volume global do Windows.",
        "input_schema": {
            "type": "object",
            "properties": {
                "acao": {"type": "string", "enum": ["up", "down", "set", "mute"]},
                "percentual": {"type": "integer", "description": "Usado se acao=set, up ou down"}
            },
            "required": ["acao"]
        }
    },
    {
        "name": "buscar_midia",
        "description": "Abre vídeos/músicas/filmes nas plataformas suportadas.",
        "input_schema": {
            "type": "object",
            "properties": {
                "plataforma": {"type": "string", "enum": ["youtube", "spotify", "netflix"]},
                "query": {"type": "string", "description": "Nome da música, artista, vídeo ou filme"}
            },
            "required": ["plataforma"]
        }
    },
    {
        "name": "controle_energia",
        "description": "Desliga, reinicia ou cancela o encerramento do PC.",
        "input_schema": {
            "type": "object",
            "properties": {
                "acao": {"type": "string", "enum": ["desligar", "reiniciar", "cancelar"]},
                "delay_segundos": {"type": "integer", "description": "Segundos pro shutdown/restart"}
            },
            "required": ["acao"]
        }
    },
    {
        "name": "executar_plugin",
        "description": "Executa diretamente um plugin local da pasta 'plugins/' quando ele já existir no projeto.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": "Nome do plugin sem .py, ex: proximo_jogo"},
                "query": {"type": "string", "description": "Parâmetro textual opcional para o plugin"}
            },
            "required": ["nome"]
        }
    },
    {
        "name": "iniciar_criacao_comando",
        "description": "Aciona o processo interativo do Telegram para você APRENDER um atalho telegram permanente (gerar python). Use SOMENTE se o usuário pedir 'aprenda', 'crie atalho' ou 'crie comando'.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "executar_terminal",
        "description": "Executa um comando no terminal do Windows (cmd/powershell) e retorna a saída (STDOUT e STDERR). Use isso PARA TUDO QUE MODIFIQUE OU LEIA o sistema. Se houver STDERR indicando falha/crash, NÃO DIGA QUE FOI SUCESSO. Leia o STDERR.",
        "input_schema": {
            "type": "object",
            "properties": {
                "comando": {"type": "string", "description": "O comando de terminal para rodar"}
            },
            "required": ["comando"]
        }
    },
    {
        "name": "buscar_web",
        "description": "Pesquisa na web e retorna uma lista curta de resultados com título, URL e resumo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Consulta de busca"},
                "max_results": {"type": "integer", "description": "Quantidade máxima de resultados (1-5)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "ler_url",
        "description": "Lê o conteúdo textual de uma URL específica para extrair informações confiáveis da página.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL completa da página"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "atualizar_memoria",
        "description": "Salva uma informação importante sobre o usuário (stack de dev, preferências, nome, gostos) para ser lembrada em conversas futuras.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fato": {"type": "string", "description": "O fato ou preferência a ser guardado (ex: 'O usuário prefere projetos em TypeScript')"}
            },
            "required": ["fato"]
        }
    },
    {
        "name": "escrever_arquivo",
        "description": "Cria ou sobrescreve um arquivo no sistema com o conteúdo fornecido. Use para criar novos plugins em 'plugins/'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "caminho": {"type": "string", "description": "Caminho do arquivo (ex: plugins/clima.py)"},
                "conteudo": {"type": "string", "description": "Código ou texto completo do arquivo"}
            },
            "required": ["caminho", "conteudo"]
        }
    },
    {
        "name": "ler_arquivo",
        "description": "Lê o conteúdo de um arquivo existente para análise.",
        "input_schema": {
            "type": "object",
            "properties": {
                "caminho": {"type": "string", "description": "Caminho do arquivo a ser lido"}
            },
            "required": ["caminho"]
        }
    },
    {
        "name": "listar_arquivos",
        "description": "Lista arquivos e pastas em um diretório específico.",
        "input_schema": {
            "type": "object",
            "properties": {
                "diretorio": {"type": "string", "description": "O diretório para listar (default: '.')"}
            }
        }
    },
    {
        "name": "enviar_mensagem_imediata",
        "description": "Envia um texto ou resposta por voz IMEDIATAMENTE ao usuário (Telegram/Mic) enquanto você continua processando outras ferramentas em background. Use para evitar timeouts e silêncios longos.",
        "input_schema": {
            "type": "object",
            "properties": {
                "mensagem": {"type": "string", "description": "O conteúdo da resposta para o usuário (voz/texto)"}
            },
            "required": ["mensagem"]
        }
    }
]


class _HTMLTextExtractor(HTMLParser):
    """Extrai texto simples de HTML ignorando script/style."""

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            cleaned = " ".join(data.split())
            if cleaned:
                self._parts.append(cleaned)

    def get_text(self) -> str:
        return " ".join(self._parts)


def _fetch_url_text(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(url, headers=_DEFAULT_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        raw = response.read().decode(charset, errors="replace")
    return raw


def _normalize_result_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        params = urllib.parse.parse_qs(parsed.query)
        uddg = params.get("uddg")
        if uddg:
            return urllib.parse.unquote(uddg[0])
    return url


def _buscar_web(query: str, max_results: int = 3) -> str:
    """Pesquisa na web usando DuckDuckGo HTML e resume os principais resultados."""
    max_results = max(1, min(5, int(max_results or 3)))
    search_url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query)
    html = _fetch_url_text(search_url)

    pattern = re.compile(
        r'<a[^>]*class="result__a"[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?'
        r'<a[^>]*class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    results = []
    for match in pattern.finditer(html):
        href = _normalize_result_url(unescape(match.group("href")))
        title = re.sub(r"<.*?>", "", unescape(match.group("title"))).strip()
        snippet = re.sub(r"<.*?>", "", unescape(match.group("snippet"))).strip()
        if href.startswith("//"):
            href = "https:" + href
        if href.startswith("/"):
            continue
        if title and href:
            results.append((title, href, snippet))
        if len(results) >= max_results:
            break

    if not results:
        return f"Nenhum resultado encontrado para: {query}"

    linhas = [f"Resultados para: {query}"]
    for idx, (title, href, snippet) in enumerate(results, start=1):
        linhas.append(f"{idx}. {title}")
        linhas.append(f"URL: {href}")
        if snippet:
            linhas.append(f"Resumo: {snippet}")
    return "\n".join(linhas)


def _ler_url(url: str) -> str:
    """Lê uma URL e devolve título e texto útil da página."""
    url = _normalize_result_url(url)
    html = _fetch_url_text(url)
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = re.sub(r"\s+", " ", unescape(title_match.group(1))).strip() if title_match else url

    parser = _HTMLTextExtractor()
    parser.feed(html)
    text = re.sub(r"\s+", " ", parser.get_text()).strip()
    if len(text) > 2500:
        text = text[:2500] + " ..."

    return f"Título: {title}\nURL: {url}\nConteúdo:\n{text}"


async def _run_tool(tool_name: str, args: dict, user_id=0, notifier_callback=None) -> str:
    """Roteador local das ferramentas."""
    try:
        import os
        import webbrowser
        import asyncio
        from urllib.parse import quote_plus
        from utils.steam_scanner import escanear_jogos_steam
        from utils.memoria import salvar_fato
        
        if tool_name == "listar_jogos":
            jogos = escanear_jogos_steam()
            if not jogos:
                return "Erro: Nenhum jogo da Steam encontrado."
            lista = ", ".join(jogos.keys())
            return f"Sucesso. Jogos encontrados: {lista}"
            
        elif tool_name == "abrir_jogo":
            return _abrir_jogo(args.get("nome", ""))
            
        elif tool_name == "controle_midia":
            acao = args["acao"]
            from handlers.controle import ctrl_pausar, ctrl_proxima, ctrl_anterior
            if acao == "pausar": return ctrl_pausar()
            elif acao == "proxima": return ctrl_proxima()
            elif acao == "anterior": return ctrl_anterior()
            return "Ação inválida para controle_midia"
            
        elif tool_name == "controle_volume":
            acao = args["acao"]
            pct = str(args.get("percentual", 10))
            if acao == "set": return _volume_set(pct)
            elif acao == "up": return _volume("up", pct)
            elif acao == "down": return _volume("down", pct)
            elif acao == "mute": return _mute()
            return "Ação inválida para volume"
            
        elif tool_name == "buscar_midia":
            plat = args["acao"] if "acao" in args else args.get("plataforma")
            query = args.get("query", "")
            if plat == "spotify":
                if query:
                    os.startfile(f"spotify:search:{query}")
                    return f"Sucesso. Buscando no Spotify por: {query}"
                os.startfile("spotify:")
                return "Spotify aberto."
            elif plat == "youtube":
                if query:
                    url, t = _primeiro_video_youtube(query)
                    webbrowser.open(url)
                    return f"Sucesso. Abrindo video no youtube: {t}"
                webbrowser.open("https://www.youtube.com")
                return "YouTube aberto."
            elif plat == "netflix":
                if query:
                    webbrowser.open(f"https://www.netflix.com/search?q={quote_plus(query)}")
                    return f"Sucesso. Buscando na Netflix: {query}"
                webbrowser.open("https://www.netflix.com")
                return "Netflix aberto."
                
        elif tool_name == "controle_energia":
            acao = args["acao"]
            delay = args.get("delay_segundos", 60)
            if acao == "desligar":
                os.system(f"shutdown /s /t {delay}")
                return f"PC agendado para desligar em {delay}s."
            elif acao == "reiniciar":
                os.system(f"shutdown /r /t {delay}")
                return f"PC agendado para reiniciar em {delay}s."
            elif acao == "cancelar":
                os.system("shutdown /a")
                return "Shutdown cancelado."

        elif tool_name == "executar_plugin":
            plugin_name = args.get("nome", "").strip()
            query = args.get("query")
            return _executar_plugin_local(plugin_name, query)
        
        elif tool_name == "iniciar_criacao_comando":
            # Essa string servirá como Flag no loop do Claude para o Telegram agir!
            return "[CRIAR_COMANDO_INTENT]"
            
        elif tool_name == "executar_terminal":
            cmd = args.get("comando", "")
            try:
                # Usa asyncio para não travar o loop de eventos
                process = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                try:
                    # Timeout de 20s para o Jarvis não ficar no vácuo
                    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=20)
                    out = stdout.decode().strip()
                    err = stderr.decode().strip()
                except asyncio.TimeoutExpired:
                    # Se expirar, o processo continua rodando no SO, mas avisamos o Jarvis
                    return "Comando inicializado e rodando em background (timeout atingido)."

                # Combina stdout e stderr limitando cada um pra não ofuscar o erro!
                full_output = ""
                if out: 
                    # Trunca pesado para salvar tokens (Rate Limit 10K TPM)
                    if len(out) > 500: out = out[:250] + "\n...[truncado]...\n" + out[-250:]
                    full_output += f"STDOUT:\n{out}\n\n"
                    
                if err: 
                    if len(err) > 500: err = err[-500:] # Pega sempre o final do erro
                    full_output += f"STDERR:\n{err}\n\n"
                
                if full_output:
                    return full_output
                    
                return "Comando executado sem retorno na tela (provável sucesso)."
            except Exception as e:
                return f"Erro ao executar comando: {e}"

        elif tool_name == "buscar_web":
            query = args.get("query", "").strip()
            max_results = args.get("max_results", 3)
            if not query:
                return "Erro: query vazia para buscar_web."
            try:
                return _buscar_web(query, max_results)
            except Exception as e:
                return f"Erro ao pesquisar na web: {e}"

        elif tool_name == "ler_url":
            url = args.get("url", "").strip()
            if not url:
                return "Erro: url vazia para ler_url."
            try:
                return _ler_url(url)
            except Exception as e:
                return f"Erro ao ler URL: {e}"
                
        elif tool_name == "atualizar_memoria":
            f = args.get("fato", "")
            if f:
                return f"[SAVE_MEMORY]{f}"
            return "Nada para salvar."
            
        elif tool_name == "escrever_arquivo":
            path = args.get("caminho")
            content = args.get("conteudo") or args.get("content")
            
            if not path or not content:
                return "Erro: 'caminho' e 'conteudo' são obrigatórios para escrever_arquivo."
                
            try:
                # Garante que o diretório pai existe
                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                return f"Sucesso: Arquivo '{path}' criado com {len(content)} bytes."
            except Exception as e:
                return f"Erro ao escrever arquivo: {e}"

        elif tool_name == "ler_arquivo":
            path = args["caminho"]
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                if len(content) > 2000:
                    content = content[:1000] + "\n...[truncado]...\n" + content[-1000:]
                return f"CONTEÚDO DE {path}:\n\n{content}"
            except Exception as e:
                return f"Erro ao ler arquivo: {e}"

        elif tool_name == "listar_arquivos":
            folder = args.get("diretorio", ".")
            try:
                items = os.listdir(folder)
                return f"ITENS EM {folder}:\n" + "\n".join([f"- {i}" for i in items])
            except Exception as e:
                return f"Erro ao listar diretório: {e}"
                
        elif tool_name == "enviar_mensagem_imediata":
            msg = args.get("mensagem", "")
            if notifier_callback and msg:
                # Chamada assíncrona para notificar o usuário "no meio" do loop
                await notifier_callback(msg)
                return f"Sucesso: Mensagem enviada ao usuário: {msg[:50]}..."
            return "Erro: Callback de notificação não disponível nesta sessão."
            
    except Exception as e:
        logger.error(f"Erro na tool {tool_name}: {e}")
        return f"Erro ao executar {tool_name}: {e}"
        
    return f"Ferramenta desconhecida."


async def run_orchestrator(user_text: str, chat_history: list = None, user_id: int = 0, is_mic: bool = False, notifier_callback=None) -> dict:
    """
    Controla o fluxo da IA com Tools.
    notifier_callback: função assíncrona(msg) para enviar respostas parciais.
    """
    if chat_history is None:
        chat_history = []
        
    wants_to_learn = False
    games_listed = []

    lock = _USER_LOCKS[user_id]
    if lock.locked():
        logger.info(f"Orchestrator ocupado para user_id={user_id}; recusando nova execução concorrente.")
        busy_response = (
            "Ainda estou processando sua solicitação anterior. Aguarde um instante."
            if not is_mic else
            "Ainda estou finalizando a tarefa anterior. Aguarde um instante."
        )
        return {
            "response": busy_response,
            "wants_to_learn": False,
            "games_listed": [],
            "new_history": chat_history,
        }

    async with lock:
        return await _run_orchestrator_locked(
            user_text=user_text,
            chat_history=chat_history,
            user_id=user_id,
            is_mic=is_mic,
            notifier_callback=notifier_callback,
        )


async def _post_with_backoff(client: httpx.AsyncClient, headers: dict, payload: dict, user_id: int) -> httpx.Response | None:
    """Envia a requisição para Anthropic com backoff exponencial quando recebe 429."""
    for tentativa in range(1, _MAX_API_RETRIES + 1):
        response = await client.post(ANTHROPIC_API_URL, headers=headers, json=payload)
        if response.status_code != 429:
            return response

        retry_after_header = response.headers.get("retry-after")
        try:
            retry_after = int(retry_after_header) if retry_after_header else 0
        except ValueError:
            retry_after = 0

        wait_seconds = retry_after if retry_after > 0 else _BACKOFF_BASE_SECONDS ** (tentativa - 1)
        logger.warning(
            "Anthropic rate limit para user_id=%s na tentativa %s/%s. Aguardando %ss.",
            user_id,
            tentativa,
            _MAX_API_RETRIES,
            wait_seconds,
        )
        await asyncio.sleep(wait_seconds)

    return None


def _executar_plugin_local(plugin_name: str, query: str | None = None) -> str:
    """Executa um plugin local da pasta plugins/ usando run(query) ou run(args)."""
    if not plugin_name:
        return "Erro: nome do plugin não informado."

    plugin_path = os.path.join(_PLUGINS_DIR, f"{plugin_name}.py")
    if not os.path.exists(plugin_path):
        return f"Erro: plugin '{plugin_name}' não encontrado."

    try:
        spec = importlib.util.spec_from_file_location(f"plugins.{plugin_name}", plugin_path)
        if not spec or not spec.loader:
            return f"Erro: não foi possível carregar o plugin '{plugin_name}'."

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        run_fn = getattr(module, "run", None)
        if not callable(run_fn):
            return f"Erro: plugin '{plugin_name}' não possui função run()."

        try:
            result = run_fn(query)
        except TypeError:
            result = run_fn({"query": query} if query else {})

        return str(result)
    except Exception as e:
        logger.error("Erro ao executar plugin local %s: %s", plugin_name, e, exc_info=True)
        return f"Erro ao executar plugin '{plugin_name}': {e}"


def _rotear_plugin_direto(user_text: str) -> tuple[str, str | None] | None:
    """Atalho local apenas para casos deterministicos e não sensíveis a dados atuais."""
    return None


def _extrair_time_futebol(texto: str) -> str:
    match = re.search(r"\b(?:do|da|de)\s+([a-z0-9\s_-]+)\??$", texto)
    if match:
        time = match.group(1).strip()
        time = re.sub(r"\b(agora|hoje|amanh[ãa]|por favor|pra mim|para mim)\b", "", time).strip()
        return time or "flamengo"
    return "flamengo"


def _parece_consulta_futebol(texto: str) -> bool:
    termos_futebol = [
        "jogo do",
        "jogo da",
        "partida do",
        "partida da",
        "flamengo",
        "vasco",
        "palmeiras",
        "corinthians",
        "sao paulo",
        "são paulo",
        "botafogo",
        "fluminense",
        "gremio",
        "grêmio",
        "internacional",
        "cruzeiro",
        "atletico",
        "atlético",
    ]
    return any(termo in texto for termo in termos_futebol)


def _normalizar_content_para_texto(content) -> str:
    """Converte conteúdo do histórico para texto, inclusive blocos estruturados."""
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        partes = []
        for item in content:
            if isinstance(item, dict):
                texto = item.get("text")
                if isinstance(texto, str):
                    partes.append(texto)
                    continue

                inner = item.get("content")
                if isinstance(inner, str):
                    partes.append(inner)
            elif isinstance(item, str):
                partes.append(item)
        return " ".join(partes)

    if content is None:
        return ""

    return str(content)


def try_local_route(user_text: str) -> str | None:
    """Executa atalhos locais determinísticos antes de acionar a IA."""
    plugin_route = _rotear_plugin_direto(user_text)
    if not plugin_route:
        return None

    plugin_name, plugin_query = plugin_route
    logger.info(
        "Roteamento local antecipado para plugin '%s' com query='%s' e texto='%s'",
        plugin_name,
        plugin_query,
        user_text,
    )
    return _executar_plugin_local(plugin_name, plugin_query)


async def _run_orchestrator_locked(user_text: str, chat_history: list, user_id: int, is_mic: bool, notifier_callback) -> dict:
    wants_to_learn = False
    games_listed = []
    original_user_text = user_text

    # FILTRO DE MEMÓRIA (Antítese do Erro)
    limpar = ["negativo", "apenas via texto", "sem módulo de audição", "não posso ouvir", "não falar", "exclusivamente texto", "não te ouço"]
    filtered_history = []
    for m in chat_history:
        content_texto = _normalizar_content_para_texto(m.get("content", ""))
        normalized_message = dict(m)
        normalized_message["content"] = content_texto
        if normalized_message.get("role") == "assistant" and any(token in content_texto.lower() for token in limpar):
            normalized_message["content"] = "Sistemas sincronizados e resposta vocal ativa."
        filtered_history.append(normalized_message)

    if is_mic:
        user_text = f"[MIC_INPUT] {user_text}"

    plugin_result = try_local_route(original_user_text)
    if plugin_result is not None:
        new_history = list(chat_history)
        new_history.append({"role": "user", "content": user_text})
        new_history.append({"role": "assistant", "content": plugin_result})
        return {
            "response": plugin_result,
            "wants_to_learn": False,
            "games_listed": [],
            "new_history": new_history[-20:],
        }

    messages = list(filtered_history)
    messages.append({"role": "user", "content": user_text})
    
    mem = carregar_memoria_longa(user_id)
    contexto_memoria = ""
    fatos = mem.get("fatos", [])
    if fatos:
        lista_formatada = "\n".join([f"- {f}" for f in fatos])
        contexto_memoria = f"\n\nFATOS SOBRE O USUÁRIO (Memorizados anteriormente):\n{lista_formatada}"
    
    contexto_sessao = (
        "\n\n[SISTEMA: VOCÊ ESTÁ OUVINDO E FALANDO PELO MICROFONE DO PC AGORA. "
        "RESPONDA VOCALMENTE COM FRASES CURTAS, NATURAIS E FÁCEIS DE FALAR. "
        "EVITE LISTAS, EXCESSO DE DETALHES, EMOJIS, MARKDOWN E TOM DE TEXTO ESCRITO.]"
        if is_mic else ""
    )
    prompt_personalizado = SYSTEM_ORCHESTRATOR + contexto_memoria + contexto_sessao + "\n\n[PRIORIDADE: Se uma tarefa demorar mais de 2 segundos, use 'enviar_mensagem_imediata' para avisar o usuário que você está trabalhando antes de continuar.]"

    headers = {
        "x-api-key": _get_api_key(),
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            for turn_index in range(_MAX_TURNS):
                logger.info(
                    "Orchestrator turno %s/%s para user_id=%s",
                    turn_index + 1,
                    _MAX_TURNS,
                    user_id,
                )
                payload = {
                    "model": MODEL,
                    "max_tokens": 1024,
                    "system": prompt_personalizado,
                    "messages": messages,
                    "tools": TOOLS
                }

                response = await _post_with_backoff(client, headers, payload, user_id)
                if response is None:
                    return {
                        "response": "⚠️ A Anthropic está ocupada no momento. Tente novamente em alguns instantes.",
                        "new_history": chat_history
                    }

                if response.status_code != 200:
                    logger.error(
                        "Falha Anthropic para user_id=%s com status=%s: %s",
                        user_id,
                        response.status_code,
                        response.text[:300],
                    )
                    return {"response": "⚠️ Erro de rede Anthropic.", "new_history": chat_history}

                data = response.json()
                assistant_message = {"role": "assistant", "content": data.get("content", [])}
                messages.append(assistant_message)
                
                tool_uses = [c for c in data["content"] if c["type"] == "tool_use"]
                
                if not tool_uses:
                    texts = [c["text"] for c in data["content"] if c["type"] == "text"]
                    final_text = "".join(texts)
                    
                    new_history = list(chat_history)
                    new_history.append({"role": "user", "content": user_text})
                    new_history.append({"role": "assistant", "content": final_text})
                    
                    return {
                        "response": final_text, 
                        "wants_to_learn": wants_to_learn, 
                        "games_listed": games_listed,
                        "new_history": new_history[-20:]
                    }

                tool_results_content = []
                for tu in tool_uses:
                    t_name = tu["name"]
                    t_args = tu["input"]
                    
                    t_res = await _run_tool(t_name, t_args, user_id=user_id, notifier_callback=notifier_callback)
                    
                    # Trata o retorno das ferramentas
                    if t_res.startswith("[SAVE_MEMORY]"):
                        fato_real = t_res.replace("[SAVE_MEMORY]", "")
                        salvar_fato(user_id, fato_real)
                        t_res = f"Fato memorizado: '{fato_real}'"
                    
                    if t_name == "listar_jogos":
                        from utils.steam_scanner import escanear_jogos_steam
                        jogos = escanear_jogos_steam()
                        if jogos: games_listed = list(jogos.keys())

                    if t_res == "[CRIAR_COMANDO_INTENT]":
                        wants_to_learn = True
                        t_res = "Sinal de criação enviado."

                    tool_results_content.append({
                        "type": "tool_result",
                        "tool_use_id": tu["id"],
                        "content": t_res
                    })
                
                messages.append({"role": "user", "content": tool_results_content})
                
            logger.warning(
                "Orchestrator atingiu o limite de turnos (%s) para user_id=%s.",
                _MAX_TURNS,
                user_id,
            )
            return {
                "response": "Concluí o que foi possível nesta rodada. Se quiser, pode repetir ou refinar o pedido.",
                "wants_to_learn": wants_to_learn,
                "games_listed": games_listed,
                "new_history": messages[-20:]
            }
            
    except Exception as e:
        logger.error(f"Erro no run_orchestrator: {e}", exc_info=True)
        return {"response": f"Erro interno (Orchestrator): {e}", "wants_to_learn": False, "games_listed": [], "new_history": chat_history}

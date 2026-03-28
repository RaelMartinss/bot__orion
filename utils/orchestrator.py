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
from utils.claude_client import _get_api_key, ANTHROPIC_API_URL, MODEL
from utils.executor import (
    _abrir_jogo, _volume_set, _volume, _mute,
    _primeiro_video_youtube
)
from utils.steam_scanner import escanear_jogos_steam

logger = logging.getLogger(__name__)

SYSTEM_ORCHESTRATOR = """Você é o ORION, um assistente de sistema avançado (estilo Jarvis do Homem de Ferro) rodando no PC Windows do usuário.
Você é direto, confiante, técnico e levemente sarcástico/elegante.

COMPORTAMENTO OBRIGATÓRIO (MUITO IMPORTANTE):
- NUNCA aja como um tutorial. NUNCA peça instruções passo a passo ou peça que o usuário preencha campos.
- NUNCA mande o usuário "copiar e colar" ou "fazer as coisas" manualmente. Você orquestra tudo.
- Fale como um sistema inteligente no controle (ex: "Entendido. Preparando ambiente", "Simulando execução...").
- Se não houver ferramenta para uma ação, chame `iniciar_criacao_comando` IMEDIATAMENTE e apenas diga que está "iniciando o protocolo de aprendizado do sistema". Não peça pro usuário descrever passo a passo com exemplos.
- Use humor rápido, leve e sutil apenas quando apropriado (erros óbvios, insistência do usuário).

REGRAS DE FERRAMENTAS:
1. Jogos/Steam? Use `listar_jogos` primeiro. Se da lista, use `abrir_jogo(nome)`.
2. Tocar música/vídeo? Use `buscar_midia`.
3. Volumes? Use `controle_volume`.
4. Midia (Play/Pause)? Use `controle_midia`.
5. Executar Tarefas de Sistema ou Projetos (ex: criar pasta, rodar scripts, npm, git, comandos do SO, processos longos): Use `executar_terminal` diretamente. Resolva a tarefa sem precisar criar ou aprender novos comandos a não ser que o usuário peça expressamente para você "aprender" ou "criar atalho".
6. Automações Permanentes/Aprender novo Comando do Bot: APENAS se o usuário explicitamente pedir "aproveita e aprende esse truque" ou "cria um atalho/comando pra isso", chame `iniciar_criacao_comando`.

Não envie emoticons exagerados. Respostas devem ser viscerais de máquina (ex: "Comando executado. Ferramenta pronta.").
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
    }
]

def _run_tool(tool_name: str, args: dict) -> str:
    """Roteador local das ferramentas."""
    try:
        import os
        import webbrowser
        from urllib.parse import quote_plus
        
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
        
        elif tool_name == "iniciar_criacao_comando":
            # Essa string servirá como Flag no loop do Claude para o Telegram agir!
            return "[CRIAR_COMANDO_INTENT]"
            
        elif tool_name == "executar_terminal":
            import subprocess
            cmd = args.get("comando", "")
            try:
                # Usa timeout maior pois ações reais de sistema (npm init, criações) demoram mais
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20)
                out = result.stdout.strip()
                err = result.stderr.strip()
                
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
            except subprocess.TimeoutExpired:
                # Comandos muito grandes expiram, mas continuam rodando no background.
                return "Comando inicializado e rodando em background."
            except Exception as e:
                return f"Erro ao executar comando: {e}"
            
    except Exception as e:
        logger.error(f"Erro na tool {tool_name}: {e}")
        return f"Erro ao executar {tool_name}: {e}"
        
    return f"Ferramenta desconhecida."


async def run_orchestrator(user_text: str, chat_history: list = None) -> dict:
    """
    Controla o fluxo da IA com Tools.
    Retorna: {
      "response": "Texto pra enviar ao usuário",
      "wants_to_learn": True/False (Se usou 'iniciar_criacao_comando'),
      "new_history": Lista atualizada de histórico
    }
    """
    if chat_history is None:
        chat_history = []
        
    # Inicializamos enviando o histórico anterior contendo textos
    messages = list(chat_history)
    messages.append({"role": "user", "content": user_text})
    
    headers = {
        "x-api-key": _get_api_key(),
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    
    max_turns = 10
    wants_to_learn = False
    games_listed = []
    
    try:
        import asyncio
        async with httpx.AsyncClient(timeout=60.0) as client:
            for _ in range(max_turns):
                payload = {
                    "model": MODEL,
                    "max_tokens": 1024,
                    "system": SYSTEM_ORCHESTRATOR,
                    "messages": messages,
                    "tools": TOOLS
                }
                
                response = None
                # Auto-retry para Rate Limits (429) e sobrecargas
                for tentativa in range(3):
                    response = await client.post(ANTHROPIC_API_URL, headers=headers, json=payload)
                    if response.status_code == 429:
                        logger.warning("Rate Limit Anthropic (429). Aguardando 15s para backoff...")
                        await asyncio.sleep(15)
                        continue
                    break
                    
                if response is None or response.status_code != 200:
                    logger.error(f"Erro Anthropic Orchestrator: {response.text if response else 'Timeou após retries'}")
                    return {"response": "⚠️ Limite de rede atingido da Anthropic.", "wants_to_learn": False, "new_history": chat_history}

                data = response.json()
                assistant_message = {"role": "assistant", "content": data.get("content", [])}
                messages.append(assistant_message)
                
                # Procura no output se ele usou uma Tool (também pode ter mandado texto junto)
                tool_uses = [c for c in data["content"] if c["type"] == "tool_use"]
                
                if not tool_uses:
                    # Se não usar, ele respondeu normalmente. Parar loop.
                    texts = [c["text"] for c in data["content"] if c["type"] == "text"]
                    final_text = "".join(texts)
                    
                    # Atualiza histórico para retornar à UI salvando apenas as falas textuais (não gasta RAM com logs de tool internal)
                    new_history = list(chat_history)
                    new_history.append({"role": "user", "content": user_text})
                    new_history.append({"role": "assistant", "content": final_text})
                    
                    # Limita memória pra 10 turnos (20 msgs)
                    if len(new_history) > 20: 
                        new_history = new_history[-20:]
                        
                    return {
                        "response": final_text, 
                        "wants_to_learn": wants_to_learn, 
                        "games_listed": games_listed,
                        "new_history": new_history
                    }

                # Executa todas as ferramentas pedidas
                tool_results_content = []
                for tu in tool_uses:
                    t_name = tu["name"]
                    t_args = tu["input"]
                    logger.info(f"Orquestrador acionou tool: {t_name} args={t_args}")
                    
                    t_res = _run_tool(t_name, t_args)
                    
                    if t_name == "listar_jogos":
                        from utils.steam_scanner import escanear_jogos_steam
                        jogos = escanear_jogos_steam()
                        if jogos:
                            games_listed = list(jogos.keys())

                    if t_res == "[CRIAR_COMANDO_INTENT]":
                        wants_to_learn = True
                        t_res = "Sinal de criação enviado com sucesso. Acionei os botões na UI do cliente!"
                    
                    tool_results_content.append({
                        "type": "tool_result",
                        "tool_use_id": tu["id"],
                        "content": t_res
                    })
                
                # Devolve o resultado das tools pro Claude
                messages.append({
                    "role": "user",
                    "content": tool_results_content
                })
                
            # Se esgotou os turnos
            new_history = list(chat_history)
            new_history.append({"role": "user", "content": user_text})
            new_history.append({"role": "assistant", "content": "Processamento assíncrono estendido ao máximo. Rotina em progresso no background."})
            return {"response": "Processamento assíncrono estendido ao máximo. Rotinas complexas ainda rodando ou finalizadas em background.", "wants_to_learn": wants_to_learn, "games_listed": games_listed, "new_history": new_history[-20:]}
            
    except Exception as e:
        logger.error(f"Erro no run_orchestrator: {e}", exc_info=True)
        return {"response": f"Erro interno (Orchestrator): {e}", "wants_to_learn": False, "games_listed": [], "new_history": chat_history}

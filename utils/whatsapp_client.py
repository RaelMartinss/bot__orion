"""
utils/whatsapp_client.py

Cliente Python para o servidor WhatsApp local (whatsapp_server/server.js).
O servidor Node.js deve estar rodando em http://localhost:3131.

Iniciar o servidor:
    cd whatsapp_server && node server.js

Na primeira vez, escaneie o QR Code que aparece no terminal do servidor.
A sessão fica salva em whatsapp_server/sessao_wpp/ — não precisa escanear de novo.
"""

import json
import logging
import subprocess
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_BASE_URL = "http://localhost:3131"
_SERVER_DIR = Path(__file__).parent.parent / "whatsapp_server"
_CONTATOS_FILE = Path("memoria/whatsapp_contatos.json")


_contatos_cache: dict[str, str] | None = None  # cache em memória; None = não carregado ainda


def _carregar_contatos() -> dict[str, str]:
    """Carrega contatos do disco com cache em memória (sem I/O repetido por lookup)."""
    global _contatos_cache
    if _contatos_cache is None:
        if _CONTATOS_FILE.exists():
            try:
                _contatos_cache = json.loads(_CONTATOS_FILE.read_text(encoding="utf-8"))
            except Exception:
                _contatos_cache = {}
        else:
            _contatos_cache = {}
    return _contatos_cache


def _salvar_contatos(contatos: dict[str, str]) -> None:
    global _contatos_cache
    _CONTATOS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CONTATOS_FILE.write_text(json.dumps(contatos, ensure_ascii=False, indent=2), encoding="utf-8")
    _contatos_cache = contatos  # mantém cache sincronizado


def salvar_contato(nome: str, numero: str) -> str:
    """
    Salva ou atualiza um contato no arquivo persistente.
    nome: qualquer apelido (ex: 'amor', 'Junior')
    numero: só dígitos com DDI (ex: '5598988537727')
    """
    numero_limpo = numero.replace("+", "").replace(" ", "").replace("-", "")
    contatos = _carregar_contatos()
    contatos[nome.lower().strip()] = numero_limpo
    _salvar_contatos(contatos)
    return f"✅ Contato *{nome}* salvo: {numero_limpo}"


# ── Controle do servidor ──────────────────────────────────────────────────────

def servidor_online() -> bool:
    """Verifica se o servidor Node.js está respondendo."""
    try:
        import urllib.request
        with urllib.request.urlopen(f"{_BASE_URL}/status", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def _servidor_saudavel() -> bool:
    """Verifica se o Puppeteer do servidor está funcional (não só online)."""
    try:
        import urllib.request
        with urllib.request.urlopen(f"{_BASE_URL}/health", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


_servidor_pid: int | None = None  # PID do processo node iniciado por nós
_iniciar_lock = __import__("threading").Lock()


def _matar_servidor() -> None:
    """Encerra apenas o processo Node.js que foi iniciado por este módulo (por PID)."""
    global _servidor_pid
    import time
    if _servidor_pid is not None:
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(_servidor_pid)],
                capture_output=True, timeout=5
            )
        except Exception:
            pass
        _servidor_pid = None
    time.sleep(1)


def iniciar_servidor(aguardar_conexao: bool = True, timeout: int = 30) -> str:
    """
    Inicia o servidor Node.js em background se não estiver rodando.
    Se o servidor estiver online mas com Puppeteer morto (detached frame), reinicia.
    Thread-safe: usa lock para evitar múltiplas polls simultâneas.
    """
    global _servidor_pid
    with _iniciar_lock:
        if servidor_online():
            st = status()
            if st.get("pronto"):
                if _servidor_saudavel():
                    return "conectado"
                logger.warning("📱 Servidor WhatsApp com Puppeteer inativo — reiniciando...")
                _matar_servidor()
        else:
            try:
                proc = subprocess.Popen(
                    ["node", "server.js"],
                    cwd=str(_SERVER_DIR),
                    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                _servidor_pid = proc.pid
            except Exception as e:
                return f"❌ Erro ao iniciar servidor WhatsApp: {e}"

    if not aguardar_conexao:
        return "iniciando"

    import time
    inicio = time.time()
    while time.time() - inicio < timeout:
        time.sleep(2)
        if not servidor_online():
            continue
        st = status()
        if st.get("pronto"):
            return "conectado"
        if st.get("estado") == "qr":
            return "qr"  # precisa escanear QR

    return "timeout"


# ── API calls ─────────────────────────────────────────────────────────────────

def _get(endpoint: str) -> dict:
    import urllib.request
    with urllib.request.urlopen(f"{_BASE_URL}{endpoint}", timeout=10) as r:
        return json.loads(r.read())


def _post(endpoint: str, dados: dict) -> dict:
    import urllib.request
    import urllib.error
    body = json.dumps(dados).encode()
    req = urllib.request.Request(
        f"{_BASE_URL}{endpoint}", data=body,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        # Lê o corpo do erro para pegar a mensagem real do servidor Node.js
        try:
            body_err = json.loads(e.read())
            return {"ok": False, "erro": body_err.get("erro", str(e))}
        except Exception:
            return {"ok": False, "erro": f"HTTP {e.code}"}


# ── Funções públicas ──────────────────────────────────────────────────────────

def status() -> dict:
    """Retorna estado da conexão WhatsApp."""
    try:
        return _get("/status")
    except Exception:
        return {"estado": "servidor_offline", "pronto": False}


def get_qr() -> str | None:
    """Retorna o QR code atual para escanear (string raw)."""
    try:
        data = _get("/qr")
        return data.get("qr")
    except Exception:
        return None


def _score_nome(query: str, candidato: str) -> int:
    """
    Retorna score de semelhança entre query e candidato (ambos lowercase).
    Maior = melhor match.
    """
    if query == candidato:
        return 100
    if query in candidato or candidato in query:
        return 80
    palavras = query.split()
    matches = sum(1 for p in palavras if p in candidato and len(p) > 2)
    if matches == len(palavras):
        return 70
    if matches > 0:
        return 40 + (matches * 10)
    return 0


def resolver_numero(nome_ou_numero: str) -> str | None:
    """
    Resolve nome amigável para número de telefone.
    Tenta: contatos persistidos em disco → lista de contatos do WhatsApp.
    Usa scoring flexível para nomes parciais ("Luiz Henrique" → "Luiz Henrique Silva").
    """
    if nome_ou_numero.replace("+", "").replace(" ", "").isdigit():
        return nome_ou_numero.replace("+", "").replace(" ", "")

    nome_lower = nome_ou_numero.lower().strip()

    # 1. Contatos salvos localmente
    melhor_score, melhor_numero = 0, None
    for nome, numero in _carregar_contatos().items():
        s = _score_nome(nome_lower, nome.lower())
        if s > melhor_score:
            melhor_score, melhor_numero = s, numero
    if melhor_score >= 70:
        return melhor_numero

    # 2. Contatos do WhatsApp
    try:
        data = _get("/contatos")
        for c in data.get("contatos", []):
            nome_c = c.get("nome", "").lower()
            if not nome_c:
                continue
            s = _score_nome(nome_lower, nome_c)
            if s > melhor_score:
                melhor_score, melhor_numero = s, c["numero"]
    except Exception:
        pass

    if melhor_score >= 40:
        return melhor_numero

    return None


def enviar_mensagem(para: str, mensagem: str) -> str:
    """
    Envia mensagem WhatsApp.
    'para' pode ser nome do contato ou número (com DDI).
    """
    if not servidor_online():
        resultado = iniciar_servidor()
        if "offline" in resultado.lower() or "Erro" in resultado:
            return f"❌ Servidor WhatsApp offline. {resultado}"

    st = status()
    if not st.get("pronto"):
        estado = st.get("estado", "desconhecido")
        if estado == "qr":
            return "📱 WhatsApp aguardando QR Code. Diga *'mostra o QR do WhatsApp'* para escanear."
        return f"❌ WhatsApp não conectado. Estado: {estado}"

    numero = resolver_numero(para)
    if not numero:
        return f"❌ Não encontrei o contato *{para}*. Use o número completo com DDI (ex: 5511999999999)."

    try:
        resultado = _post("/send", {"para": numero, "mensagem": mensagem})
        if resultado.get("ok"):
            return f"✅ Mensagem enviada para *{para}*: _{mensagem}_"
        return f"❌ Erro ao enviar: {resultado.get('erro', 'desconhecido')}"
    except Exception as e:
        return f"❌ Erro: {e}"

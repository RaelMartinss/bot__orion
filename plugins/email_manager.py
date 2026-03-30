"""
plugins/email_manager.py

Integração completa com Gmail via IMAP/SMTP.
Suporta: ler, buscar, enviar, resumir, alertar não-lidos.

Credenciais: lidas do gmail_reader.py (já configurado) ou de variáveis de ambiente.
"""

import imaplib
import smtplib
import email as emaillib
import os
import logging
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import parseaddr
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Credenciais ───────────────────────────────────────────────────────────────
# Prioridade: variável de ambiente > hardcoded no gmail_reader
def _get_credentials() -> tuple[str, str]:
    email_addr = os.environ.get("EMAIL_ADDRESS", "")
    app_pwd = os.environ.get("EMAIL_APP_PASSWORD", "")
    if not email_addr or not app_pwd:
        # Fallback: importa do plugin existente
        try:
            import importlib.util, pathlib
            spec = importlib.util.spec_from_file_location(
                "gmail_reader",
                pathlib.Path(__file__).parent / "gmail_reader.py"
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            email_addr = getattr(mod, "EMAIL", email_addr)
            app_pwd = getattr(mod, "APP_PASSWORD", app_pwd).replace(" ", "")
        except Exception:
            pass
    return email_addr, app_pwd.replace(" ", "")


def _conectar_imap() -> imaplib.IMAP4_SSL:
    email_addr, app_pwd = _get_credentials()
    if not email_addr or not app_pwd:
        raise RuntimeError("Credenciais de e-mail não configuradas.")
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(email_addr, app_pwd)
    return mail


def _decode_header_str(valor: str | None) -> str:
    if not valor:
        return ""
    partes = decode_header(valor)
    resultado = []
    for parte, enc in partes:
        if isinstance(parte, bytes):
            resultado.append(parte.decode(enc or "utf-8", errors="replace"))
        else:
            resultado.append(str(parte))
    return " ".join(resultado)


def _extrair_texto(msg) -> str:
    """Extrai o corpo de texto de uma mensagem (plain text)."""
    corpo = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            disp = str(part.get("Content-Disposition", ""))
            if ct == "text/plain" and "attachment" not in disp:
                charset = part.get_content_charset() or "utf-8"
                corpo = part.get_payload(decode=True).decode(charset, errors="replace")
                break
    else:
        charset = msg.get_content_charset() or "utf-8"
        corpo = msg.get_payload(decode=True).decode(charset, errors="replace")
    return corpo.strip()


def _parse_email(msg_bytes: bytes) -> dict:
    msg = emaillib.message_from_bytes(msg_bytes)
    return {
        "assunto": _decode_header_str(msg["Subject"]),
        "de": _decode_header_str(msg["From"]),
        "para": _decode_header_str(msg["To"]),
        "data": msg.get("Date", ""),
        "message_id": msg.get("Message-ID", ""),
        "corpo": _extrair_texto(msg)[:1000],  # Limita para não explodir tokens
    }


# ── Leitura ───────────────────────────────────────────────────────────────────

def ler_inbox(n: int = 5, apenas_nao_lidos: bool = False) -> list[dict]:
    mail = _conectar_imap()
    mail.select("inbox")
    criterio = "UNSEEN" if apenas_nao_lidos else "ALL"
    _, ids = mail.search(None, criterio)
    email_ids = ids[0].split()
    ultimos = email_ids[-n:][::-1]  # Mais recentes primeiro
    resultado = []
    for eid in ultimos:
        _, data = mail.fetch(eid, "(RFC822)")
        for parte in data:
            if isinstance(parte, tuple):
                resultado.append(_parse_email(parte[1]))
    mail.logout()
    return resultado


def contar_nao_lidos() -> int:
    try:
        mail = _conectar_imap()
        mail.select("inbox")
        _, ids = mail.search(None, "UNSEEN")
        count = len(ids[0].split()) if ids[0] else 0
        mail.logout()
        return count
    except Exception as e:
        logger.error("Erro ao contar não-lidos: %s", e)
        return -1


def buscar_emails(query: str, n: int = 5) -> list[dict]:
    """Busca por remetente ou assunto contendo a query."""
    mail = _conectar_imap()
    mail.select("inbox")
    # Tenta por assunto, depois por remetente
    _, ids_assunto = mail.search(None, f'SUBJECT "{query}"')
    _, ids_de = mail.search(None, f'FROM "{query}"')
    todos = list(set(ids_assunto[0].split() + ids_de[0].split()))
    ultimos = sorted(todos)[-n:][::-1]
    resultado = []
    for eid in ultimos:
        _, data = mail.fetch(eid, "(RFC822)")
        for parte in data:
            if isinstance(parte, tuple):
                resultado.append(_parse_email(parte[1]))
    mail.logout()
    return resultado


# ── Envio ─────────────────────────────────────────────────────────────────────

def enviar_email(para: str, assunto: str, corpo: str) -> str:
    """Envia e-mail via SMTP."""
    email_addr, app_pwd = _get_credentials()
    if not email_addr or not app_pwd:
        return "❌ Credenciais não configuradas."
    msg = MIMEMultipart()
    msg["From"] = email_addr
    msg["To"] = para
    msg["Subject"] = assunto
    msg.attach(MIMEText(corpo, "plain", "utf-8"))
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(email_addr, app_pwd)
            server.sendmail(email_addr, para, msg.as_string())
        return f"✅ E-mail enviado para *{para}*."
    except Exception as e:
        return f"❌ Erro ao enviar: {e}"


# ── Formatação ────────────────────────────────────────────────────────────────

def _formatar_email(e: dict, idx: int = 0, resumido: bool = True) -> str:
    remetente = parseaddr(e["de"])[0] or e["de"]
    linha = f"*{idx+1}.* 📧 {remetente}\n📌 {e['assunto']}\n📅 {e['data'][:16]}"
    if not resumido and e["corpo"]:
        linha += f"\n\n{e['corpo'][:400]}"
    return linha


# ── Entry points (chamados pelo executor/orchestrator) ─────────────────────────

def run(args=None) -> str:
    """Compatibilidade com sistema de plugins — mostra resumo da inbox."""
    return resumo_inbox()


def resumo_inbox(n: int = 5) -> str:
    try:
        nao_lidos = contar_nao_lidos()
        emails = ler_inbox(n=n)
        if not emails:
            return "📭 Nenhum e-mail encontrado."
        header = f"📬 *Caixa de entrada* — {nao_lidos} não lido(s)\n\n"
        linhas = [_formatar_email(e, i) for i, e in enumerate(emails)]
        return header + "\n\n".join(linhas)
    except Exception as e:
        return f"❌ Erro ao acessar e-mail: {e}"


def resumo_nao_lidos() -> str:
    try:
        emails = ler_inbox(n=10, apenas_nao_lidos=True)
        if not emails:
            return "✅ Nenhum e-mail não lido."
        linhas = [_formatar_email(e, i) for i, e in enumerate(emails)]
        return f"📬 *{len(emails)} não lido(s):*\n\n" + "\n\n".join(linhas)
    except Exception as e:
        return f"❌ Erro: {e}"


def resultado_busca(query: str) -> str:
    try:
        emails = buscar_emails(query)
        if not emails:
            return f"📭 Nenhum e-mail encontrado para: *{query}*"
        linhas = [_formatar_email(e, i) for i, e in enumerate(emails)]
        return f"🔍 *Resultados para '{query}':*\n\n" + "\n\n".join(linhas)
    except Exception as e:
        return f"❌ Erro na busca: {e}"


def ler_mais_recente() -> str:
    try:
        emails = ler_inbox(n=1)
        if not emails:
            return "📭 Nenhum e-mail."
        return _formatar_email(emails[0], resumido=False)
    except Exception as e:
        return f"❌ Erro: {e}"

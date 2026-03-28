import imaplib
import email
from email.header import decode_header

EMAIL = "raelpgm2@gmail.com"
APP_PASSWORD = "zwfy aruq fadb kmqx"

def run(args=None):
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL, APP_PASSWORD.replace(" ", ""))
        mail.select("inbox")

        status, messages = mail.search(None, "ALL")
        mail_ids = messages[0].split()
        latest_ids = mail_ids[-5:][::-1]  # últimos 5, mais recente primeiro

        resultado = []
        for mid in latest_ids:
            status, msg_data = mail.fetch(mid, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])

                    # Assunto
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding or "utf-8", errors="ignore")

                    # Remetente
                    from_ = msg.get("From", "")

                    # Data
                    date_ = msg.get("Date", "")

                    resultado.append(f"📧 De: {from_}\n📌 Assunto: {subject}\n📅 Data: {date_}")

        mail.logout()

        if resultado:
            return "\n\n".join(resultado)
        else:
            return "Nenhum e-mail encontrado."

    except Exception as e:
        return f"Erro ao acessar Gmail: {str(e)}"

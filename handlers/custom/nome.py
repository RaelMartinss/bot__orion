"""
handlers/custom/nome.py
Cria um novo projeto Node.js com npm init -y em um diretório especificado pelo usuário.
"""
import os
import subprocess
import logging

logger = logging.getLogger(__name__)


async def nome(update, context):
    """
    /nome <nome_do_projeto> — Cria um novo projeto Node.js com npm init -y.
    """
    try:
        if not context.args:
            await update.message.reply_text(
                "❓ Use: `/nome <nome_do_projeto>`", parse_mode="Markdown"
            )
            return

        project_name = context.args[0]

        # Valida o nome do projeto: apenas letras, números, hífen e underscore
        if not all(c.isalnum() or c in ("-", "_") for c in project_name):
            await update.message.reply_text(
                "❌ Nome inválido. Use apenas letras, números, `-` ou `_`.",
                parse_mode="Markdown",
            )
            return

        # Cria o diretório do projeto na pasta Documentos do usuário
        base_dir = os.path.join(os.path.expanduser("~"), "Documents", "NodeProjects")
        project_path = os.path.join(base_dir, project_name)

        if os.path.exists(project_path):
            await update.message.reply_text(
                f"⚠️ O projeto `{project_name}` já existe em:\n`{project_path}`",
                parse_mode="Markdown",
            )
            return

        os.makedirs(project_path, exist_ok=True)

        # Executa npm init -y dentro do diretório criado
        result = subprocess.run(
            ["npm", "init", "-y"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            logger.error(f"npm init falhou: {result.stderr}")
            await update.message.reply_text(
                f"❌ Erro ao executar `npm init`:\n`{result.stderr.strip()}`",
                parse_mode="Markdown",
            )
            return

        # Abre o Explorer na pasta do projeto
        os.startfile(project_path)

        await update.message.reply_text(
            f"✅ Projeto Node.js criado com sucesso!\n\n"
            f"📁 *Nome:* `{project_name}`\n"
            f"📍 *Caminho:* `{project_path}`\n\n"
            f"O Explorer foi aberto na pasta do projeto.",
            parse_mode="Markdown",
        )

    except FileNotFoundError:
        logger.error("npm não encontrado. Node.js pode não estar instalado.")
        await update.message.reply_text(
            "❌ `npm` não encontrado. Verifique se o Node.js está instalado e no PATH.",
            parse_mode="Markdown",
        )
    except subprocess.TimeoutExpired:
        logger.error("Timeout ao executar npm init.")
        await update.message.reply_text(
            "❌ Timeout ao executar `npm init`. Tente novamente.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Erro em nome: {e}")
        await update.message.reply_text(f"❌ Erro: `{e}`", parse_mode="Markdown")
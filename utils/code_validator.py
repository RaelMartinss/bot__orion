"""
utils/code_validator.py

Valida o código gerado pela IA antes de qualquer execução.
Usa análise estática (AST) — o código nunca é executado durante a validação.
"""

import ast
import re
import logging

logger = logging.getLogger(__name__)

# Imports completamente proibidos
_BLOCKED_IMPORTS = {
    "socket", "ctypes", "winreg", "importlib", "builtins",
    "pickle", "shelve", "marshal", "pty", "termios", "shutil",
}

# Nomes de funções/atributos proibidos
_BLOCKED_NAMES = {"exec", "eval", "__import__", "compile", "open"}



class ValidationError(Exception):
    """Erro de validação com mensagem amigável para o usuário."""
    pass


def _extract_code_block(raw: str) -> str:
    """
    Extrai o bloco de código Python da resposta da API.
    Aceita resposta com ou sem ``` python ```.
    """
    # Tenta extrair bloco markdown ```python ... ```
    match = re.search(r"```python\s*\n(.*?)```", raw, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Tenta bloco genérico ``` ... ```
    match = re.search(r"```\s*\n(.*?)```", raw, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Assume que a resposta inteira é código
    return raw.strip()


class _SecurityVisitor(ast.NodeVisitor):
    """Percorre a AST procurando violações de segurança."""

    def __init__(self, command_name: str):
        self.command_name = command_name
        self.async_handlers: list[str] = []
        self.errors: list[str] = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root in _BLOCKED_IMPORTS:
                self.errors.append(f"Import proibido: '{alias.name}'")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        root = (node.module or "").split(".")[0]
        if root in _BLOCKED_IMPORTS:
            self.errors.append(f"Import proibido: 'from {node.module} import ...'")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # Bloqueia exec(), eval(), etc. como chamada direta
        if isinstance(node.func, ast.Name) and node.func.id in _BLOCKED_NAMES:
            self.errors.append(f"Chamada proibida: '{node.func.id}()'")

        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self.async_handlers.append(node.name)
        self.generic_visit(node)


def validate(raw_response: str, command_name: str) -> str:
    """
    Valida e retorna o código limpo pronto para ser salvo.

    Args:
        raw_response:  Resposta bruta da API (pode conter markdown)
        command_name:  Nome do comando esperado (ex: "obs")

    Returns:
        Código Python validado como string.

    Raises:
        ValidationError: Se qualquer regra for violada.
    """
    code = _extract_code_block(raw_response)

    if not code:
        raise ValidationError("A API retornou uma resposta vazia.")

    # 1. Verifica se o código é sintaticamente válido
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ValidationError(f"Erro de sintaxe no código gerado: {e}")

    # 2. Análise de segurança via AST
    visitor = _SecurityVisitor(command_name)
    visitor.visit(tree)

    if visitor.errors:
        erros_str = "\n".join(f"  • {e}" for e in visitor.errors)
        raise ValidationError(f"Violações de segurança detectadas:\n{erros_str}")

    # 3. Verifica que existe exatamente uma função async com o nome correto
    if not visitor.async_handlers:
        raise ValidationError(
            f"O código não define nenhuma função async. "
            f"Era esperada a função `{command_name}`."
        )

    if command_name not in visitor.async_handlers:
        found = ", ".join(visitor.async_handlers)
        raise ValidationError(
            f"Função `{command_name}` não encontrada. "
            f"Funções encontradas: {found}"
        )

    logger.info(f"Código para /{command_name} validado com sucesso.")
    return code

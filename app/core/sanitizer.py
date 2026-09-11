import re
from pathlib import Path


SENSITIVE_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.~]+", re.IGNORECASE),
    re.compile(r"oauth2:[A-Za-z0-9_\-]+", re.IGNORECASE),
    re.compile(r"SAPISID=[^;\s]+", re.IGNORECASE),
    re.compile(r"SID=[^;\s]+", re.IGNORECASE),
    re.compile(r"HSID=[^;\s]+", re.IGNORECASE),
    re.compile(r"SSID=[^;\s]+", re.IGNORECASE),
    re.compile(r"APISID=[^;\s]+", re.IGNORECASE),
    re.compile(r"key=[A-Za-z0-9_\-]+", re.IGNORECASE),
    re.compile(r"token=[A-Za-z0-9_\-\.~]+", re.IGNORECASE),
    re.compile(r"https?://[^\s]+\bauth[^\s]*", re.IGNORECASE),
]


def sanitize_upload_filename(raw_filename: str | None) -> str:
    """Extrai apenas o nome seguro do arquivo, prevenindo path traversal."""
    if not raw_filename:
        return "arquivo.txt"

    base_name = Path(raw_filename).name.strip()
    safe_name = re.sub(r"[^A-Za-z0-9_\-\.]", "_", base_name)
    safe_name = safe_name.strip("._")

    if not safe_name:
        return "arquivo.txt"

    return safe_name


def sanitize_error_message(exc: Exception | str) -> str:
    """Remove credenciais, cabeçalhos ou URLs sensíveis da mensagem de erro."""
    message = str(exc).strip()
    if not message:
        return "Falha não especificada durante o processamento da tarefa."

    # Erros conhecidos comuns mapeados para mensagens seguras
    lower = message.lower()
    if "timed out" in lower or "timeout" in lower:
        return "Tempo limite esgotado ao aguardar o processamento pelo Google NotebookLM."
    if "connecterror" in lower or "connection refused" in lower:
        return "Falha temporária de conexão com os servidores do Google NotebookLM."
    if "rate limit" in lower or "too many requests" in lower or "429" in lower:
        return "Limite de requisições do Google NotebookLM atingido. Tente novamente mais tarde."
    if "401" in lower or "unauthorized" in lower or "authentication failed" in lower:
        return "Falha de autenticação com a conta do Google. Verifique o status das credenciais."

    # Mascarar qualquer padrão sensível
    sanitized = message
    for pattern in SENSITIVE_PATTERNS:
        sanitized = pattern.sub("[REMOVIDO_POR_SEGURANCA]", sanitized)

    # Evita expor tracebacks ou mensagens técnicas extensas
    if len(sanitized) > 200:
        sanitized = f"{sanitized[:197]}..."

    return sanitized

from app.core.sanitizer import sanitize_error_message, sanitize_upload_filename


def test_sanitize_upload_filename_traversal() -> None:
    # Impede path traversal com ../ ou ..\
    assert sanitize_upload_filename("../../data/auth/master_token.json") == "master_token.json"
    assert sanitize_upload_filename("..\\..\\data\\auth\\master_token.json") == "master_token.json"
    assert sanitize_upload_filename("/etc/passwd") == "passwd"
    assert sanitize_upload_filename("C:\\Windows\\System32\\calc.exe") == "calc.exe"


def test_sanitize_upload_filename_special_characters() -> None:
    assert sanitize_upload_filename("meu arquivo: 100% teste!.txt") == "meu_arquivo__100__teste_.txt"
    assert sanitize_upload_filename("") == "arquivo.txt"
    assert sanitize_upload_filename(None) == "arquivo.txt"
    assert sanitize_upload_filename("...") == "arquivo.txt"


def test_sanitize_error_message_removes_sensitive_data() -> None:
    # Mascara Bearer token em erro interno
    msg_bearer = "Falha interna ao despachar Bearer ya29.a0AfH6SMBxyz_secret_token"
    sanitized_bearer = sanitize_error_message(msg_bearer)
    assert "ya29" not in sanitized_bearer
    assert "[REMOVIDO_POR_SEGURANCA]" in sanitized_bearer

    # Mascara cookies do Google
    msg_cookie = "Falha ao enviar cookie SAPISID=v1/abc123xyz para notebooklm"
    sanitized_cookie = sanitize_error_message(msg_cookie)
    assert "abc123xyz" not in sanitized_cookie
    assert "[REMOVIDO_POR_SEGURANCA]" in sanitized_cookie

    # Mascara URLs com auth
    msg_url = "Erro na requisição para https://accounts.google.com/o/oauth2/auth?client_id=123"
    sanitized_url = sanitize_error_message(msg_url)
    assert "client_id=123" not in sanitized_url


def test_sanitize_error_message_known_errors() -> None:
    assert sanitize_error_message("Request timed out after 30 seconds") == (
        "Tempo limite esgotado ao aguardar o processamento pelo Google NotebookLM."
    )
    assert sanitize_error_message("httpx.ConnectError: connection refused") == (
        "Falha temporária de conexão com os servidores do Google NotebookLM."
    )

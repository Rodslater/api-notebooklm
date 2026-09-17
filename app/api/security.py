from dataclasses import dataclass
import hashlib
import logging
import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedClient:
    """Dados do cliente autenticado via token de API."""

    client_id: str
    is_admin: bool


def _load_allowed_tokens() -> list[tuple[str, AuthenticatedClient]]:
    """Carrega os tokens válidos a partir das configurações da aplicação."""
    tokens: list[tuple[str, AuthenticatedClient]] = []

    # Token principal (administrador)
    admin_token = settings.api_token.strip()
    if admin_token:
        tokens.append((admin_token, AuthenticatedClient(client_id="admin", is_admin=True)))

    # Tokens adicionais para outros usuários
    additional_tokens_str = settings.api_tokens.strip()
    if additional_tokens_str:
        entries = [e.strip() for e in additional_tokens_str.split(",") if e.strip()]
        for entry in entries:
            if ":" in entry:
                client_id, token = entry.split(":", 1)
                client_id = client_id.strip()
                token = token.strip()
                is_admin = client_id.lower() in ("admin", "root", "rodrigo")
                if token:
                    tokens.append((token, AuthenticatedClient(client_id=client_id, is_admin=is_admin)))
            else:
                token = entry.strip()
                if token:
                    short_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()[:8]
                    tokens.append((token, AuthenticatedClient(client_id=f"user_{short_hash}", is_admin=False)))

    return tokens


async def verify_api_token(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> AuthenticatedClient:
    """Valida o Bearer token contra os tokens configurados na aplicação."""
    allowed = _load_allowed_tokens()
    if not allowed:
        logger.critical(
            "Nenhum API_TOKEN configurado: todas as requisições serão recusadas até que "
            "API_TOKEN ou API_TOKENS seja definido no .env."
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API sem token configurado. Defina API_TOKEN no .env do servidor.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cabeçalho Authorization: Bearer <token> é obrigatório.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    provided = credentials.credentials.strip()
    for valid_token, client in allowed:
        if secrets.compare_digest(provided, valid_token):
            return client

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token de acesso inválido.",
        headers={"WWW-Authenticate": "Bearer"},
    )

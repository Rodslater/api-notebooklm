from fastapi import APIRouter

from app import __version__
from app.api.schemas import HealthResponse
from app.core.client import get_auth_paths

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Retorna o estado de execucao do servidor e presenca de credenciais."""
    storage_path, master_token_path = get_auth_paths()
    authenticated = storage_path.exists() or master_token_path.exists()
    return HealthResponse(
        status="ok",
        authenticated=authenticated,
        version=__version__,
    )

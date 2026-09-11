import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from notebooklm import NotebookLMClient
from notebooklm.auth import bootstrap_missing_storage_from_master_token

from app.config import settings

logger = logging.getLogger(__name__)


def get_auth_paths() -> tuple[Path, Path]:
    """Retorna os caminhos para storage_state.json e master_token.json."""
    auth_dir = settings.notebooklm_auth_dir.resolve()
    auth_dir.mkdir(parents=True, exist_ok=True)
    storage_path = auth_dir / "storage_state.json"
    master_token_path = auth_dir / "master_token.json"
    return storage_path, master_token_path


async def ensure_authentication() -> bool:
    """Verifica credenciais e gera storage_state.json a partir do master_token se necessário."""
    storage_path, master_token_path = get_auth_paths()

    if storage_path.exists():
        return True

    if master_token_path.exists():
        logger.info("Gerando sessão inicial a partir do master_token.json...")
        sucesso = await bootstrap_missing_storage_from_master_token(storage_path)
        if sucesso:
            logger.info("Sessão criada com sucesso a partir do master token.")
            return True
        logger.error("Falha ao inicializar sessão a partir do master token.")
        return False

    logger.warning(
        "Nenhuma credencial encontrada em %s. Crie master_token.json ou storage_state.json.",
        settings.notebooklm_auth_dir,
    )
    return False


@asynccontextmanager
async def get_notebooklm_client() -> AsyncGenerator[NotebookLMClient, None]:
    """Context manager para instanciar e gerenciar o ciclo de vida do cliente NotebookLM."""
    storage_path, master_token_path = get_auth_paths()

    if not storage_path.exists() and master_token_path.exists():
        await bootstrap_missing_storage_from_master_token(storage_path)

    if not storage_path.exists():
        raise RuntimeError(
            f"Credenciais do NotebookLM não encontradas em {settings.notebooklm_auth_dir}. "
            "Configure master_token.json ou storage_state.json."
        )

    async with NotebookLMClient.from_storage(
        path=str(storage_path),
        timeout=60.0,
    ) as client:
        yield client

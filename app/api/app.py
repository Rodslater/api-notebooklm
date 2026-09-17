import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import health, podcasts
from app.config import settings
from app.core.client import ensure_authentication

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Inicialização e encerramento dos recursos da aplicação."""
    logger.info("Iniciando API NotebookLM v%s...", __version__)

    if not settings.api_token.strip() and not settings.api_tokens.strip():
        logger.critical(
            "API_TOKEN e API_TOKENS não configurados: a API vai recusar todas as "
            "requisições. Defina API_TOKEN no .env antes de usar em produção."
        )

    # Garante estrutura de pastas
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    (settings.storage_dir / "uploads").mkdir(parents=True, exist_ok=True)
    (settings.storage_dir / "audios").mkdir(parents=True, exist_ok=True)
    (settings.storage_dir / "jobs").mkdir(parents=True, exist_ok=True)
    settings.notebooklm_auth_dir.mkdir(parents=True, exist_ok=True)

    # Verifica credenciais
    authenticated = await ensure_authentication()
    if authenticated:
        logger.info("Autenticação do NotebookLM validada com sucesso.")
    else:
        logger.warning("Servidor iniciado sem credenciais do NotebookLM configuradas.")

    yield

    logger.info("Encerrando API NotebookLM...")


def create_app() -> FastAPI:
    """Fábrica da aplicação FastAPI."""
    app = FastAPI(
        title="API NotebookLM Podcast",
        description="API HTTP para geração automatizada de podcasts em áudio a partir de textos e arquivos no Google NotebookLM.",
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Erro interno não tratado ao processar requisição: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Ocorreu um erro interno no servidor. Tente novamente mais tarde."},
        )

    app.include_router(health.router)
    app.include_router(podcasts.router)

    return app

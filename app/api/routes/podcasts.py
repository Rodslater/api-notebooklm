import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import FileResponse

from app.api.schemas import PodcastCreateRequest, PodcastJobResponse
from app.api.security import verify_api_token
from app.config import settings
from app.core.jobs import job_manager
from app.core.models import JobStatus, PodcastFormat, PodcastLength
from app.core.podcast import process_podcast_job

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/podcasts",
    tags=["Podcasts"],
    dependencies=[Depends(verify_api_token)],
)


@router.post(
    "",
    response_model=PodcastJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Cria uma nova tarefa de podcast a partir de texto ou arquivo",
)
async def create_podcast(
    request: Request,
    file: UploadFile | None = File(None),
    text: str | None = Form(None),
    title: str | None = Form(None),
    language: str | None = Form(None),
    format: str | None = Form(None),
    length: str | None = Form(None),
    instructions: str | None = Form(None),
    webhook_url: str | None = Form(None),
    cleanup_notebook: bool = Form(True),
) -> PodcastJobResponse:
    """Recebe texto ou arquivo e agenda a geração do podcast em segundo plano."""
    content_type = request.headers.get("content-type", "")

    # Suporte a requisições puramente JSON
    if content_type.startswith("application/json"):
        body_bytes = await request.body()
        try:
            data = json.loads(body_bytes.decode("utf-8"))
            req = PodcastCreateRequest.model_validate(data)
            text = req.text
            title = req.title
            language = req.language
            format = req.format.value
            length = req.length.value
            instructions = req.instructions
            webhook_url = req.webhook_url
            cleanup_notebook = req.cleanup_notebook
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Corpo JSON inválido: {exc}",
            )

    if not file and not (text and text.strip()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="É necessário fornecer um arquivo (.txt, .md, .pdf) ou o campo de texto.",
        )

    # Tratamento e persistência inicial de arquivo temporário
    uploads_dir = settings.storage_dir / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    temp_file_path: Path | None = None
    source_title = "Documento"

    if file:
        source_title = file.filename or "arquivo.txt"
        safe_name = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{source_title}"
        temp_file_path = uploads_dir / safe_name
        content = await file.read()
        temp_file_path.write_bytes(content)
    elif text:
        source_title = "Texto Enviado"

    resolved_title = title or f"Podcast {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')}"
    resolved_lang = language or settings.default_language

    try:
        resolved_format = PodcastFormat(format) if format else PodcastFormat(settings.default_audio_format)
    except ValueError:
        resolved_format = PodcastFormat.BRIEF

    try:
        resolved_length = PodcastLength(length) if length else PodcastLength(settings.default_audio_length)
    except ValueError:
        resolved_length = PodcastLength.DEFAULT

    resolved_instructions = instructions if instructions is not None else settings.default_instructions

    job = await job_manager.create_job(
        title=resolved_title,
        language=resolved_lang,
        format=resolved_format,
        length=resolved_length,
        instructions=resolved_instructions,
        webhook_url=webhook_url,
        cleanup_notebook=cleanup_notebook,
    )

    # Disparo assíncrono em segundo plano
    asyncio.create_task(
        process_podcast_job(
            job_id=job.id,
            source_file_path=temp_file_path,
            source_text=text,
            source_title=source_title,
        )
    )

    base_url = str(request.base_url)
    return PodcastJobResponse.from_domain(job, base_url=base_url)


@router.get(
    "",
    response_model=list[PodcastJobResponse],
    summary="Lista tarefas recentes de podcast",
)
async def list_podcasts(request: Request, limit: int = 50) -> list[PodcastJobResponse]:
    """Retorna as últimas tarefas solicitadas."""
    jobs = await job_manager.list_jobs(limit=limit)
    base_url = str(request.base_url)
    return [PodcastJobResponse.from_domain(j, base_url=base_url) for j in jobs]


@router.get(
    "/{job_id}",
    response_model=PodcastJobResponse,
    summary="Consulta o status de uma tarefa",
)
async def get_podcast_status(job_id: str, request: Request) -> PodcastJobResponse:
    """Retorna informações detalhadas e progresso de uma tarefa."""
    job = await job_manager.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tarefa {job_id} não encontrada.",
        )
    base_url = str(request.base_url)
    return PodcastJobResponse.from_domain(job, base_url=base_url)


@router.get(
    "/{job_id}/download",
    summary="Baixa o arquivo de áudio do podcast concluído",
)
async def download_podcast(job_id: str) -> FileResponse:
    """Entrega o arquivo .m4a gerado."""
    job = await job_manager.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tarefa {job_id} não encontrada.",
        )

    if job.status == JobStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A geração deste podcast falhou: {job.error_message}",
        )

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"O podcast ainda está em processamento. Status atual: {job.status.value}.",
        )

    if not job.audio_file_path or not Path(job.audio_file_path).exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo de áudio não encontrado no disco do servidor.",
        )

    filename = job.audio_file_name or f"{job.id}.m4a"
    return FileResponse(
        path=job.audio_file_path,
        media_type="audio/mp4",
        filename=filename,
    )

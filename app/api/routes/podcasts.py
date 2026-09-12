import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse

from app.api.schemas import PodcastCreateRequest, PodcastJobResponse
from app.api.security import AuthenticatedClient, verify_api_token
from app.config import settings
from app.core.jobs import job_manager
from app.core.models import JobStatus, PodcastFormat, PodcastLength
from app.core.podcast import process_podcast_job
from app.core.sanitizer import sanitize_upload_filename
from app.core.video import generate_podcast_video

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/podcasts",
    tags=["Podcasts"],
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
    generate_video: bool = Form(False),
    video_badge: str | None = Form(None),
    user: AuthenticatedClient = Depends(verify_api_token),
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
            generate_video = req.generate_video
            video_badge = req.video_badge
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
        original_name = sanitize_upload_filename(file.filename)
        safe_name = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}_{original_name}"
        candidate_path = (uploads_dir / safe_name).resolve()
        if not candidate_path.is_relative_to(uploads_dir.resolve()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nome de arquivo inválido para upload.",
            )
        temp_file_path = candidate_path
        content = await file.read()
        temp_file_path.write_bytes(content)
        source_title = original_name
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
        owner_id=user.client_id,
        generate_video=generate_video,
        video_badge=video_badge,
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
async def list_podcasts(
    request: Request,
    limit: int = 50,
    user: AuthenticatedClient = Depends(verify_api_token),
) -> list[PodcastJobResponse]:
    """Retorna as últimas tarefas solicitadas pelo cliente autenticado."""
    owner_filter = None if user.is_admin else user.client_id
    jobs = await job_manager.list_jobs(owner_id=owner_filter, limit=limit)
    base_url = str(request.base_url)
    return [PodcastJobResponse.from_domain(j, base_url=base_url) for j in jobs]


@router.get(
    "/{job_id}",
    response_model=PodcastJobResponse,
    summary="Consulta o status de uma tarefa",
)
async def get_podcast_status(
    job_id: str,
    request: Request,
    user: AuthenticatedClient = Depends(verify_api_token),
) -> PodcastJobResponse:
    """Retorna informações detalhadas e progresso de uma tarefa."""
    job = await job_manager.get_job(job_id)
    if not job or (not user.is_admin and job.owner_id != user.client_id):
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
async def download_podcast(
    job_id: str,
    user: AuthenticatedClient = Depends(verify_api_token),
) -> FileResponse:
    """Entrega o arquivo .m4a gerado com validação estrita de caminho."""
    job = await job_manager.get_job(job_id)
    if not job or (not user.is_admin and job.owner_id != user.client_id):
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

    if not job.audio_file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo de áudio não encontrado no disco do servidor.",
        )

    audio_path = Path(job.audio_file_path).resolve()
    audios_dir = (settings.storage_dir / "audios").resolve()
    if not audio_path.is_relative_to(audios_dir) or not audio_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo de áudio não encontrado no disco do servidor.",
        )

    filename = sanitize_upload_filename(job.audio_file_name or f"{job.id}.m4a")
    return FileResponse(
        path=str(audio_path),
        media_type="audio/mp4",
        filename=filename,
    )


@router.post(
    "/{job_id}/video",
    response_model=PodcastJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Gera vídeo sincronizado a partir de um podcast existente",
)
async def create_podcast_video(
    job_id: str,
    request: Request,
    video_badge: str | None = None,
    user: AuthenticatedClient = Depends(verify_api_token),
) -> PodcastJobResponse:
    """Dispara a esteira de criação de vídeo em segundo plano para um podcast com áudio pronto."""
    job = await job_manager.get_job(job_id)
    if not job or (not user.is_admin and job.owner_id != user.client_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tarefa {job_id} não encontrada.",
        )

    if not job.audio_file_path or not Path(job.audio_file_path).exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O áudio deste podcast ainda não foi concluído ou não está disponível para gerar vídeo.",
        )

    if job.status == JobStatus.GENERATING_VIDEO:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="O vídeo para esta tarefa já está sendo gerado no momento.",
        )

    await job_manager.update_job_status(
        job_id=job.id,
        status=JobStatus.GENERATING_VIDEO,
        message="Iniciando geração do vídeo em segundo plano...",
        generate_video=True,
        video_badge=video_badge if video_badge is not None else job.video_badge,
    )

    asyncio.create_task(generate_podcast_video(job.id))

    updated_job = await job_manager.get_job(job.id)
    base_url = str(request.base_url)
    return PodcastJobResponse.from_domain(updated_job or job, base_url=base_url)


@router.get(
    "/{job_id}/download-video",
    summary="Baixa o arquivo de vídeo do podcast concluído",
)
async def download_podcast_video(
    job_id: str,
    user: AuthenticatedClient = Depends(verify_api_token),
) -> FileResponse:
    """Entrega o arquivo .mp4 gerado com validação estrita de caminho."""
    job = await job_manager.get_job(job_id)
    if not job or (not user.is_admin and job.owner_id != user.client_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tarefa {job_id} não encontrada.",
        )

    if job.status == JobStatus.GENERATING_VIDEO:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="O vídeo ainda está sendo gerado. Aguarde a conclusão.",
        )

    if not job.video_file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo de vídeo não disponível para esta tarefa.",
        )

    video_path = Path(job.video_file_path).resolve()
    videos_dir = (settings.storage_dir / "videos").resolve()
    if not video_path.is_relative_to(videos_dir) or not video_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo de vídeo não encontrado no disco do servidor.",
        )

    filename = sanitize_upload_filename(job.video_file_name or f"{job.id}.mp4")
    return FileResponse(
        path=str(video_path),
        media_type="video/mp4",
        filename=filename,
    )


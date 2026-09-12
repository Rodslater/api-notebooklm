import asyncio
import logging
from pathlib import Path

from app.config import settings
from app.core.client import get_notebooklm_client
from app.core.jobs import job_manager
from app.core.models import JobStatus, PodcastJob
from app.core.notifier import notify_webhook
from app.core.sanitizer import sanitize_error_message
from app.core.video import generate_podcast_video

logger = logging.getLogger(__name__)


async def process_podcast_job(
    job_id: str,
    source_file_path: Path | None = None,
    source_text: str | None = None,
    source_title: str = "Fonte Principal",
) -> None:
    """Executa a criação de caderno, envio de fonte, geração e download do podcast."""
    job = await job_manager.get_job(job_id)
    if not job:
        logger.error("Tarefa %s não encontrada para execução.", job_id)
        return

    notebook_id: str | None = None
    audio_dir = settings.storage_dir / "audios"
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_file_path = audio_dir / f"{job.id}.m4a"

    try:
        async with get_notebooklm_client() as client:
            # 1. Criar o caderno
            await job_manager.update_job_status(
                job_id=job.id,
                status=JobStatus.CREATING_NOTEBOOK,
                message="Criando caderno no NotebookLM...",
            )
            notebook = await client.notebooks.create(job.title)
            notebook_id = notebook.id
            await job_manager.update_job_status(
                job_id=job.id,
                status=JobStatus.UPLOADING_SOURCE,
                message="Caderno criado. Enviando fonte...",
                notebook_id=notebook_id,
            )

            # 2. Adicionar fonte
            if source_file_path and source_file_path.exists():
                mime_type = "text/plain" if source_file_path.suffix.lower() in (".log", ".txt", ".md") else None
                source = await client.sources.add_file(
                    notebook_id,
                    str(source_file_path),
                    title=source_title,
                    mime_type=mime_type,
                    wait=True,
                )
            elif source_text:
                source = await client.sources.add_text(
                    notebook_id,
                    title=source_title,
                    content=source_text,
                    wait=True,
                )
            else:
                raise ValueError("Nenhum arquivo ou texto foi fornecido para a fonte.")

            source_id = source.id if hasattr(source, "id") else None

            # 3. Disparar a geração de áudio
            await job_manager.update_job_status(
                job_id=job.id,
                status=JobStatus.GENERATING_AUDIO,
                message="Fonte processada. Gerando áudio no NotebookLM (isso pode levar de 3 a 8 minutos)...",
                source_id=source_id,
            )

            instructions = job.instructions or settings.default_instructions
            gen_status = await client.artifacts.generate_audio(
                notebook_id=notebook_id,
                language=job.language,
                instructions=instructions,
                audio_format=job.format.to_notebooklm(),
                audio_length=job.length.to_notebooklm(),
            )

            task_id = gen_status.task_id
            await job_manager.update_job_status(
                job_id=job.id,
                status=JobStatus.GENERATING_AUDIO,
                message="Áudio solicitado com sucesso. Aguardando conclusão pelo Google...",
                task_id=task_id,
            )

            # 4. Aguardar conclusão do áudio
            await client.artifacts.wait_for_completion(
                notebook_id=notebook_id,
                task_id=task_id,
                timeout=settings.generation_timeout_seconds,
            )

            # 5. Baixar o arquivo de áudio
            await job_manager.update_job_status(
                job_id=job.id,
                status=JobStatus.DOWNLOADING_AUDIO,
                message="Áudio concluído pelo Google. Baixando arquivo para a VPS...",
            )

            saved_path = await client.artifacts.download_audio(
                notebook_id=notebook_id,
                output_path=str(audio_file_path),
            )

            file_size = Path(saved_path).stat().st_size if Path(saved_path).exists() else 0

            # 6. Limpeza do caderno no Google se configurado
            if job.cleanup_notebook and notebook_id:
                try:
                    await client.notebooks.delete(notebook_id)
                    logger.info("Caderno %s excluído do NotebookLM após download.", notebook_id)
                except Exception as e:
                    logger.warning("Não foi possível excluir caderno temporário %s: %s", notebook_id, e)

            # 7. Finalização do áudio e transição para vídeo se solicitado
            if job.generate_video:
                await job_manager.update_job_status(
                    job_id=job.id,
                    status=JobStatus.GENERATING_VIDEO,
                    message="Áudio concluído com sucesso. Iniciando geração do vídeo...",
                    audio_file_path=str(saved_path),
                    audio_file_name=f"{job.id}.m4a",
                    audio_size_bytes=file_size,
                )
                await generate_podcast_video(job.id)
            else:
                final_job = await job_manager.update_job_status(
                    job_id=job.id,
                    status=JobStatus.COMPLETED,
                    message="Podcast gerado e disponível para download.",
                    audio_file_path=str(saved_path),
                    audio_file_name=f"{job.id}.m4a",
                    audio_size_bytes=file_size,
                )
                if final_job:
                    await notify_webhook(final_job)

    except Exception as exc:
        logger.exception("Erro ao processar tarefa de podcast %s: %s", job.id, exc)
        failed_job = await job_manager.update_job_status(
            job_id=job.id,
            status=JobStatus.FAILED,
            message="Ocorreu um erro durante a geração do podcast.",
            error_message=sanitize_error_message(exc),
        )
        if failed_job:
            await notify_webhook(failed_job)

        # Tentativa de limpar o caderno em caso de falha
        if job.cleanup_notebook and notebook_id:
            try:
                async with get_notebooklm_client() as client:
                    await client.notebooks.delete(notebook_id)
            except Exception:
                pass

    finally:
        # Remover arquivo temporário de upload
        if source_file_path and source_file_path.exists():
            try:
                source_file_path.unlink()
            except Exception:
                pass

import asyncio
import logging
import shutil
from pathlib import Path

from app.config import settings
from app.core.jobs import job_manager
from app.core.models import JobStatus
from app.core.notifier import notify_webhook
from app.core.sanitizer import sanitize_error_message
from app.core.video.card import format_card_badge, format_card_subtitle, generate_topic_card
from app.core.video.collector import collect_scene_images
from app.core.video.director import direct_video_scenes
from app.core.video.renderer import assemble_video, get_audio_duration

logger = logging.getLogger(__name__)


async def generate_podcast_video(job_id: str) -> None:
    """Executa a esteira completa de criação de vídeo sincronizado ao podcast."""
    job = await job_manager.get_job(job_id)
    if not job:
        logger.error("Tarefa %s não encontrada para geração de vídeo.", job_id)
        return

    if not job.audio_file_path or not Path(job.audio_file_path).exists():
        logger.error("Áudio da tarefa %s não encontrado para geração de vídeo.", job_id)
        await job_manager.update_job_status(
            job_id=job.id,
            status=JobStatus.FAILED,
            message="Arquivo de áudio não encontrado para gerar o vídeo.",
            error_message="Arquivo de áudio ausente no storage.",
        )
        return

    audio_path = Path(job.audio_file_path)
    video_dir = settings.storage_dir / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)
    final_video_path = video_dir / f"{job.id}.mp4"

    workspace_dir = settings.storage_dir / "temp_video" / job.id
    if workspace_dir.exists():
        shutil.rmtree(workspace_dir, ignore_errors=True)
    workspace_dir.mkdir(parents=True, exist_ok=True)

    try:
        await job_manager.update_job_status(
            job_id=job.id,
            status=JobStatus.GENERATING_VIDEO,
            message="Analisando o áudio com IA para estruturar as cenas do vídeo...",
        )

        # 1. Medir duração do áudio
        duration_sec = get_audio_duration(audio_path)
        if duration_sec <= 0:
            duration_sec = 360.0

        # 2. Direção visual com Gemini Flash
        scenes = await direct_video_scenes(
            audio_path=audio_path,
            audio_duration_sec=duration_sec,
            podcast_title=job.title,
        )

        await job_manager.update_job_status(
            job_id=job.id,
            status=JobStatus.GENERATING_VIDEO,
            message=f"Roteiro visual concluído com {len(scenes)} cenas. Coletando imagens no Pexels...",
        )

        # 3. Coleta e padronização das imagens em 1080p
        images_dir = workspace_dir / "images"
        scenes = await collect_scene_images(
            scenes=scenes,
            output_dir=images_dir,
            podcast_title=job.title,
        )

        # 4. Geração dos cartões com a identidade visual no topo e tópicos dinâmicos embaixo
        cards_dir = workspace_dir / "cards"
        resolved_badge = job.video_badge or format_card_badge(job.title)
        for scene in scenes:
            card_file = cards_dir / f"card_{scene.index:03d}.png"
            generate_topic_card(
                scene=scene,
                output_path=card_file,
                badge_text=resolved_badge,
                bottom_text=scene.topic,
            )
            scene.card_path = card_file

        await job_manager.update_job_status(
            job_id=job.id,
            status=JobStatus.GENERATING_VIDEO,
            message="Renderizando segmentos e unindo ao áudio via FFmpeg...",
        )

        # 5. Renderização e montagem do vídeo no FFmpeg em thread dedicada para não bloquear o loop assíncrono
        await asyncio.to_thread(
            assemble_video,
            scenes=scenes,
            audio_path=audio_path,
            output_mp4=final_video_path,
            temp_dir=workspace_dir / "segments",
            fps=settings.video_fps,
        )

        video_size = final_video_path.stat().st_size if final_video_path.exists() else 0

        # 6. Atualização final de conclusão
        final_job = await job_manager.update_job_status(
            job_id=job.id,
            status=JobStatus.COMPLETED,
            message="Podcast e vídeo gerados com sucesso.",
            video_file_path=str(final_video_path),
            video_file_name=f"{job.id}.mp4",
            video_size_bytes=video_size,
        )

        if final_job:
            await notify_webhook(final_job)

        logger.info("Vídeo concluído para a tarefa %s (Tamanho: %d bytes).", job.id, video_size)

    except Exception as exc:
        logger.exception("Erro ao gerar vídeo para a tarefa %s: %s", job.id, exc)
        # Se o áudio já foi gerado, mantém status completed para não perder o podcast
        has_audio = bool(job.audio_file_path and Path(job.audio_file_path).exists())
        fallback_status = JobStatus.COMPLETED if has_audio else JobStatus.FAILED
        status_msg = (
            "Podcast concluído, mas ocorreu uma falha ao renderizar o vídeo."
            if has_audio
            else "Falha ao gerar o vídeo."
        )

        failed_job = await job_manager.update_job_status(
            job_id=job.id,
            status=fallback_status,
            message=status_msg,
            error_message=sanitize_error_message(exc),
        )
        if failed_job:
            await notify_webhook(failed_job)

    finally:
        # Limpeza do espaço de trabalho temporário
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir, ignore_errors=True)

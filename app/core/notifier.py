import logging
import httpx

from app.core.models import PodcastJob

logger = logging.getLogger(__name__)


async def notify_webhook(job: PodcastJob) -> bool:
    """Envia notificação POST HTTP com o resultado da tarefa para o webhook_url configurado."""
    if not job.webhook_url:
        return False

    payload = {
        "event": "podcast.completed" if job.status.value == "completed" else "podcast.failed",
        "job_id": job.id,
        "title": job.title,
        "status": job.status.value,
        "status_message": job.status_message,
        "audio_file_name": job.audio_file_name,
        "audio_size_bytes": job.audio_size_bytes,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(job.webhook_url, json=payload)
            if response.is_success:
                logger.info("Webhook enviado com sucesso para %s: HTTP %d", job.webhook_url, response.status_code)
                return True
            logger.warning("Falha ao entregar webhook em %s: HTTP %d", job.webhook_url, response.status_code)
            return False
    except Exception as e:
        logger.error("Exceção ao enviar webhook para %s: %s", job.webhook_url, e)
        return False

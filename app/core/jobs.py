import asyncio
import json
import logging
import uuid
from pathlib import Path

from app.config import settings
from app.core.models import JobStatus, PodcastFormat, PodcastJob, PodcastLength

logger = logging.getLogger(__name__)


class JobManager:
    """Gerenciador de tarefas de podcast com persistência simples em disco."""

    def __init__(self, storage_dir: Path) -> None:
        self._storage_dir = storage_dir
        self._jobs_dir = storage_dir / "jobs"
        self._jobs_dir.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, PodcastJob] = {}
        self._lock = asyncio.Lock()
        self._load_existing_jobs()

    def _load_existing_jobs(self) -> None:
        for file in self._jobs_dir.glob("*.json"):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                job = PodcastJob.model_validate(data)
                self._jobs[job.id] = job
            except Exception as e:
                logger.warning("Erro ao carregar tarefa antiga %s: %s", file.name, e)

    def _persist_job(self, job: PodcastJob) -> None:
        try:
            file_path = self._jobs_dir / f"{job.id}.json"
            file_path.write_text(job.model_dump_json(indent=2), encoding="utf-8")
        except Exception as e:
            logger.error("Erro ao persistir tarefa %s no disco: %s", job.id, e)

    async def create_job(
        self,
        title: str,
        language: str = "pt",
        format: PodcastFormat = PodcastFormat.BRIEF,
        length: PodcastLength = PodcastLength.DEFAULT,
        instructions: str = "",
        webhook_url: str | None = None,
        cleanup_notebook: bool = True,
    ) -> PodcastJob:
        async with self._lock:
            job_id = f"pod_{uuid.uuid4().hex[:12]}"
            job = PodcastJob(
                id=job_id,
                title=title,
                language=language,
                format=format,
                length=length,
                instructions=instructions,
                webhook_url=webhook_url,
                cleanup_notebook=cleanup_notebook,
            )
            self._jobs[job_id] = job
            self._persist_job(job)
            return job

    async def get_job(self, job_id: str) -> PodcastJob | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        message: str,
        error_message: str | None = None,
        notebook_id: str | None = None,
        source_id: str | None = None,
        task_id: str | None = None,
        artifact_id: str | None = None,
        audio_file_path: str | None = None,
        audio_file_name: str | None = None,
        audio_size_bytes: int | None = None,
    ) -> PodcastJob | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None

            job.update_status(status, message)
            if error_message is not None:
                job.error_message = error_message
            if notebook_id is not None:
                job.notebook_id = notebook_id
            if source_id is not None:
                job.source_id = source_id
            if task_id is not None:
                job.task_id = task_id
            if artifact_id is not None:
                job.artifact_id = artifact_id
            if audio_file_path is not None:
                job.audio_file_path = audio_file_path
            if audio_file_name is not None:
                job.audio_file_name = audio_file_name
            if audio_size_bytes is not None:
                job.audio_size_bytes = audio_size_bytes

            self._persist_job(job)
            return job

    async def list_jobs(self, limit: int = 50) -> list[PodcastJob]:
        async with self._lock:
            jobs = list(self._jobs.values())
            jobs.sort(key=lambda j: j.created_at, reverse=True)
            return jobs[:limit]


job_manager = JobManager(settings.storage_dir)

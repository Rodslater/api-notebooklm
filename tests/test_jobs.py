import pytest
from pathlib import Path
from app.core.jobs import JobManager
from app.core.models import JobStatus, PodcastFormat, PodcastLength


@pytest.mark.asyncio
async def test_job_manager_lifecycle(tmp_path: Path) -> None:
    manager = JobManager(tmp_path)

    job = await manager.create_job(
        title="Podcast Diário",
        language="pt",
        format=PodcastFormat.BRIEF,
        length=PodcastLength.SHORT,
        instructions="Fale em português claro",
    )

    assert job.id.startswith("pod_")
    assert job.title == "Podcast Diário"
    assert job.status == JobStatus.QUEUED

    retrieved = await manager.get_job(job.id)
    assert retrieved is not None
    assert retrieved.id == job.id

    updated = await manager.update_job_status(
        job_id=job.id,
        status=JobStatus.COMPLETED,
        message="Áudio finalizado.",
        audio_file_path=str(tmp_path / "audio.m4a"),
        audio_file_name="audio.m4a",
        audio_size_bytes=1024,
    )
    assert updated is not None
    assert updated.status == JobStatus.COMPLETED
    assert updated.audio_size_bytes == 1024

    jobs = await manager.list_jobs(limit=10)
    assert len(jobs) == 1
    assert jobs[0].id == job.id

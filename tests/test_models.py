from notebooklm import AudioFormat, AudioLength

from app.core.models import JobStatus, PodcastFormat, PodcastJob, PodcastLength


def test_podcast_format_mapping() -> None:
    assert PodcastFormat.BRIEF.to_notebooklm() == AudioFormat.BRIEF
    assert PodcastFormat.DEEP_DIVE.to_notebooklm() == AudioFormat.DEEP_DIVE
    assert PodcastFormat.CRITIQUE.to_notebooklm() == AudioFormat.CRITIQUE
    assert PodcastFormat.DEBATE.to_notebooklm() == AudioFormat.DEBATE


def test_podcast_length_mapping() -> None:
    assert PodcastLength.SHORT.to_notebooklm() == AudioLength.SHORT
    assert PodcastLength.DEFAULT.to_notebooklm() == AudioLength.DEFAULT
    assert PodcastLength.LONG.to_notebooklm() == AudioLength.LONG


def test_job_status_transitions() -> None:
    job = PodcastJob(id="pod_123", title="Teste de Áudio")
    assert job.status == JobStatus.QUEUED
    assert job.completed_at is None

    job.update_status(JobStatus.GENERATING_AUDIO, "Gerando áudio...")
    assert job.status == JobStatus.GENERATING_AUDIO
    assert job.status_message == "Gerando áudio..."
    assert job.completed_at is None

    job.update_status(JobStatus.COMPLETED, "Concluído.")
    assert job.status == JobStatus.COMPLETED
    assert job.completed_at is not None

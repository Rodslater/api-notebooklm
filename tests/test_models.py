from notebooklm import (
    AudioFormat,
    AudioLength,
    VideoFormat as NlmVideoFormat,
    VideoStyle as NlmVideoStyle,
)

from app.core.models import (
    JobStatus,
    PodcastFormat,
    PodcastJob,
    PodcastLength,
    VideoEngine,
    VideoFormat,
    VideoStyle,
)


def test_podcast_format_mapping() -> None:
    assert PodcastFormat.BRIEF.to_notebooklm() == AudioFormat.BRIEF
    assert PodcastFormat.DEEP_DIVE.to_notebooklm() == AudioFormat.DEEP_DIVE
    assert PodcastFormat.CRITIQUE.to_notebooklm() == AudioFormat.CRITIQUE
    assert PodcastFormat.DEBATE.to_notebooklm() == AudioFormat.DEBATE


def test_podcast_length_mapping() -> None:
    assert PodcastLength.SHORT.to_notebooklm() == AudioLength.SHORT
    assert PodcastLength.DEFAULT.to_notebooklm() == AudioLength.DEFAULT
    assert PodcastLength.LONG.to_notebooklm() == AudioLength.LONG


def test_video_format_mapping() -> None:
    assert VideoFormat.EXPLAINER.to_notebooklm() == NlmVideoFormat.EXPLAINER
    assert VideoFormat.BRIEF.to_notebooklm() == NlmVideoFormat.BRIEF
    assert VideoFormat.CINEMATIC.to_notebooklm() == NlmVideoFormat.CINEMATIC
    assert VideoFormat.SHORT.to_notebooklm() == NlmVideoFormat.SHORT


def test_video_style_mapping() -> None:
    assert VideoStyle.AUTO_SELECT.to_notebooklm() == NlmVideoStyle.AUTO_SELECT
    assert VideoStyle.CLASSIC.to_notebooklm() == NlmVideoStyle.CLASSIC
    assert VideoStyle.WHITEBOARD.to_notebooklm() == NlmVideoStyle.WHITEBOARD
    assert VideoStyle.KAWAII.to_notebooklm() == NlmVideoStyle.KAWAII
    assert VideoStyle.ANIME.to_notebooklm() == NlmVideoStyle.ANIME
    assert VideoStyle.WATERCOLOR.to_notebooklm() == NlmVideoStyle.WATERCOLOR
    assert VideoStyle.RETRO_PRINT.to_notebooklm() == NlmVideoStyle.RETRO_PRINT
    assert VideoStyle.PAPER_CRAFT.to_notebooklm() == NlmVideoStyle.PAPER_CRAFT
    assert VideoStyle.HERITAGE.to_notebooklm() == NlmVideoStyle.HERITAGE
    assert VideoStyle.CUSTOM.to_notebooklm() == NlmVideoStyle.CUSTOM


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

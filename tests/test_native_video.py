from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.core.jobs import job_manager
from app.core.models import JobStatus, VideoEngine, VideoFormat, VideoStyle
from app.core.podcast import process_podcast_job


@pytest.mark.asyncio
async def test_process_podcast_job_native_video(tmp_path: Path) -> None:
    job = await job_manager.create_job(
        title="Teste Vídeo Nativo",
        generate_video=True,
        video_engine=VideoEngine.NOTEBOOKLM,
        video_format=VideoFormat.EXPLAINER,
        video_style=VideoStyle.WHITEBOARD,
    )

    mock_client = MagicMock()
    mock_notebooks = AsyncMock()
    mock_notebook = MagicMock(id="nb_test_123")
    mock_notebooks.create.return_value = mock_notebook
    mock_notebooks.delete.return_value = None
    mock_client.notebooks = mock_notebooks

    mock_sources = AsyncMock()
    mock_source = MagicMock(id="src_test_123")
    mock_sources.add_text.return_value = mock_source
    mock_client.sources = mock_sources

    mock_artifacts = AsyncMock()
    mock_audio_gen = MagicMock(task_id="task_audio_123")
    mock_artifacts.generate_audio.return_value = mock_audio_gen
    mock_artifacts.wait_for_completion.return_value = None

    fake_audio = tmp_path / "fake_audio.m4a"
    fake_audio.write_bytes(b"dummy audio")
    mock_artifacts.download_audio.return_value = str(fake_audio)

    mock_video_gen = MagicMock(task_id="task_video_123")
    mock_artifacts.generate_video.return_value = mock_video_gen

    fake_video = tmp_path / "fake_video.mp4"
    fake_video.write_bytes(b"dummy video")
    mock_artifacts.download_video.return_value = str(fake_video)

    mock_client.artifacts = mock_artifacts

    class MockContextManager:
        async def __aenter__(self):
            return mock_client

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    with patch("app.core.podcast.get_notebooklm_client", return_value=MockContextManager()):
        await process_podcast_job(job_id=job.id, source_text="Conteúdo de teste para vídeo nativo.")

    updated = await job_manager.get_job(job.id)
    assert updated is not None
    assert updated.status == JobStatus.COMPLETED
    assert updated.video_file_name == f"{job.id}.mp4"
    assert mock_artifacts.generate_video.called
    assert mock_artifacts.download_video.called
    assert mock_notebooks.delete.called

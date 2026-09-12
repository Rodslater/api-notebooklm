import subprocess
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.config import settings
from app.core.jobs import job_manager
from app.core.models import JobStatus, PodcastFormat, PodcastLength
from app.core.video.card import format_card_badge, format_card_subtitle, generate_topic_card
from app.core.video.collector import _generate_fallback_image, _normalize_image_1080p
from app.core.video.director import _generate_fallback_scenes
from app.core.video.models import VideoScene
from app.core.video.renderer import assemble_video, get_audio_duration, get_ffmpeg_path, render_scene_segment
from app.core.video.service import generate_podcast_video


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_video_scene_model():
    scene = VideoScene(
        index=0,
        start_sec=0.0,
        end_sec=18.5,
        topic="Introdução ao Tema",
        search_query="artificial intelligence",
    )
    assert scene.duration_sec == 18.5
    assert scene.index == 0


def test_format_card_badge_and_subtitle():
    assert format_card_badge("Podcast Canal Brasil BrasIRC: 12/09/2026") == "BrasIRC Chatcast | #Brasil - 12/09/2026"
    assert format_card_badge("Log 2026-09-12 Canal Brasil") == "BrasIRC Chatcast | #Brasil - 12/09/2026"
    assert format_card_badge(None) == "BrasIRC Chatcast | #Brasil - 12/09/2026"
    assert format_card_subtitle("Podcast Canal Brasil BrasIRC: 12/09/2026") == "#Brasil - 12/09/2026"


def test_generate_topic_card(tmp_path: Path):
    scene = VideoScene(
        index=1,
        start_sec=18.0,
        end_sec=36.0,
        topic="Análise dos Resultados e Métricas",
        search_query="data metrics",
    )
    card_path = tmp_path / "card_test.png"
    result = generate_topic_card(
        scene=scene,
        output_path=card_path,
        badge_text="BrasIRC Chatcast",
        bottom_text="#Brasil - 12/09/2026",
    )

    assert result.exists()
    assert result.stat().st_size > 0


def test_generate_fallback_scenes():
    scenes = _generate_fallback_scenes(36.0, "Episódio Piloto")
    assert len(scenes) == 2
    assert scenes[0].start_sec == 0.0
    assert scenes[0].end_sec == 18.0
    assert scenes[1].start_sec == 18.0
    assert scenes[1].end_sec == 36.0


def test_generate_fallback_image(tmp_path: Path):
    scene = VideoScene(
        index=0,
        start_sec=0.0,
        end_sec=10.0,
        topic="Tema Inicial",
        search_query="tech",
    )
    img_path = _generate_fallback_image(scene, tmp_path)
    assert img_path.exists()
    assert img_path.stat().st_size > 0


def test_video_rendering_and_assembly_pipeline(tmp_path: Path):
    ffmpeg_exe = get_ffmpeg_path()
    assert ffmpeg_exe is not None

    # 1. Gera áudio sintético curto de 4 segundos
    audio_path = tmp_path / "sample.m4a"
    cmd_audio = [
        ffmpeg_exe,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=1000:duration=4",
        "-c:a",
        "aac",
        str(audio_path),
    ]
    subprocess.run(cmd_audio, check=True, capture_output=True)

    dur = get_audio_duration(audio_path)
    assert dur >= 3.8

    # 2. Prepara 2 cenas
    scenes = [
        VideoScene(index=0, start_sec=0.0, end_sec=2.0, topic="Primeira Cena", search_query="tech"),
        VideoScene(index=1, start_sec=2.0, end_sec=4.0, topic="Segunda Cena", search_query="science"),
    ]

    for sc in scenes:
        sc.image_path = _generate_fallback_image(sc, tmp_path / "images")
        sc.card_path = generate_topic_card(sc, tmp_path / f"card_{sc.index}.png")

    output_mp4 = tmp_path / "output_test.mp4"
    assemble_video(
        scenes=scenes,
        audio_path=audio_path,
        output_mp4=output_mp4,
        temp_dir=tmp_path / "work",
        fps=30,
    )

    assert output_mp4.exists()
    assert output_mp4.stat().st_size > 5000


@pytest.mark.asyncio
async def test_video_service_success_flow(tmp_path: Path):
    ffmpeg_exe = get_ffmpeg_path()
    audio_path = settings.storage_dir / "audios" / "test_job_vid.m4a"
    audio_path.parent.mkdir(parents=True, exist_ok=True)

    cmd_audio = [
        ffmpeg_exe,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=800:duration=3",
        "-c:a",
        "aac",
        str(audio_path),
    ]
    subprocess.run(cmd_audio, check=True, capture_output=True)

    job = await job_manager.create_job(
        title="Podcast de Teste para Vídeo",
        generate_video=True,
    )
    await job_manager.update_job_status(
        job_id=job.id,
        status=JobStatus.COMPLETED,
        message="Áudio pronto",
        audio_file_path=str(audio_path),
        audio_file_name="test_job_vid.m4a",
        audio_size_bytes=audio_path.stat().st_size,
    )

    await generate_podcast_video(job.id)

    updated_job = await job_manager.get_job(job.id)
    assert updated_job is not None
    assert updated_job.video_file_path is not None
    assert Path(updated_job.video_file_path).exists()
    assert updated_job.video_size_bytes > 0

    # Limpeza
    audio_path.unlink(missing_ok=True)
    if updated_job.video_file_path:
        Path(updated_job.video_file_path).unlink(missing_ok=True)


def test_api_video_trigger_and_download(client: TestClient, tmp_path: Path):
    token = settings.api_token
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Cria tarefa simulada com áudio e vídeo prontos
    videos_dir = settings.storage_dir / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)
    fake_video = videos_dir / "pod_fake123.mp4"
    fake_video.write_bytes(b"dummy mp4 video content")

    audios_dir = settings.storage_dir / "audios"
    audios_dir.mkdir(parents=True, exist_ok=True)
    fake_audio = audios_dir / "pod_fake123.m4a"
    fake_audio.write_bytes(b"dummy m4a audio content")

    import asyncio

    async def setup_fake():
        job = await job_manager.create_job(title="Podcast Fake", owner_id="admin")
        await job_manager.update_job_status(
            job_id=job.id,
            status=JobStatus.COMPLETED,
            message="Pronto",
            audio_file_path=str(fake_audio),
            audio_file_name=fake_audio.name,
            video_file_path=str(fake_video),
            video_file_name=fake_video.name,
            video_size_bytes=fake_video.stat().st_size,
            generate_video=True,
        )
        return job

    job = asyncio.run(setup_fake())

    # 2. Testa endpoint de consulta
    resp = client.get(f"/api/v1/podcasts/{job.id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["generate_video"] is True
    assert data["video_file_name"] == fake_video.name
    assert "/download-video" in data["video_download_url"]

    # 3. Testa download do vídeo
    dl_resp = client.get(f"/api/v1/podcasts/{job.id}/download-video", headers=headers)
    assert dl_resp.status_code == 200
    assert dl_resp.content == b"dummy mp4 video content"

    # Limpeza
    fake_video.unlink(missing_ok=True)
    fake_audio.unlink(missing_ok=True)


def test_api_video_download_blocks_traversal(client: TestClient):
    token = settings.api_token
    headers = {"Authorization": f"Bearer {token}"}

    import asyncio

    async def setup_traversal():
        job = await job_manager.create_job(title="Podcast Traversal", owner_id="admin")
        await job_manager.update_job_status(
            job_id=job.id,
            status=JobStatus.COMPLETED,
            message="Pronto",
            video_file_path=str(settings.notebooklm_auth_dir / "master_token.json"),
            video_file_name="master_token.json",
        )
        return job

    job = asyncio.run(setup_traversal())

    resp = client.get(f"/api/v1/podcasts/{job.id}/download-video", headers=headers)
    assert resp.status_code == 404


def test_api_create_podcast_with_video_badge(client: TestClient):
    token = settings.api_token
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "title": "Episódio com Badge",
        "text": "Texto para podcast de teste com badge.",
        "generate_video": True,
        "video_badge": "BrasIRC Chatcast | #Brasil - 12/09/2026",
    }
    resp = client.post("/api/v1/podcasts", json=payload, headers=headers)
    assert resp.status_code == 202
    data = resp.json()
    assert data["generate_video"] is True
    assert data["video_badge"] == "BrasIRC Chatcast | #Brasil - 12/09/2026"

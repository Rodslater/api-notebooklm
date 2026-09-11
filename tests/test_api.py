from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.config import settings
from app.core.jobs import job_manager
from app.core.models import JobStatus

client = TestClient(create_app())
AUTH_HEADER = {"Authorization": f"Bearer {settings.api_token}"}


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "authenticated" in data
    assert "version" in data


def test_unauthorized_access() -> None:
    response = client.post("/api/v1/podcasts", json={"text": "Olá"})
    assert response.status_code == 401


def test_create_podcast_empty_payload() -> None:
    response = client.post("/api/v1/podcasts", json={}, headers=AUTH_HEADER)
    assert response.status_code == 400


@patch("app.api.routes.podcasts.process_podcast_job")
def test_create_podcast_with_json_text(mock_process: object) -> None:
    payload = {
        "title": "Resumo Semanal",
        "text": "Este é o conteúdo base para gerar o podcast.",
        "language": "pt",
        "format": "brief",
        "length": "short",
    }
    response = client.post("/api/v1/podcasts", json=payload, headers=AUTH_HEADER)
    assert response.status_code == 202
    data = response.json()
    assert data["job_id"].startswith("pod_")
    assert data["status"] == "queued"
    assert data["title"] == "Resumo Semanal"
    assert "status_url" in data


@patch("app.api.routes.podcasts.process_podcast_job")
def test_create_podcast_with_file_upload(mock_process: object) -> None:
    files = {"file": ("documento.txt", b"Conteudo do arquivo de texto para podcast.", "text/plain")}
    data = {"title": "Podcast de Arquivo", "format": "brief"}
    response = client.post("/api/v1/podcasts", files=files, data=data, headers=AUTH_HEADER)
    assert response.status_code == 202
    res_data = response.json()
    assert res_data["job_id"].startswith("pod_")
    assert res_data["title"] == "Podcast de Arquivo"


def test_list_podcasts() -> None:
    response = client.get("/api/v1/podcasts", headers=AUTH_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_podcast_not_found() -> None:
    response = client.get("/api/v1/podcasts/pod_nao_existe", headers=AUTH_HEADER)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_download_podcast_lifecycle(tmp_path: Path) -> None:
    # Cria uma tarefa fictícia
    job = await job_manager.create_job(title="Podcast para Download")

    # 1. Tentativa de download enquanto está na fila: deve dar 409 Conflict
    resp_conflict = client.get(f"/api/v1/podcasts/{job.id}/download", headers=AUTH_HEADER)
    assert resp_conflict.status_code == 409

    # 2. Conclui a tarefa e gera um arquivo de áudio de teste no diretório permitido
    audios_dir = settings.storage_dir / "audios"
    audios_dir.mkdir(parents=True, exist_ok=True)
    audio_file = audios_dir / f"{job.id}.m4a"
    audio_file.write_bytes(b"dummy audio content")

    try:
        await job_manager.update_job_status(
            job_id=job.id,
            status=JobStatus.COMPLETED,
            message="Concluído com sucesso.",
            audio_file_path=str(audio_file),
            audio_file_name=f"{job.id}.m4a",
            audio_size_bytes=len(b"dummy audio content"),
        )

        # 3. Consulta o status da tarefa concluída
        resp_status = client.get(f"/api/v1/podcasts/{job.id}", headers=AUTH_HEADER)
        assert resp_status.status_code == 200
        assert resp_status.json()["status"] == "completed"
        assert resp_status.json()["download_url"] is not None

        # 4. Faz o download com sucesso
        resp_download = client.get(f"/api/v1/podcasts/{job.id}/download", headers=AUTH_HEADER)
        assert resp_download.status_code == 200
        assert resp_download.content == b"dummy audio content"
    finally:
        if audio_file.exists():
            audio_file.unlink()

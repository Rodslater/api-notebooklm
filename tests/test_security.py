from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.config import settings
from app.core.jobs import job_manager
from app.core.models import JobStatus

client = TestClient(create_app())


@pytest.fixture(autouse=True)
def configure_test_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings,
        "api_tokens",
        "cliente_alice:token_alice_123,cliente_bob:token_bob_456",
    )


def test_token_authentication_variants() -> None:
    # Token do admin funciona
    admin_resp = client.get("/api/v1/podcasts", headers={"Authorization": f"Bearer {settings.api_token}"})
    assert admin_resp.status_code == 200

    # Token da Alice funciona
    alice_resp = client.get("/api/v1/podcasts", headers={"Authorization": "Bearer token_alice_123"})
    assert alice_resp.status_code == 200

    # Token do Bob funciona
    bob_resp = client.get("/api/v1/podcasts", headers={"Authorization": "Bearer token_bob_456"})
    assert bob_resp.status_code == 200

    # Token inválido falha com 401
    invalid_resp = client.get("/api/v1/podcasts", headers={"Authorization": "Bearer token_falso"})
    assert invalid_resp.status_code == 401


@patch("app.api.routes.podcasts.process_podcast_job")
def test_multi_tenant_job_isolation(mock_process: object) -> None:
    headers_alice = {"Authorization": "Bearer token_alice_123"}
    headers_bob = {"Authorization": "Bearer token_bob_456"}
    headers_admin = {"Authorization": f"Bearer {settings.api_token}"}

    # Alice cria uma tarefa
    resp = client.post(
        "/api/v1/podcasts",
        json={"title": "Podcast da Alice", "text": "Conteúdo secreto da Alice."},
        headers=headers_alice,
    )
    assert resp.status_code == 202
    alice_job_id = resp.json()["job_id"]

    # Alice consegue consultar sua tarefa
    status_alice = client.get(f"/api/v1/podcasts/{alice_job_id}", headers=headers_alice)
    assert status_alice.status_code == 200
    assert status_alice.json()["title"] == "Podcast da Alice"

    # Bob NÃO consegue consultar a tarefa da Alice (recebe 404, sem expor existência)
    status_bob = client.get(f"/api/v1/podcasts/{alice_job_id}", headers=headers_bob)
    assert status_bob.status_code == 404

    # Bob lista tarefas e a tarefa da Alice não aparece na lista dele
    list_bob = client.get("/api/v1/podcasts", headers=headers_bob)
    assert list_bob.status_code == 200
    bob_job_ids = [item["job_id"] for item in list_bob.json()]
    assert alice_job_id not in bob_job_ids

    # Alice lista tarefas e sua tarefa aparece
    list_alice = client.get("/api/v1/podcasts", headers=headers_alice)
    assert list_alice.status_code == 200
    alice_job_ids = [item["job_id"] for item in list_alice.json()]
    assert alice_job_id in alice_job_ids

    # Admin consegue consultar qualquer tarefa
    status_admin = client.get(f"/api/v1/podcasts/{alice_job_id}", headers=headers_admin)
    assert status_admin.status_code == 200


@pytest.mark.asyncio
async def test_download_blocks_path_traversal_to_auth_token() -> None:
    headers_admin = {"Authorization": f"Bearer {settings.api_token}"}

    # Simula um job que maliciosamente aponta para o master_token.json do Google
    malicious_path = (settings.notebooklm_auth_dir / "master_token.json").resolve()
    job = await job_manager.create_job(title="Tentativa de Vazamento")
    await job_manager.update_job_status(
        job_id=job.id,
        status=JobStatus.COMPLETED,
        message="Concluído.",
        audio_file_path=str(malicious_path),
        audio_file_name="master_token.json",
    )

    # O endpoint deve recusar o download e retornar 404 Not Found
    resp = client.get(f"/api/v1/podcasts/{job.id}/download", headers=headers_admin)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Arquivo de áudio não encontrado no disco do servidor."

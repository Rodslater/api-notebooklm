from datetime import datetime
from pydantic import BaseModel, Field, model_validator

from app.core.models import (
    PodcastFormat,
    PodcastJob,
    PodcastLength,
    VideoEngine,
    VideoFormat,
    VideoStyle,
)


class PodcastCreateRequest(BaseModel):
    """Corpo da requisição quando enviada como JSON."""

    title: str | None = Field(default=None, description="Título do podcast ou caderno.")
    text: str | None = Field(default=None, description="Texto base para a geração do podcast.")
    language: str = Field(default="pt", description="Código do idioma (ex: pt, en).")
    format: PodcastFormat = Field(default=PodcastFormat.BRIEF, description="Formato: brief, deep_dive, critique ou debate.")
    length: PodcastLength = Field(default=PodcastLength.DEFAULT, description="Duração: short, default ou long.")
    instructions: str | None = Field(default=None, description="Instruções extras para os apresentadores.")
    webhook_url: str | None = Field(default=None, description="URL de webhook para notificação ao finalizar.")
    cleanup_notebook: bool = Field(default=True, description="Exclui o caderno do Google após baixar o áudio.")
    generate_video: bool = Field(default=False, description="Gera vídeo sincronizado a partir do conteúdo.")
    video_engine: VideoEngine = Field(
        default=VideoEngine.NOTEBOOKLM,
        description="Motor do vídeo: notebooklm (nativo do Google) ou custom (esteira própria Pexels/FFmpeg).",
    )
    video_format: VideoFormat = Field(
        default=VideoFormat.EXPLAINER,
        description="Formato do vídeo nativo: explainer (Vídeo explicativo), brief (Resumo), cinematic (Cinematográfico) ou short (Curto).",
    )
    video_style: VideoStyle = Field(
        default=VideoStyle.AUTO_SELECT,
        description="Estilo visual do vídeo nativo: auto_select, classic, whiteboard, kawaii, anime, watercolor, retro_print, paper_craft, heritage, custom.",
    )
    video_style_prompt: str | None = Field(
        default=None,
        description="Instruções de estilo visual quando video_style for custom.",
    )
    video_badge: str | None = Field(default=None, max_length=60, description="Texto exibido no topo do cartão visual do vídeo (esteira custom).")

    @model_validator(mode="after")
    def validate_video_options(self) -> "PodcastCreateRequest":
        if self.generate_video and self.video_engine == VideoEngine.NOTEBOOKLM:
            if self.video_format == VideoFormat.SHORT:
                if self.video_style != VideoStyle.AUTO_SELECT or self.video_style_prompt:
                    raise ValueError(
                        "Vídeos no formato 'short' possuem estilo visual fixo e não aceitam video_style ou video_style_prompt."
                    )
            if self.video_format == VideoFormat.CINEMATIC and self.video_style_prompt:
                raise ValueError("Vídeos no formato 'cinematic' não aceitam video_style_prompt.")
            if self.video_style == VideoStyle.CUSTOM and not (
                self.video_style_prompt and self.video_style_prompt.strip()
            ):
                raise ValueError("O campo video_style_prompt é obrigatório quando video_style for 'custom'.")
            if self.video_style_prompt and self.video_style != VideoStyle.CUSTOM:
                raise ValueError("O campo video_style_prompt só pode ser informado quando video_style for 'custom'.")
        return self


class PodcastJobResponse(BaseModel):
    """Resposta padronizada sobre o estado de uma tarefa."""

    job_id: str
    title: str
    status: str
    status_message: str
    language: str
    format: str
    length: str
    audio_file_name: str | None = None
    audio_size_bytes: int | None = None
    generate_video: bool = False
    video_engine: str | None = None
    video_format: str | None = None
    video_style: str | None = None
    video_badge: str | None = None
    video_file_name: str | None = None
    video_size_bytes: int | None = None
    error_message: str | None = None
    status_url: str
    download_url: str | None = None
    video_download_url: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    @classmethod
    def from_domain(cls, job: PodcastJob, base_url: str = "") -> "PodcastJobResponse":
        clean_base = base_url.rstrip("/")
        status_url = f"{clean_base}/api/v1/podcasts/{job.id}" if clean_base else f"/api/v1/podcasts/{job.id}"
        download_url = (
            f"{clean_base}/api/v1/podcasts/{job.id}/download"
            if job.status.value == "completed" and clean_base
            else (f"/api/v1/podcasts/{job.id}/download" if job.status.value == "completed" else None)
        )
        video_download_url = (
            f"{clean_base}/api/v1/podcasts/{job.id}/download-video"
            if job.video_file_path and clean_base
            else (f"/api/v1/podcasts/{job.id}/download-video" if job.video_file_path else None)
        )

        return cls(
            job_id=job.id,
            title=job.title,
            status=job.status.value,
            status_message=job.status_message,
            language=job.language,
            format=job.format.value,
            length=job.length.value,
            audio_file_name=job.audio_file_name,
            audio_size_bytes=job.audio_size_bytes,
            generate_video=job.generate_video,
            video_engine=job.video_engine.value if job.generate_video else None,
            video_format=job.video_format.value if job.generate_video and job.video_engine == VideoEngine.NOTEBOOKLM else None,
            video_style=job.video_style.value if job.generate_video and job.video_engine == VideoEngine.NOTEBOOKLM else None,
            video_badge=job.video_badge,
            video_file_name=job.video_file_name,
            video_size_bytes=job.video_size_bytes,
            error_message=job.error_message,
            status_url=status_url,
            download_url=download_url,
            video_download_url=video_download_url,
            created_at=job.created_at,
            updated_at=job.updated_at,
            completed_at=job.completed_at,
        )


class HealthResponse(BaseModel):
    """Resposta do endpoint de verificação de saúde."""

    status: str
    authenticated: bool
    version: str

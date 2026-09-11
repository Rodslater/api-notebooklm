from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field
from notebooklm import AudioFormat, AudioLength


class JobStatus(str, Enum):
    QUEUED = "queued"
    CREATING_NOTEBOOK = "creating_notebook"
    UPLOADING_SOURCE = "uploading_source"
    GENERATING_AUDIO = "generating_audio"
    DOWNLOADING_AUDIO = "downloading_audio"
    COMPLETED = "completed"
    FAILED = "failed"


class PodcastFormat(str, Enum):
    BRIEF = "brief"
    DEEP_DIVE = "deep_dive"
    CRITIQUE = "critique"
    DEBATE = "debate"

    def to_notebooklm(self) -> AudioFormat:
        mapping = {
            PodcastFormat.BRIEF: AudioFormat.BRIEF,
            PodcastFormat.DEEP_DIVE: AudioFormat.DEEP_DIVE,
            PodcastFormat.CRITIQUE: AudioFormat.CRITIQUE,
            PodcastFormat.DEBATE: AudioFormat.DEBATE,
        }
        return mapping[self]


class PodcastLength(str, Enum):
    SHORT = "short"
    DEFAULT = "default"
    LONG = "long"

    def to_notebooklm(self) -> AudioLength:
        mapping = {
            PodcastLength.SHORT: AudioLength.SHORT,
            PodcastLength.DEFAULT: AudioLength.DEFAULT,
            PodcastLength.LONG: AudioLength.LONG,
        }
        return mapping[self]


class PodcastJob(BaseModel):
    """Representação interna de uma tarefa de geração de podcast."""

    id: str
    title: str
    status: JobStatus = JobStatus.QUEUED
    status_message: str = "Aguardando início do processamento."

    language: str = "pt"
    format: PodcastFormat = PodcastFormat.BRIEF
    length: PodcastLength = PodcastLength.DEFAULT
    instructions: str = ""

    webhook_url: str | None = None
    cleanup_notebook: bool = True

    notebook_id: str | None = None
    source_id: str | None = None
    task_id: str | None = None
    artifact_id: str | None = None

    audio_file_path: str | None = None
    audio_file_name: str | None = None
    audio_size_bytes: int | None = None

    error_message: str | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None

    def update_status(self, status: JobStatus, message: str) -> None:
        self.status = status
        self.status_message = message
        self.updated_at = datetime.now(timezone.utc)
        if status in (JobStatus.COMPLETED, JobStatus.FAILED):
            self.completed_at = self.updated_at

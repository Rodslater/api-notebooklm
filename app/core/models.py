from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field
from notebooklm import (
    AudioFormat,
    AudioLength,
    VideoFormat as NlmVideoFormat,
    VideoStyle as NlmVideoStyle,
)


class JobStatus(str, Enum):
    QUEUED = "queued"
    CREATING_NOTEBOOK = "creating_notebook"
    UPLOADING_SOURCE = "uploading_source"
    GENERATING_AUDIO = "generating_audio"
    DOWNLOADING_AUDIO = "downloading_audio"
    GENERATING_VIDEO = "generating_video"
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


class VideoEngine(str, Enum):
    NOTEBOOKLM = "notebooklm"
    CUSTOM = "custom"


class VideoFormat(str, Enum):
    EXPLAINER = "explainer"
    BRIEF = "brief"
    CINEMATIC = "cinematic"
    SHORT = "short"

    def to_notebooklm(self) -> NlmVideoFormat:
        mapping = {
            VideoFormat.EXPLAINER: NlmVideoFormat.EXPLAINER,
            VideoFormat.BRIEF: NlmVideoFormat.BRIEF,
            VideoFormat.CINEMATIC: NlmVideoFormat.CINEMATIC,
            VideoFormat.SHORT: NlmVideoFormat.SHORT,
        }
        return mapping[self]


class VideoStyle(str, Enum):
    AUTO_SELECT = "auto_select"
    CLASSIC = "classic"
    WHITEBOARD = "whiteboard"
    KAWAII = "kawaii"
    ANIME = "anime"
    WATERCOLOR = "watercolor"
    RETRO_PRINT = "retro_print"
    PAPER_CRAFT = "paper_craft"
    HERITAGE = "heritage"
    CUSTOM = "custom"

    def to_notebooklm(self) -> NlmVideoStyle:
        mapping = {
            VideoStyle.AUTO_SELECT: NlmVideoStyle.AUTO_SELECT,
            VideoStyle.CLASSIC: NlmVideoStyle.CLASSIC,
            VideoStyle.WHITEBOARD: NlmVideoStyle.WHITEBOARD,
            VideoStyle.KAWAII: NlmVideoStyle.KAWAII,
            VideoStyle.ANIME: NlmVideoStyle.ANIME,
            VideoStyle.WATERCOLOR: NlmVideoStyle.WATERCOLOR,
            VideoStyle.RETRO_PRINT: NlmVideoStyle.RETRO_PRINT,
            VideoStyle.PAPER_CRAFT: NlmVideoStyle.PAPER_CRAFT,
            VideoStyle.HERITAGE: NlmVideoStyle.HERITAGE,
            VideoStyle.CUSTOM: NlmVideoStyle.CUSTOM,
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
    owner_id: str = "admin"

    notebook_id: str | None = None
    source_id: str | None = None
    task_id: str | None = None
    artifact_id: str | None = None

    audio_file_path: str | None = None
    audio_file_name: str | None = None
    audio_size_bytes: int | None = None

    generate_video: bool = False
    video_engine: VideoEngine = VideoEngine.NOTEBOOKLM
    video_format: VideoFormat = VideoFormat.EXPLAINER
    video_style: VideoStyle = VideoStyle.AUTO_SELECT
    video_style_prompt: str | None = None
    video_badge: str | None = None
    video_file_path: str | None = None
    video_file_name: str | None = None
    video_size_bytes: int | None = None

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

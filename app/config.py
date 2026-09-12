from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações da aplicação carregadas de variáveis de ambiente."""

    api_token: str = "dev_token_notebooklm_2026"
    api_tokens: str = ""
    port: int = 8000
    host: str = "0.0.0.0"

    notebooklm_auth_dir: Path = Path("./data/auth")
    storage_dir: Path = Path("./storage")

    default_language: str = "pt"
    default_audio_format: str = "brief"
    default_audio_length: str = "default"
    default_instructions: str = (
        "Apresente em português brasileiro natural, descontraído e bem-humorado. "
        "Os apresentadores devem demonstrar carisma, usar tiradas inteligentes, analogias divertidas "
        "e manter a conversa leve e cativante, resumindo os pontos essenciais com clareza."
    )

    generation_timeout_seconds: float = 1200.0
    cleanup_notebook: bool = True

    # Configurações para geração de vídeo
    default_video_engine: str = "notebooklm"
    default_video_format: str = "explainer"
    default_video_style: str = "auto_select"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    pexels_api_key: str = ""
    openai_api_key: str = ""
    video_director_provider: str = "gemini"
    video_width: int = 1920
    video_height: int = 1080
    video_fps: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

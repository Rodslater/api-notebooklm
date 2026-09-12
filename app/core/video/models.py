from pathlib import Path
from pydantic import BaseModel


class VideoScene(BaseModel):
    """Representa um bloco visual sincronizado com a linha do tempo do áudio."""

    index: int
    start_sec: float
    end_sec: float
    topic: str
    search_query: str
    image_path: Path | None = None
    card_path: Path | None = None

    @property
    def duration_sec(self) -> float:
        """Duração do bloco em segundos, com piso de segurança de 1 segundo."""
        return max(1.0, self.end_sec - self.start_sec)

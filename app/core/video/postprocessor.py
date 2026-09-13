import logging
import re
import subprocess
from pathlib import Path
from PIL import Image

from app.core.video.renderer import get_ffmpeg_path

logger = logging.getLogger(__name__)


def get_video_duration(video_path: Path) -> float:
    """Extrai a duração exata do arquivo de vídeo em segundos via FFmpeg."""
    ffmpeg_exe = get_ffmpeg_path()
    res = subprocess.run(
        [ffmpeg_exe, "-i", str(video_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
    if not match:
        logger.warning("Não foi possível identificar a duração do vídeo %s.", video_path)
        return 0.0

    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def postprocess_native_video(
    video_path: Path,
    logo_path: Path | None = None,
    trim_seconds: float = 3.1,
) -> Path:
    """Aplica pós-processamento no vídeo nativo do NotebookLM.

    Remove a vinheta promocional final e sobrepõe a logo personalizada
    sobre a inscrição Gemini Notebook no canto inferior direito.
    """
    if not video_path.exists():
        logger.warning("Arquivo de vídeo %s não encontrado para pós-processamento.", video_path)
        return video_path

    ffmpeg_exe = get_ffmpeg_path()
    total_duration = get_video_duration(video_path)
    new_duration = max(1.0, total_duration - trim_seconds) if total_duration > (trim_seconds + 2.0) else None

    resolved_logo: Path | None = None
    if logo_path and Path(logo_path).exists():
        resolved_logo = Path(logo_path)

    temp_output = video_path.parent / f"processed_{video_path.name}"

    if resolved_logo:
        filtro_logo = "[1:v]scale=200:-2[logo];[0:v][logo]overlay=W-w-8:H-h-8"
        try:
            with Image.open(resolved_logo) as img:
                largura, _ = img.size
                if largura <= 250:
                    filtro_logo = "[0:v][1:v]overlay=W-w-8:H-h-8"
        except Exception as e:
            logger.warning("Não foi possível inspecionar dimensões da logo: %s", e)

        cmd = [
            ffmpeg_exe,
            "-y",
            "-i", str(video_path),
            "-i", str(resolved_logo),
        ]
        if new_duration is not None:
            cmd.extend(["-t", f"{new_duration:.3f}"])
        cmd.extend([
            "-filter_complex", filtro_logo,
            "-c:a", "copy",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "18",
            str(temp_output),
        ])
    else:
        cmd = [
            ffmpeg_exe,
            "-y",
            "-i", str(video_path),
        ]
        if new_duration is not None:
            cmd.extend(["-t", f"{new_duration:.3f}"])
        cmd.extend([
            "-c:a", "copy",
            "-c:v", "copy",
            str(temp_output),
        ])

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    if result.returncode == 0 and temp_output.exists() and temp_output.stat().st_size > 0:
        temp_output.replace(video_path)
        logger.info("Vídeo nativo pós-processado com sucesso: %s", video_path)
    else:
        logger.error("Falha ao pós-processar vídeo nativo via FFmpeg: %s", result.stderr[-400:])
        if temp_output.exists():
            temp_output.unlink(missing_ok=True)

    return video_path

import logging
import re
import shutil
import subprocess
from pathlib import Path
import imageio_ffmpeg

from app.core.video.models import VideoScene

logger = logging.getLogger(__name__)


def get_ffmpeg_path() -> str:
    """Retorna o caminho do executável do FFmpeg (sistema ou empacotado)."""
    system_path = shutil.which("ffmpeg")
    if system_path:
        return system_path
    return imageio_ffmpeg.get_ffmpeg_exe()


def get_audio_duration(audio_path: Path) -> float:
    """Extrai a duração exata do arquivo de áudio em segundos via FFmpeg."""
    ffmpeg_exe = get_ffmpeg_path()
    res = subprocess.run(
        [ffmpeg_exe, "-i", str(audio_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
    if not match:
        logger.warning("Não foi possível identificar a duração do áudio %s pelo FFmpeg.", audio_path)
        return 0.0

    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def render_scene_segment(
    scene: VideoScene,
    output_path: Path,
    fps: int = 30,
) -> Path:
    """Renderiza um segmento curto de vídeo com efeito Ken Burns e cartão do tópico."""
    if not scene.image_path or not scene.image_path.exists():
        raise FileNotFoundError(f"Imagem da cena {scene.index} não encontrada.")

    if not scene.card_path or not scene.card_path.exists():
        raise FileNotFoundError(f"Cartão da cena {scene.index} não encontrado.")

    ffmpeg_exe = get_ffmpeg_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    dur = scene.duration_sec
    total_frames = max(1, int(fps * dur))
    fade_dur = min(0.3, dur / 4)

    # Aplica zoom suave e fusão suave de entrada e saída
    filter_graph = (
        f"[0:v]zoompan=z='min(zoom+0.0008,1.15)':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"s=1920x1080:fps={fps},fade=t=in:st=0:d={fade_dur:.2f},fade=t=out:st={dur - fade_dur:.2f}:d={fade_dur:.2f}[bg]; "
        f"[bg][1:v]overlay=0:0[v]"
    )

    cmd = [
        ffmpeg_exe,
        "-y",
        "-i",
        str(scene.image_path),
        "-i",
        str(scene.card_path),
        "-filter_complex",
        filter_graph,
        "-map",
        "[v]",
        "-t",
        f"{dur:.2f}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    if result.returncode != 0:
        logger.error("Erro ao renderizar segmento %d: %s", scene.index, result.stderr[-400:])
        raise RuntimeError(f"FFmpeg falhou na renderização do segmento {scene.index}.")

    return output_path


def assemble_video(
    scenes: list[VideoScene],
    audio_path: Path,
    output_mp4: Path,
    temp_dir: Path,
    fps: int = 30,
) -> Path:
    """Renderiza os segmentos de cada cena e monta o vídeo final com a trilha de áudio."""
    temp_dir.mkdir(parents=True, exist_ok=True)
    segment_paths: list[Path] = []

    for scene in scenes:
        seg_file = temp_dir / f"seg_{scene.index:03d}.mp4"
        render_scene_segment(scene=scene, output_path=seg_file, fps=fps)
        segment_paths.append(seg_file)

    # Cria arquivo com lista de segmentos para o demuxer concat
    concat_list_file = temp_dir / "concat_list.txt"
    lines = [f"file '{seg.name}'" for seg in segment_paths]
    concat_list_file.write_text("\n".join(lines), encoding="utf-8")

    ffmpeg_exe = get_ffmpeg_path()
    output_mp4.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg_exe,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        concat_list_file.name,
        "-i",
        str(audio_path.resolve()),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(output_mp4.resolve()),
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        cwd=str(temp_dir),
    )
    if result.returncode != 0:
        logger.error("Erro ao concatenar segmentos do vídeo: %s", result.stderr[-400:])
        raise RuntimeError("FFmpeg falhou ao unir segmentos e áudio.")

    return output_mp4

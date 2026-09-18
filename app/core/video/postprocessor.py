import logging
import re
import subprocess
from pathlib import Path
from PIL import Image

from app.core.video.renderer import get_ffmpeg_path

logger = logging.getLogger(__name__)


def get_video_info(video_path: Path) -> dict:
    """Extrai metadados essenciais do vídeo (duração, resolução, taxa de quadros e áudio) via FFmpeg."""
    ffmpeg_exe = get_ffmpeg_path()
    res = subprocess.run(
        [ffmpeg_exe, "-i", str(video_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )

    duration = 0.0
    dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
    if dur_match:
        hours, minutes, seconds = dur_match.groups()
        duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    else:
        logger.warning("Não foi possível identificar a duração do vídeo %s.", video_path)

    width, height = 1920, 1080
    vid_match = re.search(r"Stream #\d+:\d+.*Video:.*?(\d{3,4})x(\d{3,4})", res.stderr)
    if vid_match:
        width, height = int(vid_match.group(1)), int(vid_match.group(2))

    fps = 30.0
    fps_match = re.search(r"(\d+(?:\.\d+)?)\s*fps", res.stderr)
    if fps_match:
        fps = float(fps_match.group(1))

    has_audio = bool(re.search(r"Stream #\d+:\d+.*Audio:", res.stderr))

    return {
        "duration": duration,
        "width": width,
        "height": height,
        "fps": fps,
        "has_audio": has_audio,
    }


def get_video_duration(video_path: Path) -> float:
    """Extrai a duração exata do arquivo de vídeo em segundos via FFmpeg."""
    info = get_video_info(video_path)
    return info["duration"]


def postprocess_native_video(
    video_path: Path,
    logo_path: Path | None = None,
    trim_seconds: float = 3.1,
    outro_path: Path | None = None,
) -> Path:
    """Aplica pós-processamento no vídeo nativo do NotebookLM.

    Remove a vinheta promocional final e sobrepõe a logo personalizada
    sobre a inscrição Gemini Notebook no canto inferior direito do vídeo principal,
    concatenando a vinheta de encerramento ao final.
    """
    if not video_path.exists():
        logger.warning("Arquivo de vídeo %s não encontrado para pós-processamento.", video_path)
        return video_path

    ffmpeg_exe = get_ffmpeg_path()
    main_info = get_video_info(video_path)
    total_duration = main_info["duration"]
    new_duration = max(1.0, total_duration - trim_seconds) if total_duration > (trim_seconds + 2.0) else None

    resolved_logo: Path | None = None
    if logo_path:
        p_logo = Path(logo_path)
        if p_logo.exists():
            resolved_logo = p_logo
        else:
            logger.warning("Arquivo de logo %s não encontrado para pós-processamento.", logo_path)

    resolved_outro: Path | None = None
    if outro_path:
        p_outro = Path(outro_path)
        if p_outro.exists():
            resolved_outro = p_outro
        else:
            logger.warning("Arquivo de encerramento %s não encontrado para pós-processamento.", outro_path)

    # Não anexa vinheta horizontal em vídeos verticais (shorts 9:16)
    if resolved_outro and main_info["height"] > main_info["width"]:
        logger.info(
            "Vídeo vertical detectado (%sx%s). Vinheta de encerramento horizontal não será anexada.",
            main_info["width"],
            main_info["height"],
        )
        resolved_outro = None

    temp_output = video_path.parent / f"processed_{video_path.name}"

    if resolved_outro:
        outro_info = get_video_info(resolved_outro)
        width, height = main_info["width"], main_info["height"]
        fps = main_info["fps"]

        inputs = ["-i", str(video_path)]
        logo_idx: int | None = None
        outro_idx = 1

        if resolved_logo:
            inputs.extend(["-i", str(resolved_logo)])
            logo_idx = 1
            outro_idx = 2

        inputs.extend(["-i", str(resolved_outro)])

        filter_parts: list[str] = []

        if new_duration is not None:
            trim_v = f"trim=0:{new_duration:.3f},setpts=PTS-STARTPTS"
            trim_a = f"atrim=0:{new_duration:.3f},asetpts=PTS-STARTPTS"
        else:
            trim_v = "setpts=PTS-STARTPTS"
            trim_a = "asetpts=PTS-STARTPTS"

        filter_parts.append(f"[0:v]{trim_v},fps={fps},setsar=1[v0_trimmed]")

        if resolved_logo and logo_idx is not None:
            logo_needs_scale = True
            try:
                with Image.open(resolved_logo) as img:
                    if img.size[0] <= 250:
                        logo_needs_scale = False
            except Exception as e:
                logger.warning("Não foi possível inspecionar dimensões da logo: %s", e)

            if logo_needs_scale:
                filter_parts.append(f"[{logo_idx}:v]scale=200:-2[logo_ready]")
                filter_parts.append("[v0_trimmed][logo_ready]overlay=W-w-8:H-h-8[v0_ready]")
            else:
                filter_parts.append(f"[v0_trimmed][{logo_idx}:v]overlay=W-w-8:H-h-8[v0_ready]")
        else:
            filter_parts.append("[v0_trimmed]null[v0_ready]")

        if main_info["has_audio"]:
            filter_parts.append(f"[0:a]{trim_a},aformat=sample_rates=48000:channel_layouts=stereo[a0_ready]")
        else:
            silence_dur = new_duration if new_duration is not None else (total_duration if total_duration > 0 else 1.0)
            filter_parts.append(f"aevalsrc=0:d={silence_dur:.3f},aformat=sample_rates=48000:channel_layouts=stereo[a0_ready]")

        filter_parts.append(
            f"[{outro_idx}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[v1_ready]"
        )

        if outro_info["has_audio"]:
            filter_parts.append(f"[{outro_idx}:a]aformat=sample_rates=48000:channel_layouts=stereo[a1_ready]")
        else:
            filter_parts.append(f"aevalsrc=0:d={outro_info['duration']:.3f},aformat=sample_rates=48000:channel_layouts=stereo[a1_ready]")

        filter_parts.append("[v0_ready][a0_ready][v1_ready][a1_ready]concat=n=2:v=1:a=1[outv][outa]")

        cmd = [
            ffmpeg_exe,
            "-y",
            *inputs,
            "-filter_complex", ";".join(filter_parts),
            "-map", "[outv]",
            "-map", "[outa]",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "18",
            "-c:a", "aac",
            str(temp_output),
        ]
    elif resolved_logo:
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

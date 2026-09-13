from pathlib import Path
from PIL import Image

from app.core.video.postprocessor import get_video_duration, postprocess_native_video
from app.core.video.renderer import get_ffmpeg_path


def test_postprocess_native_video_with_synthetic_clip(tmp_path: Path):
    ffmpeg_exe = get_ffmpeg_path()
    clip_path = tmp_path / "synthetic.mp4"

    # Gera um pequeno vídeo sintetizado de 6 segundos para teste via FFmpeg
    import subprocess
    cmd_gen = [
        ffmpeg_exe,
        "-y",
        "-f", "lavfi",
        "-i", "color=c=blue:s=320x240:d=6.0",
        "-f", "lavfi",
        "-i", "anullsrc=r=44100:cl=mono",
        "-t", "6.0",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-c:a", "aac",
        str(clip_path),
    ]
    subprocess.run(cmd_gen, check=True, capture_output=True)

    dur = get_video_duration(clip_path)
    assert 5.8 <= dur <= 6.2

    # Cria uma logo temporária
    logo_path = tmp_path / "logo.png"
    img = Image.new("RGBA", (100, 30), color=(255, 255, 255, 255))
    img.save(logo_path)

    # Processa: corta 3.1 segundos (duração esperada: 6.0 - 3.1 = 2.9s)
    processed = postprocess_native_video(
        video_path=clip_path,
        logo_path=logo_path,
        trim_seconds=3.1,
    )

    assert processed.exists()
    dur_after = get_video_duration(processed)
    assert 2.7 <= dur_after <= 3.1

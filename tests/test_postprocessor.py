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


def test_postprocess_native_video_with_outro_concatenation(tmp_path: Path):
    ffmpeg_exe = get_ffmpeg_path()
    clip_path = tmp_path / "synthetic_main.mp4"
    outro_path = tmp_path / "synthetic_outro.mp4"

    import subprocess
    # Gera clipe principal de 6.0 segundos
    cmd_main = [
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
    subprocess.run(cmd_main, check=True, capture_output=True)

    # Gera clipe de encerramento de 3.0 segundos
    cmd_outro = [
        ffmpeg_exe,
        "-y",
        "-f", "lavfi",
        "-i", "color=c=red:s=320x240:d=3.0",
        "-f", "lavfi",
        "-i", "anullsrc=r=44100:cl=mono",
        "-t", "3.0",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-c:a", "aac",
        str(outro_path),
    ]
    subprocess.run(cmd_outro, check=True, capture_output=True)

    logo_path = tmp_path / "logo.png"
    img = Image.new("RGBA", (80, 20), color=(255, 255, 255, 255))
    img.save(logo_path)

    # 6.0s - 3.1s de corte = 2.9s + 3.0s do encerramento = ~5.9s
    processed = postprocess_native_video(
        video_path=clip_path,
        logo_path=logo_path,
        trim_seconds=3.1,
        outro_path=outro_path,
    )

    assert processed.exists()
    dur_after = get_video_duration(processed)
    assert 5.7 <= dur_after <= 6.1


def test_postprocess_native_video_with_real_brasirc_outro(tmp_path: Path):
    real_outro = Path("app/assets/brasirc_video_encerramento.mp4")
    if not real_outro.exists():
        return

    ffmpeg_exe = get_ffmpeg_path()
    clip_path = tmp_path / "synthetic_main.mp4"

    import subprocess
    cmd_main = [
        ffmpeg_exe,
        "-y",
        "-f", "lavfi",
        "-i", "color=c=blue:s=1280x720:d=6.0",
        "-f", "lavfi",
        "-i", "anullsrc=r=48000:cl=stereo",
        "-t", "6.0",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-c:a", "aac",
        str(clip_path),
    ]
    subprocess.run(cmd_main, check=True, capture_output=True)

    # 6.0s - 3.1s = 2.9s + ~10.0s do encerramento oficial = ~12.9s
    processed = postprocess_native_video(
        video_path=clip_path,
        logo_path=None,
        trim_seconds=3.1,
        outro_path=real_outro,
    )

    assert processed.exists()
    dur_after = get_video_duration(processed)
    assert 12.5 <= dur_after <= 13.5

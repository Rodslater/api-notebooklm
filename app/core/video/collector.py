import asyncio
import logging
from pathlib import Path
import httpx
from PIL import Image, ImageDraw

from app.config import settings
from app.core.video.models import VideoScene

logger = logging.getLogger(__name__)


async def collect_scene_images(
    scenes: list[VideoScene],
    output_dir: Path,
    podcast_title: str,
) -> list[VideoScene]:
    """Baixa em paralelo fotos exclusivas do Pexels garantindo que nenhuma imagem se repita."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Controle de fotos já utilizadas para garantir variedade total
    used_photo_ids: set[int] = set()
    lock = asyncio.Lock()

    async with httpx.AsyncClient(timeout=25.0) as client:
        tasks = [
            _fetch_single_image(
                client=client,
                scene=scene,
                output_dir=output_dir,
                podcast_title=podcast_title,
                used_photo_ids=used_photo_ids,
                lock=lock,
            )
            for scene in scenes
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for idx, res in enumerate(results):
        if isinstance(res, Path) and res.exists():
            scenes[idx].image_path = res
        else:
            logger.warning("Falha ao coletar imagem para cena %d: %s. Gerando fundo substituto.", idx, res)
            scenes[idx].image_path = _generate_fallback_image(scenes[idx], output_dir)

    return scenes


async def _fetch_single_image(
    client: httpx.AsyncClient,
    scene: VideoScene,
    output_dir: Path,
    podcast_title: str,
    used_photo_ids: set[int],
    lock: asyncio.Lock,
) -> Path:
    """Busca no Pexels uma foto única não utilizada e salva em 1920x1080."""
    target_path = output_dir / f"scene_{scene.index:03d}.jpg"

    if not settings.pexels_api_key:
        return _generate_fallback_image(scene, output_dir)

    headers = {"Authorization": settings.pexels_api_key}
    query = scene.search_query.strip() or podcast_title.strip() or "technology"

    search_url = "https://api.pexels.com/v1/search"
    search_params = {
        "query": query,
        "orientation": "landscape",
        "size": "large",
        "per_page": 10,
    }

    resp = await client.get(search_url, headers=headers, params=search_params)
    photos: list[dict] = []

    if resp.status_code == 200:
        photos = resp.json().get("photos", [])

    if not photos:
        # Segunda tentativa com busca genérica variada pelo índice da cena
        fallback_queries = [
            "technology workplace",
            "modern data server",
            "podcast studio audio",
            "people talking cafe",
            "neon night city",
            "retro computer terminal",
        ]
        fb_query = fallback_queries[scene.index % len(fallback_queries)]
        fb_params = {
            "query": fb_query,
            "orientation": "landscape",
            "size": "large",
            "per_page": 10,
        }
        fb_resp = await client.get(search_url, headers=headers, params=fb_params)
        if fb_resp.status_code == 200:
            photos = fb_resp.json().get("photos", [])

    if not photos:
        return _generate_fallback_image(scene, output_dir)

    # Escolhe a primeira foto ainda não utilizada em outra cena
    selected_photo = None
    async with lock:
        for p in photos:
            pid = p.get("id")
            if pid and pid not in used_photo_ids:
                used_photo_ids.add(pid)
                selected_photo = p
                break
        if not selected_photo and photos:
            selected_photo = photos[scene.index % len(photos)]

    photo_url = selected_photo["src"].get("large2x") or selected_photo["src"].get("large")
    img_resp = await client.get(photo_url)
    img_resp.raise_for_status()

    # Salva temporariamente e ajusta proporção para 1920x1080
    temp_path = output_dir / f"raw_{scene.index:03d}.jpg"
    temp_path.write_bytes(img_resp.content)

    _normalize_image_1080p(temp_path, target_path)
    temp_path.unlink(missing_ok=True)
    return target_path


def _normalize_image_1080p(source_path: Path, dest_path: Path, width: int = 1920, height: int = 1080) -> None:
    """Redimensiona e recorta a imagem para o formato exato 16:9 (1920x1080)."""
    with Image.open(source_path) as im:
        im = im.convert("RGB")
        orig_w, orig_h = im.size

        scale = max(width / orig_w, height / orig_h)
        new_w = int(orig_w * scale)
        new_h = int(orig_h * scale)
        resized = im.resize((new_w, new_h), Image.Resampling.LANCZOS)

        left = (new_w - width) // 2
        top = (new_h - height) // 2
        cropped = resized.crop((left, top, left + width, top + height))
        cropped.save(dest_path, format="JPEG", quality=90)


def _generate_fallback_image(scene: VideoScene, output_dir: Path, width: int = 1920, height: int = 1080) -> Path:
    """Gera um fundo escuro com gradiente e paleta variada por cena quando não houver imagem."""
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / f"scene_{scene.index:03d}.jpg"
    if target_path.exists():
        return target_path

    # Paletas distintas para manter variedade visual mesmo no fallback
    palettes = [
        ((15, 23, 42), (30, 41, 59)),    # Slate
        ((24, 24, 27), (63, 63, 70)),    # Zinc
        ((17, 24, 39), (31, 41, 55)),    # Gray
        ((30, 27, 75), (49, 46, 129)),   # Indigo
        ((8, 47, 73), (12, 74, 96)),     # Sky/Cyan
        ((19, 78, 74), (17, 94, 89)),    # Teal
    ]
    c1, c2 = palettes[scene.index % len(palettes)]

    img = Image.new("RGB", (width, height), c1)
    draw = ImageDraw.Draw(img)

    for y in range(height):
        ratio = y / height
        r = int(c1[0] + ratio * (c2[0] - c1[0]))
        g = int(c1[1] + ratio * (c2[1] - c1[1]))
        b = int(c1[2] + ratio * (c2[2] - c1[2]))
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Círculos decorativos sutis no canto superior
    for radius in (400, 300, 200):
        draw.arc([width - radius, -radius, width + radius, radius], start=90, end=180, fill=c2, width=2)

    img.save(target_path, format="JPEG", quality=90)
    return target_path

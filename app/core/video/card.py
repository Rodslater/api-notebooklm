import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from app.core.video.models import VideoScene


def format_card_badge(podcast_title: str | None = None) -> str:
    """Formata o distintivo superior com a marca do canal e a data extraída do título."""
    if not podcast_title:
        return "BrasIRC Chatcast | #Brasil - 12/09/2026"

    match_br = re.search(r"(\d{2}/\d{2}/\d{4})", podcast_title)
    if match_br:
        return f"BrasIRC Chatcast | #Brasil - {match_br.group(1)}"

    match_iso = re.search(r"(\d{4})-(\d{2})-(\d{2})", podcast_title)
    if match_iso:
        ano, mes, dia = match_iso.groups()
        return f"BrasIRC Chatcast | #Brasil - {dia}/{mes}/{ano}"

    return "BrasIRC Chatcast"


def format_card_subtitle(podcast_title: str | None = None) -> str:
    """Formata o subtítulo com o canal e data quando necessário."""
    if not podcast_title:
        return "#Brasil - 12/09/2026"

    match_br = re.search(r"(\d{2}/\d{2}/\d{4})", podcast_title)
    if match_br:
        return f"#Brasil - {match_br.group(1)}"

    match_iso = re.search(r"(\d{4})-(\d{2})-(\d{2})", podcast_title)
    if match_iso:
        ano, mes, dia = match_iso.groups()
        return f"#Brasil - {dia}/{mes}/{ano}"

    return "#Brasil - 12/09/2026"


def _load_ui_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Carrega fonte TrueType com suporte a acentuação em português (Segoe UI, Arial, DejaVu Sans)."""
    candidates = (
        [
            "segoeuib.ttf",
            "arialbd.ttf",
            "DejaVuSans-Bold.ttf",
            "LiberationSans-Bold.ttf",
            "FreeSansBold.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
        if bold
        else [
            "segoeui.ttf",
            "arial.ttf",
            "DejaVuSans.ttf",
            "LiberationSans-Regular.ttf",
            "FreeSans.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    )

    for font_name in candidates:
        try:
            return ImageFont.truetype(font_name, size)
        except Exception:
            continue

    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def generate_topic_card(
    scene: VideoScene,
    output_path: Path,
    width: int = 1920,
    height: int = 1080,
    badge_text: str = "BrasIRC Chatcast",
    bottom_text: str | None = None,
) -> Path:
    """Gera um cartão gráfico transparente do terço inferior com identificação do canal e data."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    font_badge = _load_ui_font(size=18, bold=True)
    font_topic = _load_ui_font(size=26, bold=False)

    main_text = bottom_text.strip() if bottom_text else scene.topic.strip()
    if ":" in main_text:
        partes = main_text.split(":")
        if any(termo in partes[0].lower() for termo in ("podcast", "brasirc", "brasil", "2026")):
            main_text = partes[-1].strip()

    # Cálculo da largura necessária para a caixa
    try:
        badge_box = draw.textbbox((0, 0), badge_text, font=font_badge)
        topic_box = draw.textbbox((0, 0), main_text, font=font_topic)
        text_width = max(badge_box[2] - badge_box[0], topic_box[2] - topic_box[0])
    except Exception:
        text_width = 400

    card_padding_x = 28
    card_width = min(width - 160, max(420, text_width + card_padding_x * 2))
    card_height = 96
    card_x0 = 80
    card_y0 = height - 160
    card_x1 = card_x0 + card_width
    card_y1 = card_y0 + card_height

    # Fundo escuro semitransparente com borda sutil
    draw.rounded_rectangle(
        [card_x0, card_y0, card_x1, card_y1],
        radius=14,
        fill=(15, 23, 42, 225),
        outline=(59, 130, 246, 200),
        width=2,
    )

    # Barra de destaque lateral azul
    draw.rounded_rectangle(
        [card_x0, card_y0, card_x0 + 6, card_y1],
        radius=3,
        fill=(59, 130, 246, 255),
    )

    # Texto do distintivo superior
    draw.text(
        (card_x0 + card_padding_x, card_y0 + 16),
        badge_text,
        font=font_badge,
        fill=(147, 197, 253, 255),
    )

    # Texto principal inferior
    draw.text(
        (card_x0 + card_padding_x, card_y0 + 46),
        main_text,
        font=font_topic,
        fill=(255, 255, 255, 255),
    )

    image.save(output_path, format="PNG")
    return output_path
